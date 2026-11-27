# Configuring issuer-uri, jwk-set-uri, and Trusted Keys

## 1. The Problem: Whose Access Tokens Should a WebFlux Resource Server Trust?

A **Spring WebFlux** application acting as an **OAuth 2.0 Resource Server** protects its API with access tokens. Clients send tokens over HTTP:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0yMDI2LTAxIn0...
```

The API cannot accept a token merely because it has three dot-separated segments or because its payload contains `sub` and `scope`. Before creating an authenticated principal, the API must answer:

1. **Who issued the token?** Does the `iss` claim match a configured trusted **issuer**?
2. **Is the signature actually valid?** Do the `alg` and `kid` headers lead to an accepted public key from a trusted source?
3. **Is the token intended for this API?** `aud` must match `orders-api`; tokens meant for a frontend or another API must not be accepted by default.
4. **Is the token still valid and of the right profile?** `exp`, `nbf`, and any additional access-token profile requirements must pass.
5. **Does the token have sufficient permissions?** `scope`/authorities must match the endpoint; owner/tenant and business policy must still be checked.

In Spring Security, two commonly seen properties are:

- **`issuer-uri`:** identifier of a trusted Authorization Server or OpenID Provider. When using discovery, Spring can look up metadata and then obtain the JWKS address; Spring must also validate the JWT's `iss` claim.
- **`jwk-set-uri`:** address of a **JSON Web Key Set (JWKS)** containing public keys that the Resource Server uses to verify JWS signatures. This URI must be obtained from a trusted issuer or configured via a trusted channel, **never taken from a client-supplied token**.

The two values are related but **not interchangeable**. A JWKS public key verifying a signature does not prove the JWT is an access token intended for `orders-api`; a matching `iss` claim does not prove the signature if the key source is wrong.

This lesson belongs to the **JWT in WebFlux** chapter of the **Spring Security OAuth 2.0 OIDC Resource Server** module. Examples use **Java 17+, Spring Boot 3.x, Spring Security 6.x, and Reactor/WebFlux**. Paths, domains, key IDs, JWTs, and clients are illustrative data. For newer library versions, check the corresponding API/builders and auto-configuration.

> **Principle:** Trust does not arise from `kid`, `alg`, or `iss` inside an unverified JWT. Trust comes from **pre-authorized issuer/key source configuration**, cryptographic verification rules, and the Resource Server's token validation.

---

## 2. Visualizing the JWT Verification Flow in WebFlux

A reactive Resource Server goes through `SecurityWebFilterChain`, not servlet `SecurityFilterChain`. Spring Security extracts the Bearer token, invokes `ReactiveJwtDecoder`, and places authentication into the **Reactor Context** per request.

```mermaid
sequenceDiagram
    participant C as Client
    participant W as Spring WebFlux SecurityWebFilterChain
    participant D as ReactiveJwtDecoder
    participant M as Trusted issuer metadata/JWKS
    participant A as Reactive Controller / Service

    C->>W: GET /api/orders/42 + Bearer JWT
    W->>D: decode(token)
    opt Discovery/JWKS needed per config, cache, and key id
        D->>M: HTTPS GET metadata/JWK set from trusted source
        M-->>D: issuer metadata / public keys
    end
    D->>D: Verify signature + alg + iss + timestamps + aud/profile
    alt JWT rejected
        D-->>W: Reactive authentication failure
        W-->>C: 401 + Bearer challenge
    else JWT valid
        D-->>W: Jwt verified
        W->>W: Map scope -> authorities
        alt Missing route permission
            W-->>C: 403 Forbidden
        else Sufficient route authority
            W->>A: Reactive request with authenticated principal
            A->>A: Check owner/tenant/business policy
            A-->>C: Permitted data or denial
        end
    end
```

Separate this into three **trust boundaries**:

| Boundary | Evidence required | Who checks? |
|---|---|---|
| **Cryptographic trust** | Token signed with the private key corresponding to a **trusted public key**, using an allowed algorithm. | `ReactiveJwtDecoder`/JWS verifier. |
| **Token applicability** | Issuer, audience, expiration, token type/profile match the API. | Resource Server JWT validators. |
| **Business authorization** | Scope, role, ownership, tenant, business state. | `SecurityWebFilterChain`, method/domain service, repository. |

A common mistake is **enforcing only the first boundary** and then calling the token "valid" for every purpose.

### 2.1. Components That Differ from the Servlet Stack

| Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|
| `SecurityFilterChain` | **`SecurityWebFilterChain`** |
| `HttpSecurity` | **`ServerHttpSecurity`** |
| `JwtDecoder` | **`ReactiveJwtDecoder`** |
| `JwtDecoders` | **`ReactiveJwtDecoders`** |
| `NimbusJwtDecoder` | **`NimbusReactiveJwtDecoder`** |
| `AuthenticationManager` | **`ReactiveAuthenticationManager`** |
| `SecurityContextHolder` based on thread context in Servlet | **`ReactiveSecurityContextHolder` / Reactor Context** for reactive flows |
| `MockMvc` | **`WebTestClient`** |

A `spring-boot-starter-webflux` application must not copy `HttpSecurity`, `OncePerRequestFilter`, or servlet `JwtDecoder` and assume they automatically protect WebFlux routes. When both WebFlux and MVC dependencies are present, Spring Boot may choose a different web application type than intended; verify which stack is actually running.

---

## 3. An Illustrative JWT Access Token

JWT header:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "orders-signing-key-2026-11"
}
```

Payload:

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders:read orders:write",
  "iat": 1890000000,
  "nbf": 1890000000,
  "exp": 1890003600,
  "client_id": "web-portal"
}
```

Explanation:

- `iss` is the access token's issuer; it must match the **configured or allowlisted issuer**.
- `sub` identifies the subject within the issuer's namespace; it is not assumed to be the owner of every order.
- `aud` indicates the resource the token is intended for. `orders-api` must be in the audience per contract.
- `alg=RS256` is only a **claimed** algorithm in the JWS header. The decoder must accept only configured algorithms, not trust any value sent by the client.
- `kid` hints at the **key ID** to select a key in the trusted JWKS. `kid` is neither proof of trust nor a URL.
- `typ=at+jwt` is the header type used by the RFC 9068 JWT access token profile. Checking the token type depends on configuration/version; do not assume `issuer-uri` alone implements full RFC 9068 validation.
- `exp`, `nbf`, and `iat` use **NumericDate** (Unix epoch seconds), not milliseconds.
- `scope` expresses OAuth permissions per contract; Spring Security typically maps these to `SCOPE_orders:read`, `SCOPE_orders:write` authorities.

The JWT payload is **not secretly encrypted by Base64URL**. Anyone holding the JWT can read its claims if it is a regular JWS. Values in the payload must not be trusted until the signature, issuer, and validators have passed.

> **Time note:** The timestamp numbers above are format examples only. A demo token with timestamps in the future or past relative to the runtime environment will be rejected when checking `exp`/`nbf` against real time. In tests, generate timestamps relative to `Clock`/`Instant.now()` or fix the clock.

---

## 4. `issuer-uri`: Issuer Identity and the Discovery Mechanism

In Spring Boot:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/realms/orders
```

With an issuer-only configuration and no custom decoder bean, Spring Boot/Spring Security can:

1. Use provider/Authorization Server metadata discovery to find the issuer's endpoints.
2. Read `jwks_uri` from the trusted metadata.
3. Create a `ReactiveJwtDecoder` capable of fetching/refreshing public keys from JWKS.
4. Set up the required JWT validation, including **issuer**.
5. Verify access tokens in the reactive flow as requests arrive.

### 4.1. What Might Discovery Metadata Look Like?

For example, an OpenID Provider publishes:

```http
GET /realms/orders/.well-known/openid-configuration HTTP/1.1
Host: auth.example.test
Accept: application/json
```

An illustrative metadata document:

```json
{
  "issuer": "https://auth.example.test/realms/orders",
  "authorization_endpoint":
    "https://auth.example.test/realms/orders/protocol/openid-connect/auth",
  "token_endpoint":
    "https://auth.example.test/realms/orders/protocol/openid-connect/token",
  "jwks_uri":
    "https://auth.example.test/realms/orders/protocol/openid-connect/certs"
}
```

**Do not hardcode the exact same discovery path for every issuer.** Depending on the issuer path and supported metadata standards, the library may try URLs according to OIDC Discovery and OAuth 2.0 Authorization Server Metadata rules. `jwks_uri` must come from trusted metadata, never chosen by a JWT header.

Configuring `issuer-uri` gives the application an **explicit issuer identifier**. Once keys are obtained, the JWT claim:

```json
{"iss":"https://auth.example.test/realms/orders"}
```

must match the accepted issuer. Comparison is typically an **exact string match**, so do not assume URLs differing only by trailing slash, path, scheme, or letter case are the same issuer:

```text
https://auth.example.test/realms/orders
https://auth.example.test/realms/orders/
https://auth.example.test/realms/other
http://auth.example.test/realms/orders
```

If the actual issuer uses a trailing slash, configuration must match the exact published issuer and emitted `iss`, rather than "fixing" it by disabling issuer validation.

### 4.2. When Does Issuer-Only Make the Application Depend on the Authorization Server?

In an auto-discovery setup, the decoder/auto-configuration may need to call the metadata endpoint during initialization. **In certain versions/configuration paths, the application cannot start successfully if issuer metadata is unreachable at startup.** That is why many production operations prefer configuring `jwk-set-uri` directly.

Do not infer from a different Spring Security version that discovery is always performed at startup or always deferred until the first request. Observe the behavior of the **framework version and configuration in use**.

### 4.3. Issuer-Only Still Does Not Know Business Audience

Having only:

```yaml
jwt:
  issuer-uri: https://auth.example.test/realms/orders
```

does not prove the JWT has `aud=orders-api`. An issuer can issue tokens for `payments-api` and `reports-api` using the **same signing keys**. If the Resource Server only checks signature + issuer + timestamps, tokens meant for another API risk being mistakenly accepted.

Therefore, the API should specify the audience:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/realms/orders
          audiences:
            - orders-api
```

The `audiences` property is supported in compatible Spring Boot 3.x versions; when using a custom `ReactiveJwtDecoder` bean, you must attach the corresponding validator yourself because auto-configuration may yield to your bean. Never assume the YAML `audiences` property automatically applies to every custom decoder.

---

## 5. `jwk-set-uri`: Address of the Signature Verification Key Set

A **JWKS** is a JSON object with a `keys` field containing **JSON Web Keys (JWKs)**. For JWTs signed with asymmetric RSA/EC, the public portion in the JWKS can be used to **verify** signatures without possessing the private signing key.

Abbreviated JWKS example:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "orders-signing-key-2026-11",
      "alg": "RS256",
      "n": "BASE64URL_PUBLIC_MODULUS_PLACEHOLDER",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "orders-signing-key-2026-12",
      "alg": "RS256",
      "n": "BASE64URL_NEXT_PUBLIC_MODULUS_PLACEHOLDER",
      "e": "AQAB"
    }
  ]
}
```

The placeholder `n` strings are not valid RSA moduli and only illustrate structure. In a real JWKS:

- `kty` identifies the key type (`RSA`, `EC`, ...).
- `kid` is the key ID for picking a matching key from a **trusted** key set.
- `use=sig` indicates the key is used for signing/verifying signatures.
- `alg` can constrain usage per metadata/profile, **but the decoder itself must enforce an algorithm allowlist** rather than relying solely on the `alg` in the JWKS.
- `n` and `e` are the **public RSA key** components (Base64URL).
- For elliptic curves, a JWK typically has `crv`, `x`, `y` instead of `n`/`e`.

**A JWKS must never contain private signing key components** such as `d` from RSA. The Authorization Server keeps the private key securely stored; the Resource Server only needs the public key to verify asymmetric JWS signatures.

### 5.1. Configuring Only `jwk-set-uri`

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://auth.example.test/realms/orders/protocol/openid-connect/certs
```

Advantage: the decoder knows directly where to fetch public keys without needing to locate `jwks_uri` via metadata discovery.

However, remember the catch: **knowing only the JWKS URL does not automatically establish an expected issuer**. If the Resource Server does not add an issuer validator, a token signed by a key in the JWKS could be accepted even if its `iss` claim does not match the intended API, depending on other validators. Thus **jwk-set-uri-only is not a complete configuration** for an API requiring strict issuer binding.

A common surprise:

```text
Configured JWK Set URI:
  https://auth.example.test/realms/orders/certs

JWT claims:
  iss = https://different-issuer.example.test

Cryptographic signature:
  verifies with configured public key

Question:
  Is issuer mismatch rejected?
Answer:
  Only if issuer validation is configured for the decoder.
```

Do not use this option while skipping issuer validation merely to make the system start up more easily.

### 5.2. `kid` Does Not Mean "Trust Whoever Points to a Key"

A JWT header might look like:

```json
{
  "alg": "RS256",
  "kid": "orders-signing-key-2026-11",
  "jku": "https://attacker.example.test/my-jwks"
}
```

In a secure configuration, **a token-supplied `jku` must never determine the JWKS endpoint automatically**. If a custom decoder fetches keys from a URL inside the token, an attacker can:

1. Generate their own private key and public JWKS on their own host.
2. Sign a forged JWT containing admin privileges using that private key.
3. Attach `jku` pointing to the attacker's JWKS.
4. Trick the Resource Server into fetching the non-allowlisted public key and verifying the forged token's signature.

This is a **key-source confusion / untrusted JWK URL** vulnerability, which can lead to SSRF or authentication bypass. A Spring Security decoder must only use a **trusted configured JWK source** or a resolver with a strict issuer allowlist. Never treat `jku`, `x5u`, or an embedded `jwk` in the header as an arbitrary trust source.

### 5.3. `kid` Can Change During Key Rotation

When the AS rotates its signing key, new JWTs may carry `kid=orders-signing-key-2026-12`. The Resource Server should be able to reload the JWKS from the **same trusted endpoint** according to its refresh/cache policy to verify the new key.

**Do not hardcode a single immutable `kid` in code** if the system requires auto-rotation. On the other hand, do not accept an unknown key from a different source merely because `kid` matches. The trust source must be fixed; the key ID may rotate within that source.

---

## 6. Combining `issuer-uri` and `jwk-set-uri`: A Common Production Pattern

To **avoid metadata discovery dependency at startup** while still validating the issuer, configure both:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/realms/orders
          jwk-set-uri: https://auth.example.test/realms/orders/protocol/openid-connect/certs
          audiences:
            - orders-api
```

Meaning:

- **`issuer-uri`**: expected JWT `iss`, protecting the issuer identity boundary.
- **`jwk-set-uri`**: fixed HTTPS endpoint serving public keys, avoiding `jwks_uri` discovery at bootstrap.
- **`audiences`**: token must be intended for `orders-api`, not just the same issuer.
- **JWT validators**: timestamps and other decoder conditions.
- **HTTP authorization rules**: scopes per operation.
- **Business policy**: owner/tenant/resource permissions.

With compatible Spring Boot auto-configuration, this combination still verifies the issuer without depending on metadata discovery to locate the JWK set URI. **Do not confuse "no startup discovery needed" with "never needs the network."** When a corresponding JWK is not yet cached, or when key rotation requires a refresh, the decoder still needs to reach the JWKS endpoint to verify tokens.

### 6.1. Comparison Table of the Three Approaches

| Configuration | Public key source | Issuer check | Startup/discovery |
|---|---|---|---|
| **`issuer-uri` only** | Discovery metadata leads to `jwks_uri`. | Yes, via issuer-aware decoder/auto-config. | May depend on metadata endpoint at bootstrap depending on version. |
| **`jwk-set-uri` only** | Fixed directly by config. | **Not inferred automatically** unless another validator is configured. | No issuer discovery needed to know the JWK URL. |
| **Both `issuer-uri` and `jwk-set-uri`** | Fixed directly; trusted config. | Yes, via issuer-aware auto-config. | Avoids discovery to locate the JWK URL; still needs JWKS when verifying uncached keys. |

If the application declares a custom `ReactiveJwtDecoder` bean, the Boot auto-config behavior above may **not automatically apply**: you must ensure issuer/audience/time/algorithm/profile validators are properly configured.

### 6.2. Do Not Pick JWKS Paths Arbitrarily

Some issuers have metadata like:

```json
{
  "issuer": "https://login.example.test/tenant-a",
  "jwks_uri": "https://keys.example.test/tenant-a/jwks.json"
}
```

The JWKS is **not required** to share the same hostname/path as the issuer if the issuer has a trusted contract for that endpoint. What matters is:

- The endpoint comes from **verified metadata** or **trusted deployment configuration**.
- The HTTPS certificate is valid and hostname-verified.
- No new URL is accepted from a Bearer token or query parameter.
- Operators confirm the URL belongs to the right realm/tenant/resource.
- Firewall/egress restrictions block arbitrary connections to internal networks.

Do not enforce "JWKS must always be on the same domain as issuer" as a protocol rule; however, a separate JWKS host must be controlled via trusted configuration.

---

## 7. Spring WebFlux: A Complete `SecurityWebFilterChain` for Study

### 7.1. Maven Dependencies

Use the Spring Boot parent/BOM to manage versions:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
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

    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

In typical Boot 3.x setups, the resource-server starter manages the dependencies required for JWT validation. Avoid overriding Nimbus/Jackson versions arbitrarily without a specific dependency-control reason. Verify the dependency tree when using a different BOM.

### 7.2. WebFlux Security Configuration

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            // Example API uses only Bearer headers, not cookie
            // sessions as credentials. Browser apps need dedicated CSRF.
            .csrf(ServerHttpSecurity.CsrfSpec::disable)

            .authorizeExchange(exchange -> exchange
                .pathMatchers(HttpMethod.GET, "/api/public/ping")
                    .permitAll()

                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders:read")

                .pathMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders:write")

                .pathMatchers("/api/admin/**")
                    .hasAuthority("SCOPE_orders:admin")

                .anyExchange().denyAll()
            )

            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Key takeaways:

- **`@EnableWebFluxSecurity`** and **`ServerHttpSecurity`** apply to the reactive stack.
- **`SecurityWebFilterChain`** protects WebFlux requests, not servlet filters.
- **`authorizeExchange`** and **`pathMatchers`** are used for reactive exchanges.
- Rules are specific by method/path; `anyExchange().denyAll()` reduces the risk of new endpoints accidentally being left open.
- `oauth2ResourceServer(...jwt(...))` enables Bearer JWT authentication.
- `csrf(...disable)` is only appropriate for stateless APIs accepting solely Bearer headers without relying on browser cookies. Applications using sessions/cookies require a separate CSRF evaluation.

A valid token with `scope="orders:write"` does not automatically receive `SCOPE_orders:read`. Scope semantics are defined by the issuer and API; never assume write implies read. And even holding `SCOPE_orders:read` does not grant permission to read another tenant's or owner's order.

### 7.3. WebFlux Configuration Does Not Mean the API Must Use HTTP Sessions

A reactive Resource Server normally operates cleanly with a stateless Bearer flow, validating the token on each request. If the application also has OAuth login/browser sessions, separate `SecurityWebFilterChain` instances by matcher and do not let a web session substitute for an API Bearer credential. `ReactiveSecurityContextHolder` stores identity in the reactive context; do not use Servlet's thread-local `SecurityContextHolder` as the user source in reactive handlers.

An application with multiple filter chains must define priority and `securityMatcher` for each chain. Do not apply `oauth2Login`/form-login to a pure Bearer API if policy forbids accepting session cookies.

---

## 8. When You Must Build `ReactiveJwtDecoder` Yourself

Spring Boot provides helpful auto-configuration. However, some cases require a custom decoder bean:

- Accepting only an explicit set of JWS algorithms.
- Adding a programmatic audience validator and custom claim validators.
- Controlling the JWKS source/HTTP client/timeouts per requirements.
- Using a static public key in a closed environment.
- Supporting multiple issuers under a specific trust policy.
- Enforcing an additional token profile such as RFC 9068.

**Remember:** The bean type is `ReactiveJwtDecoder`, not servlet `JwtDecoder`.

### 8.1. Creating a Decoder via Issuer Discovery

Example:

```java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoders;

@Configuration
public class ReactiveDecoderFromIssuerConfig {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.issuer}") String issuer) {
        return ReactiveJwtDecoders.fromIssuerLocation(issuer);
    }
}
```

Configuration:

```yaml
app:
  security:
    issuer: https://auth.example.test/realms/orders
```

`ReactiveJwtDecoders.fromIssuerLocation(...)` obtains a decoder via issuer metadata. When **registering your own decoder bean**, verify that additional requirements like `aud=orders-api` are configured on your decoder or validators; do not assume they are inferred from Boot properties normally handled by auto-configuration.

### 8.2. Creating a Decoder with JWKS URL + Issuer + Audience

When you need to avoid issuer discovery while keeping issuer/audience validation, you can build the decoder explicitly:

```java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class ExplicitReactiveJwtDecoderConfig {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.audience}") String requiredAudience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withJwkSetUri(jwkSetUri)
                // Trust allowlist decided by the server,
                // not taken from the alg field inside the JWT.
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(requiredAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Required audience is missing",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audience
            )
        );

        return decoder;
    }
}
```

`application.yml`:

```yaml
app:
  security:
    issuer: https://auth.example.test/realms/orders
    jwk-set-uri: https://auth.example.test/realms/orders/protocol/openid-connect/certs
    audience: orders-api
```

**Meaning of each protection layer:**

1. `withJwkSetUri(jwkSetUri)`: key material comes from a trusted endpoint.
2. `jwsAlgorithm(RS256)`: tokens are verified only against the algorithm chosen by the API; never blindly trust the `alg` header.
3. `JwtValidators.createDefaultWithIssuer(issuer)`: applies default time-related validators together with the issuer validator.
4. `audience` custom validator: the token must be intended for `orders-api`.
5. `DelegatingOAuth2TokenValidator`: passes the token only if all required conditions succeed.
6. After decoding, WebFlux HTTP authorization still checks scopes.

**Important:** Do not register two different `ReactiveJwtDecoder` beans from sections 8.1 and 8.2 without explicitly choosing which bean is used. When defining a custom decoder bean, Boot auto-config may back off; properties like `spring.security.oauth2.resourceserver.jwt.audiences` or other defaults will **not necessarily** be added automatically to this bean.

### 8.3. What If the Issuer Uses ES256 or RS512?

The example uses **RS256** because it is common; not all issuers use RS256. Agree on the permitted cryptographic algorithm with the AS and explicitly configure the decoder accordingly.

On builders that support it, additional allowed algorithms can be added via `jwsAlgorithm(...)`. The example merely illustrates configuration intent:

```java
NimbusReactiveJwtDecoder decoder =
    NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .jwsAlgorithm(SignatureAlgorithm.RS512)
        .build();
```

This widens the accepted set of algorithms; **do this only when you genuinely intend to trust both**. Do not write logic that reads `alg` from the token and grants "accept whichever algorithm it asks for." For EC, configure the matching algorithm/curve and key type according to your Spring Security/Nimbus version.

Never use `alg="none"`, and never allow a symmetric algorithm like `HS256` with an RSA public key via custom logic; this is a dangerous algorithm confusion attack. Key types and signature verification must be enforced by a proven cryptographic library.

### 8.4. Beyond Issuer and Audience: Token Type/Profile

A JWT with valid `iss`/`aud` can still be an **ID Token** or a JWT meant for another purpose if the issuer shares a keyset. With the RFC 9068 access token profile, there are extra requirements such as the `typ` header and profile-required claims. A WebFlux API should clearly decide:

- Which **OAuth 2.0 JWT access token** profile does it accept?
- Should it check `typ=at+jwt` if the contract requires it?
- Which claim describes the OAuth client (`client_id`), actor, or delegated user?
- How does an Authorization Code token differ from a Client Credentials token?
- Are `azp`, `client_id`, or domain-specific claims required?
- Which claims are mandatory for each token kind?

Do not assume `JwtValidators.createDefaultWithIssuer(...)` performs every RFC 9068 validation. Configuring token type and required claims may require a dedicated validator/profile-aware decoder compatible with your Spring Security version.

---

## 9. Scenario: Using a Fixed Public Key Instead of JWKS

Some systems connect to an AS over unreliable channels, or small labs/services have **a key distributed through an internal trust process**. In such cases, you can build a decoder with a static public RSA key.

### 9.1. Configuring a Decoder with an RSAPublicKey

Example:

```java
package com.example.orders.security;

import java.security.interfaces.RSAPublicKey;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class FixedPublicKeyDecoderConfig {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(RSAPublicKey trustedKey) {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withPublicKey(trustedKey)
                .signatureAlgorithm(SignatureAlgorithm.RS256)
                .build();

        // MUST attach issuer, audience, time, and token-profile validators
        // per the API contract, just like the previous custom decoder approach.
        return decoder;
    }
}
```

The snippet above illustrates the builder API and is **not yet a complete production decoder** because issuer/audience validators are not attached. You can add:

```java
OAuth2TokenValidator<Jwt> validator =
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(expectedIssuer),
        audienceValidator
    );
decoder.setJwtValidator(validator);
```

where `audienceValidator` verifies the token audience matches the API. Do not copy `withPublicKey` code into production and forget those validators.

### 9.2. Where Does a Trusted Public Key Come From?

A public key is not secret like a private key, but **its distribution source and integrity** must be protected:

- Verified from the AS or an internal key management process.
- Distributed via configuration/artifacts/secret management with clear provenance.
- Never taken from a JWT header or query parameter.
- Never fetched from an untrusted endpoint at runtime.
- Has versioning, an owner, and rotation/rollback procedures.

**A public key is not a secret, yet unauthorized modification of the trusted public key opens the door for an attacker to sign forged tokens with their own private key.** Therefore, permission to modify the trusted public key/config is a critical security privilege.

### 9.3. Trade-offs of a Static Key

| Benefits | Limitations |
|---|---|
| No JWKS network fetch needed when processing tokens. | Rotation requires deploying/distributing the new key via operations. |
| Fewer dependencies and easy to operate in a lab. | Does not automatically select across multiple keys by `kid` like a JWKS decoder. |
| Can pin a specific key with clear provenance. | A compromised key requires immediate rollout/update; risk of rejecting new tokens. |
| Easy to inspect trust root in configuration. | Unsuitable when the AS has multiple signing keys, tenants, or continuous rotation lifecycles. |

If the AS rotates keys frequently, **JWKS with old/new key overlap** is usually far more convenient. Static keys can be valid in tightly controlled systems, provided cutover and monitoring plans are in place.

---

## 10. Trust Root: What Is in JWKS and What Evidence Is Enough?

A token signed with the private key matching a public key downloaded from JWKS **only passes the signature condition**. A secure API must combine:

```text
Trusted issuer configuration
  AND trusted JWKS public key source
  AND allowed JWS algorithm
  AND valid signature
  AND iss == expectedIssuer
  AND aud contains requiredResource
  AND exp/nbf and required token claims pass
  AND token profile/type is accepted
  AND required scope/authority exists
  AND resource owner/tenant policy grants access
```

### 10.1. "Key Is in JWKS" Does Not Give Every Token Admin Access

Suppose the issuer emits a JWT:

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "aud": ["orders-api"],
  "scope": "profile email",
  "sub": "alice-123"
}
```

If the signature is valid, the token may be **authenticated**, yet `GET /api/orders/42` must still receive 403 when the route requires `SCOPE_orders:read`. And even with the scope, the service must still check permissions on the specific order.

### 10.2. Do Not Trust the JWKS of an Unauthorized Issuer

A mistake:

```java
// DO NOT USE: reading issuer from an unverified token to build a trust root.
String issuer = parseUnverifiedJwt(token).getIssuer();
ReactiveJwtDecoder decoder =
    ReactiveJwtDecoders.fromIssuerLocation(issuer);
```

An attacker can issue tokens with an issuer they own, serve a JWKS they control, and be accepted by the application if there is no allowlist. Beyond authentication bypass, calling metadata/JWKS at a token-determined URL can cause **SSRF**.

With multiple issuers, maintain an **explicit issuer allowlist**, such as onboarded tenants/providers, and select the matching decoder. Reading the issuer from the token before verification may only serve as a **hint to look up inside the allowlist**, never as a decision to trust an arbitrary issuer.

### 10.3. Do Not Automatically Trust Public Keys Fetched via Cross-Host Redirects

The JWKS URL must come from trusted config/metadata. If the HTTP client automatically follows redirects and carries credentials or redirects to an inappropriate host, evaluate risks of key injection, SSRF, and availability.

JWKS endpoints normally serve public keys, so fetching JWKS does not need a client secret; **never forward the API caller's access token to the JWKS endpoint**. Do not confuse a JWKS fetch with opaque-token introspection.

### 10.4. TLS and Trust Store

With `https://.../jwks.json`, ensure:

- Hostname/certificate chain is verified against an accepted trust store.
- Never disable certificate validation to "fix" environment errors.
- If using a private CA, distribute the CA certificate in a controlled manner.
- Restrict outbound network access to issuer/JWKS hosts.
- Configure appropriate network timeouts and response size limits.
- Never log the full Bearer JWT when a JWKS fetch fails.

An HTTP-valid JWKS endpoint compromised by an attacker can serve the attacker's public key. Therefore, TLS verification + DNS/proxy/config control is part of the trust root, not an optional optimization.

---

## 11. Key Lifecycle: `kid`, Caching, and Rotation

Modern Authorization Servers rotate private signing keys periodically or during emergencies. The Resource Server should handle key rotation without wiping all application state or taking downtime, within the bounds of configuration/library support.

### 11.1. A Healthy Rotation Process

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant JWKS as Trusted JWKS Endpoint
    participant RS as WebFlux Resource Server

    AS->>JWKS: Publish old public key K1 + new public key K2
    RS->>JWKS: Load/refresh JWKS set
    JWKS-->>RS: K1, K2
    AS->>AS: Sign new access tokens with private key K2
    AS-->>RS: JWT header kid=K2
    RS->>RS: Verify signature using trusted public K2
    Note over AS,RS: Old JWTs signed K1 may remain valid until expiry
    AS->>JWKS: Retire K1 after allowed overlap window
```

A basic rotation plan:

1. **Publish the new public key** in the JWKS before issuing tokens signed with the new private key.
2. Maintain an **overlap** of old/new public keys long enough to verify still-valid older JWTs.
3. Begin signing new tokens with the new private key and new `kid`.
4. Monitor `unknown kid` counts, JWKS refresh failures, and JWT authentication failures.
5. Remove the old public key only after the acceptance window for older tokens expires or when revocation policy requires it.
6. If a private key is compromised, emergency rotation/revocation may require rejecting even unexpired tokens; **simply swapping keys in JWKS does not automatically revoke every already-issued token** in all systems.

### 11.2. JWKS Caching Is Not an Access-Token Cache

A decoder can cache **public keys** to avoid fetching JWKS over the network on every request. This is completely different from caching token authentication results:

| Cache | What is cached | Main risk |
|---|---|---|
| **JWKS cache** | Public keys/KID metadata from trusted endpoint. | Delay in noticing newly added or retired keys. |
| **JWT access token authorization cache** (if custom-built by app) | Verification result/claims/rights of a token. | Permissions changed while the cached principal is still trusted. |
| **Introspection cache** (in opaque mode) | Active/token metadata from AS. | Delay in noticing revocation/changes. |

**A JWT Resource Server with cached JWKS still verifies every JWT**; caching public keys does not create a client session. Rotation mechanics must align with cache TTL and how the decoder refreshes when encountering an uncached `kid`. Do not assume "the library always refreshes immediately on every error"—behavior depends on cache configuration and version.

### 11.3. How Should an Unknown `kid` Be Handled?

If a JWT has `kid=K99` while the trusted JWKS currently only has `K1` and `K2`:

- The decoder may attempt to refresh the JWKS from the **trusted endpoint** per policy.
- If no matching key is found, **the signature cannot be verified** → reject the token.
- Do not call a different `jku` self-specified by the JWT to look up the key.
- Do not temporarily disable signature validation.
- Do not use "the first key in the JWKS" to verify regardless of key type/alg/policy.
- If refresh/rate limits are hit, fail closed and log the error safely.

During real key rotation, `unknown kid` can indicate a synchronization issue between the AS, CDN/JWKS cache, and RS. Fix TTL/caching headers rather than solving it by allowing unverified tokens.

### 11.4. JWKS Endpoint Network Outage

When the RS already has public key K1 cached, a JWT signed with K1 may still verify in some implementations/configurations if the cache remains valid. A JWT signed with an uncached K2 may be rejected during a JWKS endpoint outage.

Therefore:

- Do not interpret "having `jwk-set-uri`" as "not needing the network."
- Configure finite timeouts, bounded retries, and circuit breaker/egress policies as needed.
- Never allow requests through just because the AS/JWKS is temporarily unreachable.
- Monitor p95/p99 JWKS fetch latencies and cache misses, not just 401 rates.
- Run outage drills with JWTs signed by cached keys and JWTs signed by new keys.
- Do not recklessly purge valid cached keys during an issuer outage.

---

## 12. HTTP 401, 403, and JWKS Dependency Failures

A Spring Security WebFlux Resource Server distinguishes authentication from authorization.

| Scenario | Rejection step | Typical result |
|---|---|---|
| Missing Bearer token on protected endpoint | No authentication | **401 Unauthorized**, `WWW-Authenticate: Bearer`. |
| Invalid token signature | JWT verification | **401**, possibly `invalid_token`. |
| Expired token or before `nbf` | JWT validation | **401**, possibly `invalid_token`. |
| Wrong `iss` | Issuer validator | **401**. |
| Wrong `aud` | Audience validator | **401**. |
| `alg` header not in allowlist | JWS verification policy | **401**. |
| Key ID absent from trusted JWKS | Signature verification | **401** if unverified. |
| Valid token lacking `SCOPE_orders:read` | HTTP/method authorization | **403 Forbidden**, possibly `insufficient_scope`. |
| Valid token, sufficient scope, wrong owner/tenant | Object-level policy | **403** or **404** per API contract. |
| JWKS endpoint unavailable when key is needed | Dependency/authentication cannot complete | No authentication granted; exact HTTP status depends on exception mapping. |
| Bug in claim parser/decoder | Code/integration failure | Possibly **5xx**; do not pretend the token expired. |

These statuses reflect typical behavior, not a hard guarantee for every custom handler. WebFlux uses reactive security handlers such as `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler`, not servlet `AuthenticationEntryPoint`/`AccessDeniedHandler`.

### 12.1. Bearer Challenge

An HTTP 401 may look like:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

An invalid JWT may produce:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

A valid JWT lacking scope may produce:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

Per RFC 6750, not every 401 **without a token** needs `error="invalid_token"`; exact conditions and error details depend on context. Never log or echo raw JWTs in headers or error bodies.

### 12.2. Do Not Use HTTP Basic or Web Login Fallback to Rescue a Bad JWT

A Bearer-only API should not fall back to web sessions/HTTP Basic to "log in automatically" when a JWT fails, unless that is a **separate, explicit, approved, and tested** authentication policy. Frontend OIDC login capability does not authorize using an ID Token or session cookie as an API access token.

---

## 13. Testing WebFlux Security with `WebTestClient`

### 13.1. An Endpoint to Observe the Principal

A simple reactive controller:

```java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    @GetMapping("/api/identity")
    public Mono<Map<String, String>> identity(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("sub", jwt.getSubject()));
    }

    @GetMapping("/api/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }
}
```

Add the route rule `GET /api/identity → authenticated()` before `anyExchange().denyAll()`:

```java
.pathMatchers(HttpMethod.GET, "/api/identity").authenticated()
```

The controller above only illustrates receiving a JWT principal. Never return all JWT claims, scopes, secrets, or private identifiers in a production debug endpoint. With opaque tokens, the principal type may differ; do not blindly cast to `Jwt`.

### 13.2. Testing HTTP Authorization with `mockJwt()`

`spring-security-test` provides `SecurityMockServerConfigurers.mockJwt()` for WebFlux. It injects a mocked authenticated JWT into the test reactive security context:

```java
package com.example.orders.security;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OrdersAuthorizationWebFluxTest {

    @Autowired
    WebTestClient client;

    @Test
    void noBearerTokenCannotUseProtectedEndpoint() {
        client.get().uri("/api/identity")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void mockedJwtWithReadAuthorityCanReadRoute() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders:read")))
            .get().uri("/api/orders/probe")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void mockedJwtWithoutReadAuthorityIsDenied() {
        client.mutateWith(mockJwt()
                .authorities(new SimpleGrantedAuthority(
                    "SCOPE_orders:write")))
            .get().uri("/api/orders/probe")
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

**Condition:** the test application must have a `GET /api/orders/probe` endpoint; the service/fixture must permit the mocked principal to read the corresponding content. Without that controller, the 200 test cannot run as expected. Imports must match the Spring Boot version in use.

**Critical boundary:** `mockJwt()` **bypasses `ReactiveJwtDecoder` and does not check JWS signature, issuer, audience, JWKS networking, or the algorithm allowlist**. It is suitable for testing HTTP authorization. **Do not use `mockJwt()` results as proof that `issuer-uri` or `jwk-set-uri` is configured correctly.**

### 13.3. Testing JWT Validation with a Real Decoder

To verify the trust root, a separate test suite is required:

1. Generate an **RSA test keypair K1**, unrelated to any production private key.
2. Serve **public JWK** K1 from a test JWKS endpoint (local HTTP server or test HTTPS server depending on environment).
3. Configure `NimbusReactiveJwtDecoder.withJwkSetUri(...)` pointing to the trusted test endpoint.
4. Sign access tokens with **private test key** K1, header `alg=RS256`, `kid=K1`.
5. Send real Bearer JWTs through `WebTestClient`/embedded WebFlux server.
6. Verify valid issuer/audience/time succeed, and invalid conditions are rejected.

There is no need to call the production Authorization Server to run unit/integration tests; use MockWebServer/WireMock or a local server. For test TLS, use a dedicated test CA/certificate rather than disabling hostname verification in production.

### 13.4. Trust Root Test Matrix

| JWT / configuration | What to prove | Expected result |
|---|---|---|
| Valid K1 signature, valid issuer/audience/time, RS256 allowed | Decoder truly verifies. | Authentication succeeds. |
| Tampered payload with original signature | Tamper resistance. | 401. |
| JWT signed with private key outside trusted JWKS | Correct trust source. | 401. |
| Token with `kid=K999` absent from JWKS | Unknown keys are untrusted. | 401 after refresh policy if key not found. |
| Token with `jku` pointing to attacker JWKS | Does not follow key-source from untrusted header. | 401 if invalid under configured JWKS; does not fetch attacker URL. |
| JWT with `alg=HS256` or `none` | Algorithm allowlist. | 401. |
| Valid signature but different `iss` | Issuer validation. | 401. |
| Valid signature but `aud=payments-api` | Audience validation. | 401. |
| Valid signature but `exp` in the past | Timestamp validation. | 401. |
| Valid signature but `nbf` in the future | Timestamp validation. | 401. |
| ID Token instead of access token | Token type/profile boundary. | Rejected when access-token profile is enforced. |
| Valid JWT missing `SCOPE_orders:read` | HTTP authorization. | 403. |
| Valid JWT with scope, order belongs to Bob | Object authorization. | 403/404. |
| Old JWKS K1, new JWKS K1+K2 | Key rotation. | New token signed with K2 verifies after keyset refresh. |
| JWKS endpoint outage, key uncached | Fail-closed. | Does not accept unverified tokens. |
| Issuer-only with metadata endpoint unavailable at bootstrap | Startup coupling (version-dependent). | Observe actual behavior; never fall back to alternate trust. |
| Direct Issuer+JWKS, metadata discovery unavailable | Startup independence from metadata. | Does not need metadata to locate JWK URL; needs key fetch at decode time. |

Do not mechanically assert 401 for every infrastructure failure; when JWKS fetch fails, a 5xx may occur depending on the exception handler. The security invariant to prove is that **requests are never authorized from an unverified token**.

### 13.5. Using `StepVerifier` to Test the Reactive Decoder Directly

When testing `ReactiveJwtDecoder` in isolation:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import reactor.test.StepVerifier;

class ReactiveJwtDecoderTest {

    private final ReactiveJwtDecoder decoder;

    ReactiveJwtDecoderTest(ReactiveJwtDecoder decoder) {
        this.decoder = decoder;
    }

    @Test
    void validTokenProducesVerifiedClaims() {
        String signedJwt = signedTestJwtForOrdersApi();

        StepVerifier.create(decoder.decode(signedJwt))
            .assertNext(jwt ->
                assertEquals("alice-123", jwt.getSubject()))
            .verifyComplete();
    }

    @Test
    void tokenWithWrongAudienceFails() {
        String signedJwt = signedTestJwtForPaymentsApi();

        StepVerifier.create(decoder.decode(signedJwt))
            .expectError()
            .verify();
    }

    // Two helpers generating signed test JWTs with a fixture private key,
    // implemented in the actual test suite.
    private String signedTestJwtForOrdersApi() {
        throw new UnsupportedOperationException("test fixture");
    }

    private String signedTestJwtForPaymentsApi() {
        throw new UnsupportedOperationException("test fixture");
    }
}
```

This is a **skeleton** illustrating `Mono<Jwt>`/`StepVerifier`. In a real test class, the decoder must be injected/initialized via valid JUnit setup; the two helpers must actually generate RSA/EC-signed JWTs using a test key. Do not run the snippet as-is with `UnsupportedOperationException` and treat it as a complete test. Signature verification tests must include a case with a JWT signed by the wrong key or with a tampered payload.

### 13.6. Do Not Test Trust by Base64URL-Decoding the Payload

A flawed test:

```java
String issuer = parseJwtPayloadWithoutVerify(token).get("iss");
assertEquals(expectedIssuer, issuer);
```

This only proves the JWT string **self-declares** the expected issuer. An attacker can easily create a token claiming the right `iss`. Real tests must go through **`ReactiveJwtDecoder.decode(...)` and JWS verification**.

---

## 14. Multi-Issuer: Can One Application Trust Multiple Issuers?

A WebFlux Resource Server may serve multiple tenants or partners with multiple issuers. However, "multi-issuer" does not mean:

```text
Accept any JWT
  -> read unverified iss
  -> fetch that issuer's metadata/JWKS
  -> accept token if signature matches issuer it invented
```

This is an anti-pattern because an attacker can spin up their own issuer and JWKS.

### 14.1. The Right Way to Think About It

Suppose only two onboarded issuers exist:

```text
https://idp-a.example.test/realms/orders
https://idp-b.example.test/realms/orders
```

For each issuer:

- Has its own trust policy.
- Has its own trusted metadata/JWKS URL.
- Has its own permitted signing algorithms.
- Has its own audience/resource binding for `orders-api`.
- Has its own token type/profile and claim mapping.
- Has a domain identity namespace (`iss` + `sub`) and tenant permissions.
- Has its own key rotation process.

Spring Security WebFlux supports a resolver model that picks a reactive authentication manager based on an allowlisted issuer, such as APIs in the `JwtIssuerReactiveAuthenticationManagerResolver` family in compatible versions. When implementing, ensure the issuer input is only used to **select from a set of already-trusted issuers**; never build a decoder for arbitrary URLs.

### 14.2. Same `sub` Does Not Mean Same User

Issuer A has `sub=123` and Issuer B also has `sub=123`; they are not automatically the same person. When storing owners in the DB or mapping to local accounts, namespace by issuer or map to a controlled internal user ID.

### 14.3. Same JWKS Does Not Automatically Mean Same Issuer

An Authorization Server may share signing keys across multiple realms or clients. Verifying a signature with a shared public key **does not merge** those issuers into a single trust domain. The Resource Server still needs to check `iss` and `aud` per policy.

---

## 15. WebFlux Reactive Specifics: Do Not Accidentally Block the Event Loop

JWT verification using RSA/EC and JWKS fetching have cost. Spring Security's reactive decoder is designed to use non-blocking APIs where appropriate for network I/O; customizations can break reactivity if they perform blocking I/O on the event loop.

### 15.1. What to Avoid

```java
// DO NOT USE in reactive authentication flow:
Mono<Jwt> decode(String token) {
    Jwt jwt = blockingHttpClient.getJwksAndVerify(token);
    return Mono.just(jwt);
}
```

Making synchronous HTTP calls or reading large files inside a method running on an event-loop thread can severely degrade request latency and throughput. Also avoid calling `.block()` inside a reactive authentication filter to wait for JWKS/introspection.

### 15.2. Distinguish Bean Initialization from Request Processing

Reading a small PEM public key **once at startup** to initialize a decoder behaves differently from performing blocking file/network reads on **every request**. Startup dependencies should still be measured and controlled, however. For `jwk-set-uri`, let the reactive decoder library use an appropriate HTTP client/cache, or customize the right extension point to preserve non-blocking semantics.

### 15.3. Reactor Context for Principal

In WebFlux:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentSubject() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .map(authentication -> authentication.getName());
}
```

This illustrates retrieving authentication from the **Reactor Context**, rather than a static "last user" variable. When using `@AuthenticationPrincipal Jwt` in a controller, the framework injects the appropriately verified JWT; do not decode the raw JWT manually in the controller.

If using async tasks, thread pools, or context switches, design propagation explicitly so one request's principal never leaks into another.

---

## 16. Avoiding Common Configuration Mistakes

### Mistake 1 — Configuring Only `jwk-set-uri`, Forgetting `iss`

A token signed with the right keyset but an unexpected `iss` may pass if no issuer validator is configured. Add `issuer-uri` or `JwtValidators.createDefaultWithIssuer(...)` in custom decoders.

### Mistake 2 — Configuring Only `issuer-uri`, Forgetting Audience

A token from another API sharing the same issuer/keyset may be accepted. Add `audiences` or an audience validator matching the token contract.

### Mistake 3 — Accepting an ID Token as an Access Token

An OIDC client's ID Token may be signed by the same keys. The API must validate the right `aud` and access-token type/profile, rather than relying on `sub` or signature alone to conflate the two token kinds.

### Mistake 4 — Fetching the JWKS URI from the JWT's `jku`

An attacker can point to a keyset they own. Use only configured/allowlisted key sources over verified HTTPS.

### Mistake 5 — Letting the JWT's `alg` Decide What Is Permitted

The JWS header is unverified data. The decoder needs an algorithm allowlist; never accept `none` or allow algorithm confusion.

### Mistake 6 — Hardcoding an Immutable `kid`

AS rotation to a new key causes valid tokens to be rejected. Design JWKS refresh and overlap; pin the **trust source and algorithms**, not just a single key ID when the issuer rotates keys.

### Mistake 7 — Using a Public Key Without Checking Provenance

A public key downloaded from an attacker's host will verify the attacker's tokens. A public key is not secret, yet **the integrity of the key source is critically important**.

### Mistake 8 — Confusing Reactive Decoders with Servlet Decoders

WebFlux requires `ReactiveJwtDecoder`, `ServerHttpSecurity`, and `SecurityWebFilterChain`. Do not add `HttpSecurity`/`JwtDecoder` and assume reactive requests are protected as intended.

### Mistake 9 — Writing a Decoder Bean and Forgetting Validators

When defining a custom `ReactiveJwtDecoder`, Boot may not automatically add audience/issuer validators as it does with auto-configuration. Verify everything explicitly and test tokens with wrong issuer/audience.

### Mistake 10 — Accepting Any Issuer via a Dynamic Resolver

Reading `iss` from an unverified token may be used as a hint **only when matched against an allowlist**. Never fetch keysets/metadata from arbitrary URLs supplied by the token.

### Mistake 11 — Checking Signature Without Checking Scope/Owner

A validly signed JWT only proves an issuer assertion. The API must still enforce scope authorities, tenant/owner, ACLs, and business rules.

### Mistake 12 — Clearing the JWK Cache During an Issuer Outage and Falling Back

If no trusted public key is available, reject unverified tokens. Never "keep the system available" by disabling signature checks or trusting unverified claims.

### Mistake 13 — Testing Only with `mockJwt()`

Mock JWT bypasses the decoder. Include signed-JWT integration tests and a local JWKS server to test the real trust root.

### Mistake 14 — Trusting JWTs from HTTP Query Parameters

Bearer tokens should be sent via the `Authorization` header; avoid query parameters because they leak into logs, browser history, and gateways. Configure bearer extraction strictly rather than accepting tokens from arbitrary channels.

### Mistake 15 — Logging Raw JWTs on JWKS Errors

A JWT is a Bearer credential and its payload may contain PII. Log a reason code, issuer configuration ID, request ID, and upstream HTTP status; never log the Authorization header, token, private key, or sensitive JWKS details.

---

## 17. Runbook: Tokens Signed with a New Key and API Starts Returning 401

A common incident after rotation:

```text
Yesterday:
  AS signs with K1
  JWKS contains K1
  Resource Server verifies K1 tokens

Today:
  AS signs with K2
  JWKS cache in RS still contains K1
  API receives JWT kid=K2
  Verification fails -> 401
```

Investigation steps:

1. **Confirm symptoms:** rising Bearer 401 rate, correlated with a new `kid`, affecting one issuer/region or everywhere?
2. **Check configured JWKS source:** do `issuer-uri` and `jwk-set-uri` point to the right realm/tenant? Never change paths based on JWT input.
3. **Check published metadata:** does the trusted JWKS contain the K2 public key yet? Did the AS publish the new key before signing with it?
4. **Check cache/CDN:** is the JWKS URL returning different responses across nodes/regions/cache layers?
5. **Check algorithms:** does K2 match the key type, `use`, and JWS algorithm accepted by the decoder?
6. **Check issuer/audience:** do new tokens have a different `iss`/`aud` after migration? Do not relax validators without an agreed contract.
7. **Check TLS/network:** are certificates/hostnames and outbound access to JWKS valid?
8. **Check other failure causes:** tokens might be expired, fail `nbf`, or be rejected by profile; do not blame every 401 on key rotation.
9. **Recover per policy:** fix AS overlap publishing, safely refresh JWKS, or roll back the signing key; never disable signature checks.
10. **Prevent recurrence:** staging rotation drills, `unknown kid`/JWKS latency metrics, alerts before AS cutover, rollback plan.

### 17.1. When a Private Signing Key Is Compromised

This is more severe than routine rotation. If private key K1 is compromised, an attacker can sign forged JWTs with K1 for as long as the Resource Server trusts public key K1. A key revocation/token-acceptance restriction process is needed per policy, potentially requiring **removing K1 from JWKS/cache immediately** and accepting the impact on older tokens.

Do not simply "wait for tokens to expire" if the threat model cannot tolerate it. Coordinate across the issuer, API owners, gateways, and Resource Servers sharing the keyset, and execute revocation/incident response.

---

## 18. Trust Configuration Deployment Checklist

Before deploying a reactive JWT Resource Server to production:

| Item | What to verify |
|---|---|
| **Web stack** | Correct WebFlux, `SecurityWebFilterChain`, `ServerHttpSecurity`, and `ReactiveJwtDecoder`. |
| **Issuer** | `issuer-uri` exactly matches the `iss` of permitted tokens. |
| **JWKS source** | `jwk-set-uri` from trusted metadata/config, valid HTTPS, never from token header. |
| **Audience** | `orders-api` enforced; tokens issued for other clients/APIs rejected. |
| **Algorithm** | Only RS256/ES256/... per contract; no dynamic trust of `alg`. |
| **Key rotation** | JWKS overlap, cache refresh/TTL, unknown `kid`, and incident rollback. |
| **Token profile** | Access token, not confused with ID Token, required claims/token type. |
| **Time claims** | `exp`/`nbf` and clock skew policy. |
| **HTTP policy** | Clear scope/authority by path/method; deny-by-default. |
| **Domain policy** | Owner/tenant/business authorization. |
| **Network safety** | TLS/hostname, egress allowlist, timeouts, bounded retries where appropriate. |
| **Startup coupling** | Know whether issuer-only requires metadata discovery at bootstrap. |
| **Custom decoder** | Explicitly attach issuer/audience/required validators when Boot auto-config backs off. |
| **Reactive behavior** | Do not block the event loop in custom authentication. |
| **Error semantics** | 401 invalid token, 403 insufficient scope, fail-closed on dependency failure. |
| **Tests** | `mockJwt()` for authorization; signed JWT + local JWKS for signature/trust. |
| **Observability** | Correlation ID and error codes; never log raw tokens, private keys, or PII. |
| **Multi-issuer** | Issuer allowlist only; namespace subject by issuer. |

### 18.1. A Pragmatic Configuration Decision

If the Authorization Server supports metadata discovery and the environment accepts startup coupling, **`issuer-uri`** is usually the most concise configuration. If you need to eliminate metadata discovery from bootstrap while keeping issuer binding, use **`issuer-uri + jwk-set-uri`** with the appropriate audience. If using a **custom decoder bean**, configure all validators explicitly since you can no longer rely on Boot auto-configuration defaults.

If using a **fixed public key**, do so only with a clear operational reason and documented rotation/revocation procedures.

---

## 19. A Concept Map to Remember

```mermaid
flowchart TD
    A["Trusted Resource Server configuration"] --> B["issuer-uri: expected issuer"]
    A --> C["jwk-set-uri: trusted key endpoint"]
    A --> D["audience: expected resource"]
    A --> E["JWS algorithm allowlist"]
    C --> F["JWKS public keys"]
    F --> G["Verify JWT signature"]
    E --> G
    B --> H["Validate iss"]
    D --> I["Validate aud"]
    G --> J{"Signature valid?"}
    H --> K{"Claims/profile valid?"}
    I --> K
    J -->|No| R["Reject authentication"]
    K -->|No| R
    J -->|Yes| L["JWT verified + token validators"]
    K -->|Yes| L
    L --> M["SCOPE_ authorities & reactive route policy"]
    M --> N["Owner/tenant/domain authorization"]
    N --> O["Permit or deny per policy"]
```

**Remember four distinctions:**

1. **`issuer-uri` identifies the issuer**, not the public key.
2. **`jwk-set-uri` provides trusted public keys**, not proof of audience.
3. **`kid` and `alg` are technical selection fields in the JWS header**, not authority to choose the trust root.
4. **Successful JWT verification does not mean access to every resource** — scopes and owner/tenant checks are still required.

---

## 20. References

- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): issuer metadata, JWKS, `ReactiveJwtDecoder`, and HTTP authorization.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity`, `SecurityWebFilterChain`, and reactive configuration.
- [Spring Security API — NimbusReactiveJwtDecoder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html): JWK set, public key builders, and validators.
- [Spring Security API — ReactiveJwtDecoders](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/ReactiveJwtDecoders.html): creating a decoder from issuer location.
- [Spring Security — Reactive Tests](https://docs.spring.io/spring-security/reference/reactive/test/index.html): `WebTestClient` and testing security context.
- [Spring Boot — OAuth 2.0 Resource Server Properties](https://docs.spring.io/spring-boot/reference/web/spring-security.html): Boot property bindings, version-dependent.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): JWK/JWK Set structure, `kty`, `kid`, and key parameters.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): JWS header, signature, and algorithms.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518.html): RS256, ES256, and JOSE algorithms.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): `iss`, `sub`, `aud`, `exp`, `nbf`, `iat`.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): issuer metadata, endpoints, JWKS URI.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OIDC provider metadata discovery.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): access token purpose and profile, avoiding ID Token confusion.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): issuer/audience, algorithm confusion, and JWT trust boundaries.
- [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer requests and `WWW-Authenticate` responses.

**Conclusion:** When configuring a JWT Resource Server on WebFlux, start from a **trusted issuer**, specify a **trusted JWKS URL**, restrict **JWS algorithms**, validate **issuer/audience/timestamps/token profile**, and only then map scopes and enforce resource permissions. `issuer-uri`, `jwk-set-uri`, and public keys play distinct roles yet must together form a **chain of trust independent of client-supplied data**. In reactive code, use `ReactiveJwtDecoder` and `SecurityWebFilterChain`, and test real signature verification with signed JWTs/JWKS rather than mocking authorities alone.
