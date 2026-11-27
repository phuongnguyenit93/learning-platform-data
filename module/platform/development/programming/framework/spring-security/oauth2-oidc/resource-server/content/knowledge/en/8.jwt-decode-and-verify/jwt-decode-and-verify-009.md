# Handling `typ` and Token Profiles According to Version Capabilities

When a **Spring Security OAuth 2.0 Resource Server** receives a JWT, checking only the signature, expiration, and issuer is not always sufficient. The API must also know **what kind of token it is** and **whether the token conforms to a profile accepted by the API**. An important indicator sits in the **JOSE header**, named `typ`. For example:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "at+jwt"
}
~~~

The value `at+jwt` is commonly used for **RFC 9068 JWT access tokens**, whereas `JWT` is a common generic type value. How Spring Security/Nimbus verifies `typ` has evolved and can continue to vary by version: in some versions, the Nimbus decoder checks the type directly during decoding; in other versions or modes, Spring Security can check it via **`OAuth2TokenValidator<Jwt>`**. Therefore, when supporting a token profile such as `at+jwt`, you must distinguish the **standard profile**, the **Authorization Server's contract**, and the **APIs actually available in your dependency version**.

The goal of this lesson is to understand how `typ` helps protect a Resource Server, avoid confusing access tokens with ID tokens, configure validation per version capabilities, and recognize the limits of each approach.

## 1. What is `typ` in the JOSE header?

A JWT signed with JWS Compact Serialization typically has three segments:

~~~text
BASE64URL(protected-header).BASE64URL(claims-payload).BASE64URL(signature)
~~~

Example of a decoded JWT access token header and payload:

**JOSE protected header:**

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "signing-key-7"
}
~~~

**JWT Claims Set:**

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "client_id": "orders-web",
  "iat": 1761955200,
  "exp": 1761958800,
  "jti": "token-abc-123",
  "scope": "orders.read"
}
~~~

Here:

| Field | Location | Core meaning |
| --- | --- | --- |
| `alg` | JOSE header | Signature/authentication algorithm declared by the JWT; the API must restrict permitted algorithms |
| `kid` | JOSE header | Key-identifier hint to locate a matching verification key in a **trusted** key set |
| `typ` | JOSE header | Declares the content/token type, helping distinguish JWT kinds per protocol contract |
| `cty` | JOSE header when present | Content type of inner payload; usually relates to nested JWTs, **not synonymous with `typ`** |
| `iss`, `sub`, `aud` | JWT claims | Issuer, subject, audience |
| `exp`, `nbf`, `iat` | JWT claims | NumericDate: expiration, not-before, and issued-at timestamps |
| `scope`, `client_id` | JWT claims per profile/contract | Granted permission scopes, client identifier |

**`typ` lives in the JOSE header, not as a payload claim.** An issuer-supplied `"typ": "at+jwt"` field inside the payload does not substitute for validating the protected-header `typ` per token profile.

`typ` can help an application prevent a JWT with a **different purpose** from being used in the wrong place. Still, `typ` is just a data field; it **does not self-verify** the signature, issuer, audience, lifetime, or scopes. An attacker can write any `typ` into a forged token. The system should rely on `typ` only after the token passes cryptographic processing and appropriate trust checks.

### Distinguishing `typ` and `cty`

Typical JWS header example:

~~~json
{
  "alg": "RS256",
  "typ": "JWT"
}
~~~

The header of a **nested JWT** may carry `cty` indicating the inner content is a JWT:

~~~json
{
  "alg": "dir",
  "enc": "A256GCM",
  "cty": "JWT"
}
~~~

The second example only illustrates `cty` on an encrypted JOSE layer. A Resource Server configuring `NimbusJwtDecoder` for standard JWS **does not automatically gain the ability to read arbitrary JWEs or nested JWTs**. If the system uses encrypted/nested tokens, configure decoders, keys, JOSE policies, and layer processing suited to the emitted format.

## 2. Generic JWTs vs. specialized JWT profiles

**JWT (RFC 7519)** defines the basic structure and core claims. On top of that foundation, other protocols add rules specifying what a JWT is used for.

A **token profile** is a stricter set of format and semantic constraints on tokens. A profile may mandate:

- Which `typ` value must be present or which set of values is allowed.
- Required claims, data types, and their interpretation.
- Which issuing authorities are accepted.
- Which audiences are valid for receiving applications/APIs.
- Requirements on algorithms, signatures, lifetimes, key retrieval, and trust levels.
- Rules for subjects, clients, scopes, or profile-specific claims.

Common token forms encountered in practice:

| Token or profile | `typ` values you may see | Where is it used? | What the Resource Server must note |
| --- | --- | --- | --- |
| Generic JWT per RFC 7519 | `JWT` or omitted, per convention | Many kinds of apps using JWTs | Cannot infer this is definitely an OAuth 2.0 access token |
| RFC 9068 JWT access token | `at+jwt` or `application/at+jwt` | Client sends to Resource Server | Check token type plus **all** access-token profile conditions |
| OIDC ID token | Usually a JWT; `typ` is not always `at+jwt` | OIDC Client uses to authenticate user login | **Never** use an ID token in place of an API access token |
| Custom-profile JWT | Value defined by that profile | Only within a specific system/trust relationship | Build validators matching issuer docs; do not assume RFC 9068 compatibility |
| Opaque access token | No JWT-readable JOSE header | Resource Server verifies via introspection or issuer-supported mechanism | JWT `typ` checks do not apply to opaque strings |

Two JWTs can share a valid signature, the same issuer, and the same `sub` claim yet have **different intended purposes**. For instance:

- An **ID token** attests to a user authentication event for an OIDC client; `aud` normally targets the client's identifier.
- An **Access token** targets a Resource Server; `aud` must reflect the allowed API or resource indicator.

If an API checks only the signature and `iss`, treating every JWT from that issuer as a valid API token, it risks accepting **tokens issued for another recipient or purpose** (token confusion/cross-JWT confusion).

## 3. `typ` in RFC 7519 and RFC 9068

### 3.1. Generic JWT: `typ` is optional, profiles can tighten it

In generic JWTs, the `typ` header declares the object type. A structurally valid generic JWT **is not required** to carry `typ`. The value `JWT` is very common, yet that value alone **does not prove** the token is an OAuth 2.0 access token meant for an API.

This explains why a Resource Server cannot merely do:

~~~text
if header.typ == "JWT" then accept
~~~

A JWT meant for another purpose can also carry `typ: JWT`. Checking `typ` is meaningful only when combined with **the other conditions of the token profile**.

### 3.2. RFC 9068: JWT Profile for OAuth 2.0 Access Tokens

**RFC 9068** defines a standard profile for representing OAuth 2.0 access tokens as JWTs. A key identifier is the JOSE header `typ` using:

~~~json
{
  "alg": "RS256",
  "typ": "at+jwt"
}
~~~

Or the full media-type form permitted by the profile:

~~~json
{
  "alg": "RS256",
  "typ": "application/at+jwt"
}
~~~

When an API accepts only **RFC 9068** access tokens, a token with generic `typ: JWT`, or omitting `typ`, **fails the profile's type requirement**, even if it is otherwise a well-formed JWT.

RFC 9068 places additional requirements on issuer, signature, audience, timestamps, and access-token claims. Typical profile claims include:

| Claim | Meaning |
| --- | --- |
| `iss` | Authorization Server/issuer that issued the access token |
| `sub` | Subject the token refers to; may represent a user or client entity depending on grant |
| `aud` | Target Resource Server or resource set |
| `exp` | Token expiration |
| `iat` | Issued-at timestamp |
| `jti` | Token identifier |
| `client_id` | OAuth 2.0 client granted access |
| `scope` | Granted permission scope when present; not a universal object-ownership claim |

An access token carrying `typ: at+jwt` **can still be rejected** if the signature is invalid, `iss` is untrusted, `aud` omits the current API, the token is expired, required claims are missing/wrongly typed, or permission policies deny it.

**Do not accept `typ: JWT` as “equivalent” to `at+jwt` when the actual contract requires RFC 9068.** To allow multiple profiles, describe each profile explicitly and apply separate validators with their respective conditions.

### 3.3. Tokens issued by an issuer might not follow RFC 9068

Not every OAuth 2.0 Authorization Server issues access tokens per RFC 9068. Some providers:

- Issue **opaque access tokens**.
- Issue JWT access tokens with `typ: JWT`.
- Issue JWTs with custom headers or claims under a proprietary profile.
- Support RFC 9068 only when explicitly enabled or configured per client/resource type.

Therefore, **do not turn on RFC 9068 profile checks blindly** just because tokens look like JWTs. Before configuring, confirm what access tokens the issuer actually emits and the official issuer/API requirements.

## 4. At which layer is `typ` checked in Spring Security?

For a JWT Resource Server on the Servlet stack, the general processing flow is:

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["AuthenticationManager"]
    C --> D["JwtAuthenticationProvider"]
    D --> E["JwtDecoder / NimbusJwtDecoder"]
    E --> F{"Valid JOSE & JWT?"}
    F -- "No" --> X["AuthenticationException → 401"]
    F -- "Yes" --> G["JWT claims and protected headers"]
    G --> H["Jwt validators: timestamps, issuer, audience, typ/profile..."]
    H --> I{"Satisfies token policy?"}
    I -- "No" --> X
    I -- "Yes" --> J["JwtAuthenticationConverter"]
    J --> K["JwtAuthenticationToken"]
    K --> L["SecurityContext and authorization"]
    L --> M["Controller or 403 if insufficient permissions"]
~~~

Where `typ` is checked **can differ across versions**:

1. **Inside Nimbus's JOSE/JWT processing layer**: the decoder may reject a `typ` header outside what it accepts **before** Spring's `OAuth2TokenValidator<Jwt>` ever sees a `Jwt` object.
2. **Inside Spring Security's token validator layer**: the decoder is configured to delegate the `typ` decision to a validator, such as `JwtTypeValidator` or an `at+jwt` profile validator, if that API exists in the active version.

For developers, this leads to two distinct observations:

| Symptom | Explanation |
| --- | --- |
| `at+jwt` token is rejected immediately by decoder; custom validator never sees it | The Nimbus layer is still checking type as a generic JWT |
| Token is decoded, then rejected by a validator due to `typ` | Header type checking has been delegated to Spring Security's validator layer |

Thus, when handling tokens with `typ` other than `JWT`, **do not merely add a validator and assume it will always run**. First inspect how `NimbusJwtDecoder` handles `typ` in the exact Spring Security version you are running.

## 5. Why the answer depends on version

**Spring Security, Spring Boot, Nimbus JOSE + JWT, and related starters have their own version lifecycles.** Spring Boot manages a default dependency set, yet projects can override versions manually. Class names, builder options, and validation behavior change across release lines.

Distinguish three capability tiers:

| Capability tier | What can you do? | What to check in your actual version |
| --- | --- | --- |
| **Standard JWT decoder only** | Verify JWTs per config and whichever profiles the decoder supports by default | Which `typ` headers are accepted by default; whether type checking can be delegated to a validator |
| **Decoder supports `validateType(false)` option** | Prevent the Nimbus layer from enforcing its default `typ` rule so Spring's validator handles it | Does your builder have this method; which accompanying validators exist |
| **Has `JwtTypeValidator` or `JwtValidators.createAtJwtValidator()`** | Validate `typ` or an `at+jwt` profile using Spring Security's built-in validation API | Exact public API, method signatures, claim constraints, and version defaults |

In versions that support it, the recommended approach is **letting the decoder verify signatures and having validator classes enforce the specific token contract**. However, never copy API examples from a newer version into an older project and tweak method calls by guesswork.

### Checklist when choosing configuration for your project version

1. Identify the **exact Spring Boot and Spring Security versions actually resolved** at build time, rather than assuming from a starter snippet in documentation.
2. Identify whether the issuer emits **JWT or opaque**, what `typ` and profile it uses, and whether metadata/JWKS are supported.
3. Inspect your version's `NimbusJwtDecoder` API: does `withIssuerLocation(...)` or `withJwkSetUri(...)` builder expose `validateType(...)`?
4. Check whether `JwtValidators` provides an **RFC 9068** validator builder; if not, check for `JwtTypeValidator` or supply a custom `OAuth2TokenValidator<Jwt>`.
5. Verify the full validator set running for **issuer, audience, lifetime, and type/profile**. Avoid replacing one validator and accidentally dropping the rest.
6. Distinguish **Nimbus parse/verify conditions** from **Spring validator conditions**. If either layer rejects, the request is not authenticated.

**“Supporting `at+jwt`” does not merely mean the decoder stops throwing an error on `typ: at+jwt`.** Proper support also requires enforcing the profile requirements and Resource Server policies.

## 6. Basic JWT Resource Server configuration

For a Spring Boot Servlet API application, the typical dependency is:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Example `application.yml` when the issuer issues JWTs accepted by the API:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Example Servlet security filter chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This configuration protects the API with Bearer JWTs, **and does not automatically guarantee audience checking or a specialized profile like RFC 9068** across all versions. Disabling CSRF in the example is appropriate only for stateless APIs authenticating via bearer tokens that do **not** rely on browser-automatically-sent authentication cookies; apps using session cookies need proper CSRF protection.

If a token carries scope `orders.read`, default mapping normally produces authority `SCOPE_orders.read`. That only checks operation-level permission; order-reading logic must still verify whether the caller is allowed to view **the specific record and tenant**.

## 7. Configuring the RFC 9068 profile when supported by your version

In Spring Security versions **providing** the `validateType(false)` builder option and `JwtValidators.createAtJwtValidator()`, you can configure the JWT decoder as follows.

### 7.1. Example for one issuer, one API, and one permitted client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class AccessTokenJwtDecoderConfiguration {

    private static final String ISSUER =
        "https://auth.example.com/realms/shop";
    private static final String AUDIENCE = "orders-api";
    private static final String CLIENT_ID = "orders-web";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withIssuerLocation(ISSUER)
            .validateType(false)
            .build();

        OAuth2TokenValidator<Jwt> accessTokenValidator =
            JwtValidators.createAtJwtValidator()
                .issuer(ISSUER)
                .audience(AUDIENCE)
                .clientId(CLIENT_ID)
                .build();

        decoder.setJwtValidator(accessTokenValidator);
        return decoder;
    }
}
~~~

**Applicability condition:** This example targets **a release line that includes all of the APIs used above**. If `createAtJwtValidator()` or `validateType(false)` is absent from your project's dependencies, the example **will not compile**. In that case, choose an approach compatible with your actual version—or consider upgrading—rather than deleting security checks to make the code run.

Breaking down each part:

1. `withIssuerLocation(ISSUER)` configures issuer/JWKS resolution via the supported mechanism. Connections to the issuer must be trusted per system configuration.
2. `validateType(false)` **does not mean “skip JWT verification”**. In versions offering this option, it disables the default `typ` check at that decoder layer so Spring Security's validator can decide token type validity.
3. `createAtJwtValidator()` provides validation for the **RFC 9068 OAuth 2.0 JWT access token profile** when supported by Spring Security.
4. `issuer(...)`, `audience(...)`, and `clientId(...)` specify the exact values this example expects.
5. `setJwtValidator(...)` attaches the validator to the decoder; this is an easy place to make mistakes if you replace required validators with one that is too narrow.

When an API allows **multiple clients**, you cannot hardcode a single `CLIENT_ID` as in the example and expect other clients to pass. Design an allowed-client policy based on the issuer/API contract, then apply validation matching your version. Never strip out `client_id` verification completely just to let everything through if the system genuinely requires client control.

### 7.2. Why shouldn't you call `validateType(false)` alone?

This is a configuration **missing profile verification** if no matching `typ`/access-token validator is attached:

~~~java
// ILLUSTRATIVE incomplete approach for an API requiring at+jwt.
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withIssuerLocation("https://auth.example.com/realms/shop")
    .validateType(false)
    .build();

// Validator for at+jwt/token profile not yet specified.
~~~

When the decoder skips type checking in the Nimbus layer and the application also omits it in the Spring layer, the API can **lose its guard distinguishing JWT kinds**. This risk is especially acute if the same issuer emits both ID tokens and access tokens for different recipients.

**The right approach** combines decoding/signature verification with an appropriate profile validator: JWT type, issuer, audience, lifetime, required claims, and application policy.

### 7.3. Risk of overwriting default validators

Another mistake is attaching a new validator that checks only a single condition:

~~~java
// DO NOT USE alone for an API-protecting Resource Server.
decoder.setJwtValidator(jwt ->
    "at+jwt".equals(jwt.getHeaders().get("typ"))
        ? org.springframework.security.oauth2.core.OAuth2TokenValidatorResult.success()
        : org.springframework.security.oauth2.core.OAuth2TokenValidatorResult.failure(
            new org.springframework.security.oauth2.core.OAuth2Error("invalid_token")
        )
);
~~~

`setJwtValidator(...)` replaces the validator attached to the decoder. If an application replaces the composite validator with one that checks only `typ` while dropping timestamp, issuer, audience, and profile checks, invalid tokens can be accepted.

In versions supporting a standard profile validator, **prefer the built-in profile validator**. If you must define validators manually, assemble a complete validation chain and attach it using the components actually present in your version. Never equate “decoder verifies the signature” with “Resource Server verified the entire token”.

## 8. Validating `typ` yourself with `OAuth2TokenValidator<Jwt>`

Not every organization uses RFC 9068. Some APIs accept JWTs under an internal profile with a specific `typ`. In versions allowing `typ` checks to be delegated to Spring Security, applications can write a custom validator.

Example **illustrating only JOSE header checking** for a token profile accepting both `at+jwt` representations:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

public final class AccessTokenTypeValidator
        implements OAuth2TokenValidator<Jwt> {

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        Object typ = jwt.getHeaders().get("typ");
        boolean matchesProfile =
            "at+jwt".equals(typ) ||
            "application/at+jwt".equals(typ);

        if (matchesProfile) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Unexpected token type for this API",
                null
            )
        );
    }
}
~~~

**Limitation of this example:** This validator **checks only `typ`**; it is not a complete **RFC 9068 validator**. It does not prove `iss`, `aud`, `exp`, `client_id`, `jti`, or other conditions are valid. If your version supports `JwtValidators.createAtJwtValidator()`, that is a better starting point for the RFC 9068 profile.

When you need to compose individual validators, Spring Security provides `DelegatingOAuth2TokenValidator<Jwt>`. Conceptual example:

~~~java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtIssuerValidator;
import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

String issuer = "https://auth.example.com/realms/shop";
String expectedAudience = "orders-api";

OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
    jwt.getAudience().contains(expectedAudience)
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error("invalid_token", "Invalid audience", null)
        );

OAuth2TokenValidator<Jwt> validator =
    new DelegatingOAuth2TokenValidator<>(
        new JwtTimestampValidator(),
        new JwtIssuerValidator(issuer),
        audienceValidator,
        new AccessTokenTypeValidator()
    );

// Attach the validator to a NimbusJwtDecoder already configured for signature verification
// and with validateType handling configured appropriately for your version.
~~~

This snippet shows **how to compose custom validators**, not a substitute for the full RFC 9068 profile. In production, add all required claims and policies mandated by the API/issuer. Some APIs in the example may differ in older versions; use the equivalent mechanisms supported in that version.

**Crucial trust ordering:** an application may read an unverified header for technical routing in intentionally designed cases, yet **must never treat a self-asserted header value as proof for granting privileges**. Accept a JWT only after verifying the signature/trusted key and passing every required validator.

## 9. Failure types to distinguish when handling `typ`

Suppose the Orders API accepts only RFC 9068 JWT access tokens, issuer `https://auth.example.com/realms/shop`, and audience `orders-api`.

| Scenario | Conclusion |
| --- | --- |
| `typ: at+jwt`, valid signature, valid issuer/audience/lifetime/profile claims | Token **can** be authenticated; still must check scope and business permissions |
| `typ: application/at+jwt` with all valid conditions | Acceptable if the API permits this representation allowed by the profile |
| `typ: JWT` while API requires RFC 9068 | Rejected for wrong token type/profile |
| Missing `typ` when profile requires it | Rejected per profile requirement |
| `typ: at+jwt` with invalid signature | Rejected; header does not establish trust |
| `typ: at+jwt`, yet `aud` targets Payments API | Rejected; token is not meant for Orders API |
| `typ: at+jwt`, yet expired | Rejected; type value does not extend lifetime |
| `typ: at+jwt` from an unknown issuer | Rejected; do not trust issuers outside allowlist |
| `typ: at+jwt`, valid, lacking `orders.write` | Authentication may succeed, yet write request receives **403** |
| Client sends an opaque token to a JWT decoder | JWT decoder rejects because token lacks compatible structure/verification |

In a Resource Server, **tokens with invalid signature/type/issuer/audience/expiry** normally result in authentication errors such as **401 Unauthorized**. Tokens that authenticate cleanly yet lack sufficient scope or object permissions normally result in **403 Forbidden**. Exact status codes and `WWW-Authenticate` headers depend on the entry point, access-denied handler, and app configuration; never assume every 401 means a bad `typ`.

### When `typ` is valid yet you still get 401

Isolate the root cause by layer:

1. **Bearer parsing**: is the header syntactically valid?
2. **JOSE processing**: does the JWS have valid structure, an allowed algorithm, and a valid signature?
3. **Type/profile**: is the `typ` header accepted by the API and are all profile claims present?
4. **Token validation**: do `iss`, `exp`, `nbf`, `aud`, `client_id`, etc., match the contract?
5. **Authorization**: is the token valid yet lacking the scope/action permission?

Never fix errors by removing validators or accepting arbitrary `typ` values without clarifying the issuer's token profile.

## 10. Avoiding confusion between OIDC ID tokens and OAuth 2.0 access tokens

An OIDC ID token can also be a JWT signed with keys from the exact same issuer. For example:

**ID token (illustrative):**

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": "orders-web",
  "iat": 1761955200,
  "exp": 1761958800,
  "nonce": "n-123456"
}
~~~

**Access token for Orders API (illustrative):**

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "client_id": "orders-web",
  "iat": 1761955200,
  "exp": 1761958800,
  "jti": "at-123456",
  "scope": "orders.read"
}
~~~

Both can share identical `iss`, `sub`, and `exp`. Yet **the ID token targets the OIDC client**, whereas the access token targets the API. If an API checks only `iss` and signature, a client could accidentally or intentionally send an ID token in `Authorization: Bearer ...`.

Identify token purpose via the issuer contract:

- The access token's **audience** must match the API.
- The **`typ` header** must satisfy the profile when required.
- **Claims** must carry access-token semantics; OIDC ID tokens have a different claim set.
- The API **never** accepts a token solely because it carries a valid user identity.

This is also why you must never build a filter that merely calls `jwt.getSubject()` and treats the presence of `sub` as valid authorization to access the API.

## 11. Multiple issuers, multiple token profiles, and multiple SecurityFilterChains

A system might integrate:

- Issuer A issuing RFC 9068 JWT access tokens with `typ: at+jwt`.
- Issuer B issuing JWT access tokens under an internal profile with `typ: JWT`.
- Another internal service issuing opaque tokens with introspection.

**Do not collapse all tokens into a rule of “any JWT goes”.** Each token kind needs its own trust conditions: issuer, JWKS or introspection endpoint, audience, algorithms, lifetimes, and profile.

On the Servlet stack, several implementation approaches exist:

1. **Multiple `SecurityFilterChain` beans**: cleanly separate endpoints, giving each chain its own authentication setup when paths/APIs have distinct token contracts.
2. **`AuthenticationManagerResolver<HttpServletRequest>`**: select an authentication manager based on a designed, allowlisted context when the same endpoint scope must accept multiple issuers/profiles.
3. **Single issuer, single profile**: usually simplest for an API; configure one decoder with explicit validators.

Example path-based layout:

~~~text
/api/orders/**     -> issuer A / JWT at+jwt / audience orders-api
/api/legacy/**     -> issuer B / custom-profile JWT
/api/partner/**    -> introspection at approved issuer
~~~

With multiple chains, configure `securityMatcher(...)` and chain ordering accurately; never register multiple broad chains matching the same path assuming all three will run.

**Never extract `iss` or `typ` from an unverified payload/header and automatically fetch an arbitrary sender-supplied JWKS URL.** If token claims are used to choose a processing branch, they must serve strictly as **routing hints** within a controlled set of trusted issuers/decoders. Final verification must guarantee the token genuinely belongs to the matching issuer, audience, and profile. This prevents both trusting the wrong issuer and exposing the server to uncontrolled network targets.

## 12. JWT `typ` header and related JOSE concerns

A validator checking only `typ` will not catch all JOSE risks. The Resource Server also needs to care about:

### 12.1. Algorithms and trusted keys

A JOSE header may declare `alg: RS256`, `ES256`, or another value. The API must restrict algorithms to those matching the issuer and trusted key configuration. Never accept `alg: none` tokens as signed access tokens protecting an API.

`kid` is a **key-selection hint**, not a trusted URL or proof of permission to call an API. Use only keys from a configured trusted JWKS/keystore; never load arbitrary keys from a header value supplied by an attacker.

### 12.2. Extended headers, `crit`, and profile extensions

Some JOSE mechanisms use extended headers or `crit` to declare parameters that must be understood. Security components must follow JOSE/decoder rules for these headers. Never write a custom parser that “ignores all unknown headers” just to accept unexpected tokens.

### 12.3. JWT with valid `typ` yet wrongly typed claims

A token with:

~~~json
{
  "exp": "1761958800",
  "aud": 123
}
~~~

fails NumericDate formatting for `exp` and valid audience typing per JWT rules. **A valid `typ` does not make wrongly typed claims valid.** Likewise, `"scope": ["orders.read"]` must not be automatically assumed identical to a space-delimited scope string in a profile expecting a string; verify against profile/issuer documentation.

## 13. Distinguishing “configurability” from “default behavior”

An online example might show:

~~~java
NimbusJwtDecoder.withIssuerLocation(issuer)
    .validateType(false)
    .build();
~~~

This is **a configuration option in versions that support it**, not a statement that every Spring Security version:

- Has `validateType(false)`.
- Accepts `at+jwt` by default.
- Automatically applies `JwtTypeValidator`.
- Automatically enables full RFC 9068 validators.
- Automatically tells ID tokens apart from access tokens from JWT syntax alone.

Similarly, when `JwtValidators.createAtJwtValidator()` is available in a given version, understand exactly which checks that validator performs and pass parameters fitting your system. Default behavior in other versions may vary as `typ` validation evolves between Nimbus and Spring Security.

**A principle that holds across versions:** explicitly decide which token profile the API accepts, verify signature/key and issuer, validate audience/lifetime/type/claims per profile, and only then use the principal and authorities for authorization.

### If your version lacks the desired API

Approaches to consider based on actual capabilities:

1. **Use a profile supported by both the issuer and current decoder**, with the required validators. Base this on the token contract—do not simply ask the issuer to change `at+jwt` to `JWT` just to silence an error.
2. **Upgrade to a compatible Spring Security/Spring Boot version** if you need RFC 9068 support and cleaner control over `typ`.
3. **Build or configure a compatible `JwtDecoder`/JOSE processor** if upgrading is impossible, ensuring full signature and profile verification. This is security-sensitive code; use a trusted JOSE library and review the design thoroughly.
4. **Use introspection** when the Authorization Server supports it and the system contract permits. That is a different verification model, not a shortcut for “skipping JWT `typ` checks”.

Removing `typ` validation without replacing it with an explicit token-profile policy **is not an equivalent solution**.

## 14. Example expected behavior table for Orders API

Suppose the design requirement is: Orders API accepts only **RFC 9068 access tokens** from the trusted issuer, audience `orders-api`, scope `orders.read` for GET requests.

| Test token | Expected outcome | Reason |
| --- | --- | --- |
| Validly signed JWT, `typ: at+jwt`, valid `iss`, valid `aud`, unexpired, sufficient scope/profile | **200** if order-level permissions also allow | Matches profile and satisfies business permissions |
| Validly signed JWT, `typ: JWT`, same issuer/audience | **401** | Wrong token type for RFC 9068 profile |
| Validly signed JWT, `typ: at+jwt`, `aud: payments-api` | **401** | Token not intended for Orders API |
| Validly signed JWT, `typ: at+jwt`, expired `exp` | **401** | Token lifetime expired |
| JWT `typ: at+jwt` with forged signature | **401** | JWT untrusted even though `typ` looks right |
| Valid JWT carrying only `orders.write` | **403** | Lacks scope required for GET |
| Valid JWT with `orders.read`, yet user may not view order 123 | **403** or appropriate business response | Insufficient object-level permission |
| No bearer token sent | **401** on protected endpoints | Missing authentication credentials |

HTTP status codes above reflect typical configurations; actual results can be affected by custom entry points, access-denied handlers, and business error policies.

### Testing notes

**Testing the real filter/decoder** requires a JWT signed with a test key and a matching decoder/issuer configuration. Mock authentication helpers like `jwt()` in Spring Security Test help test **authorization rules**, yet typically **bypass real signature decoding and token validators**. Therefore, a passing `jwt()` mock test **does not prove** the API blocks wrong `typ` or invalid signatures in production.

Distinguish test types clearly:

- **Authorization tests**: scopes, authorities, endpoints, and object access permissions using an authenticated `Authentication`.
- **Token validation tests**: real JWTs with test issuer/keys, valid/invalid `typ` headers, wrong audiences, expirations, invalid signatures, and missing profile claims.

This serves as guidance for understanding the feature and does not replace verifying against your exact library version when deploying.

## 15. Common misconceptions

**“`typ` is a claim, so call `jwt.getClaimAsString("typ")`.”**  
No. In the case discussed here, `typ` is a **JOSE header**; with Spring Security `Jwt`, use `jwt.getHeaders()` to read headers. A custom payload claim named `typ` is not equivalent.

**“`typ: JWT` means this is definitely an access token.”**  
No. That is a generic JWT type declaration and does not specify full purpose. ID tokens or other tokens can also be JWTs.

**“Every OAuth 2.0 JWT access token has `typ: at+jwt`.”**  
No. RFC 9068 is one specific profile. An issuer may emit JWTs under another profile or opaque tokens.

**“Just calling `validateType(false)` safely accepts RFC 9068 access tokens.”**  
No. That option, where it exists, only changes how the decoder layer handles `typ`; you must attach validators checking the exact token profile.

**“A validator comparing `typ` alone is enough.”**  
No. You must also verify JOSE signature, issuer, audience, lifetime, and required profile claims.

**“If a token is rejected due to `typ`, the API should issue a fresh access token itself.”**  
No. A Spring Security Resource Server only authenticates access tokens. The client must obtain a suitable token from the Authorization Server under a supported grant.

**“Seeing `JwtTypeValidator` in an article means any version can use it.”**  
No. Check the public API of your active Spring Security version and verify whether validation happens in the Nimbus or Spring layer.

**“If `typ` doesn't match the profile, fix it by editing the JWT header/payload.”**  
No. The header is protected by the JWS signature; altering the header invalidates the signature. Only the Authorization Server has authority to issue tokens conforming to the designed profile.

## 16. Design workflow for a Resource Server

When implementing a Spring Security OAuth 2.0/OIDC Resource Server API, answer these in order:

1. **Who issued the token?** Define allowed issuers, key/JWKS retrieval or introspection, and the accepted algorithm set.
2. **What is the token's purpose?** Specify RFC 9068 JWT access tokens, custom-profile JWTs, or opaque tokens. Never confuse them with OIDC ID tokens.
3. **What must the `typ` header look like?** Specify whether it is mandatory and which values are valid per profile.
4. **Which claims are required?** Specify `iss`, `aud`, `exp`, `iat`, `client_id`, `jti`, `scope`, and custom claims matching the profile.
5. **What does your version support?** Check `NimbusJwtDecoder`, `validateType(false)`, `JwtTypeValidator`, `JwtValidators.createAtJwtValidator()`, and validator composition in the running library version.
6. **How are endpoints and data protected?** After authenticating the JWT, enforce scopes, roles, tenants, record permissions, and business policies.
7. **What happens when a token is invalid?** Reject authentication properly; never drop validators or accept wrong-purpose tokens to “fix” 401 errors.

A sound security configuration must answer both **“who issued this token and is it valid?”** and **“which profile was this token issued under and is it meant for this API?”**. The `typ` header is only one piece of that answer. In Spring Security, use your version's capabilities properly to combine `typ` and token-profile checks with signature, issuer, audience, lifetime, and authorization checks.
