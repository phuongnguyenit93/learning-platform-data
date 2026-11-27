# Isolating Management Endpoints from Public Traffic

## 1. Why Does API Gateway Management Need a Separate Access Plane?

In a microservices architecture, **Spring Cloud Gateway Server WebFlux** typically listens for user HTTP traffic on a public port, evaluates **route predicates**, runs the **filter chain**, transforms paths/headers, and forwards to backends via fixed URLs or service discovery `lb://service-id`. This is the **data plane**: every client request must pass through appropriate authentication, authorization, rate limiting, circuit breakers, retries, TLS, and observability rules.

Inside the same application, **Spring Boot Actuator** can expose HTTP endpoints serving the **control/management plane**: checking health, exporting metrics, listing routes, inspecting filters, and—when permitted—refreshing or modifying routes. These endpoints are valuable to SREs, monitoring systems, and deployment pipelines, yet **must never appear as public APIs for general users**.

Dangerous configuration example:

~~~text
Internet
   |
   v
https://api.example.test
   |
   v
Gateway :8080
   +-- /api/orders/**             → orders-service
   +-- /actuator/gateway/routes   → lists internal routes
   +-- /actuator/gateway/refresh  → can refresh routes
   +-- /actuator/env              → can expose config metadata
~~~

Without proper protection layers, an attacker can discover internal routes/hosts, probe system details, apply load through diagnostic endpoints, or—when write access is misconfigured—alter routes to cause **SSRF, open proxying, or security filter bypasses**.

This lesson belongs to the **Actuator Management** chapter of the `SPRING_CLOUD_GATEWAY` module and focuses on a critical operational requirement: **separating management traffic from public traffic through multiple independent, verifiable boundaries**.

After this lesson, you will be able to:

1. Distinguish the public API port from the monitoring/administration port.
2. Use `management.server.port` and `management.server.address` under the right conditions.
3. Distinguish **endpoint access**, **web exposure**, **Spring Security**, and **network controls**.
4. Set the `gateway` endpoint to **read-only**, avoiding accidentally exposing route create/delete/refresh operations.
5. Test from both inside and outside, rather than relying on the status of a single `curl` command.
6. Design Kubernetes Ingress/Service/NetworkPolicy or VM firewalls/reverse proxies.
7. Understand the risks of probes, proxy-route bypasses, TLS, logs/metrics, and dynamic management permissions.

> **Scope:** Examples use **Spring Cloud Gateway Server WebFlux** and Spring Boot Actuator in matching release lines. Gateway Server MVC differs in its filter system and configuration properties. Never treat these configurations as license to expose management endpoints to the Internet.

## 2. A Management Endpoint Has Four Distinct Control Layers

Never equate “Spring Security is enabled” with “the endpoint is isolated”. An endpoint should only be reachable when every relevant layer allows it.

| Control Layer | Question | Examples |
| --- | --- | --- |
| **Network reachability** | Can the client connect to the management port? | Loopback bind, private interface, firewall, Service/NetworkPolicy |
| **Endpoint access** | Does the endpoint exist and which operation types are allowed? | `management.endpoint.gateway.access=read-only` |
| **Transport exposure** | Is the endpoint published over HTTP/JMX? | `management.endpoints.web.exposure.include=health,gateway` |
| **Identity & authorization** | Who is the caller really, and what role do they hold? | Spring Security Reactive, mTLS, RBAC, service identity |

Decision model:

~~~mermaid
flowchart TD
    C["HTTP client"] --> N{"Can reach management port?"}
    N -->|"No"| X["Connection denied / unreachable"]
    N -->|"Yes"| E{"Endpoint enabled and exposed?"}
    E -->|"No"| F["Endpoint not found / unpublished"]
    E -->|"Yes"| S{"Caller authenticated<br/>with sufficient role?"}
    S -->|"No"| A["401 or 403"]
    S -->|"Yes"| P{"Operation permitted?"}
    P -->|"Read operation"| R["Read health/routes/metrics"]
    P -->|"Disallowed mutation"| D["Deny POST/DELETE/WRITE"]
    P -->|"Permitted mutation, strict policy"| W["Strictly inside management plane"]
~~~

**Note:** Specific responses may be 401, 403, 404, 405, or connection errors depending on the blocking layer and version. What matters is that public clients **cannot use sensitive endpoints**, rather than forcing every blocked path to return the same status code.

### 2.1. Access Is Not Authentication

For example:

~~~properties
management.endpoint.gateway.access=read-only
~~~

means write management operations on the `gateway` endpoint are not registered at the **endpoint operation** level. It does **not** automatically authenticate who reads the route list. If that endpoint remains reachable from the Internet without Security, route URIs or metadata can still leak.

### 2.2. Exposure Is Not Write Permission

For example:

~~~properties
management.endpoints.web.exposure.include=health,gateway
~~~

specifies which endpoints appear over HTTP. It does not decide whether `/gateway/refresh` is permitted to execute. Read/write capabilities depend on the access level and Security policies. Conversely, setting `access=unrestricted` without HTTP exposure does not make the endpoint a public web API, though JMX or other channels may still exist if configured.

### 2.3. Renaming `/actuator` Is Not Isolation

~~~yaml
management:
  endpoints:
    web:
      base-path: /_private_ops
~~~

changes `/actuator/health` to `/_private_ops/health`. This is merely a **path namespace change**—it has none of the protections of a firewall, authentication, or authorization. Attackers can guess, scan paths, or read leaked configs; never rely on “secret URLs” for defense.

## 3. Recognizing Sensitivity Levels Across Actuator Endpoints

| Endpoint / Group | Primary Purpose | Risk If Public |
| --- | --- | --- |
| `health`, `health/liveness`, `health/readiness` | Health checks / probes | Leaks component details if `show-details` is overly broad; subject to constant scanning |
| `info` | Version, build, app metadata | Leaks versions or deployment details if over-configured |
| `metrics` / `prometheus` | Monitoring | Reveals topology, labels, operational metrics; scraping adds load |
| `gateway/routes`, `gateway/globalfilters` | Inspecting routes and filters | Reveals internal URIs, filter ordering, service names |
| `gateway/refresh` and route add/delete ops | Dynamic route management | Can enable bypasses, SSRF/open proxying, or DoS |
| `env`, `configprops`, `beans`, `mappings` | Runtime diagnostics | Reveals app structure and config metadata, even when many values are sanitized |
| `loggers` | Read/change log levels | If writable, can enable DEBUG/TRACE and leak sensitive headers/bodies |
| `heapdump`, `threaddump`, `logfile` | Memory/thread/log analysis | Can contain tokens, personal data, and sensitive payloads |
| `shutdown` | Stop process (if enabled) | Immediate service outage |

This list does not mean every endpoint is enabled by default. In Spring Boot 3.5/4.x, **default web exposure normally includes only `health`**. The `gateway` endpoint has its own access rules and is recommended by Gateway docs to be **`read-only`** when observation is needed. High-risk endpoints like `shutdown`/`heapdump` are restricted by default and should never be opened casually for testing.

### 3.1. Two Use-Case Groups Should Have Different Policies

- **Minimal probes:** liveness/readiness serve workload orchestration. They should return minimal data and not depend on credentials that kubelet/health checkers cannot supply.
- **Advanced observation/management:** routes, detailed metrics, configs, and route changes. Permit only authenticated, explicitly authorized observability agents/operators over the management network.

For Prometheus, `prometheus` exists only when the corresponding exporter/registry dependency is present; adding the endpoint name to exposure without the dependency does not create the endpoint.

## 4. Target Architecture: Two Ports, Two Network Paths

~~~mermaid
flowchart LR
    U["Internet / Mobile / Browser"] --> EDGE["Public Ingress / WAF<br/>TLS + auth + rate limiting"]
    EDGE --> API["Gateway WebFlux<br/>:8080 public API"]
    API --> B["Backend services<br/>route/filter/lb://"]
    OPS["Operators / Monitoring<br/>private identity"] --> FW["VPN / Private network<br/>Firewall + RBAC / mTLS"]
    FW --> MGMT["Actuator management listener<br/>:9090 private/loopback"]
    MGMT -.->|"same application, separate listener"| API
    X["Public clients"] -.- NOT["No route to :9090"]
~~~

On a local machine, binding the management listener to **127.0.0.1** lets the application and local tools access it. In Kubernetes or multi-network VMs, bind to an appropriate **private IP**/address and enforce network ACLs/NetworkPolicies.

**A separate port alone is not enough:** if a firewall/Ingress still forwards port 9090 from the Internet, the endpoint is not isolated. Likewise, merely writing a deny `/actuator/**` rule on public Ingress can be defeated if the base path changes or if the Gateway itself defines a route pointing to the management listener. Verify the **actual physical/virtual network paths**.

### 4.1. Management Port vs. Application Port

Two pairs of example addresses:

~~~text
Public / lab API       http://127.0.0.1:8080/api/ping
Local management       http://127.0.0.1:9090/actuator/health
Public external        https://api.example.test/api/orders
Private control plane  https://mgmt.internal.example.test/actuator/gateway/routes
~~~

In production, the management listener should only have a dedicated hostname/service on a private network. Do not treat an “internal” DNS name as a standalone control if the underlying IP/port remains reachable from the Internet.

## 5. Baseline Configuration: Spring Boot 3.5/4.x + Gateway Server WebFlux

Spring Boot lets Actuator run on a separate port with `management.server.port` and bind to a specific address with `management.server.address`. **Per documentation, a management address different from the application address can only be configured when the management port differs from the main port.**

### 5.1. Read-Only Lab Configuration Example

`src/main/resources/application.yml`:

~~~yaml
server:
  address: 127.0.0.1
  port: 8080

spring:
  application:
    name: secure-gateway-actuator-lab

management:
  server:
    address: 127.0.0.1
    port: 9090

  # Only endpoints explicitly declared below receive access.
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,info,gateway"
    jmx:
      exposure:
        exclude: "*"

  endpoint:
    health:
      access: read-only
      show-details: never
    info:
      access: read-only
    gateway:
      access: read-only
~~~

Key points:

1. **API and management run on two separate ports.** Both bind loopback for a safe lab; in production, the API can bind public/private interfaces behind ingress per infra design while management needs a private network.
2. `management.endpoints.access.default=none` enforces **deny by default** at the actuator endpoint level.
3. `management.endpoints.access.max-permitted=read-only` caps the maximum level, preventing accidental write enablement via per-endpoint overrides.
4. Only `health`, `info`, and `gateway` get read access; all other endpoints remain disabled under this configuration.
5. `exposure.include` exposes strictly those three endpoints over HTTP; `jmx.exposure.exclude="*"` shrinks the JMX management surface when unused.
6. `show-details: never` avoids exposing component health details to any caller in this lab.
7. `gateway.access: read-only` **provides no route create, delete, or refresh operations**.

The `management.endpoint.<id>.access`, `management.endpoints.access.default`, and `max-permitted` properties are documented in Spring Boot 3.5/4.x. On older releases, property names or semantics may differ; cross-check configuration metadata for your **exact Boot patch** instead of applying unrecognized properties.

> **Do not misunderstand:** This config isolates at the **local network** level and shrinks the endpoint surface, yet **does not build an admin identity system on its own**. On a multi-user/multi-process host, another local process can still call `127.0.0.1:9090` if OS policies allow. Production requires authentication, RBAC, and network isolation.

### 5.2. Gateway WebFlux 4.2/4.3 vs. 5.x

The **Gateway routes** namespace differs across release lines:

| Component | Gateway Server WebFlux 4.2/4.3 | Gateway Server WebFlux 5.x |
| --- | --- | --- |
| Route YAML | `spring.cloud.gateway.routes` | `spring.cloud.gateway.server.webflux.routes` |
| Gateway starter (patch-dependent) | `spring-cloud-starter-gateway` or WebFlux-specific starter | `spring-cloud-starter-gateway-server-webflux` |
| Actuator management port | `management.server.port` | `management.server.port` |
| Actuator access/read-only | Provided by **Spring Boot**; verify Boot version | Provided by **Spring Boot**; verify Boot version |
| Gateway actuator | `management.endpoint.gateway.access=read-only` per docs | Same access model; requires HTTP exposure |

Never define Route YAML in both the old and new namespaces simultaneously. **Changing the route namespace does not move the Actuator listener port.** Keep Spring Boot, Spring Security, and Spring Cloud aligned via compatible BOMs rather than bumping one artifact independently.

### 5.3. When an HTTP Management Listener Is Unneeded

If an organization uses other observability tools or wants no HTTP Actuator endpoints:

~~~yaml
management:
  server:
    port: -1
~~~

Spring Boot allows disabling the HTTP management server via `management.server.port=-1`. Alternatively, exclude everything from HTTP exposure:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        exclude: "*"
~~~

These differ in implementation; choose based on health-check and monitoring requirements. If JMX or other transports remain active, evaluate that management surface separately.

### 5.4. Changing `base-path` Is Not a Defense Line

~~~yaml
management:
  endpoints:
    web:
      base-path: /_ops
~~~

When management uses a separate port, `base-path` resolves relative to `management.server.base-path`. On a shared port, it resolves relative to the web stack's context/base path. This helps avoid endpoint name collisions, yet **never replaces security**. Keep one consistent path across tests and reverse proxy rules.

## 6. Lab: API Port 8080 and Actuator Only on 9090

This lab needs **one Gateway WebFlux application with Actuator**. To avoid building a separate backend just to test two listeners, we add a small endpoint directly on the Gateway. This endpoint **is not meant to replace proxied routes**—it merely verifies the data port is alive.

### 6.1. Maven Dependencies

For recent Gateway Server WebFlux releases:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
~~~

The Spring Cloud BOM must match Spring Boot. This example **omits Spring Security initially** to test network isolation by itself; we add the security layer in Section 8. Never run this unauthenticated configuration on a management port reachable from untrusted networks.

### 6.2. Spring Boot Application

`src/main/java/demo/gateway/ManagementIsolationApplication.java`:

~~~java
package demo.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ManagementIsolationApplication {
    public static void main(String[] args) {
        SpringApplication.run(ManagementIsolationApplication.class, args);
    }
}
~~~

`src/main/java/demo/gateway/PingController.java`:

~~~java
package demo.gateway;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PingController {

    @GetMapping("/api/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok", "source", "public-api"));
    }
}
~~~

Create `application.yml` per Section 5.1, then run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows you can run `mvnw.cmd spring-boot:run`. This lesson provides a **self-run procedure**, not claims that builds or tests were executed inside this repository.

### 6.3. Verify the Data-Plane API

~~~bash
curl -i "http://127.0.0.1:8080/api/ping"
~~~

Expected:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"ok","source":"public-api"}
~~~

The endpoint on port 8080 proves only that the **public/application listener** is running. It does not prove an `lb://...` route, security filter, or real backend is healthy.

### 6.4. Verify Management on the Separate Port

~~~bash
# Access through the management listener:
curl -i "http://127.0.0.1:9090/actuator/health"

curl -i "http://127.0.0.1:9090/actuator/info"

curl -i "http://127.0.0.1:9090/actuator/gateway/routes"
~~~

In a **lab without Spring Security**, localhost calls to these three allowed endpoints can return 2xx. `health` typically returns JSON like:

~~~json
{"status":"UP"}
~~~

If no routes are declared yet, `/actuator/gateway/routes` may return an empty array or routes supplied by active locators; no backend is required for the endpoint to exist. Statuses may differ if Spring Security was pulled in by another dependency or a custom security chain exists.

### 6.5. Negative Test: Public Port Must Not Expose Actuator

~~~bash
curl -i "http://127.0.0.1:8080/actuator/health"

curl -i "http://127.0.0.1:8080/actuator/gateway/routes"

curl -i "http://127.0.0.1:8080/actuator/env"

curl -i -X POST \
  "http://127.0.0.1:8080/actuator/gateway/refresh"
~~~

Expected in a **lab with no route/proxy pointing to Actuator**: these URLs **are not served as management endpoints** on port 8080; they typically return 404 or an error from another handler/security rule. Crucially:

- No internal routes list JSON is returned.
- No environment or detailed config is readable.
- No route refresh/create/delete is triggered.
- No information leaks outside the designed public API.

**Trap:** If the Gateway defines a broad `Path=/**` route pointing to another backend, `/actuator/...` on the public port could be **proxied** and receive HTTP 200 from that backend. Therefore, never rely solely on 404/200 status codes; identify **which component generated the response** and whether real management data leaked.

### 6.6. Negative Test: `read-only` Forbids Mutating Management Calls

~~~bash
curl -i -X POST \
  "http://127.0.0.1:9090/actuator/gateway/refresh"

curl -i -X DELETE \
  "http://127.0.0.1:9090/actuator/gateway/routes/catalog-live"
~~~

With `management.endpoint.gateway.access=read-only` and `max-permitted=read-only`, **no route refresh or deletion may take effect** via Actuator. Exact responses may be 404, 405, or another rejection status depending on endpoint/version/security. Avoid hardcoding one HTTP code in tests; verify instead that route caches and definitions **remained unchanged**.

If any write succeeds, that is a serious policy failure: check active profiles, property namespaces, custom endpoints, Actuator version, and where the request actually routed.

### 6.7. Testing from Another Host

Calling from **localhost** does not prove the management port is unreachable from the network. From an **authorized test host on the same network**, try connecting to the Gateway machine's IP:

~~~bash
# Use only a test IP assigned by system administrators:
curl -i --connect-timeout 2 \
  "http://192.0.2.10:9090/actuator/health"
~~~

`192.0.2.10` belongs to the documentation example address block, **not a real machine's IP**. Replace it with a valid test address provided by your environment. When management binds `127.0.0.1` without special proxies/tunnels, remote clients **must fail to connect** to the management listener. If a connection succeeds, check container port publishing, port-forwards, firewalls, reverse proxies, and actual bind addresses.

Do not scan the Internet or hosts you do not administer. This strictly verifies **access paths of systems you operate**.

### 6.8. Smoke Test Matrix

| Request Source | URL | Purpose | Expected Outcome |
| --- | --- | --- | --- |
| Host machine, localhost | `:8080/api/ping` | Application API | Returns 200 |
| Host machine, localhost | `:9090/actuator/health` | Management health | Readable per policy |
| Host machine, localhost | `:9090/actuator/gateway/routes` | Route inventory | Read-only; requires auth when Security is enabled |
| Host machine, localhost | `:9090/actuator/gateway/refresh` via POST | Probe write operation | Disallowed |
| Host machine, localhost | `:8080/actuator/gateway/routes` | Probe public bypass | Serves no management data |
| Another host on network | `host-ip:9090/actuator/health` | Verify loopback bind | Connection fails in lab |
| Client via public Ingress | `https://api.example.test/actuator/...` | Verify public path | Management endpoint unreachable |
| Authorized monitoring | Management address on private network | Scrape / observe | Permitted endpoints only, with auth/RBAC |

## 7. Three Design Mistakes That Leave a “Separate Port” Insecure

### 7.1. Public Reverse Proxy Also Forwards the Management Port

A proxy might be configured as:

~~~text
Public /api/**       → Gateway :8080
Public /actuator/**  → Gateway :9090    <-- WRONG
~~~

This separates ports in Spring Boot yet **re-merges both paths at the Ingress layer**. Proper design:

~~~text
Public hostname     → Gateway :8080 only
Private monitoring  → Gateway :9090 (separate network + identity)
~~~

Never expose port 9090 in public Ingress rules, reverse proxy locations, TCP LoadBalancer listeners, or unintended container port publishes. Prefer an **explicit public allowlist** over hoping a `/actuator/**` blacklist catches every path variant.

### 7.2. A Dynamic Gateway Route Loops Back to the Management Port

Dangerous route example:

~~~yaml
# SEVERE MISCONFIGURATION - NEVER DEPLOY
- id: public-admin-proxy
  uri: http://127.0.0.1:9090
  predicates:
    - Path=/ops/**
  filters:
    - StripPrefix=1
~~~

With dynamic route-editing access, someone could create a route from the public port to the **internal management listener**. Browsers never connect directly to 9090, yet requests enter Gateway 8080 and proxy to 9090; **loopback from the Gateway process still reaches it**.

This is an example of **SSRF/open-proxy and administrative bypass**. You must:

1. Protect **create/edit/delete `RouteDefinition`** privileges with strict authorization.
2. Enforce **allowlists for URI schemes, hostnames, ports, route IDs, predicates, and filters**.
3. Block destinations in loopback, link-local, metadata, or private management ranges unless explicitly allowed.
4. Account for DNS resolution and redirects to prevent DNS-rebinding allowlist bypasses.
5. Enforce defense-in-depth on the management listener rather than trusting localhost-only binding.

Once a dynamic route targets the management port, renaming `/actuator` to `/_ops` **solves nothing**.

### 7.3. An Overly Broad Spring Security Rule

Dangerous logic example:

~~~java
// POLICY ANTI-PATTERN:
// .anyExchange().permitAll() across the whole Gateway
// assuming the management listener is already "private".
~~~

If an infrastructure mistake exposes the management port, this rule makes exposed endpoints trivially readable/callable. Moreover, defining a **custom `SecurityWebFilterChain`** can cause Spring Boot's default security auto-configuration to **back off**: never assume Actuator remains locked down by default.

When configuring Spring Security, define **complete** endpoint-specific and application policies rather than matching `/actuator/**` and leaving unmatched requests open.

## 8. Spring Security Reactive: Role Control on Actuator

Port separation limits network reachability; **authentication/authorization** decides which users or service identities may read management data. In multi-operator systems, a VPN or IP allowlist alone cannot attribute actions to specific identities.

### 8.1. `SecurityWebFilterChain`, Not Servlet `SecurityFilterChain`

For Gateway Server **WebFlux**, use:

~~~text
ServerHttpSecurity
SecurityWebFilterChain
ServerWebExchangeMatcher
EndpointRequest (reactive package)
~~~

Never copy Servlet examples using `HttpSecurity`, `SecurityFilterChain`, and `org.springframework.boot...servlet.EndpointRequest` into Gateway WebFlux.

**Import differences by Spring Boot version:**

~~~java
// Spring Boot 3.5.x:
import org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest;
~~~

~~~java
// Spring Boot 4.0.x:
import org.springframework.boot.security.autoconfigure.actuate.web.reactive.EndpointRequest;
~~~

Pick **one import line**, never both. This reflects Spring Boot's package reorganization; surrounding Security code may also evolve across Spring Security versions, so build against the exact BOM.

### 8.2. Authorization Example: Health Readable, Routes Only for `OPS`

Complete conceptual example with **two WebFlux Security chains** on Spring Boot 3.5:

~~~java
package demo.gateway.security;

import org.springframework.boot.actuate.autoconfigure.security.reactive.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class GatewaySecurityConfiguration {

    @Bean
    @Order(0)
    SecurityWebFilterChain actuatorSecurity(ServerHttpSecurity http) {
        return http
                .securityMatcher(EndpointRequest.toAnyEndpoint())
                .authorizeExchange(exchanges -> exchanges
                        .matchers(EndpointRequest.to("health")).permitAll()
                        .anyExchange().hasRole("OPS"))
                .httpBasic(Customizer.withDefaults())
                .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain applicationSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/ping").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**This example demonstrates security rules; real access requires a `ReactiveUserDetailsService` or identity provider supplying `ROLE_OPS` accounts/authorities and securely managed passwords/credentials.** Never hardcode passwords or demo accounts in production. With Basic auth, mandate TLS on every hop over untrusted networks.

Explanation:

- The `@Order(0)` chain handles requests matching `EndpointRequest.toAnyEndpoint()`; health is readable while routes require `ROLE_OPS`.
- The `@Order(1)` chain protects remaining application requests; here only `/api/ping` is public.
- Boot will not automatically add another full API protection chain once you define custom `SecurityWebFilterChain` beans.
- `EndpointRequest` is safer than hardcoding `"/actuator/**"`, since Actuator supports custom base paths and nested endpoints.
- The example does not disable CSRF globally. With a **`read-only`** policy, there is no reason to enable state-changing operations just to test configuration.

**Important with a separate management port:** the management listener may run in a **child application context** with different filter/security initialization than the main port. Never assume those two `SecurityWebFilterChain` beans **automatically** govern both ports identically across every Boot setup. Test 401/403/2xx **against the real port 9090**, while confirming port 8080 stays protected. For complex setups, place security config in the management server's context per your Boot version/infrastructure docs.

### 8.3. `OPS` Role Does Not Grant Route Write Access

Even for a user holding `ROLE_OPS`, with:

~~~yaml
management:
  endpoint:
    gateway:
      access: read-only
  endpoints:
    access:
      max-permitted: read-only
~~~

POST refresh or route deletion remains disabled at the endpoint level. **Successful authentication does not elevate endpoint access levels.**

If your organization needs **route admins** authorized to modify routes, separate `OPS_READ` from `ROUTE_ADMIN`, enabling write endpoints solely inside a tightly locked control plane with audit logs and approval/rollback workflows. Never reuse metrics-reading OPS privileges to grant traffic-modification rights.

### 8.4. Never Open CORS on Management Endpoints Out of Habit

Spring Boot Actuator has dedicated CORS properties under `management.endpoints.web.cors.*`. CORS is neither network control nor authentication. Never set `allowed-origins: "*"` so a public dashboard can call admin endpoints from browsers.

If a cross-origin admin UI genuinely exists, authenticate users/services, specify **exact origins**, configure CSRF/credentials properly, and keep endpoints on the management network; browser CORS checks **never replace** firewalls.

## 9. Kubernetes Deployment: Public Ingress Differs from Management Service

In Kubernetes, the goals are:

- Public Ingress/LoadBalancer reaches **only** API port `8080`.
- In-cluster monitoring or authorized operators reach management port `9090` through a **separate Service** or authorized port-forward/tunnel.
- **`NetworkPolicy`** permits only authorized sources to port 9090—never rely on naming a Service “internal”.
- Health probes have appropriate reachability and permissions without causing spurious Gateway restarts or traffic drops.

### 9.1. Pod Bind Address Differs from Localhost

In a single-machine lab, `management.server.address=127.0.0.1` makes sense. Inside a Kubernetes Pod, however, kubelet and monitoring Pods connect via the **Pod IP**, not the container's loopback namespace. Binding only `127.0.0.1` can prevent them from **connecting** to port 9090 even when Services exist.

A production deployment might use:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080

management:
  server:
    address: 0.0.0.0
    port: 9090
~~~

**This is not isolation provided by Spring Boot alone.** It simply tells listeners to bind all interfaces inside the container/Pod; you must combine it with **never publishing 9090 on Ingress, a dedicated Service, NetworkPolicy/firewalls, authentication, and TLS**. Use this only when infrastructure layers truly control ingress paths.

Another option is keeping management on loopback and having a sidecar/agent in the **same Pod network namespace** scrape localhost and forward over a secured channel—which also requires verifying RBAC/identity and ensuring no public tunnels are opened.

### 9.2. Two Kubernetes Services, Only One Public

**Illustrative** manifests; the `app: gateway` selector must match your actual Deployment labels:

~~~yaml
apiVersion: v1
kind: Service
metadata:
  name: gateway-api
spec:
  type: ClusterIP
  selector:
    app: gateway
  ports:
    - name: http-api
      port: 8080
      targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: gateway-management
spec:
  type: ClusterIP
  selector:
    app: gateway
  ports:
    - name: http-management
      port: 9090
      targetPort: 9090
~~~

Public Ingress references only the `gateway-api` Service:

~~~yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: gateway-public
spec:
  rules:
    - host: api.example.test
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: gateway-api
                port:
                  number: 8080
~~~

This minimal snippet highlights **Ingress backend Service + port**. Production requires `IngressClass`, TLS certificates/secrets, auth policies, and rate limiting. **Never** create a public Ingress pointing to `gateway-management:9090`.

**`ClusterIP` does not mean secret.** Without a `NetworkPolicy` blocking them, other Pods in the cluster can call the management Service. Restrict callers by namespace/pod/service identity.

### 9.3. NetworkPolicy Allowing Only Valid Sources per Port

**Illustrative** policy: Pods labeled `app=gateway` accept API traffic only from the ingress namespace and management traffic only from Prometheus in the monitoring namespace.

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: gateway-ingress-isolation
spec:
  podSelector:
    matchLabels:
      app: gateway
  policyTypes:
    - Ingress
  ingress:
    # Data plane: ingress-controller namespace only
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: ingress-system
      ports:
        - protocol: TCP
          port: 8080

    # Management plane: monitoring namespace only
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: monitoring
          podSelector:
            matchLabels:
              app: prometheus
      ports:
        - protocol: TCP
          port: 9090
~~~

For this policy to take effect:

1. The CNI/network plugin must **enforce Kubernetes NetworkPolicies**.
2. Namespace/Pod labels must **match reality**; names here are illustrative.
3. Account for kubelet health probes, log collectors, service-mesh sidecars, egress/DNS, and related traffic so you don't accidentally break readiness/metrics.
4. If mTLS or service-level identity is required, add that layer; IP/label-based NetworkPolicies do not authenticate caller identity.
5. Check all other policies targeting the same Pods: allowed ingress is the union of matching policies—there are no priority deny rules like traditional firewalls.

### 9.4. Why Does a Separate Management Service Still Need In-App Security?

A compromised Pod in the `monitoring` namespace could attempt to reach `gateway-management`. Kubernetes RBAC governs Kubernetes API calls, **not HTTP endpoints inside Pods**. Routes/metrics endpoints should still enforce service identity, Basic-over-TLS, OAuth2, or mTLS with least-privilege permissions per platform.

Never attach `cluster-admin` to a metrics scraper. Give scrapers the narrowest possible role, e.g., GET `/actuator/prometheus` only.

## 10. Health Probes When Actuator Runs on a Separate Port

Spring Boot exposes health groups such as:

~~~text
/actuator/health
/actuator/health/liveness
/actuator/health/readiness
~~~

In Kubernetes, liveness/readiness are normally enabled automatically; you can also enable them explicitly:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

With a separate management port, probes hitting 9090 can **succeed even when application port 8080 is failing to accept requests**. This is an operational trap: a healthy management context does not prove the data plane is healthy.

Spring Boot supports exposing probe paths on the **application port**:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
        add-additional-paths: true
~~~

When active per your Boot version's docs:

~~~text
GET :8080/livez    → liveness
GET :8080/readyz   → readiness
GET :9090/actuator/health/liveness  → same health group, management port
GET :9090/actuator/health/readiness → same health group, management port
~~~

`/livez` and `/readyz` are **intentional minimal exceptions** on the application port—never an opening of all `/actuator/**`. They should return minimal status without route inventories or secrets.

### 10.1. Probe Example in a Deployment

~~~yaml
# Partial Pod container spec, not a full Deployment manifest
ports:
  - name: http-api
    containerPort: 8080
  - name: http-management
    containerPort: 9090

livenessProbe:
  httpGet:
    path: /livez
    port: http-api
  periodSeconds: 10
  timeoutSeconds: 2

readinessProbe:
  httpGet:
    path: /readyz
    port: http-api
  periodSeconds: 5
  timeoutSeconds: 2
~~~

With `NetworkPolicy` enabled, verify kubelet can reach port 8080 for probes. Never set `management.server.address=127.0.0.1` and point probes to Pod IP port 9090 assuming they will work.

### 10.2. Liveness Differs from Readiness

| Probe | What It Asks | What Not to Do |
| --- | --- | --- |
| **Liveness** | Is the process still able to recover/run? | Couple to shared Redis/DB so one dependency outage triggers mass restarts |
| **Readiness** | Should this Pod receive new traffic right now? | Report healthy superficially when the API listener is broken |
| **Startup** | Has the app finished starting up? | Let liveness kill a legitimately slow-starting process |

If rate-limiter Redis fails or service discovery briefly disconnects, readiness should reflect real impact. Never force all Gateway instances to restart together just because a shared dependency went down—that causes **cascading failures**.

### 10.3. Options When All Management Must Stay Off Public Ingress

Some organizations forbid even `/livez`/`/readyz` on public Ingress. Options include:

- Let kubelet or an internal load balancer probe the **Pod IP/app port directly** without routing health endpoints through public Ingress.
- Expose health checks on an internal endpoint with firewall/Ingress rules enforcing authentication or IP allowlists.
- Use a non-HTTP internal probe mechanism if supported and tested on your platform.

Never delete probes just to hide status from the Internet: separate the **probe network path** from public traffic without losing Pod failure detection.

## 11. Prometheus, Metrics, and Management Data Leakage Risks

To scrape metrics:

~~~xml
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
</dependency>
~~~

Add Prometheus to the exposure allowlist **only when needed**:

~~~yaml
management:
  endpoints:
    access:
      default: none
      max-permitted: read-only
    web:
      exposure:
        include: "health,info,gateway,prometheus"
  endpoint:
    prometheus:
      access: read-only
~~~

Keep port and security policies from the baseline config. Prometheus should connect from an **authorized monitoring namespace/host** to the management port, never over public URLs.

**Never assume metrics are harmless data.** Labels can reveal route IDs, service IDs, backend hosts, tenants, or paths. Avoid raw tokens, session IDs, user IDs, or PII-containing paths as metric labels, which cause both data leaks and high cardinality. Review data exposed via Actuator Gateway routes/filter inventories too.

### 11.1. When `loggers`, `env`, or `threaddump` Are Needed

Never add `loggers`, `env`, `heapdump`, or `threaddump` to production exposure merely for routine debugging. If strictly required:

1. Use the private management plane, authenticate the on-call responder, and set a time limit.
2. Audit who enabled it, when, which read/write operations ran, and why.
3. Keep sensitive env/config values sanitized unless strictly necessary.
4. Never let read-only monitoring users enable TRACE or alter log levels on systems carrying sensitive data.
5. Revoke access and revert to the minimal exposure allowlist once troubleshooting ends.

Changing log levels is a **write operation**; under `max-permitted=read-only`, it stays blocked regardless of Security-layer admin roles.

### 11.2. What Can Still Leak Without Any Secrets?

`GET /actuator/gateway/routes` can expose:

~~~json
[
  {
    "route_id": "payments-internal",
    "uri": "lb://payments-service",
    "order": 0
  }
]
~~~

This JSON is illustrative; actual payloads include predicates/filters and vary by version. Service names and route structures help attackers map the system. Hence **`read-only` remains sensitive** and must stay off the Internet.

## 12. TLS, Authentication, and Remote Management Access

### 12.1. TLS Is Mandatory for Management Traffic Over Untrusted Networks

If the management listener binds `127.0.0.1` and is called locally on the same machine, HTTP may suffice in a lab. Across hosts/networks or untrusted tunnels, enforce HTTPS/mTLS or equivalent encrypted channels.

Spring Boot allows a dedicated SSL context on a separate management port via `management.server.ssl.*`. Practical setups include:

- Direct TLS on the management listener;
- TLS/mTLS via internal ingress, service mesh, or sidecar;
- Access through VPN/SSH tunnels or orchestrators with strong identity and auditing;
- SSO/OAuth2 for admin UIs, client credentials/mTLS for monitoring agents.

**Never disable TLS certificate validation** to work around hostname mismatches. Never commit keystore passwords, Basic passwords, or API keys into repositories, sample YAML, or shell history.

### 12.2. Role-Based Access

| Role | Typical Privileges |
| --- | --- |
| Public API client | Forbidden from calling management endpoints |
| Health probe | Minimal health/liveness/readiness read only |
| Metrics scraper | Required Prometheus/metrics read only |
| Read-only SRE | Approved health, routes, filters, and observability read access |
| Route administrator | Proposes/approves route changes via a dedicated control plane |
| Break-glass admin | Emergency privilege, short-lived, fully audited |

Never share a single `ops` account with unrestricted access across everyone. **AuthN/AuthZ** must be enforced at the management endpoint, never trusting self-asserted headers like `X-Admin: true`.

### 12.3. If Dynamic Route Modification Is Needed

Spring Cloud Gateway Actuator provides:

~~~text
POST   /actuator/gateway/refresh
POST   /actuator/gateway/routes/{id}
DELETE /actuator/gateway/routes/{id}
GET    /actuator/gateway/routes
~~~

For Gateway WebFlux 4.2/5.0, docs recommend:

~~~properties
# For observation only; forbids create/delete/refresh routes:
management.endpoint.gateway.access=read-only
~~~

If Actuator write operations are **genuinely** needed:

~~~properties
# STRICTLY inside an isolated, tightly authorized control plane:
management.endpoint.gateway.access=unrestricted
~~~

When enabling `unrestricted`, you must **remove** `management.endpoints.access.max-permitted=read-only` if writes are truly intended; treat this as a deliberate security-posture change, not a harmless one-line tweak. Pair it with a dedicated security chain, mTLS, destination allowlists, filter/predicate validation, auditing, and rollback.

**Approach many organizations should prefer:** keep Actuator's write API disabled; instead have authenticated pipelines/operators update a **`RouteDefinitionRepository`** via a controlled interface, emit `RefreshRoutesEvent` across replicas, and verify runtime routes. Securing that control plane remains mandatory.

### 12.4. Do Not Confuse a Read-Only Endpoint with System Immutability

Even with `gateway.access=read-only`, routes can still change via **Config Server, Java code, `DiscoveryClient`, databases, or other workflows**. Read-only only restricts operations through that Actuator endpoint; it does not freeze route definitions or discovery stores.

## 13. Troubleshooting: Why Is Actuator Still Visible or Unreachable?

| Symptom | Possible Causes | Diagnostic Steps |
| --- | --- | --- |
| `localhost:9090/actuator/health` connection refused | Actuator not on separate port, bind failure, app not started | Check startup logs, `management.server.port/address`, and listeners |
| Port 9090 open yet `/gateway/routes` returns 404 | Missing endpoint access or web exposure | Check Actuator starter, `gateway.access`, and exposure include |
| Port 9090 GET gateway returns 401 | Spring Security requires authentication | Supply valid IdP/credentials; never disable auth |
| Port 9090 GET gateway returns 403 | Caller lacks role/policy | Check `ROLE_OPS`, `SecurityWebFilterChain`, and management context |
| POST refresh returns 404/405/403 | `read-only` access, CSRF, or security block | Confirm this is **desired behavior** when read-only |
| Port 8080 serves `/actuator/gateway/routes` | Shared port, proxy looping back to 9090, or custom controller | Identify response owner and actual route |
| Remote host reaches 9090 despite loopback bind | Proxy/NAT/port-forward, profile override, container publish | Inspect effective config and actual listening sockets |
| Prometheus scrape returns 404 | Missing registry or `prometheus` lacks access/exposure | Check dependencies and config |
| Health 9090 succeeds while API 8080 times out | Separate management context stays healthy | Probe main port and Netty data plane |
| Kubelet probe times out against `127.0.0.1` | Kubelet hits Pod IP while listener bound localhost | Use main-port health paths or private interface + NetworkPolicy |
| GET routes shows few or no routes | Routes not materialized or wrong 4.x/5.x namespace | Check logs, route IDs, and configuration metadata |
| Adding Security chain causes API 401 | Boot auto-security backed off; other chain fell back | Check matchers, `@Order`, and both chains |
| Valid operator still blocked | Boot 3/4 import/matcher mismatch or child security context | Build against exact BOM; test directly on management port |
| Metrics contain user/token/sensitive URIs | Uncontrolled labels or exporter config | Redact/fix labels; shrink exposure |

### 13.1. Distinguish Connection Errors from HTTP Errors

- **Connection refused / timeout:** no HTTP response from endpoint; inspect listeners and network.
- **HTTP 404:** HTTP server replied yet no matching handler exists, or a proxy/handler returned 404.
- **HTTP 401:** caller must authenticate.
- **HTTP 403:** caller lacks authority, or security/CSRF policy blocked it.
- **HTTP 405:** path is served yet HTTP method/operation is unavailable.

Never switch an endpoint from `read-only` to `unrestricted` simply because a test POST returned 404/405. When write operations are blocked, that is likely the **intended policy working**.

### 13.2. Version Differences to Verify

| Feature | Cross-Check |
| --- | --- |
| `management.endpoint.gateway.access` | Gateway and Boot docs for running version |
| `management.endpoints.access.default/max-permitted` | Spring Boot 3.5/4.x configuration metadata |
| Reactive `EndpointRequest` import | Boot 3.5: `org.springframework.boot.actuate.autoconfigure.security.reactive`; Boot 4.x: `org.springframework.boot.security.autoconfigure.actuate.web.reactive` |
| WebFlux routes | Gateway 4.x: `spring.cloud.gateway.routes`; 5.x: `spring.cloud.gateway.server.webflux.routes` |
| HTTP Actuator base path | `management.endpoints.web.base-path` and management context |
| SSL on management port | `management.server.ssl.*` and ingress/service mesh |
| Gateway read-only | No write operations; verify with negative tests |

**Always verify actual dependency versions** before applying docs: Spring Boot, Spring Security, and Spring Cloud can alter binding/auto-configuration between lines.

## 14. Automated Testing: Verify Both Permitted and Blocked Paths

Testing only `GET /actuator/health = 200` is insufficient. A management-isolation test suite must include **negative tests**.

### 14.1. Security Acceptance Matrix

| ID | Request | Condition | Expected Outcome |
| --- | --- | --- | --- |
| M01 | GET `:8080/api/ping` | Public test client | Served |
| M02 | GET `:8080/actuator/health` | Public listener | Not served as Actuator endpoint |
| M03 | GET `:8080/actuator/gateway/routes` | Public listener | Does not expose route inventory |
| M04 | POST `:8080/actuator/gateway/refresh` | Public listener | Does not alter routes |
| M05 | GET `:9090/actuator/health` | Internal health probe | Minimal status per policy |
| M06 | GET `:9090/actuator/gateway/routes` | Anonymous with Spring Security enabled | Rejected |
| M07 | GET `:9090/actuator/gateway/routes` | Operator with valid role | Read-only |
| M08 | POST `:9090/actuator/gateway/refresh` | Even authenticated operator | Blocked by `read-only` access |
| M09 | GET `:9090/actuator/env` | Internal caller | Unexposed per allowlist |
| M10 | GET `:9090/actuator/heapdump` | Internal caller | Unexposed |
| M11 | TCP to port 9090 over public network | External client | No reachable network path |
| M12 | GET `:8080/readyz` | Kubelet/internal probe | Minimal readiness if additional health paths enabled |
| M13 | Public hostname `/actuator/**` | Internet client | Not proxied to management context |
| M14 | Dynamic route targeting `127.0.0.1:9090` | Control-plane validation | Rejected by destination policy |
| M15 | Out-of-allowlist Pod calling management Service | Another cluster Pod | Blocked by NetworkPolicy/mTLS/RBAC |

For M08, do not check only HTTP status: verify **route definitions and caches did not change**. M14 should test loopback, link-local, and metadata addresses; never let attackers bypass URI allowlists via alternate hostnames or DNS resolution.

### 14.2. Inspecting Listeners with OS Tools

On a test machine or VM, use TCP listener tools to confirm which addresses the process bound:

~~~bash
# Linux example; run only on systems you are authorized to administer
ss -lnt
~~~

On Windows you can use `Get-NetTCPConnection`. **OS socket output alone does not prove Ingress/tunnel configs at other layers**, so still test across every network boundary.

### 14.3. Testing in the Deployment Pipeline

A pipeline can:

1. Validate YAML, configuration metadata, and dependency BOMs.
2. Start a test Gateway with two separate ports.
3. Test the application API and management health.
4. Run negative tests for Actuator URLs on the **main port**.
5. Verify Gateway Actuator write operations are disabled.
6. Test WebFlux Security with anonymous, monitoring, and ops roles.
7. Deploy to staging with real Ingress/Service/NetworkPolicy and test from **outside** and **inside** the cluster.
8. Promote to production only upon passing; re-verify after routing or config changes.

Never open production firewalls to an untrusted host just to run tests. Keep test runners inside the authorized management network.

## 15. Management-Plane Observability Without Leaking Data

### 15.1. Signals to Monitor

| Signal | Operational Value |
| --- | --- |
| Request count by endpoint group | Detect scanning or anomalous access |
| HTTP 401/403 to management | Spot unauthorized callers or expired credentials |
| Route refresh/update events | Audit route impacts, revisions, and operators |
| Route count/hash/revision per replica | Detect route drift across Gateway nodes |
| Separate API latency/error rate | Measure data-plane health without confusing it with management health |
| Heap, direct memory, process RSS | Spot memory pressure or diagnostic overload |
| Liveness/readiness | Detect broken or unready nodes |
| Prometheus scrape success/errors | Confirm metrics pipeline health |

These metric names represent **signals you should collect**, not built-in metric names emitted identically by Spring Cloud Gateway. Depending on Spring Boot/Micrometer versions, create custom metrics or map dashboards to built-in ones.

**Never put raw access tokens, session cookies, per-user principal IDs, raw IPs, or PII-bearing paths into metric labels.** They cause both high cardinality and data leaks. Audit logs should record the **authenticated** principal, action, endpoint group, outcome, and controlled correlation ID; avoid logging full query strings containing secrets.

### 15.2. Alerts to Maintain

- Any public hostname reading route inventories or Actuator diagnostics outside public policy.
- `gateway.access=unrestricted` appearing outside a change window.
- A read-only role triggering refresh or DELETE route.
- Any replica's route inventory diverging from the approved revision.
- Spikes in 401/403 on the management port; investigate credential stuffing or scanning.
- Sudden spikes in requests to `env`, `heapdump`, `loggers`, or `threaddump`.
- Health probe succeeding on the management port while the API port stops serving requests.
- Prometheus scrapes failing or management latency spiking.

During alerts, never paste raw dumps, env outputs, or tokens into unapproved chat/ticket tools.

### 15.3. Incident Runbook: Actuator Exposed to the Internet

1. **Immediately block public ingress/firewall access** to the management port and any routes proxying to Actuator.
2. Disable write privileges via access level/`read-only` or disable the endpoint if needed; confirm writes are truly blocked.
3. Review audit trails/route revisions for unauthorized `RouteDefinition`/filter changes.
4. If credentials/secrets may have leaked, run proper rotation/revocation procedures.
5. Inspect secondary exposure paths: NodePorts, TCP LoadBalancers, Ingress routes, port-forwards, sidecars, Services, and JMX.
6. Re-run the positive/negative test matrix from both **public** and **private** networks.
7. Add CI/CD guardrails to prevent recurrence and document root cause and mitigations.

Not every read-only Actuator exposure guarantees data was exfiltrated; investigate logs and evidence methodically rather than guessing impact.

## 16. Common Myths and Counter-Examples

**A — “Renaming the path to `/secret-admin` makes it safe.”**

False. Paths can be guessed, leaked in configs, or rewritten by proxies. Defense requires network isolation, authentication, and authorization.

**B — “Port 9090 is separate, so anyone reaching it can read routes.”**

False. If NAT/Ingress exposes that port to the Internet, route inventory still leaks topology. A separate port is an architectural layer, not a security guarantee.

**C — “Spring Security is on the classpath, so Actuator locks down automatically.”**

Never assume this. A custom `SecurityWebFilterChain` can cause Boot auto-security to back off. Test exact chains on the management port.

**D — “`gateway.access=read-only` means public access doesn't matter.”**

False. Read-only can still leak internal service names, route filters, and metadata; it never replaces firewalls.

**E — “Binding `127.0.0.1` stops the Gateway from reaching Actuator.”**

False. A route inside the Gateway itself can proxy to `127.0.0.1:9090` from the local process; enforce destination allowlists and management-plane security.

**F — “Health on 9090 is UP, so the API on 8080 is definitely healthy.”**

Not always true. A separate management context can stay responsive while the application listener fails; probe the main port or send real traffic probes.

**G — “Kubernetes `ClusterIP` is enough to protect management.”**

False. Other Pods in the cluster can connect unless blocked by `NetworkPolicy`. Service types are not HTTP authentication.

**H — “Adding `/actuator/**` to a CORS denylist solves it.”**

False. CORS is enforced only by browsers and never stops `curl`, service-to-service clients, or internal routes. Lock down networking, endpoint access, and identity.

## 17. Pre-Production Deployment Checklist

- [ ] Clearly separated **data plane / management plane**, ports, hostnames, and network owners.
- [ ] Management listener runs on a dedicated port or HTTP management is disabled when unneeded.
- [ ] On local/VMs, management binds loopback/private IP properly; on Kubernetes, verified Pod IP and kubelet probes.
- [ ] Public Ingress forwards only the API port; no public NodePort/LoadBalancer/Ingress exposes the management port.
- [ ] Management Service traverses a private network with NetworkPolicy/firewall/mTLS per policy.
- [ ] Set `management.endpoints.access.default=none` and declared an intentional endpoint allowlist.
- [ ] Configured `max-permitted=read-only` when only read operations are needed.
- [ ] Set `management.endpoint.gateway.access=read-only`; never leave `unrestricted` permanently enabled.
- [ ] Web exposure lists only truly needed `health`/`info`/`gateway`/`prometheus`; never use `"*"` carelessly.
- [ ] Reviewed JMX and other management transports.
- [ ] Unexposed `env`/`configprops`/`heapdump`/`shutdown`/`loggers` unless strictly required and tightly governed.
- [ ] WebFlux Security uses reactive `EndpointRequest` matchers and policies matching your Boot version.
- [ ] Verified security on the **real management port**, not just by reading Java code.
- [ ] Operator/monitoring identities follow role separation and least privilege, avoiding overly broad shared accounts.
- [ ] Enforced TLS/mTLS or equivalent encrypted channels for networked management; no hardcoded credentials.
- [ ] Health probes return minimal info; main-port liveness/readiness verified.
- [ ] Dynamic `RouteDefinition`s cannot proxy to localhost/management/link-local/metadata services outside allowlists.
- [ ] Never trust client-supplied `X-Forwarded-*` headers outside an established proxy trust boundary.
- [ ] Positive API/health tests and **negative public Actuator tests** run after every config change.
- [ ] Verified GET routes is read-only and POST refresh/DELETE route are denied.
- [ ] Logs/metrics/audits contain no secrets, tokens, session IDs, or PII.
- [ ] Runbook ready for blocking management exposure, rolling back, and post-incident checks.

## 18. Self-Check Knowledge Quiz

**1. Does `management.server.port=9090` block Internet clients by itself?**

No. If Ingress, a reverse proxy, NAT, or firewall opens that port to the Internet, clients can still connect. Control network paths and security.

**2. How does `access` differ from `exposure`?**

`access` controls whether an endpoint exists and which operations are permitted; `exposure.include` controls which endpoints are published over HTTP. Neither replaces caller authentication.

**3. Can you bind a different management address from the main address while sharing the same port?**

Per Spring Boot docs, binding `management.server.address` independently is only supported when the **management port differs from the application port**.

**4. Why must you define an application security chain after adding a dedicated Actuator security chain?**

Because custom WebFlux Security configuration can cause Boot auto-security to back off. A chain matching only Actuator does not protect remaining API routes.

**5. Why is a new route with `uri: http://127.0.0.1:9090` so dangerous?**

It turns the public Gateway into a proxy to loopback Actuator, bypassing port/address isolation. Enforce URI destination allowlists and strict write governance.

**6. Why might enabling `management.endpoint.health.probes.add-additional-paths=true` be advisable?**

So liveness/readiness can also be probed on the **application port** at `/livez` and `/readyz`, avoiding false positives when the management listener is healthy while the data plane stops accepting requests.

**7. Does a `ClusterIP` Service guarantee only monitoring Pods can access it?**

No. You need `NetworkPolicy`, service identity, and potentially mTLS to restrict callers and permissions.

**8. When is enabling `gateway.access=unrestricted` acceptable?**

Only within a controlled route-management workflow: private management network, authentication/RBAC, auditing, change approvals, URI allowlists, rollback, and negative security tests. Never enable as a public default.

## 19. Official References

1. [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): access levels, exposure, security, sanitization, and Kubernetes probes.
2. [Spring Boot 4.0 — Actuator Endpoints](https://docs.spring.io/spring-boot/4.0/reference/actuator/endpoints.html): `management.endpoints.access.default/max-permitted`, endpoint security, and health groups.
3. [Spring Boot — Monitoring and Management over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): `management.server.port/address`, management-specific SSL, base-path, and disabling HTTP management.
4. [Spring Cloud Gateway Server WebFlux 5.0 — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/5.0/spring-cloud-gateway-server-webflux/actuator-api.html): `gateway.access=read-only/unrestricted`, routes, filters, and refresh.
5. [Spring Cloud Gateway WebFlux 4.2 — Actuator API](https://docs.spring.io/spring-cloud-gateway/reference/4.2/spring-cloud-gateway/actuator-api.html): endpoint behavior and access levels in 4.2.
6. [Spring Boot 3.5 — Reactive EndpointRequest API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/actuate/autoconfigure/security/reactive/EndpointRequest.html): matchers for Actuator on WebFlux.
7. [Spring Boot 4.0 — Reactive EndpointRequest API](https://docs.spring.io/spring-boot/4.0/api/java/org/springframework/boot/security/autoconfigure/actuate/web/reactive/EndpointRequest.html): package changes in Boot 4.x.
8. [Spring Security — WebFlux Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `SecurityWebFilterChain` and reactive request authorization.
9. [Kubernetes — Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/): ingress/egress policies across Pods/namespaces when supported by CNI.
10. [Kubernetes — Ingress](https://kubernetes.io/docs/concepts/services-networking/ingress/): public routing to the right Service/port.

**Key takeaway:** **Isolating Actuator is neither renaming URLs nor enabling Spring Security in isolation.** A secure WebFlux Gateway requires a **dedicated management path/port**, endpoint allowlists with **`read-only`** for observation, **authentication/authorization**, TLS, and appropriate Ingress/`NetworkPolicy` rules. After deployment, test from **both public and private networks**, verify write operations are blocked, prevent loopback proxy bypasses to the management listener, and ensure health probes still check actual data-plane health.
