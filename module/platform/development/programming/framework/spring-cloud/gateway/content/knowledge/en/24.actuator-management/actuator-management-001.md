# Enabling Gateway Actuator with Version-Appropriate Access

## 1. What Problem Does Gateway Actuator Solve?

In a microservices system, **Spring Cloud Gateway** handles traffic at the entry point: selecting routes using `Path`, `Method`, and other predicates; executing the filter chain; transforming paths/headers; resolving `lb://service-id` via service discovery; handling authentication, rate limiting, circuit breakers, retries, TLS, and logging requests. When the system is running, the operations team needs to answer questions such as:

- What **routes currently exist** in the Gateway, along with their predicate conditions and target URIs?
- Has a newly added or updated route actually been **loaded** into the Gateway?
- Which **GlobalFilter** and **GatewayFilter** instances are attached to a route?
- Why is `GET /api/orders/42` not reaching the Orders service as expected?
- After a configuration or service discovery change, has the Gateway **refreshed its route definitions**?

The **Gateway Actuator endpoint** is a set of administrative endpoints provided by Spring Cloud Gateway integrated with **Spring Boot Actuator** to observe and, when permitted, interact with Gateway routes. It is distinct from business APIs normally called by clients. Route information can speed up troubleshooting, but it also reveals system architecture, internal service addresses, and how filters protect requests. Some versions/modes also provide operations to **add, delete, or refresh routes** — which represent privileges that alter live traffic flow.

The lesson **“Enabling Gateway Actuator with Version-Appropriate Access”**, part of the **Actuator Management** chapter of the **SPRING_CLOUD_GATEWAY** module, focuses on opening Gateway Actuator **enough for observability without inadvertently creating an administrative backdoor**.

After this lesson, you will be able to:

1. Distinguish **Spring Boot Actuator** from the **Gateway-specific actuator endpoint**.
2. Distinguish three independent concerns: **granting endpoint access**, **exposing the endpoint**, and **HTTP authentication/authorization**.
3. Choose `management.endpoint.gateway.access: read-only` in supported versions, or configure `enabled` in a way compatible with older release lines.
4. Protect `/actuator/gateway/**` with Spring Security WebFlux, internal networking, and TLS/mTLS when appropriate.
5. Understand route/filter read operations and why route refresh/add/delete operations belong to a higher-risk **management plane**.
6. Accurately diagnose 401, 403, 404/405 responses when an endpoint is inaccessible.
7. Verify with curl, WebTestClient, and a permission matrix to prove that Internet users cannot read or modify routes.
8. Operate multi-replica Gateways without mistaking the output on **one instance** for cluster-wide synchronized state.

> **Scope:** Primary examples use **Spring Cloud Gateway Server WebFlux** and reactive Spring Boot Actuator/Spring Security. Spring Cloud Gateway Server Web MVC, Spring Boot 3.3, 3.4+, 4.x, and corresponding releases may differ in starters, endpoint configuration, and endpoint operations. **Do not choose properties by looking only at the Gateway version name**: you must cross-check **Spring Boot**, the **Spring Cloud BOM**, and the available Actuator API.

## 2. Two Types of APIs on the Same Application with Different Trust Boundaries

The Gateway receives traffic from clients, while Actuator is the **administrative channel**.

~~~mermaid
flowchart TD
    Public["Client / Internet"] --> API["Public API ingress"]
    API --> G["Spring Cloud Gateway"]
    G --> O["Orders service"]
    G --> C["Catalog service"]
    Ops["SRE / trusted operator"] --> M["Private management access"]
    M --> A["Spring Boot Actuator"]
    A --> GA["Gateway endpoint: inspect routes / filters"]
    GA --> G
    A --> H["Health / readiness"]
    A --> MT["Metrics"]
~~~

The **data plane** is where business requests are routed. For example, `GET /api/orders/42` via the `lb://orders-service` route. The **management plane** is where the Gateway runtime is observed/controlled. For example, `GET /actuator/gateway/routes` lists route definitions at the level supported by the endpoint.

A user permitted to call `/api/orders/42` **is not automatically permitted** to access `/actuator/gateway/routes`. A **business** admin account managing products is also not implicitly authorized to modify Gateway routes. These must remain separate permissions.

### How Do Spring Boot Actuator and Gateway Actuator Differ?

| Component | Role | Examples |
| --- | --- | --- |
| **Spring Boot Actuator** | Application management, health, metrics, and various management endpoints | `/actuator/health`, `/actuator/info`, `/actuator/metrics` |
| **Gateway Actuator** | Endpoint dedicated to route definitions, filters, refresh, and route management operations when permitted | `/actuator/gateway`, `/actuator/gateway/routes` |
| **Spring Security WebFlux** | Decides who may invoke management URLs when exposed over HTTP | `SecurityWebFilterChain`, authority/role/scope |
| **Network/TLS boundary** | Allows only trusted access sources to connect to the management port | Private interface, firewall, mTLS/VPN |

Actuator itself is not a graphical dashboard. It typically provides **HTTP management operations**; clients such as curl, operations systems, or observability tools can invoke them according to policy.

### Not Every Actuator Endpoint Should Be Public

Some endpoints such as `health` can provide minimal status for probes if designed appropriately. Endpoints such as `env`, `configprops`, `beans`, `heapdump`, `threaddump`, `loggers`, and **gateway route-management** have an entirely different sensitivity level. Never use `management.endpoints.web.exposure.include: "*"` just for “convenient debugging” on an Internet-facing Gateway.

## 3. Three Gates That Must Be Passed Before Calling Gateway Actuator

An HTTP request to `/actuator/gateway/routes` requires distinguishing **three decision layers**.

~~~mermaid
flowchart TD
    R["GET /actuator/gateway/routes"] --> E{"Is the endpoint available / granted access?"}
    E -->|No| N["Operation is not registered"]
    E -->|Yes| X{"Is Gateway Actuator exposed over HTTP?"}
    X -->|No| H["No public HTTP mapping for the endpoint"]
    X -->|Yes| S{"Do network + HTTP security allow it?"}
    S -->|No| D["Blocked / 401 / 403"]
    S -->|Yes| OK["Read route info within endpoint access level"]
~~~

**Gate 1 — Endpoint availability and access.** An endpoint can be disabled completely; in newer Spring Boot lines, the `management.endpoint.gateway.access` property allows selecting `none`, `read-only`, or `unrestricted` when Gateway Actuator supports this policy. `read-only` is intended to remove write operations defined by Actuator.

**Gate 2 — Exposure over transport.** `management.endpoints.web.exposure.include` determines which endpoints are exposed over HTTP. An endpoint can be available inside the application yet have **no HTTP mapping** because it is not included. Exposure is **not** authentication; it only defines the callable surface.

**Gate 3 — HTTP security and network.** An exposed endpoint must still be protected by **Spring Security**, network policy, TLS, and/or mTLS depending on the architecture. `read-only` **does not prevent unauthorized users from reading internal configuration** if you expose the endpoint publicly. Conversely, a `SecurityWebFilterChain` that only blocks HTTP requests **does not change whether an Actuator write operation is defined**; privileges should be minimized at both the endpoint and HTTP levels.

### Do Not Confuse “read-only” with Role Permissions

| Property | What It Controls | What It **Does Not** Control |
| --- | --- | --- |
| `management.endpoint.gateway.access=read-only` | Which types of Gateway Actuator operations are permitted under the access model | Who is authorized to call that GET endpoint |
| `management.endpoints.web.exposure.include=gateway` | Publishes the endpoint onto the HTTP management surface | Which principals are allowed access |
| `.hasAuthority("SCOPE_ops.gateway.read")` | Request authorization in Spring Security | Whether Actuator write operations exist or not |
| Private management port/firewall | Who can connect over the network | Per-operator identity permissions |

**Defense in depth:** When you only need to **inspect routes/filters**, configure the endpoint as **read-only**, expose selectively, protect HTTP with a dedicated authority, and keep the management port off the Internet. If the running version's endpoint does not support read-only, prioritize strict security/network protection and plan an upgrade accordingly.

## 4. Choosing Properties by Version: access or enabled?

Spring Boot Actuator has evolved its **endpoint access** mechanism over time. Because Gateway Actuator integrates into Actuator, the syntax for enabling and restricting operations must match the actual **Spring Boot and Spring Cloud Gateway versions**.

| Version / Capability Group | Configuration to Check | Meaning |
| --- | --- | --- |
| **Modern Spring Boot supporting endpoint access**, typically Boot 3.4 onward with compatible Gateway | `management.endpoint.gateway.access=read-only` | Allows Gateway Actuator read operations within the supported scope |
| Same group as above, **requires modifying routes** with a controlled management plane | `management.endpoint.gateway.access=unrestricted` | Also allows write operations if the endpoint provides them, **high risk** |
| Same group as above, **wants to disable Gateway endpoint** | `management.endpoint.gateway.access=none` | Grants no access to the Gateway endpoint at the Actuator level |
| **Earlier Spring Boot/Gateway** or lines still using the enable/disable flag | `management.endpoint.gateway.enabled=true` | Enables the endpoint under the legacy mechanism; does not provide the new access-based read-only protection |
| **All groups with Actuator web exposure** | `management.endpoints.web.exposure.include=gateway` | Exposes gateway only if the endpoint is available; still requires security |

**This is a directional selection matrix, not an exact compatibility table for every patch release.** Some versions may still read the `enabled` property for compatibility; some support the `access` property while still being subject to overall Actuator caps. Check the documentation for the **exact running version**, metadata/config binding, and actual HTTP operations, rather than copying both `enabled` and `access` “just in case”.

### Why You Should Not Infer Features from the Gateway Routes Namespace

In some Spring Cloud Gateway lines, route definitions use:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog
          uri: lb://catalog-service
          predicates:
            - Path=/api/catalog/**
~~~

In newer **Gateway Server WebFlux** lines, they may live under `spring.cloud.gateway.server.webflux.routes`. **That is the route namespace**, not the property controlling Gateway Actuator. Actuator configuration resides under **`management.*`**. Do not assume you have to write `spring.cloud.gateway.server.webflux.actuator...` simply because routes moved namespaces.

### How to Identify Your Environment

1. Identify the **Spring Boot version** and **Spring Cloud release train/BOM** from the project dependency configuration approved by the responsible team.
2. Identify whether the application runs **Gateway Server WebFlux** or **Gateway Server Web MVC**; do not mix servlet/reactive starters when writing security config.
3. Verify the **Actuator starter** is present and that the Gateway endpoint is provided by the Gateway dependency in use.
4. Choose one configuration approach (`access` or `enabled`) that is actually supported by the version.
5. Enable `web.exposure` selectively and configure Spring Security.
6. Use HTTP tests to confirm that route GET requests are permitted and write requests are blocked or absent according to policy.

Do not rely on IDE property recognition to assert that an endpoint is active. An unbound property may be ignored or trigger a warning depending on configuration; **HTTP behavior and tests** are the proof.

## 5. Recommended Configuration: Read-Only Gateway Actuator

In a **Spring Boot application supporting `management.endpoint.gateway.access`** with a compatible Gateway, an intentional minimal setup is:

~~~yaml
management:
  endpoint:
    gateway:
      access: read-only
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

**Explanation:**

- `gateway.access: read-only` allows route/filter read operations as supported by the implementation; it grants no route modification privileges.
- `web.exposure.include` exposes **exactly three endpoint IDs** (`health`, `info`, `gateway`) over HTTP, instead of using a wildcard.
- `health.show-details: never` keeps the health response minimal in this example. If operators need details, design dedicated health groups and permissions.
- This YAML **does not yet define authentication/authorization or network isolation**. If the deployment exposes the management port to the Internet, it is still **insecure**, even when read-only.

An illustrative example (with proper port protection and access) is:

~~~bash
curl -i 'http://127.0.0.1:9091/actuator/gateway/routes'
~~~

If configured with a separate management port at 9091 and the operator is running directly **on an authorized host**, GET can return the JSON route list. If no routes exist yet, the list may be empty. **Do not treat HTTP 200 from localhost as proof that the Internet cannot reach the endpoint**; you must test from outside the network boundary.

### Can You Apply an Access Cap Across All Actuator Endpoints?

Spring Boot lines supporting the endpoint access model may also provide a **global access cap** such as `management.endpoints.access.max-permitted`. If the system only needs to read management data, a global **read-only** cap can add defense in depth. However, that property can also affect other management endpoints; check compatibility and never use it as a substitute for HTTP security. When uncertain about binding/version, prefer per-endpoint configuration and test write operations explicitly.

## 6. Compatibility Configuration for Legacy Lines Using enabled

For a Spring Boot/Gateway line whose version documentation uses **`management.endpoint.gateway.enabled`** instead of access mode:

~~~yaml
management:
  endpoint:
    gateway:
      enabled: true
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

**Critical safety warning:** `enabled: true` does not state that only GET operations are allowed. Depending on implementation and version, Gateway Actuator may expose **POST refresh**, **POST create route**, or **DELETE route** once exposed. With this mechanism:

1. Do not expose the Gateway endpoint to the Internet or business clients.
2. Use **Spring Security WebFlux** to restrict only allowed methods/paths and verify operator identity.
3. Consider a private management port, TLS/mTLS, firewall, or VPN/zero-trust access.
4. Test both `POST` and `DELETE`, not only GET.
5. If this boundary cannot be guaranteed, **do not enable Gateway Actuator** in production just to obtain a route listing.

### If Route Management Write Operations Are Required

The `access: unrestricted` mode (in supported versions) should only be used when the operations team has a **concrete business/operational requirement** to alter routes at runtime, paired with a management channel independent of the user-facing API:

~~~yaml
# Illustration only; NOT recommended on public ports.
management:
  endpoint:
    gateway:
      access: unrestricted
  endpoints:
    web:
      exposure:
        include: gateway
~~~

Do not copy the configuration above into a public environment. Dedicated write permissions, change approval/audit, route destination validation, rollback, SSRF/token-egress prevention, and synchronization across multiple Gateway instances are required. Later sections analyze write operations and their risks.

## 7. Protecting Gateway Actuator with Spring Security WebFlux

In **Spring Cloud Gateway Server WebFlux**, HTTP security policies should be built using **`SecurityWebFilterChain`** from reactive Spring Security, not Servlet `SecurityFilterChain`. The example below assumes:

- Actuator and API share **the same WebFlux application port** and the default `/actuator` base path.
- The Gateway endpoint is configured as **read-only** at the Actuator level, per version capability.
- Operators hold a valid JWT with the **`SCOPE_gateway.read`** authority.
- Business APIs have a separate security chain with a deny-by-default policy.
- The application uses **stateless Bearer tokens**, without relying on cookies/sessions for state-changing operations.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class GatewayHttpSecurityConfig {

    @Bean
    @Order(0)
    SecurityWebFilterChain managementChain(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        ServerWebExchangeMatchers.pathMatchers("/actuator/**"))
                .authorizeExchange(auth -> auth
                        .pathMatchers(HttpMethod.GET, "/actuator/health")
                            .permitAll()
                        .pathMatchers(
                                HttpMethod.GET,
                                "/actuator/gateway",
                                "/actuator/gateway/**")
                            .hasAuthority("SCOPE_gateway.read")
                        .anyExchange()
                            .denyAll()
                )
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                // Strictly for pure Bearer JWT APIs, no cookie auth.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain applicationChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers(HttpMethod.GET, "/api/public/**")
                            .permitAll()
                        .pathMatchers("/api/**")
                            .authenticated()
                        .anyExchange()
                            .denyAll()
                )
                .oauth2ResourceServer(resourceServer ->
                        resourceServer.jwt(Customizer.withDefaults()))
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .build();
    }
}
~~~

**How to read this:**

1. `@Order(0)` and `securityMatcher("/actuator/**")` select the dedicated management security chain **before** the application chain.
2. Health GET is permitted in the example for probes; **this does not mean all health details or all actuator endpoints are public**.
3. Gateway GET operations require an **authority dedicated to management viewing**. Never use `authenticated()` for all of `/actuator/**`, because normal user accounts would then be able to view management information.
4. `anyExchange().denyAll()` in the management chain blocks other endpoints/methods, including route write operations. Do not place `/actuator/**.permitAll()` ahead of management rules.
5. The application chain protects `/api/**` separately; do not rely on Gateway route filters to replace Spring Security at the WebFlux layer.
6. `oauth2ResourceServer(...jwt(...))` **validates presented JWTs**; it does not issue tokens. Proper issuer/trust and audience validation must match the contract.
7. `csrf(...disable)` is an illustrative choice **only when authenticating via Bearer JWT and not using cookies/sessions**. With a cookie-based admin UI or form login, design proper CSRF protection rather than copying this line.

In this example, `info` is in the HTTP exposure list but **cannot be accessed** through the management security chain because `anyExchange().denyAll()` blocks undeclared paths. If viewing `/actuator/info` is needed, add a GET rule with an appropriate authority; if not needed, remove `info` from the exposure list to shrink the surface.

### Configuring the Issuer for the Bearer JWT Example

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/operations
~~~

This is a **fictional lab address**, not a real Identity Provider. Spring Security must be configured to verify signature, issuer, expiration, and **audience matching the management API**. Do not assume `issuer-uri` automatically checks your business audience as desired; add an audience validator appropriate for your version and IdP.

The `SCOPE_gateway.read` authority in code only appears if the JWT access token is mapped from the `gateway.read` scope (or a trusted converter assigns an equivalent authority). If the IdP only issues a `roles: ["OPS"]` claim, you need an explicit **role → authority mapping**; never trust a client-supplied `X-Role: ops` header.

### Multiple SecurityWebFilterChains: Chain Selection Is Not Additive

Spring Security picks the first security chain whose matcher matches in order; it does not merge rules from all chains. If a chain for `/**` precedes the `/actuator/**` chain, management rules may not be applied. Therefore:

- Give the management chain a specific matcher and priority order.
- Use deny-by-default for paths/methods not explicitly permitted.
- Test chain selection with anonymous users, regular users, operators, and under-scoped operators.
- If you change `management.endpoints.web.base-path`, update the matcher accordingly.

**Note on separate management ports:** When `management.server.port` differs from the server port, Spring Boot may create a separate management context/HTTP server. How security chains apply to the management context depends on the application/version configuration. **Do not assume** that seeing `GatewayHttpSecurityConfig` on the application port means the management port is protected. You must test the **exact port, base path, and access source**; add dedicated management-context security configuration if required by the architecture.

## 8. Separating the Management Port from the Public Port

In production, one way to reduce the attack surface is to have the API and management interface listen on **two different ports**, then use network policy so only operational sources can reach the management port.

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoint:
    gateway:
      access: read-only
  endpoints:
    web:
      exposure:
        include: health,info,gateway
~~~

This example is only valid on **versions supporting `gateway.access`**. The management server listens on loopback `127.0.0.1`, reducing external connectivity **on the same host/network namespace**. It does not by itself solve TLS, operator permissions, or every deployment model.

### Understanding Network Namespaces in Containers and Kubernetes

When the application runs inside a container:

- `127.0.0.1` is typically the loopback **of the container or Pod/network namespace**, not the operator workstation's loopback.
- If Prometheus or a sidecar runs elsewhere, listening only on loopback can break scraping or health probes.
- For management access from a monitoring network, you may need to bind an appropriate private interface and use **Kubernetes Service/NetworkPolicy, firewalls, or a service mesh** to restrict source access.
- Never configure `0.0.0.0:9091` and open the port via a public LoadBalancer without authentication and network restrictions.
- If ingress automatically forwards all paths to the application on 8080, splitting out port 9091 helps prevent accidental exposure; still verify mappings and published ports.

**Port separation is a defense layer**, not a replacement for Spring Security. Someone able to reach the management network should not automatically be authorized to read route definitions. Use TLS/mTLS or proper identity mechanisms internally.

### Management Base Path and Liveness/Readiness Probes

The default HTTP path is usually `/actuator`, though it can be changed via `management.endpoints.web.base-path` or path mapping:

~~~yaml
management:
  endpoints:
    web:
      base-path: /manage
~~~

The endpoint can then appear under `/manage/gateway/routes` instead of `/actuator/gateway/routes` (in the corresponding HTTP mapping environment). **Security matchers, ingress rules, firewalls, and monitoring checks must be updated in sync**. Never treat renaming the path as a secret or security mechanism.

Health probes usually need different access from Gateway route inspection. Design **`/actuator/health/liveness`**, **`/actuator/health/readiness`**, or dedicated health paths according to your Spring Boot version's capabilities—never give all management endpoints the same access level just because liveness must be callable unauthenticated.

## 9. Common Gateway Actuator Read Operations

When the endpoint is enabled, exposed, and readable, the following operations are often useful for diagnosing **Gateway Server WebFlux**. **Available operations and payloads may vary by version**:

| HTTP Operation | Purpose | Notes |
| --- | --- | --- |
| `GET /actuator/gateway` | Info/index of Gateway operations if provided by the running release | Identical output is not guaranteed across all releases |
| `GET /actuator/gateway/routes` | Lists available routes with predicate/filter/URI info | Can leak service IDs, hostnames, and internal configuration |
| `GET /actuator/gateway/routes/{id}` | Inspects details of a single route | Route ID and output depend on implementation |
| `GET /actuator/gateway/globalfilters` | Lists GlobalFilters and order/metadata reportable by the endpoint | Does not prove every request passes through every filter |
| `GET /actuator/gateway/routefilters` | Inspects recognized GatewayFilter factories | Does not mean the filter is attached to every route |
| `GET /actuator/gateway/routes/{id}/combinedfilters` | Inspects the combined filter chain for a route if supported | Helps check ordering, does not replace request tracing |
| `GET /actuator/gateway/routepredicates` | Inspects route predicate factories if provided by the release | Useful for identifying registered factories |

**Do not hardcode assumptions that every operation above exists in every release.** Some releases return a different set of operations or change JSON output/verbose formats. The reliable approach is to read the locked version's documentation and test with an HTTP client in an authorized environment.

### What Does Route Listing Tell You?

A route might be declared like this:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-read
              uri: lb://orders-service
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
                - AddRequestHeader=X-Gateway-Source,orders-edge
~~~

When the route is loaded, the read endpoint can help confirm that `orders-read` exists, its URI is `lb://orders-service`, and the expected predicates/filters are declared. However, this is **route definition** info—it does not guarantee:

- Service discovery currently has healthy instances.
- The client's JWT is accepted or authorization succeeds.
- `StripPrefix` produces the right backend path in all edge cases.
- TCP connect/TLS handshake to the backend succeeds.
- The circuit breaker is CLOSED or a request was not retried.
- Every Gateway replica is running the same route definition.

To answer those questions, combine **request traces, safe Spring Security logs, Netty/LoadBalancer metrics, backend stubs, and HTTP tests**.

### Why Are GET Route Results Still Sensitive?

Gateway Actuator output can contain internal URIs, filter arguments, header constants, host matchers, route metadata, or other operational details. In some apps, developers mistakenly place secrets directly in route URIs or filter args — e.g., embedding an API key in `SetRequestHeader`. When that happens, route listing becomes a secret-leak vector.

**Never store secrets in route definitions as if they were public data**, and never rely on Actuator sanitization behavior to protect secrets. Store credentials in a secrets management system, design filters not to log or expose unnecessary secrets, and inspect Actuator output in a test environment.

## 10. Read-Only Is View Access, Not a Comprehensive Health Report

A GET to `/actuator/gateway/routes` can return HTTP 200 when the Gateway is running and route definitions are readable. Yet the Orders backend may be down, the registry empty, or a circuit breaker OPEN. Separate your signals:

| Observation | Question Answered |
| --- | --- |
| Actuator gateway routes | Has the route been loaded into this instance? |
| Spring Boot health | What status do the application/health groups report? |
| Readiness | Should this Gateway instance receive new traffic? |
| Route metrics | Which routes are receiving requests, and what are their statuses and latencies? |
| Reactor Netty metrics | Are connection pools or timeouts saturating? |
| LoadBalancer/discovery | Are suitable `ServiceInstance` entries available? |
| Resilience4j/circuit metrics | Is a breaker OPEN and blocking calls? |
| Tracing and backend logs | Which route/filters did a specific request traverse? |

**Route existence does not mean backend readiness.** Conversely, a management endpoint blocked by security does not mean API routing is broken. Isolating the management plane allows administration without mixing observability permissions with business traffic.

## 11. Write Operations Must Be Treated as High Privilege

In versions/modes supporting mutation, Gateway Actuator may provide operations such as:

| Illustrative HTTP Operation | Meaning | Risk |
| --- | --- | --- |
| `POST /actuator/gateway/refresh` | Requests the Gateway to refresh/reload route info per implementation | An unexpected change can reroute traffic or temporarily drop routes |
| `POST /actuator/gateway/routes/{id}` | Creates/writes a route definition when supported by the operation and repository | Could add a route to an internal service or untrusted upstream |
| `DELETE /actuator/gateway/routes/{id}` | Deletes a route when supported by the operation and repository | Traffic disruption, making critical APIs disappear |

**Having a read endpoint does not mean write operations exist or are available.** `read-only` mode in supported versions should suppress write operations at the Actuator level; in unrestricted mode and legacy lines, verify via tests. The backing `RouteDefinitionRepository` also affects create/delete capability and route persistence.

### Why Is Route Write Access Especially Dangerous?

Anyone authorized to create routes can do far more than “edit a path menu”:

1. Point a route URI at an internal network endpoint never meant for clients.
2. Change `lb://orders-service` to another service not authorized to receive the JWT.
3. Attach `StripPrefix` or `RewritePath` to funnel requests into backend administrative paths.
4. Remove/omit filters checking headers or rate limiting on a route.
5. Create a catch-all `Path=/**` route that shadows active routes.
6. Combined with unsafe filter configs, forward tokens/API keys to an untrusted upstream.

This creates an **SSRF, credential exfiltration, and routing bypass** surface if abused. Therefore, write access requires a **separate access source**, strong authentication, least privilege, change approval, auditing, and destination allowlist validation. Never treat business-level `hasRole("ADMIN")` as sufficient for infrastructure changes.

### Editing Routes at Runtime Is Not the Same as Editing Config Files

Some dynamic route mechanisms affect only an instance's **runtime repository/cache**. Never assume that:

- New routes survive a restart.
- All other Gateway replicas automatically receive the same change.
- A refresh always reloads from the intended configuration source.
- Changes made via Actuator are version-controlled, reviewed, and reversible.

A better workflow is usually **managed GitOps/config repository/service registry**, reviewed deployments, and pre/post-change verification steps. If an organization must manage routes dynamically, clearly define the source of truth, consistency model, propagation, and rollback.

## 12. Safe Testing with an HTTP Client

Only run the HTTP requests below in a **lab environment or authorized management network**. `127.0.0.1:9091` is assumed to match the management port example in Section 8; replace it with the organization-approved endpoint in real environments.

### Minimal Health Check

~~~bash
curl -i 'http://127.0.0.1:9091/actuator/health'
~~~

If health is exposed and policy permits, an example response is:

~~~http
HTTP/1.1 200 OK
Content-Type: application/vnd.spring-boot.actuator.v3+json

{"status":"UP"}
~~~

**This is an illustrative response, not live execution output.** If the app is unhealthy, security differs, or the Actuator format changes, the status/content-type may differ. Never force health to return 200 just to turn probes green.

### Checking Gateway Route Listing

~~~bash
# Without credentials: expect security rejection (usually 401).
curl -i 'http://127.0.0.1:9091/actuator/gateway/routes'

# With legitimately issued operational credentials:
curl -i \
  -H "Authorization: Bearer ${OPS_READ_TOKEN}" \
  'http://127.0.0.1:9091/actuator/gateway/routes'
~~~

In the example above, `OPS_READ_TOKEN` is only a test variable holding a token issued for an **operator**, never a user token. **Never place production tokens directly on the command line, in screenshots, or in shared logs.** Even shell environment variables can leak via OS tracing/process inspection; use appropriate client/secret injection mechanisms in real operations.

### Reading Details of a Single Route

~~~bash
curl -i \
  -H "Authorization: Bearer ${OPS_READ_TOKEN}" \
  'http://127.0.0.1:9091/actuator/gateway/routes/orders-read'
~~~

If `read-only` is enabled, the GET calls above can succeed **when** authorized, the endpoint is actually loaded, and the route exists. If the request returns 404, distinguish between **missing route ID** and **Gateway Actuator unexposed/disabled**. The troubleshooting section below systematizes this.

### Never Use Write Operations to “Test Permissions” in Production

**Never run `POST /actuator/gateway/refresh` or `DELETE /actuator/gateway/routes/{id}` in production just to see whether it gets rejected.** A misconfigured security rule could execute the request and cause an outage. Test write protection using **WebTestClient/isolated environments**, targeting a dummy route ID and asserting no changes in the repository/backend counters.

## 13. Default Spring Security Is Not a Permanent Security Guarantee

Spring Boot auto-configures Actuator security when Spring Security is present, yet defining one or more **custom `SecurityWebFilterChain` beans** can alter or replace how Boot protects endpoints. **Do not assume that simply adding `spring-boot-starter-security` keeps every Actuator endpoint locked down per organizational policy.**

### Verify All Three Protection Layers

| Protection Source | Goal | Question to Ask |
| --- | --- | --- |
| Actuator endpoint access | Do not register disallowed operations | Does `read-only` actually hide write operations in the running version? |
| Spring Security WebFlux | Per-request authentication/authorization | What status do anonymous, user, ops-read, and ops-write receive? |
| Network/TLS/mTLS | Restrict who can connect to the management HTTP server | Is there any path from the Internet or other tenants to the management port? |

Suppose a team already has Spring Security for `/api/**` and adds Actuator:

~~~java
// ANTI-PATTERN: matcher only protects /api/**.
// Do not treat this as a complete security policy for management endpoints.
.authorizeExchange(auth -> auth
        .pathMatchers("/api/**").authenticated()
        .anyExchange().permitAll())
~~~

With the trailing `anyExchange().permitAll()`, if that chain covers `/actuator/gateway/routes`, the endpoint can be called anonymously once exposed. Switch to a management-specific chain or deny-by-default with explicit matchers, ensuring default API configs never open Actuator.

### Separating Read and Write Permissions

A reference authority model:

| Role | Appropriate Permission | Prohibited |
| --- | --- | --- |
| Public user | No Gateway Actuator permissions | Reading routes/filters or modifying routes |
| Application user | Calls business APIs with JWT | Reading Gateway Actuator merely by being logged in |
| Operations viewer | `SCOPE_gateway.read` | Mutating/refreshing unless explicitly authorized |
| Operations change manager | Dedicated authority for infrastructure changes via approved workflow | Bypassing audit, destination allowlist, or review |
| Break-glass operator | Temporary privilege granted under emergency procedure | Retaining unrestricted access long-term |

If the version supports `access: read-only`, **even a user with a write scope** cannot invoke Actuator write operations that the endpoint does not register. When unrestricted mode is temporarily needed, execute an approved, time-bounded change, separate the **management change workflow** from the data plane, and restore read-only afterward.

### CSRF and Write Methods

In the Security WebFlux example using **Bearer JWTs not sent automatically by browsers like cookies**, CSRF was conditionally disabled. If a management API uses browser sessions/cookies or cookie-based SSO, **CSRF protection must be properly designed** for POST/DELETE. Never “fix” a 403 error by unconditionally disabling CSRF or opening `permitAll` on management endpoints.

### Do Not Rely on a GatewayFilter to Protect Actuator

A `GlobalFilter` or `GatewayFilter` only runs when requests are processed by the corresponding **Gateway FilteringWebHandler**. `/actuator/gateway/**` is a WebFlux/Actuator endpoint and does not necessarily pass through Gateway routes. Therefore:

- Do not write a GlobalFilter checking `X-Admin: true` and conclude Actuator is protected.
- Do not expect `RequestRateLimiter` on a `Path=/**` route to automatically meter Actuator traffic.
- Do not expect `StripPrefix` or `RewritePath` on a Gateway route to apply to Actuator.
- Enforce protection at **Spring Security WebFilter** and the actual **management HTTP/network boundary**.

If you define a catch-all `Path=/**` Gateway route, test that it does not interfere with or shadow management mappings according to the application's `HandlerMapping` order. Regardless of which handler receives the request, the security policy must never become more permissive.

## 14. Interpreting 401, 403, 404, and 405 When Calling Actuator

When a GET to Gateway Actuator fails, determine **where the request was blocked** before changing configuration.

| Observation | Possible Legitimate Causes | Diagnostic Step |
| --- | --- | --- |
| **Connection refused / timeout** | Wrong port, loopback-only bind, network policy, server not listening | Check listeners, ingress/Service, exact IP:port |
| **TLS handshake failure** | Wrong scheme, CA, hostname, or mTLS identity | Check certs/trust; never disable verification |
| **401 Unauthorized** | Missing valid token or Resource Server rejected token | Check issuer, audience, expiration, operator credentials |
| **403 Forbidden** | Valid token missing required authority or denied by security rule | Check chain order, `SCOPE_gateway.read`, CSRF if cookie-based |
| **404 Not Found** | Endpoint not enabled/`access=none`, unexposed, wrong base path, nonexistent route ID, or different mapping | Check Boot/Gateway version and Actuator mappings |
| **405 Method Not Allowed** | Operation exists but method is unsupported or disallowed by access mode | Check read-only vs write operation in the actual version |
| **200 with empty JSON** | Endpoint readable but no routes configured, empty route repository, or response lacks expected info | Verify route definition source and target instance |
| **500 or 503** | Internal error building route definitions, actuator, security, or dependency | Inspect safe logs and authorized stack/metadata |

**A status code does not always point to a single cause.** For instance, an unexposed path might return 404 at the mapping layer, while a security chain with a broad matcher might return 401/403 **before knowing** whether a matching handler exists. For write endpoints in read-only mode, the response may be 403, 404, or 405 depending on security/mapping/version. Verify against policy and endpoint behavior rather than treating a status code as final proof.

### Diagnostic Procedure Without Expanding Privileges

1. **Verify the exact HTTP port**, scheme, base path, and reverse proxy path rewrites.
2. **Check the Actuator starter** and Spring Boot + Spring Cloud Gateway versions in approved dependencies.
3. **Check endpoint access/enable settings**, avoiding mixing properties from two eras.
4. **Check exposure include**, never temporarily switching to `"*"` in production.
5. **Check security matchers/chain order**, and the operator's issuer/audience/authority.
6. **Call the approved health endpoint** to confirm the management server is alive, without inferring the gateway endpoint is enabled from health 200.
7. **Call the read endpoint with a valid ops token** inside the management network.
8. **Check the route ID and repository** if the endpoint returns JSON without the expected route.
9. **Run negative tests for write access in a lab**, never sending test POST/DELETE requests directly to production.

### Specific Case: Health UP, Gateway Returns 404

This is not necessarily a proxy error. Boot Actuator may be exposing `health`, while `gateway` is not yet permitted by `management.endpoint.gateway.access` or is missing from `web.exposure.include`. The fix is to set the right **version-appropriate** property—not to alter route predicates or enable `permitAll`.

### Specific Case: Route Listing Returns 200, Client API Receives 503

GET route listing only confirms the **route is loaded into the instance**. A client HTTP 503 can result from missing `ServiceInstance`, TLS/connect timeouts, overloaded backend, OPEN circuit breaker, Gateway rate limiting/fallback, or upstream returning 503. Inspect the **load balancer, HTTP client, breaker state, and telemetry**; granting Actuator write access will not fix the root cause.

## 15. Never Blindly Feed Both Configurations to One Version

When migrating from `enabled` to `access`, certain setups cause confusion:

~~~yaml
# DO NOT blindly copy this without knowing precedence/version.
management:
  endpoint:
    gateway:
      enabled: true
      access: read-only
~~~

In one version, `enabled` may still be read for compatibility; in another, `access` is the primary setting; in a version not supporting one property, it may have no effect. If another config layer (environment, config server, deployment manifest) overrides values, the effective result differs from application YAML.

### Principles for Auditable Configuration

- **Lock the BOM**, never mixing a too-new Gateway starter into an older Boot release just to get endpoint access.
- Choose **one approved management config source**, avoiding duplicate values scattered across multiple profiles.
- Document in deployment specs: “Boot/Gateway version, endpoint enable property, access mode, exposure, port, allowed principals, write policy”.
- On versions supporting `access`, set `read-only` **explicitly** rather than relying on defaults that may shift across upgrades.
- Check config binding warnings after upgrades, without treating “the app starts” as proof of security.
- Maintain a test confirming “GET can read, POST/DELETE cannot execute” before promoting a new release to production.

### Per-Environment Configuration

A reasonable policy might be:

| Environment | Gateway Actuator | Who Can View? | Runtime Route Changes Allowed? |
| --- | --- | --- | --- |
| Local development | Can enable read-only for learning/diagnostics | Developer on local machine | Only in a controlled lab |
| CI/integration test | Enabled per test, including unrestricted when testing writes | Isolated test harness | Allowed in test sandbox |
| Staging | Read-only, private network, auth | Authorized SRE/ops | Per change workflow if needed |
| Production | Read-only or disabled when unnecessary | Very few approved operators/automation | **No** by default; only if a dedicated workflow requires it |

**Never treat staging as a safe place to use production tokens.** Test data and credentials must stay separate. In production, if only health/metrics are needed operationally and route listing is unnecessary, **disabling the Gateway endpoint completely** is a good way to reduce attack surface.

## 16. Route Information Is Also Sensitive Data

The primary risk of a read-only endpoint is **information disclosure**, even without mutation:

~~~text
GET /actuator/gateway/routes
    -> route ids
    -> predicates / host & path patterns
    -> gateway filter names / arguments
    -> lb:// service IDs or HTTP backend URIs
    -> route metadata / ordering
~~~

This information can help an attacker discover:

- Admin APIs or internal endpoints not publicly advertised.
- How paths/headers are rewritten to reach backends.
- Service IDs and internal network addresses, including services using TLS/mTLS.
- Configured rate limiting layers, authentication filters, or fallbacks.
- Route IDs to target misconfigurations or correlate log entries.

### Three Rules on Secrets in Route Configuration

1. **Never embed credentials** in `uri`, route metadata, request header filter args, or raw URL queries. Manage secrets through dedicated systems and use service identity/TLS and token exchange as needed.
2. **Never paste raw Actuator responses into public logs/tickets**. When sending output to support, redact URIs, hosts, filter args, and sensitive details.
3. **Restrict viewers** via read-only policy + ops role/scope + private network. Anyone authorized for GET can still copy the response, so enforce proper auditing, retention, and access controls.

### What Data Should Be Exported to Metrics?

To measure route counts or identify routing failures, prefer standard low-cardinality metadata such as **route ID**, HTTP status, latency, and normalized error categories. Never use:

- Raw JWTs, API keys, Cookies, or secret filter arguments.
- Raw request URIs containing `?access_token=...`.
- Unbounded client-supplied user IDs/tenant IDs or hosts as metric labels.
- Entire Actuator JSON payloads as a span attribute.

Separate **logs, metrics, and traces** from Actuator route listing: each channel has distinct access controls and sensitivity levels. Enabling Gateway Actuator does not automatically make Reactor Netty wiretap or HTTP body logging safe; each mechanism requires its own policy.

## 17. Multi-Replica Spring Cloud Gateway: Is Route Listing Consistent?

In Kubernetes or multi-instance deployments, an operator tool may hit the management port of **one Gateway pod**:

~~~mermaid
flowchart TD
    Ops["Ops read request"] --> Mgmt["Private management service"]
    Mgmt --> G1["Gateway G1: route set v2"]
    Mgmt --> G2["Gateway G2: route set v1"]
    Mgmt --> G3["Gateway G3: route set v2"]
    Pub["Public ingress"] --> G1
    Pub --> G2
    Pub --> G3
~~~

If route definitions are loaded from config files, service discovery, or a dynamic repository, there may be **config propagation lag**, version mismatches, or instances not restarted/refreshed simultaneously. Hence:

- GET `/actuator/gateway/routes` on G1 **does not prove** G2 and G3 hold the same list.
- A POST refresh sent through a load balancer to one Pod **does not guarantee** all Pods have refreshed.
- A dynamically created route on G1 **does not automatically** exist on G2 if the backing store is not shared.
- Routing bugs can appear intermittently as clients hit different instances.

### Checking Consistency During Rollouts

1. Identify the **source of truth** for route definitions: config repository, static YAML, discovery, database, or custom `RouteDefinitionRepository`.
2. Tag deployments with **deployment revision/config version** using non-sensitive operational metadata.
3. Check route counts/IDs per instance or via a controlled per-Pod query workflow.
4. Send test requests across instances or orchestrate tests to catch mismatches.
5. Verify readiness before ingress routes traffic to new Pods.
6. If runtime refresh exists, document **which events trigger refresh**, propagation delay, rollback, and the impact if a Pod misses an event.

You do not need to open `access: unrestricted` to solve every inconsistency. Sometimes the issue lies in config sync, deployment, or caching; the fix is to repair the **definition source and rollout process**, not to add ad-hoc write calls per instance.

## 18. Protecting Management Paths When There Is a Gateway in Front of a Gateway

Many organizations place a reverse proxy, ingress, or another Gateway in front of management endpoints. You must then distinguish **hostname, path, authentication, and upstream**:

~~~mermaid
flowchart LR
    O["Trusted operator"] --> Z["VPN / zero-trust access"]
    Z --> I["Private ingress / mTLS"]
    I --> S["Spring Security WebFlux"]
    S --> A["/actuator/gateway/routes"]
    X["Internet client"] -. "Denied by network" .-> I
~~~

Items to verify:

1. **Never create a public route** `Path=/actuator/**` pointing directly to the management port just for convenience.
2. If ingress rewrites `/manage` to `/actuator`, the security chain must inspect **the exact path received by the application**, and ingress must not expose bypass paths.
3. Never treat client-supplied headers like `X-Operator: true` or `X-Forwarded-Host` as proof of identity.
4. If the proxy performs authentication, still define the **trust relationship between proxy and Gateway**, and how the Gateway receives/verifies the principal; TLS/mTLS or audience-restricted tokens are typically useful.
5. Define request/response size limits, timeouts, rate limiting, and auditing for the management plane; do not let an oversized route listing endpoint create unbounded resource usage.
6. Verify HTTPS/mTLS to the management server across the network; avoid sending ops tokens over plain HTTP outside trusted loopback.

**Renaming a URL to something hard to guess is not security.** You need operator authentication, least privilege, network isolation, and evidence from negative tests.

## 19. Testing Gateway Actuator Authorization with WebTestClient

A security configuration is only considered complete when covered by **negative tests**: unauthorized requests cannot read routes, requests with a regular user token are denied, and requests using a read-only operator token **cannot modify routes**.

### Required Permission Matrix

Assuming the lab environment uses `read-only`, selective exposure, and Security WebFlux as in Section 7:

| Request | Anonymous | Valid User Token Without Ops Authority | Operator With `SCOPE_gateway.read` |
| --- | --- | --- | --- |
| `GET /actuator/health` | Allowed if health is exposed | Allowed | Allowed |
| `GET /actuator/gateway/routes` | **401** typical | **403** typical | Allowed to read route listing |
| `GET /actuator/gateway/globalfilters` | Denied | Denied | Allowed to read if operation is available |
| `GET /actuator/gateway/routes/orders-read` | Denied | Denied | Allowed to read when route ID exists |
| `POST /actuator/gateway/refresh` | Denied or operation unregistered | Denied or operation unregistered | **Must not refresh** |
| `POST /actuator/gateway/routes/new-route` | Denied or operation unregistered | Denied or operation unregistered | **Must not create route** |
| `DELETE /actuator/gateway/routes/orders-read` | Denied or operation unregistered | Denied or operation unregistered | **Must not delete route** |
| `GET /actuator/env` | Denied | Denied | **Denied** per example policy |

**Exact status codes** may be 401, 403, 404, or 405 depending on security/mapping order and version. What must be guaranteed for write operations is **zero mutation**. Never accept HTTP 2xx simply because the response body contains the word “error”.

### Integration Test: Anonymous and Operator Reads

In an isolated test environment, you can use `WebTestClient` against the **real management port**:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayActuatorAccessIT {

    private final WebTestClient client = WebTestClient.bindToServer()
            .baseUrl("http://127.0.0.1:9091")
            .build();

    @Test
    void anonymousCannotReadRoutes() {
        client.get()
                .uri("/actuator/gateway/routes")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void operatorCanReadRoutes() {
        // Token issued by test IdP with valid issuer/audience/scope.
        String token = System.getenv("OPS_READ_TEST_TOKEN");
        assertThat(token).isNotBlank();

        client.get()
                .uri("/actuator/gateway/routes")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void operatorCannotUseRefreshWriteOperation() {
        // Run only in sandbox; if misconfigured, POST may mutate state.
        String token = System.getenv("OPS_READ_TEST_TOKEN");
        assertThat(token).isNotBlank();

        client.post()
                .uri("/actuator/gateway/refresh")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
                .exchange()
                .expectStatus().is4xxClientError();
    }
}
~~~

**Run prerequisites:** The Gateway must be started in the lab on port 9091 with Actuator and Spring Security properly configured, JUnit/Spring Test/AssertJ available, and test-only tokens supplied. This illustrative snippet is **not live execution output**. In a different topology, adjust the port/base path to match your deployment.

The POST test above is **safe only in a sandbox** because if security is misconfigured, the refresh could actually execute. In real tests, beyond checking the status code, verify **no side effects** via event/counter checks or route definition snapshots. For DELETE, use only dummy route IDs and an isolated repository; never send DELETE to critical routes in production.

### Testing App User Permissions and Invalid Tokens

Add tests using a valid test token **without** `SCOPE_gateway.read` and assert GET route listing is denied. Then test:

1. JWT with invalid signature.
2. Expired JWT.
3. JWT with wrong issuer or audience.
4. JWT containing `roles: ["OPS"]` claim where the authority converter has not mapped it to `SCOPE_gateway.read`.
5. Revoked/expired ops token per IdP policy.

**`mockJwt()` tests only verify matcher/authority logic**—they do not validate real signatures, issuers, audiences, or JWKS configuration. Use signed test tokens/test IdP and a real decoder to test authentication end-to-end.

### Testing on the Right Context/Port

If `management.server.port` is 9091, test port 9091 directly **and** attempt to access `/actuator/gateway/routes` through the public API port 8080. Expect the public path not to expose management endpoints when the architecture restricts exposure to a separate port. If a proxy rewrites paths or uses custom management path mappings, test through the ingress too, not just `WebTestClient` bound directly to the process.

## 20. Common Configuration Mistakes and Fixes

| Anti-Pattern or Issue | Consequence | Fix |
| --- | --- | --- |
| Adding `spring-boot-starter-actuator` and assuming Gateway endpoint is enabled and secured | Endpoint missing, or exposed with unintended permissions | Configure enable/access, exposure, and security per version |
| Using `enabled: true` on a version that should use `access` without testing | No read-only guarantee | Use the version-appropriate property, test write denial |
| Setting only `web.exposure.include=gateway` | Endpoint may not be available or security may be wrong | Verify all three gates: access/expose/security |
| Treating `read-only` as a replacement for auth | Outsiders can read routes/filters if port is public | Protect with Spring Security + network |
| Using `management.endpoints.web.exposure.include: "*"` | Exposes many sensitive management surfaces | Include selectively |
| Having `anyExchange().permitAll()` in a custom security chain | Actuator may be exposed when Boot auto-security backs off | Dedicated management chain, deny by default |
| Attaching only a security GatewayFilter for `Path=/actuator/**` | Does not necessarily run for Actuator handlers | Use WebFlux `SecurityWebFilterChain` |
| Using business admin `hasRole("ADMIN")` | Mixes application roles with infrastructure privileges | Separate ops read/write authorities |
| Configuring a separate management port without testing its security context | Separate port may not receive the expected chain | Run integration tests directly against management port |
| Binding loopback inside a container so Prometheus cannot scrape | Loss of monitoring/readiness | Choose an appropriate network boundary + policy |
| Exposing 9091 via a public LoadBalancer | Management API reachable from the Internet | Private Service, firewall/NetworkPolicy, TLS |
| Changing `base-path: /manage` but forgetting the security matcher | Old rules no longer match | Update route/path matchers and test |
| Route listing returns 404 and editing Path predicates | Diagnosing the wrong layer | Check Actuator access/exposure/path |
| GET routes returns 200 and assuming Orders backend is healthy | Overlooks missing instances, TLS, timeouts | Use dependency health/metrics/traces |
| Running POST refresh after rollout affecting only one Pod | Gateway replicas out of sync | Design config propagation/source of truth |
| Allowing dynamic routes with arbitrary URIs | SSRF, route bypass, token exfiltration | Change approval, destination allowlist, network egress policy |
| Placing API keys in `SetRequestHeader` and exposing route listing | Secret leak via output/diagnostics | Dedicated secret management, limit endpoint output |
| Using user tokens to call management | Over-privileged access | Separate ops tokens, clear audience/scope |
| Testing write protection with DELETE on a real route in production | Can cause an outage if misconfigured | Negative tests in sandbox |
| Pasting full routes JSON into public tickets | Leaks internal topology | Redaction and sharing controls |

### When 404 Persists Despite Adding Exposure

Do not keep tweaking firewalls or loosening `permitAll` if the response is 404. First verify:

- Correct **Gateway Server WebFlux** application with **Actuator starter**.
- Gateway endpoint is available via `access` or `enabled` for the exact version.
- HTTP exposure include contains `gateway`, not just `health`.
- Base path/port are correct, with no unexpected ingress rewrite.
- The security chain is not intentionally returning 404 via a custom handler.
- The `/actuator/gateway/routes` path matches the endpoint mappings provided by the running release.

Nothing requires opening Actuator with a wildcard; wildcards only expand the attack surface.

## 21. Deployment and Rollback Procedure for Gateway Actuator

Management plane changes must be reviewed as security changes, even when adding read-only GET access.

### Before Deployment

1. **Lock versions:** record exact Spring Boot/Gateway versions and the dependency BOM.
2. **Define scope:** do you need to read routes/filters, or are write operations needed? If not needed, do not enable the endpoint.
3. **Choose mode:** `read-only` if supported; on legacy lines, set `enabled` paired with strict security/network controls.
4. **Lock network:** management port, private address, ingress, mTLS/TLS, and allowed sources.
5. **Lock authorization:** ops scope/role, issuer/audience, token storage/rotation, break-glass policy.
6. **Lock exposure:** include only needed endpoint IDs; keep health details minimal.
7. **Prepare tests:** route read succeeds with ops token, anonymous/user tokens and out-of-policy writes are blocked.

### During Deployment

1. Apply the config to a staging/lab environment running the same version.
2. Test from both the management network and an **unauthorized source** to verify real firewall/security enforcement.
3. Verify endpoint responses leak no credentials and do not accidentally reveal internal secrets.
4. Execute a controlled rollout, checking replicas and config revisions.
5. Monitor API Gateway rate/latency/errors to spot anomalies when the management server is enabled.
6. Confirm probes, Prometheus scraping, and automation are unaffected by port/path changes.

### If Misconfigured Exposure Is Detected

1. **Block access immediately at the network boundary** to reduce exposure while fixing the config.
2. Narrow HTTP exposure, switch the endpoint to read-only or disable it per version; apply controlled config/deployment updates.
3. Review logs/audits to see whether route GET info or POST/DELETE was invoked by unexpected sources.
4. If routes were altered without authorization, restore from the **source of truth**, verify every instance, and inspect destination/token egress.
5. If secrets leaked via route listing, execute proper credential rotation/revocation; do not merely delete log lines.
6. Add negative tests and change controls to prevent recurrence.

**Never “quick-fix” by renaming the base path to an obscure string.** That is security by obscurity and does not solve actual access control.

## 22. Hands-On Exercise: Enabling Read-Only Gateway Actuator in a Multi-Route Gateway

**Scenario:** A learning system consists of Catalog, Orders, and Identity services. Spring Cloud Gateway receives requests on port `8080` and defines route predicates/filters for the three services. The learner wants to inspect loaded routes, **without allowing Internet users or regular logged-in users to view or modify routes**.

### Part A — Verify Environment and Choose Mode

1. Confirm the Gateway uses **Server WebFlux**, along with Spring Boot/Gateway versions and the Actuator starter.
2. Set up a backend stub for Catalog and an illustrative Orders service ID/URI; verify public/private API routes behave per contract.
3. If the version supports `management.endpoint.gateway.access`, select **`read-only`** and include the exact endpoint ID in HTTP exposure.
4. If the legacy line only supports `enabled`, turn on the endpoint using the version-supported property, but **do not assume read-only is enforced**; prepare an explicit HTTP read-only method policy and network isolation.
5. Choose a private management port, e.g., 9091; in containers, decide on bind/listener settings compatible with the monitoring network.
6. Do not enable `unrestricted` outside a sandbox without a clear purpose and change workflow.

### Part B — Configure Access Paths

A lab configuration on a **Spring Boot line supporting read-only endpoint access**:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9091
    address: 127.0.0.1
  endpoint:
    gateway:
      access: read-only
    health:
      show-details: never
  endpoints:
    web:
      exposure:
        include: health,info,gateway

spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-read
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
            - id: orders-read
              uri: http://127.0.0.1:9002
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
~~~

In this example, the test backends must listen on `9001`/`9002` in a namespace reachable by the Gateway; inside Docker, `127.0.0.1` of the Gateway container is **not** the backend container's address. When switching to service discovery, use `lb://catalog-service` with the appropriate Spring Cloud LoadBalancer dependency. These two routes serve as test data; learners do not need to assume the Identity service is live simply to test Actuator route listing.

**You must add Spring Security** per Section 7 or an equivalent verified management-port policy. The YAML above only illustrates port/exposure/access and route definitions; by itself it is not security-complete.

### Part C — Verify Route Reading

In the lab with a secured management server:

~~~bash
# Minimal health probe:
curl -i 'http://127.0.0.1:9091/actuator/health'

# Without ops token: expect rejection:
curl -i 'http://127.0.0.1:9091/actuator/gateway/routes'

# With TEST environment ops READ token:
curl -i \
  -H "Authorization: Bearer ${OPS_READ_TEST_TOKEN}" \
  'http://127.0.0.1:9091/actuator/gateway/routes'

# Inspect a specific route:
curl -i \
  -H "Authorization: Bearer ${OPS_READ_TEST_TOKEN}" \
  'http://127.0.0.1:9091/actuator/gateway/routes/catalog-read'
~~~

Verify route IDs `catalog-read` and `orders-read`, target URIs, predicates, and filters. If the JSON format differs from documentation examples, do not force it into a guessed schema: use the actual output from your running version and assert only relevant attributes.

**Never use real tokens in exercise outputs.** Use test-only signed JWTs with a short TTL and matching audience/scope. Once finished, revoke or let test tokens expire per procedure.

### Part D — Negative Tests for Read/Write

| Case | Action in Lab | Expected Result |
| --- | --- | --- |
| A | Anonymous GET `/actuator/gateway/routes` | Blocked by security |
| B | User JWT without ops permission GET route listing | Permission denied |
| C | JWT `SCOPE_gateway.read` GET route listing | Succeeds if endpoint is properly loaded |
| D | Ops-read JWT POST refresh | **Cannot refresh** |
| E | Ops-read JWT POST new route | **Cannot create route** |
| F | Ops-read JWT DELETE test route | **Cannot delete** |
| G | JWT with wrong issuer/audience/expired GET routes | Cannot read routes |
| H | GET routes from disallowed network/ingress | Cannot reach management endpoint per policy |
| I | Call `/actuator/gateway/routes` via public API port `8080` | Management endpoint not exposed on public port |
| J | Change management base path in lab | Only new mapping/matcher works; old path does not stay unexpectedly open |
| K | Downgrade to `access: none` in lab | Gateway endpoint no longer available |
| L | Legacy line with `enabled: true` | GET works per policy, writes remain blocked by security/network |

Cases D/E/F **must run only in a sandbox with test repositories/route IDs**, never targeting critical production routes. After each test, confirm **no changes to route definitions**. Under read-only mode, operations may not be registered; 403/404/405 depends on version and security order, while **zero HTTP writes executed** is the true pass criterion.

### Part E — Simulate Multi-Replica Operations

1. Run two Gateway instances G1 and G2 with identical route definitions from the test source of truth.
2. Call the read endpoint on **each instance individually**, not only through a random load balancer.
3. Compare route IDs, predicates, URIs, and config/deployment revisions.
4. Change G1's route config **in the sandbox** to observe mismatch detection.
5. Restore via the controlled config/deployment workflow; do not try to dynamically create an overriding route everywhere.
6. Confirm public APIs still route properly and management security denies regular users.

### Part F — Diagnose and Complete the Report

Record the following details:

- Spring Boot and Spring Cloud Gateway versions, starter, and route namespace.
- The **`access` or `enabled`** property used and the rationale.
- `management.endpoints.web.exposure.include` along with management port/base path.
- Spring Security rules, and the ops JWT issuer/audience/authority.
- GET route listing results with ops token and negative tests for anonymous/user callers.
- Evidence that write operations are disallowed; no routes were unexpectedly created/deleted/refreshed.
- Access results from the management network and an out-of-policy network.
- Route consistency across replicas, if applicable.

**Passing criteria:** Gateway Actuator runs under the right version/configuration, operators can inspect routes/filters for diagnostics, regular users and the Internet have no access, write operations never occur outside policy, no secrets leak, and route inspection is not confused with backend health checks.

## 23. Summary

- **Gateway Actuator belongs to the management plane**, separate from APIs proxied by Spring Cloud Gateway for clients. It enables inspecting routes/filters and, in certain modes/versions, modifying routes.
- Enabling it safely requires considering **three gates**: endpoint access/enable, HTTP exposure, and authentication/authorization + network isolation.
- On Spring Boot/Gateway versions supporting access mode, **`management.endpoint.gateway.access: read-only`** is the right choice when only observation is needed. On legacy lines, **`management.endpoint.gateway.enabled: true`** does not equate to a read-only guarantee.
- **`management.endpoints.web.exposure.include=gateway` only opens the HTTP surface**—it neither grants permissions nor protects the reader. Never use wildcard exposure on a public Gateway.
- Use **Spring Security WebFlux** with a dedicated ops authority and deny-by-default; never use a `GatewayFilter` or business admin role instead of Actuator security.
- **Private management ports, TLS/mTLS, network policies, and testing from unauthorized networks** form essential defense layers. With separate ports or containers, verify the real context, bind address, and path.
- Read operations like `GET /actuator/gateway/routes` can reveal service IDs, backend URIs, predicates, and filter args. Never put secrets into route definitions or share Actuator output publicly.
- Write operations like refresh, create route, or delete route carry risks of outages, SSRF, and credential exfiltration; **enable unrestricted mode only with a dedicated operational workflow**.
- In multi-replica deployments, **route listing on one instance does not prove cluster-wide synchronization**. Rely on the source of truth, rollout checks, health, metrics, and request traces for diagnosis.
- Tests must verify **GET succeeds for ops, anonymous/user callers are blocked, and POST/DELETE cause no mutation**, while distinguishing 401/403/404/405 by configuration and version.

The goal is not “exposing as many Actuator endpoints as possible for operational convenience”, but **providing the necessary observability over a protected administrative channel, with least privilege and exact compatibility with the running version**.
