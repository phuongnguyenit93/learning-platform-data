# Separating the Management Port and Evaluating Endpoint Access in Spring Boot

## 1. Problem to Solve

A Spring Boot application typically handles two distinct classes of HTTP traffic:

- **Business traffic:** customers, frontends, or external systems calling `/api/orders`, `/api/products`, logging in, downloading assets, and executing user-facing functionality.
- **Operational traffic:** Kubernetes, load balancers, Prometheus, monitoring platforms, or operators querying `health`, `readiness`, `metrics`, `info`, `loggers`, `mappings`, or other Actuator endpoints.

Placing every Actuator endpoint on the public port with wide exposure can leak configuration, bean graphs, routes, detailed metrics, or even runtime-mutating operations. Conversely, separating a management port **without restricting who can connect and which endpoints are exposed** still leaves risk.

This lesson focuses on two goals:

1. **Separating management HTTP traffic from application HTTP traffic when needed:** configuring `management.server.port`, bind address, base path, SSL, and understanding the limits of a separate port.
2. **Evaluating endpoint access across multiple layers:** whether the endpoint exists, whether it is exposed over HTTP, who is authorized to call it, and whether its response leaks sensitive information.

The main example uses **Spring Boot 3.5.16, Spring Framework 6.2.x, Spring Security 6.x, Java 17+, and Maven**. Business traffic runs on port `8080`, management runs on port `9091` bound strictly to `127.0.0.1`, `health` allows unauthenticated reads, `metrics` requires role `OPS`, and sensitive endpoints like `env`, `beans`, `loggers`, and `mappings` are never exposed.

**Core takeaway:** *Separating the port reduces attack surface; it is not an authentication or authorization mechanism.* Combine network policies, HTTP exposure, Actuator access controls, Spring Security, and multi-path testing.

## 2. What Is Spring Boot Actuator?

`spring-boot-starter-actuator` provides **observability and management** capabilities for your application. An endpoint ID is not necessarily its full URL: the default web mapping is `/actuator/{id}`. Common endpoints:

| Endpoint ID | Purpose | Sensitivity and notes |
| --- | --- | --- |
| `health` | Application health status and health contributors | Can be public at summary level; restrict `details` |
| `info` | Configured application metadata | Audit whatever data is placed into `info` |
| `metrics` | Micrometer meter list and measurements | Intended for operators; can reveal topology |
| `prometheus` | Prometheus metric exposition | Requires registry dependency and scraper access control |
| `httpexchanges` | Recent HTTP requests/responses | Requires a repository bean; potentially sensitive |
| `mappings` | Registered request mappings | Reveals routes and endpoints |
| `beans` | Beans in the Spring context | Reveals runtime architecture |
| `conditions` | Auto-configuration condition evaluation | Internal operational details |
| `configprops` | Configuration property values | Sanitized by default; can still be sensitive |
| `env` | Environment properties | Sanitized yet highly sensitive |
| `loggers` | View and modify runtime log levels | Supports runtime-mutating operations |
| `threaddump` | JVM thread dump | Can expose internal state and details |
| `heapdump` | JVM heap dump | Extremely sensitive; can contain secrets and user data |
| `shutdown` | Graceful application shutdown | Disabled by default; never expose to the Internet |

Not every ID works automatically upon adding Actuator. Several endpoints require extra dependencies, beans, or explicit access/exposure settings. For example, `prometheus` needs `micrometer-registry-prometheus`, and `httpexchanges` needs an `HttpExchangeRepository`. Having **Actuator on the classpath** does not mean every endpoint is active or exposed.

### 2.1. Security-Friendly Defaults

In **Spring Boot 3.5**, only the `health` endpoint is exposed over HTTP by default; Actuator does **not** automatically expose `env`, `beans`, `heapdump`, or `loggers` to the network. When Spring Security is on the classpath and **no custom `SecurityFilterChain` bean exists**, Boot auto-configures security to protect Actuator endpoints other than `health`.

However, once an application **defines its own `SecurityFilterChain`**, Boot's default security configuration backs off. You must explicitly review and secure **both Actuator and application APIs**, rather than assuming adding `spring-boot-starter-security` handles everything.

### 2.2. Two Distinct Observability Profiles

- **Read-only monitoring**: `health`, `readiness`, `metrics`. Typically polled automatically by scrapers and liveness probes.
- **Operations/management**: changing log levels, taking dumps, shutting down, inspecting `env`/`beans`, triggering actions. Needs far stricter controls and should never be enabled just because "we need metrics".

Separating these two use cases enforces least privilege. You can expose just `health,metrics` with zero state-mutating operations enabled.

## 3. Three Independent Control Layers: Access, Exposure, and Security

Spring Boot Actuator 3.5 includes **endpoint access levels** alongside exposure. When evaluating a URL, inspect all three layers:

1. **Endpoint access (`management.endpoint.<id>.access`)**: whether the endpoint/operations are allowed to exist at all (`none`, `read-only`, `unrestricted`).
2. **Exposure (`management.endpoints.web.exposure.include/exclude`)**: whether an allowed endpoint is exposed over **HTTP**. JMX has its own exposure policy.
3. **HTTP authentication/authorization (Spring Security, proxy, firewall)**: whether the caller is allowed to invoke an exposed endpoint—for instance, allowing anonymous `health` while requiring role `OPS` for `metrics`.

Diagram:

```text
Request GET /actuator/metrics
          |
          v
Actuator endpoint access policy
      (metrics: read-only?)
          |
          v
HTTP exposure list
      (metrics included?)
          |
          v
Network route / listener / firewall
      (management port reachable?)
          |
          v
Spring Security / proxy authorization
      (caller has ROLE_OPS?)
          |
          v
     Response metrics
```

This diagram illustrates the **logical sequence of checks**, not the literal execution order of filters. An endpoint disabled via `access=none` yields `404`; an exposed endpoint without login yields `401`; logged-in without the required role yields `403`. Proxies or `SecurityFilterChain` ordering can alter which status wins first, so verify logs and security rules.

### 3.1. Access Level (Boot 3.5)

```properties
management.endpoints.access.default=none
management.endpoint.health.access=read-only
management.endpoint.metrics.access=read-only
```

This adopts an **opt-in** posture: endpoints have no access by default, with only `health` and `metrics` granted read-only access. `read-only` permits read operations and blocks write/mutating operations.

You can also enforce a global ceiling:

```properties
management.endpoints.access.max-permitted=read-only
```

This caps the highest permitted access level application-wide; an endpoint cannot receive `unrestricted` access if global `max-permitted` is `read-only`. In Boot 3.5, `none` removes the endpoint from the application context completely rather than merely returning HTTP 403.

**Version distinction:** endpoint access-level properties are a Boot 3.4+ feature present in Boot 3.5. Do not apply `management.endpoints.access.default` to legacy Boot 2.x projects whose property metadata does not support it.

### 3.2. Web Exposure

```properties
management.endpoints.web.exposure.include=health,metrics
```

Only `health` and `metrics` are exposed over HTTP. Even if `management.endpoint.env.access=unrestricted`, omitting `env` from web exposure keeps `/actuator/env` unreachable over HTTP.

Beware:

```properties
management.endpoints.web.exposure.include=*
```

This is a **dangerous example if left uncontrolled**, and is not used in the main demo. It exposes every permitted and created endpoint; `management.endpoints.web.exposure.exclude` takes precedence over `include`. Never rely on excluding a handful of known endpoints and forget new endpoints introduced in future upgrades.

### 3.3. Spring Security

Inside a custom `SecurityFilterChain`, use Boot's matcher:

```java
http.securityMatcher(EndpointRequest.toAnyEndpoint())
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(EndpointRequest.to(HealthEndpoint.class))
        .permitAll()
        .anyRequest().hasRole("OPS"))
    .httpBasic(Customizer.withDefaults());
```

This is a **snippet**; see Section 9 for the full file. `EndpointRequest.toAnyEndpoint()` matches **Actuator endpoints**, not "every request hitting the management port". A non-Actuator URL on the management port falls through to subsequent filter chains—never assume you matched by **port** when matching only by **endpoint**.

### 3.4. Access Control Outcome Matrix

| Access | Exposed over HTTP? | Security | Expected result |
| --- | --- | --- | --- |
| `none` | Any | Any | Endpoint not created; URL has no valid endpoint |
| `read-only` | No | Any | Unreachable via HTTP; may exist on other channels if separately exposed |
| `read-only` | Yes | Permit anonymous | Allows GET/HEAD if operation permits |
| `read-only` | Yes | Require OPS | 401 unauthenticated, 403 missing role, 200 for valid OPS |
| `unrestricted` | Yes | Require OPS | Permits write operations **if endpoint supports them**; do not grant lightly |
| `unrestricted` | Yes | No network ACL | Reachable from external networks if listener is routable |
| `read-only` | Yes | Firewall allows monitoring CIDR only | Network-restricted, still requires security in depth against bypass |

**One control layer cannot substitute for the other two.** A separate port does not make unauthenticated endpoints private; an `OPS` role cannot save you if an application security matcher accidentally runs `permitAll` on the wrong path.

## 4. Separating the Management Port from the Application Port

### 4.1. Minimal Configuration

```properties
server.port=8080
management.server.port=9091
```

Regular application routes listen on `8080`, while Actuator HTTP endpoints listen on `9091` (with Actuator enabled). Spring Boot creates a **separate management web application context** with its own web server/dispatcher when a distinct management port is set.

Diagram:

```text
Client
    |
    +-----> :8080 (main application)
    |           /api/ping
    |           /api/orders
    |
    +-----> :9091 (management context)
                /actuator/health
                /actuator/metrics
```

Once separated, do not expect `http://localhost:8080/actuator/metrics` to remain active on the main port. However, **specific additional health paths** can intentionally be exposed on the main port, as shown in Section 7.

### 4.2. Binding Management to Loopback Only

```properties
management.server.port=9091
management.server.address=127.0.0.1
```

Spring Boot allows setting a management bind address **different** from the main server only when the management port is actually different. On a local host, `127.0.0.1` accepts connections from the same network namespace and **blocks** direct remote connections via public IPs.

Inside Docker/Kubernetes, however, container/pod loopback behaves differently. A Prometheus server in another pod **cannot** connect to `127.0.0.1` inside your container without a sidecar, forwarding, or port-forward. If metrics must be scraped across a monitoring namespace, bind to the pod interface and enforce **NetworkPolicy, firewalls, security groups, mTLS, and auth** instead of opening it publicly.

### 4.3. A Separate Management Port Is Not Complete Isolation

- Both listeners still run inside the same JVM/process, sharing heap, GC, business state, and dependencies.
- Management health can return 200 while the main servlet thread pool is saturated, so polling only the management port **misses main-listener outages**.
- If a firewall or ingress accidentally publishes port 9091, endpoints remain externally reachable.
- If a reverse proxy publicly forwards `/actuator/**` to 9091, binding management internally only protects against direct access, not the exposed proxy route.
- Moving management to another port never replaces TLS, role-based authorization, and audit logs.

### 4.4. Disabling HTTP Management Endpoints

If no management HTTP listener is needed:

```properties
management.server.port=-1
```

Or keep the listener while exposing zero HTTP endpoints:

```properties
management.endpoints.web.exposure.exclude=*
```

These two options are **not identical**: `port=-1` disables the HTTP management listener completely; `exclude=*` hides endpoints over HTTP while other channels/settings depend on config. Never set `management.server.port=-1` if your deployment relies on Actuator HTTP liveness/readiness probes.

## 5. Management Paths: `base-path` and `context-path`

### 5.1. Default Base Path

```properties
management.endpoints.web.base-path=/actuator
```

When management **shares the Servlet app port**, this path resolves relative to `server.servlet.context-path`. For example:

```properties
server.port=8080
server.servlet.context-path=/shop
management.endpoints.web.base-path=/actuator
```

Without port separation, the health URL becomes `http://localhost:8080/shop/actuator/health`.

### 5.2. When Management Uses a Different Port

```properties
server.port=8080
server.servlet.context-path=/shop

management.server.port=9091
management.server.base-path=/ops
management.endpoints.web.base-path=/actuator
```

The main port serves under `/shop`. The management port serves Actuator at `http://localhost:9091/ops/actuator/health` — **not** `/shop/ops/actuator/health`. Boot 3.5 documentation specifies that `management.endpoints.web.base-path` resolves relative to `management.server.base-path` when a separate management port is configured.

Keep them distinct:

| Property | Scope | Example |
| --- | --- | --- |
| `server.servlet.context-path` | Main Servlet app | `/shop` |
| `management.server.port` | Management listener | `9091` |
| `management.server.base-path` | Management web context (separate port only) | `/ops` |
| `management.endpoints.web.base-path` | Endpoint URL prefix | `/actuator` |
| `management.endpoints.web.path-mapping.health` | Renames just the health endpoint path | `healthcheck` |

### 5.3. Customizing Paths Is Not Security

Renaming `/actuator` to `/admin` or `/monitor` is merely **URL routing**—not a credential or network ACL. Scanners discover endpoints easily, and proxies can reverse-map paths.

```properties
management.endpoints.web.base-path=/manage
management.endpoints.web.path-mapping.health=healthcheck
```

Depending on `management.server.base-path`, health moves to `/manage/healthcheck` or `/ops/manage/healthcheck`. In security rules, prefer `EndpointRequest` over hardcoding `/actuator/**` so path changes never bypass security.

## 6. TLS and Network Policy for the Management Port

### 6.1. Separate SSL When Management Port Differs

Spring Boot supports configuring management TLS via `management.server.ssl.*` when management has its **own port**. Example with separate main HTTPS and management HTTPS certificates (illustrative, requires provisioned keystores):

```properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=file:/run/secrets/main.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=${MAIN_KEYSTORE_PASSWORD}

management.server.port=9443
management.server.ssl.enabled=true
management.server.ssl.key-store=file:/run/secrets/management.p12
management.server.ssl.key-store-type=PKCS12
management.server.ssl.key-store-password=${MANAGEMENT_KEYSTORE_PASSWORD}
```

No certificates are pre-generated in this lesson; this is a **production-style fragment, not for copying directly into the demo**. You need valid certificates/hostnames/trust chains, secret stores, and renewal. Spring Boot also supports SSL bundles; if using bundles, follow your exact Boot version and avoid mixing bundle properties arbitrarily with discrete keystore properties.

### 6.2. Local Management HTTP

In the demo project, management binds to `127.0.0.1:9091` over HTTP **strictly for local development**. Never send Basic credentials over plain HTTP across untrusted networks, as Basic auth is merely Base64-encoded without transport confidentiality.

In production, protect management traffic with **HTTPS/mTLS across networks**, using patterns such as:

- A scraper sidecar inside the same pod/host accessing loopback.
- A monitoring service in a private network locked down with NetworkPolicy/ACLs.
- An internal proxy enforcing mTLS, auth, and IP allowlists without public management routes.
- Authenticated, audited port-forwarding strictly for incident response.

Never open port `9091` on a public load balancer simply because Spring Security is enabled. Defense-in-depth requires **network segmentation + authentication + authorization + endpoint minimization**.

### 6.3. Testing Real Network Reachability

On a local Linux/macOS host:

```bash
curl -i http://127.0.0.1:9091/actuator/health
```

Connections targeting the machine's public IP will be **refused** when bound strictly to loopback. Still, never claim an endpoint is unreachable from the Internet until you have verified Docker port publishing, firewalls/security groups, Ingress rules, and proxies.

Note that Docker port mapping `-p 9091:9091` cannot make an in-container listener bound solely to `127.0.0.1` reachable from external hosts. To allow remote Prometheus scraping over the network, configure both the listener and security policies intentionally rather than merely publishing ports.

## 7. Health, Liveness, Readiness, and the Application Port

### 7.1. General Health

`GET /actuator/health` can return:

```json
{"status":"UP"}
```

This minimal response indicates the app and its health contributors are healthy. Status can become `DOWN`/`OUT_OF_SERVICE` with HTTP 503 under default mapping; never assume it always returns `200`.

`management.endpoint.health.show-details=never` avoids leaking database, disk, service-name, or stack details to unauthorized callers. Spring Boot 3.5 supports `never`, `when-authorized`, and `always`. In production, use `never` or `when-authorized` scoped to specific roles; never set `always` publicly.

### 7.2. Liveness vs. Readiness

- **Liveness**: is the app process still in a healthy state where a restart would help if it broke? Keep shared DB/Redis/downstream dependencies out to prevent fleet-wide restarts when a shared service blips.
- **Readiness**: can this specific instance accept business traffic right now? May verify essential local prerequisites, carefully weighing any external-service coupling.
- **Startup**: slow-starting applications can use a Kubernetes `startupProbe` to avoid premature liveness kills.

Spring Boot 3.5 provides `liveness` and `readiness` health groups backed by `ApplicationAvailability`:

```text
/actuator/health/liveness
/actuator/health/readiness
```

Outside Kubernetes, enable them explicitly:

```properties
management.endpoint.health.probes.enabled=true
```

### 7.3. Why Probing Only the Management Port Is Insufficient

When management and main app run on two separate web servers/contexts, `9091` can still return `UP` while main port `8080` cannot accept requests due to thread-pool saturation or connector failures. Spring Boot documentation recommends considering **additional probe paths on the main server port**:

```properties
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true
```

Result:

- Management port: `/actuator/health/liveness`, `/actuator/health/readiness`.
- **Main port:** `/livez` and `/readyz` (default additional paths).

Additional paths verify the main web listener, yet **still do not prove every endpoint, database, or business flow works**. Monitor live API errors and latency alongside probes.

### 7.4. Sample Kubernetes Probes

With the main app on 8080 and additional paths enabled:

```yaml
livenessProbe:
  httpGet:
    path: /livez
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
readinessProbe:
  httpGet:
    path: /readyz
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

This is a **container spec fragment** inside a Kubernetes Pod/Deployment container definition, not a standalone YAML manifest. Timings are illustrative; tune startup windows, timeouts, and `failureThreshold` to your SLOs.

If your app sets `server.servlet.context-path=/shop`, verify the actual URL of additional paths rather than blindly copying `/livez` from a root-path demo. And never place a shared DB dependency into the Kubernetes liveness check, as it can trigger cascading restarts.

### 7.5. Evaluating How Much Detail Health Should Return

| Caller | Appropriate visibility | Recommendation |
| --- | --- | --- |
| Internet/public LB | Minimal up/down if strictly needed | Hide components and internal hostnames |
| Kubelet | Liveness/readiness status | Additional paths on main port |
| Prometheus scraper | Permitted metrics | Restrict to monitoring network + valid credentials |
| SRE/ops | Detailed metrics, authorized logs | Role-based access + audit |
| Product users | Business APIs | No management internals needed |

A `"UP"` health check is not a security certification; it merely signals availability of the configured checks.

## 8. Designing Endpoint Authorization Around Real Needs

### 8.1. An Auditable Access Matrix

| Endpoint/path | Caller | Expected result | Rationale |
| --- | --- | --- | --- |
| `GET :8080/api/ping` | Unauthenticated | `200` | Demo public health-like app route |
| `GET :9091/actuator/health` | Unauthenticated on localhost | `200` when UP | Minimal health status |
| `GET :9091/actuator/metrics` | Unauthenticated | `401` | Only ops can read metrics |
| `GET :9091/actuator/metrics` | User with role OPS | `200` | Authorized operator |
| `GET :9091/actuator/env` | Even ops | Not exposed | Prevent sensitive data exposure |
| `GET :9091/actuator/beans` | Even ops | Not exposed | Reduce attack surface |
| `GET :9091/actuator/heapdump` | Even ops | Not enabled/exposed | Memory may hold secrets |
| `POST :9091/actuator/loggers/...` | Even ops | Not enabled/exposed | Prevent runtime logging tampering |
| `GET :8080/actuator/metrics` | Even ops | Not 200 | Actuator lives on management port |
| `GET :8080/livez`, `/readyz` | Kubelet/monitoring | `200` when healthy | Exercises main listener |

This access matrix is **specific to the demo project**, not a universal default for every app. Update tests whenever URLs, roles, security chains, or proxies change.

### 8.2. Three Tests to Distinguish Failure Modes

- **401 Unauthorized**: endpoint is exposed, authentication is missing. Basic auth typically includes `WWW-Authenticate: Basic`.
- **403 Forbidden**: caller is recognized but lacks permission; can also result from missing CSRF on unsafe methods, WAF/proxy rules, or explicit `denyAll`.
- **404 Not Found**: endpoint does not exist, is unexposed, or has no mapping; a security chain may also intercept before the router returns 404.

Never assume "404 = completely secure". A route returning 404 on the public listener could still be reachable on a private listener or via JMX if configured.

### 8.3. HTTP Basic Is Only a Demo Mechanism

The demo defines user `ops` with role `OPS` and reads the password from an environment variable. Basic auth over **local loopback HTTP** simply demonstrates `401`/`200` behavior; production must use TLS/mTLS and a managed identity provider. Never hardcode passwords, paste tokens/passwords into logs/chat, or leave `permitAll` on metrics when a port is network-reachable.

## 9. Complete Demo: Spring Boot 3.5.16 with Main 8080 and Management 9091

### 9.1. Structure

```text
management-boundary-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/management/
    │   │   ├── ManagementBoundaryApplication.java
    │   │   ├── PingController.java
    │   │   └── SecurityConfiguration.java
    │   └── resources/
    │       └── application.properties
    └── test/
        └── java/com/example/management/
            └── ManagementPortTest.java
```

The project runs **Spring MVC** on embedded Tomcat. Boot/Actuator configures the separate management port automatically without custom Tomcat connectors.

### 9.2. `pom.xml`

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

    <groupId>com.example</groupId>
    <artifactId>management-boundary-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

With Actuator and Spring Security starters, `EndpointRequest` and `HealthEndpoint` are available. `starter-test` includes JUnit and `TestRestTemplate` for HTTP integration tests. Jersey/WebFlux and Prometheus dependencies are omitted since the demo uses the built-in `metrics` endpoint; add the Prometheus registry separately if `/actuator/prometheus` is needed.

### 9.3. Main Class

File `src/main/java/com/example/management/ManagementBoundaryApplication.java`:

```java
package com.example.management;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ManagementBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManagementBoundaryApplication.class, args);
    }
}
```

### 9.4. Business Endpoint

File `src/main/java/com/example/management/PingController.java`:

```java
package com.example.management;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class PingController {

    @GetMapping("/ping")
    public Map<String, String> ping() {
        return Map.of("message", "pong");
    }
}
```

Route on **main port**: `http://localhost:8080/api/ping` returns JSON `{"message":"pong"}` when healthy. It is a simple business route—not an Actuator endpoint—used to compare network paths.

### 9.5. Security Configuration with Two Filter Chains

File `src/main/java/com/example/management/SecurityConfiguration.java`:

```java
package com.example.management;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain actuatorSecurity(HttpSecurity http)
            throws Exception {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(
                                EndpointRequest.to(HealthEndpoint.class))
                        .permitAll()
                        .anyRequest().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/ping").permitAll()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            @Value("${demo.ops.password}") String password,
            PasswordEncoder encoder) {
        UserDetails ops = User.withUsername("ops")
                .password(encoder.encode(password))
                .roles("OPS")
                .build();
        return new InMemoryUserDetailsManager(ops);
    }
}
```

**How to read this configuration:**

- `@Order(1)` evaluates the Actuator matcher first: `health` is public, while all other Actuator endpoints require `ROLE_OPS`.
- `EndpointRequest.toAnyEndpoint()` matches **Actuator endpoint mappings** (including links and additional health paths where applicable); it does **not match every arbitrary URL on port 9091**.
- `@Order(2)` acts as the fallback chain for application requests: `/api/ping` is permitted and everything else is `denyAll`. This is a **strictly narrowed demo policy**, not a general rule for production APIs.
- The two chains are **not automatically port-specific chains**—selection uses request matchers. An unknown path hitting the management listener can fall through to the application chain; verify real statuses rather than assuming every unknown path returns 404.
- Defining custom `SecurityFilterChain` beans disables Spring Boot's default auto-configured security, so you must explicitly define rules for application routes as shown here.
- `BCryptPasswordEncoder` hashes the password in memory at startup instead of storing plaintext credentials. Even so, **Basic auth headers on plain HTTP remain visible** without transport encryption—use only on local loopback demos.
- `User.withUsername(...).roles("OPS")` grants authority `ROLE_OPS`, matching `hasRole("OPS")`. Do not write `hasRole("ROLE_OPS")`, which doubles the prefix.

**CSRF:** because the demo exposes only GET/HEAD read operations, default CSRF protection remains enabled. When exposing `POST`/`PUT`/`DELETE` operations like `loggers` or `shutdown`, review CSRF and authorization explicitly—never disable CSRF globally just to bypass a 403.

### 9.6. Complete `application.properties`

File `src/main/resources/application.properties`:

```properties
spring.application.name=management-boundary-demo

# Main application listener
server.port=8080

# Separate management listener, local-only for demo
management.server.port=9091
management.server.address=127.0.0.1

# Actuator web path: /actuator/{id}
management.endpoints.web.base-path=/actuator

# Opt-in: only create selected read-only endpoints
management.endpoints.access.default=none
management.endpoint.health.access=read-only
management.endpoint.metrics.access=read-only
management.endpoints.access.max-permitted=read-only

# Expose only two endpoints over HTTP
management.endpoints.web.exposure.include=health,metrics

# Never disclose health details
management.endpoint.health.show-details=never

# Probe paths on management, plus /livez and /readyz on main port
management.endpoint.health.probes.enabled=true
management.endpoint.health.probes.add-additional-paths=true

# Require password from environment; no production fallback
demo.ops.password=${OPS_PASSWORD}
```

**No real password is stored in the file.** If `OPS_PASSWORD` is unset, startup intentionally fails due to the unresolved placeholder. Provide the password via environment variable when running; this single in-memory user is strictly for demos, not production administration.

**Important:** `management.server.address=127.0.0.1` means the metrics listener accepts loopback connections within the current host/process network namespace only. In a cluster, verify scraping topology before copying this setting.

### 9.7. Building and Running Locally

Bash/Linux/macOS:

```bash
export OPS_PASSWORD='local-example-secret-only'
mvn clean package
java -jar target/management-boundary-demo-1.0.0.jar
```

PowerShell:

```powershell
$env:OPS_PASSWORD = 'local-example-secret-only'
mvn clean package
java -jar target/management-boundary-demo-1.0.0.jar
```

Run in the directory containing `pom.xml` with JDK 17+ and Maven. Ports 8080 and 9091 must be free. These commands are development examples; `local-example-secret-only` is **not a production secret**. In real systems, use a secret manager and keep passwords out of shell history.

### 9.8. Testing the Business Route on the Main Port

```bash
curl -i http://127.0.0.1:8080/api/ping
```

When successful:

```http
HTTP/1.1 200
Content-Type: application/json

{"message":"pong"}
```

This is an abbreviated response; Spring Security and the server may add `Cache-Control`, `X-Content-Type-Options`, and other headers. JSON key ordering does not matter here.

### 9.9. Public Health on the Management Port

```bash
curl -i http://127.0.0.1:9091/actuator/health
```

When healthy, typical response:

```http
HTTP/1.1 200
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
```

`Content-Type` may vary with parameters or `Accept` negotiation; status and body are what matter. If health is `DOWN`, HTTP returns 503. Health has `permitAll` in the Actuator chain, yet **remains reachable only from loopback** because of the management bind address.

### 9.10. Metrics Requires Role `OPS`

Without credentials:

```bash
curl -i http://127.0.0.1:9091/actuator/metrics
```

Expect **HTTP 401 Unauthorized**, typically with `WWW-Authenticate: Basic`. Unauthenticated callers cannot read metric names or measurements.

Supply Basic credentials interactively so curl prompts for the password rather than exposing it in the command line:

```bash
curl --user ops -i http://127.0.0.1:9091/actuator/metrics
```

Enter `OPS_PASSWORD` when prompted. Expect **HTTP 200** and JSON containing a `names` array of JVM/HTTP metrics depending on runtime. **Exact metric names are not fixed** across differing classpaths, traffic, or configs.

Never use Basic auth over plain HTTP in production. Over TLS, target `https://...` with proper certificate verification.

### 9.11. Sensitive Endpoints Are Not Exposed

```bash
curl -i http://127.0.0.1:9091/actuator/env
curl -i http://127.0.0.1:9091/actuator/beans
curl -i http://127.0.0.1:9091/actuator/loggers
curl -i http://127.0.0.1:9091/actuator/shutdown
```

None of these URLs have **exposed Actuator handlers in the demo**. Because of the fallback `SecurityFilterChain`, responses may be `403` instead of `404`; the QA criterion is **never returning 200 data and never executing management operations**, even when supplying `OPS` credentials. Never rely on a single HTTP status code to confirm an endpoint is disabled when custom security filters can intercept earlier.

### 9.12. Verifying Both Ports Stay Distinct

```bash
curl -i http://127.0.0.1:8080/actuator/metrics
curl -i http://127.0.0.1:9091/api/ping
```

Neither URL serves the corresponding content. `metrics` exists only on the management context, and the business controller exists only on the main app. Due to fallback security, wrong-port requests may return 401/403/404; **do not assume only 404 is valid**.

### 9.13. Additional Probes on the Main Port

```bash
curl -i http://127.0.0.1:8080/livez
curl -i http://127.0.0.1:8080/readyz
curl -i http://127.0.0.1:9091/actuator/health/liveness
curl -i http://127.0.0.1:9091/actuator/health/readiness
```

When healthy/ready, all four endpoints succeed with health group data. Liveness/readiness return `DOWN`/503 during startup, shutdown, or detected failures. `/livez` and `/readyz` appear on the main port because of `management.endpoint.health.probes.add-additional-paths=true`, **not** because Actuator leaked onto the main port.

## 10. Real HTTP Testing with Two Random Ports

The test below checks access across **two separate listeners** rather than `MockMvc` alone. `MockMvc` exercises the Spring MVC filter/controller pipeline without proving a second management web server actually bound and served requests.

File `src/test/java/com/example/management/ManagementPortTest.java`:

```java
package com.example.management;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalManagementPort;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "management.server.port=0",
                "management.server.address=127.0.0.1",
                "demo.ops.password=test-only-secret"
        })
class ManagementPortTest {

    @LocalServerPort
    int appPort;

    @LocalManagementPort
    int managementPort;

    @Autowired
    TestRestTemplate http;

    private String app(String path) {
        return "http://127.0.0.1:" + appPort + path;
    }

    private String mgmt(String path) {
        return "http://127.0.0.1:" + managementPort + path;
    }

    @Test
    void mainBusinessRouteWorks() {
        ResponseEntity<String> result =
                http.getForEntity(app("/api/ping"), String.class);
        assertEquals(HttpStatus.OK, result.getStatusCode());
        assertTrue(result.getBody().contains("pong"));
    }

    @Test
    void healthAllowsAnonymousOnManagementPort() {
        ResponseEntity<String> result =
                http.getForEntity(
                        mgmt("/actuator/health"), String.class);
        assertEquals(HttpStatus.OK, result.getStatusCode());
        assertTrue(result.getBody().contains("UP"));
    }

    @Test
    void metricsRequireOpsAuthentication() {
        String url = mgmt("/actuator/metrics");

        ResponseEntity<String> anonymous =
                http.getForEntity(url, String.class);
        assertEquals(HttpStatus.UNAUTHORIZED,
                     anonymous.getStatusCode());

        ResponseEntity<String> ops =
                http.withBasicAuth("ops", "test-only-secret")
                    .getForEntity(url, String.class);
        assertEquals(HttpStatus.OK, ops.getStatusCode());
        assertTrue(ops.getBody().contains("names"));
    }

    @Test
    void sensitiveEndpointIsNotReadableEvenWithOps() {
        ResponseEntity<String> result =
                http.withBasicAuth("ops", "test-only-secret")
                    .getForEntity(
                            mgmt("/actuator/env"), String.class);
        assertNotEquals(HttpStatus.OK, result.getStatusCode());
    }

    @Test
    void metricsAreNotExposedOnMainPort() {
        ResponseEntity<String> result =
                http.withBasicAuth("ops", "test-only-secret")
                    .getForEntity(
                            app("/actuator/metrics"), String.class);
        assertNotEquals(HttpStatus.OK, result.getStatusCode());
    }

    @Test
    void livenessAlsoChecksMainWebListener() {
        ResponseEntity<String> result =
                http.getForEntity(app("/livez"), String.class);
        assertEquals(HttpStatus.OK, result.getStatusCode());
    }
}
```

### 10.1. Why Does the Test Need `@LocalManagementPort`?

- `@SpringBootTest(webEnvironment=RANDOM_PORT)` picks a **random main port**.
- `management.server.port=0` picks a **random management port**, avoiding port 9091 conflicts in CI.
- `@LocalServerPort` and `@LocalManagementPort` inject the bound ports after startup; the two numbers differ.
- `TestRestTemplate` sends real HTTP over TCP to each listener, exercising security filters, sessions, and the management context.
- The `env` test asserts **not 200**, since `access=none` and non-exposure combine with fallback security which may yield different non-200 statuses.
- `metricsRequireOpsAuthentication` verifies both negative (anonymous) and positive (`OPS`) authorization.
- `test-only-secret` is a fixed **test-context-only** value never used in real environments.

Run from the directory containing the POM:

```bash
mvn test
```

This is a smoke/integration test template; full security validation should also test wrong roles, disallowed HTTP methods, inbound gateways, TLS, NetworkPolicies, rate limits, and audit logs.

### 10.2. Testing a User Without the `OPS` Role

In real systems, use Spring Security test users or a test identity provider to define a regular user (role `USER`). Verify that user receives **403 Forbidden** when calling metrics after authenticating, complementing the anonymous 401 and `OPS` 200 cases. The minimal demo defines only `ops` to avoid complex identity-provider setup.

This is a suggested additional test, not a claim that a regular user already exists in the demo code.

## 11. Evaluating Management Port Security in Production

### 11.1. Threat Model

When opening management endpoints, evaluate at least:

- **External attackers** scanning for `/actuator`, brute-forcing credentials, or exploiting misconfigurations.
- **Compromised workloads** in the same private subnet reaching port 9091 if network policies are overly permissive.
- **Insiders** authorized for monitoring who should not inspect `env`, `heapdump`, or `shutdown`.
- **Service accounts / scrapers** needing metrics/health without permission to change log levels.
- **Reverse proxies/Ingress** accidentally publishing management paths or stripping auth headers.
- **Supply-chain vulnerabilities** requiring timely patches to Actuator/runtime libraries.
- **Sensitive data leakage** via `env`, `configprops`, `beans`, `mappings`, `logfile`, `heapdump`, `httpexchanges`, or high-cardinality metric tags.
- **Denial of service** via expensive thread/heap dumps or excessive metrics scrape frequencies.

Define security principals, allowed network sources, endpoint IDs, permitted operations, and retention/audit policies per role.

### 11.2. Least Privilege

**Role design example:**

| Role | Need | Policy to consider |
| --- | --- | --- |
| Anonymous/Kubelet | Detail-free liveness/readiness | Health/probes only, restricted network |
| Metrics scraper | Read metrics | Dedicated identity + read-only endpoints |
| SRE read-only | View metrics, info, possibly internal mappings | Authenticated read-only, audited |
| SRE privileged | Adjust log levels during incidents | Strictly scoped, time-approved, audited |
| Runtime admin | Dumps/shutdown | Rarely exposed over HTTP; use dedicated ops tooling |

Never grant broad `ROLE_OPS` to every pod just so Prometheus can scrape metrics. Separate scraper and SRE identities/matchers and test negative permissions.

### 11.3. CORS Does Not Replace Authentication

Browser CORS only governs whether cross-origin JavaScript can read responses; it never blocks `curl`, backend-to-backend clients, proxies, or attackers. `management.endpoints.web.cors.allowed-origins` may assist internal cross-origin dashboards, yet **never** replaces Spring Security, network ACLs, token validation, or mTLS. Never enable wildcard CORS with credentials on Actuator.

### 11.4. CSRF with State-Changing Operations

Spring Security enables CSRF protection by default on unsafe HTTP methods. Actuator `POST`/`PUT`/`DELETE` operations can return 403 even with the right role if a CSRF token is missing, depending on chain/CSRF config.

Never "fix" this by disabling CSRF across the entire app. If Actuator is called purely machine-to-machine with tokens/mTLS and no browser cookies, evaluate a narrowly scoped policy on the management chain. Because the demo **exposes no write operations**, CSRF remains intact.

### 11.5. Auditing and Monitoring

For privileged management endpoints:

- Log **who** called, **endpoint ID**, result status, trusted client IP, request ID, and timestamp.
- Never log Basic `Authorization` headers, bearer tokens, cookies, or heap dump contents.
- Monitor `401`/`403` spikes, requests to denied endpoints, and anomalous network sources.
- Set SLOs for scrape availability and p95 response latency.
- Periodically verify from **unauthorized networks** that the management listener/route is unreachable.
- Re-audit ingress, load balancers, and cloud firewalls after every deployment, not just when editing code.

## 12. Management Port Separation Across WebFlux and Runtimes

### 12.1. Spring MVC

The main example uses the Servlet stack on Tomcat. Boot creates the separate management listener, and security uses a Servlet `SecurityFilterChain` with `EndpointRequest`. Main-port additional health paths let probes traverse the same web infrastructure as business traffic.

### 12.2. Spring WebFlux

Spring WebFlux typically runs on Reactor Netty and uses **`SecurityWebFilterChain`**, not Servlet `HttpSecurity`/`SecurityFilterChain`. Securing reactive Actuator requires reactive APIs and matchers—such as `EndpointRequest` from Boot's reactive security package.

Follow the principle, **never copy MVC Java security source verbatim into WebFlux**. Properties `management.server.port`, `management.endpoints.web.exposure.include`, and `management.endpoint.health.*` map conceptually, though always verify docs for your reactive runtime.

### 12.3. Two Servers Do Not Equal Two Processes

A Spring Boot app listening on `8080` and `9091` is normally **one JVM hosting two web application contexts**. Both still share process-level failure modes. Stronger isolation of resources, OS privileges, or networking requires process/deployment-level boundaries rather than `management.server.port` alone.

### 12.4. Spring Boot Versioning

Do not copy Boot **4.x** package imports into a Boot 3.5 project. In Boot 3.5, the Servlet matcher import is:

```java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
```

Newer Boot releases may relocate packages and alter default policies. Always **re-test configuration** after upgrades—especially access levels, endpoint mappings, security chain ordering, `management.server.base-path`, SSL, and test helpers.

## 13. Diagnosing 401, 403, 404, and Network Failures

| Symptom | Possible cause | Verification check |
| --- | --- | --- |
| `/actuator/health` returns 404 on 8080 | Management port separated | Query `127.0.0.1:9091` at the right path |
| Cannot connect to 9091 from another host | Bound to loopback or firewalled | Check listen address and network namespace |
| Prometheus pod cannot connect to 9091 | Different pod network; management bound to loopback | Use sidecar/NetworkPolicy or protected interface binding |
| 404 on management despite Actuator dependency | `access=none`, unexposed, or wrong path | Check `access`, `exposure`, and `base-path` |
| 401 on `/actuator/metrics` | Missing Basic auth | Send credentials to the right listener (TLS in production) |
| 403 despite valid credentials | Missing `OPS` role or security chain/CSRF | Inspect authorities, matchers, HTTP method |
| 200 on `/actuator/env` | Sensitive endpoint exposed / misconfigured access | Narrow `include`/`access`, audit Security |
| 404 instead of 401 on invalid URL | Route doesn't exist or security filtered differently | Check HTTP path and owning handler |
| 503 on `/actuator/health` | Health is `DOWN`/`OUT_OF_SERVICE` | Inspect health contributors carefully |
| Health 200 while API returns 503 | Management context healthy, main listener/downstream failing | Probe `/readyz` on main port; track business SLOs |
| Metrics 200 yet Prometheus cannot scrape | Wrong DNS/NetworkPolicy/proxy/TLS/cert or target config | Test from the scraper's network namespace |
| 401 via proxy despite 200 locally | Proxy stripped auth header or rewrote path | Compare headers/correlation ID per hop |
| `/actuator/prometheus` 404 | Missing Prometheus registry or unexposed | Add registry and configure policy if needed |
| `/actuator/loggers` POST 403 | CSRF, missing role, or `read-only` access | Check access level, method, CSRF; never disable CSRF globally |
| Browser reports CORS error | Origin disallowed; can mask underlying 401/403 | Inspect Network tab and raw HTTP response |
| Main context path `/shop` breaks health URL | Confused main context path with `management.server.base-path` | Check path composition per port |
| Management port changes during tests | `management.server.port=0` | Inject `@LocalManagementPort` |
| Compile error after major Boot upgrade | Package/API namespace changed | Consult docs/JavaDoc for exact Boot version |

### 13.1. Never Guess from a Single Status Code

A `401` from Spring Security differs from a `401` from a reverse proxy. A `403` can come from CSRF or authorization. A `404` can mean a properly disabled endpoint—or a wrong URL, port, or base-path. A `503` on health can mean a `DOWN` contributor—or a gateway error. Always identify **who emitted the response** via headers/logs and test at each hop.

## 14. Verifying with Operational Tools

### 14.1. Listening Sockets

On Linux, useful tools include:

```bash
ss -lntp
curl -i http://127.0.0.1:8080/api/ping
curl -i http://127.0.0.1:9091/actuator/health
```

Confirm listener `9091` binds specifically to `127.0.0.1`. Minimal containers may lack `ss`; use `netstat` or platform inspection tools instead.

### 14.2. Docker

Example launching a container publishing only the main app port:

```bash
docker run --rm -p 8080:8080 my-management-demo:local
```

This is an **illustrative command assuming you built `my-management-demo:local`**, not a required Maven demo step. When management binds `127.0.0.1` inside a container, only processes in that same network namespace can reach it directly. **Never** publish port 9091 uncontrollably.

Building a production image requires your own build pipeline; this lesson creates no Dockerfile and assumes no pre-built image exists.

### 14.3. Kubernetes Services and NetworkPolicy

A public Service should route **only the main app port**. If monitoring needs management access:

- Create an internal-only `Service`/`ServiceMonitor`/`PodMonitor` per platform conventions.
- Write a `NetworkPolicy` permitting only the monitoring namespace/pod selector on the management TCP port.
- Use TLS/mTLS/identities across untrusted networks.
- Never expose the management port on an Internet-facing Ingress.
- Monitor traffic sources and verify unauthorized namespaces are blocked.

Setting a separate port is an application config knob—it **does not create a `NetworkPolicy` by itself**.

### 14.4. Prometheus

`/actuator/metrics` is Actuator's JSON metrics API, **distinct** from `/actuator/prometheus`. To scrape OpenMetrics/Prometheus text format, add the registry dependency:

```xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
```

and add `prometheus` to your managed access and exposure policies:

```properties
management.endpoint.prometheus.access=read-only
management.endpoints.web.exposure.include=health,metrics,prometheus
```

This is an **extension fragment**, not part of the running demo. When enabling Prometheus, verify Spring Security matchers/rules for scraper identity and network restrictions. Never enable wildcard exposure just to get one scraper working.

### 14.5. Testing Network Boundaries from Outside

Never run `curl` on `localhost` alone and declare the port private. Test from an **unauthorized** host/pod under authorized organizational security testing:

- Confirm public LBs and Ingress have no route to 9091.
- Confirm `NetworkPolicy` and security groups actually drop unauthorized traffic.
- Confirm reverse proxies do not accidentally expose `/actuator/**` on 8080.
- Check port forwarding, published host ports, and DNS aliases.
- Audit network/security logs and confirm zero credentials appear in tool output.

## 15. Deployment Checklist for HTTP Security and Observability

### 15.1. Pre-Deploy

- [ ] Identify which Actuator endpoints are genuinely needed: `health`, `metrics`, `info`, or `prometheus`.
- [ ] Decide whether a dedicated management port is needed and who scrapes/manages it.
- [ ] Configure `management.server.port` appropriately; if setting `management.server.address`, ensure port differs from main.
- [ ] Bind only permitted addresses and never expose management to the Internet.
- [ ] Verify `management.server.base-path` and `management.endpoints.web.base-path` together.
- [ ] Set `management.endpoints.access.default=none` for strict opt-in if desired.
- [ ] Grant `read-only` per approved endpoint and cap `max-permitted` when no write operations are needed.
- [ ] List only required endpoints in `management.endpoints.web.exposure.include`.
- [ ] Audit JMX exposure separately if JMX is active and requires protection.
- [ ] Ensure Spring Security allows anonymous `health`, authenticates `metrics`/ops, and checks exact roles/authorities.
- [ ] When defining custom filter chains, declare full rules for app routes without relying on Boot defaults.
- [ ] Keep `env`, `beans`, `heapdump`, `shutdown`, and `loggers` closed unless explicitly justified and secured.
- [ ] Ensure `management.endpoint.health.show-details` never leaks details anonymously.
- [ ] Test liveness/readiness health groups and main-port additional paths.
- [ ] Enforce TLS/mTLS or secure proxies for management HTTP across untrusted networks.
- [ ] Never hardcode Basic passwords/secrets; rotate credentials and audit usage.
- [ ] Never rely on wildcard CORS as an authentication substitute.
- [ ] Include negative tests for anonymous callers, insufficient roles, unexposed endpoints, and wrong ports.
- [ ] Run smoke tests from both the monitoring network and an unauthorized network.
- [ ] Audit Ingress/LB/cloud firewalls/NetworkPolicies, not just `application.properties`.
- [ ] Keep endpoint logs/metrics free of PII and high-cardinality tags.
- [ ] After Boot patch/major upgrades, re-test statuses, paths, matchers, listeners, roles, and JMX exposure.

### 15.2. Post-Deploy

- [ ] Main business routes function without interference from Actuator rules.
- [ ] Health returns 200 when UP and `DOWN`/503 when components genuinely fail.
- [ ] Metrics returns 401 anonymously and 200 for authorized `OPS`/scrapers over the intended network.
- [ ] `env`, `beans`, `heapdump`, and `shutdown` are inaccessible.
- [ ] Port 9091 is unreachable from the public Internet.
- [ ] Main port serves `/livez` and `/readyz` if using additional paths.
- [ ] Kubelet/Prometheus are not locked out by misconfigured `127.0.0.1` binding for your topology.
- [ ] Verify reloads, restarts, rolling deployments, and health transitions.
- [ ] Monitor audit logs for 401/403 spikes and probe/scrape anomalies.
- [ ] Maintain runbooks for lost `OPS` access, TLS errors, network policy blocks, and port conflicts.

## 16. Scenario Exercises and Solutions

### Scenario A — Port Separated, Yet Actuator Remains Public

An app sets `management.server.port=9091`, yet Ingress publishes both 8080 and 9091 to the Internet, `env` is added to web exposure, and security sets `permitAll`.

**Analysis:** separating ports creates no security boundary if routing remains public. Shrink exposure/access, block at Ingress/firewall, enforce authentication, and test from the Internet—do not merely change 9091 to another number.

### Scenario B — Prometheus Cannot Scrape

`management.server.address=127.0.0.1` while Prometheus runs in a separate pod. Connections are refused.

**Analysis:** loopback lives strictly inside the pod's network namespace. To scrape across the pod network, bind an appropriate interface/Service protected by `NetworkPolicy`/mTLS/auth, or run a sidecar in the same pod—never strip all network controls blindly.

### Scenario C — Health 200 While Users Hit Errors Across the Entire API

The independent management listener stays healthy, while the main Servlet thread pool is exhausted.

**Analysis:** never treat management `/actuator/health` alone as proof the main web app accepts traffic; enable additional `/livez`/`/readyz` on the main port and monitor business requests. Avoid putting shared external dependencies into liveness where they cause fleet-wide restarts.

### Scenario D — Security Starter Present, Yet Metrics Are Public

The app defines a custom `SecurityFilterChain` with `anyRequest().permitAll()`. Boot's auto-configured security backs off.

**Analysis:** the custom chain replaced default protection. Add `EndpointRequest.toAnyEndpoint()` with role rules plus a dedicated chain for remaining app routes, backed by negative tests.

### Scenario E — `/actuator/env` Returns 404 Despite `OPS` User

`management.endpoints.web.exposure.include=health,metrics` and `management.endpoints.access.default=none`.

**Analysis:** `env` has no access and is not exposed. This is the intended behavior, not a broken `OPS` role. Never expose the endpoint just to satisfy a faulty test expectation.

### Scenario F — Metrics Returns 401 in Browser While `curl` Returns 200

`curl` passed Basic auth; browser `fetch` omitted credentials and lacked valid CORS setup.

**Analysis:** inspect actual `Authorization` and `Origin` headers, preflights, `Allow-Origin`, and Security chains. CORS never replaces auth, and never open credentialed wildcard CORS on metrics.

### Scenario G — Changing Management Base Path Makes Health Disappear

The app added:

```properties
management.server.base-path=/ops
management.endpoints.web.base-path=/actuator
```

**Analysis:** with a separate management port, the active URL became `/ops/actuator/health`. Update monitor/scraper targets and smoke tests.

### Scenario H — SRE Has `OPS` Role, Yet `POST loggers` Returns 403

CSRF may be active; `loggers` may lack `unrestricted` access or exposure; or roles may be mis-mapped.

**Analysis:** inspect **access → exposure → Security/CSRF → HTTP method/operation**. Never disable CSRF app-wide and never grant `unrestricted` access carelessly just to "see if it works".

### Scenario I — Endpoint on Management Port Doesn't Match `EndpointRequest`

`GET /unknown` on 9091 is not an Actuator endpoint.

**Analysis:** `EndpointRequest.toAnyEndpoint()` matches Actuator mappings only, so requests may hit the fallback filter chain. If you need a policy spanning the entire management listener, evaluate management-context matchers/chains and test them—never treat `toAnyEndpoint()` as a port matcher.

### Scenario J — Upgrading and Copying Newer Imports by Mistake

Copying Boot 4 docs into a Boot 3.5 project breaks compilation because `EndpointRequest` moved packages.

**Analysis:** reference docs/JavaDoc matching version 3.5.16, inspect the Maven dependency tree, and keep the Boot BOM consistent. Major upgrades require migration guides and regression testing.

## 17. Self-Assessment Questions

1. **What does `management.server.port` do?** Creates an HTTP management listener on a separate port when configured differently from `server.port`.
2. **Does separating the port automatically enforce login?** No. Security and network policies are separate layers.
3. **Can `management.server.address` differ from the main server when sharing the same port?** No, it requires a separate management port.
4. **What does Actuator expose over HTTP by default in Boot 3.5?** `health`.
5. **How does `management.endpoints.access.default=none` differ from `web.exposure.exclude=*`?** The first prevents endpoints from being created in the context; the second hides them from HTTP exposure.
6. **Does `read-only` access on `loggers` permit changing log levels?** No, only read operations.
7. **Does `EndpointRequest.toAnyEndpoint()` match every URL on the management port?** No, it matches Actuator endpoints.
8. **How does a custom `SecurityFilterChain` affect Boot's default security?** Boot's auto-configured security backs off; the app must protect all routes explicitly.
9. **Why are there two security chains in the example?** Separate rules for Actuator endpoints and a fallback policy for application routes.
10. **Is `management.server.base-path` the same as `management.endpoints.web.base-path`?** No; paths compose differently depending on context and port separation.
11. **Can Prometheus in another pod reach `127.0.0.1` inside a container?** Not directly; requires appropriate network topology or sidecar forwarding.
12. **Is Basic auth over plain HTTP outside trusted networks safe?** No. Use TLS/mTLS or a secure proxy.
13. **Do `/actuator/metrics` and `/actuator/prometheus` share the same format?** No; Prometheus requires its own registry dependency and exposure.
14. **Does HTTP 200 on management-port health prove the main app is healthy?** Not completely; there are two separate web infrastructures.
15. **Why add additional probe paths?** So liveness/readiness checks exercise the main web listener.
16. **Should a shared database be added to liveness?** Usually not, to avoid restarting all replicas during an external outage.
17. **Why never expose `heapdump` publicly?** It can contain secrets/sensitive data and consumes heavy resources.
18. **If an endpoint returns 404, is it guaranteed to be secured by roles?** No; it may simply not exist or be unexposed.
19. **When anonymous `metrics` returns 401, what does that mean?** HTTP Security requires authentication.
20. **What defines completion when deploying a management port?** Endpoint minimization, access policy, auth, network ACL/TLS, accurate probe targets, positive/negative tests, and live verification.

## 18. Official Documentation

- [Spring Boot 3.5 — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/3.5/reference/actuator/monitoring.html): management port/address/base-path/SSL and disabling HTTP endpoints.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): endpoint access levels, web/JMX exposure, Spring Security, health groups, and Kubernetes probes.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `management.server.*`, `management.endpoint.*`, `management.endpoints.*`.
- [Spring Boot 3.5 — Actuator How-to](https://docs.spring.io/spring-boot/3.5/how-to/actuator.html): changing HTTP port/address for Actuator.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest(RANDOM_PORT)`, `TestRestTemplate`, and integration tests.
- [Spring Boot 3.5.16 — LocalManagementPort JavaDoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/web/server/LocalManagementPort.html): retrieving the random management port in tests.
- [Spring Boot 3.5.16 — EndpointRequest JavaDoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html): matching Actuator endpoints instead of the whole port.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request matchers and role-based authorization.
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF for mutating operations.
- [Kubernetes — Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): designing health probes at the orchestration layer.

**Conclusion:** `management.server.port` and `management.server.address` provide **network path separation**; `management.endpoints.access.*` and `management.endpoints.web.exposure.*` govern which endpoints exist on each channel; Spring Security and network policies decide **who is actually permitted to call them**. Whenever running the management context on a separate port, test **both ports**, expose main-port liveness/readiness probes where appropriate, and confirm sensitive endpoints remain **completely inaccessible** before going to production.