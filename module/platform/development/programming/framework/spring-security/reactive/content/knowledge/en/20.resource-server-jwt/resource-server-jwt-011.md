# Handling Missing, Malformed, Expired, or Insufficient-Scope Tokens — Spring Security Reactive JWT Resource Server

## 1. Context and Objectives

A **Spring WebFlux** application acting as an **OAuth2 Resource Server** does not issue access tokens and does not sign users in on behalf of the Authorization Server. It receives HTTP requests, extracts Bearer tokens, verifies tokens, and decides whether the caller may act on the resource. For example:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
~~~

At least four distinct errors must be separated:

1. **Missing token:** request to a protected endpoint without Bearer authentication.
2. **Malformed or invalid format:** `Authorization` header violates Bearer syntax rules, or a string accepted as a token is rejected by the JWT parser/signature validator.
3. **Expired or not-yet-valid token:** `exp` has passed, `nbf` is in the future, or the token fails other claim validators such as `iss` and `aud`.
4. **Valid token with insufficient scope:** authenticated successfully, yet lacks the `GrantedAuthority` required for the endpoint.

These typically correspond to **401**, **400/401**, **401**, and **403**, though you must understand **which layer raised the error** instead of guessing status codes solely from “invalid JWT”.

After this lesson, you will:

- Understand the Reactive flow `ServerBearerTokenAuthenticationConverter` → `JwtReactiveAuthenticationManager` → `ReactiveJwtDecoder` → `JwtAuthenticationToken` → authorization.
- Distinguish `BearerTokenServerAuthenticationEntryPoint` and `BearerTokenServerAccessDeniedHandler` per **RFC 6750**.
- Configure signature checking, trusted JWK Set, `iss`, `aud`, `exp`, `nbf`, and scope mapping.
- Build a **Java 17+ / Spring Boot 3.x / Spring Security 6.x** example with GET/POST endpoints requiring different scopes.
- Test 401/403 and `WWW-Authenticate` with `WebTestClient`, distinguishing `mockJwt()` from real decoder validation.
- Diagnose clock skew, key rotation, API audience, bearer request syntax, CORS/CSRF, and infrastructure errors.

> **Scope:** Reactive stack using `ServerHttpSecurity` and `SecurityWebFilterChain`. Do not copy Servlet MVC `HttpSecurity` or `BearerTokenAuthenticationFilter` code into WebFlux apps. The OAuth2 Client requests tokens, the Authorization Server issues tokens, and the Resource Server **consumes and verifies** Bearer tokens.

## 2. Two Gates: Authentication First, Authorization Second

**Authentication:** Is a token present, does it match Bearer format, does the JWT have a valid signature, was it issued by a trusted issuer, and is it currently valid? If it fails, no authenticated `Authentication` may be created.

**Authorization:** Does a valid `Authentication` have the right authority/scope for the action? Does the resource belong to this principal or tenant? If permission is lacking, deny even if the JWT is genuine, unexpired, and validly signed.

Sample API policy:

~~~text
GET  /public/ping   → public
GET  /api/profile   → requires authenticated JWT
GET  /api/orders    → requires SCOPE_orders.read
POST /api/orders    → requires SCOPE_orders.write
~~~

Examples:

- GET `/api/orders` without an Authorization header → **401**.
- `Authorization: Bearer x.y.z` with invalid signature/JWT → **401 invalid_token**.
- JWT with valid signature whose `exp` is past → **401 invalid_token**.
- Valid, unexpired JWT with `profile` scope lacking `orders.read` → **403**, typically with `insufficient_scope`.
- JWT with the right scope where user Alice accesses Bob's order → business authorization must still deny with **403 or 404 per policy**, because scopes do not replace object ownership.

Do not treat 401 as “user lacks permission”, and do not use 403 to report “invalid password/token” across the board.

## 3. Common Error Classification Table

| Symptom | Detecting component | Typical status | Meaning |
| --- | --- | --- | --- |
| Missing `Authorization` | Authorization requiring authentication | **401** | No authentication credentials supplied |
| `Authorization: Basic ...` when API enables only Bearer | Converter does not recognize scheme | Usually **401** | Equivalent to missing Bearer credential |
| `Authorization: Bearer` with no token | Bearer request parser | **400 or 401** | Depends on whether parser classifies `invalid_request` or missing token |
| Duplicate tokens / mixed mechanisms supplied | Bearer converter | Typically **400 invalid_request** | HTTP request violates protocol contract |
| String treated as token, invalid JWT/base64url format | JWT decoder | Typically **401 invalid_token** | Cannot verify JWT |
| Bad signature / untrusted algorithm | JWT decoder | **401 invalid_token** | JWT payload cannot be trusted |
| `exp` in the past or `nbf` in the future | JWT timestamp validator | **401 invalid_token** | Outside valid time window |
| `iss` does not match trusted issuer | Claim validator | **401 invalid_token** | Issued by unpermitted issuer |
| `aud` does not include API audience | Additional claim validator | **401 invalid_token** | Token not intended for this Resource Server |
| Valid JWT lacking `orders.read` | Authorization policy | **403**, typically `insufficient_scope` | Caller lacks required permission |
| JWT has scope, lacks permission for specific resource | Domain authorization | **403/404** | Object-/tenant-level access denied |
| JWKS provider/metadata/network failure | Decode/discovery infrastructure | May be **5xx** or custom error | Must not be blindly treated as a bad token |
| Malformed JSON request body after authentication | WebFlux decoder/validation | **400** | Input error, not Bearer `invalid_request` |

**Do not assert that every malformed header is 401 or every 403 has `insufficient_scope`.** Spring Security 6.x distinguishes parse errors (`invalid_request`) from token validation (`invalid_token`); gateways, custom handlers, and security chain types can affect responses. Check both status **and** `WWW-Authenticate` on real requests.

## 4. Reactive Authentication Pipeline

~~~mermaid
flowchart TD
    A[HTTP Request] --> B[SecurityWebFilterChain]
    B --> C{Syntactically valid Bearer token?}
    C -->|None| D[Authorization checks requirements]
    D -->|Public| Z[Allow request]
    D -->|Protected| E[Authentication Entry Point 401]
    C -->|Malformed Bearer request| F[Bearer invalid_request]
    C -->|Token present| G[JwtReactiveAuthenticationManager]
    G --> H[ReactiveJwtDecoder: parse, JWS verify, claims validate]
    H -->|JWT invalid / expired| I[Bearer invalid_token 401]
    H -->|Valid JWT| J[JwtAuthenticationToken + GrantedAuthority]
    J --> K{Sufficient endpoint authority?}
    K -->|No| L[Bearer access denied 403]
    K -->|Yes| M[Domain ownership/tenant rules]
    M -->|Valid| N[Controller response]
    M -->|Denied| O[403 or 404 per policy]
~~~

In WebFlux, Bearer extraction is normally handled by `ServerBearerTokenAuthenticationConverter`, working with `AuthenticationWebFilter` and `JwtReactiveAuthenticationManager`. `NimbusReactiveJwtDecoder` uses trusted keys to verify signatures, checks JWT claims, and places `JwtAuthenticationToken` into the Reactor/Spring Security authentication context.

**Special note:** `@RestControllerAdvice` is not the default place handling all 401/403s. Spring Security filters typically reject requests **before** controllers are invoked. To customize the response body, use proper `ServerAuthenticationEntryPoint`/`ServerAccessDeniedHandler`, not just controller exception handlers.

### Public Endpoints Can Still Fail If Sent a Bad Bearer Token

`permitAll()` allows requests **without authentication** at that endpoint; it does not promise to ignore authentication attempts when the client actively sends a Bearer header. If a client attaches a broken token to `/public/ping`, the authentication filter may reject it before authorization evaluates `permitAll`. Therefore, never configure a frontend `WebClient`/HTTP client to blindly attach a bearer token to **every URL**.

## 5. Bearer Challenges and RFC 6750 Error Codes

### 5.1. Missing Token: 401 + Bearer Challenge

When a request lacks authentication on a protected endpoint:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

With a realm:

~~~http
WWW-Authenticate: Bearer realm="orders-api"
~~~

Per RFC 6750, when a request carries **no authentication credentials at all**, the server should avoid sending unnecessary error codes or descriptions. `BearerTokenServerAuthenticationEntryPoint` generates protocol-compliant challenges.

### 5.2. Invalid or Expired Token: `invalid_token`

Illustrative example:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

This could be an unparseable token, bad signature, expired, revoked under a validation model, or failing claim validation. Clients should request a fresh token via the appropriate grant/refresh flow **if a new token can resolve the issue**.

Never return raw JWTs, private keys/JWKs, stack traces, full decoder messages, or `error_description` containing secret details to clients.

### 5.3. Malformed Bearer Request: `invalid_request`

Example of a request containing multiple conflicting token delivery methods disallowed by policy:

~~~http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer error="invalid_request"
~~~

`invalid_request` means the **presentation of the request/token** is malformed. It differs from a token that was extracted cleanly yet failed signature/expiry checks. For `Authorization: Bearer` missing the token value, the exact status depends on the converter/handler; do not blindly assert all malformed headers return 400.

### 5.4. Valid Token with Insufficient Scope: `insufficient_scope`

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

`BearerTokenServerAccessDeniedHandler` checks whether the request has valid OAuth2 authentication; if so, it may include `insufficient_scope`. Not every 403 is guaranteed to contain this string: CSRF, object policies, or custom access-denied handlers can produce different responses.

**Key point:** for Bearer APIs, **status + `WWW-Authenticate` are the contract**, not just a JSON body.

## 6. Decodable Tokens Are Not Authenticated Tokens

A JWT typically looks like:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

An attacker can craft payload `{"sub":"admin","scope":"orders.write"}` and Base64URL-encode it. Reading header/payload alone proves nothing about whether a trusted IdP issued the token.

A JWT Resource Server must verify:

1. **JWS signature** using trusted JWK/public keys.
2. **Trusted algorithms**: reject `alg=none` or algorithms read straight from the token without an allowlist check.
3. **Issuer `iss`** matching a permitted IdP/tenant.
4. **Audience `aud`** containing the API's audience; reject tokens issued for other services.
5. **Expiry `exp`, not-before `nbf`** against current clock and reasonable clock skew.
6. **Token type/claims** required by the Resource Server; do not mistake an OIDC ID token for an API access token.
7. **Scopes/authorities** mapped properly and checked for the requested action/resource.

Spring Security 6.x provides `ReactiveJwtDecoder` and `JwtValidators` to perform these checks. When configuring a decoder manually, **keep the default validators** rather than replacing them with a lone audience validator.

### How Clock Skew Affects Expiry Testing

Spring Security Resource Server tolerates slight time drift, defaulting around **60 seconds**. A token expired by a few seconds may still be accepted within that tolerance. To test expiration, generate JWTs expired by **several minutes**, or test `JwtTimestampValidator(Duration.ZERO)` directly when checking exact `exp` boundaries.

Never widen clock skew to hours just to turn a test green; fix clock sync/NTP and token lifetime settings instead.

### JWKS, `kid`, and Key Rotation

The Authorization Server may rotate keys. The Resource Server fetches public keys from trusted JWKS and matches `kid`/algorithms per decoder caching/refresh mechanics. If the IdP swaps keys abruptly or JWKS fails, many requests may fail; operations must distinguish **invalid tokens** from **key fetch outages**. Never disable signature verification to ride out a network outage.

## 7. Scopes in JWTs and `SCOPE_` Authorities

Example JWT claims:

~~~json
{
  "sub": "alice",
  "iss": "https://idp.example.test/tenant",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write"
}
~~~

Another IdP might use `scp`:

~~~json
{
  "sub": "alice",
  "scp": ["orders.read", "orders.write"]
}
~~~

By default, `JwtGrantedAuthoritiesConverter` converts OAuth2 scopes into `SCOPE_`-prefixed authorities:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

In WebFlux security config:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders")
    .hasAuthority("SCOPE_orders.read")
.pathMatchers(HttpMethod.POST, "/api/orders")
    .hasAuthority("SCOPE_orders.write")
~~~

`hasAuthority("orders.read")` is **not the same** as `hasAuthority("SCOPE_orders.read")`. `hasRole("ADMIN")` normally checks `ROLE_ADMIN`, not auto-mapped from `scope=admin`. If the IdP uses custom `permissions` or `roles`, configure a controlled JWT-to-authentication converter rather than trusting client-sent role parameters in queries.

**Scope is only a necessary condition.** Even with `orders.read`, Alice must not automatically read Bob's orders; object-level authorization and tenant boundaries are required. A 403 for missing scope differs from 403/404 for resource ownership.

## 8. Complete Java 17+ Illustrative Application

Model: pure `Authorization: Bearer` API, **no form login, cookie session authentication, or HTTP Basic**. GET and POST require different scopes:

- `GET /public/ping` — public.
- `GET /api/profile` — requires authenticated JWT.
- `GET /api/orders` — `SCOPE_orders.read`.
- `POST /api/orders` — `SCOPE_orders.write`.

The config intentionally uses a dummy IdP domain. The app and mock tests can run; validating real JWTs requires configuring a real issuer/JWKS or a test IdP. **No API should accept unsigned JWTs merely for a demo.**

### 8.1. Dependencies in `build.gradle`

In a Spring Boot 3.x project already set up with Gradle plugins, repositories, and Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

The Resource Server starter brings everything needed for OAuth2 Resource Server/JWT/JOSE via Spring Boot's dependency management. Do not add `spring-boot-starter-web` just to get REST controllers, because this is **WebFlux Reactive**.

### 8.2. `src/main/resources/application.yml`

~~~yaml
server:
  port: 8080

demo:
  jwt:
    issuer: https://idp.example.test/tenant
    jwk-set-uri: https://idp.example.test/tenant/jwks.json
    audience: orders-api
~~~

All three values must be replaced with real settings in deployment: trusted issuer, IdP JWKS URL, and API audience. Never let clients specify a JWKS URL via requests. The example uses custom `demo.jwt` properties because we explicitly illustrate an audience validator.

Spring Boot also offers built-in Resource Server config:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.test/tenant
          jwk-set-uri: https://idp.example.test/tenant/jwks.json
~~~

The second snippet is an **alternative approach**—do not add both while the demo already declares a custom `ReactiveJwtDecoder` and expect them to merge. When using Boot properties, add audience validation per your Boot version's support or compatible decoder customization.

### 8.3. `src/main/java/demo/jwterrors/JwtErrorsApplication.java`

~~~java
package demo.jwterrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JwtErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtErrorsApplication.class, args);
    }
}
~~~

### 8.4. `src/main/java/demo/jwterrors/SecurityConfig.java`

~~~java
package demo.jwterrors;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context
    .NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance())
            .csrf(csrf -> csrf.disable())
            .httpBasic(basic -> basic.disable())
            .formLogin(form -> form.disable())
            .authorizeExchange(ex -> ex
                .pathMatchers("/public/ping").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Why does `csrf.disable()` appear only here?** This demo is restricted to a **stateless API authenticating solely via client-sent Bearer tokens in the header**. It uses no cookies/browser-managed credentials or form login. In products with browser sessions, browser-cached HTTP Basic, or multiple auth mechanisms, **do not copy the CSRF-disable line**; evaluate your threat model, keep CSRF for unsafe methods needing protection, or separate security chains.

`NoOpServerSecurityContextRepository` avoids storing authentication in a session for subsequent requests. Clients must send a Bearer token on **every** protected request. `httpBasic` and `formLogin` are disabled so the API does not redirect to HTML login when Bearer is absent.

`oauth2ResourceServer(...jwt(...))` registers the Bearer flow using the `ReactiveJwtDecoder` bean in the next section. Spring Security configures RFC 6750 Bearer entry point and access-denied handler by default.

### 8.5. `src/main/java/demo/jwterrors/JwtDecoderConfig.java`

~~~java
package demo.jwterrors;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class JwtDecoderConfig {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${demo.jwt.issuer}") String issuer,
            @Value("${demo.jwt.jwk-set-uri}") String jwks,
            @Value("${demo.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwks).build();

        OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator =
            new JwtClaimValidator<List<String>>(
                JwtClaimNames.AUD,
                aud -> aud != null && aud.contains(audience));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaults, audienceValidator));

        return decoder;
    }
}
~~~

In Markdown output, Spring placeholders `@Value("${demo.jwt.issuer}")` follow standard Spring syntax, with the dollar sign as a required part of the property expression.

The key point is that `JwtValidators.createDefaultWithIssuer(issuer)` preserves `iss`, `exp`, and `nbf` checks; the audience validator is **composed alongside** rather than replacing default validations. `NimbusReactiveJwtDecoder` also verifies the JWT signature against trusted JWKS. If a token from the right issuer targets a different API, the audience validator rejects it before reaching controllers.

### 8.6. `src/main/java/demo/jwterrors/OrderController.java`

~~~java
package demo.jwterrors;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class OrderController {

    public record CreateOrderRequest(String sku) {}

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/profile")
    public Mono<Map<String, String>> profile(
            JwtAuthenticationToken authentication) {
        return Mono.just(Map.of(
            "subject", authentication.getName()));
    }

    @GetMapping("/api/orders")
    public Mono<Map<String, Object>> orders(
            JwtAuthenticationToken authentication) {
        return Mono.just(Map.of(
            "owner", authentication.getName(),
            "ids", List.of("order-101", "order-102")));
    }

    @PostMapping("/api/orders")
    public Mono<ResponseEntity<Map<String, String>>> create(
            @RequestBody Mono<CreateOrderRequest> body,
            JwtAuthenticationToken authentication) {
        return body.map(input ->
            ResponseEntity.status(HttpStatus.CREATED).body(
                Map.of(
                    "createdBy", authentication.getName(),
                    "sku", input.sku())));
    }
}
~~~

The controller only illustrates HTTP responses and **has no database**. `JwtAuthenticationToken.getName()` normally reflects the decoder-verified `sub` claim. In a real product, listing orders must still filter by user/tenant and resource policies; never return all orders just because the token carries `orders.read`.

### 8.7. Running

~~~bash
# Linux/macOS
./gradlew bootRun

# Windows
gradlew.bat bootRun
~~~

`GET /public/ping` returns status 200 and body:

~~~json
{"status":"ok"}
~~~

The JWKS domain `idp.example.test` is an illustration **with no real service**. Do not expect any real JWT to verify against this endpoint. You can test no-token, mock authentication, and mocked decoder branches; end-to-end verification requires configuring a real IdP/JWKS or a test JWKS server.

## 9. Testing with `curl`

**Without a token:**

~~~bash
curl -i http://localhost:8080/api/orders
~~~

Expect 401 and `WWW-Authenticate: Bearer`.

**With a Bearer header whose token is not a valid JWT:**

~~~bash
curl -i \
  -H 'Authorization: Bearer broken.jwt.value' \
  http://localhost:8080/api/orders
~~~

A working decoder backed by trusted JWKS will reject malformed/badly signed tokens, typically with 401 `invalid_token`. With the non-working demo IdP, runtime outcomes depend on whether the error hits the parser or key lookup first; use a mocked decoder or test JWKS server for reproducible status checks.

**Header missing token after the Bearer scheme:**

~~~bash
curl -i \
  -H 'Authorization: Bearer' \
  http://localhost:8080/api/orders
~~~

Do not guess an absolute status code. The converter may classify it as a malformed Bearer request (`invalid_request`) or treat it as missing a token; check the actual header/status and Spring Security version.

**Genuinely expired JWT:**

~~~bash
curl -i \
  -H "Authorization: Bearer EXPIRED_SIGNED_TEST_JWT" \
  http://localhost:8080/api/orders
~~~

`EXPIRED_SIGNED_TEST_JWT` is merely a placeholder in this lesson. To test **expiry**, the token must have a valid signature/issuer/audience, with `exp` far enough in the past. Passing the literal placeholder string tests malformed JWTs, not expiration.

**Valid JWT lacking scope:**

~~~bash
curl -i \
  -H "Authorization: Bearer VALID_SIGNED_JWT_WITH_PROFILE_ONLY" \
  http://localhost:8080/api/orders
~~~

The test token must **pass the decoder**, carrying `scope=profile` without `orders.read`; typical outcome is 403 `insufficient_scope`. A badly signed token returns 401 and never reaches scope evaluation.

**Valid JWT + scope:**

~~~bash
curl -i \
  -H "Authorization: Bearer VALID_SIGNED_JWT_WITH_ORDERS_READ" \
  http://localhost:8080/api/orders
~~~

Only a real signed test token issued by a test IdP is expected to return 200. All `VALID_*` tokens here are placeholders, **not credentials**.

## 10. Testing Authorization with `WebTestClient` and `mockJwt()`

Spring Security Test's `SecurityMockServerConfigurers.mockJwt()` supplies a fake `JwtAuthenticationToken` in tests to check **authorization policies** without signing JWTs or running an IdP. It **does not perform signature/expiry/issuer/audience validation**, so never use it to prove the production decoder is configured correctly.

File `src/test/java/demo/jwterrors/JwtScopePolicyTest.java`:

~~~java
package demo.jwterrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class JwtScopePolicyTest {

    @Autowired
    WebTestClient client;

    @Test
    void noTokenReturns401AndBearerChallenge() {
        client.get().uri("/api/orders").exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().value(HttpHeaders.WWW_AUTHENTICATE,
                value -> assertTrue(value.startsWith("Bearer")));
    }

    @Test
    void publicPingIsAllowed() {
        client.get().uri("/public/ping").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void validJwtWithoutReadScopeReturns403() {
        client.mutateWith(mockJwt().jwt(
                jwt -> jwt.claim("scope", "profile")))
            .get().uri("/api/orders").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void readScopeAllowsGet() {
        client.mutateWith(mockJwt().jwt(
                jwt -> jwt.claim("scope", "orders.read")))
            .get().uri("/api/orders").exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.ids[0]").isEqualTo("order-101");
    }

    @Test
    void readScopeDoesNotAllowPost() {
        client.mutateWith(mockJwt().jwt(
                jwt -> jwt.claim("scope", "orders.read")))
            .post().uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"sku\":\"notebook\"}")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void writeScopeAllowsPost() {
        client.mutateWith(mockJwt().jwt(
                jwt -> jwt.claim("scope", "orders.write")))
            .post().uri("/api/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"sku\":\"notebook\"}")
            .exchange()
            .expectStatus().isCreated()
            .expectBody()
            .jsonPath("$.sku").isEqualTo("notebook");
    }
}
~~~

Run:

~~~bash
./gradlew test --tests 'demo.jwterrors.JwtScopePolicyTest'
~~~

**Interpretation:** A mock JWT authentication is injected before authorization. Missing token gets 401; authenticated missing scope gets 403; GET/POST require distinct scopes. Never call these tests “JWT signature tests”; `mockJwt()` can produce an `alg=none` `Jwt` in tests, which **does not change the real token verification policy** of the production decoder.

## 11. Testing Error Handling When the Decoder Rejects a JWT

To verify that decoder failures translate into 401 and `WWW-Authenticate: Bearer error="invalid_token"`, you can use a test-specific Mockito mock for `ReactiveJwtDecoder`. **This tests filter/handler wiring**, not real expiry or signatures.

File `src/test/java/demo/jwterrors/JwtAuthenticationFailureTest.java`:

~~~java
package demo.jwterrors;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.JwtValidationException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.when;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class JwtAuthenticationFailureTest {

    @Autowired
    WebTestClient client;

    @MockBean
    ReactiveJwtDecoder decoder;

    @Test
    void invalidJwtReturns401InvalidToken() {
        when(decoder.decode("broken.jwt.value"))
            .thenReturn(Mono.error(
                new BadJwtException("Synthetic malformed JWT")));

        client.get().uri("/api/orders")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer broken.jwt.value")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().value(HttpHeaders.WWW_AUTHENTICATE,
                value -> assertTrue(value.contains("invalid_token")));
    }

    @Test
    void syntheticExpiryErrorReturns401InvalidToken() {
        var validationError = new JwtValidationException(
            "Synthetic expired JWT",
            List.of(new OAuth2Error(
                "invalid_token", "expired", null)));

        when(decoder.decode("expired.jwt.value"))
            .thenReturn(Mono.error(validationError));

        client.get().uri("/api/orders")
            .header(HttpHeaders.AUTHORIZATION,
                "Bearer expired.jwt.value")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().value(HttpHeaders.WWW_AUTHENTICATE,
                value -> assertTrue(value.contains("invalid_token")));
    }
}
~~~

`@MockBean` is supported in Spring Boot 3.x, though deprecated in some Boot 3.4+ releases in favor of newer Mockito bean override mechanisms. When upgrading versions, update the test annotation rather than changing the production decoder.

**Do not mistake `expired.jwt.value` for a real expired token.** Mockito simulates the validator's `JwtValidationException`. This test verifies only **exception → 401 `invalid_token` mapping**.

### Testing `exp` Expiration Directly

File `src/test/java/demo/jwterrors/JwtExpiryValidatorTest.java`:

~~~java
package demo.jwterrors;

import java.time.Duration;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

import static org.junit.jupiter.api.Assertions.assertTrue;

class JwtExpiryValidatorTest {

    @Test
    void jwtExpiredFiveMinutesAgoIsRejected() {
        Instant now = Instant.now();

        Jwt token = Jwt.withTokenValue("synthetic-test-token")
            .header("alg", "RS256")
            .claim("sub", "alice")
            .issuedAt(now.minusSeconds(3600))
            .expiresAt(now.minusSeconds(300))
            .build();

        assertTrue(
            new JwtTimestampValidator(Duration.ofSeconds(60))
                .validate(token).hasErrors());
    }
}
~~~

This tests the **timestamp validator**, not signatures even though `header("alg","RS256")` is present. For complete verification, sign a JWT with a test private key and use a decoder configured with the matching public JWK.

## 12. Testing Real JWTs with a JWKS Test Server

When stepping up to integration tests, generate an RSA/EC keypair **exclusively inside the test environment**, host JWKS via a mock server, sign test JWTs, and send real `Authorization: Bearer ...` headers via `WebTestClient` without `mockJwt()`. The test suite should include:

| Test token | Signature | `iss` | `aud` | `exp` | Scope | Expected |
| --- | --- | --- | --- | --- | --- | --- |
| Valid read | Valid | Valid | orders-api | Future | orders.read | 200 GET |
| Missing | No token | — | — | — | — | 401 |
| Tampered | Invalid | Valid in forged payload | Valid fake | Future | orders.read | 401 invalid_token |
| Malformed JWT | Unparseable | — | — | — | — | 401 invalid_token |
| Expired | Valid | Valid | Valid | Minutes past | orders.read | 401 invalid_token |
| Not-before | Valid | Valid | Valid | Future, nbf in future | orders.read | 401 invalid_token |
| Wrong issuer | Valid | Wrong | Valid | Future | orders.read | 401 invalid_token |
| Wrong audience | Valid | Valid | billing-api | Future | orders.read | 401 invalid_token |
| Missing scope | Valid | Valid | Valid | Future | profile | 403 insufficient_scope |
| Read on POST | Valid | Valid | Valid | Future | orders.read | 403 |
| Write on POST | Valid | Valid | Valid | Future | orders.write | 201 |

When testing `kid`/key rotation, swap the JWKS between requests and observe cache/reload behavior per policy. **Never** use production private keys in tests. Note that access tokens can be opaque rather than JWTs; if the IdP issues opaque tokens, the Resource Server must configure introspection rather than forcing a JWT decoder to read opaque tokens.

## 13. Custom JSON Errors: Preserving the Bearer Standard

By default Spring Security provides:

- `BearerTokenServerAuthenticationEntryPoint`: initiates authentication/challenge when a Bearer token is missing or authentication fails.
- `BearerTokenServerAccessDeniedHandler`: handles `AccessDeniedException` when an authenticated request lacks sufficient permissions.

If explicit configuration in the `oauth2ResourceServer` DSL is needed:

~~~java
// SecurityWebFilterChain excerpt for illustration only.
.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationEntryPoint(
        new BearerTokenServerAuthenticationEntryPoint())
    .accessDeniedHandler(
        new BearerTokenServerAccessDeniedHandler())
    .jwt(Customizer.withDefaults()))
~~~

Imports:

~~~text
org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint
org.springframework.security.oauth2.server.resource.web.access.server.BearerTokenServerAccessDeniedHandler
~~~

Many REST APIs want to add a body:

~~~json
{
  "code": "AUTHENTICATION_REQUIRED",
  "message": "A valid access token is required"
}
~~~

This can be done via a custom `ServerAuthenticationEntryPoint` or `ServerAccessDeniedHandler`, provided you preserve:

1. Proper **401/403/400** status codes and Bearer error codes.
2. RFC 6750 `WWW-Authenticate` header; a JSON body must not replace the challenge.
3. No leaking of raw JWTs, JWKs, sensitive claims, stack traces, server filesystem paths, or client secrets.
4. Never returning 200 with an error field in the body.
5. Never writing the response twice; if a delegate already committed/called `setComplete()`, do not blindly chain `.then(writeJson())`.
6. Never putting “token refresh” logic inside a Resource Server error handler. The OAuth2 Client is responsible for obtaining a new token.
7. Testing status, headers, and body with `WebTestClient`, including missing token, expired, and insufficient-scope cases.

A safe policy is **keeping the default Bearer entry point/denied handler** if the frontend already handles status/challenge; customize only when the product genuinely needs a custom error envelope.

## 14. Expired Tokens: What Must the Resource Server and Client Do?

**Resource Server:** validate `exp`/`nbf`, fail closed when the token is no longer valid, return Bearer `invalid_token` as appropriate, and never re-issue tokens.

**OAuth2 Client:** if holding a refresh token under Authorization Code, run the appropriate refresh-token flow with the Authorization Server; if using Client Credentials, request a new access token via client authentication rather than a refresh token. Clients must not endlessly retry with the same expired JWT.

**Be careful with retries:** If a POST had side effects and the client received 401/timeout, blindly retrying can duplicate transactions when a response was lost; require idempotency keys/contracts before retrying. Idempotent GETs retry more safely, though still bounded.

**Clock skew:** if all services simultaneously reject JWTs as “not yet valid”, check NTP/`nbf` and the issuer clock. If only one node rejects, inspect that node and its validator version. Never issue infinite-lifetime tokens to avoid clock drift.

## 15. CSRF, CORS, Basic, and JWT Are Separate Mechanisms

In the demo, `csrf.disable()` is only valid because the API path is restricted to **stateless Bearer tokens actively placed in headers by clients**, with no browser-attached cookies/sessions for auth. If the app supports form login, browser cookies, or browser-cached Basic credentials, the CSRF threat model changes; retain CSRF for unsafe methods or split `SecurityWebFilterChain`s.

**CORS:** a frontend from another origin may trigger a preflight when sending the `Authorization` header. Preflight OPTIONS must be handled by CORS in the right order with allowed headers/methods. A CORS error does not equal a JWT 401; browsers sometimes report a “CORS error” simply because a 401/500 response lacked CORS headers. Never enable wildcard origins + credentials as a quick fix.

**HTTP Basic:** `Authorization: Basic ...` is not Bearer. When Basic is disabled and a protected API accepts only Bearer, sending Basic produces no authenticated identity, so the response is typically a 401 Bearer challenge. Never mix `httpBasic()` and JWT Bearer in the same chain unless the API contract explicitly requires both.

## 16. Common Pitfalls

**Pitfall 1: Base64URL-decoding and trusting `scope`.** Signatures must be verified; payloads can be forged by attackers.

**Pitfall 2: Accepting any `alg`/`kid` declared by the JWT.** Use trusted algorithms/JWKS allowlists and proper key resolution; never fetch URLs from untrusted headers.

**Pitfall 3: Checking `iss` while skipping `aud`.** Tokens meant for another API can be misused against this API.

**Pitfall 4: Turning an expired 401 into 403.** Expiration is an authentication failure; lacking scope is an authorization denial.

**Pitfall 5: Treating every malformed header as `invalid_token`.** `invalid_request` describes structural Bearer request errors, often status 400.

**Pitfall 6: Using `hasRole("orders.read")` when the JWT carries scopes.** By default scopes map to `SCOPE_orders.read`.

**Pitfall 7: Skipping object authorization because scope is present.** APIs must still enforce owner/tenant/resource constraints.

**Pitfall 8: Running `mockJwt()` tests and claiming signature/expiry were tested.** Mock authentication bypasses the decoder.

**Pitfall 9: Putting tokens in URL query strings.** Tokens can leak via logs, browser history, referrers, and caches; use the `Authorization` header over HTTPS.

**Pitfall 10: Printing full `Authentication`/JWTs into logs.** Can expose access tokens, claims, and personal info; log only error categories, request IDs, and safe metrics.

**Pitfall 11: Widening clock skew to hours or disabling validation.** Fix clocks/provider lifecycles instead of accepting expired tokens.

**Pitfall 12: Letting tokens pass unverified when JWKS errors.** Always fail closed and establish monitoring/outage strategies.

**Pitfall 13: Using an OIDC `id_token` to call an API expecting an access token.** Token type, audience, and scopes must match the resource server.

**Pitfall 14: Having the Resource Server fetch refresh tokens on 401.** The Client/AS manage refreshing; the Resource Server only receives and verifies access tokens.

## 17. Diagnostic Procedure

1. **Right route and chain?** Check method/path and `SecurityWebFilterChain`, ensuring another chain did not match first.
2. **What are status + challenge?** 400, 401, 403, or 5xx; is `WWW-Authenticate: Bearer` present and with what error code?
3. **Is a Bearer token present?** Confirm the client sent a proper `Authorization` header, without pasting real tokens into tickets.
4. **Can the JWT parse/verify?** Check trusted JWKS, algorithm, signature, `kid`, and key-fetch connectivity.
5. **Are claims valid?** `iss`, `aud`, `exp`, `nbf`, clock skew/NTP, and token type.
6. **If 403:** Do authorities include the matching `SCOPE_`? Do GET/POST need different scopes? Did an object/tenant policy deny it?
7. **If multiple nodes:** Check clocks, caches, consistent issuer/JWKS config, and key rotation.
8. **If browser differs from curl:** Check CORS preflight, cookies/CSRF in the security model, and `Authorization` header injection.
9. **If mass 5xx errors:** Inspect JWKS/IdP/network and service logs rather than assuming expired tokens.
10. **Run negative tests** for missing, malformed, bad signature, expired, wrong issuer/audience, and insufficient scope.

### Operational Guidance Table

| Symptom | Remediation |
| --- | --- |
| 401 Bearer without error | Client omitted credentials or scheme was unrecognized |
| 401 `invalid_token` | Decode/validation failed; categorize internally as signature/expiry/issuer/aud |
| 400 `invalid_request` | Fix HTTP request/Bearer header structure |
| 403 `insufficient_scope` | Fix grants/scopes or access policies; do not silently elevate privileges |
| Other 403 | Check domain ownership/CSRF/custom denied handler |
| 5xx JWKS | Check upstream/timeouts/caching/key rotation |
| GET succeeds, POST fails | Read/write scopes differ; or CSRF in cookie-using models |
| Mock tests pass, real JWTs fail | `mockJwt()` does not check signatures/claims |
| Public request with bad Bearer returns 401 | Filter may attempt authentication even on `permitAll` routes |

## 18. Quality and Production Checklist

| Check | Target outcome |
| --- | --- |
| Token transport | Bearer header over HTTPS, never tokens in URLs |
| Missing | Protected route returns **401** with Bearer challenge |
| Malformed header | `invalid_request`/status per real parser; no ambiguity tolerated |
| Invalid JWT | Wrong signature/issuer/audience/expiry → **401 invalid_token** |
| Missing scope | Valid JWT lacking `SCOPE_...` → **403** |
| Resource-level policy | Separate owner/tenant authorization |
| Decoder | `ReactiveJwtDecoder` with trusted algorithms/JWKS |
| Claims | `iss`/`aud`/`exp`/`nbf` validation enabled |
| Key rotation | Trusted JWKS cache/refresh/timeouts tested |
| Clock | Accurate NTP, small intentional skew |
| Entry point | `BearerTokenServerAuthenticationEntryPoint` semantics |
| Denied handler | `BearerTokenServerAccessDeniedHandler` semantics |
| Error response | Standard status/headers; no tokens/stack traces leaked |
| JWT type | Never accept ID tokens as API access tokens |
| CSRF | Disabled only under a verified bearer-only stateless threat model |
| Policy tests | `WebTestClient` + `mockJwt()` for authorities |
| Actual decoder tests | Signed JWTs with mock JWKS for signature/audience/time |
| Logs | Free of `Authorization`, JWTs, refresh tokens, and private keys |
| Client | Refreshes/re-authorizes via AS; no infinite retries |
| Multi-tenant | Issuer/decoder allowlist and tenant boundaries |

## 19. Self-Check Questions

**1. Should a missing Authorization header on a protected GET return 403 or 401?**  
Typically 401 with a Bearer challenge, since the request has no valid authentication yet.

**2. What should a valid JWT lacking `orders.read` return?**  
Typically 403, potentially with `insufficient_scope` from the Bearer denied handler.

**3. Should a JWT with a past `exp` still be processed if it carries `scope=orders.read`?**  
No; authentication must succeed before authorization. An expired JWT never produces a trusted `Authentication`.

**4. How does `invalid_request` differ from `invalid_token`?**  
`invalid_request` describes malformed Bearer request structure; `invalid_token` describes a presented token that failed validation.

**5. Why is `Base64.decode` on a JWT payload insufficient?**  
Because an unverified payload carries no trust without verifying signature and claims.

**6. Which authority does `scope=orders.read` map to by default?**  
`SCOPE_orders.read`.

**7. Why is `aud` needed if `iss` is already checked?**  
One issuer can mint tokens for multiple APIs; `aud` ensures the token was issued for this API.

**8. Does `mockJwt()` verify signatures and `exp`?**  
No. It simulates authentication to test authorization; testing the real decoder requires signed JWT/JWKS tests.

**9. Who refreshes the access token when the Resource Server returns 401 expired?**  
The OAuth2 Client / Authorization Server, never the Resource Server.

**10. Should CSRF always be disabled when JWT is enabled?**  
No. Consider how browsers transmit credentials; the demo disables it only because it is stateless Bearer header-only.

## Remember

- **Missing token → 401 Bearer challenge.**
- **Invalid/expired JWT → typically 401 `invalid_token`; malformed Bearer request → may be 400 `invalid_request`.**
- **Valid JWT lacking scope → typically 403 `insufficient_scope`.**
- Authentication via `ReactiveJwtDecoder` must check signature, issuer, audience, timestamps, and trusted keys; authorization checks `SCOPE_` alongside resource permissions.
- Never trust a JWT solely because it decodes, and never treat `mockJwt()` as a signature test.
- Preserve `WWW-Authenticate` per RFC 6750; avoid leaking tokens or stack traces in JSON/logs.
- Resource Servers do not issue or refresh tokens, and scopes do not replace ownership/tenant policies.

### Official Documentation

- [Spring Security 6.5 — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html)
- [Spring Security 6.5 — OAuth2 Resource Server WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html)
- [Spring Security — Testing OAuth2 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security 6.5 — BearerTokenServerAuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/web/server/BearerTokenServerAuthenticationEntryPoint.html)
- [Spring Security 6.5 — BearerTokenServerAccessDeniedHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/web/access/server/BearerTokenServerAccessDeniedHandler.html)
- [Spring Security 6.5 — BearerTokenErrorCodes](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/BearerTokenErrorCodes.html)
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
