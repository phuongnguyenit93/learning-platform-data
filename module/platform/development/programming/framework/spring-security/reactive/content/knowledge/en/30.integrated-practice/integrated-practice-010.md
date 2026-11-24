# Design Review from Threat Modeling to Testing and Deployment — Spring Security Reactive

> **Integrated Practice:** reviewing a WebFlux system from business requirements, threat modeling, security control selection, Spring Security implementation, and negative-path testing through release and operations planning. Examples use Java 17+, Spring Boot 3.x, and Spring Security 6.x; verify BOMs/APIs when adopting newer releases. Domains, tenants, tokens, and accounts are illustrated with dummy data.

## 1. Review Mindset: Proving a Security Property

A design review is satisfactory when it answers six questions with evidence:

1. **What are we protecting?** Which data, actions, and properties matter: confidentiality, integrity, availability, auditability, tenant isolation?
2. **Who and what is trusted?** Which boundaries do browsers, reverse proxies, identity providers (IdP), resource servers, databases, and downstream HTTP services cross?
3. **What can an attacker do?** Unauthenticated callers, callers holding a valid token for another tenant, compromised clients, callers abusing API quotas, or attackers causing a dependency to hang.
4. **Where are controls placed?** Token verification, scopes/roles, ownership checks, CSRF/CORS, data protection, timeouts, rate limits, secrets, auditing, and hardening.
5. **What do tests prove?** Every threat has at least one negative test (attack denied) and technical evidence; mocks must never substitute for real cryptographic or network checks.
6. **Can it deploy safely?** Environment-specific configuration, attack telemetry, rollout/rollback, key rotation, change controls, and incident response plans.

**Never judge security merely by “Spring Security is enabled” or HTTP `200`.** Authentication can succeed while returning another tenant's order; routes can be guarded while sending bearer tokens to the wrong downstream; WebFlux can be enabled while blocking the entire Netty event loop with synchronous JDBC.

Outputs of a review include: data-flow/trust-boundary diagrams, asset inventory, threat register, security decisions, test matrix with results, deployment configuration evidence, and remaining risks with accountable owners.

## 2. Case Study and Explicit Assumptions

Design an **Orders API** running on Spring WebFlux. Order data spans multiple tenants; users or services authenticate with access tokens issued by the organization's IdP.

Endpoints in this lab:

| Endpoint | Purpose | Expected policy |
| --- | --- | --- |
| `GET /public/ping` | Public probe containing no sensitive operational data | Allow anonymous |
| `GET /api/orders/{id}` | View a single order | Valid JWT, scope `orders.read` **and** order belongs to the token's tenant |
| `GET /api/admin/metrics` | Illustrative sensitive business metrics | Valid JWT, scope `admin.read` |
| Undeclared endpoints/methods | No business need | **Deny by default** |

This is the scope of the **runnable code example** in section 7. A real system may add `POST /api/orders`, payments, status updates, OAuth2 Client calls to downstreams, browser sessions, or GraphQL; those risks are analyzed in separate sections rather than **assuming the demo implements them**.

Assumptions and requirements:

- Tokens are JWT Bearer tokens in `Authorization`, from a trusted issuer, with an audience targeting the Orders API (e.g., `orders-api`), within valid lifetime. Production verifies signatures against issuer trust/JWKS rather than trusting unverified claim strings.
- The `tenant_id` claim is issued by the trusted IdP for an authorized identity. Clients **must never** pick a tenant via query/header and be trusted directly.
- Token scopes are mapped by Spring Security to authorities like `SCOPE_orders.read` or `SCOPE_admin.read` under suitable default config. If the IdP uses custom claims, configure and test a custom converter separately.
- In the demo, orders live in memory to focus on security controls. Production must use a repository with tenant-filtered queries, auditing, transactions, and proper DB protections.
- The sample API uses neither cookies for authentication nor form login or HTTP sessions. Thus disabling CSRF can be evaluated **specifically** for this Bearer-only API; adding cookie/browser flows requires redesigning CSRF before release.
- No real customer identifiers, real secrets, or live service networks appear in the example.

### Defining Acceptance Criteria Before Writing Code

| Property | Acceptance condition |
| --- | --- |
| Authentication | Anonymous requests denied on protected routes; expired, wrongly signed, wrong-issuer, or wrong-audience tokens rejected in real verification tests |
| Authorization (endpoint) | Only authorities with the matching scope may call each route |
| Authorization (object) | A tenant A user cannot read tenant B's order even with `orders.read` |
| Fail closed | Undeclared routes/methods are denied; missing `tenant_id` never defaults to “all tenants” |
| Privacy | No cross-tenant order names/details leaked via body, status, or logs |
| Availability | Auth filters, DB, and downstreams never block the event loop; timeouts/backpressure/rate limits are in place |
| Operations | Secrets injected outside source code, missing required config fails startup safely, logs contain no tokens/PII |

## 3. Data Flow Diagram and Trust Boundaries

```text
[User / API client — untrusted]
         |
         | HTTPS, Bearer JWT, input {id}
         v
[Edge / API Gateway / WAF]  -- rate-limit, TLS, size caps -->
         |
         | Boundary A: external client -> internal ingress
         v
[WebFlux Orders API]
   ├─ SecurityWebFilterChain: verify JWT, issuer/audience/time, route scopes
   ├─ Controller: validate input + tenant ownership
   ├─ Reactive service: business rules + audit
   └─ Reactive repository: tenant-scoped DB query
         |                           |
         | Boundary B: app -> DB     | Boundary C: app -> external service
         v                           v
[Orders DB]                   [Payment/Inventory API]
         ^
         |
[Identity Provider] -- Boundary D: token issue / JWKS trust -->
         |
[Workload identity / Secret Manager] -- Boundary E: secret distribution
```

Analyzing each boundary:

- **A — internet to ingress/API:** every header, body, path, and bearer token can be spoofed. Gateways offload traffic, yet the application must still enforce authentication and object-level authorization; never trust `X-User` or `X-Tenant` solely because traffic came via a proxy without a strong trust contract.
- **B — app to database:** DB holds multi-tenant data; querying by `id` without tenant risks isolation breaches. Use bound parameters, tenant-scoped queries, least privilege, and row-level security where appropriate.
- **C — app to downstream:** hosts/redirects can be manipulated for SSRF or Bearer leakage; `WebClient` must restrict destinations, enforce timeouts, and send tokens with the proper audience.
- **D — IdP to API:** verify token signature/`iss`/`aud`/`exp`/`nbf`/algorithm/JWK plus trusted scope and tenant claims. `mockJwt()` in unit tests proves zero cryptographic properties.
- **E — secret distribution:** client secrets, DB passwords, private keys (if any), trust credentials, and JWT verification keys need provisioning, rotation, and audit. A Resource Server typically needs only public JWKS, not private signing keys.

### Identifying Attacker Capabilities

Rehearse at least three attacker profiles:

1. **Anonymous:** holds no token; can probe endpoints/methods, flood requests, and inject malicious headers/JSON.
2. **Valid tenant A user:** holds an access token with `orders.read` and tries to read tenant B's orders by guessing IDs, spoofing tenant headers, adding query params, or forging unsigned claims.
3. **Compromised client or leaked credential:** holds a real token/secret with limited scope and tries to reach higher privileges, replay refresh tokens, or abuse caller-controlled downstream URLs.

Never trust a client just because traffic is “internal” or carries a JWT. Authentication tells *who is calling*; authorization decides *what may be done to a specific object*.

## 4. Threat Modeling with STRIDE and Risk Register

STRIDE is a prompting framework, not an exhaustive checklist. Use **Spoofing, Tampering, Repudiation, Information disclosure, Denial of service, Elevation of privilege** across every data flow. Add API-specific threats such as Broken Object Level Authorization (BOLA), token audience confusion, SSRF, and cross-request state leaks in reactive pipelines.

Example risk register before controls:

| ID | Attack path and asset | STRIDE | Initial risk | Required control | Test / evidence |
| --- | --- | --- | --- | --- | --- |
| T01 | Forged token, wrong issuer, or wrong audience accesses Orders API | S/E | High | JWT signature + `iss` + `aud` + lifetime + JWKS trust | Signed-invalid/wrong-aud tests, decoder integration |
| T02 | Tenant A user guesses tenant B order IDs | I/E | Very high | Scope **and** per-object tenant-scoped authorization | Cross-tenant requests return 404/403 per policy with no body leak |
| T03 | Caller without `orders.read` hits protected route | E | High | `SecurityWebFilterChain`, deny by default | JWT missing scope → 403 |
| T04 | Client sends `X-Tenant: victim`, app trusts header | S/T/E | High | Tenant taken from trusted identity; ignore headers/queries | Altering header does not change tenant authorization |
| T05 | WebClient sends Orders API token to malicious host | I | High | Fixed destination/allowlist, audience-matched token, no auto-forward | Mock downstream captures headers; SSRF checks |
| T06 | Browser uses cookie on cross-site POST | T | High if cookies used | CSRF protection, cookie flags, and CORS policy | Browser-form/CSRF negative tests |
| T07 | API flood starves Reactor Netty or DB pool | D | High | Edge rate limits, timeouts, bounded concurrency, non-blocking I/O | Load/soak tests, event-loop lag, p99 |
| T08 | Tokens, PII, or secrets leak in logs/traces/Actuator | I/R | High | Redaction, structured audit, restricted management exposure | Log scan and endpoint exposure review |
| T09 | JWK/client secret rotated or stale version remains | S/T | High | Workload identity, versioning/rotation, JWKS cache policy, audit | Key rotation/revocation staging rehearsal |
| T10 | Missing audit trail prevents tracing admin actions | R | Medium–High | Immutable audit events, correlation/request IDs, retained access logs | Audit field and retention tests |
| T11 | Blocking JDBC/SDK call stalls event loop in auth filter | D | High | Reactive drivers or `boundedElastic` at blocking boundary | BlockHound (where supported), thread/load metrics |
| T12 | New route added without protection rule | E | High | `anyExchange().denyAll()`; review matchers and actuator mapping | Unknown-route tests and CI security review |

The “Initial risk” column is a **contextual estimate for the case study**, not an automated formula. In a real review, record **likelihood**, **impact**, current controls, **residual risk**, priority, owner, target date, and release acceptance/block decision. A 12-row table does not replace inspecting real code, network topology, and data policies.

### Practical Prioritization Method

1. Assess **impact:** multi-tenant data exposure, admin privilege escalation, or IdP compromise outweighs failing to reject a single malformed request.
2. Assess **exploitability:** public exposure, guessable IDs, missing object-level checks, and leaked keys raise likelihood.
3. Assess **detectability and recovery:** absent audit logs, bulk data exfiltration, or hard-to-rotate keys amplify damage.
4. Fix **T01–T04 and T12** before opening live traffic; re-score after implementing controls.
5. For any remaining high residual risk, require an explicit owner and decision; **never** mark pass solely because unit tests ran.

## 5. Turning the Threat Model into Design Decisions

### 5.1. Validating JWTs Against the Trust Contract

WebFlux Resource Server uses `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` configured with issuer/JWKS to verify signatures. For many apps, Spring Security validates standard claims like expiration and issuer when configured properly; **audience is an application contract and requires explicit validation** if the resource must accept only tokens meant for it.

Never accept a JWT merely because its Base64 payload parses. Never allow `alg: none`, never treat `kid` as a path to fetch arbitrary keys, and never accept an OpenID Connect `id_token` as an API access token just because both are JWTs.

If the IdP issues opaque tokens instead of JWTs, use token introspection with controlled verification, caching, and timeouts; never try to parse an opaque token as a JWT.

### 5.2. Layering Authorization: Route + Object + Action

- **Route:** `GET /api/orders/{id}` requires `SCOPE_orders.read`.
- **Object:** reading an order is allowed only when the trusted principal's tenant matches the order's tenant and other domain constraints hold (e.g., an order scoped to one user inside that tenant).
- **Data layer:** the repository should query by both `id` and `tenant_id` to avoid loading another tenant's row before filtering or triggering side effects/logs.
- **All entry points:** exports, batches, jobs, event handlers, or other admin endpoints must never bypass service/domain authorization.

A `tenant_id` claim inside a JWT is untrustworthy **until the token is verified**; a user holding `orders.read` does not gain access to **every** order across **every** tenant. Never use a client-supplied `X-Tenant-ID` header for authorization unless a dedicated identity-bound delegation contract is designed and tested.

### 5.3. CSRF and CORS by Credential Type

- **Bearer-only API:** does not rely on browser-auto-sent cookies, so CSRF can be disabled on that API once all routes in the chain satisfy this condition. The code example below intentionally fits this model.
- **Browser sessions, form login, cookie-based OAuth2 login:** never blindly disable CSRF; verify state-changing methods, `SameSite`/`Secure`/`HttpOnly` cookies, and CSRF token issuance/submission.
- **CORS:** controls browser cross-origin response access only—it is **not authentication or a firewall**. Configure explicit allowed origins/methods/headers, and handle `OPTIONS` preflight before requiring bearer auth when serving browsers. Never assume “no CORS” stops non-browser HTTP clients from calling the API.
- With multiple security chains, separate browser and Bearer API chains cleanly; review `securityMatcher` order so a `permitAll` chain never intercepts a sensitive route.

### 5.4. Reactive Execution and Side Effects

- Never call `.block()` in controllers, `WebFilter`s, `ReactiveAuthenticationManager`, or Netty callbacks; return `Mono`/`Flux` and compose errors/cancellations cleanly.
- Use R2DBC/async HTTP clients where appropriate. If a blocking SDK is unavoidable, wrap `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` at the **source**, with SDK timeouts, bounded concurrency, and queue monitoring.
- Obtain authentication/tenant identity via `@AuthenticationPrincipal` or `ReactiveSecurityContextHolder`, never via `ThreadLocal` `SecurityContextHolder`.
- In the demo, the API returns `404` for both non-existent orders and cross-tenant blocked orders to reduce enumeration; this policy helps hide existence, yet **does not replace** logging/auditing unauthorized access attempts.
- `WebClient` can retry; for order creation or payment charges, require **idempotency keys** and strict retry conditions. Never retry side-effecting POSTs blindly on HTTP timeouts.

### 5.5. Secrets, Network, and Dependencies

- Supply DB credentials, OAuth2 client secrets, and private keys via a secret manager, config tree, or controlled env vars. Never commit secrets or bake them into images/logs; prefer workload identity scoped per workload and environment.
- Use KMS/HSM for sensitive key material when required; a Resource Server needs only public/JWKS verification keys and must not store JWT private signing keys.
- `WebClient` should call only approved fixed HTTPS base URLs/hostnames, validate redirects/destinations, and restrict egress. Never pass client-supplied URLs directly into `WebClient.uri(...)` for server-side fetches.
- For service-to-service OAuth2, pick the `OAuth2AuthorizedClient`/grant/client registration matching the downstream audience. Never forward incoming bearer JWTs to every downstream by default.
- Scan dependencies for CVEs/SBOM, run containers with least privilege, enforce TLS/mTLS per network design, restrict egress, and lock down Actuator and the management plane.

## 6. Mapping Threats → Acceptance Criteria → Evidence

Every decision needs three dimensions: **policy**, **tests**, and **operations**.

| ID | Pre-merge evidence | Pre-production evidence | Runtime telemetry |
| --- | --- | --- | --- |
| T01 | Anonymous/wrong-scope route tests; dedicated decoder validation tests | Bad-signature/`iss`/`aud` JWT tests against staging IdP/JWKS | Rising 401/`invalid_token`, JWKS fetch/rotation errors |
| T02 | `WebTestClient` cross-tenant 404 without body leaks | Tenant-scoped R2DBC integration tests, migration/schema tests | Cross-tenant attempts, policy-deny audit events |
| T03/T12 | Route scope tests and deny-by-default tests | Scan public URLs, gateway paths, and HTTP methods | 403 spikes, unexpected reachable endpoints |
| T04 | Fake `X-Tenant` header leaves authorization unchanged | Proxy trust policy and header-stripping tests | Spoofed tenant headers, suspicious request patterns |
| T05 | `ExchangeFunction`/`MockWebServer` assert host/token header | Egress allowlists, TLS/certs, and token audience checks | Egress destination anomalies, OAuth errors |
| T06 | CSRF tests if cookies exist; CORS preflight tests | Browser integration tests with real Origin | Post-rollout CSRF rejects / CORS errors |
| T07/T11 | Bounded timeouts, no-`block()` review, load tests | p95/p99, event-loop lag, DB pool saturation thresholds | Latency, rate-limit rejects, scheduler queue depth |
| T08/T09/T10 | Log scanning, secret scans, audit schema checks | Rotation rehearsal, access/RBAC/Actuator review | Secret access audits, token/key failures, audit gaps |

Example **release gate definition**:

- Zero open Critical/High risks without implemented mitigations or formal policy-approved exceptions.
- Mandatory negative authorization tests pass (anonymous, wrong scope, missing tenant, cross-tenant, admin, unknown route).
- Real JWT validation, egress, flow-appropriate CSRF/CORS, and load/timeout scenarios rehearsed in suitable environments.
- Named owners, links to pipeline evidence, log/secret scan results, and a rollback plan exist.
- Mark pass only on **real evidence**; if staging or load tests haven't run, mark “unverified” rather than extrapolating from unit tests.

## 7. Java 17+ Hands-On Lab: WebFlux Orders API with Multi-Layer Authorization

This section builds a **small runnable demo in a Spring Boot 3.x project**. Place each class in its own file under package `demo.review`. Test tokens are synthetic; section 8 tests use `mockJwt()` to prove authorization logic, while cryptographic validation is addressed in section 9.

### 7.1. Dependencies and Startup

In `build.gradle.kts` of a project already configured with the Spring Boot plugin/BOM and Java 17, add:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Do not add `spring-boot-starter-web` to the demo. With Spring Boot 3, the imports below use `org.springframework.boot.test.autoconfigure.web.reactive` for `@AutoConfigureWebTestClient`; Boot 4 may organize test auto-configuration modules differently, so check the actual API/BOM.

Create `src/main/java/demo/review/ReviewApplication.java`:

```java
package demo.review;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReviewApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReviewApplication.class, args);
    }
}
```

### 7.2. Authorization Config: Route Scopes, Deny by Default

File `src/main/java/demo/review/ApiSecurity.java`:

```java
package demo.review;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ApiSecurity {
    @Bean
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                // Suitable only for stateless Bearer APIs without cookies/forms.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .authorizeExchange(routes -> routes
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.GET, "/api/admin/metrics")
                            .hasAuthority("SCOPE_admin.read")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2.jwt(
                        Customizer.withDefaults()))
                .build();
    }
}
```

Notes:

- Specific rules precede `anyExchange().denyAll()`, protecting undeclared endpoints.
- `SCOPE_orders.read`/`SCOPE_admin.read` are the JWT resource server authorities produced by the default scope converter; configure a custom converter if your IdP emits scopes under a different claim.
- `NoOpServerSecurityContextRepository` fits the demo's stateless Bearer design, yet must not be used as a “trick” to drop sessions for browser logins.
- The demo does not enable CORS for SPAs; production must configure approved origins/headers/methods and test preflight requests.
- The demo defines no production `ReactiveJwtDecoder` bean; use `issuer-uri`/`jwk-set-uri`/custom validators in production as shown in section 9. Section 8 tests supply a test-only stub decoder and use mock JWTs.

### 7.3. Demo Repository: Two Orders in Different Tenants

File `src/main/java/demo/review/InMemoryOrders.java`:

```java
package demo.review;

import java.util.Map;

import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class InMemoryOrders {
    private final Map<String, Order> orders = Map.of(
            "ord-a", new Order("ord-a", "tenant-a", "camera"),
            "ord-b", new Order("ord-b", "tenant-b", "keyboard"));

    public Mono<Order> findById(String id) {
        return Mono.defer(() -> Mono.justOrEmpty(orders.get(id)));
    }

    public record Order(String id, String tenantId, String label) {
    }
}
```

This is an immutable in-memory fixture illustrating logic with zero blocking JDBC/JPA/network calls. **Production** should query with tenant filters—conceptually `findByIdAndTenantId(id, tenantId)` with R2DBC—so another tenant's data never enters the service before authorization. Never use a `Map` fixture as a benchmark or real storage solution.

### 7.4. Ownership Check Using Trusted Identity

File `src/main/java/demo/review/OrderController.java`:

```java
package demo.review;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
public class OrderController {
    private final InMemoryOrders orders;

    public OrderController(InMemoryOrders orders) {
        this.orders = orders;
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/api/orders/{id}")
    public Mono<OrderResponse> getOrder(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        String tenant = (jwt == null)
                ? null
                : jwt.getClaimAsString("tenant_id");

        // Prevent a missing tenant claim from becoming global access.
        if (tenant == null || tenant.isBlank()) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.FORBIDDEN));
        }

        return orders.findById(id)
                .filter(order -> tenant.equals(order.tenantId()))
                .map(order -> new OrderResponse(order.id(), order.label()))
                // Do not distinguish "not found" from "different tenant".
                .switchIfEmpty(Mono.error(new ResponseStatusException(
                        HttpStatus.NOT_FOUND)));
    }

    @GetMapping("/api/admin/metrics")
    public Mono<String> adminMetrics() {
        return Mono.just("admin-ok");
    }

    public record OrderResponse(String id, String label) {
    }
}
```

**Two independent barriers:** the Spring Security filter checks scope before invoking the handler; the controller checks `tenant_id` before building the response. Removing the filter lets tenant A invoke under-scoped routes; removing the ownership filter lets any user with `orders.read` read tenant B.

In real apps, also verify validated issuer/audience claims, tenant status, user/role/order permissions, query predicates, and auditing. Never store tenant info in a shared static field/`ThreadLocal`; propagate identity in the reactive request context.

## 8. Negative Testing with `WebTestClient` and `mockJwt()`

The demo tests verify HTTP contract behavior completely decoupled from an authorization server. `mockJwt()` injects a synthetic `JwtAuthenticationToken` into Spring Security Test; it **does not verify signatures, expiration, issuer, audience, or JWKS**. Therefore add real decoder/IdP tests as outlined in section 9.

Create `src/test/java/demo/review/ReviewApiTest.java`:

```java
package demo.review;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
@Import(ReviewApiTest.TestDecoder.class)
class ReviewApiTest {
    @Autowired
    WebTestClient client;

    // Test only: prevent auto-config from contacting issuer over the network.
    @TestConfiguration(proxyBeanMethods = false)
    static class TestDecoder {
        @Bean
        ReactiveJwtDecoder reactiveJwtDecoder() {
            return token -> Mono.error(
                    new BadJwtException("Use mockJwt for this test"));
        }
    }

    @Test
    void publicRouteIsAvailableAnonymously() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void protectedRouteRejectsAnonymous() {
        client.get().uri("/api/orders/ord-a")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void ownerCanReadOwnOrderWithCorrectScope() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-a")))
                .get().uri("/api/orders/ord-a")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo("ord-a")
                .jsonPath("$.label").isEqualTo("camera");
    }

    @Test
    void userCannotReadOtherTenantsOrder() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .subject("alice")
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-a")))
                .get().uri("/api/orders/ord-b")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void missingReadScopeIsForbiddenEvenForOwner() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .claim("scope", "orders.write")
                    .claim("tenant_id", "tenant-a")))
                .get().uri("/api/orders/ord-a")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void missingTenantClaimIsForbidden() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .claim("scope", "orders.read")
                    .claims(claims -> claims.remove("tenant_id"))))
                .get().uri("/api/orders/ord-a")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void fakeClientTenantHeaderCannotBypassTenantCheck() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-a")))
                .get().uri("/api/orders/ord-b")
                .header("X-Tenant-ID", "tenant-b")
                .exchange()
                .expectStatus().isNotFound();
    }

    @Test
    void adminRequiresItsOwnScope() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .claim("scope", "orders.read")
                    .claim("tenant_id", "tenant-a")))
                .get().uri("/api/admin/metrics")
                .exchange()
                .expectStatus().isForbidden();

        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .claim("scope", "admin.read")
                    .claim("tenant_id", "tenant-a")))
                .get().uri("/api/admin/metrics")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-ok");
    }
}
```

Run in a project with the wrapper/BOM: `./gradlew test --tests demo.review.ReviewApiTest`; on Windows: `gradlew.bat test --tests demo.review.ReviewApiTest`. Expected result: **8 `@Test` methods pass**, with no mandatory app stdout. `@SpringBootTest` requires the sample app to sit under scanned packages, WebFlux/Security/JWT dependencies present, and compatible test versions. `TestDecoder` is strictly for tests; when testing real HTTP tokens, replace it with an issuer/JWKS-configured decoder.

**Exact limits of these assertions:**

- `401` means no valid authentication was provided on a protected route.
- `403` means authentication is present yet fails route/business claim rules.
- `404` for another tenant's order reflects the chosen app policy to avoid revealing record existence. To be certain no body/metadata leaks, inspect responses and logs, not status alone.
- `mockJwt()` only mocks principal/authorities. To test custom converters or real JWT signatures, write dedicated tests without pre-mocked authentication.
- The demo uses an in-memory repo; it does not prove R2DBC queries bind tenant properly or that DB row-level security is enabled.

### Adding a “New Route Disallowed” Check

For instance, add a test-only controller `GET /private/debug`, call it with a JWT holding `orders.read`, and assert `403` due to `anyExchange().denyAll()`. If an endpoint **does not exist**, a `404` from having no handler does not prove deny-by-default for a newly added endpoint; test against a genuinely registered route. That is the difference between **route not found** and **route exists but blocked by security**.

## 9. Real JWT Verification and Limits of Mock Tests

When deploying the API to real environments, configure resource-server trust. Example `application-prod.yml` (values supplied at runtime):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${ORDERS_JWT_ISSUER}
```

A valid issuer requires metadata/JWKS and proper TLS trust. Spring Security verifies issuer/timestamps/signatures via the decoder. **An Orders-API-specific audience must still be enforced**, e.g., with a custom validator; do not assume `issuer-uri` alone constrains every audience.

**Alternative** config snippet for a production decoder enabling explicit issuer and audience checks. This is a **configuration fragment** for a production `@Configuration` class given `app.security.jwt-issuer` and `app.security.jwks-uri`; if adding this bean, ensure a single decoder source rather than registering duplicate decoder beans:

```java
@Bean
ReactiveJwtDecoder ordersJwtDecoder(
        @Value("${app.security.jwt-issuer}") String issuer,
        @Value("${app.security.jwks-uri}") String jwksUri) {

    NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwksUri).build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                    "invalid_token",
                                    "Unexpected token audience",
                                    null));

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    issuerAndTime, audience));
    return decoder;
}
```

Imports for this fragment (merge into the corresponding config class):

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
```

Production must also check allowed JWS algorithms, key lifecycle, JWKS caching, clock skew, issuer/audience contracts, and tenant/role claims per IdP policy. Load `jwksUri` from **trusted deployment configuration**, never from arbitrary tokens or request inputs. If the IdP uses complex tenant mappings, add a converter/validator or authorization service rather than relying solely on a string claim.

Dedicated test matrix for decoder and integration:

| Token or scenario | Expected |
| --- | --- |
| JWT signed by right test issuer private key, `aud=orders-api`, unexpired | Request accepted per policy |
| Signed by unknown private key | `401 invalid_token` |
| `iss` differs from trusted issuer | `401` |
| `aud` missing `orders-api` | `401` |
| Past `exp` / future `nbf` beyond tolerance | `401` |
| Invalid/disallowed `alg` header | `401` |
| JWKS/key rotation | New key accepted; old tokens handled per TTL/revocation policy |
| IdP/JWKS temporarily unavailable | Cache/timeout behavior verified; verification never bypassed |

These checks must use **real signed JWTs** with test keys and a real decoder, or an integration environment with a controlled test IdP/JWKS. Never use `mockJwt()` to claim signature, expiration, or issuer checks work. Record clearly which test layer proves which property.

## 10. Integration Testing, Data, and Downstream Flows

### 10.1. Database / Multi-Tenant Isolation

For production R2DBC/PostgreSQL, test that queries return only the matching tenant, even when a client guesses another tenant's ID. Illustrative parameterized query (conceptual SQL, adjusted for dialect/schema):

```sql
SELECT id, tenant_id, label
FROM orders
WHERE id = :orderId AND tenant_id = :tenantId;
```

Always use bound parameters via R2DBC `DatabaseClient`/repositories, never concatenating user input into SQL. If DB row-level security is enabled, test with the **actual application DB role**; connection-pool/session tenant state must be set, reset, and isolated properly. Test cross-tenant queries and concurrency instead of assuming “filtering in the controller” suffices.

### 10.2. WebClient and Outbound Tokens

If the service calls Payment/Inventory:

- Allow only approved hostnames/HTTPS base URIs; never let client-supplied `orderId` or callback URLs select an arbitrary host.
- With OAuth2 Client, test exact client registrations, `OAuth2AuthorizedClient`, and **downstream token audience/scopes**, avoiding blindly forwarding incoming bearer tokens to other hosts.
- Use `MockWebServer`/WireMock or a fake `ExchangeFunction` to assert request method, URI, `Authorization` header, and that secrets/tokens never leave for out-of-scope hosts.
- Test downstream `401/403`, `429`, `5xx`, timeouts, and cancellation; distinguish outbound `401` from an under-privileged inbound caller.
- If adding a transaction-creating `POST`, require idempotency keys, storage deduplication, and retry rules to avoid double charges.

### 10.3. Sessions, CSRF, CORS, and Browsers

If browser cookie login is added later:

- Use `WebSession`/reactive Spring Session appropriately; never import `HttpSession` or Servlet filters into WebFlux.
- Test `Secure`/`HttpOnly`/`SameSite` cookies, session fixation, logout, expired sessions, and shared session state across pods if needed.
- Enable CSRF protection per flow; negative tests must confirm POST/DELETE without a CSRF token are rejected.
- CORS: test preflight and actual requests with allowed and disallowed origins; never combine wildcard origins with credentials.
- Separate bearer-only and stateful browser chains with explicit matchers/order so the API's disabled CSRF never leaks onto cookie-authenticated routes.

### 10.4. Blocking Threads and Resilience

Inspect the call graph for: `.block()`/`.blockFirst()` on the event loop, `Thread.sleep`, JDBC/JPA, `RestTemplate`, long synchronization locks, blocking SDK/KMS calls, `CompletableFuture.join`, and large file I/O. Prefer reactive APIs or offload at the exact blocking boundary with `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, paired with DB/downstream limits. Run load tests with slow/timeout faults to measure p95/p99 and event-loop lag rather than extrapolating throughput from unit tests.

## 11. Complete Testing Matrix from PR to Staging

| Test layer | Core cases | Suitable tools | Evidence limitations |
| --- | --- | --- | --- |
| Unit/domain | Ownership rules, missing tenant, validators/DTOs | JUnit 5, `StepVerifier` | Does not verify Security filters or HTTP routing |
| WebFlux security slice/integration | `401/403/404/200`, scopes, methods, default deny, proper CSRF/CORS | `WebTestClient` + Spring Security Test | `mockJwt()` does not prove cryptography |
| JWT decoder integration | Signature, issuer, audience, expiry, algorithms, JWKS rotation | Signed test JWT + real decoder/mock JWKS HTTP | Does not prove deployment firewalls or RBAC |
| Data integration | Tenant-scoped R2DBC queries, duplicates/idempotency, transactions | Testcontainers / isolated DB | Cannot be replaced by a `Map` repository |
| HTTP downstream | Bearer forwarding, host allowlists, retries/timeouts | `MockWebServer`/WireMock | Does not prove prod TLS or real IdP |
| Browser integration | Cookie sessions, CSRF, CORS preflight, redirects/logout | Browser/HTTP integration tests | Requires real browser flows |
| Security pipeline | Secret scanning, SCA/SBOM, linters, image scanners | CI tooling | Scanners have false negatives/positives |
| Dynamic/security checks | BOLA, injection, SSRF, request floods, access bypass | Authorized DAST/pentest in staging | Run only within authorized environments |
| Performance/soak | Event-loop saturation, latency, DB pools, retry storms | Load generator + metrics | Does not replace security logic checks |
| Deployment rehearsal | Secret rotation, JWKS, canary/rollback, recovery | Production-like staging | Never report PASS from paper designs alone |

**Never conflate “mock JWT passes” with “JWT trust verified.”** Both require independent evidence. Every test record should capture environment, version, commit/artifact, fixture data, outcome, redacted logs/traces, and CI link.

## 12. Per-Change Review Checklist

Before approving a security-impacting pull request, reviewers should verify:

**Security model and access control**

- Do new routes have explicit policies? Is `anyExchange().denyAll()` still intact?
- Are scopes taken from a **verified token** rather than a raw request string?
- Do all object queries filter by tenant/owner or enforce domain policies?
- Can another tenant be passed via path/header/query/body to bypass checks?
- Do admin permissions and state mutations have required business approvals/auditing?
- With multiple `SecurityWebFilterChain` beans, could chain precedence expose a route?

**Input and output**

- Are paths/queries/bodies validated for size, format, and contract constraints?
- Do DB queries use bound parameters with no user-controlled dynamic SQL/scripts/path traversal?
- Do error responses avoid disclosing cross-tenant record existence, stack traces, tokens, or credentials?
- Is sensitive data minimized in JSON/audit/traces without logging raw `Authorization` headers?

**Reactive and dependencies**

- Are there zero blocking calls on the Netty event loop and zero fire-and-forget `subscribe()` calls in handlers/filters?
- Do downstreams enforce timeouts, concurrency limits, circuit breakers/bounded retries, and avoid wrong-audience tokens?
- Are sessions managed with WebFlux APIs and authentication read from Reactor Context?
- Are exceptions mapped properly: unauthorized `401`, authenticated-but-denied `403`, non-visible object `404` per policy?

**Deployment**

- Are secrets supplied via an approved secret store/identity with no hardcoding, build-arg leaks, or image leaks?
- Are key rotation/revocation, TLS trust, and egress tested? Do staging/prod differ on auth config?
- Does Actuator expose only needed endpoints with protection, and are logs/metrics free of tokens/PII?
- Is there a clear answer for “if bad authorization ships, where do we roll back and revoke tokens?”

## 13. Secure Deployment and Runtime Observability

### 13.1. Environment Configuration

- **Production:** supply issuer/JWKS/audience trust, HTTPS/TLS, workload identity, DB credentials, and downstream URLs from managed config outside source code.
- **Fail fast** when required config values are missing; never fall back to `dev-password` defaults or fake issuers in production.
- Restrict secret read access per Pod/service account, disable env dumps, lock down `/actuator/env` and `/actuator/configprops`, and inspect logs/CI artifacts.
- Configure trusted proxy headers for accurate scheme/host/redirects while never trusting raw `X-Forwarded-*` from Internet clients before proxy sanitization.
- Restrict network access to DB/IdP and egress to approved downstreams; signer private keys must never sit in the resource-server image.

### 13.2. Pre-Deployment Pipeline

```text
Commit / PR
  -> code review + threat changes identified
  -> secret scan + dependency scan + SAST
  -> unit + WebFlux authorization negative tests
  -> JWT decoder + R2DBC + HTTP downstream integration
  -> build immutable artifact + provenance/SBOM
  -> staging: DAST authorized + load/timeout + secret/key rehearsal
  -> approve release gates + canary
  -> monitor + expand rollout / rollback
```

Archive evidence at every gate. **Not every load or pentest must run on every commit**; choose cadences aligned with risk and release schedules, ensuring sensitive releases have current valid results. Temporarily waived dependency vulnerabilities require justification, an owner, an expiration date, and mitigations.

### 13.3. What to Observe Post-Rollout

- **Properly anonymized** `401` and `403` rates by endpoint/tenant, without logging raw tokens.
- Cross-tenant access attempts, unusual methods, request rates above baseline, and gateway `429`s.
- JWT verification failures, JWKS fetch/cache issues, issuer downtime, certificate expiry, and host clock drift.
- p95/p99 latency, event-loop lag, `boundedElastic` queue depth, R2DBC pool usage, and downstream timeouts/retries.
- Secret manager anomalous access audits, key/secret rotation status, and access policy changes.
- Trace/correlation IDs free of sensitive PII; audit logs retain user/tenant references per retention/access policy without tokens.

Monitor **security signals** and **availability** together: a 401 spike can stem from legitimately expired tokens or broken issuer/key rotation; a 403 spike can indicate wrong scope rules or a BOLA probe. Always confirm from primary telemetry before concluding.

### 13.4. Canary, Rollback, and Incidents

- Canary on a slice of traffic with controlled feature/routing flags, comparing `401/403/5xx`, p99, and cross-tenant behavior.
- If a release introduces an auth bypass, isolate routes/traffic, roll back the artifact, disable exposed privileges/tokens, and investigate audits—**rolling back code does not undo already exfiltrated data**.
- On leaked client secrets or private keys, rotate/revoke at the issuer, block old credentials, and audit logs, images, Git history, and downstream permissions.
- On JWT signing key rotation, coordinate `kid`, JWKS caching, token TTLs, and overlap windows; never remove old public keys prematurely and break valid tokens unless executing emergency compromise revocation.
- When deploying tenant-related schema/DB policy changes, ensure data-compatible rollbacks, test transactions, and verify permissions under the real DB role.

## 14. Anti-Patterns That Commonly Fail Reviews

| Anti-pattern | Why it is dangerous | Design / test fix |
| --- | --- | --- |
| `.anyExchange().permitAll()` as default then protecting a few routes | New routes become public easily | Default deny and test genuinely registered routes |
| Checking only `hasAuthority("SCOPE_orders.read")` | Scope says nothing about which tenant owns an order | Object-level / tenant-level authorization |
| Trusting client-supplied `X-Tenant-ID` | Tenants can be spoofed | Derive tenant from verified principal / auth service |
| Claiming signatures are safe because `mockJwt()` passed | Mocks skip cryptographic decoding | Dedicated signed/invalid JWT tests |
| Skipping `aud` validation | Tokens issued for another resource can be accepted | Audience validator matching the API contract |
| Relying solely on CORS to block access | Non-browser HTTP clients still call the API | JWTs, authorization, and network controls |
| Disabling CSRF for all flows | Cookie/browser credentials become CSRF-vulnerable | Separate chains by credential type and test |
| `Mono.just(jdbcDao.load(id))` | JDBC runs eagerly and can block the event loop | R2DBC or `fromCallable + boundedElastic` |
| Manual `subscribe()` in filters for audit/auth | Side effects run outside response chain, risking races/lost context | Compose publishers with reactive operators |
| `WebClient` forwards incoming `Authorization` to any host | Token leakage and confused deputy | Pick audience-matched outgoing client/token + host allowlist |
| Logging full JWTs, request bodies/headers to debug | Leaks secrets/PII | Redaction and structured audit allowlists |
| Not testing missing tenant claim | Can fail open | Missing claim → 403 |
| Trusting staging based on a few unit tests | Misses real network/DB/IdP boundaries | Integration, load, and rotation rehearsals |
| Keeping signing private keys on the resource server | Expands compromise blast radius | Verify with public JWKS; keep private keys on signer |
| Blindly retrying payment POSTs | Duplicate transactions after commit timeout | Idempotency/deduplication and strict retry contracts |

## 15. Reusable Review Report Template

```markdown
# Security Design Review: Orders API
## Scope
- Release/commit:
- Data classification and tenant model:
- Included endpoints, services and deployment environments:
- Explicit exclusions:

## Trust boundaries
- Client -> Gateway -> WebFlux
- WebFlux -> IdP/JWKS
- WebFlux -> DB
- WebFlux -> downstream and secret manager

## Threat register
| ID | Asset | Threat | Likelihood | Impact | Control | Test | Owner | Residual risk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

## Security decisions
- JWT issuer/audience/expiry/algorithm and key lifecycle:
- Route and object authorization:
- CSRF/CORS/session:
- Input validation and downstream token:
- Reactor nonblocking and quotas:
- Secrets, logging, audit, deployment:

## Evidence
- PR/CI authorization tests:
- Decoder signature/issuer/audience tests:
- DB tenant isolation:
- Downstream/SSRF/timeout checks:
- Staging/browser/load/key rotation:
- Vulnerability/secrets scan:
- Monitoring/rollback rehearsal:

## Release decision
- PASS / CONDITIONAL / BLOCK
- Unresolved risks, owners and due dates:
- Reviewer and approval record:
```

This is a **template**; blank fields are for real reviews, not the status of the demo or any live deployment. A `CONDITIONAL` decision is valid only when policy allows it, with an owner, mitigation, due date, and accepted scope. If token validation or tenant isolation has not actually been verified, production traffic should normally be blocked.

## 16. Self-Assessment Exercises

1. A valid tenant A JWT has scope `orders.read` and calls `GET /api/orders/ord-b` belonging to tenant B. Name the **two authorization layers** involved and the expected status.
2. Why must adding `X-Tenant-ID: tenant-b` to a request never override the JWT's tenant identity?
3. If `mockJwt()` allows a request with `iss=evil`, what conclusion are you **forbidden** to draw from that test?
4. Why does `issuer-uri` alone not guarantee `aud=orders-api` is validated?
5. A frontend uses cookie sessions to send browser POSTs. Can it copy `csrf(disable)` from the Bearer-only demo? What must be tested?
6. When a Payment API call times out after the server already charged the card, why is retrying without an idempotency key dangerous?
7. Which test confirms the API never returns another tenant's order **even after** the user passes route-level scope checks?
8. When adding a new route `GET /api/orders/export`, how must matchers, default deny, and object-level authorization be reviewed?
9. Why does `Mono.just(jpaRepository.findById(...))` fail to make JDBC non-blocking?
10. Write the three most critical release gates for opening canary traffic on a multi-tenant system and explain the matching evidence.

## Learning Resources and Reference Standards

- Spring Security — Reactive WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive Testing OAuth2/JWT: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security — Reactive CSRF: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Framework — WebFlux Testing: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Spring Framework — WebFlux Concurrency Model: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- OWASP — API Security Top 10 (BOLA, Broken Auth, SSRF, Misconfiguration): https://owasp.org/API-Security/
- OWASP — ASVS (Application Security Verification Standard): https://owasp.org/www-project-application-security-verification-standard/
- OWASP — Threat Modeling: https://owasp.org/www-community/Threat_Modeling

> When applying to a real project, replace dummy data with authorized environment config, verify against current Spring Boot/Security versions, and gather **executed evidence** before declaring any control satisfied. Tests mocking tokens, storage, or gateways prove only the layers they actually traverse.
