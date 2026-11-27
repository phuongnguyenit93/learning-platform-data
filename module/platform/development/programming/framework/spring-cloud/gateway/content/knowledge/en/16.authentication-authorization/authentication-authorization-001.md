# Authentication Boundary at the Gateway and Authorization Checks at the Service

## 1. Context: A Single Entry Point Does Not Replace Microservice Security

In a microservices system, **SPRING_CLOUD_GATEWAY** is the entry point that receives requests from clients, evaluates route predicates and the filter chain, can modify paths/headers, selects instances via `lb://`, applies rate limiting, circuit breakers, retries, TLS, and records telemetry. Because the Gateway sits at the **system ingress boundary**, performing authentication checks here helps reject invalid requests early.

However, the Gateway **does not own all data and business rules** of every service. A valid token with permission to call the "read order" API does not necessarily allow the user to read **any order**.

For example:

- User `user-a` owns order `O-100`.
- User `user-b` owns order `O-200`.
- Both have the `orders.read` scope, meaning they are allowed to use the order-reading capability.
- `user-a` sends `GET /api/orders/O-200`.

The Gateway can verify `user-a`'s token and see that the `orders.read` scope is valid. **Orders Service must still deny access to `O-200`**, because only this service (or a trusted business authorization component it uses) knows who owns the order.

**Core principle: authentication at the Gateway does not replace authorization checks at the service.** You should view the Gateway as an early control layer, while the service is where the final authorization decision is enforced based on the actual resource.

### Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **authentication**, **authorization**, and **business/resource-level authorization**.
2. Identify the responsibilities of the Gateway, Identity Provider, and downstream services following the **defense in depth** principle.
3. Configure Spring Security WebFlux Resource Server to verify JWTs (`iss`, signature, `exp`/`nbf`, `aud`) and check scopes at the Gateway.
4. Implement order ownership checks in Orders Service without trusting client-supplied IDs/headers.
5. Explain how `401` differs from `403`, `WebFilter` differs from `GlobalFilter`, and `TokenRelay` differs from authorization checks.
6. Test early rejection at the Gateway, resource-based rejection at the backend, and direct calls to the service.
7. Recognize trust boundaries when using TLS/mTLS, `lb://`, rate limiting, retry, circuit breakers, and observability.

> **Technical scope:** examples illustrate Spring Boot 3.5.x, Spring Cloud 2025.0.x, **Spring Cloud Gateway Server WebFlux 4.3.x**, Spring Security 6.5.x. The Gateway starter uses `spring-cloud-starter-gateway-server-webflux`; route YAML uses the `spring.cloud.gateway.server.webflux` prefix. The stated versions illustrate a compatible pair, not a recommendation to pin `*.0` releases forever in production.

## 2. Authentication and Authorization Are Two Different Questions

| Concept | Question to answer | Example |
| --- | --- | --- |
| **Authentication** | "Which identity did the request come from, and is the identity proof valid?" | Verify JWT signature, issuer, audience, token expiration, and other token requirements. |
| **Coarse-grained authorization – API-level authorization** | "Is this identity allowed to call this **API group** with this HTTP method?" | The token must have `SCOPE_orders.read` to `GET /api/orders/**`. |
| **Fine-grained / resource authorization** | "Is this identity allowed to read **order O-200** belonging to which tenant/user?" | Match the token's `sub` against the order's owner/tenant in trusted data. |
| **Network trust** | "Did the call to the service originate from an accepted connection/host?" | NetworkPolicy, mTLS, service-to-service identity. |
| **Transport security** | "Is data protected in transit?" | HTTPS and certificate/hostname verification across all legs that need protection. |

A common mistake is putting scope checks in the Gateway and assuming every service inside the network can trust `X-User-Id` or skip owner checks. This approach has flaws: requests can bypass the Gateway if a service is accessed directly, or another internal service that is not fully trusted can make cross-service calls.

### Horizontal and Vertical Authorization

- **Vertical authorization:** a user can read but cannot modify/delete. For example, `orders.read` differs from `orders.write`.
- **Horizontal authorization:** two users have the same role/scope but must not access each other's resources. For example, `user-a` must not view `user-b`'s `O-200`.
- **Tenant isolation:** the same ID or route in a multi-tenant system must match the token's tenant against the tenant stored on the record; a tenant ID sent by the client is not trustworthy on its own.

The Gateway typically handles **token format, HTTP method, path, and basic scopes** well, whereas the service must check **owner, tenant, business state, and per-record permissions**. For decisions spanning multiple services, a shared policy system can be used, but the service must still call or enforce the policy reliably.

## 3. Trust Boundaries in an API Gateway Architecture

```mermaid
flowchart LR
    U["Client"] -->|"Access token"| G["Gateway WebFlux\nSpring Security"]
    I["Identity Provider\nIssuer + JWKS"] -.->|"Public keys / metadata"| G
    G -->|"Request after API-level checks"| O["Orders Service\nResource Server"]
    I -.->|"Public keys / metadata"| O
    O -->|"Check owner / tenant"| DB[("Orders DB")]
    O -->|"200 / 403 / 404"| G
    G -->|"HTTP response"| U
```

**Identity Provider (IdP)** is responsible for issuing access tokens according to OAuth2/OIDC policies; it does not inherently know whether order `O-200` belongs to the requesting user at read time.

**Gateway** receives the token, verifies its validity, and applies general API conditions. The Gateway can reject with `401`/`403` **before** selecting an upstream to proxy to.

**Orders Service** is a separate resource server that must answer: which service is this token intended for; what scopes does it have; who is the caller; is the caller allowed to read the order from the database? The service must not treat "having passed through the Gateway" as sufficient self-proof to allow every operation.

**Database / domain data** holds the source of truth about the order's owner, tenant, management permissions, or status. The path `/orders/O-200` is merely an access request, **not proof of permission**.

### Practical Division of Responsibilities

| Task | Gateway | Orders Service | IdP / Platform |
| --- | --- | --- | --- |
| Receive client requests and select route | Yes | No | No |
| Verify token has valid signature, issuer, lifetime, audience | Should be at ingress | **Should independently verify** tokens intended for it | Issue tokens, publish metadata/JWKS |
| Block URL/method without granted scope | Can do early | Re-check per internal API | Issue scopes/claims per policy |
| Check owner of `O-200` | Usually lacks the required data source | **Yes, primary responsibility** | Does not know owners by default |
| Check tenant and business policy | Can check tenant at route level | **Must enforce tenant/resource access** | Provide tenant claim if policy requires |
| TLS for Gateway → upstream connection | Configure HttpClient HTTPS/mTLS | Prove TLS server identity; can verify client | PKI/cert management |
| Rate limiting, retry, circuit breaker | Can implement centrally | Self-protect resources and business consistency | Metrics/observability |
| Monitoring, audit | Log ingress-level decisions | Log/audit resource-level decisions | Centralize logs/traces per policy |

**Defense in depth** is not "repeating the same check for decoration." Each layer must be responsible for what it actually knows and can prove.

## 4. What Must Be Checked for a Valid JWT?

A JWT access token typically contains three Base64URL parts: `header.payload.signature`. The payload **is readable** when using standard signed JWS; **do not put secrets** into claims assuming the JWT is encrypted.

Example of *illustrative* claims, not a real token:

```json
{
  "iss": "https://idp.example.test/realms/lab",
  "sub": "user-a",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1920000000,
  "nbf": 1919990000
}
```

A JWT Resource Server must perform appropriate checks:

| Check | Purpose | If missing |
| --- | --- | --- |
| **Signature + valid algorithm** | Proves the token was signed by a trusted issuer and was not tampered with. | Clients can forge `sub`, `scope`, `tenant` claims. |
| **`iss`** | Token comes from the allowed issuing system. | Tokens from other issuers may be accepted. |
| **`aud`** | Token was issued for the right resource server/API. | Tokens meant for another app may be misused. |
| **`exp` and `nbf`** | Token is within its valid time window. | Expired or not-yet-valid tokens may be accepted. |
| **Scope/authority** | Checks which capabilities the caller is allowed to use. | Unauthorized methods may be permitted. |
| **Owner/tenant/policy** | Checks permission on the actual record. | Easy IDOR/BOLA vulnerability when changing the ID in the path. |

Spring Security Resource Server provides built-in mechanisms using issuer metadata and JWKS to verify JWT signatures, `iss`, and `exp`/`nbf`. **`aud` should be explicitly configured** for the API. When using bearer access tokens, Spring Security typically converts scopes in `scope` or `scp` into `GrantedAuthority` instances with the **`SCOPE_`** prefix. For example, `orders.read` becomes `SCOPE_orders.read`.

Never write code that merely decodes a JWT into JSON and reads `sub` or `scope` while skipping **signature verification**. Unverified claims are untrusted data.

### 401 and 403 Are Not the Same

- **401 Unauthorized:** missing authentication proof or invalid/expired/wrong-issuer/wrong-audience token. With bearer tokens, the response typically includes `WWW-Authenticate: Bearer` per standard and configuration.
- **403 Forbidden:** an authenticated identity exists, but **lacks permission** for the action/resource, such as missing `orders.read` or accessing an order that does not belong to it.
- **404 Not Found:** no route/handler/resource exists, or an intentional policy avoids disclosing resource existence. Do not assume every lack-of-permission case must return 404.

Actual status codes also depend on security rules evaluated **before** route mapping: a URL with no matching route that is blocked by a `denyAll` security rule can return **403** before ever getting a chance to return 404. When debugging, identify the response source via logs/traces.

## 5. Why Spring Security WebFlux Is Not Just a Regular GatewayFilter

Gateway Server WebFlux has at least two distinct filter mechanisms:

```text
WebFlux HTTP handling
  |
  +-- Spring Security WebFilter chain (SecurityWebFilterChain)
  |     - Authentication (JWT bearer token)
  |     - Authorization (URL + method + scope)
  |
  +-- RoutePredicateHandlerMapping
        - Path=/api/orders/**
        - Select Route
          |
          +-- FilteringWebHandler
                - GlobalFilter + route's GatewayFilter
                - StripPrefix, header transforms
                - LoadBalancer / routing / Netty HttpClient
```

- `SecurityWebFilterChain` is part of the **Spring WebFlux security pipeline**. It can block requests before they reach Gateway route filters.
- `GlobalFilter` belongs to the **Spring Cloud Gateway** pipeline after a route is selected; the word "global" does not make it a replacement for full WebFlux security.
- `GatewayFilter` or `GatewayFilterFactory` is attached to a specific route, typically for path/header transforms, rate limiters, retries, or circuit breakers.
- If you only add a manual filter checking `Authorization != null`, you have **not** verified the JWT or access rights.

In this lesson, **Spring Security** handles authentication and basic scope checks; Gateway route filters only transform requests and proxy. Orders Service also uses Spring Security to validate the token, then runs business checks.

## 6. Gateway Example: Checking JWT and Scope Right at the Entry Point

Suppose the Gateway application handles:

- `GET /public/status`: public, proxied to `/status` on Orders Service.
- `GET /api/orders/{orderId}`: requires a valid access token with scope `orders.read`, then proxies to `/orders/{orderId}`.

We **do not open POST/PUT/DELETE APIs** in the example so learners do not accidentally assume read scope also grants write permission.

### 6.1. Maven Dependencies

Use **JDK 17+, Maven**, Spring Boot `3.5.0`, and Spring Cloud `2025.0.0` *only to illustrate a compatible release train*. New projects should pick supported patch versions per the Spring Cloud compatibility matrix.

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>secured-gateway</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.cloud</groupId>
                <artifactId>spring-cloud-dependencies</artifactId>
                <version>2025.0.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-gateway-server-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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

The Resource Server starter brings in what is needed to verify JWTs (including Spring Security and JOSE/JWT support via managed dependencies). You **do not need** `spring-boot-starter-oauth2-client` just to validate a JWT bearer token sent by a client. OAuth2 client and `TokenRelay` serve a different scenario, explained in section 9.

### 6.2. Gateway Entry Point

Create `src/main/java/com/example/gateway/GatewayApplication.java`:

```java
package com.example.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
```

### 6.3. Configuring Issuer, Audience, and Routes

Create `src/main/resources/application.yml`:

```yaml
server:
  port: 8080

spring:
  application:
    name: secured-gateway

  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/lab
          audiences:
            - orders-api

  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: public-status
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/public/status
              filters:
                - StripPrefix=1

            - id: orders-api
              uri: http://127.0.0.1:9001
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
                - RemoveRequestHeader=X-User-Id
                - RemoveRequestHeader=X-Tenant-Id
```

This example uses a **hypothetical IdP**. `https://idp.example.test/realms/lab` **is only a placeholder**, not a real service. You must replace it with the exact `issuer-uri` of the IdP you manage and use a **real access token** with an appropriate `aud`. Do not generate fake-signed tokens or disable verification just to make a demo return 200.

Meaning of each part:

- `issuer-uri`: IdP metadata endpoint helping the Resource Server locate JWKS/signing keys; the token's issuer must match.
- `audiences: orders-api`: the access token must be intended for the API with audience `orders-api`. In the demo, both the Gateway and Orders Service intentionally use the same audience; when a system has multiple APIs with distinct audiences, a different strategy is needed.
- `Path=/api/orders/**`: route matching HTTP requests from clients.
- `StripPrefix=1`: `/api/orders/O-100` reaches the backend as `/orders/O-100`.
- `RemoveRequestHeader=X-User-Id`, `RemoveRequestHeader=X-Tenant-Id`: prevents forwarding **as-is** identity headers that a client could spoof. They do not replace the backend verifying the JWT and checking ownership.

> **Note on audience:** the example has only one business API and both layers validate tokens intended for `orders-api`. In a system with multiple backends that have separate audiences, **do not blindly accept every audience at the Gateway and forward the same token to every service**. Token audiences must be designed per resource server, and consider token exchange/delegation if the Gateway must exchange an incoming access token for a downstream token.

### 6.4. Creating SecurityWebFilterChain for the Gateway

Create `src/main/java/com/example/gateway/GatewaySecurityConfig.java`:

```java
package com.example.gateway;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class GatewaySecurityConfig {

    @Bean
    SecurityWebFilterChain gatewaySecurity(ServerHttpSecurity http) {
        return http
                // Only appropriate for stateless APIs using Authorization: Bearer.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/status")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults())
                )
                .build();
    }
}
```

Key points to understand:

1. `@EnableWebFluxSecurity` and the `SecurityWebFilterChain` bean register the policy at the **WebFlux layer**, not as a Gateway route filter.
2. `permitAll()` applies only to `GET /public/status`. It does not mean every `/public/**` request is public.
3. `hasAuthority("SCOPE_orders.read")` checks the authority converted from the JWT scope after token verification.
4. `anyExchange().denyAll()` enforces **fail closed**: paths or HTTP methods not explicitly permitted are denied. For example, order-write permissions are not granted.
5. `oauth2ResourceServer(...jwt(...))` enables bearer JWT verification.
6. `csrf(...disable)` is only appropriate for **stateless APIs relying solely on bearer tokens in the Authorization header**, without using cookies/sessions for authentication. If sessions, OAuth2 Login/BFF, or automatically sent cookies are used, proper CSRF protection must be designed; never copy the disable line mechanically.

**Limitation of Gateway rules:** they know the HTTP method, URL, and authorities; they do not read the database to know whether an order belongs to `user-a` or `user-b`. The backend must still perform the next step.

### 6.5. Should Every Route Check Specific Roles or Scopes?

As the API grows, you can differentiate:

```java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
.pathMatchers(HttpMethod.POST, "/api/orders/**")
    .hasAuthority("SCOPE_orders.write")
.anyExchange().denyAll()
```

This is an **authorization extension pattern**, not a drop-in replacement when the backend does not yet support `POST`. The Gateway should not assume write permissions just because a token has read permission or because the user is authenticated.

## 7. Orders Service Must Independently Check Resource Authorization

On the backend side, create **a separate Spring Boot application**, such as `orders-service`, listening on port `9001`. This is not the Gateway and does not need the Spring Cloud Gateway starter.

The service must:

- Verify the incoming JWT with the appropriate issuer/audience.
- Check the `orders.read` scope when calling `/orders/{id}`.
- Check the authenticated `sub` against the **owner of the record**.
- Never use client-sent `X-User-Id`, `X-Tenant-Id`, or `orderId` as proof of access rights.

### 7.1. Service Dependencies and Resource Server Configuration

In the Maven project (Spring Boot 3.5.x) of **Orders Service**:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
</dependencies>
```

This is the **dependencies section** of the backend `pom.xml`, not a standalone `pom.xml`. It assumes the backend project already has an appropriate Spring Boot parent/BOM and build plugin.

`src/main/resources/application.yml` of **Orders Service**:

```yaml
server:
  address: 127.0.0.1
  port: 9001

spring:
  application:
    name: orders-service
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/realms/lab
          audiences:
            - orders-api
```

The placeholder issuer must be replaced with a real IdP in both the Gateway and backend. The backend shares the same audience configuration as the Gateway in this **single-API demo**; in practice, plan separate token audiences for each resource server according to security policy.

**Note:** binding `127.0.0.1` is only suitable for two processes on the same machine. In containers/Kubernetes, configure the appropriate hostname and network policy, and **do not** expose Orders Service directly to the Internet. Network isolation adds defense, but does not replace token/permission verification inside the service.

### 7.2. Service-Side SecurityWebFilterChain

Create `src/main/java/com/example/orders/OrdersSecurityConfig.java`:

```java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OrdersSecurityConfig {

    @Bean
    SecurityWebFilterChain ordersSecurity(ServerHttpSecurity http) {
        return http
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/status")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults())
                )
                .build();
    }
}
```

Even when a request **does not go through the Gateway**, Orders Service still requires a valid token and the `orders.read` scope for `/orders/**`. That is a layer of defense reducing the impact of route misconfiguration, internal service calls, or a network path bypassing the Gateway.

`/status` is only a public endpoint for the demo. In production, health/Actuator endpoints must have their own environment-specific policies; allowing access to a status check endpoint does not mean exposing configuration details, metrics, or secrets.

### 7.3. Controller Checking Ownership

Mock data for illustration:

```text
Order O-100 -> owner user-a
Order O-200 -> owner user-b
```

Create `src/main/java/com/example/orders/OrdersController.java`:

```java
package com.example.orders;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    // Mock data, not a production order management system.
    private static final Map<String, String> ORDER_OWNERS = Map.of(
            "O-100", "user-a",
            "O-200", "user-b"
    );

    @GetMapping("/status")
    public Mono<Map<String, String>> status() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/orders/{id}")
    public Mono<ResponseEntity<Map<String, String>>> getOrder(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {

        return Mono.defer(() -> {
            String owner = ORDER_OWNERS.get(id);

            if (owner == null) {
                return Mono.just(ResponseEntity
                        .status(HttpStatus.NOT_FOUND)
                        .body(Map.of("error", "not_found")));
            }

            // jwt.getSubject() is the identity from the JWT verified
            // by Resource Server before the controller runs.
            if (!owner.equals(jwt.getSubject())) {
                return Mono.just(ResponseEntity
                        .status(HttpStatus.FORBIDDEN)
                        .body(Map.of("error", "not_allowed")));
            }

            return Mono.just(ResponseEntity.ok(
                    Map.of("orderId", id, "ownerId", owner)));
        });
    }
}
```

In the backend Spring Boot application, there must be a `@SpringBootApplication` entry point placed in `com.example.orders` or an appropriate parent package so component scanning finds the controller/security config.

**Why does the controller use `jwt.getSubject()`?** Because `Jwt` is created by Spring Security Resource Server from a **verified** token. It is completely different from:

```java
// UNSAFE if used for authorization:
String claimedUser = request.getHeaders().getFirst("X-User-Id");
```

A client can send `X-User-Id: user-b` to impersonate someone else. The demo code intentionally **ignores this header** and compares against the order's owner in the server-side data source.

In production:

- Read owner/tenant from a database or trusted domain service, not from a hardcoded map.
- Use queries constrained by **both resource and identity**, conceptually like `findByIdAndOwnerId(orderId, subject)`, if the data contract allows. This reduces unauthorized access risks and prevents leaking resource existence.
- For admin/delegate roles, define clear policies and auditing; do not automatically allow every user with `orders.read` scope to view all orders.
- Separate **authentication subject** and **authorization domain user ID** if the IdP uses a different ID from the internal ID. A reliable mapping is needed; do not assume every system has `sub = user-a`.
- Control tenant/owner within the same transaction or consistent process to reduce TOCTOU risks when permissions and resources change concurrently.

### 7.4. Using Method Security When Appropriate

With reactive Spring Security, you can enable `@EnableReactiveMethodSecurity` and use `@PreAuthorize` for conditions at the service method layer:

```java
@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfig {
}
```

Example of restricting a service method by scope:

```java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<OrderView> findOrder(String id) {
    // Owner/tenant checks must be enforced inside the business logic
    // or through a trusted policy bean.
    return orderRepository.findViewById(id);
}
```

This is an **illustrative snippet**, assuming `OrderView`, `orderRepository`, and the corresponding imports already exist. Simply adding a scope annotation **is not** enough to solve the `user-a` viewing `O-200` issue: resource-level permission logic must still be present.

For reactive methods, Spring Security uses Reactor Context to propagate the security context across the pipeline; do not place identity into a self-managed `ThreadLocal` and expect it to follow across async steps.

## 8. HTTP Flow from Client to Two Decision Layers

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Gateway Security
    participant R as Gateway Route/Proxy
    participant S as Orders Service Security
    participant O as Orders Domain/DB

    C->>G: GET /api/orders/O-200 + user-a's JWT
    G->>G: Verify signature, iss, aud, exp/nbf
    G->>G: Check SCOPE_orders.read
    alt Invalid token/scope
        G-->>C: 401 or 403
    else Allowed to call API
        G->>R: Allow route /api/orders/**
        R->>S: GET /orders/O-200 + bearer token
        S->>S: Independently verify token and SCOPE_orders.read
        alt Invalid backend token
            S-->>C: 401/403 via Gateway
        else Valid backend token
            S->>O: Read owner of O-200
            O-->>S: owner=user-b
            S->>S: user-a != user-b
            S-->>C: 403 Forbidden via Gateway
        end
    end
```

For `user-a`'s `GET /api/orders/O-100` (with a valid token and sufficient scope), both layers allow it and the controller returns `200 OK`.

**Do not conflate the two roles:** the Gateway can reject before HTTP proxying; Orders Service makes the specific owner/tenant decision. If downstream returns 403, the Gateway typically passes that status back to the client; a 403 does not necessarily originate at the Gateway.

## 9. How Does the Token Travel from the Gateway to the Service?

Choose the model based on client type and how tokens are issued:

### 9.1. Client Sends Bearer JWT; Gateway Is a Resource Server

This lesson's scenario:

```http
GET /api/orders/O-100 HTTP/1.1
Authorization: Bearer <access-token>
```

- The Gateway verifies the bearer JWT and requires the scope before proxying.
- For Orders Service to verify independently, the backend must **receive a bearer access token permitted for it** (or an equivalent properly designed downstream credential).
- With regular HTTP proxy routes, `Authorization` is a request header that can be forwarded if no security/filter/proxy component strips or replaces it. **You must actually test** the application's header-forwarding behavior rather than assuming every middleware preserves it in all cases.
- The backend continues verifying signature, issuer, audience, token expiration, and owner. **Having authenticated at the Gateway does not turn an arbitrary header into a trusted identity.**

If the backend requires a different audience than the incoming token, do not arbitrarily reuse a token with the wrong audience. Look into the appropriate IdP **token exchange / on-behalf-of** mechanism, or an approved service-to-service authentication architecture.

### 9.2. OAuth2 Login / BFF: TokenRelay

A Gateway acting as an **OAuth2 Client** (for instance, users log in via OAuth2 Login and the Gateway manages the authorized client) can use the **`TokenRelay`** filter to retrieve the appropriate access token and forward it downstream.

Route configuration pattern when OAuth2 client registration/authorized client is properly set up:

```yaml
filters:
  - TokenRelay=
```

**Mandatory requirements:**

1. Add the `spring-boot-starter-oauth2-client` dependency.
2. Configure `spring.security.oauth2.client.*` properly so `ReactiveClientRegistrationRepository` and authorized client infrastructure exist.
3. Ensure the relayed access token **has the appropriate audience/scopes** for downstream.
4. Design persistence for `ReactiveOAuth2AuthorizedClientService` suitable for production (the default may be in-memory).
5. **The backend still verifies the access token and resource permissions.**

Do not mistake `TokenRelay` as being "automatically enabled" just by adding Spring Security Resource Server JWT. An app that only receives and verifies bearer tokens does not necessarily need OAuth2 Client or TokenRelay; those are two related but distinct models.

### 9.3. Using Internal Identity Headers

Some systems pass `X-Authenticated-User` or `X-Tenant` downstream to the backend instead of forwarding the access token. This is only safe if a **strict trust boundary** has been designed:

- The Gateway strips any client-sent headers with the same name before emitting identity information itself.
- The service **only** accepts identity headers from a Gateway/service proxy authenticated via mTLS/service identity or a verifiable message-signing mechanism.
- Bypassing the Gateway via another network path is impossible; proper NetworkPolicy/egress/ingress rules are in place.
- Headers protect against spoofing, replay, and enforce audience/tenant checks per policy.
- The service still checks resource permissions even when it knows the identity.

If those guarantees are not in place, **prefer letting the service verify the token itself** rather than reading a plaintext header.

## 10. Hands-On Practice and Testing Against the Permission Matrix

The lesson uses a real IdP per the `issuer-uri` configuration and valid access tokens so it does not have to illustrate **self-signing fake JWTs**. When running on localhost:

1. Start **Orders Service** on `127.0.0.1:9001`.
2. Start **Gateway** on `127.0.0.1:8080`.
3. Provide a real JWT access token issued by the IdP, with the configured issuer, audience `orders-api`, scope `orders.read`, and subject matching the configured sample user.
4. Do not share real tokens in logs, screenshots, commit examples, or issue trackers.

> Because `https://idp.example.test/realms/lab` is a placeholder, token-based steps cannot succeed until replaced with a real IdP, configured JWKS, and a valid JWT. If your token has a `sub` other than `user-a`/`user-b`, update the mock owner data to match your test identity rather than editing claims manually.

### 10.1. Public Endpoint

```bash
curl -i http://127.0.0.1:8080/public/status
```

When Orders Service is running, the expected response body is:

```json
{"status":"ok"}
```

This endpoint is configured with `permitAll` in **both** security chains. Note: a request carrying a **malformed** bearer token may still be rejected by the authentication layer even on a public path; `permitAll` does not mean the system must ignore invalid credentials.

### 10.2. Missing Access Token

```bash
curl -i http://127.0.0.1:8080/api/orders/O-100
```

With the demo policy, the request lacks authentication credentials and is typically rejected by the Gateway with `401 Unauthorized`. **No HTTP proxy call is made to Orders Service** in this branch.

### 10.3. Valid Token Missing Scope

Use an access token with a valid issuer/audience but without `orders.read`. Send a similar request:

```bash
curl -i -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  http://127.0.0.1:8080/api/orders/O-100
```

The token authenticates, but scope is insufficient, so the Gateway typically returns **403 Forbidden**. Do not use `YOUR_ACCESS_TOKEN` as a literal token string; it is only a placeholder to replace with a properly issued bearer access token.

### 10.4. `user-a` Token with Read Scope Calling Their Own Order

If the access token contains `sub=user-a`, `aud=orders-api`, `scope=orders.read`, and is still valid:

```bash
curl -i -H "Authorization: Bearer YOUR_VALID_USER_A_TOKEN" \
  http://127.0.0.1:8080/api/orders/O-100
```

Once the backend receives and successfully verifies the token, the response will be:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"orderId":"O-100","ownerId":"user-a"}
```

### 10.5. Same Token Calling Someone Else's Order

```bash
curl -i -H "Authorization: Bearer YOUR_VALID_USER_A_TOKEN" \
  http://127.0.0.1:8080/api/orders/O-200
```

The Gateway **still allows the API call** because the token has read scope. Orders Service sees that `O-200` belongs to `user-b` and returns **403 Forbidden** per the example. This is the most important test in the lesson: **having a scope does not imply permission on every object**.

### 10.6. Spoofing Headers and Calling the Backend Directly

```bash
curl -i \
  -H "X-User-Id: user-b" \
  -H "X-Tenant-Id: privileged" \
  -H "Authorization: Bearer YOUR_VALID_USER_A_TOKEN" \
  http://127.0.0.1:8080/api/orders/O-200
```

The Gateway strips the two client-supplied headers; the backend only uses the identity from the verified JWT, so `user-a` is not allowed to read `user-b`'s order.

Try calling Orders Service **directly** in the demo environment:

```bash
curl -i http://127.0.0.1:9001/orders/O-100
```

Without a bearer token, Orders Service still returns **401** (per its security config). This proves the service does not rely **solely** on requests having passed through the Gateway. In production, network isolation is also needed; direct testing only demonstrates the service's own protection layer.

### 10.7. Expectation Table

| Request | Gateway | Orders Service | Expected Result |
| --- | --- | --- | --- |
| `GET /public/status`, no token | Allow | Allow | `200`, `{"status":"ok"}` |
| `GET /api/orders/O-100`, no token | Deny | Not called | `401` |
| Token with invalid signature/`iss`/`aud` or expired | Deny | Not called | Typically `401` |
| Valid token, missing `orders.read` | Deny | Not called | Typically `403` |
| `user-a` with scope, reading `O-100` | Allow | Owner matches | `200` |
| `user-a` with scope, reading `O-200` | Allow | Different owner | `403` from service |
| No token calling `:9001/orders/O-100` directly | Not involved | Deny | `401` |
| `POST /api/orders/O-100` | Not permitted | Not called | `403` via `denyAll` when security is authenticated |
| `GET /unknown` | Blocked by `denyAll` | Not called | May be `403`, not guaranteed `404` |

Do not assert only HTTP status: to distinguish where a 403 originated, combine backend request counters, route IDs, tracing, or auditing. **Do not log access tokens** as evidence.

## 11. Notable Production Considerations

### 11.1. IDOR/BOLA: Changing the ID in the Path Is Not Access Permission

**Broken Object Level Authorization** occurs when an application successfully authenticates the caller but forgets to check permissions on the requested object. Changing `/orders/O-100` to `/orders/O-200` must produce a result matching actual permissions, not merely the scope. Check owner/tenant at the query or domain layer and apply it across read, update, delete, export, and reporting operations.

### 11.2. Multiple Issuers, Multiple Audiences, and Multi-Tenant Authorization

If the Gateway serves Orders, Billing, and User Profile, each service may require a distinct audience. Do not configure "accept any token from the IdP" and treat every access token as having sufficient authority. You must check:

- Which `iss` is permitted per tenant or trust zone.
- Which `aud` targets which resource server.
- How scopes/roles are mapped; an IdP role does not automatically grant business permissions.
- Whether the tenant ID in the token matches the resource's tenant.
- When using client credentials (machine-to-machine), is there still a `sub` representing an end user? A dedicated policy is needed for service identities.

A resource server using **opaque tokens** can use introspection instead of JWT validation; that is a different model from the JWT example, yet still requires resource-level authorization checks.

### 11.3. Token Rotation, Expiry, and Revocation

JWTs typically carry an expiration and signature; Resource Server verifies public keys published via JWKS and time claims. An unexpired JWT **does not automatically know** that an account just had permissions revoked in the database or was immediately blocked. For rapid revocation requirements, consider short access token TTLs, introspection, denylists, or an appropriate policy mechanism.

If the IdP/JWKS is unreachable, there must be a key caching strategy, timeouts, and **fail-closed** error handling. Never fall back to "skipping signature verification" during network issues.

### 11.4. CSRF and CORS Are Not Authorization

- **CORS** is a browser rule for cross-origin requests; it does not stop `curl` or other clients from calling the API. Configure CORS with proper origins/methods/headers; handle `OPTIONS` preflight requests per security architecture, without expanding data-write permissions.
- **CSRF** matters when authentication uses cookies/sessions automatically sent by browsers. Only disable CSRF when the API is truly stateless and does not rely on cookies; using only bearer JWTs in the `Authorization` header is one such case.
- Do not treat a CORS allowlist as the list of users allowed to read orders.

### 11.5. Rate Limiting, Circuit Breakers, and Retries

The Gateway can **reject early** via Spring Security or a rate limiter before calling the backend. Circuit breakers and retries address availability, **not** replacing authorization verification:

- Identity-based rate limiters must extract the **authenticated** identity; never trust a self-supplied `X-User-Id`.
- Retries must not turn a `401`/`403` into an "opportunity" to retry with another identity, and must not blindly retry write operations.
- Fallbacks/circuit breakers must not return sensitive data when the primary service denied permission or the principal could not be determined.
- Service discovery/`lb://` only selects an instance; every service replica needs consistent JWT and owner/tenant policies.

### 11.6. TLS, Service-to-Service, and Header Trust

TLS between client–Gateway and Gateway–service consists of **two hops**. If the Gateway forwards bearer tokens to the service, protect the backend hop with HTTPS/mTLS per policy, verifying certificates and hostnames. Do not send access tokens to un-allowlisted backend URIs or invalid certificates. NetworkPolicy/firewalls/mTLS limit bypasses and service spoofing, but **do not eliminate business authorization checks**.

### 11.7. Observability and Auditing

Record **non-sensitive** fields: route ID, service ID, HTTP method, normalized path, `401`/`403` outcome, categorized reason (invalid_token/insufficient_scope/owner_mismatch), trace ID, latency, and where the decision was made. Do not log raw bearer tokens, cookies, signing keys, private claims, full queries containing PII, or sensitive order data. Service-level auditing can log principal ID and resource ID **per data protection policies**, though such data should be restricted in metric labels to avoid PII exposure and high cardinality.

## 12. Diagnosing Common Errors

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `401` despite `Authorization` header | Expired token, invalid signature, issuer, audience, `nbf`, or missing JWKS config. | Check Resource Server/IdP logs and validated claims; do not log the full token. |
| `403` at Gateway | Valid JWT but missing `SCOPE_orders.read`, or method/path hit `denyAll`. | Inspect HTTP method, matchers, authority mapping, and Gateway audit logs. |
| `403` from Orders Service | Owner/tenant mismatch, or service enforces stricter policy. | Check resource ID and permission data in the source of truth. |
| Same bearer token returns 401 at backend through Gateway | `Authorization` not forwarded; backend expects different audience; different issuer/JWKS; token invalid at backend. | Check header-forwarding policy, audience, and backend security configuration. |
| Direct backend access without token still reads orders | Service does not protect endpoints or matcher is wrong. | Add Resource Server + authorization on the service and test direct access. |
| `X-User-Id: admin` escalates privileges | Backend trusts client header instead of authenticated identity. | Strip untrusted headers, verify JWT, or establish a proven trust boundary. |
| Unrouted URL returns 403 instead of 404 | `denyAll` security rule rejects before route matching. | Distinguish security layer from route mapping; do not infer routing bugs from status alone. |
| `TokenRelay` has no effect | Missing OAuth2 client/registration config, no authorized client, or missing starter. | Check `ReactiveClientRegistrationRepository` and client security config. |
| `CSRF 403` on cookie/session requests | CSRF protection and session workflow misconfigured. | Distinguish cookie-based from stateless bearer; design CSRF properly. |
| Requests via `lb://` hit inconsistent replicas | Security config/issuer/audience/permissions differ across replicas. | Check deployment, config/secret rotation, and policy rollout. |
| Service returns 200 for another user's order | Only checking scope, forgetting owner/tenant. | Add resource authorization checks and cross-user tests. |
| 5xx during token verification | JWKS/IdP unreachable, TLS/certificate error, or app misconfiguration. | Verify issuer/JWKS connectivity, TLS trust, timeouts, and root-cause logs. |

## 13. Design and Testing Checklist

- [ ] IdP issues access tokens with appropriate issuer, audience, lifetime, and scopes.
- [ ] Gateway uses Spring Security WebFlux, **not** merely checking for `Authorization` header presence.
- [ ] APIs without explicit permissions are **deny by default**; GET/read and POST/write do not arbitrarily share scopes.
- [ ] Backend independently validates the access token or a verified identity under a strict trust model.
- [ ] Check owner/tenant against trusted data on **every** read/write/delete operation.
- [ ] Test missing/malformed/wrong-audience/wrong-issuer/expired tokens and insufficient scopes.
- [ ] Test **two users with the same scope** where only one owns the resource.
- [ ] Test direct calls to the service with no token, invalid token, and spoofed headers.
- [ ] Define a clear policy for TokenRelay/token exchange if using OAuth2 Client/BFF.
- [ ] Do not treat `lb://`, TLS, rate limiters, retries, or circuit breakers as substitutes for authorization.
- [ ] Disable CSRF only for truly stateless bearer APIs; CORS is not authorization.
- [ ] Never put tokens/PII into unprotected logs, metrics, or trace attributes.

### Self-Check Questions

**1. Why can a valid JWT with `orders.read` still receive a 403 when reading a specific order?**

Because scopes typically grant permission to **perform an operation type**; permission on a specific order also depends on owner, tenant, and business state inside Orders Service.

**2. If JWT verification is already done at the Gateway, can Spring Security be omitted from Orders Service?**

Not in a defense-in-depth architecture. The service may be called via another path or receive a request from another internal component; the backend must be able to verify permissions and trusted identity under the designed model.

**3. Can a `GlobalFilter` in the Gateway replace Spring Security's `SecurityWebFilterChain`?**

No. They belong to two different pipelines; manually checking headers in a filter does not perform full standard authentication/authorization.

**4. How are `401` and `403` used differently?**

`401` usually indicates missing/invalid authentication; `403` means authenticated but lacking permission. A `403` can originate from either the Gateway or the service.

**5. Do a JWT's `sub` and a request's `X-User-Id` carry the same level of trust?**

No. `sub` is only trustworthy once the token is fully verified; `X-User-Id` sent by the client can be spoofed.

**6. Does `TokenRelay` cause Orders Service to automatically check owner and audience?**

No. TokenRelay only forwards the appropriate credential downstream; the backend must validate the token and enforce its own policy.

**7. Why can a stateless bearer-token-only API disable CSRF, whereas an app using session cookies should not copy that configuration?**

Because cookie/session authentication is automatically sent by browsers, changing the CSRF threat model. Decisions must be based on how credentials are stored and sent, not on the name "Gateway".

**8. If a service supports `lb://` with multiple instances, is access control guaranteed automatically?**

No. LoadBalancer only selects an instance; every replica must have the same authentication, authorization, and owner/tenant checks properly configured.

## Conclusion

**The Gateway authenticates early to filter out invalid requests, while the service must decide permissions on the resources it owns.** In Spring Cloud Gateway Server WebFlux, Spring Security `SecurityWebFilterChain` can verify bearer JWTs, issuer, audience, and scopes **before** the Gateway proxies; Orders Service must independently verify tokens intended for it, then check owner/tenant on business data. When these layers work alongside TLS/mTLS, rate limiting, discovery, circuit breakers, retries, and controlled observability, the system protects both the ingress **and** internal call paths.

### Official References

- [Spring Cloud Gateway — Spring Security Integration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/spring-security.html)
- [Spring Cloud Gateway Server WebFlux 4.3 — TokenRelay GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html)
- [Spring Cloud Gateway Server WebFlux 4.3 — How It Works](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/how-it-works.html)
- [Spring Security 6.5 — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Reactive Method Security](https://docs.spring.io/spring-security/reference/6.5/reactive/authorization/method.html)
- [Spring Boot — OAuth2 Resource Server properties and audiences](https://docs.spring.io/spring-boot/reference/security/oauth2.html)
- [Spring Cloud — Release Train Compatibility Matrix with Spring Boot](https://spring.io/projects/spring-cloud/)
