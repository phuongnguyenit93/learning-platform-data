# Testing CORS, Preflight, JWT, Session, and TokenRelay

## Lesson Objectives

In the **Testing** chapter of the **Spring Cloud Gateway** module, this lesson builds an **end-to-end** security testing strategy for a microservices entry point. Four concerns frequently appear on the same request yet must be verified **independently and in order**:

1. **CORS and preflight:** Is a browser allowed to call the API from another origin? Which layer handles `OPTIONS`, and which response headers come back?
2. **JWT:** Is the token valid in signature, issuer, audience, and expiration? Does the principal hold sufficient authorities to pass through the Gateway?
3. **Session:** Does an OAuth2 Login user hold a valid session? How are cookies, sessions, CSRF, and logout handled?
4. **`TokenRelay`:** Does the Gateway retrieve the user's/authorized client's **OAuth2 access token** and place it cleanly into the **outbound `Authorization` header** sent downstream?

Each mechanism serves a distinct purpose: **CORS is not authentication**, **authentication is not authorization**, **a session cookie is not a downstream access token**, and **`TokenRelay` does not verify resource permissions on the backend**.

After this lesson, you will be able to:

- Design a test matrix covering **allowed/denied origins**, `OPTIONS` preflight, actual requests, and `Access-Control-Allow-Credentials`.
- Distinguish CORS `allowedMethods`/`allowedHeaders` from route `Method` predicates.
- Write `WebTestClient` tests for HTTP/CORS and use a backend stub to verify routes, headers, and real bodies.
- Use `mockJwt()` to test scopes/authorities while understanding why it **does not verify signatures, JWKS, `iss`, `aud`, or `exp`**.
- Test real JWTs using a test issuer/JWKS, malformed tokens, expired tokens, wrong audiences, and key rotation.
- Use `mockOAuth2Login()`, `mockOidcLogin()`, and `mockOAuth2Client()` in the right test scope without mistaking them for a real OAuth2 authorization-code flow.
- Test `WebSession`, `SESSION` cookies, `SameSite`/`Secure`/`HttpOnly`, CSRF, logout, timeouts, and multiple Gateway replicas.
- Verify `TokenRelay` forwards the **right access token for the right registration/audience**, never substituting an ID token or browser cookie.
- Accurately diagnose `401`/`403`/`404`, preflight errors, IdP redirects, backend 401s, session stores, and token forwarding.
- Configure safe logging so **no JWTs, cookies, refresh tokens, client secrets, or OAuth2 authorization codes** leak into test reports.

> **Scope:** Spring Cloud Gateway **Server WebFlux**, Spring Security WebFlux (`SecurityWebFilterChain`, `ServerHttpSecurity`), and Gateway route/filter chains. Gateway Server Web MVC, Servlet `HttpSecurity`, and `MockMvc` use different APIs; do not copy reactive test snippets to MVC. Primary config examples use the modern `spring.cloud.gateway.server.webflux.*` namespace; older releases use `spring.cloud.gateway.*`. Always align with your actual Spring Boot/Spring Cloud Gateway/Spring Security release train.

## 1. A Single Request Crosses Multiple Boundaries

Our illustrative system serves two client models:

- **SPA:** a frontend at `https://app.example.com` calling `https://api.example.com/api/orders/**` with a bearer JWT.
- **BFF / OAuth2 Login:** a browser holding a Gateway session cookie while the Gateway uses `TokenRelay` to send an OAuth2 authorized client's access token to the Order Service.

```mermaid
flowchart LR
    SPA["SPA / Browser<br/>https://app.example.com"]
    O["Gateway<br/>CORS + Security WebFilters"]
    RT["Gateway route predicates<br/>Path / Method"]
    FR["GatewayFilter chain<br/>TokenRelay / rewrite"]
    API["Order Service<br/>JWT authz + business checks"]
    IDP["OAuth2 / OIDC IdP"]
    SES["WebSession / authorized-client store"]
    SPA -->|"OPTIONS + GET /api/orders"| O
    IDP <-->|"Authorization Code / JWKS"| O
    O <--> SES
    O --> RT --> FR -->|"Bearer access token if relayed"| API
```

For a cross-origin request using `Authorization`, a browser typically executes:

```text
1. OPTIONS /api/orders/42  (preflight)
2. Gateway returns valid CORS policy
3. GET /api/orders/42 + Origin + Authorization: Bearer ...
4. Spring Security validates token and scopes
5. Gateway selects route and runs filters
6. Backend receives HTTP request
7. Gateway returns response with matching CORS headers
8. Browser decides whether JavaScript may read the response
```

If step (2) fails CORS, the browser **never sends the actual GET for that preflight**. If step (4) fails, the backend may **never be called**. If step (7) omits `Access-Control-Allow-Origin`, the backend may have returned 200 while JavaScript **still cannot read the response**.

### 1.1. Do Not Collapse Everything into One `200 OK` Assertion

| Layer | Test question | Representative assertion |
| --- | --- | --- |
| Route predicate | Did the Gateway select the right route? | Backend stub receives exact method/path |
| CORS preflight | Is the browser allowed to send the actual request? | `OPTIONS` response includes proper ACAO/ACAM/ACAH |
| Authentication | Is the credential valid? | Invalid/missing token fails security |
| Authorization | Does the principal hold the permission? | Missing scope returns 403; backend receives no request |
| Session | Is login preserved and revoked cleanly? | Cookie/session works on follow-up requests; logout invalidates it |
| `TokenRelay` | Was the right access token forwarded? | Upstream receives the **exact** `Authorization: Bearer ...` |
| Backend authorization | Does the service verify scope/audience/owner? | Token lacking resource permission is denied by backend |
| CORS actual response | Can the browser read the response? | GET response carries ACAO for the allowed origin |
| Observability | Is evidence present without leaking secrets? | Logs contain only route/status/trace ID |

Security testing must cover **both happy paths and negative paths**. A test returning 200 might skip route checks, fake a JWT, or never inspect the downstream token.

## 2. Two Authentication Models to Keep Separate in Tests

### 2.1. Model A — Resource Server Accepting Bearer JWTs

```text
SPA or native client
    → Authorization: Bearer <JWT>
    → Gateway validates JWT
    → Route /api/orders/**
    → Backend (enforces authorization per contract)
```

Here the Gateway acts as an OAuth2 **Resource Server**: it validates incoming tokens. Tokens may still be forwarded via a dedicated mechanism, which **differs** from an OAuth2 **Client** holding an authorized client/session and applying `TokenRelay`.

### 2.2. Model B — OAuth2 Login + Session + `TokenRelay`

```text
Browser
    → /oauth2/authorization/portal
    → IdP Authorization Code + OIDC
    → Gateway creates authenticated WebSession
    → Browser sends session cookie
    → Gateway looks up OAuth2AuthorizedClient
    → TokenRelay attaches access token to outbound request
    → Backend Resource Server validates access token
```

Both models can coexist in one app, so tests must **state explicitly which security chain each request traverses**. Never treat session cookies and bearer JWTs as interchangeable forms of the same credential.

| Concept | Purpose | Where it typically lives |
| --- | --- | --- |
| JWT access token | API authentication/authorization by audience & scope | `Authorization` header |
| OIDC ID token | Proof of login event for the OAuth2 client | Inside OAuth2/OIDC login context |
| Refresh token | Renews authorized client access tokens per policy | Server-side authorized-client store |
| Session ID cookie | Reference to `WebSession`/login state | `Cookie` header from browser |
| CSRF token | Prevents unauthorized state-changing browser actions | Header/form token in session flows |
| CORS origin | Condition for browsers allowing JS to read responses | `Origin`, `Access-Control-Allow-Origin` |

**Never substitute an ID token for an access token** when calling the Order Service. Backends expect an access token with the right **audience and scopes**, not proof that the user logged into the Gateway.

## 3. Tiered Testing Strategy

Instead of spinning up an IdP, Redis, TLS, Gateway, discovery, and five microservices for every single test, split tests into focused tiers:

| Tier | Tools | What does it genuinely prove? | What does it not prove? |
| --- | --- | --- | --- |
| **Unit authz** | `WebTestClient` + `mockJwt()` | Path/scope/role rules with a synthetic principal | JWT signatures / JWKS |
| **Unit OAuth2** | `mockOAuth2Login()`, `mockOAuth2Client()` | Security context / authorized-client logic | Real browser redirects, callbacks, or cookies |
| **Gateway integration** | Spring Boot random port + HTTP stub | Routes, filters, CORS, header forwarding | Full IdP flow when login is mocked |
| **JWT validation** | Real JWT + test key/JWKS server | Signatures, `iss`, `aud`, `exp`, `nbf`, algorithms | Backend resource ownership unless tested too |
| **OAuth2 authorization-code E2E** | Test IdP/OIDC + browser/HTTP client | Redirects, `state`, callbacks, sessions/cookies | Production IdP availability |
| **Distributed integration** | 2+ Gateway replicas + session store | Cookie/session consistency, authorized-client persistence | Absolute production-scale capacity |
| **Browser E2E** | Browser automation | Real CORS enforcement, credentials/cookies, redirects | Crypto/JWKS edge cases unless explicitly tested |

**Rule:** every test must state **which components are real and which are mocked**. If you use `mockJwt()`, the conclusion is *authorization rules match for a mocked principal*, never *production JWT validation is verified*.

### 3.1. Test Dependencies

Maven example for a Spring Boot WebFlux application:

```xml
<dependencies>
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
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Production dependencies depend on the active profile and may include:

```text
spring-cloud-starter-gateway-server-webflux
spring-boot-starter-security
spring-boot-starter-oauth2-resource-server  (JWT API)
spring-boot-starter-oauth2-client           (OAuth2 Login / TokenRelay)
```

Pick a Spring Cloud BOM compatible with Spring Boot; newer starter names and versions may differ from older lines. For HTTP stub backends, use **MockWebServer**, **WireMock**, or a dedicated test HTTP server outside the Gateway port.

### 3.2. Naming Test Fixtures Deliberately

Label synthetic test fixtures clearly:

```text
ALLOWED_ORIGIN       = https://app.example.com
DENIED_ORIGIN        = https://attacker.example
API_BASE             = http://localhost:<gateway-random-port>
UPSTREAM_STUB        = http://localhost:<stub-random-port>
TEST_JWT_VALID       = token signed with test key (NOT a production key)
TEST_SESSION         = session state from test login
TEST_ACCESS_TOKEN    = FAKE_ACCESS_TOKEN_FOR_STUB
```

**Never** use real tokens/sessions, staging customer client secrets, or access tokens copied from browser DevTools in assertions. Generate test data inside the test process or use invalid synthetic credentials.

## 4. CORS: Origin, Actual Request, and Preflight

An **Origin** is defined by **scheme + host + port**:

```text
https://app.example.com
https://app.example.com:8443
http://app.example.com
```

are three distinct origins. `/path` and query strings are **not part of Origin**.

Browsers typically send:

```http
OPTIONS /api/orders/42 HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization,content-type
```

Headers to inspect in the preflight response:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST
Access-Control-Allow-Headers: authorization,content-type
Access-Control-Max-Age: 600
Vary: Origin
```

Header values and list ordering vary across implementations; **do not assert exact string ordering** when semantics are sets of values. Preflight may return 200 or 204 depending on framework/configuration, so assert per contract rather than forcing one status everywhere.

### 4.1. CORS Is Not Authorization

CORS is a **browser-enforced rule** controlling whether a web page can read a cross-origin response. `curl` and backend HTTP clients ignore browser same-origin policy:

```bash
curl -i \
  -H "Origin: https://attacker.example" \
  "https://api.example.com/api/orders/42"
```

If the server returns 200 without `Access-Control-Allow-Origin`, browsers block JavaScript from reading the body; **it does not mean the API rejected the request at the authentication layer**.

Therefore:

- CORS does not block direct API calls.
- CORS does not replace JWT validation, role/scope checks, or backend authorization.
- CORS does not replace CSRF protection when browsers attach cookies automatically.
- Never treat the `Origin` header as proof of user/tenant identity.

### 4.2. Every CORS Test Needs Two Requests

**Preflight** and the **actual GET** are two separate exchanges:

```text
OPTIONS: verifies allowed method/headers/origin
GET:     verifies auth, route, backend, and CORS response headers
```

A passing `OPTIONS` test **does not prove the actual GET carries ACAO**. Conversely, a passing GET in `WebTestClient` **does not prove a browser can send GET with a custom `Authorization` header**, because the browser must clear preflight first.

## 5. Global CORS and Route Metadata in the Gateway

Spring Cloud Gateway Server WebFlux supports CORS configuration at either the **global** or **per-route** level. Keep demo policies distinct; never stack overlapping policies unintentionally.

### 5.1. Global CORS Example for Integration Tests

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          globalcors:
            add-to-simple-url-handler-mapping: true
            cors-configurations:
              '[/**]':
                allowedOrigins:
                  - "https://app.example.com"
                allowedMethods:
                  - GET
                  - POST
                allowedHeaders:
                  - Authorization
                  - Content-Type
                  - X-Request-Id
                exposedHeaders:
                  - X-Trace-Id
                allowCredentials: true
                maxAge: 600
          routes:
            - id: orders
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
                - Method=GET
              filters:
                - StripPrefix=1
```

Explanation:

- `allowedOrigins` lists **exact origins** with no trailing path slashes.
- `allowedMethods` lists **methods CORS permits browsers to invoke**, separate from route `Method` predicates.
- `allowedHeaders` lists request headers browsers may send on actual requests.
- `exposedHeaders` lets browser JS read extra **response headers** beyond CORS-safelisted defaults.
- `allowCredentials: true` permits credentialed cross-origin responses per policy; **it neither issues nor validates cookies/JWTs**.
- `maxAge` controls how long browsers cache preflight results, not JWT/session lifetimes.
- `add-to-simple-url-handler-mapping: true` helps when `Method=GET` stops `OPTIONS` from matching the route predicate, letting the global CORS handler answer preflight.

**Important:** `localhost:9001` here represents a test stub backend; it does not apply to production where no service listens there. Substitute the live test server port via dynamic test configuration.

### 5.2. Configuring CORS Per Route

Replaces the global policy above with `metadata.cors` on the target route:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders
              uri: http://localhost:9001
              predicates:
                - Path=/api/orders/**
              metadata:
                cors:
                  allowedOrigins:
                    - https://app.example.com
                  allowedMethods:
                    - GET
                  allowedHeaders:
                    - Authorization
                  allowCredentials: true
                  maxAge: 300
```

**This is an alternative to the global config above**; do not paste both into one test app assuming Spring picks the one you want. With route-level CORS metadata, if the route also defines `Method=GET`, `OPTIONS` will fail to match the route; pair it with an appropriate global handler mapping or Security CORS integration.

### 5.3. Combining CORS with Spring Security

Spring Security WebFlux executes **before** Gateway route filtering on most paths. Preflights normally **carry no session cookies or `Authorization` headers**. If Security rejects `OPTIONS` before CORS runs, browsers report a CORS failure even when the JWT used on the actual GET is valid.

Therefore:

- CORS must process preflights **ahead of the authentication gate**.
- Use `CorsWebFilter`/Spring Security CORS integration, or allow `OPTIONS` through a **tightly scoped** security rule so Gateway global CORS handles it.
- Never treat `.pathMatchers(HttpMethod.OPTIONS, "/**").permitAll()` as a complete solution; it only alters authorization and **does not emit ACAO/ACAM/ACAH**.
- Never let two CORS owners (Gateway, Spring Security, ingress, backend) emit duplicate `Access-Control-Allow-Origin` headers.
- Even when `OPTIONS` is permitted, **actual GET/POST requests must still undergo full auth/authz**.

CORS/Security ordering is a configuration choice that requires **integration tests on your real framework version**, not isolated unit tests of a single filter.

## 6. Testing Preflight with `WebTestClient`

The example below assumes the Gateway runs on a random port with the CORS profile from section 5.1, and `WebTestClient` **sends real HTTP traffic** to the Gateway listener.

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class GatewayCorsHttpIT {

    @LocalServerPort
    int port;

    private WebTestClient client() {
        return WebTestClient.bindToServer()
            .baseUrl("http://localhost:" + port)
            .build();
    }

    @Test
    void allowedPreflightContainsCorsPolicy() {
        client().options()
            .uri("/api/orders/42")
            .header(HttpHeaders.ORIGIN, "https://app.example.com")
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                "GET"
            )
            .header(
                HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                "authorization,content-type"
            )
            .exchange()
            .expectStatus().is2xxSuccessful()
            .expectHeader()
                .valueEquals(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                    "https://app.example.com"
                )
            .expectHeader()
                .exists(HttpHeaders.ACCESS_CONTROL_ALLOW_METHODS)
            .expectHeader()
                .exists(HttpHeaders.ACCESS_CONTROL_ALLOW_HEADERS);
    }
}
```

**Note:** this snippet is a **test fixture** requiring matching dependencies, test profile, and coordinated security/CORS beans. `@LocalServerPort` packages may shift in newer Spring Boot lines; check your dependencies. Unused imports like `@Autowired` can be dropped in your project.

This test exercises **live HTTP preflight**. It does not fake a security context via `mockJwt()`, because normal browser preflights carry no JWT credentials.

### 6.1. Proving Preflight Does Not Call the Backend

Combine with a backend stub and check request counts:

```text
Given:
  Stub receivedRequests = 0

When:
  OPTIONS /api/orders/42
  Origin: https://app.example.com
  Access-Control-Request-Method: GET

Then:
  Gateway returns valid CORS response
  Stub receivedRequests = 0
```

This matters: CORS preflight is normally a **gateway/web-layer decision** that should not hit Order Service. If `OPTIONS` leaks downstream, the backend may return 401/404/405 and browsers will abort the actual request.

### 6.2. Negative Preflight: Disallowed Origin

```java
@Test
void deniedOriginMustNotBeAuthorizedByCors() {
    client().options()
        .uri("/api/orders/42")
        .header(HttpHeaders.ORIGIN, "https://attacker.example")
        .header(
            HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
            "GET"
        )
        .exchange()
        .expectHeader()
            .doesNotExist(HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN);
}
```

Depending on CORS/Security implementation, the response may be 403 or another non-2xx status. The **invariant** is that browsers never receive a CORS header authorizing the disallowed origin. If `Access-Control-Allow-Origin: *` still leaks from ingress or a backend, this test catches the **wrong CORS owner**.

### 6.3. Negative Preflight: Disallowed Method or Header

Test:

```http
OPTIONS /api/orders/42
Origin: https://app.example.com
Access-Control-Request-Method: DELETE
Access-Control-Request-Headers: authorization
```

and:

```http
OPTIONS /api/orders/42
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: x-unapproved-admin-header
```

Expected: preflight must **not approve disallowed methods or headers**. Even a 200 response lacking `Access-Control-Allow-Methods: DELETE` does not authorize a browser to send `DELETE`. Assert status, headers, and zero backend calls.

### 6.4. `Method=GET` Does Not Match `OPTIONS`

A common trap:

```yaml
predicates:
  - Path=/api/orders/**
  - Method=GET
```

On preflight:

```http
OPTIONS /api/orders/42
Access-Control-Request-Method: GET
```

**The actual HTTP method is `OPTIONS`**; `Access-Control-Request-Method: GET` only declares what the browser plans to send next. Hence `Method=GET` **does not match `OPTIONS`**.

If no route matches, route-level `metadata.cors` may be skipped. Global CORS `add-to-simple-url-handler-mapping: true` is one documented approach in Gateway Server WebFlux. Tests must verify **preflight hits the right handler and returns CORS headers**, not merely that the `GET` route exists.

## 7. Actual Cross-Origin Request After Preflight

A real GET from the browser:

```http
GET /api/orders/42 HTTP/1.1
Origin: https://app.example.com
Authorization: Bearer <jwt-access-token>
```

A successful response may look like:

```http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"id":"42","state":"PAID"}
```

`Access-Control-Allow-Credentials: true` is needed for **credentialed CORS** (e.g., `credentials: 'include'`), though whether cookies or JWTs are sent depends on browser API/client config. Never infer from this response header that the Gateway authenticated anyone.

### 7.1. CORS Headers on Error Responses

Test the same `Origin` across these cases:

| Actual request | Expected auth response | Expected CORS policy |
| --- | --- | --- |
| GET without bearer | 401 (resource-server API profile) | Browser allowed to read error status if origin is valid |
| GET with bad JWT signature | 401 | Never open CORS to a disallowed origin |
| GET with valid JWT missing scope | 403 | ACAO present for allowed origin per policy |
| GET with valid JWT | 200 from backend stub | ACAO matches allowed origin |
| GET from disallowed origin | Auth may still run | No ACAO for disallowed origin |
| GET when backend returns 503 | 503/fallback per route | CORS headers not stripped by error handling |

An API may return a clean **401**, yet the frontend sees only a **"CORS error"** if ACAO is missing on error responses. Test error paths **both before and after the Gateway route chain**: Spring Security, `RateLimiter`, `CircuitBreaker`, backend, and exception handlers.

### 7.2. Never Confuse `allowedHeaders` with `exposedHeaders`

`allowedHeaders` answers:

> May the browser send **request header** `Authorization` on the actual request?

`exposedHeaders` answers:

> May JavaScript read **response header** `X-Trace-Id`?

You cannot fix a preflight rejecting `Authorization` by adding `Authorization` to `exposedHeaders`. They govern opposite directions.

### 7.3. `Vary` and Caching

Origin-specific CORS responses must respect caching semantics. If a proxy/CDN caches one response across multiple origins without honoring `Vary: Origin` (and preflight variations where applicable), clients receive wrong CORS policies.

Test:

```text
Origin A → ACAO A
Origin B → ACAO B (if allowed)
Origin C → no ACAO if disallowed
```

For user-specific APIs, also enforce `Cache-Control`/private caching rules. `Vary: Origin` **never prevents cross-user caching leaks**.

## 8. Credentialed CORS: Cookies, JWTs, and Wildcards

Browsers can issue credentialed cross-origin requests:

```javascript
fetch("https://api.example.com/api/orders/42", {
  method: "GET",
  credentials: "include"
});
```

With a matching domain/Path/SameSite session cookie, the browser attaches `Cookie` automatically. When `allowCredentials: true` is active, responses must never return wildcard `Access-Control-Allow-Origin: *` for credentialed browser reads.

### 8.1. Verify Wildcards Cannot Bypass Credential Rules

Configuration pattern to catch:

```yaml
allowedOrigins:
  - "*"
allowCredentials: true
```

This is invalid/unsafe for credentialed CORS; Spring Framework may reject or disallow this combination depending on binding/config. Tests must confirm wildcard origins **never** pair with `allowCredentials` on sensitive endpoints.

`allowedOriginPatterns` supports wildcard patterns where needed, yet patterns must be reviewed carefully: overly broad subdomain patterns can accidentally trust tenant-controlled subdomains. Prefer exact origin allowlists when the origin list is small.

### 8.2. `SameSite`/`Secure`/`HttpOnly` Are Cookie Policies, Not CORS

Verify attributes:

```http
Set-Cookie: SESSION=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=None
```

Use `SameSite=None` only when **cross-site cookies** are genuinely required, always paired with `Secure` per browser rules. Same-site apps can use `Lax`/`Strict`. Browsers may still restrict **third-party cookies** even with `SameSite=None; Secure`.

Include real browsers or browser automation whenever behavior depends on cookie policies. `WebTestClient` **does not enforce browser same-origin or third-party cookie restrictions**.

### 8.3. CORS Does Not Replace CSRF Protection

When browsers automatically attach session cookies, third-party sites can attempt state-changing requests. CORS governs whether JS reads the response—**it does not stop the request from mutating state**.

For cookie-authenticated `POST`/`PUT`/`PATCH`/`DELETE`, test:

- Missing CSRF token → blocked per policy.
- Wrong CSRF token → blocked.
- Valid CSRF token → allowed **only if authentication and authorization also pass**.
- Wrong `Origin` → CORS prevents JS from reading the response, while CSRF protection stays independently enforced.

Never disable CSRF across all routes just to make a CORS POST test pass.

## 9. JWT Resource Server: Sample Test Configuration

For APIs accepting bearer JWTs, Spring Security WebFlux uses `ReactiveJwtDecoder` to verify signatures and claims.

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/issuer
```

In production, `issuer-uri` must point to a trusted token issuer. If your backend requires a specific audience, configure **audience validation** matching your Spring Boot version or add a custom validator; never assume issuer validation implies audience validation.

### 9.1. Illustrative `SecurityWebFilterChain` for a JWT API

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ApiJwtSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

This is a **minimal security skeleton for a resource-server test profile**; it omits full CORS/CSRF, health, actuator, and multi-chain rules. Add `OPTIONS` CORS handling at the right layer as in section 5.3, or `.anyExchange().authenticated()` will reject preflights.

Spring Security normally maps JWT scopes to `SCOPE_`-prefixed authorities, though custom claim converters can change this. Tests should check **effective authorities** rather than inspecting only the raw JWT `scope` string.

### 9.2. When to Expect 401 vs. 403?

| Scenario | Typical expectation | Meaning |
| --- | --- | --- |
| No bearer token on protected API | **401** | Unauthenticated |
| Invalid/malformed/expired bearer token | **401** | Authentication failed |
| Valid JWT signature missing `orders.read` | **403** | Authenticated, insufficient authorization |
| Valid JWT with right scope, wrong object owner | **403 or 404 per backend contract** | Backend resource authorization |
| Valid JWT with right scope and permission | 200/2xx per backend | Does not prove CORS without Origin tests |
| Session-only browser hitting bearer-only route | 401 or redirect per security chain | Must match intended design |

Exact statuses can vary with custom authentication entry points or access-denied handlers; base tests on explicit contracts rather than treating 401/403/302 as interchangeable.

## 10. `mockJwt()`: Testing Permissions, Not Cryptography

Spring Security provides `SecurityMockServerConfigurers.mockJwt()` for **`WebTestClient` bound to a Spring WebFlux application context**.

### 10.1. Scope Verification Example

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

class JwtAuthorizationRulesTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void readerScopeAllowsRead() {
        client()
            .mutateWith(mockJwt()
                .jwt(jwt -> jwt.subject("user-42"))
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders.read"
                )))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void missingScopeIsForbidden() {
        client()
            .mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_profile.read"
                )))
            .get()
            .uri("/api/orders/42")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**This is a test logic template**; it requires `@SpringBootTest` (or equivalent context), security/route beans, and an upstream stub returning 200 for `readerScopeAllowsRead()` to pass. `ApplicationContext` must be injected by the test runner; copying this class alone without test config will not run.

Key traits of `mockJwt()`:

- Injects a JWT-style authentication/principal into the security context.
- Lets tests specify authorities and claims directly.
- **Requires no** signed raw JWT.
- **Never calls** JWKS/issuer endpoints to check signatures.
- Does not simulate browser preflight, OAuth2 login callbacks, or authorized-client storage.

**Therefore:** `mockJwt()` fits **authorization rules**, yet **must never be cited as proof that the JWT decoder checks `exp`, `iss`, `aud`, signing algorithms, or key rotation**.

### 10.2. Do Not Confuse `.claim("scope", ...)` with Authorities

If you write only:

```java
.jwt(jwt -> jwt.claim("scope", "orders.read"))
```

authorization results depend on how the test JWT mutator and authority converter construct `GrantedAuthority`. To keep tests explicit, specify:

```java
.authorities(
    new SimpleGrantedAuthority("SCOPE_orders.read")
)
```

Then write a **dedicated unit test** for the converter mapping `scope`/`scp`/roles so you never conflate *how claims are parsed* with *whether access rules are right*.

### 10.3. `mockJwt()` Never Uses a Real HTTP Socket

`WebTestClient.bindToApplicationContext(context)` with `springSecurity()` runs against a **mock exchange**. To test the **real HTTP listener** and JWT decoder, use:

```java
WebTestClient.bindToServer()
    .baseUrl("http://localhost:" + gatewayPort)
    .build();
```

and send a bearer token **signed by your test issuer/key**, never `mockJwt()`. This also exercises proxy headers, TLS termination in integration environments, and actual CORS responses.

## 11. Testing Real JWTs: Signatures, Issuer, Audience, and Expiration

Set up a **test authorization server/JWKS endpoint** using test keys only, or configure `ReactiveJwtDecoder` with a test public key. Real token tests must cover at least:

| Case | Token | Expectation |
| --- | --- | --- |
| Valid | Valid signature, right `iss`, right `aud`, future `exp`, sufficient scope | Allowed through Gateway |
| Bad signature | Signed with untrusted key | 401 |
| `alg=none` / disallowed algorithm | Header declares unapproved algorithm | 401 |
| Wrong issuer | `iss` differs from configured issuer | 401 |
| Wrong audience | `aud` lacks allowed API | 401 when audience validator is enabled |
| Expired | `exp` in the past | 401 |
| Not yet valid | `nbf` in the future | 401 |
| Missing scope | Valid token lacking `orders.read` | 403 |
| Key rotation | Token signed by newly published JWKS key | Follows refresh/trust policy |
| Token revocation | Token revoked before `exp` | Depends on introspection/revocation strategy |

Never fabricate fake JWTs by base64-encoding plain JSON and calling them valid access tokens. Test real cryptographic verification with test keys.

### 11.1. Testing Over Live HTTP

Skeleton:

```java
WebTestClient http = WebTestClient.bindToServer()
    .baseUrl("http://localhost:" + gatewayPort)
    .build();

http.get()
    .uri("/api/orders/42")
    .headers(headers -> headers.setBearerAuth(
        signedTestJwtWithOrdersReadScope
    ))
    .exchange()
    .expectStatus().isOk();

http.get()
    .uri("/api/orders/42")
    .headers(headers -> headers.setBearerAuth(
        signedTestJwtWithWrongAudience
    ))
    .exchange()
    .expectStatus().isUnauthorized();
```

This is a **test scaffold**; both token variables are minted by a test JWT builder/encoder and test IdP. Never commit production private keys, refresh tokens, or client secrets into test repositories.

### 11.2. Mind Audience Validation

Configuring only:

```yaml
issuer-uri: https://identity.example.test/issuer
```

does not prove your API enforces `aud` checks. On supported Spring Boot versions, enable audience validation properties or register an `OAuth2TokenValidator<Jwt>` requiring your exact audience.

**Negative tests for wrong audiences are mandatory** whenever the Gateway or Order Service authorizes API-specific access tokens. A valid token issued for another service must never be accepted everywhere.

### 11.3. Clock Skew and Test Time

`exp` and `nbf` depend on issuer and resource-server clocks. Tests should use fixed timestamps or configurable clocks/validators where supported:

- Expired past allowed clock skew → rejected.
- Not yet valid beyond skew → rejected.
- Boundary near `exp` → handled per exact policy.
- Distributed clusters keep synchronized clocks.

Never inflate allowed clock skew just to "stop test failures" if doing so lets expired tokens remain valid past policy.

## 12. WebFlux Sessions and OAuth2 Login

With OAuth2 Login, the Gateway uses **`WebSession`** to retain user state after the authorization-code callback. The browser stores a **session cookie** pointing to server-side state, and `TokenRelay` retrieves the `OAuth2AuthorizedClient` tied to the authenticated principal.

```mermaid
sequenceDiagram
    participant B as Browser
    participant G as Gateway WebFlux
    participant IDP as OIDC Provider
    participant S as Session / Authorized Client Store
    participant U as Backend
    B->>G: GET /oauth2/authorization/portal
    G-->>B: 302 to IdP with state/PKCE per client config
    B->>IDP: Login + user consent
    IDP-->>B: Redirect with authorization code
    B->>G: GET /login/oauth2/code/portal?code=...&state=...
    G->>IDP: Server-to-server token request
    IDP-->>G: Access token (+ ID token / refresh token if issued)
    G->>S: Store authenticated session + authorized client
    G-->>B: Set-Cookie: SESSION=...; redirect
    B->>G: GET /bff/orders + Cookie: SESSION=...
    G->>S: Look up session and authorized client
    G->>U: GET /orders + Authorization: Bearer access-token
    U-->>G: 200 or 401/403
    G-->>B: Response
```

This diagram is a logical model; callback paths, authorization-request repositories, PKCE, token refresh, and storage details depend on version and identity provider.

### 12.1. Never Use `mockOAuth2Login()` to Claim Real Cookies Work

Spring Security test:

```java
client.mutateWith(mockOAuth2Login())
    .get()
    .uri("/bff/orders")
    .exchange();
```

creates a synthetic OAuth2 authentication in the mock exchange and test fixtures. It helps test route authorization and principal binding, yet **proves nothing about**:

- Whether a real browser received and sent the session cookie.
- Whether authorization-code callbacks, `state`, and PKCE work.
- Whether cookies carry proper `Secure`, `HttpOnly`, `SameSite`, Domain, and Path flags.
- Whether sessions survive restarts or span Gateway replicas.
- Whether refresh tokens are stored securely and refreshed per policy.

Those require **HTTP/browser integration tests** with a test IdP and realistic session store.

### 12.2. Session Cases to Test

| Case | What to prove |
| --- | --- |
| Unauthenticated | `/bff/**` redirects to login or returns 401 per API contract |
| Successful login | Gateway establishes session; browser retains valid cookie |
| Follow-up request | Cookie resolves to authenticated session with same principal |
| Tampered cookie | Cannot hijack session or impersonate another user |
| Expired session | Old cookie cannot access protected APIs |
| Logout | Session invalidated; authorized client/token lifecycle follows policy |
| Session fixation | Attackers cannot fix session ID across login |
| CSRF | State-changing cookie requests require valid CSRF token |
| Cookie flags | `Secure`, `HttpOnly`, `SameSite`, Path/Domain accurate |
| Cross-site browser | Real browser sends cookie per policy, not just `WebTestClient` |
| Multi-replica | Login on pod A, call on pod B still resolves session if required |
| Restart | Session/authorized client persists or expires per contract |

### 12.3. A Session Cookie Is Not an Access Token

A request:

```http
GET /bff/orders HTTP/1.1
Cookie: SESSION=<opaque-session-id>
```

never means downstream should receive:

```http
Authorization: Bearer <opaque-session-id>
```

`TokenRelay` must extract the **OAuth2 access token** from the authorized-client context. Never copy `SESSION` cookies into bearer headers, and never forward raw browser cookies to backends outside the same session boundary.

## 13. `mockOAuth2Login()`, `mockOidcLogin()`, and `mockOAuth2Client()`

### 13.1. Testing OAuth2 Principals and Permissions

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;

client.mutateWith(
    mockOAuth2Login()
        .authorities(
            new SimpleGrantedAuthority("ROLE_USER")
        )
)
.get()
.uri("/bff/orders")
.exchange()
.expectStatus().isOk();
```

This template requires a test context and backend stub when the route proxies upstream; it verifies **security rules for an OAuth2 login principal**.

For OIDC users requiring ID-token claims or `OidcUser` principal types, use `mockOidcLogin()`. Still, `mockOidcLogin()` **does not prove the OIDC provider signed a real ID token or that callbacks are verified properly**.

### 13.2. Testing Authorized Clients

Test support provides:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Client;

client.mutateWith(
    mockOAuth2Client("portal")
)
.get()
.uri("/bff/orders")
.exchange();
```

It populates a mocked `OAuth2AuthorizedClient` in the mock repository for the request. You can customize tokens and client registrations through the mutator per Spring Security's test API.

**Important:** having `mockOAuth2Client("portal")` on the mock exchange **does not automatically guarantee** `TokenRelay` picks that token in an app configured with a custom `ReactiveOAuth2AuthorizedClientService` or authorization manager. Always verify the `Authorization` header on the backend stub and align test fixtures with the filter's real lookup path.

### 13.3. Avoid Overstating Mock Helper Conclusions

| Test helper | What it proves | What it does not prove |
| --- | --- | --- |
| `mockJwt()` | JWT principal/authorities for authz | Real signature/claims validation |
| `mockOAuth2Login()` | Synthetic logged-in OAuth2 principal | Real code flow or cookie persistence |
| `mockOidcLogin()` | Synthetic OIDC principal/claims | Real OIDC issuer/ID-token verification |
| `mockOAuth2Client()` | Authorized-client lookup in mock fixture | Correct `TokenRelay` token in real deployment |
| `csrf()` | CSRF rule accepts valid token | Browser cookie delivery and origin rules |

Never substitute mock test helpers for an **HTTP/browser authorization-code flow** when testing cookies, sessions, and `TokenRelay` end-to-end.

## 14. `TokenRelay`: Verifying the Real Token Is Sent Upstream

Spring Cloud Gateway Server WebFlux documentation describes `TokenRelay` as a `GatewayFilter` that extracts the authenticated user's/authorized client's **OAuth2 access token** and sets it on the outbound request header.

### 14.1. Route Configuration for Session/OAuth2 Clients

A dedicated route in the **BFF test profile**:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-bff
              uri: http://localhost:9001
              predicates:
                - Path=/bff/orders/**
              filters:
                - StripPrefix=1
                - TokenRelay=
```

`TokenRelay=` with no arguments relays the **access token tied to the OAuth2-logged-in user**. Specifying:

```yaml
filters:
  - TokenRelay=portal
```

selects the authorized client by `clientRegistrationId`. Registration `portal` must exist under `spring.security.oauth2.client.registration.*` with valid authorized-client state.

**Never assume** simply adding the filter logs users in, fetches tokens, or refreshes expired tokens on every request. You need OAuth2 client dependencies, `ReactiveClientRegistrationRepository`, authorized-client infrastructure, and a valid login session.

### 14.2. Dependencies and Stores

Using `TokenRelay` in Gateway Server WebFlux typically requires:

```text
spring-boot-starter-oauth2-client
spring.security.oauth2.client.registration.portal.*
spring.security.oauth2.client.provider.portal.*
```

Per Gateway docs, `TokenRelayGatewayFilterFactory` is created only when OAuth2 client properties produce a **`ReactiveClientRegistrationRepository`**. Docs also note that the default `ReactiveOAuth2AuthorizedClientService` may use an **in-memory store**; multi-pod deployments or restarts requiring durable token storage need a shared repository.

### 14.3. Verifying the Exact Header at the Backend

Test with a **backend stub** (not production) receiving:

```http
GET /orders/42 HTTP/1.1
Host: localhost:9001
Authorization: Bearer FAKE_TEST_ACCESS_TOKEN
```

Mandatory assertions:

1. `Authorization` carries **exactly one bearer value** per contract.
2. That bearer value equals the **chosen authorized client's access token**.
3. Never substituted with an OIDC ID token.
4. Gateway's `SESSION` cookie never leaks to backends outside the session boundary.
5. Client-supplied inbound `Authorization` cannot override `TokenRelay` against policy.
6. Route `StripPrefix` produces the right path.
7. Backend resource server validates the token's **audience, scopes, and ownership**, not merely token presence.
8. When tokens are missing, expired, or fail refresh, requests never silently fall back to wrong credentials.

**This verifies token forwarding**, unlike `mockJwt()` tests which only check Gateway-level authorities.

### 14.4. What If No Access Token Is Available?

Negative cases to cover:

```text
Anonymous user
Expired session
Logged-in principal missing OAuth2AuthorizedClient
Wrong clientRegistrationId
Authorized client with expired access token
Invalid refresh token
Token audience mismatched with backend
OAuth2 client store unavailable
```

Exact outcomes may be login redirects, 401/403, error responses, or relay refusal depending on config—**never falling back to an arbitrary client bearer token or another user's credential**. Backend stubs and redacted logs must prove this.

### 14.5. Resource Server Bearer JWT vs. OAuth2 Login Token

When an incoming request sends:

```http
Authorization: Bearer <jwt>
```

Spring Security's resource server produces a `JwtAuthenticationToken`. However, `TokenRelay` tied to **OAuth2 Client/authorized clients** must not be assumed to forward raw JWTs in every configuration simply because the current `Authentication` holds a JWT. Docs cover both client and resource-server use cases, yet exact token resolution depends on version, filters, registrations, and security context.

If you need **JWT passthrough** from public clients downstream, design and test that relay/forwarding policy and token audience explicitly. Never treat OAuth2-login `TokenRelay` as a generic `Authorization`-copying filter.

## 15. Testing `TokenRelay` with a Mocked Authorized Client and HTTP Stub

Application-context test plan:

```text
Given:
  User logged in via OAuth2 mock principal
  Authorized client "portal" holds access token = FAKE_ACCESS_A
  Route /bff/orders/** includes TokenRelay
  Backend stub listens on /orders/**

When:
  GET /bff/orders/42

Then:
  Backend receives GET /orders/42
  Backend Authorization = Bearer FAKE_ACCESS_A
  Backend receives no browser SESSION cookie
  Gateway returns expected body/status
```

`WebTestClient` scaffold:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Client;

// webTestClient: bindToApplicationContext + apply(springSecurity())
// backendStub: HTTP server injected at test route URI.
webTestClient
    .mutateWith(mockOAuth2Login())
    .mutateWith(mockOAuth2Client("portal"))
    .get()
    .uri("/bff/orders/42")
    .exchange()
    .expectStatus().isOk();

// Assert on backendStub:
// path "/orders/42", Authorization bearer token matches fixture.
```

This is a **test scaffold**, not a complete suite: you must configure `ClientRegistration`, register a test authorized-client repository per version, and match `TokenRelay`'s lookup path. `mockOAuth2Client()` provides a default test token; if asserting exact token strings, **set an explicit test access token** via the builder API and verify it on the backend stub.

### 15.1. Attaching an Explicit Access Token to the Fixture

```java
import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

OAuth2AccessToken accessToken = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "FAKE_ACCESS_TOKEN_FOR_STUB",
    Instant.now().minusSeconds(10),
    Instant.now().plusSeconds(300),
    Set.of("orders.read")
);

// With mockOAuth2Client("portal"):
//   .accessToken(accessToken)
// then assert backend receives this exact bearer token.
```

This synthetic token is strictly for **stub HTTP tests**. A backend Resource Server verifying real JWT signatures will reject `"FAKE_ACCESS_TOKEN_FOR_STUB"`, which is not a `TokenRelay` bug. Keep three tests distinct:

- **Relay test:** compare outbound header against fixture token.
- **JWT signature test:** use a test-issuer-signed JWT against a real test resource server.
- **OAuth2 code flow test:** use a test IdP with real browser/session/callback steps.

### 15.2. Verify ID Tokens Are Never Sent by Mistake

OIDC login produces:

```text
id_token:     OIDC identity assertion for the Gateway client
access_token: OAuth2 token for calling resource APIs
```

The backend stub must receive the **access token**, never the ID token—a frequent bug when developers hand-roll header relays from the authenticated principal.

### 15.3. Never Log Secrets in Tests

On assertion failures, never print full `RecordedRequest` objects or raw HTTP headers to CI logs if real tokens could be present. Use **synthetic** tokens or assert boolean flags:

```text
hasAuthorizationHeader = true
isBearerScheme          = true
matchesExpectedTestToken = true
```

without dumping sensitive values on failure. Production telemetry needs only relay outcome (`present`, `missing`, `rejected`) and trace IDs, never token strings.

## 16. Testing Real OAuth2 Authorization Code Flows and Sessions

To verify callbacks, cookies, and state, run a **test OIDC provider** or mock authorization server exposing real endpoints:

```text
/.well-known/openid-configuration
/authorize
/token
/jwks
```

Use **test client registrations**, redirect URIs, and signing keys owned by the test suite. Never route automated browser tests through a production identity provider without explicit authorization.

### 16.1. E2E Steps to Prove

1. Unauthenticated browser visits `/bff/orders/42`.
2. Gateway redirects to `/oauth2/authorization/portal` or the identity provider per flow.
3. Authorization request includes unpredictable `state`, contract parameters, and PKCE if required/supported.
4. Test IdP returns authorization code and matching `state`.
5. Gateway exchanges the code at the token endpoint with proper client authentication.
6. Gateway validates `state`, issuer, OIDC ID-token claims, and `nonce` where applicable.
7. Gateway establishes an authenticated session and sets cookie with security flags.
8. Browser sends that cookie on the next `/bff/orders/42` request.
9. Gateway looks up the authorized client and `TokenRelay` sends the access token to the backend.
10. Logout/session invalidation leaves subsequent requests unauthenticated.

**Steps 3–6 are never proven simply because `mockOAuth2Login()` creates a principal.** Run the actual protocol over HTTP.

### 16.2. Cookie Attributes

Example expected header (deployment-dependent):

```http
Set-Cookie: SESSION=<opaque>; Path=/; HttpOnly; Secure; SameSite=Lax
```

Verify:

- Cookies never contain raw access or refresh tokens.
- `HttpOnly` is set when JS should not read the session ID.
- `Secure` is set for production HTTPS.
- `SameSite` fits login callbacks and cross-site requirements.
- Domain/Path never widen cookies across unnecessary hosts.
- Session fixation mitigation runs at login.
- Credentials are never pushed into browser `localStorage` to paper over session issues.

**Note:** OAuth2 redirects/callbacks and cross-site deployments impose specific `SameSite` requirements. Never hardcode `Strict`/`None` blindly; test against your real browser/IdP topology.

### 16.3. Session Stores Across Multiple Gateway Replicas

When running multiple Gateway pods:

```text
Browser ── cookie ──▶ Gateway A: login
Browser ── cookie ──▶ Gateway B: /bff/orders/42
```

verify that both **`WebSession` state** and **`OAuth2AuthorizedClient` state** are readable on pod B when required. An in-memory repository on pod A **will not** share state with pod B even if both share Redis for something else.

Test:

- Log in via A, then call B with the same cookie.
- Restart A and call B.
- Verify consistent session expiry and revocation.
- Verify OAuth2 client access/refresh tokens are protected/encrypted per policy.
- Verify fail-closed policy when the session store is unavailable—never assign another user's session.

## 17. CSRF with Sessions: Never Mix with Stateless JWT Tests

When browsers automatically attach **BFF session cookies**, state-changing routes such as:

```http
POST /bff/orders
Cookie: SESSION=...
```

require a matching CSRF strategy. Spring Security reactive tests provide:

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

client.mutateWith(mockOAuth2Login())
    .mutateWith(csrf())
    .post()
    .uri("/bff/orders")
    .exchange();
```

`csrf()` injects a valid test CSRF token in the **mock `WebTestClient` context**; it does not test whether a real browser extracts and sends CSRF cookies/headers properly.

### 17.1. Negative CSRF Tests

| Request | Authentication | CSRF token | Expectation |
| --- | --- | --- | --- |
| GET `/bff/orders` | Valid session cookie | None | Allowed per read policy |
| POST `/bff/orders` | Valid session cookie | None | Rejected when CSRF protection applies |
| POST `/bff/orders` | Valid session cookie | Invalid | Rejected |
| POST `/bff/orders` | Valid session cookie | Valid | Proceeds to authz/business checks |
| POST `/bff/orders` | Not logged in | Valid | Never treated as authenticated just for having CSRF |
| Cross-origin POST | Cookie + different Origin | Varies | Must satisfy CORS, CSRF, and authz together |

For **bearer-only APIs** without browser-attached credentials, the CSRF threat model differs. Separate security chains/profiles appropriately, and **never disable CSRF across the entire Gateway** just to make a POST test pass.

## 18. Integration Suites Require a Backend Stub

A common mistake is writing:

```java
client.get().uri("/api/orders/42")
    .exchange()
    .expectStatus().isOk();
```

with **no upstream stub**, or a backend returning 200 for every path. You then know nothing about post-`StripPrefix` paths, outbound auth headers, or actual URIs sent.

### 18.1. Stub Design

An HTTP stub (MockWebServer/WireMock) should record:

```text
method
path
request headers (in test memory; never print secrets)
body (synthetic only)
request count
test-controlled response status/body
```

Include fixtures:

```text
GET /orders/42 → 200 {"id":"42"}
GET /orders/99 → 403 (backend denies object)
GET /orders/503 → 503
POST /orders → 201
```

### 18.2. Dynamic Route URIs from Random Backend Ports

When the backend stub binds a random port, inject its URI into the Spring test context via **dynamic properties** instead of hardcoding `localhost:9001`:

```java
// Test setup pseudocode:
// 1. Start HTTP backend stub before Spring context binds properties.
// 2. Capture backendBaseUrl = "http://127.0.0.1:<random-port>".
// 3. @DynamicPropertySource registers the orders route URI.
// 4. @SpringBootTest(RANDOM_PORT) starts the Gateway.
// 5. WebTestClient.bindToServer() calls the local Gateway port.
// 6. Assert the backend stub received the exact request.
```

The route property in the sample config may be:

```text
spring.cloud.gateway.server.webflux.routes[0].uri
```

This works only when the test profile actually places that route at index 0 and Spring Boot's binder applies the override. With multiple routes, inject placeholders in test YAML or define a test `RouteLocator` bean. Never push indexed property overrides into production without understanding route ordering and config merging.

### 18.3. Auth Failure Tests Must Never Call the Backend

Example case:

```text
Given:
  Stub request count = 0

When:
  GET /api/orders/42, no bearer token

Then:
  Gateway responds 401
  Stub request count = 0
```

Likewise, a valid JWT missing `orders.read` → 403 with **zero outbound requests**. If the backend still gets called, check security filter matchers or route bypasses.

### 18.4. Testing `TokenRelay` on the Right Hop

For BFF:

```text
Client → Gateway:
  Cookie: SESSION=<opaque>

Gateway → Backend:
  Authorization: Bearer <access token>
```

Test all of:

- Never forward `SESSION` cookies unintentionally.
- Never log access tokens in wiretap/debug headers.
- Spoofed client `Authorization` headers are overwritten per policy.
- Backend returns 401 when access token audience/scope is wrong.
- Expired sessions or missing authorized clients never reuse another request's stale token.

### 18.5. Retries Must Never Leak or Duplicate Tokens

Retries create multiple outbound attempts. When a `TokenRelay` route sits inside a retrying filter chain, verify how requests replay and which token accompanies each attempt.

For POSTs, enforce **idempotency keys** and backend deduplication; test:

```text
One inbound POST
→ Gateway attempts 1..N per policy
→ Backend executes business logic exactly once
```

Never enable unbounded retries or mint uncontrolled tokens per attempt. Auth errors like 401 should not be retried like transient 502 network failures.

## 19. Comprehensive Test Matrix

| # | Group | Test input | Primary assertion |
| --- | --- | --- | --- |
| 1 | Preflight | Allowed origin, GET, `Authorization` | 2xx and expected ACAO/ACAM/ACAH |
| 2 | Preflight | Disallowed origin | No ACAO for disallowed origin |
| 3 | Preflight | Disallowed `DELETE` method | `DELETE` not permitted |
| 4 | Preflight | `X-Admin-Override` header | Unapproved header not permitted |
| 5 | Preflight | Route `Method=GET`, `OPTIONS` request | Global fallback/handler responds |
| 6 | Preflight | `OPTIONS` with fake cookie | CORS decides without user credentials |
| 7 | Preflight | Repeated `OPTIONS` | `maxAge` cache headers match policy |
| 8 | CORS actual | GET from allowed origin | ACAO matches origin |
| 9 | CORS actual | GET from denied origin | No wrong ACAO emitted |
| 10 | CORS actual | Backend 503 | Error path preserves CORS policy |
| 11 | CORS actual | Security 401 | Browser allowed to read error response for valid origin |
| 12 | CORS | `allowCredentials=true` | No illegal wildcard ACAO |
| 13 | CORS | Exposed `X-Trace-Id` | Browser JS allowed to read header |
| 14 | CORS | `Authorization` request header | In `allowedHeaders`; not confused with `exposedHeaders` |
| 15 | JWT | Missing bearer token | 401; backend receives no request |
| 16 | JWT | Malformed token | 401 |
| 17 | JWT | Bad signature/alg | 401 |
| 18 | JWT | Wrong issuer | 401 |
| 19 | JWT | Wrong audience | 401 when validator configured |
| 20 | JWT | Expired `exp` | 401 |
| 21 | JWT | Future `nbf` | 401 |
| 22 | JWT | Valid token, missing scope | 403; backend not called |
| 23 | JWT | Valid scope | Backend receives expected path/request |
| 24 | JWT | Custom scope converter | Expected `GrantedAuthority` produced |
| 25 | Session | Login redirect/callback | State/nonce/PKCE and token exchange valid |
| 26 | Session | Post-login cookie | `Secure`/`HttpOnly`/`SameSite`/`Path` accurate |
| 27 | Session | Follow-up request with cookie | Authenticated principal restored |
| 28 | Session | Forged/expired cookie | Access denied |
| 29 | Session | Logout | Session and BFF access revoked |
| 30 | Session | POST missing CSRF | Denied when session CSRF applies |
| 31 | Session | POST with valid CSRF | Proceeds to authz/business checks |
| 32 | Session | Login on Pod A → request on Pod B | Session and authorized client preserved |
| 33 | `TokenRelay` | Valid OAuth2 authorized client | Backend receives right access token |
| 34 | `TokenRelay` | Missing authorized client | Never relays another user's credential |
| 35 | `TokenRelay` | Wrong registration ID | Never pulls wrong registration's token |
| 36 | `TokenRelay` | Expired token | Refreshes or errors per policy; no stale token |
| 37 | `TokenRelay` | Distinct OIDC ID token & access token | Relays access token, never ID token |
| 38 | `TokenRelay` | Client spoofs `Authorization` | Never overrides relay against policy |
| 39 | `TokenRelay` | Backend rejects audience | Backend 401 and clean error handling |
| 40 | Privacy | Synthetic tokens in requests | Logs/traces store zero tokens |
| 41 | Routing | CORS/JWT pass + `StripPrefix=1` | Backend receives expected path |
| 42 | Resilience | `CircuitBreaker` open | Zero outbound calls; CORS/error intact |
| 43 | Resilience | `Retry` after 503 | Attempt count verified; idempotency protected |
| 44 | Network | CORS via ingress/TLS | No duplicate ACAO or proxy-header bypass |

### 19.1. Prioritizing by Risk

If your team cannot automate all 44 cases immediately, prioritize this minimum set:

1. `OPTIONS` preflight for allowed origin/method/headers **succeeds**.
2. Preflight is rejected for **wrong origins and methods**.
3. Actual GET carries CORS headers on **200, 401, and 403**.
4. JWT tests for **missing, bad signature, wrong issuer/audience, expired, and missing scope**.
5. Session **login, cookies, CSRF, and logout**.
6. `TokenRelay` delivers the right access token to the **backend stub** without leaking cookies.
7. Multi-replica session/authorized-client state if production runs multiple pods.
8. Logs and traces contain zero bearer tokens, cookies, or client secrets.

This forms the baseline regression suite to catch common CORS failures and security bypasses.

## 20. Troubleshooting by Symptom

### 20.1. Browser Reports CORS Error While `curl` Gets 200

Causes:

- Browser sent an `OPTIONS` preflight first; `curl` hit GET directly.
- GET response lacks ACAO or fails to expose a needed response header.
- Origin/port/scheme mismatch.
- Gateway/Security/ingress emit conflicting CORS headers.

**Fix:** reproduce exact `OPTIONS` with `Origin`, `Access-Control-Request-Method`, and `Access-Control-Request-Headers`, followed by actual GET with `Origin`. Check browser Network tab to see which request failed.

### 20.2. `OPTIONS` Returns 401

Likely cause: Spring Security intercepted preflight as an API call needing a bearer token before CORS ran, or the request lacked preflight headers so it was not recognized as preflight.

**Fix:** ensure the CORS handler runs before authentication or `OPTIONS` passes the security chain appropriately; remember `Method=GET` routes do not match `OPTIONS`. **Never** make actual GET endpoints public just to fix `OPTIONS`.

### 20.3. `OPTIONS` Returns 404 Even Though GET Matches

Likely cause: the route specifies `Method=GET`, preflight's HTTP method is `OPTIONS`, and route-level metadata did not apply.

**Fix:** enable global CORS `add-to-simple-url-handler-mapping: true` or equivalent CORS mapping, and test against the right route path.

### 20.4. Preflight Returns 200, Yet GET Returns 401

This **can be completely valid**: CORS lets the browser send GET, while JWT authentication checks the token independently.

Inspect the actual `Authorization` header, JWT decoder errors, and audience/scope settings. Never assume preflight approving a method authorizes the user's data access.

### 20.5. GET Returns 403 Despite a Valid JWT

Likely causes:

- JWT lacks `SCOPE_orders.read` authority.
- `scope` claim mapped unexpectedly.
- Backend denied object ownership/tenant access.
- CSRF blocked a state-changing session request.

**Fix:** determine whether 403 originated at the **Gateway or backend**, inspect effective authorities safely (without printing tokens), and review security filters.

### 20.6. `mockJwt()` Passes, Yet Real JWT Gets 401

No contradiction here. `mockJwt` bypasses cryptographic decoding. Real decoders reject:

```text
signature / kid / JWKS
iss / aud / exp / nbf
algorithm
issuer discovery/network
```

**Fix:** add JWT validation integration tests signed with test keys/JWKS.

### 20.7. OAuth2 Login Test Passes, Yet Browsers Drop the Session

`mockOAuth2Login` does not test real cookies. Check for:

- Wrong `Domain`/`Path`/`SameSite`/`Secure`.
- Third-party cookie blocks.
- Wrong redirect host/proto from untrusted proxy headers.
- In-memory session store across multiple Gateway pods.

**Fix:** run browser E2E through realistic HTTPS ingress, inspect `Set-Cookie`/callbacks/`state`, and never log real session IDs.

### 20.8. OAuth2 Callback Gets 403 / Invalid State

Likely causes:

- State/correlation cookie or `WebSession` not sent back.
- Inconsistent session affinity or session store.
- Wrong external redirect URI/scheme/host.
- Expired/replayed `state`, or PKCE/OIDC `nonce` mismatch.

**Fix:** test a real authorization-code flow with a test IdP across multiple replicas if clustered. Never disable `state` validation "to get login working".

### 20.9. `TokenRelay` Filter Is Not Created

Likely causes: missing OAuth2 Client dependency, registration properties failing to create `ReactiveClientRegistrationRepository`, wrong Gateway edition/namespace, or unrecognized filter name.

**Fix:** inspect runtime beans/routes, dependencies, and version-matched docs. Never hardcode `Authorization` in route YAML.

### 20.10. Gateway Is Authenticated, Yet Backend Returns 401

Likely causes:

- Authorized client lacks an access token.
- Gateway did not apply `TokenRelay` on the matched route.
- Backend received a token with the wrong audience, issuer, or expired timestamp.
- `TokenRelay` pulled a token from a different registration.
- Request carried a session cookie with no OAuth2 authorized client.

**Fix:** verify **header presence and test token identity** on the backend stub, then test backend JWT validation separately. Never substitute session cookies or ID tokens as bearer credentials.

### 20.11. `TokenRelay` Passes on One Pod, Fails on Another

Likely cause: in-memory `ReactiveOAuth2AuthorizedClientService` or `WebSession` state is not shared across pods.

**Fix:** test multi-pod session/authorized-client persistence and store connectivity; define failure policies for store outages and protect refresh token secrets.

### 20.12. CORS Returns 200, Yet Browser Reports a Credential Error

Likely causes:

- `Access-Control-Allow-Origin: *` paired with `credentials: include`.
- Missing `Access-Control-Allow-Credentials: true`.
- Browser blocked cookies due to `SameSite`/`Secure`/third-party rules.
- Duplicate ACAO headers emitted by multiple layers.

**Fix:** inspect actual wire headers and browser cookie rules rather than trusting status 200 or `WebTestClient` cookie jars alone.

## 21. Protecting Test Data and Telemetry

CORS/JWT/session/`TokenRelay` tests easily leak **secrets into logs** if raw request/response headers are printed.

### 21.1. Data That Must Never Be Logged

```text
Authorization: Bearer ...
Cookie: SESSION=...
Set-Cookie: SESSION=...
Refresh token
Raw ID token / Access token
OAuth2 authorization code
Client secret
?code=...&state=...&access_token=...
```

Even with a backend stub, avoid dumping full recorded requests on assertion failures. Log only:

```text
routeId=orders-bff
authenticated=true
relayTokenPresent=true
relayTokenMatchedTestFixture=true
status=200
traceId=<synthetic-trace-id>
```

### 21.2. Test with Synthetic Markers

Use:

```text
FAKE_ACCESS_TOKEN_FOR_STUB
FAKE_SESSION_ID
FAKE_REFRESH_TOKEN
FAKE_CLIENT_SECRET
```

After tests run, you can assert that a **test-specific log sink** contains none of those markers in structured operational logs. Still, a clean local logger does not prove Netty wiretap, ingress, APM, or CI systems are clean; audit every collector in your deployment scope.

### 21.3. Never Enable Wiretap DEBUG on Real Traffic

`httpclient/httpserver.wiretap` logs HTTP payloads before and after transformations—including tokens and cookies. When debugging, use synthetic traffic in an isolated namespace and disable wiretap once evidence is collected. TLS protects transport on the wire, **not raw entries in application logs**.

### 21.4. Preventing Time- and Environment-Driven Flakes

- Use random ports and independent backend stubs.
- Enforce bounded deadlines/timeouts; avoid fixed `Thread.sleep()` calls.
- Use deterministic JWT timestamps/test clocks or deliberate clock-skew limits.
- Give every test its own session/authorized client; never share state across test methods.
- Never rely on external DNS/IdPs during CI unit/integration runs.
- Never store session cookies/tokens in shared static fixtures that leak across tests.
- Never assume test execution order when sharing a backend stub queue.

## 22. Suggested Practice Labs

### Exercise 1 — Testing Preflight with a `Method=GET` Route

1. Declare route `Path=/api/orders/**`, `Method=GET`.
2. Enable global CORS with an exact origin and `add-to-simple-url-handler-mapping: true`.
3. Send `OPTIONS` from the allowed origin requesting method `GET` and header `authorization`.
4. Assert CORS headers and zero backend calls.
5. Request method `DELETE` and assert it is not authorized.
6. Disable `add-to-simple-url-handler-mapping` in a test profile and observe behavior; explain **why `Method=GET` does not match `OPTIONS`**.

### Exercise 2 — JWT Authorization

1. Use `mockJwt` with `SCOPE_orders.read`; verify GET succeeds.
2. Use `mockJwt` with `SCOPE_profile.read`; verify GET returns 403.
3. Omit auth mocking; verify GET returns 401.
4. Mint a real JWT signed with a test key; test valid issuer/audience/expiry.
5. Mint a JWT with wrong `aud`/signature; verify 401.
6. Compare what the mock test proved vs. the validation test.

### Exercise 3 — Sessions and CSRF

1. Use `mockOAuth2Login` to verify `/bff/**` security rules.
2. Verify POST without `csrf()` is denied under the session profile.
3. Verify POST with `csrf()` proceeds.
4. Run a real test-IdP OAuth2 flow checking `state`, cookies, and logout.
5. Replay with an expired cookie and across a second pod.

### Exercise 4 — `TokenRelay`

1. Declare route `/bff/orders/**` with `TokenRelay`.
2. Set up authorized client `portal` with a synthetic access token.
3. Verify bearer header and path on the backend stub.
4. Test principal missing authorized client, wrong `clientRegistrationId`, and expired token.
5. Test an OIDC login fixture with distinct ID and access tokens; verify only the access token goes downstream.
6. Verify against a real backend Resource Server using the test JWT issuer.

### Exercise 5 — Browser Cross-Origin End-to-End

1. Host a test SPA at `https://app.example.test`.
2. Run the test API Gateway at `https://api.example.test`.
3. Test `fetch` with an `Authorization` header and preflight.
4. Test session cookies with `credentials: 'include'` per `SameSite` policy.
5. Test a disallowed origin and inspect browser console/Network tab.
6. Verify 401/403/503 error responses still include matching CORS headers.

## 23. Self-Practice Questions and Answers

1. **Must CORS preflight carry the same bearer JWT as the actual GET?**  
   No; preflights should never depend on actual-request credentials. CORS processing should run ahead of the auth gate per policy.

2. **Does `Access-Control-Request-Method: GET` turn the HTTP method of `OPTIONS` into `GET`?**  
   No. The actual method remains `OPTIONS`; a `Method=GET` route predicate does not match `OPTIONS`.

3. **Is it contradictory when GET returns 200 in `curl` while the browser reports a CORS error?**  
   No. Browsers also run preflight and enforce CORS response headers.

4. **Does `allowCredentials: true` automatically create cookies?**  
   No. It only configures the CORS policy; cookies, sessions, and browser policies belong to separate layers.

5. **Can `allowedOrigins: '*'` be used with credentialed browser requests?**  
   No under valid credentialed CORS rules; the response must echo a specific allowed origin.

6. **Does `mockJwt()` verify RSA signatures?**  
   No. It injects a synthetic authentication for authorization testing.

7. **Should a validly signed JWT with the wrong `aud` be accepted?**  
   No if the API requires that audience; configure an audience validator and write negative tests.

8. **Does a JWT missing a required scope return 401 or 403?**  
   Normally 403, because authentication succeeded while authorization was insufficient.

9. **Does `mockOAuth2Login()` prove `Secure` cookies and Redis sessions work?**  
   No. You need real HTTP/browser and distributed integration tests.

10. **Is a session ID cookie an OAuth2 access token?**  
    No. Session IDs reference server state, whereas access tokens authorize resource APIs by audience and scope.

11. **Should `TokenRelay` send an ID token down to the Order Service?**  
    No. Resource servers expect an access token per contract.

12. **If the backend returns 401 even though the user logged into the Gateway, is that a CORS bug?**  
    Not necessarily. Relay may be missing, audience may mismatch, or the backend may not trust that access token.

13. **If `TokenRelay` works on Pod A but fails on Pod B, what should you inspect?**  
    `WebSession` and `ReactiveOAuth2AuthorizedClientService` persistence, plus routing/session affinity if used.

14. **Why test CORS on 401/403 responses?**  
    Browsers require matching CORS headers for frontend code to read error responses; requests may also fail ahead of the route chain.

15. **Does `Access-Control-Allow-Headers` containing `Authorization` let JS read `X-Trace-Id`?**  
    No. Reading response headers requires `Access-Control-Expose-Headers`.

16. **Can CORS replace CSRF protection?**  
    No. CSRF protects state-changing actions when browsers auto-send credentials; CORS governs JS reads of cross-origin responses.

17. **Does `mockOAuth2Client()` prove `TokenRelay` picks the right registration?**  
    No. Assert the outbound `Authorization` header on a backend stub and confirm the real authorized-client lookup.

18. **Why avoid logging JWTs when tests fail?**  
    JWTs, refresh tokens, and session IDs are credentials. Use synthetic tokens and assertions that never print raw values.

19. **Does a 200 preflight prove the backend received the GET?**  
    No. Preflight is a separate request; the actual GET must still be sent and clear auth/routing.

20. **Should you blanket-enable `permitAll` for all `OPTIONS` requests?**  
    Not by default. Define a clear CORS policy and security scope so preflight is handled at the right layer.

## 24. Pre-CI/CD Checklist

- [ ] Using **Spring Cloud Gateway Server WebFlux**, not confused with Web MVC/Servlet?
- [ ] `spring.cloud.gateway.server.webflux.*` or legacy namespace verified for your version?
- [ ] **Resource-server JWT** tests separated from **OAuth2 Login/session BFF** profiles or chains?
- [ ] Single clear CORS owner, with no duplicate ACAO from Gateway/Security/ingress/backend?
- [ ] `OPTIONS` preflight for allowed origin/method/headers succeeds without requiring a JWT?
- [ ] Tested that `Method=GET` predicates do not match `OPTIONS` and global fallback handles it?
- [ ] Actual requests tested from allowed/denied origins, including on 401/403/503?
- [ ] With credentialed CORS, ACAO echoes the exact allowed origin rather than `*`?
- [ ] `allowedHeaders` and `exposedHeaders` tested in their respective directions?
- [ ] Tested CORS response caching, `Vary`, and browser cookie restrictions?
- [ ] JWT tests cover missing token, signature, issuer, audience, expiry, `nbf`, and algorithms?
- [ ] Scope converter/authority mapping tested, distinguishing 401 from 403?
- [ ] `mockJwt` tests are never labeled as cryptographic validation tests?
- [ ] Session tests cover cookie flags, login, CSRF, logout, expiry, and fixation?
- [ ] Auth-code callback/`state`/PKCE/`nonce` tested when using OAuth2/OIDC Login?
- [ ] `WebSession` and OAuth2 authorized clients tested across multiple replicas if clustered?
- [ ] `TokenRelay` route matches cleanly and backend stub receives the exact access token?
- [ ] ID tokens, session cookies, and other users' credentials never forwarded against policy?
- [ ] Missing/expired authorized clients handled safely with no silent fallback?
- [ ] Backend still validates JWT audience, scopes, and object/tenant ownership?
- [ ] Synthetic tokens/test keys used; zero client secrets or prod JWTs stored in CI?
- [ ] Raw `Authorization`, `Cookie`, `Set-Cookie`, OAuth2 codes, or refresh tokens never logged?
- [ ] Backend stub records path/method/headers/count without exposing secrets?
- [ ] Tests are deterministic with random ports, bounded timeouts, and isolated per-test state?
- [ ] Browser E2E over TLS/ingress included for CORS/cookie redirects where needed?
- [ ] Regression matrix covers `Retry`/`CircuitBreaker`/security errors alongside CORS headers?

## 25. Official References

- [Spring Cloud Gateway Server WebFlux — CORS Configuration](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/cors-configuration.html): global/route CORS metadata and `add-to-simple-url-handler-mapping`.
- [Spring Cloud Gateway Server WebFlux — `TokenRelay` GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html): OAuth2 access token relay, `clientRegistrationId`, authorized-client store.
- [Spring Cloud Gateway — Configuration Properties](https://docs.spring.io/spring-cloud-gateway/reference/configprops.html): namespaces and properties per Gateway release train.
- [Spring Security WebFlux — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt`, `mockOAuth2Login`, `mockOidcLogin`, `mockOAuth2Client`.
- [Spring Security WebFlux — Testing with CSRF](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html): `WebTestClient.mutateWith(csrf())`.
- [Spring Security WebFlux — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): JWT decoder, issuer, signatures, scopes/authorities, and validation.
- [Spring Security — CORS Integration](https://docs.spring.io/spring-security/reference/reactive/integrations/cors.html): ensuring CORS runs before Spring Security.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): mock-context and server-bound tests.

## Summary

Testing **CORS, preflight, JWT, session, and `TokenRelay`** must mirror the real boundaries inside **Spring Cloud Gateway Server WebFlux**. **`OPTIONS` preflight** tests browser cross-origin access, **not JWT authentication**; a `Method=GET` route predicate never matches `OPTIONS` despite `Access-Control-Request-Method: GET`. **JWT tests** must separate authorization checks via `mockJwt()` from signature/issuer/audience/expiry checks using real signed tokens and a test JWKS. **Session/OAuth2 Login tests** must separate mocked principals from real browser cookies, callbacks, CSRF, logout, and multi-replica persistence. **`TokenRelay` tests** must use an upstream stub to prove the Gateway sends the **right OAuth2 access token**, never confusing it with an ID token or session cookie.

A valuable suite does more than assert `200 OK`: it verifies **`OPTIONS` and actual response headers**, **401/403 from the right source**, **zero upstream calls when blocked**, **accurate paths and `Authorization` headers reaching the backend**, **session lifecycles**, and **zero credential leaks in test logs**. Combining tiered tests, synthetic fixtures, targeted browser E2E, and negative matrices keeps Gateway routing, auth, access control, and token relaying safe and verifiable in CI/CD.
