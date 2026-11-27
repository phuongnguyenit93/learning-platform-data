# Replacing the Default Decoder While Preserving Required Checks

In **Spring Security OAuth 2.0 Resource Server**, `JwtDecoder` is the component that turns a Bearer JWT string from an HTTP request into a `Jwt` object **verified against the API's policy**. Many applications need only declare `issuer-uri` to let Spring Boot/Spring Security auto-create a decoder; however, when you need to change the JWK source, signing algorithm, HTTP client configuration, timeouts, or custom audience checks, you may need to **replace the default decoder**.

The most important point: **replacing how the decoder is constructed must not drop the checks protecting the Resource Server**. A JWT's JSON can be decoded while still being untrustworthy; a signature can be valid while the token is expired, from the wrong issuer, or meant for another API. A custom decoder must preserve all relevant trust conditions and return a `Jwt` only when the token meets the API's contract.

This lesson belongs to the **JWT Decoding and Verification** section of the *Spring Security OAuth 2.0 OIDC Resource Server* module, focusing on **Servlet/Spring MVC** applications while contrasting the equivalent approach in WebFlux. URIs, audiences, tokens, and system names below are illustrative examples only.

## 1. Where does the decoder sit in the authentication chain?

A client sends an access token:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders-api.example.test
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

In a Servlet Resource Server, the typical JWT processing flow is:

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["BearerTokenAuthenticationToken"]
    C --> D["AuthenticationManager / ProviderManager"]
    D --> E["JwtAuthenticationProvider"]
    E --> F["JwtDecoder"]
    F --> G["Verify JOSE/JWS, signature, and trusted key source"]
    G --> H["OAuth2TokenValidator: iss, exp, nbf, aud, ..."]
    H --> I["Verified Jwt"]
    I --> J["JwtAuthenticationConverter"]
    J --> K["JwtAuthenticationToken + GrantedAuthority"]
    K --> L["SecurityContext / Authorization"]
    L --> M["Controller if authorized"]
~~~

`JwtDecoder` is primarily responsible for **verifying the token and producing a trusted JWT object**. `JwtAuthenticationConverter` then converts verified claims into an `Authentication` and `GrantedAuthority` instances, such as mapping `scope="orders.read"` to `SCOPE_orders.read`. `authorizeHttpRequests` or `@PreAuthorize` then enforces permissions.

Therefore, distinguish two customization directions:

| Need | Component to replace |
|---|---|
| Selecting the right JWK Set/public key and signing algorithm | `JwtDecoder` / builder or decoder's JWK source |
| Validating `iss`, `aud`, `exp`, `nbf`, and mandatory security claims | `OAuth2TokenValidator<Jwt>` integrated into the decoder |
| Changing principal name from `sub` to another claim | `JwtAuthenticationConverter` |
| Mapping `scope`/`scp`/`roles` into authorities | `JwtGrantedAuthoritiesConverter` or a custom converter |
| Requiring `SCOPE_orders.read` on an endpoint | `SecurityFilterChain` and HTTP authorization |
| Checking resource ownership/tenant | Service/domain-level authorization |

**Never fix a wrong audience by editing the converter**, because the converter runs only after authentication. Nor should you replace the decoder just to add roles when the real task is authority mapping.

## 2. What can the default decoder do?

Example Spring Boot Resource Server using Spring MVC:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

In `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

When auto-configuration conditions are met and the application has not supplied a replacement decoder bean, Spring Boot can create a `JwtDecoder` based on the issuer. Spring Security can use the issuer's discovery metadata to locate the JWK Set, verify signatures, and execute related validators.

An illustrative JWT access token has claims:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1924988400,
  "nbf": 1924988400,
  "exp": 1924992000
}
~~~

The payload above **is not a signed token** and cannot be used as a real credential. For an issuer-configured decoder, key default checks typically include:

- **JWS signature and algorithm**: the token must be signed with an algorithm and key matching the configured trusted source.
- **Issuer (`iss`)**: the token's issuer value must match the trusted issuer.
- **Validity timeframe (`exp`, `nbf`)**: reject tokens that are expired or not yet valid, accounting for accepted clock skew.
- **Other token profile/JOSE requirements**: may vary by Spring Security version and how the decoder is initialized, such as validating the `typ` header.

**Audience (`aud`) must be checked intentionally** for your API. Merely declaring an issuer does not prove a token was issued for the right API. Some Spring Boot versions provide a property or mechanism to configure audiences; if you define a custom decoder yourself, ensure the audience validator remains applied.

### Security constraints to consider preserving

| Condition | Target checked | Harm if omitted |
|---|---|---|
| Valid JWS signature | Integrity and origin | Attackers edit claims and escalate privileges |
| Keys fetched from a trusted place | JWK Set/key pinning per issuer | Tokens select attacker-chosen keys |
| Allowed algorithm | `alg` and JOSE header processing | Unapproved signing schemes accepted |
| Exact `iss` | API's trusted issuer | Tokens from another tenant/issuer accepted |
| `exp` and `nbf` | Time validity | Expired or premature tokens accepted |
| Matching `aud` | Permitted target API/resource | Billing API tokens accepted by Orders API |
| Token type/profile | Access token vs. ID token, `typ` per profile | Wrong-purpose tokens misused |
| Other mandatory claims | Tenant, client, grant, token age... per contract | Validly signed token used out of context |

Not every claim is enforced automatically by Spring Security in every version. The **token contract** must dictate which requirements are mandatory for your application. For RFC 9068 JWT access token profiles, specific profile rules differ from generic JWTs; configure matching validators if the API relies on that profile.

## 3. When do you genuinely need to replace `JwtDecoder`?

| Deployment requirement | Appropriate approach |
|---|---|
| Trusting one issuer with default configuration | Use `issuer-uri`; avoid unnecessary customization |
| Fixed JWK Set URL without startup discovery dependence | Use appropriate `jwk-set-uri` config or a custom decoder with an issuer validator |
| Dedicated audience for Orders API | Add audience validation via supported API/property |
| Issuer signs with a non-default algorithm | Configure allowed JWS algorithms on the decoder |
| Custom timeout, proxy, HTTP client, or caching for JWK Set | Customize builder/HTTP client/JWK source per your version's API |
| Combining issuer, audience, token type, and custom claims | Decoder + intentionally composed `OAuth2TokenValidator<Jwt>` |
| Multiple trusted issuers with separate JWK Sets | Consider `AuthenticationManagerResolver`, one decoder/policy per issuer |
| Only changing authorities derived from `scope`/`roles` | Keep the decoder, replace `JwtAuthenticationConverter` |

When “replacing the decoder”, know **which mechanism is currently providing the default decoder**. The application may be using Spring Boot auto-configuration, `issuer-uri` configuration, a standalone `JwtDecoder` bean, or a decoder attached directly in the DSL. If creating a new decoder, explicitly list which validation policies must be re-applied.

## 4. Three ways to attach a decoder and their precedence

### 4.1. Letting Spring Boot create the decoder

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
~~~

And use:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
        .build();
}
~~~

In the method above, import `HttpSecurity`, `SecurityFilterChain`, `@Bean`, and static `Customizer.withDefaults` accordingly. This is the simplest case where Boot supplies the decoder from configuration.

### 4.2. Declaring a custom `JwtDecoder` bean

~~~java
@Bean
JwtDecoder jwtDecoder() {
    // Build your own decoder, key source, and validators here.
}
~~~

When the application supplies a `JwtDecoder` bean, Spring Boot typically **backs off** and does not create its default decoder of the same kind. The new bean is used by the Resource Server when HTTP security is configured to resolve the decoder from the ApplicationContext. **Previous properties are not automatically wired as validations onto the bean you return**: configure them directly in code or via centralized app-managed config.

### 4.3. Attaching a decoder directly in the Resource Server DSL

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
    jwt.decoder(customJwtDecoder)
));
~~~

This snippet uses the Servlet `HttpSecurity` API. The decoder is attached **directly** to that filter chain. Avoid maintaining two different decoder configurations without knowing which one a chain uses. When multiple `SecurityFilterChain`s exist, each chain can use its own matcher/decoder; control ordering and scope so no chain protects an endpoint with a weaker token policy than intended.

**Practical rule:** choose one clear integration point per filter chain. If defining an application-wide decoder bean, `jwt(withDefaults())` is usually enough; if attaching directly via `jwt.decoder(...)`, ensure that instance carries all required validators.

## 5. Safe example: replacing the decoder while keeping issuer/time and adding audience

Suppose the Orders API contract is:

~~~text
Trusted issuer:  https://login.example.test/realms/company
Trusted JWKS:    https://login.example.test/realms/company/protocol/openid-connect/certs
Expected aud:    orders-api
Allowed JWS alg: RS256
Required scope:  orders.read for GET /api/orders/**
~~~

Here the JWK Set URL must come from the **trusted issuer's** documentation/metadata. Never guess a JWK URL by arbitrary string concatenation if the issuer does not publish that exact path.

### 5.1. Using dedicated properties for an application-managed decoder

~~~yaml
app:
  security:
    jwt:
      issuer: https://login.example.test/realms/company
      jwk-set-uri: https://login.example.test/realms/company/protocol/openid-connect/certs
      audience: orders-api
~~~

`app.security.jwt.*` are **custom properties defined by this example**, not official Spring Boot auto-configuration properties. This avoids configuring two out-of-sync issuer sources when you supply your own `JwtDecoder` bean.

### 5.2. Creating `NimbusJwtDecoder` with explicit validators

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class OrdersJwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        // Preserve default checks for timestamps and exact issuer.
        OAuth2TokenValidator<Jwt> defaultsAndIssuer =
            JwtValidators.createDefaultWithIssuer(issuer);

        // Add audience of the current Resource Server.
        OAuth2TokenValidator<Jwt> requiredAudience = jwt -> {
            if (jwt.getAudience() != null
                    && jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience does not include this API",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultsAndIssuer,
                requiredAudience
            )
        );

        return decoder;
    }
}
~~~

This example uses modern Spring Security Java APIs; exact builder and validator differences can depend on your application's Spring Security version.

**Why does this approach preserve the required conditions?**

1. `NimbusJwtDecoder.withJwkSetUri(jwkSetUri)` selects a **trusted public key source**. The token cannot choose an unknown JWK Set via headers.
2. `jwsAlgorithm(SignatureAlgorithm.RS256)` configures the signing algorithm per the example contract. For systems using multiple algorithms, define an explicit allowlist and verify the exact builder semantics of your version.
3. `JwtValidators.createDefaultWithIssuer(issuer)` reuses the appropriate default validation set, including timestamps and issuer. This keeps manual decoder creation from accidentally omitting those constraints.
4. `requiredAudience` requires `aud` to contain `orders-api`, rejecting tokens without an audience or meant for another Resource Server.
5. `DelegatingOAuth2TokenValidator` combines the checks; a token must pass every validator, not just one.
6. `setJwtValidator(...)` is called **after** the builder builds the decoder. This method sets a new validator on the decoder, so include all validators you need to keep inside the new composite validator.

**Note on `setJwtValidator`:** this operation **replaces the validator** attached to the decoder; it is not an “append” operation that implicitly preserves whatever validators the instance previously held. Calling only:

~~~java
decoder.setJwtValidator(requiredAudience);
~~~

risks **losing the default issuer/timestamp validations** that must be preserved. That is a major security bug when replacing `JwtDecoder`.

### 5.3. Wiring the decoder into HTTP security

With the `JwtDecoder` bean above, the security chain can be written as:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class OrdersApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

Spring Security retrieves the `JwtDecoder` bean from the context; issuer/time/audience verification occurs **before** mapping scopes and checking `SCOPE_orders.read`. In real applications, reading individual orders must also check owner/tenant; scope does not automatically grant access to every record.

This configuration is for an API **using solely Bearer JWTs for these requests**. If the application also offers cookie/session-based login, design CSRF and separate filter chains according to your application model. The example does not disable CSRF automatically so you do not mistake that for a requirement when replacing a decoder.

### 5.4. An equivalent approach via issuer discovery

If you prefer the decoder to fetch metadata/JWK Set from the trusted issuer rather than configuring a separate JWK URI, replace initialization with:

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation(issuer)
    .jwsAlgorithm(SignatureAlgorithm.RS256)
    .build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        requiredAudience
    )
);
~~~

This snippet is an **alternative to the initialization and validator-attachment block in section 5.2**, not a standalone bean. It continues to rely on the trusted issuer and can perform discovery to locate the JWK Set; network/cache initialization characteristics depend on version and deployment mechanism. If the system must avoid discovery at startup, a known JWK Set URI is an option.

**Do not conflate key source and issuer:** `withJwkSetUri(...)` knows where to fetch keys, **yet does not prove `iss` is valid**. `JwtValidators.createDefaultWithIssuer(...)` is what enforces the issuer constraint when using a direct JWK URI.

## 6. Which validators must a decoder preserve?

### 6.1. Exact issuer: avoid loose string matching

Example trusted issuer:

~~~text
https://login.example.test/realms/company
~~~

These values are **not equivalent** under the issuer contract:

~~~text
https://login.example.test/realms/personal
https://login.example.test/realms/company/
https://login.attacker.test/realms/company
~~~

In systems with multiple tenants or realms, sharing a domain or IdP host does not mean tokens from every issuer should be accepted. `JwtValidators.createDefaultWithIssuer(issuer)` enforces the exact issuer inside the decoder.

Never use logic like:

~~~java
// ANTI-PATTERN: overly permissive issuer check
boolean trusted = jwt.getIssuer() != null
    && jwt.getIssuer().toString().contains("login.example.test");
~~~

`iss` comes from the token; verify the signature and match against the configured issuer. Matching must follow the official issuer contract—never use substring matching or strip tenant paths.

### 6.2. Time: `exp`, `nbf`, and clock skew

In a JWT:

- `exp` is when the token expires; after this timestamp the token is rejected, minus defined clock skew tolerance.
- `nbf` is when the token becomes valid; before that time the token must be rejected.
- `iat` is when the token was issued; it is **not synonymous** with expiration or not-before time.

`JwtValidators.createDefaultWithIssuer(issuer)` preserves Spring Security's default timestamp checking. For profiles requiring mandatory time claims such as `exp`, verify explicitly whether the profile and validator require the claim to **exist** or only check it when present.

To require access tokens to contain `exp`, compose an extra validator:

~~~java
OAuth2TokenValidator<Jwt> requireExpiry = jwt -> {
    if (jwt.getExpiresAt() != null) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Access token must contain exp",
            null
        )
    );
};
~~~

Then combine with defaults/issuer and audience:

~~~java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        requiredAudience,
        requireExpiry
    )
);
~~~

This replaces the `setJwtValidator` line from the earlier example. It assumes `decoder`, `issuer`, and `requiredAudience` were already created in the same configuration. If adding a **maximum token age** policy, build a dedicated validator using `iat` and current time, explicitly handling missing `iat`, future values, and clock skew.

**Clock skew is not infinite.** Servers can drift slightly; widening tolerance too far lets expired or premature tokens remain accepted longer than intended. When replacing the default timestamp mechanism, specify an explicit tolerance and system clock synchronization rather than disabling the validator.

### 6.3. Audience is the set of allowed token recipients

Suppose there are two APIs:

~~~text
Orders API:  aud = orders-api
Billing API: aud = billing-api
~~~

Token:

~~~json
{
  "iss": "https://login.example.test/realms/company",
  "aud": ["billing-api"],
  "scope": "orders.read"
}
~~~

This token **does not belong to the Orders API**, even with a valid issuer and signature, or even if the scope claim contains `orders.read`. The audience validator in section 5 rejects it before `JwtAuthenticationConverter` and HTTP rules inspect scopes.

The JWT `aud` claim can be a single string or an array of strings. `Jwt.getAudience()` exposes audiences as a list so resource checks are clearer. The example policy accepts when the list contains `orders-api`. If an API forbids multi-audience tokens, add policy checking audience count/values per contract.

### 6.4. Checking token type and avoiding ID token vs. access token confusion

OpenID Connect defines **ID tokens** for OIDC clients. An OAuth 2.0 Resource Server must validate **access tokens** intended for APIs. Both can be JWTs from the same issuer, so never conclude “valid signature = valid token type”.

Some systems follow the **RFC 9068** JWT access token profile with a JOSE `typ` header like `at+jwt`; others use proprietary token profiles. Example JOSE header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-01",
  "typ": "at+jwt"
}
~~~

When an API requires RFC 9068, validate **token type/profile** in the manner supported by your running Spring Security version. Nimbus's `typ` header validation and profile validators can depend on builder/version; use profile-aware APIs where available and never assume a claim-checking lambda automatically overrides JOSE `typ` checks that ran earlier.

Do not force `typ=at+jwt` across **every** Resource Server if the Authorization Server does not actually emit that profile. Tightening must reflect the issuer contract; omitting token-type checks must never let an ID token pass as an access token.

### 6.5. Custom claims: client, tenant, grant, and access permissions

An API may enforce additional conditions:

| Claim/metadata | Possible application requirement | Notes |
|---|---|---|
| `client_id` | Token limited to allowlisted clients | Understand how the issuer emits the claim |
| `tenant_id` | Token tenant belongs to permitted set | Does not replace data ownership checks in services |
| `azp` | Authorized party per certain profiles | Not present by default in every OAuth access token |
| `jti` | Token identifier for audit/revocation | Presence of `jti` does not prove token is unrevoked |
| `iat` | Token does not exceed maximum age | Requires time validator with explicit clock skew |
| `scope` / `scp` | Operation permissions | Usually handled by authority converter and authorization rules |

If a claim governs **initial token acceptance** (such as audience, token type, or issuer), put it in a **validator**. If a claim describes permissions for rules, the converter is the right place. If a rule concerns specific records, enforce it in business authorization.

## 7. JWK source and algorithms: replacing the decoder must not alter the trust model

### 7.1. `alg` and `kid` values are not trust policies

A signed JWT typically has three parts:

~~~text
BASE64URL(JOSE_HEADER).BASE64URL(CLAIMS).BASE64URL(SIGNATURE)
~~~

Example header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-01"
}
~~~

`kid` helps the decoder find the right key within the **already trusted key set**. `alg` declares the algorithm claimed for verifying the token. However, both header and claims initially constitute **unauthenticated data**: the decoder must never let a token choose an issuer or JWK Set location outside policy.

Risks arise if the application:

- Accepts algorithm `none` or an unapproved algorithm.
- Trusts keys sent by an attacker in JWT headers or un-allowlisted `jku`/`x5u` URLs.
- Switches from asymmetric signature verification to an arbitrary secret without evaluating the token contract.
- Fetches a JWK Set from an endpoint specified by the client-supplied token, creating SSRF risk and accepting unknown key sources.
- Merely Base64URL-decodes JSON and constructs a `Jwt` without verifying the JWS signature.

### 7.2. JWK Set URI and issuer must share the same trust boundary

With `NimbusJwtDecoder.withJwkSetUri(...)`, the application explicitly chooses the endpoint hosting public keys. Obtain that URL from the **approved issuer's** metadata/specification, use HTTPS, and apply appropriate network restrictions.

~~~text
Trusted issuer:
  https://login.example.test/realms/company

Trusted JWKS:
  https://login.example.test/realms/company/protocol/openid-connect/certs

Expected audience:
  orders-api
~~~

Declaring a JWK Set URL **does not automatically add issuer validation** if a custom decoder omits the validator. Conversely, checking an issuer claim without verifying a trusted signature has no security value: forged tokens can mimic a real issuer's `iss`.

### 7.3. Reading metadata from a trusted issuer

When using discovery, Spring can fetch the issuer's metadata and locate the corresponding JWK Set. Safe conditions:

1. The input issuer must be **pre-configured/allowlisted**.
2. Metadata and `jwks_uri` must be retrieved over a trusted mechanism (HTTPS, TLS verification, and trusted origin).
3. Accepted algorithms/keys obey API policy.
4. After signature verification, validators must still check `iss`, `aud`, lifetime, and required claims.

Never build “dynamic issuers” by reading an arbitrary `iss` claim from an unverified token and calling discovery on that URI. Multi-issuer setups require a dedicated **trusted registry**.

### 7.4. Static keys instead of a dynamic JWK Set

Some offline environments or specialized integrations pre-deploy public keys. The decoder has a public-key builder, for instance:

~~~java
// publicKey is an RSAPublicKey obtained from a trusted source.
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withPublicKey(publicKey)
    .build();

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        requiredAudience
    )
);
~~~

`publicKey` and `issuer` here are system-controlled values, not taken from the request payload. When using a static key, establish a **key rotation** process and update keys on schedule; JWTs signed with a new issuer key will be rejected if the app still trusts only the old key.

There is no requirement to fetch JWKs on every request when using a JWK Set: implementations normally cache keys and refresh per HTTP client/JWK source mechanisms. Confirm **TTL, timeout, and refresh policies** for your Spring Security/Nimbus version.

## 8. Combining `issuer-uri` and `jwk-set-uri` in Spring Boot

If the sole goal is **declaring a known JWK URI to avoid startup discovery**, you do not necessarily have to write a decoder bean:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/company
          jwk-set-uri: https://login.example.test/realms/company/protocol/openid-connect/certs
~~~

In supported Spring Boot/Spring Security configurations, the application knows the JWK Set address up front while still performing issuer validation via `issuer-uri`. This helps when the Authorization Server is unavailable at startup, though **it does not remove dependence on the JWK endpoint when fetching uncached keys**.

If you need audience validation and your Spring Boot version provides the `audiences` property, prefer the official property after verifying your version. Otherwise, add a custom validator via the framework's supported APIs. Never assume a property is supported across all versions.

**Comparing configuration styles:**

| Approach | Who builds the decoder | Who handles validation? |
|---|---|---|
| Plain `issuer-uri` | Auto-config/Spring Security | Framework provides default issuer/time/crypto; API adds extra required claims |
| `issuer-uri` + `jwk-set-uri` | Auto-config/Spring Security | Framework retains issuer context; API checks audience/custom policies |
| `JwtDecoder` bean using `withJwkSetUri` | Application | Application must wire all default validators, issuer, and required claims |
| Decoder attached directly via `jwt.decoder(...)` | Application per chain | That decoder must self-contain crypto + validators; do not expect other beans/properties to patch it |

Exact APIs and precedence can vary across Spring Security/Spring Boot versions. When using multiple config sources, maintain a single source of truth for issuer/audience values so the API never runs with a different policy than documented.

## 9. Preserving validators when adding more requirements

Suppose beyond issuer/audience, the API must ensure the token's `client_id` claim belongs to an allowed client list. Depending on the issuer contract, add a validator:

~~~java
Set<String> allowedClients = Set.of(
    "web-orders-client",
    "orders-mobile-client"
);

OAuth2TokenValidator<Jwt> allowedClientValidator = jwt -> {
    String clientId = jwt.getClaimAsString("client_id");
    if (clientId != null && allowedClients.contains(clientId)) {
        return OAuth2TokenValidatorResult.success();
    }
    return OAuth2TokenValidatorResult.failure(
        new OAuth2Error(
            "invalid_token",
            "Client is not allowed for this API",
            null
        )
    );
};
~~~

This snippet requires importing `java.util.Set` alongside `OAuth2TokenValidator`, `OAuth2TokenValidatorResult`, `OAuth2Error`, and `Jwt` as in section 5. Combine all into one validator:

~~~java
decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        requiredAudience,
        allowedClientValidator
    )
);
~~~

`client_id` here is a claim **guaranteed by the issuer in the access token profile**; do not assume every Authorization Server emits it. In particular, never use an unverified request parameter to decide which clients are permitted.

### When composing multiple validators

~~~text
JwtDecoder
   ├── Verify JWS and algorithm/key
   └── DelegatingOAuth2TokenValidator
         ├── Defaults + issuer
         ├── Audience orders-api
         └── Client allowlist (per contract)
                ↓
         Return Jwt only when valid
~~~

If any condition fails, the decoder does not return a verified JWT to `JwtAuthenticationProvider`. Only after passing full authentication does Spring Security map the principal and authorities to evaluate `hasAuthority(...)`.

### Be careful when stacking timestamp validators

To replace the default clock skew with a specific value, do not keep the default timestamp validator with skew A while adding a second timestamp validator with skew B assuming B overrides A. Both validators may run, yielding narrower or unexpected effective boundaries.

Choose one explicit time configuration and retain other default/profile checks per your framework version. If replacing the entire default set with a custom validator list, confirm no checks provided by your version's defaults were dropped.

## 10. Replacing the decoder in Spring WebFlux: same policy, different interfaces

On **Spring WebFlux**, the Resource Server still receives Bearer JWTs and must enforce the same issuer, audience, signature, and time checks. However, the security pipeline uses **reactive APIs**:

| Responsibility | Servlet / Spring MVC | Reactive / WebFlux |
|---|---|---|
| HTTP Security | `HttpSecurity` | `ServerHttpSecurity` |
| Filter chain bean | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Decoder interface | `JwtDecoder` | `ReactiveJwtDecoder` |
| Nimbus decoder | `NimbusJwtDecoder` | `NimbusReactiveJwtDecoder` |
| Decode result | `Jwt` or exception | `Mono<Jwt>` or error signal |
| Resource Server DSL | `oauth2ResourceServer(o -> o.jwt(...))` | Same intent on `ServerHttpSecurity` |
| Security context | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |

Common WebFlux Resource Server dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

The same `app.security.jwt.*` properties from section 5 can be used if the application provides its own reactive decoder.

### 10.1. `ReactiveJwtDecoder` bean example

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
class ReactiveOrdersJwtDecoderConfig {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience() != null
                    && jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience is not allowed",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator
            )
        );

        return decoder;
    }
}
~~~

The validation design is **identical to Servlet**: trusted JWK Set source, allowed algorithm, defaults + issuer, and audience. The Java API differs only in the decoder type and reactive return model.

### 10.2. Wiring the reactive decoder into a WebFlux security chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ReactiveOrdersApiSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

With the `ReactiveJwtDecoder` bean from section 10.1, the reactive chain picks up the decoder from the context. If attaching a decoder directly in the DSL, that decoder must also carry equivalent validators. **Never use a synchronous Servlet `JwtDecoder` directly as WebFlux's decoder**, and avoid introducing unnecessary blocking calls onto the event loop when customizing JWK/HTTP sources.

## 11. Multiple issuers: replacing a single decoder may not suffice

Suppose the API is permitted to accept tokens from two issuers:

~~~text
Issuer A: https://login.example.test/realms/company
Issuer B: https://partners.example.test/oauth2/default
API Audience: orders-api
~~~

Using a single `NimbusJwtDecoder` pointed at Issuer A's JWK Set cannot properly verify JWTs from Issuer B even when Issuer B is allowlisted. **Never work around this by dropping issuer validation**, or pooling keys from every issuer into one boundary-less set.

The appropriate pattern is usually an **issuer-aware authentication manager resolver**:

~~~mermaid
flowchart TD
    A["Bearer JWT"] --> B["Read iss as an untrusted routing hint"]
    B --> C{"Is iss in trusted issuer list?"}
    C -->|No| D["Reject"]
    C -->|Yes| E["Select AuthenticationManager/decoder by issuer"]
    E --> F["Verify signature using that issuer's own JWK"]
    F --> G["Validate iss, exp, nbf, aud, and policy"]
    G --> H["JwtAuthenticationToken"]
~~~

Servlet Spring Security provides `JwtIssuerAuthenticationManagerResolver` or building an `AuthenticationManagerResolver<HttpServletRequest>` to select a manager per trusted issuer; WebFlux has an equivalent reactive resolver option. Constructor/factory names and wiring can vary by version, so match your project's actual APIs.

Subtle detail: the resolver may need to read `iss` **before the token signature is verified** to select a decoder. At that moment `iss` is strictly a **routing hint**, not a trusted assertion. The resolver must check the allowlist, and the selected decoder must verify the signature with **that exact issuer's key** and confirm the `iss` claim truly matches.

### When each issuer has different rules

| Policy | Issuer A | Issuer B |
|---|---|---|
| Trusted JWKS | JWK Set A | JWK Set B |
| Signing algorithm | RS256 per contract A | Permitted algorithm per contract B |
| Expected audience | `orders-api` | `orders-api` or dedicated resource ID |
| Scope claim | `scope` | Might be `scp` |
| Tenant claim | `tenant_id` | Might be another claim |
| Token profile | Policy A | Policy B |

If the same scope string means different things between two issuers, the converter and authorization policy must also distinguish them. Never assume `scope="admin"` from issuer B grants the same administrative privilege as issuer A.

**Never implement dynamic discovery for arbitrary client-supplied issuers**, as that can be abused to make the server call untrusted addresses or spoof token origins. Issuer management is a server-side trust decision.

## 12. Replacing the decoder without mistakenly altering `JwtAuthenticationConverter`

A common mistake is replacing the decoder to “read roles from the token”, accidentally dropping default validators in the process. If the token is already verified and you only need to map a `roles` claim, keep the safe decoder as is.

For example, a valid JWT contains:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "roles": ["AUDITOR"]
}
~~~

Spring Security JWT Resource Server normally converts scope into `SCOPE_orders.read`. To also add `ROLE_AUDITOR`, use an authorities converter operating on **verified claims**, without changing key sources or removing issuer validation.

~~~java
JwtGrantedAuthoritiesConverter scopeConverter =
    new JwtGrantedAuthoritiesConverter();

JwtAuthenticationConverter authenticationConverter =
    new JwtAuthenticationConverter();

authenticationConverter.setJwtGrantedAuthoritiesConverter(
    scopeConverter
);
~~~

This is the basic converter structure, with imports from `org.springframework.security.oauth2.server.resource.authentication`. When custom roles are needed, supply a converter combining scopes and roles; that is post-validation mapping logic.

Register the converter in the JWT DSL:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
    jwt.jwtAuthenticationConverter(authenticationConverter)))
~~~

This differs from:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
    jwt.decoder(customJwtDecoder)))
~~~

An API may need both, yet the **decoder** establishes token trustworthiness while the **converter** builds the principal and authorities. Keeping that order clear ensures unverified claim data never enters Spring Security authorities.

## 13. Tokens with valid signatures that must still be rejected

Suppose the Orders API trusts issuer `https://login.example.test/realms/company`, audience `orders-api`, and GET requires authority `SCOPE_orders.read`.

| Received JWT | What does the decoder do? | Post-decoder authorization |
|---|---|---|
| Valid signature, right `iss`, `aud=orders-api`, unexpired, read scope | Returns valid `Jwt` | Passes HTTP rule; service continues data policy |
| Invalid signature or tampered payload | Throws authentication error | No trusted principal created |
| Different `iss` than trusted issuer | Rejects | Never reaches scope check |
| `aud=billing-api` | Audience validator rejects | Never reaches scope check |
| Missing `aud` when required by API | Audience validator rejects | Never reaches scope check |
| Expired `exp` | Timestamp validator rejects | Never reaches scope check |
| Future `nbf` beyond allowed clock skew | Timestamp validator rejects | Never reaches scope check |
| Disallowed JWS algorithm | Decoder rejects | Never reaches scope check |
| Incompatible key/JWK | Decoder rejects | Never reaches scope check |
| Valid token holding only `orders.create` | Decoder returns valid `Jwt` | Lacks `SCOPE_orders.read`, denied by authorization |
| Valid token, sufficient scope, non-owner of record | Decoder returns valid `Jwt` | Service/domain denies data access |

Key distinction:

- **Decoder/validator failure** = **authentication** error; Resource Server normally returns HTTP **401 Unauthorized**.
- **Authenticated token lacking authority/policy** = **authorization** error; Resource Server normally returns **403 Forbidden**.
- JWK/metadata infrastructure errors do not necessarily share the exact same status as an invalid token; still, **never let requests proceed when tokens cannot be verified**.

Example Bearer token challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

When scope is insufficient:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="orders.read"
~~~

These illustrate RFC 6750; actual response details depend on Spring Security, gateways, and exception handling. Never include full JWTs, secrets, private JWK material, or internal details in error messages sent to clients.

## 14. Common ways checks are lost when writing a custom `JwtDecoder`

### 14.1. Only decoding the payload JSON

~~~java
// ANTI-PATTERN — decoding the payload is not verifying the signature:
String json = new String(
    Base64.getUrlDecoder().decode(jwtSegments[1]),
    StandardCharsets.UTF_8
);
~~~

This code only extracts Base64URL content without verifying JWS. An attacker can modify `sub`, `scope`, or `aud` in JSON. **Never return a trusted `Jwt` object from an unverified payload.**

### 14.2. Fabricating a fake JWT inside a decoder

~~~java
// ANTI-PATTERN — never use this for real requests:
// return Jwt.withTokenValue(token)
//     .header("alg", "none")
//     .claim("sub", "anonymous")
//     .claim("scope", "orders.read")
//     .build();
~~~

`Jwt.withTokenValue(...)` is helpful for constructing test data for converters, not for replacing a signature-verifying decoder. Returning a manually constructed `Jwt` from an unchecked token tricks `JwtAuthenticationProvider` into trusting a forged result.

### 14.3. Overwriting the validator with only an audience check

~~~java
// ANTI-PATTERN — may drop issuer/time validation:
decoder.setJwtValidator(requiredAudience);
~~~

Conceptually, the right fix is composing them:

~~~java
decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
    JwtValidators.createDefaultWithIssuer(issuer),
    requiredAudience
));
~~~

### 14.4. Setting only `jwk-set-uri` and forgetting `iss`

A trusted set of public keys can verify signatures, yet if code omits issuer validation, the API may accept tokens from the wrong realm/tenant/issuer in shared-key architectures or complex trust boundaries. Key source and issuer are **complementary conditions**.

### 14.5. Adding audience while dropping default/profile validators

A single validator checking `jwt.getAudience().contains(...)` does not check expiration, issuer, token type, or other constraints. Beyond validations in the Nimbus/JWS layer, compose a **complete set of claim validators** matching the token contract.

### 14.6. Disabling `typ` checks to “fix” rejected JWTs

If Spring Security/Nimbus rejects a JWT due to an incompatible JOSE `typ`, the root cause may be **the API receiving the wrong token type** or an incompletely configured profile. Do not simply turn off type validation and consider the issue solved. If the API requires RFC 9068, use the right token-profile validator; if the issuer uses a custom profile, align and validate the valid token type accurately.

### 14.7. Accepting any issuer with a matching `kid`

`kid` is merely a key identifier inside a JWK Set. Identical `kid`s across two issuers do not imply shared trust. Never treat `kid` as an issuer, audience, or principal identifier.

### 14.8. Letting requests pass when the JWKS endpoint fails

When no trusted public key can be found or the endpoint is temporarily unavailable, skipping signature verification to avoid downtime turns the API into an endpoint accepting forged tokens. Design caching, timeouts, alerting, and **fail closed** on access.

### 14.9. Trusting any `roles` claim as soon as JSON is visible

Claims have authorization meaning only after validation. To map roles, use a converter on the verified `Jwt`. Never write a servlet filter reading raw payloads to assign `ROLE_ADMIN` from the request before authentication.

### 14.10. Using `issuer-uri` without defining resource identity

An Authorization Server can issue tokens for multiple APIs. Checking only the issuer without audience can let a Billing API token be accepted at the Orders API when scopes/claims happen to overlap. Defining an explicit **expected audience** is part of the Resource Server contract.

## 15. Operational considerations when changing key sources

### 15.1. Key rotation

An Authorization Server may rotate public keys periodically. With a decoder using a dynamic JWK Set:

1. The issuer publishes a JWK Set containing currently valid keys.
2. When preparing to rotate, the issuer may publish the new key before signing tokens with it.
3. The Resource Server updates its JWK Set via supported caching/refresh mechanisms.
4. During the transition window, the issuer usually retains the old public key while older tokens remain unexpired.
5. Once old tokens expire and policy permits, the issuer retires the old key.

If the API pins a single public key via `withPublicKey(...)`, rotating keys requires coordinated deployment/configuration updates. Never “quick-fix” by disabling signature verification.

### 15.2. Timeouts and network dependencies

A decoder using a remote JWK Set may require HTTP connections to fetch keys. Consider:

| Aspect | What to decide |
|---|---|
| Connect/read timeouts | Prevent requests from hanging indefinitely when the JWK endpoint is slow |
| TLS/truststore | Trust the right CA and endpoint hostname |
| Proxy/firewall | Ensure the API can reach the approved JWK URL |
| Cache TTL | Handle rotation without hitting the network excessively |
| Refresh on new `kid` | Ensure JWK Set refresh behavior matches your version |
| Retry/circuit breaker | Avoid retry storms during issuer outages |
| Fail-closed policy | Never pass unverified tokens through |

Depending on your Spring Security/Nimbus APIs, you can configure the HTTP client via builder or custom JWK source; never assume global application HTTP client timeout properties automatically apply to the decoder.

### 15.3. Safe logging

Observability should focus on **failure categories** and performance, such as:

- Counts of `invalid_token` errors by signature/issuer/audience/timestamp (internally categorized appropriately).
- Counts of missing `kid` or JWK Set fetch failures.
- Latency and HTTP error counts to the JWK endpoint.
- Counts of 401/403 responses by endpoint and request ID.
- Active config versions for issuer/audience/allowed algorithms and last key refresh time.

Never log raw Bearer tokens, HTTP `Authorization` headers, private keys, client secrets, or full payloads containing PII. When auditing is needed, use low-sensitivity identifiers and metadata permitted by policy; never paste real tokens into issues or shared transcripts.

## 16. How to verify the new decoder truly preserves security checks

When replacing a decoder, the key question is not merely “can a valid JWT reach the endpoint?” but also **“are tokens invalid under each condition rejected at the right step?”**. There are two distinct test levels:

1. **Real decoder/validator tests**: invoke verification logic with JWTs actually signed by test keys, test JWK Sets, and varied claim/algorithm cases.
2. **Security chain authorization tests**: after valid authentication, confirm `SCOPE_*` or roles map properly and endpoints enforce expected rules.

Never rely solely on principal-mocking tests to conclude **signature, issuer, audience, and lifetime** are checked, because mock authentication usually **bypasses the real decoder**.

### 16.1. Behavior matrix to demonstrate

Suppose the Orders API contract is:

~~~text
Trusted issuer:        https://login.example.test/realms/company
Expected audience:     orders-api
JWS algorithm:         RS256 per contract
Required GET scope:    orders.read
Token profile:         OAuth 2.0 access token accepted by the API
~~~

| Case | JWT characteristic | Decoder expectation | HTTP expectation for protected GET |
|---|---|---|---|
| All valid | Valid signature, right issuer, right audience, unexpired, read scope | Succeeds | Passes HTTP rule |
| Tampered signature | Claims content lacks a matching valid signature | Rejects | 401 |
| Untrusted signing key | Signature from key outside trusted JWK Set | Rejects | 401 |
| Disallowed algorithm | JOSE `alg` not permitted | Rejects | 401 |
| Wrong issuer | `iss` from another realm | Rejects | 401 |
| Another API's audience | `aud=["billing-api"]` | Rejects | 401 |
| Missing audience | Token omits `aud` | Rejects per contract | 401 |
| Expired JWT | `exp` in past beyond clock skew | Rejects | 401 |
| Not-yet-valid JWT | `nbf` in future beyond clock skew | Rejects | 401 |
| JWT missing `exp` | No expiration claim | Per validator/profile requirement | 401 if `exp` is mandatory |
| Wrong token type | ID token or disallowed `typ` profile | Rejects per policy | 401 |
| Valid token, missing scope | All auth claims valid, lacks `orders.read` | Succeeds | 403 |
| Valid token, sufficient scope, wrong data owner | Valid token, order does not belong to principal | Succeeds | 403 or 404 per business policy |
| JWK endpoint outage | Trusted key absent from cache | Cannot verify | Do not let request proceed; HTTP status per error handling |

If a custom `JwtDecoder` accepts tokens with the wrong issuer/audience even though `SecurityFilterChain` rejects some scopes, that is still an **authentication-layer vulnerability**. HTTP permission rules cannot fully compensate for a decoder trusting the wrong tokens.

### 16.2. Why is `mockMvc().with(jwt())` not enough?

Spring Security Test provides the `jwt()` request post-processor to inject a pre-authenticated simulation. For example:

~~~java
mockMvc.perform(
        get("/api/orders/42")
            .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            ))
    )
    .andExpect(status().isOk());
~~~

This illustrates an **authorization rule test** on an endpoint assumed to return HTTP 200 for an authorized principal, with full `MockMvc`/`spring-security-test` imports and setup. Calling `jwt()` like this **does not prove `NimbusJwtDecoder` loaded the JWK Set or verified the signature, issuer, or audience**.

To verify the real decoder, use tokens **signed with a test private key**, serve the matching **public JWK** from a stubbed endpoint or trusted key, and test both valid tokens and invalid variants. Separate decoder tests from authorization tests so failures immediately pinpoint the right layer.

### 16.3. Replacing a decoder in an existing codebase

If the system previously used only `issuer-uri`, before switching to a custom `JwtDecoder`, know:

- Where the issuer and JWK Set were obtained from.
- Which signing algorithms are accepted.
- Which default validators were actually installed in the current version.
- Whether the API already had audience validation via properties, beans, or custom filters.
- Whether there is a specific JWT access token profile or mandatory tenant/client claim.
- Whether multiple security chains or multiple issuers share the decoder.
- How behavior changes when the JWK endpoint is unavailable at startup vs. request runtime.

Then build a new decoder that is **equivalent or stricter** per contract. There is no need to wrap every JWT verification library in hand-written code when Spring Security/Nimbus provides official maintained implementations.

## 17. Diagnosing errors after replacing a decoder

| Symptom | Common cause | Analysis path |
|---|---|---|
| All Bearer tokens get 401 | Wrong issuer, JWK URI, allowed algorithm, missing key, wrong audience | Separate validation exceptions from JWK fetch errors; verify source-of-truth config |
| JWT worked before replacing decoder, now gets 401 | New validator set has different policy or incompatible `typ`/`alg` config | Compare token contract against version's decoder config |
| Expired JWTs still accepted | `setJwtValidator` received only audience/custom validator, dropping timestamp validation | Re-compose `JwtValidators.createDefaultWithIssuer` or equivalent validators |
| Tokens from another issuer accepted | Configured only JWK URI, forgot issuer validator or trust boundary | Check exact `iss` and per-issuer key source |
| Tokens for another API accepted | Audience validator not applied | Bind `aud` to expected resource ID |
| Only missing scope returns 403 | Decoder succeeds, converter fails to produce required authority | Check `scope`/`scp`, `SCOPE_` prefix, and HTTP rules |
| `401` appears when IdP rotates keys | JWK cache not refreshed or issuer retired old key too early | Check `kid`, JWK lifecycle, and rotation policy |
| Startup depends on IdP | Decoder runs discovery at initialization | Consider a trusted JWK Set URI and appropriate startup policy |
| MVC app has bean, yet decoder does not run | DSL attaches another decoder or security chain does not match | Check decoder config on the exact matching chain |
| `JwtDecoder` bean not injected in WebFlux | Reactive app requires `ReactiveJwtDecoder` | Switch to the reactive interface and pipeline |
| `typ` errors when adopting RFC 9068 | Token profile and JOSE `typ` processing misaligned | Align issuer profile, API validation, and version capabilities |
| JWK URL hits TLS/timeout errors | CA, hostname, proxy, network, or timeout config | Adjust HTTP client/truststore per policy; never skip verification |

### Distinguishing token 401s from infrastructure errors

A JWT with an invalid signature or wrong audience is a **rejected credential**. Yet when the issuer's JWK Set is unreachable, the root cause may be **network/IdP or operational configuration**. Neither should produce a successful authentication; however, internal logs, metrics, and client status codes may need to distinguish them for proper operations.

Never return raw JWTs, private keys, or secret-bearing network exceptions in HTTP responses. To include a request ID for trace correlation, use only system-generated metadata safe for logging.

## 18. Decision workflow when customizing a decoder

~~~mermaid
flowchart TD
    A["Need to change Resource Server behavior?"] --> B{"Only changing scope/role/principal?"}
    B -->|Yes| C["Customize JwtAuthenticationConverter"]
    B -->|No| D{"Only need standard issuer/JWK/audience config?"}
    D -->|Yes| E["Prefer supported Spring Boot/Security properties"]
    D -->|No| F["Create custom JwtDecoder / ReactiveJwtDecoder"]
    F --> G["Select trusted JWK source & algorithms"]
    G --> H["Compose default + issuer validators"]
    H --> I["Add audience + profile/custom validators"]
    I --> J["Attach to the right SecurityFilterChain"]
    J --> K["Test both accepted and rejected cases"]
~~~

When an API uses JWT access tokens, keep this in mind:

~~~text
Raw Bearer JWT
  |
  v
Decoder with trusted key source/algorithm
  |
  v
Verify signature + validate issuer/time/audience/profile
  |
  v
Verified Jwt
  |
  v
JwtAuthenticationConverter
  |
  v
JwtAuthenticationToken + SCOPE_*/ROLE_* authorities
  |
  v
SecurityContext + authorization rules + business logic
~~~

**Replacing the default decoder means replacing the component that establishes trust in a JWT.** Preserve full signature and key-source verification, issuer validation, lifetime checks, and all validators required by the API contract; add audience and token profile checks as needed. Whenever you call `setJwtValidator(...)` yourself, always re-compose the default checks your application still requires, because that method does not append to the previous set automatically. When you uphold that boundary, replacing a decoder for specific infrastructure needs still preserves Spring Security's secure authentication and authorization model.

## References

- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet Bearer Token Authentication](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security — JWT Decoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtDecoder.html)
- [Spring Security — NimbusJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [Spring Security — JwtValidators Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtValidators.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
