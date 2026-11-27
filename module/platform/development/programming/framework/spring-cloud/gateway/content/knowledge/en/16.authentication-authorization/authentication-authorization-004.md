# Checking Token Issuer, Audience, Lifetime, and Signature

## 1. Goal: Not Just "Decoding a JWT," but Properly Validating the JWT

In a microservices architecture, **Spring Cloud Gateway** is typically the public entry point receiving HTTP requests before routing them to backends. A client calls:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...
~~~

The Gateway can select a route using `Path`/`Method`, apply the filter chain, transform paths/headers, and discover instances via `lb://orders-service`. Yet before granting access to a protected API, it must know **whether the Bearer token is truly valid and issued for this resource**.

For a **signed JWT access token** (JWS), the four core checks in this **Authentication and Authorization** chapter lesson are:

1. **Signature:** was the token signed with a key and algorithm trusted by the Gateway, and was the payload left untampered?
2. **Issuer (`iss`):** was the token issued by the exact configured Authorization Server/Identity Provider?
3. **Audience (`aud`):** was the token issued for this API/resource server, or is it intended for a different application?
4. **Lifetime (`exp`, `nbf`; also understand `iat`):** is the token expired, not yet valid, or out of compliance with time policies?

**A validly signed JWT is not necessarily permitted at this API.** For example, a token legitimately issued for `billing-api` must not be accepted by the Gateway to access `orders-api` merely because its signature is valid.

In the **SPRING_CLOUD_GATEWAY** module, this validation is foundational for running a secure API Gateway alongside route predicates, header/path transforms, service discovery, rate limiting, circuit breakers, retries, TLS, and request observability. This lesson focuses on **Spring Cloud Gateway Server WebFlux** with **Spring Security Reactive OAuth2 Resource Server**. Gateway Server MVC uses a different security stack.

> **Assumptions:** This covers validating **signed JWT access tokens** issued by a trusted issuer. Opaque tokens require introspection rather than a JWT decoder; encrypted JWE JWTs are handled differently from JWS. Example hostnames, tokens, and audiences are purely illustrative, not an active authentication system.

## 2. JWT Structure and What Can and Cannot Be Trusted

A compact JWS JWT has three dot-separated parts:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

**Illustrative** header:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "key-2026-11"
}
~~~

**Illustrative** payload:

~~~json
{
  "iss": "https://id.example.test/realms/platform",
  "sub": "user-123",
  "aud": ["gateway-api", "orders-api"],
  "scope": "orders.read",
  "iat": 1795000000,
  "nbf": 1795000000,
  "exp": 1795003600
}
~~~

| Component | Meaning | What to Check |
| --- | --- | --- |
| Header `alg` | Signature algorithm | Algorithm must be in a **server-configured allowlist**, never trusted solely from the header |
| Header `kid` | Key hint for selecting from JWKS | Key must come from a **trusted configured source**; `kid` is not proof of validity |
| Header `typ` | Token type hint | Some access token profiles (e.g., RFC 9068) require dedicated type checking |
| Claim `iss` | Token issuer | Compare against expected issuer |
| Claim `aud` | Valid token recipients | Must include the audience required by this API |
| Claim `exp` | Expiration time | Reject tokens past expiration after accounting for allowed clock skew |
| Claim `nbf` | Not-before timestamp | Reject tokens not yet active |
| Claim `iat` | Issued-at timestamp | Useful for audits and custom policies; does not replace `exp` |
| Claim `scope` or `scp` | Granted permissions | Input for **authorization**, does not prove signature/issuer/audience |

JWT timestamps are **NumericDate**: seconds since Unix epoch, **not milliseconds**. For example, Java `Instant.getEpochSecond()` and JavaScript `Date.now() / 1000` yield seconds; using `Date.now()` directly as `exp` is the wrong unit.

**Crucial:** Header and payload are only **Base64URL-encoded, not encrypted**. Anyone holding the token can read the claims. Never put passwords, secrets, or sensitive data in a JWT payload. Splitting the payload and invoking a JSON parser **does not verify the signature at all**; never use unverified results to build `Authentication` or make routing/role decisions.

## 3. Where Does Validation Happen in the Gateway WebFlux Flow?

In a WebFlux Gateway with Reactive Spring Security:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security WebFilterChain
    participant J as ReactiveJwtDecoder / JWKS
    participant G as Gateway route + filter chain
    participant B as orders-service

    C->>S: GET /api/orders/42 + Bearer JWT
    S->>J: Decode, verify signature and claims
    Note over J: Signature, iss, aud, exp, nbf
    alt Invalid token
        J-->>S: Authentication failure
        S-->>C: 401 Unauthorized
    else Valid token but missing scope
        J-->>S: Verified JWT
        S-->>C: 403 Forbidden
    else Valid token and sufficient permissions
        J-->>S: JWT + authorities
        S->>G: Allow request through security chain
        G->>B: Forward request per route
        B-->>G: HTTP response
        G-->>C: HTTP response
    end
~~~

This is a **logical diagram**, not a detailed ordering of every WebFilter/GatewayFilter across every version. The key takeaway is that **Spring Security WebFlux protects requests at the WebFilter layer** before an invalid request reaches the backend. Gateway route predicates **do not replace** authentication or authorization.

| Outcome | Common Meaning | Does the Backend Receive the Request? |
| --- | --- | --- |
| **401 Unauthorized** | Missing token or unverified JWT: wrong signature, issuer, audience, or lifetime | No, if blocked by Gateway |
| **403 Forbidden** | Valid token but insufficient permissions/scope; or denied by another security policy | No, if blocked by Gateway |
| **404 Not Found** | No matching route/handler or backend returns 404 | Depends on where 404 originates |
| **503 Service Unavailable** | E.g., `lb://...` route matches but no instances are available | Typically has not reached backend |

Actual status codes may vary due to custom exception handlers/filters. **Do not expose internal details about tokens, keys, or policies in public error responses**; log necessary diagnostics only to protected logs.

## 4. Signature Verification: Which Keys and Algorithms to Trust?

For tokens signed with **RS256**, the Authorization Server keeps the **private key** for signing; the Gateway retrieves the corresponding **public key** to verify. Issuers commonly publish public keys via a **JWKS endpoint**.

~~~mermaid
flowchart LR
    A["Authorization Server<br/>holds private key"] -->|"Signs JWT"| T["JWT: alg + kid + claims + signature"]
    A -->|"Publishes public JWKs"| K["JWKS HTTPS"]
    T --> G["Gateway JWT decoder"]
    K --> G
    G --> V{"Verify signature<br/>with trusted key?"}
    V -->|"No"| N["401"]
    V -->|"Yes"| C["Next check iss / aud / exp / nbf"]
~~~

### 4.1. JWKS, kid, and Key Rotation

Example of a JWKS snippet (**illustrative, not a real key**):

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "key-2026-11",
      "alg": "RS256",
      "n": "<modulus-public-key>",
      "e": "AQAB"
    }
  ]
}
~~~

The `kid` field helps the library pick the matching key from the **server-configured trusted key set**. It **does not allow** clients to make the Gateway fetch keys from an arbitrary URL. Token-supplied headers like `jku`/`x5u` must not become open key sources, preventing **SSRF/key-source substitution**.

When an issuer rotates keys, it can temporarily publish **both old and new keys** in JWKS so unexpired tokens continue validating. Resource Server supports updating keys when JWKS changes; exact refresh/cache behavior depends on library and version. Plan for unreachable issuer/JWKS endpoints, and do not remove old keys before tokens requiring them expire.

### 4.2. Do Not Trust Self-Declared Algorithms in the Token

A sound configuration has an **algorithm allowlist** matching the IdP and key type:

- `RS256`, `RS512`, `ES256`, etc. only when the issuer genuinely uses them and the Gateway is configured to verify them.
- **Never accept `alg=none`** for signed access tokens.
- Prevent attackers from switching asymmetric `RS256` to symmetric `HS256` causing *algorithm confusion*.
- Never use weak or publicly shared secrets; with asymmetric JWKS, the Gateway only needs the public key.

Per Spring Security Reactive JWT documentation, `NimbusReactiveJwtDecoder` trusts **RS256** by default in standard setups; this can be changed via `jws-algorithms` or the builder. If the IdP uses another algorithm, configure **only the allowed algorithm(s)** rather than enabling all algorithms just to make a token pass.

### 4.3. Signature Does Not Replace Claim Validation

A token with a valid signature yet:

~~~json
{
  "iss": "https://other-issuer.example.test",
  "aud": "another-api",
  "exp": 1700000000
}
~~~

must still be rejected at this Gateway if the issuer, audience, or timestamp is invalid. In particular, **a validly signed token from the same IdP issued for a different application** is a very common vulnerability when `aud` is skipped.

## 5. Checking Issuer (iss)

`iss` identifies the token issuer. Example issuer accepted by the Gateway:

~~~text
https://id.example.test/realms/platform
~~~

Spring Security OAuth2 Resource Server can use the `issuer-uri` property to discover Authorization Server metadata (OIDC Provider Configuration / OAuth Authorization Server Metadata), retrieve the JWKS URI, and validate the `iss` claim. The value must match the **issuer published by the IdP**, not be roughly guessed from a hostname.

| `iss` claim value in JWT | Compared with configured issuer above |
| --- | --- |
| `https://id.example.test/realms/platform` | Matches |
| `http://id.example.test/realms/platform` | Wrong scheme |
| `https://id.example.test/realms/other` | Wrong realm/tenant |
| `https://id.example.test/realms/platform/` | Mismatched string due to trailing slash |
| `https://evil.example.test/realms/platform` | Wrong hostname |

**Never accept arbitrary issuers based on an unverified token's `iss` claim** and use it to fetch JWKS dynamically. In multi-tenant/multi-issuer systems, maintain an explicit **issuer allowlist and binding from issuer → JWKS → audience/policy**, preventing one tenant's token from working for another tenant.

An Issuer URI may include a **path**, such as `/realms/platform`. There is no single universal convention for `jwk-set-uri`; consult IdP metadata or vendor documentation rather than guessing `/keys` from a realm name.

## 6. Checking Audience (aud): Who Is the Token For?

Audience indicates **which resource/API is permitted to consume the token**. `aud` may be a string or string array in a JWT; Spring Security typically normalizes it to a list when accessing `Jwt.getAudience()`.

Example Gateway requirement:

~~~text
Expected audience: gateway-api
~~~

| `aud` Claim | Valid for expected `gateway-api`? |
| --- | --- |
| `"gateway-api"` | Yes |
| `["gateway-api", "orders-api"]` | Yes |
| `"billing-api"` | No |
| `["orders-api", "billing-api"]` | No |
| Missing `aud` | No, if Gateway policy requires audience |

**`aud` differs from `iss` and `client_id`/`azp`.** Issuer states *who issued it*, audience states *who it is for*, while client ID/authorized party identifies the application that requested the token. Never use `sub`, `azp`, or `scope` as a substitute for audience validation.

### 6.1. Audience at the Gateway vs. Backend

In a multi-service system, decide **which APIs act as resource servers**:

- If the Gateway is the protected resource, it may require `gateway-api` in `aud`.
- If the Gateway forwards the same access token to `orders-service`, the backend should **independently verify the token** and require its accepted audience, e.g. `orders-api`, alongside order permissions.
- If using token exchange or token relay by policy, the downstream token's audience may differ from the token the client sent to the Gateway.

A JWT with `aud=["gateway-api","orders-api"]` is only an **example**; avoid inflating every token with broader audiences than necessary. Design audiences to match the IdP, trust boundaries, and least-privilege principles.

## 7. Lifetime: exp, nbf, iat, and Clock Skew

Time-related claims:

| Claim | Meaning | Rule |
| --- | --- | --- |
| `exp` | Expiration time | Token must not be accepted at or after expiration, accounting for allowed clock skew |
| `nbf` | Not before | Do not use token before effective time, accounting for clock skew |
| `iat` | Issued at | Indicates issuance time; **does not replace expiration checks** |

Timeline example:

~~~text
nbf = 10:00:00 UTC
iat = 10:00:00 UTC
exp = 10:20:00 UTC

09:59:00 ── not yet valid ── 10:00:00 ── valid ── 10:20:00 ── expired
~~~

Spring Security Reactive Resource Server uses **`JwtTimestampValidator`** to check the `exp`/`nbf` window; the docs note a **default 60-second clock skew** to tolerate minor clock differences across machines. For a newly expired token, behavior inside the skew window may differ from strict millisecond cutoff. This is an engineering trade-off and should not be widened indefinitely.

### 7.1. Do Not Confuse Validation with Requiring `exp` Presence

Checking a claim's timestamp **if present** does not mean every default configuration **mandates that `exp` exist in the token**. If your security policy requires every access token to have a finite lifetime, **add a validator requiring `exp` presence**, in addition to checking the timestamp. Similarly, you can validate that `iat` is not too far in the future or cap token lifetime `exp - iat` per policy.

Do not merge all three rules into a custom "token age" check while discarding `JwtTimestampValidator`. Each claim serves a distinct purpose; custom time logic easily breaks on timezones or second/millisecond mismatches.

### 7.2. Clock Synchronization and Token Lifecycle

- Synchronize NTP across IdP, Gateway, and microservices.
- Keep skew as small as infrastructure allows; the 60-second default is a reference point, not mandatory for all systems.
- Use short-lived access tokens and protect refresh tokens appropriately.
- A signature-verified, unexpired JWT **is not automatically revoked** when a user logs out or loses permissions. If instant revocation is required, design session state, token introspection, revocation lists, token exchange, or shorter TTLs as needed.

## 8. Minimal Configuration: Spring Boot Resource Server JWT for Gateway WebFlux

### 8.1. Maven Dependencies

Example for modern Spring Cloud Gateway Server WebFlux lines:

~~~xml
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
~~~

The OAuth2 Resource Server starter brings in Spring Security Resource Server and necessary JWT/JOSE support via Spring Boot dependency management. In some older Gateway WebFlux versions, the starter is named `spring-cloud-starter-gateway`. Pick a **Spring Cloud BOM compatible with Spring Boot**; do not mix Servlet MVC dependencies (`spring-boot-starter-web`) into Gateway Server WebFlux without a specific reason.

### 8.2. Configuring Issuer, Audience, and Algorithm

`src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/platform
          audiences:
            - gateway-api
          jws-algorithms:
            - RS256

  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: orders-api
              uri: http://localhost:9091
              predicates:
                - Path=/api/orders/**
              filters:
                - StripPrefix=1
~~~

**Meaning of the Spring Boot security properties:**

- `issuer-uri`: trusted issuer source; Resource Server uses it to locate metadata/JWKS when needed and verify `iss`.
- `audiences`: requires `aud` to contain at least the configured audience, here `gateway-api` (supported in current Spring Boot lines per docs).
- `jws-algorithms`: restricts accepted signature algorithms, here `RS256`.

**No Gateway route property replaces these checks.** `Path=/api/orders/**` is solely a routing predicate; verification lives in **Spring Security WebFlux**.

In Gateway **Server WebFlux 4.2/4.3**, the route list in the example above typically uses the `spring.cloud.gateway.routes` namespace instead of `spring.cloud.gateway.server.webflux.routes`. The `spring.security.oauth2.resourceserver.jwt.*` properties belong to Spring Boot/Security and **do not change just because the routes namespace changes**. Match your target version when deploying.

### 8.3. When Setting JWK Set URI Directly

If the IdP lacks standard metadata, or you want to specify the JWKS URL upfront, you can configure both:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/platform
          jwk-set-uri: https://id.example.test/realms/platform/protocol/openid-connect/certs
          audiences:
            - gateway-api
          jws-algorithms:
            - RS256
~~~

The JWKS path above is **an example styled after one IdP's endpoint**, not a universal path across all providers. When specifying both `issuer-uri` and `jwk-set-uri`, Resource Server can skip discovery to locate the JWKS URL while **still verifying `iss`** against the configured issuer. If you set only `jwk-set-uri` without configuring an issuer validator, **do not assume `iss` is still being verified**.

JWKS must be retrieved over trusted HTTPS with TLS validation; never embed the IdP's private key in the Gateway. Some newer Spring Security lines defer metadata initialization/fetching **until the first request**; when declaring a custom decoder bean, verify initialization lifecycle because overriding auto-config can change this behavior.

## 9. Protecting APIs by Scope After JWT Verification

A JWT valid in signature and claims does not mean the caller can access every resource. For instance, a token with `scope: "orders.read"` can read orders but cannot create orders.

Create `SecurityWebFilterChain` in Gateway WebFlux:

~~~java
package demo.gateway.security;

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
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                // Only disable CSRF for stateless APIs using Bearer
                // headers, without cookies/sessions for auth.
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/actuator/health").permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

In default JWT Resource Server configuration, Spring Security prefixes `scope`/`scp` values with `SCOPE_`. Thus `orders.read` becomes `SCOPE_orders.read`. If the IdP uses a custom role/claim format, configure an explicit converter and test it; do not assume a `roles` claim automatically becomes an authority.

**Notes:**

- Disabling CSRF as in the snippet is only appropriate if the API is **truly stateless and authenticates solely via Bearer tokens in headers**. If browsers authenticate via cookies, evaluate CSRF protection separately.
- With cross-origin browsers, CORS/preflight must be processed in the right order before authentication. Never require a Bearer token on CORS preflight OPTIONS, which prevents browsers from sending the real request.
- The backend must still perform **resource-level authorization**, e.g., confirming the user can read *their own order 42*. Scopes do not check resource ownership.
- Gateway JWT validation does not mean the backend should automatically trust any `X-User-Id` header from the client. When forwarding identity, use trusted channels and restrict direct backend access.

## 10. Custom ReactiveJwtDecoder: Checking Audience and Requiring exp

In some systems, you need custom validators, such as:

- Token must include `exp`.
- `aud` must contain `gateway-api`.
- `iss`, `exp`, and `nbf` are still checked by standard validators.
- Only `RS256` signatures from the **server-configured** JWKS are accepted.

The example below **replaces the auto-configured decoder** with an explicit bean. Use it **as an alternative**, without assuming the `spring.security.oauth2.resourceserver.jwt.*` properties from section 8 will automatically apply to your custom decoder.

Additional `application.yml`:

~~~yaml
app:
  security:
    jwt:
      issuer: https://id.example.test/realms/platform
      jwk-set-uri: https://id.example.test/realms/platform/protocol/openid-connect/certs
      audience: gateway-api
~~~

`JwtValidationConfig.java`:

~~~java
package demo.gateway.security;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimNames;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    ReactiveJwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.audience}") String requiredAudience) {

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        // Keep standard checks, including issuer and exp/nbf.
        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(issuer);

        // aud on a Jwt object is typically normalized to List<String>.
        OAuth2TokenValidator<Jwt> audience =
                new JwtClaimValidator<List<String>>(
                        JwtClaimNames.AUD,
                        audiences -> audiences != null
                                && audiences.contains(requiredAudience));

        // Additional policy: reject any JWT missing exp.
        OAuth2TokenValidator<Jwt> requireExp = jwt -> {
            if (jwt.getExpiresAt() == null) {
                OAuth2Error error = new OAuth2Error(
                        "invalid_token", "Missing exp claim", null);
                return OAuth2TokenValidatorResult.failure(error);
            }
            return OAuth2TokenValidatorResult.success();
        };

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience, requireExp));
        return decoder;
    }
}
~~~

In the example:

1. **Signature verification** is performed by `NimbusReactiveJwtDecoder` using the **server-configured JWKS URL and RS256**.
2. **Issuer and lifetime** remain verified by `JwtValidators.createDefaultWithIssuer(issuer)`; do not overwrite them with a standalone custom audience validator and accidentally lose default checks.
3. **Audience** is matched by a dedicated validator against `gateway-api`.
4. **Presence of exp** is explicitly enforced; this custom policy complements expiration timestamp checks.

If your application uses a Spring Security or Spring Boot line with different APIs, check exact method signatures in your version's docs. This snippet demonstrates how to **compose validators**, not a build/tested deployment artifact.

### 10.1. Customizing Clock Skew Without Dropping Other Validation

If a non-default clock skew is needed, combine `JwtTimestampValidator(Duration)` with issuer/audience/requireExp validators inside the same `DelegatingOAuth2TokenValidator`. Only adjust skew after checking system clocks:

~~~java
// Illustrates a custom time policy, replacing the standard validator part
// with a complete validator set rather than timestamp alone.
OAuth2TokenValidator<Jwt> timestamp =
        new JwtTimestampValidator(java.time.Duration.ofSeconds(30));
OAuth2TokenValidator<Jwt> issuer =
        new JwtIssuerValidator(expectedIssuer);
~~~

This snippet requires importing `JwtTimestampValidator` and `JwtIssuerValidator` and declaring `expectedIssuer` in proper Java context. You must **combine timestamp, issuer, audience, and requireExp** when configuring the decoder; never call `setJwtValidator(timestamp)` alone and lose issuer checks.

### 10.2. Alternative: Audience Property When Standard Policy Suffices

If your Spring Boot version supports `spring.security.oauth2.resourceserver.jwt.audiences`, the example in section 8 may be **sufficient** to validate audience without a custom bean. That usually requires less code and is easier to maintain. Only customize the decoder for specific needs such as mandatory `exp`, max token age, or multi-issuer policies; when customizing, own and test the entire validator chain.

## 11. Integration Testing Scenarios

Prepare an **operator-managed test Identity Provider** with a valid JWKS endpoint that can issue test tokens per variant. Sample tokens in documentation lack valid signatures; **do not pass them directly to the Gateway expecting 200**.

To avoid confusing JWT errors with backend errors, temporarily use a stable route such as:

~~~yaml
# Place inside the routes list per your Gateway WebFlux namespace
- id: orders-api
  uri: http://localhost:9091
  predicates:
    - Path=/api/orders/**
  filters:
    - StripPrefix=1
~~~

The backend at `localhost:9091` needs a GET `/orders/42` endpoint; a simple echo service works. Remember that Security WebFilters run before business-result checks, so when a JWT is invalid, the backend **should not** see the request.

### 11.1. Calling Without a Token

~~~bash
curl -i "http://localhost:8080/api/orders/42"
~~~

Expect **401** on a route requiring authentication; depending on configuration, `WWW-Authenticate: Bearer` may appear. This differs from 404 for an unrouted path and 503 for `lb://` with no instances.

### 11.2. Calling with a Valid IdP-Issued Token

In your terminal, store the **test token** in an environment variable securely via OS/CI mechanisms. Bash illustration once the variable is set:

~~~bash
curl -i "http://localhost:8080/api/orders/42" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
~~~

With a JWT having valid signature, `iss`, `aud`, `exp/nbf`, and the `SCOPE_orders.read` authority, the security chain admits the request into the Gateway. If the backend endpoint works, the response can return **200**. Do not attribute every 200 solely to "valid JWT": final status also depends on routing, LoadBalancer, and backend.

### 11.3. Authentication and Authorization Test Matrix

| Test Case | Token Data/Condition | Expected at Gateway |
| --- | --- | --- |
| A. Missing Bearer token | No `Authorization` | **401** |
| B. Malformed token | Not a valid JWT | **401** |
| C. Payload tampered after signing | Signature no longer matches | **401** |
| D. Wrong algorithm or `alg=none` | Not in allowlist | **401** |
| E. Signed with untrusted key | `kid` finds no matching key, or bad signature | **401** |
| F. Wrong issuer | `iss` is another realm/tenant | **401** |
| G. Wrong audience | `aud=["billing-api"]`, requires `gateway-api` | **401** |
| H. Missing audience | No `aud`, policy requires it | **401** |
| I. Expired | `exp` expired beyond clock skew | **401** |
| J. Not yet valid | `nbf` in future beyond clock skew | **401** |
| K. Missing exp | Token lacks `exp`, section 10 `requireExp` enabled | **401** |
| L. All claims valid, missing scope | Valid JWT lacking `orders.read` | **403** |
| M. Valid and sufficient scope | Has `orders.read` | **Forwarded**, status decided by backend |
| N. Revoked at IdP but unexpired | Offline JWT still has valid signature | Requires **dedicated revocation mechanism**; not automatically rejected immediately |

**When constructing cases C–K**, use a test IdP or token-issuing tool **where you control test keys**, never modifying production tokens or putting real secrets in docs/logs. Scenarios requiring `exp` presence must be tested with a custom decoder if that policy is not enabled by default.

### 11.4. Do Not Confuse Issuer and Audience Checks with Scope

Consider two JWTs sharing:

~~~json
{
  "iss": "https://id.example.test/realms/platform",
  "scope": "orders.read"
}
~~~

yet differing in `aud`:

~~~text
Token 1: aud = ["gateway-api"] → may be accepted by Gateway.
Token 2: aud = ["billing-api"] → rejected by Gateway.
~~~

If only signature and scope are checked, Token 2 may be wrongly accepted, leading to **token confusion/cross-service token reuse**. That is why audience validation is critical when multiple microservices share an IdP/JWKS.

## 12. Distinguishing 401, 403, 404, 429, and 503 Errors

When securing the Gateway, status codes do not come solely from the JWT decoder:

| Status | Common Origin | Investigation |
| --- | --- | --- |
| **401** | OAuth2 Resource Server missing or failing to verify Bearer token | Check `iss/aud/exp/nbf/alg/kid` and JWKS |
| **403** | Valid token, but authorization policy denies | Check scope, role mapping, route permission |
| **404** | Gateway has no route, or backend has no endpoint | Check route ID and transformed path |
| **429** | Gateway rate limiter blocks request | Check quota keys, policy, and verified identity |
| **503** | LoadBalancer finds no instance for `lb://service-id` | Check discovery, registry, supplier, and health |
| **Other 5xx** | Backend failure, timeout, or proxy/decoder cannot reach JWKS | Distinguish infrastructure network errors from bad JWTs |

**Do not turn all token errors into HTTP 403 to "simplify."** 401 indicates failed authentication, while 403 usually indicates authenticated but unauthorized; clients and monitoring must distinguish them.

For CORS preflight, `OPTIONS` may lack a Bearer token; if Security blocks early, the frontend reports a CORS error instead of a JWT error. When serving browser frontends, configure reactive CORS properly before authentication and test real requests separately.

## 13. Security Pitfalls to Avoid

### 13.1. Reading Payload via Base64URL Alone

Having `Base64.getUrlDecoder()` read JSON claims or a parser extract `sub` **proves nothing** about JWT validity. All checks must pass through `ReactiveJwtDecoder` with signature verification and validators; never build `Authentication` from an unverified payload.

### 13.2. Trusting Signature Only, Ignoring Issuer/Audience

One issuer can mint tokens for many apps and APIs. Sharing a public key **does not mean every token is meant for the Gateway**. You must verify the trusted issuer, required audience, and appropriate resource policy.

### 13.3. Fetching JWKS Dynamically from Client-Supplied jku/iss

Never infer key-retrieval URLs from unverified JWT headers/payloads. Only use metadata/JWKS endpoints belonging to **server-controlled allowlisted issuers**; enforce HTTPS and proper timeouts/caching to avoid SSRF and token/key confusion.

### 13.4. Allowing Insecure Algorithms

Never accept `alg=none` or let a client header downgrade RS256 → HS256. Configure an explicit algorithm allowlist and key types matching the IdP; never use "decode without verify" in security flows.

### 13.5. Omitting exp or Setting Excessively Large Skew

Validly signed tokens that have expired must be rejected. If the app requires every token to have `exp`, add a validator requiring that claim. Synchronize clocks; never set `clockSkew` to hours to hide NTP issues.

### 13.6. Gateway Authenticates, Backend Blindly Trusts

A service can be called directly if the network is not locked down. Backends must protect APIs along their own boundary: verify appropriate tokens or trust Gateway-asserted identity only over a protected channel (e.g., mTLS, network policy, and strict header provenance). Never trust client-sent `X-User-Id`.

### 13.7. Confusing Access Tokens with ID Tokens

An **ID token** in OpenID Connect is primarily for the client application to learn login session and user identity details; it is not by default an **API access token**. Never send an ID token to the Gateway just because both are JWTs from the same issuer.

### 13.8. Passing Tokens in URLs, Logs, or Public Online Tools

A Bearer token is a **bearer secret**: anyone possessing it can attempt to use it until it expires or is revoked. Never pass it in query strings, write it to access logs, traces, exception messages, Git, or public JWT debugger websites. You may inspect metadata from dummy test tokens, but never upload real user tokens to untrusted tools.

## 14. Impact of Retries, Caching, and TLS

**JWT key cache:** Resource Server can cache JWKS/public keys to avoid hitting the IdP on every request. Tune TTL/refresh appropriately and plan for rotation; never accept arbitrary unknown keys during transient JWKS failures. Discovery/lazy decoder behavior varies across versions; measure startup and first-request latency in real environments.

**Retry:** Retries in the Gateway or LoadBalancer typically apply to backend requests after authentication. Never use retries to bypass token errors, and protect non-idempotent POSTs with idempotency safeguards. If service token exchange is added, keep client tokens separate from backend tokens; never treat Gateway issuer/audience validation as "automatically trusted by every backend."

**Rate limiting:** Quota keys should rely on **verified** identity (such as principal/`sub` or trusted client ID) rather than decoded-but-unverified claims or unnormalized `X-Forwarded-For`. Tokenless requests need their own policy.

**Circuit breaker:** When the IdP or JWKS is unreachable, never "fail open" by skipping signature/claim validators. Design timeouts, caching, readiness, and alerting separately; circuit breakers/fallbacks must never synthesize access permissions.

**TLS:** client → Gateway, Gateway → IdP/JWKS, and Gateway → backend are distinct hops. Use HTTPS/mTLS as required per hop, verify certificates, and never disable hostname verification just to make a demo work.

## 15. Pre-Production Deployment Checklist

- [ ] Gateway uses **Spring Security Reactive Resource Server** on WebFlux with appropriate JWT/JOSE dependencies.
- [ ] Accept access tokens only via secure channels, typically `Authorization: Bearer`; never log tokens.
- [ ] Issuer URI matches the IdP's published `iss` exactly, including scheme/path/trailing slash if present.
- [ ] JWKS/metadata are fetched from **trusted configured issuer endpoints** over HTTPS.
- [ ] Signing algorithms are allowlisted; never accept `none` or token-dictated algorithms.
- [ ] Audience strictly requires the expected API/resource ID; never substitute `scope` or `client_id` for `aud`.
- [ ] Verify `exp`/`nbf` and consider **requiring `exp` presence**, `iat` policy, and max token lifetime if needed.
- [ ] System clocks are synchronized; clock skew is small and intentional.
- [ ] Custom decoders always **combine** standard validators with custom ones, never accidentally dropping issuer/time checks.
- [ ] Authorize by scopes/roles and **business permissions** after authentication.
- [ ] Clearly separate 401, 403, and routing/LoadBalancer/backend errors.
- [ ] CORS preflight and Spring Security execute in the right order for browser frontends.
- [ ] Plans exist for JWKS unavailability, new `kid`, key rotation, and revoked tokens.
- [ ] Backend cannot be reached without authorization by bypassing the Gateway.
- [ ] Metrics/traces record error categories and route IDs safely, without raw tokens or sensitive data.
- [ ] Test suite includes invalid signature, issuer, audience, expired, not-before, missing exp, and insufficient scope tokens.

## 16. Official References for Version Cross-Checking

1. [Spring Security — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): signature verification, `issuer-uri`, `jwk-set-uri`, algorithms, timestamps, and audience validators.
2. [Spring Security 6.5 — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html): `NimbusReactiveJwtDecoder`, `DelegatingOAuth2TokenValidator`, and clock skew examples.
3. [Spring Boot — OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html): `spring.security.oauth2.resourceserver.jwt.issuer-uri`, `jwk-set-uri`, and `audiences` properties.
4. [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `SecurityWebFilterChain`, matching, and scope/authorization.
5. [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `sub`, `aud`, `exp`, `nbf`, and `iat` claims.
6. [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm/key confusion, strict validation, preventing token substitution.
7. [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): `at+jwt` format and required rules when adhering to this profile.

**Key takeaway:** JWT verification at Spring Cloud Gateway requires **all four layers**: signature from a **trusted key/algorithm**, exact `iss` issuer, `aud` containing the target resource, and valid `exp/nbf` within reasonable clock skew. After authentication, **authorization by scope and resource remains a separate step**. Use Spring Security Reactive Resource Server and standard validators, add intentional custom validators, test invalid tokens as well, and never trust a payload merely because it is readable.
