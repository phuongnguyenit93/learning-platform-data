# Separating Security Responsibilities at the API Gateway and Downstream Services

## 1. Problem and Objectives

In a Spring WebFlux architecture with an API Gateway, multiple microservices, and multiple tenants, a very common mistake is assuming: **"Because the Gateway has already authenticated the JWT, downstream services can trust every request."** This assumption easily leads to bypasses, header spoofing, token substitution, and cross-tenant data access.

For example, a user holds a valid access token with `tenant=acme` and scope `orders.read`. They send:

```http
GET /edge/orders/globex/records/r9 HTTP/1.1
Host: api.example.invalid
Authorization: Bearer <access-token>
X-Tenant: globex
X-User: admin
```

The Gateway can verify the token and the `orders.read` scope; however, whether the caller has permission to read record `r9` of tenant `globex` is a decision **owned by the Orders Service**, which manages tenant, owner, and database ACL information. The backend cannot simply trust `X-Tenant` or `X-User` supplied by the caller.

**Topic:** Separating Security Responsibilities at the API Gateway and Downstream Services.  
**Parent Chapter:** Gateway and Multi-tenancy.  
**Module:** Spring Security - reactive.  
**Illustrative Stack:** Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, Spring Cloud Gateway Server WebFlux 4.3.x (Spring Cloud 2025.0.x).

### After this lesson, you will be able to

1. Separate authentication, coarse-grained authorization, and fine-grained/resource authorization.
2. Explain why token verification at the Gateway **does not replace** backend resource self-protection, even when network ACLs or mTLS are present.
3. Prevent header spoofing (`X-User`, `X-Tenant`, `X-Roles`) and gateway bypasses.
4. Bind a JWT to a trusted issuer, expiry, audience, scope, tenant, and owner/record ACL.
5. Understand `TokenRelay` when the Gateway acts as an OAuth2 Client and why a token issued for the Gateway cannot automatically be used downstream.
6. Resolve the tenant/issuer from a verified source rather than relying on raw `Host`/`X-Forwarded-*`/query parameters.
7. Design route allowlists, StripPrefix, forwarded header trust, and the Gateway → backend connection path.
8. Build two standalone reactive Java 17+ applications: Gateway and Orders Service.
9. Write `WebTestClient` integration tests against invalid JWTs, missing scopes, forged headers, cross-tenant requests, and IDOR/BOLA.
10. Evaluate the limitations of fake JWT decoder tests, and plan tests for real JWT cryptographic signatures/JWKS.

## 2. Two Distinct Trust Boundaries

```text
External client / mobile / browser
            |
         HTTPS/TLS
            |
    [API GATEWAY - EDGE]
    - verify caller's token
    - block routes outside allowlist
    - coarse-grained scope/role check
    - rate limit, request size, WAF
    - strip untrusted identity headers
    - route to trusted destination
            |
        internal TLS/mTLS
            |
    [ORDERS SERVICE - RESOURCE]
    - verify JWT independently
    - issuer, signature, aud, exp, nbf
    - scope orders.read
    - tenant claim == requested tenant
    - record owner / role / ACL
            |
       Tenant-aware database
```

**The Gateway owns ingress and routing control; the downstream service owns data and business authorization control.**

| Concern | Gateway | Orders Service |
|---|---|---|
| TLS and ingress endpoint | Primary | Internal TLS/mTLS where appropriate |
| Coarse rate limits / WAF / size limits | Primary | Service-specific business quotas |
| Caller Bearer authentication | Should verify | Must re-verify if accepting Bearer as a trust boundary |
| Orders token audience | Checked per route | Checks `aud=orders-api` |
| `orders.read` scope | Early check | Re-checks upon entering endpoint |
| Tenant in path | Routing hint | Verified against trusted claim |
| Record owner / ACL | Insufficient data | Mandatory |
| Forged `X-User`/`X-Roles` | Stripped | Never used as principal |
| TokenRelay / token exchange | May handle | Verifies received token |
| Direct backend bypass | Network ACL and topology | Still requires authentication/authorization |
| DB row-level isolation | Cannot enforce | Service/repository/DB |
| Audit | Route, status, rate | Principal, tenant, record access decision |
| CORS / CSRF | Depends on browser/session flow | Do not disable local protections if using session/cookie |

### 2.1. Authentication is not automatically authorization

Authentication checks who the caller is and whether the credential/token is valid. Authorization checks whether that caller has permission to perform **a specific operation**.

A token with `scope=orders.read` grants an operation-level permission; it does not prove that the caller may read all orders across all tenants. Therefore, a request may pass the Gateway yet be rejected by the backend with **403 Forbidden** due to a tenant or owner mismatch.

### 2.2. Zero trust does not mean "unbounded trust after one check"

In a zero-trust architecture, permissions are not granted merely because a request originates from a private subnet. Identities, permissions, and boundaries are evaluated at every hop. The backend may accept the user's own JWT access token or a **signed internal assertion** issued by the Gateway with a strict audience/TTL/service identity, but it must **verify** that source of truth. A plaintext `X-Authenticated-User` header is insufficient.

Double JWT verification at both the Gateway and the backend costs some CPU, but provides isolated trust boundaries. If you choose an alternative based on mTLS + signed gateway assertions, you must establish a clear protocol, threat model, and service ingress controls, and the backend must still enforce record ACLs.

## 3. Deployment Patterns to Distinguish

### 3.1. Gateway receives a JWT Bearer token and proxies the same token

```text
Client --Authorization: Bearer T--> Gateway
Gateway --Authorization: Bearer T--> Orders Service
Orders Service --verify T independently--> Record ACL
```

In this example, token `T` is intended for `aud=orders-api`. The Gateway acts as a pre-check layer before the Orders route and can verify the token against this audience; the backend also verifies the token intended for itself.

This is **not the TokenRelay GatewayFilter**: the inbound request already carries an Authorization Bearer header. The Gateway does not need to act as an OAuth2 login client to obtain a new access token. The route is allowed to forward Authorization downstream; the backend re-verifies the token and does not trust it merely because the Gateway forwarded it.

Verify the behavior of your actual proxy/filters/version using integration tests. Never assume every proxy preserves Authorization across all configurations.

### 3.2. Gateway acts as an OAuth2 Login Client for the browser

```text
Browser --session cookie--> Gateway (oauth2Login)
Gateway --access token via TokenRelay--> downstream
Downstream --verify token and ACL--> data
```

Spring Cloud Gateway Server WebFlux provides a `TokenRelay` filter, commonly used with an OAuth2 client registration. Example snippet:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-login
              uri: https://orders.internal.example.invalid
              predicates:
                - Path=/edge/orders/**
              filters:
                - StripPrefix=1
                - TokenRelay=
```

When the Gateway acts as an OAuth2 Client, `TokenRelay` can retrieve the user's current access token (or the token of a specified `clientRegistrationId`) and attach it to the outbound request. It requires `spring-boot-starter-oauth2-client` and a proper `ReactiveClientRegistrationRepository`. The default authorized-client service may use in-memory storage; multiple replicas require appropriate storage and refresh behavior.

**Do not confuse:**
- An ID token attests user authentication to the OIDC Client; it is **not** an access token to send to downstream APIs.
- A browser session cookie is not a Bearer token with the Orders audience.
- TokenRelay **does not automatically transform the audience**. If the access token only has `aud=gateway` while Orders requires `aud=orders-api`, use token exchange or request a token for the target resource; **do not** remove the backend's audience check.
- Only relay tokens to **trusted route destinations**, never to caller-supplied URLs.

### 3.3. Gateway sends a signed internal assertion instead of the original token

Another option is for the Gateway to validate the external token, then mint a short-lived **signed assertion** for downstream with `iss=gateway-internal`, `aud=orders-api`, tenant/sub, and TTL, combined with mTLS. The backend must verify the signature, audience, expiry, trusted gateway identity, and replay protection per contract, then apply ACLs. Without signatures/mTLS and ingress restrictions, a plaintext custom `X-User` header is vulnerable to spoofing.

## 4. Attacks Caused by Misallocated Responsibilities

### 4.1. Disabling backend security because "the Gateway already did it"

A developer configures `permitAll()` for `/orders/**` downstream. Under normal conditions this may appear safe, but an attacker can call the service directly due to:
- A compromised internal pod/workload.
- The backend being accidentally exposed via a load balancer/Ingress.
- A new route configuration bypassing the Gateway.
- Mesh/proxy route drift.
- An internal service sending a request without going through edge authn.

**Defense:** the backend remains a Resource Server with route authorization and tenant checks; network policies block direct public ingress, with mTLS where appropriate. Test that a direct backend request without a token returns 401.

### 4.2. Identity header spoofing

Headers such as `X-Tenant: acme`, `X-User: admin`, `X-Roles: ROLE_ADMIN` sent by the client **must never be used to construct an Authentication**. The Gateway must strip untrusted identity headers at ingress/route; the backend should ideally extract the principal from a JWT/verified assertion rather than reading those headers to grant permissions.

If the product needs to pass internal identity metadata, you must guarantee that the header is generated by a trusted proxy after stripping external headers, over an authenticated channel, with protective policies. Malformed or duplicate headers can cause parser discrepancies across layers; test duplicates, case-insensitivity, and forwarding normalization.

### 4.3. Tenant mismatch and IDOR/BOLA

A client token is signed for `tenant=acme` and has `SCOPE_orders.read`. Request:

```http
GET /edge/orders/globex/records/r9
Authorization: Bearer <token-acme>
```

The Gateway checks the scope and proxies the request, but the backend must compare the **verified token's** tenant against the tenant in the path/resource. Mismatch → reject. Even within tenant acme, Bob's record r2 must not be readable by user Alice when owner/ACL rules do not permit it.

```text
token.scope contains orders.read
AND token.tenant == requestedTenant
AND record.tenant == token.tenant
AND record.owner / ACL permits token.sub
```

Never query the database by a global `recordId` while forgetting the tenant predicate. For updates/deletes, enforce tenant/owner within the same transaction and repository filter to prevent TOCTOU.

### 4.4. Token substitution and audience

An active token from the right AS could be issued for `aud=payments-api`. If the Orders Service only verifies the signature and skips the audience check, it may accept a token not meant for Orders (**confused deputy**). You must verify `iss`, `exp`, `nbf`, signature or introspection, audience, scopes, and the service's own authorization policy.

Spring Boot 3.5 supports `spring.security.oauth2.resourceserver.jwt.audiences` on both Reactive and Servlet stacks; use the audience property or an equivalent validator.

### 4.5. Route confusion / SSRF

Never let the caller choose an arbitrary upstream destination:

```text
GET /edge/proxy?url=http://169.254.169.254/metadata
```

Routes must come from trusted server config/service registry. Never write `uri(request.getQueryParams().getFirst("url"))`. Validate trusted schemes, hosts/ports, redirects, and egress IP/DNS policies if dynamic destinations are ever required. Path rewrites must not produce a new authority from encoded/untrusted input.

### 4.6. Forwarded headers and tenant resolution

`Host`, `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Forwarded-Host` can be forged by a client. Spring Cloud Gateway 2025.0/4.3 provides the `spring.cloud.gateway.server.webflux.trusted-proxies` property for forwarded-header trust configuration.

Trust only actual proxies in the ingress topology; never set a `.*` wildcard regex on public input. If the tenant is selected from the hostname, verify a trusted domain/tenant mapping and still check the token tenant downstream. Any dynamic issuer/JWKS routing decision based on an unverified JWT `iss` must also **allowlist trusted issuers** to avoid SSRF.

## 5. Distinguishing HTTP 401, 403, and 404 Outcomes

| Case | Gateway | Backend | Outcome |
|---|---|---|---|
| Missing Bearer | Does not proxy | Never receives | 401 at Gateway |
| Malformed token / bad signature | Does not proxy | Never receives | 401 |
| Valid token, missing coarse scope | Does not proxy | Never receives | 403 |
| Valid token, sufficient scope | Proxies | Revalidates issuer/aud/scope/tenant/ACL | 200/403/404 |
| Token for tenant acme requesting globex | May proxy | Tenant mismatch → reject | 403 |
| Token acme/alice reading Bob's r2 | May proxy | Owner ACL → reject | 403 |
| Direct backend call without Bearer | Bypassed | Backend rejects | 401 |
| Unlisted path | No route / deny | Never receives | 403/404 per config |
| Token for payments-api | Rejects if aud checked | If reached, Orders rejects | 401 |
| AS/JWKS unavailable and token unverified | Fail closed | Fail closed | No protected success |

**401** indicates missing/invalid authentication; **403** indicates an authenticated principal lacking permission. Some businesses choose to return 404 when a record does not exist or is hidden to reduce enumeration; that is a separate policy and never an excuse to omit ACLs.

## 6. Architecture Using Spring Cloud Gateway Server WebFlux

Example running two Spring Boot applications:

```text
workspace/
  edge-gateway/                      port 9000
    src/main/java/demo/edge/
      EdgeApplication.java
      EdgeSecurity.java
      EdgeHealthController.java
    src/main/resources/application.yml
    src/test/java/demo/edge/
      EdgeBoundaryTests.java

  orders-service/                    port 9001
    src/main/java/demo/orders/
      OrdersApplication.java
      OrdersSecurity.java
      OrderAccess.java
      OrdersController.java
    src/main/resources/application.yml
    src/test/java/demo/orders/
      OrdersBoundaryTests.java
```

Use **two projects from Spring Initializr**, each with its own Gradle wrapper/build plugins/repositories/Java toolchain. The example uses Spring Boot 3.5.x and Spring Cloud 2025.0.x for Java 17+, Security 6.5.x/Gateway 4.3.x. **Spring Cloud 2025.0.3 is a release for Boot 3.5.x, though this line reached end of OSS support in mid-2026; production deployments must choose a vendor-supported baseline with appropriate security patches.** The demo versions illustrate the module's APIs and are not a recommendation to run an unsupported platform in new deployments.

### 6.1. edge-gateway Dependencies

In the Initializr-generated project, use the following `build.gradle` snippet:

```groovy
dependencyManagement {
    imports {
        mavenBom 'org.springframework.cloud:spring-cloud-dependencies:2025.0.3'
    }
}
dependencies {
    implementation 'org.springframework.cloud:spring-cloud-starter-gateway-server-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Keep the `org.springframework.boot` and `io.spring.dependency-management` plugins from Initializr; the block above is **not** a complete standalone build.gradle. Use the newer `spring-cloud-starter-gateway-server-webflux` artifact instead of the deprecated legacy starter name. Gateway Server WebFlux requires a Netty/WebFlux runtime, not Servlet MVC.

### 6.2. orders-service Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Do not add `spring-boot-starter-web`: in Boot 3.x when both MVC and WebFlux are present, Servlet MVC is typically chosen as the inbound stack.

## 7. Gateway Java 17+ Code

### 7.1. EdgeApplication.java

```java
package demo.edge;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class EdgeApplication {
    public static void main(String[] args) {
        SpringApplication.run(EdgeApplication.class, args);
    }
}
```

### 7.2. EdgeSecurity.java

```java
package demo.edge;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class EdgeSecurity {

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/edge/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/edge/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Explanation:

- The Gateway independently verifies inbound JWTs via `oauth2ResourceServer().jwt()`.
- `/edge/orders/**` only allows GET requests with `SCOPE_orders.read`. This is a **coarse** check, not a record-owner check.
- Other URLs are denied; avoid `permitAll()` across the entire gateway.
- Do not enable HTTP Basic or form login on a bearer-only API.
- Do not unconditionally disable CSRF; the demo only exposes GET. When browser sessions/cookies and unsafe methods are present, design CSRF according to your threat model.

### 7.3. EdgeHealthController.java

```java
package demo.edge;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class EdgeHealthController {

    @GetMapping("/edge/health")
    public Mono<String> health() {
        return Mono.just("edge-ok");
    }
}
```

### 7.4. edge-gateway application.yml

```yaml
server:
  port: 9000

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.invalid/
          audiences:
            - orders-api
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders
              uri: ${ORDERS_SERVICE_URL:http://127.0.0.1:9001}
              predicates:
                - Path=/edge/orders/**
              filters:
                - StripPrefix=1
                - RemoveRequestHeader=X-User
                - RemoveRequestHeader=X-Tenant
                - RemoveRequestHeader=X-Roles
                - RemoveRequestHeader=X-Authenticated-User
                - RemoveRequestHeader=X-Forwarded-User
```

This configuration uses the **`spring.cloud.gateway.server.webflux.routes`** prefix for Spring Cloud Gateway 4.3/Cloud 2025.0. Legacy examples using `spring.cloud.gateway.routes` may be deprecated or fail to work properly in this version.

`StripPrefix=1`: `/edge/orders/acme/records/r1` → `/orders/acme/records/r1`. The upstream points to `http://127.0.0.1:9001` for **local demo** purposes; production must use a trusted service URL over HTTPS/mTLS/private network.

The `RemoveRequestHeader` filters strip identity headers sent by the client. The demo backend **never trusts** them under any circumstances, including direct requests. Do not remove `Authorization` because the Orders Service needs the access token to verify it independently. `issuer.example.invalid` is a placeholder domain; there is no real Authorization Server.

`ORDERS_SERVICE_URL` must be set via trusted configuration; never turn it into a URL taken from a caller's query parameter or header.

## 8. Backend Java 17+ Code

### 8.1. OrdersApplication.java

```java
package demo.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

### 8.2. orders-service application.yml

```yaml
server:
  port: 9001

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.invalid/
          audiences:
            - orders-api
```

**Audience matters:** Orders Service accepts only tokens intended for `orders-api`. The Gateway in the demo validates the same token matching the Orders route, and the backend validates it again. If in a real architecture the Gateway has a different audience, use a dedicated access token for Orders or token exchange; never ask the backend to drop audience validation.

### 8.3. OrdersSecurity.java

```java
package demo.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OrdersSecurity {

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/health")
                    .permitAll()
                .pathMatchers(HttpMethod.GET, "/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Even with a Gateway in front, Orders Service is an **independent Resource Server**: it verifies the token, checks scopes, and proceeds to local ACLs. A direct request to the backend without a token must return 401.

### 8.4. OrderAccess.java — Service-Level Tenant and Owner Checks

```java
package demo.orders;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@Service
public class OrderAccess {

    private static final Map<String, Map<String, String>> OWNERS =
        Map.of(
            "acme", Map.of("r1", "alice", "r2", "bob"),
            "globex", Map.of("r9", "alice"));

    public record OrderView(
            String tenant, String recordId,
            String owner, String summary) {
    }

    public Mono<OrderView> read(
            String tenant, String recordId, Jwt jwt) {

        String tokenTenant = jwt.getClaimAsString("tenant");
        String subject = jwt.getSubject();

        if (tokenTenant == null
                || !tokenTenant.equals(tenant)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Tenant is not permitted"));
        }

        Map<String, String> tenantRecords = OWNERS.get(tenant);
        if (tenantRecords == null
                || !tenantRecords.containsKey(recordId)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Record not found"));
        }

        String owner = tenantRecords.get(recordId);
        if (!owner.equals(subject)) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Record access denied"));
        }

        return Mono.just(new OrderView(
            tenant, recordId, owner,
            "Illustrative protected order"));
    }
}
```

Three distinct checks:

1. `tokenTenant` is read from the **JWT verified by Spring Security**, never from the `X-Tenant` header.
2. Repository lookup occurs only within the requested tenant; the demo uses a Map, while production must include a tenant predicate in the DB query.
3. The record's owner must match `Jwt.sub` or an ACL/role permitted by business policy.

Thus, user acme/alice cannot read globex/r9 or Bob's acme/r2, even with the `orders.read` scope.

**Not every OAuth2 access token carries a tenant claim**; that is an application-specific contract that must be issued by a trusted AS. If tenant memberships are complex, the backend should query a membership DB/authorization service and enforce policy rather than blindly trusting an overly broad claim. When tokens/roles are revoked, consider TTL and membership revocation.

### 8.5. OrdersController.java

```java
package demo.orders;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrdersController {

    private final OrderAccess access;

    public OrdersController(OrderAccess access) {
        this.access = access;
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("orders-ok");
    }

    @GetMapping("/orders/{tenant}/records/{recordId}")
    public Mono<OrderAccess.OrderView> read(
            @PathVariable String tenant,
            @PathVariable String recordId,
            @AuthenticationPrincipal Jwt jwt) {
        return access.read(tenant, recordId, jwt);
    }
}
```

This is a WebFlux controller returning `Mono`; `Jwt` is injected from the verified resource-server authentication. Never read the principal from `request.getHeaders().getFirst("X-User")` and never call `.block()`.

In a real application, protect read/write/aggregate endpoints, enforce field-level permissions and database isolation, and prevent cross-tenant data leakage via cache keys, metrics, or logs.

## 9. Running the Applications Locally

Create two separate Gradle projects as shown in Section 6. In terminal 1, start Orders Service:

```bash
./gradlew bootRun
```

In terminal 2, start Gateway:

```bash
./gradlew bootRun
```

On Windows PowerShell in each project:

```powershell
.\gradlew.bat bootRun
```

Verify:

```bash
curl -i http://127.0.0.1:9000/edge/health
curl -i http://127.0.0.1:9001/health
curl -i http://127.0.0.1:9000/edge/orders/acme/records/r1
curl -i http://127.0.0.1:9001/orders/acme/records/r1
```

Expect HTTP 200 for health with bodies `edge-ok` and `orders-ok` respectively. Both protected GET requests without a Bearer token must return 401. There is no real JWT to log in successfully: the `example.invalid` issuer is a non-functional placeholder; therefore, only tests using a fake JwtDecoder verify the policy logic offline.

## 10. Testing the Gateway with WebTestClient and a Local Netty Stub

File `edge-gateway/src/test/java/demo/edge/EdgeBoundaryTests.java`:

```java
package demo.edge;

import java.time.Instant;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("test")
@Import(EdgeBoundaryTests.FakeDecoder.class)
class EdgeBoundaryTests {

    static final AtomicInteger PROXIED = new AtomicInteger();
    static final AtomicReference<String> PATH =
        new AtomicReference<>();
    static final AtomicReference<String> USER =
        new AtomicReference<>();
    static final AtomicReference<String> TENANT =
        new AtomicReference<>();
    static final AtomicReference<String> ROLES =
        new AtomicReference<>();
    static final AtomicReference<String> AUTH =
        new AtomicReference<>();

    static final DisposableServer UPSTREAM = HttpServer.create()
        .host("127.0.0.1").port(0)
        .handle((request, response) -> {
            PROXIED.incrementAndGet();
            PATH.set(request.uri());
            USER.set(request.requestHeaders().get("X-User"));
            TENANT.set(request.requestHeaders().get("X-Tenant"));
            ROLES.set(request.requestHeaders().get("X-Roles"));
            AUTH.set(request.requestHeaders()
                .get(HttpHeaders.AUTHORIZATION));
            return response.status(200)
                .sendString(Mono.just("stub-orders-ok"));
        }).bindNow();

    @DynamicPropertySource
    static void upstream(DynamicPropertyRegistry registry) {
        registry.add("ORDERS_SERVICE_URL",
            () -> "http://127.0.0.1:" + UPSTREAM.port());
    }

    @AfterAll
    static void stop() {
        UPSTREAM.disposeNow();
    }

    @TestConfiguration
    static class FakeDecoder {
        @Bean
        ReactiveJwtDecoder jwtDecoder() {
            return token -> {
                if ("edge-read".equals(token)) {
                    return Mono.just(jwt(token, "orders.read"));
                }
                if ("edge-no-scope".equals(token)) {
                    return Mono.just(jwt(token, "profile"));
                }
                return Mono.error(new BadJwtException(
                    "Not a trusted test JWT"));
            };
        }

        static Jwt jwt(String value, String scope) {
            Instant now = Instant.now();
            return Jwt.withTokenValue(value)
                .header("alg", "RS256")
                .claim("iss", "https://issuer.example.invalid/")
                .claim("aud", List.of("orders-api"))
                .claim("sub", "alice")
                .claim("tenant", "acme")
                .claim("scope", scope)
                .issuedAt(now.minusSeconds(60))
                .expiresAt(now.plusSeconds(600))
                .build();
        }
    }

    @Autowired
    WebTestClient client;

    @Test
    void healthIsPublic() {
        client.get().uri("/edge/health")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("edge-ok");
    }

    @Test
    void missingBearerRejectedBeforeProxy() {
        int before = PROXIED.get();
        client.get().uri("/edge/orders/acme/records/r1")
            .exchange().expectStatus().isUnauthorized();
        assertEquals(before, PROXIED.get());
    }

    @Test
    void invalidBearerRejectedBeforeProxy() {
        int before = PROXIED.get();
        client.get().uri("/edge/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("invalid"))
            .exchange().expectStatus().isUnauthorized();
        assertEquals(before, PROXIED.get());
    }

    @Test
    void missingScopeRejectedAtGateway() {
        int before = PROXIED.get();
        client.get().uri("/edge/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("edge-no-scope"))
            .exchange().expectStatus().isForbidden();
        assertEquals(before, PROXIED.get());
    }

    @Test
    void routingSanitizesIdentityHeaders() {
        client.get().uri("/edge/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("edge-read"))
            .header("X-User", "attacker")
            .header("X-Tenant", "globex")
            .header("X-Roles", "ROLE_ADMIN")
            .header("X-Authenticated-User", "attacker")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("stub-orders-ok");

        assertEquals("/orders/acme/records/r1", PATH.get());
        assertNull(USER.get());
        assertNull(TENANT.get());
        assertNull(ROLES.get());
        assertEquals("Bearer edge-read", AUTH.get());
    }

    @Test
    void unknownEdgePathIsDenied() {
        int before = PROXIED.get();
        client.get().uri("/edge/private")
            .headers(h -> h.setBearerAuth("edge-read"))
            .exchange().expectStatus().isForbidden();
        assertEquals(before, PROXIED.get());
    }
}
```

**6 tests**: public health, missing token, invalid token, missing scope, strip headers + path rewrite + Authorization pass-through, unlisted route. The Gateway test uses a Netty stub on a dynamic loopback port, so it **does not call the real backend** and requires no IdP. The stub accepts the fake Bearer `edge-read` to verify forwarding; never use this test pattern to capture/print production secrets.

**Limitation:** FakeDecoder constructs `Jwt` directly without a real signature, so the tests do not verify key/issuer/aud signatures. Production uses the Spring Boot JWT decoder backed by a trusted AS/JWKS and the audience property. These HTTP tests verify Gateway routing/edge rules/header stripping.

## 11. Testing the Backend Independently of the Gateway

File `orders-service/src/test/java/demo/orders/OrdersBoundaryTests.java`:

```java
package demo.orders;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

@SpringBootTest(webEnvironment =
    SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
@ActiveProfiles("test")
@Import(OrdersBoundaryTests.FakeDecoder.class)
class OrdersBoundaryTests {

    @Autowired
    WebTestClient client;

    @TestConfiguration
    static class FakeDecoder {
        static final String ISS =
            "https://issuer.example.invalid/";

        @Bean
        ReactiveJwtDecoder jwtDecoder() {
            return token -> {
                Jwt jwt = switch (token) {
                    case "acme-alice-read" -> jwt(
                        token, ISS, "orders-api",
                        "acme", "alice", "orders.read");
                    case "acme-bob-read" -> jwt(
                        token, ISS, "orders-api",
                        "acme", "bob", "orders.read");
                    case "globex-alice-read" -> jwt(
                        token, ISS, "orders-api",
                        "globex", "alice", "orders.read");
                    case "acme-no-scope" -> jwt(
                        token, ISS, "orders-api",
                        "acme", "alice", "profile");
                    case "bad-audience" -> jwt(
                        token, ISS, "payments-api",
                        "acme", "alice", "orders.read");
                    case "bad-issuer" -> jwt(
                        token, "https://untrusted.example.invalid/",
                        "orders-api", "acme", "alice", "orders.read");
                    default -> null;
                };

                if (jwt == null
                        || !ISS.equals(jwt.getClaimAsString("iss"))
                        || !jwt.getAudience().contains("orders-api")
                        || jwt.getExpiresAt() == null
                        || !jwt.getExpiresAt().isAfter(
                            Instant.now())) {
                    return Mono.error(new BadJwtException(
                        "Invalid test JWT"));
                }
                return Mono.just(jwt);
            };
        }

        static Jwt jwt(
                String value, String issuer, String audience,
                String tenant, String subject, String scope) {
            Instant now = Instant.now();
            return Jwt.withTokenValue(value)
                .header("alg", "RS256")
                .claim("iss", issuer)
                .claim("aud", List.of(audience))
                .claim("sub", subject)
                .claim("tenant", tenant)
                .claim("scope", scope)
                .issuedAt(now.minusSeconds(60))
                .expiresAt(now.plusSeconds(600))
                .build();
        }
    }

    @Test
    void healthPublic() {
        client.get().uri("/health")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("orders-ok");
    }

    @Test
    void directWithoutJwtIsUnauthorized() {
        client.get().uri("/orders/acme/records/r1")
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void invalidJwtIsUnauthorized() {
        client.get().uri("/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("unknown"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void ownRecordIsReadable() {
        client.get().uri("/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("acme-alice-read"))
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.tenant").isEqualTo("acme")
            .jsonPath("$.recordId").isEqualTo("r1")
            .jsonPath("$.owner").isEqualTo("alice");
    }

    @Test
    void wrongTenantIsForbidden() {
        client.get().uri("/orders/globex/records/r9")
            .headers(h -> h.setBearerAuth("acme-alice-read"))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void recordOfOtherOwnerIsForbidden() {
        client.get().uri("/orders/acme/records/r2")
            .headers(h -> h.setBearerAuth("acme-alice-read"))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void correctRecordOwnerIsAllowed() {
        client.get().uri("/orders/acme/records/r2")
            .headers(h -> h.setBearerAuth("acme-bob-read"))
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.owner").isEqualTo("bob");
    }

    @Test
    void otherTenantOwnRecordIsAllowed() {
        client.get().uri("/orders/globex/records/r9")
            .headers(h -> h.setBearerAuth("globex-alice-read"))
            .exchange().expectStatus().isOk()
            .expectBody().jsonPath("$.tenant").isEqualTo("globex");
    }

    @Test
    void badAudienceIsUnauthorized() {
        client.get().uri("/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("bad-audience"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void badIssuerIsUnauthorized() {
        client.get().uri("/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("bad-issuer"))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void missingScopeIsForbidden() {
        client.get().uri("/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("acme-no-scope"))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void forgedIdentityHeadersDoNotChangePrincipal() {
        client.get().uri("/orders/acme/records/r1")
            .headers(h -> h.setBearerAuth("acme-alice-read"))
            .header("X-User", "bob")
            .header("X-Tenant", "globex")
            .header("X-Roles", "ROLE_ADMIN")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.owner").isEqualTo("alice")
            .jsonPath("$.tenant").isEqualTo("acme");
    }

    @Test
    void missingRecordReturnsNotFound() {
        client.get().uri("/orders/acme/records/missing")
            .headers(h -> h.setBearerAuth("acme-alice-read"))
            .exchange().expectStatus().isNotFound();
    }

    @Test
    void unlistedBackendPathIsDenied() {
        client.get().uri("/internal/debug")
            .headers(h -> h.setBearerAuth("acme-alice-read"))
            .exchange().expectStatus().isForbidden();
    }
}
```

**14 tests** protecting downstream: direct bypass without token, issuer/audience, scope, tenant, owner/IDOR, forged headers, unknown record, and deny-all. The fake decoder checks a few claims via test logic but **has no cryptographic signature verification**; these tests primarily verify the HTTP security chain and business policy. Never deploy `@TestConfiguration` beans in production.

### 11.1. Running the Tests

In each project root:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

Total of **20 test methods** (6 Gateway + 14 Orders Service). These are **test cases written and statically reviewed**; Gradle execution has not yet been confirmed in the learner's workspace.

To verify Spring Boot security properties in production, add integration tests with a test AS/JWKS and real signed JWTs, expired tokens, wrong issuer/audience, JWK rotation, mTLS, token exchange, and Gateway→backend end-to-end flows. A mock JwtDecoder cannot replace a real signature verification test.

## 12. Scaling to Multiple Services/Tenants

### 12.1. Multi-route Gateways need per-route audiences

```text
/edge/orders/**    -> aud=orders-api
/edge/billing/**   -> aud=billing-api
/edge/hr/**        -> aud=hr-api
```

The demo configuration `audiences: orders-api` only fits a **Gateway with a single Orders route**. When scaling out, never configure a single decoder that broadly accepts all audiences and forwards tokens indiscriminately. Choose per-route policies, trusted issuer/audience resolvers, and token exchange targeting the specific Resource Server. Backends must always enforce their own audience/scope checks.

### 12.2. Tenant selected from hostname/path is only a routing hint

The Gateway may route `acme.api.example.invalid` to the acme shard, but the backend must compare it against the token claim or authoritative membership. If the tenant is declared in a signed JWT, compare it against the record's tenant. If the AS does not issue a tenant claim, look up membership by `iss+sub` from a database/authorization service.

### 12.3. Multi-issuer resolver

Spring Security Reactive provides `JwtIssuerReactiveAuthenticationManagerResolver.fromTrustedIssuers(...)` to handle JWTs arriving from an allowed set of issuers. The resolver may inspect the unverified `iss` to select a decoder, but the issuer must belong to an **allowlist** and be verified by signature/issuer validation afterward. Never construct JWKS URLs from an arbitrary claim; doing so can introduce SSRF.

### 12.4. Service accounts and background jobs

`client_credentials` tokens represent an application and do not automatically carry user tenant memberships. Use dedicated scopes for batch jobs, downstream audiences, and explicit tenant allowlists/audits. Never assign `tenant=*` or admin privileges to all background jobs just to work around authorization errors.

## 13. What the Gateway Cannot Replace for the Backend

- Row-level and object-level ACLs.
- Tenant isolation in R2DBC/SQL queries.
- Business invariant validation on updates.
- Field-level permissions and PII redaction.
- Low-latency revocation/membership business checks.
- Transactional authorization and TOCTOU prevention.
- Account-level rate/resource quotas for expensive operations.
- Non-Gateway access paths such as queues, internal jobs, and RPC.

A system with multiple trust paths cannot rely solely on an HTTP Gateway to enforce all permissions. Every entry point to data requires an equivalent security boundary.

## 14. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| API returns another tenant's data | Backend skips tenant/owner check | Enforce JWT tenant, tenant-aware DB/ACL |
| Direct backend call without token returns 200 | Backend `permitAll` | Configure its own Resource Server |
| `X-User=admin` header escalates privileges | Trusts client header | Strip at ingress, never use header as principal |
| Token with aud payments enters orders | Missing audience validation | `jwt.audiences=orders-api` and service ACL |
| Gateway returns 403 but direct backend returns 200 | Backend lacks scope policy | `hasAuthority("SCOPE_orders.read")` |
| TokenRelay uses ID token | Confused token types | Only access tokens with matching audience |
| TokenRelay needs different downstream aud | No token exchange | Token exchange per AS policy |
| Wrong route path after prefix strip | YAML/predicate mismatch | Integration test raw upstream path |
| YAML routes fail to load | Legacy version prefix | 2025.0 uses `server.webflux.routes` |
| Basic auth prompt appears on Bearer API | Default security chain | Configure `oauth2ResourceServer` and disable basic |
| X-Forwarded-Host blindly trusted | Wrong trusted proxy config | Ingress strips and trusted-proxies allowlist |
| JWT issuer resolver SSRF | Uses arbitrary unverified iss | Trusted issuer allowlist |
| CSRF disabled for cookie login | Confused bearer-only and browser session | Align CSRF with credential model |
| Cache data shared across tenants | Cache key lacks tenant | Tenant-scoped keys, ownership checks |
| Logs contain Bearer tokens | Logging raw headers | Redact Authorization/Cookie/PII |
| Fake decoder tests pass but real JWT fails | Cryptography untested | Signed JWT/JWKS integration tests |
| Gateway overloaded when JWKS/AS is slow | Missing timeouts/caching | Quotas, deadlines, trusted key caching |
| New route headers not stripped | Stripping configured on only one route | Test all routes, apply global boundary policy |

## 15. Exercises with Answers

### Exercise 1. Gateway JWT is valid—is backend permitAll okay?

**Answer:** Not safe by default. If the backend is called directly, Gateway checks are bypassed. The backend must still verify the token/trusted assertion and enforce ACLs.

### Exercise 2. Is scope orders.read enough to read every record in acme?

**Answer:** No. Scope grants an operation-type permission; the service must also verify the token's tenant, the record's tenant, and owner/ACL.

### Exercise 3. What happens when an acme token requests globex/r9?

**Answer:** Rejected with 403 at the backend after verified token tenant != path tenant, even if the Gateway checked the scope.

### Exercise 4. Does X-Tenant=acme prove membership?

**Answer:** No. Headers are controlled by the caller. Obtain the tenant from a verified token/membership DB/trusted assertion.

### Exercise 5. Can X-User=admin be treated as the principal?

**Answer:** Not if it is untrusted plaintext. The Gateway strips it and the backend uses the verified Jwt principal. If using a gateway assertion, it requires signatures/mTLS/audience and no-bypass.

### Exercise 6. Does Gateway TokenRelay automatically change the audience?

**Answer:** No. It forwards the existing access token; use token exchange or request a downstream-scoped token if needed.

### Exercise 7. Can an ID token be used as a Bearer token for Orders Service?

**Answer:** Not under this OAuth2 resource server model. An OIDC ID token serves the Relying Party to verify the user; downstream APIs use an access token with the proper aud/scope.

### Exercise 8. Does the backend still need TLS if the Gateway already uses HTTPS?

**Answer:** Given an appropriate network threat model, internal HTTPS/mTLS protects credentials and workload identity. Gateway HTTPS does not automatically protect the private hop.

### Exercise 9. What if a JWT is valid but has aud=payments-api?

**Answer:** Orders Service rejects it; a valid signature does not prove the token was issued for Orders.

### Exercise 10. Can CORS replace authentication?

**Answer:** No. CORS is a browser policy; non-browser clients can still call the API. The backend must protect itself with tokens/ACLs.

### Exercise 11. Why should Host/X-Forwarded-Host not be trusted automatically?

**Answer:** Callers can spoof them if ingress does not properly normalize/trust proxies. A routing hint is not a tenant entitlement.

### Exercise 12. Why use a fake JWT decoder in tests?

**Answer:** To test security rules and business ACLs offline without depending on an AS. To prove cryptography/JWK rotation, you must use signed test JWTs and a real decoder.

### Exercise 13. Can a multi-service Gateway route use aud=orders-api for all routes?

**Answer:** No. Design per-downstream audience policies or token exchange; each service must validate its own aud.

### Exercise 14. Does mTLS automatically grant permission to read r1?

**Answer:** No. It authenticates the workload/channel, not user-owner/tenant ACLs.

### Exercise 15. What if the Gateway header stripping malfunctions?

**Answer:** The backend still does not trust those headers, so it will not turn them into a principal. Integration-test actual routes and normalize headers at ingress.

### Exercise 16. What should be tested for Gateway bypass?

**Answer:** Direct request without token returns 401, invalid token returns 401, missing scope returns 403, wrong tenant/owner returns 403, valid tenant/owner returns 200.

## 16. Production Checklist

- [ ] Gateway protects ingress, paths, and upstream allowlists, with no dynamic SSRF targets.
- [ ] Backend is not unintentionally public; internal network policy/mTLS/HTTPS matches the threat model.
- [ ] Backend independently validates trusted issuer, JWT signature/introspection, audience, exp/nbf.
- [ ] Scopes are checked at both Gateway and backend where needed.
- [ ] Tenant/membership is verified and matched against the URL and database record.
- [ ] Owner/ACL is checked at the data-owning service, not just the Gateway.
- [ ] Forged identity headers are stripped at ingress; backend never trusts them.
- [ ] `Forwarded`/`X-Forwarded-*` only trust verified proxies, never a public wildcard.
- [ ] TokenRelay uses only access tokens with the right audience/downstream; token exchange when needed.
- [ ] ID tokens/session cookies are never treated as Bearer resource tokens.
- [ ] JWKS/issuer URLs are never fetched from an untrusted JWT to arbitrary hosts.
- [ ] Route rewrites and header sanitization have HTTP integration tests.
- [ ] JWT cryptography, signature/JWKS/expiry/aud are tested with a real decoder and signed tokens.
- [ ] Direct service bypass is tested; unauthenticated callers receive no data.
- [ ] Browser CORS/CSRF/sessions are designed according to the credential model.
- [ ] Gateway and services have rate limits, timeouts, resilience, and auditing.
- [ ] Logs/traces/APM do not leak Authorization/Cookie/tokens/PII.
- [ ] Tenant-aware cache keys and DB queries enforce isolation/ACLs.
- [ ] Production runs supported Boot/Cloud lines with CVE patches applied.

## 17. Summary

```text
Gateway:
  Authn + coarse authz + route allowlist
  Strip X-User/X-Tenant/X-Roles
  Rate limit/TLS/proxy trust
  Forward access token matching the target resource

Orders Service:
  Verify token independently (issuer + aud + signature + exp)
  Check SCOPE_orders.read
  Check signed tenant == requested tenant
  Check record.tenant + owner/ACL
  401/403/404 per policy

Do not confuse:
  Gateway authenticated != backend authorized
  Internal IP / mTLS != permission on a record
  TokenRelay != token exchange
  Token active != valid audience
  X-User header != trusted principal
  Jwt test fixture != signature verification
```

**Takeaway:** The Gateway guards **the entrance and the route**, while downstream guards **resources, tenants, and data**. Combining two independent boundaries limits the blast radius when a proxy rule, identity header, or route is misconfigured.

## 18. Official References

- [Spring Cloud Gateway 4.3 — Server WebFlux starter](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/starter.html)
- [Spring Cloud Gateway — Spring Security Integration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/spring-security.html)
- [Spring Cloud Gateway 4.3 — TokenRelay](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html)
- [Spring Cloud Gateway 4.3 — StripPrefix](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/gatewayfilter-factories/stripprefix-factory.html)
- [Spring Cloud Gateway 4.3 — HTTP Headers Filters](https://docs.spring.io/spring-cloud-gateway/reference/4.3/spring-cloud-gateway-server-webflux/httpheadersfilters.html)
- [Spring Cloud 2025.0 Release Notes](https://github.com/spring-cloud/spring-cloud-release/wiki/Spring-Cloud-2025.0-Release-Notes)
- [Spring Boot 3.5 — Spring Security and JWT Resource Server](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [Spring Security 6.5 — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — Reactive Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/multitenancy.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [RFC 8707 — OAuth 2.0 Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [OWASP — API Security Top 10](https://owasp.org/API-Security/editions/2023/en/0x11-t10/)
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
