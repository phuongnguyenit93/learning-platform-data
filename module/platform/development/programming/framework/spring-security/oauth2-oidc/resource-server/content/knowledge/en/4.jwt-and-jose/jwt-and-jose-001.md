# JWT Is a Set of Claims Represented in a Token Format

In the **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server** ecosystem, JWTs frequently appear as access tokens or ID tokens. However, before configuring JWT validation, it is essential to understand the foundational concept accurately: **a JWT (JSON Web Token) is a way to represent a set of assertions (claims) in a standardized token format**, so that systems can exchange and verify those assertions according to consistent rules.

A JWT may state that a subject is `user-123`, issued by `https://identity.example.test`, intended for `orders-api`, valid within a time window, and carrying the scope `orders.read`. These assertions are **data**; whether that data is trustworthy, which system the token is intended for, and whether the user is allowed to read a specific order are separate questions that must be checked explicitly.

> **Key takeaway:** A claim is a name-and-value assertion; a **JWT Claims Set** is the collection of claims; a **JWT** is the packaging of that set into a token structure based on the JOSE standards. A token in JWT format is not automatically valid, confidentially encrypted, or authorized to access every API.

## 1. From Claims to the JWT Claims Set

### 1.1. What Is a Claim?

In the context of JWT, a **claim** is a **name → value** pair representing information about a subject or about the token itself.

For example:

| Claim name | Sample value | Corresponding assertion |
| --- | --- | --- |
| `sub` | `"user-123"` | The subject the token refers to has identifier `user-123`. |
| `iss` | `"https://identity.example.test"` | The party claiming to be the token issuer. |
| `aud` | `"orders-api"` | The token is intended for the Orders API. |
| `scope` | `"orders.read"` | The token carries the read-orders permission scope under the system contract. |
| `exp` | `1893459600` | The token expires at the corresponding Unix timestamp. |

A claim value can be a string, number, boolean, array, object, or `null` according to JSON rules and each claim's specification. Not every claim allows every data type: for instance, `exp` uses a **NumericDate**, whereas `aud` can be a string or an array of strings.

### 1.2. A Claims Set Is a JSON Object

A **JWT Claims Set** is a JSON object containing claims. For example:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893459600,
  "iat": 1893456000,
  "scope": "orders.read",
  "tenant_id": "tenant-7"
}
~~~

Here:

- `iss`, `sub`, `aud`, `exp`, and `iat` are claim names defined by the JWT specification.
- `scope` is commonly used in OAuth 2.0, but its exact semantics and representation must follow the **access token profile / agreement with the issuer**; it is not among the seven registered claims of RFC 7519.
- `tenant_id` is a system-specific extension claim, trustworthy only once the token has been verified and a contract defines its origin and meaning.

**The JSON object above is not yet a complete JWT string.** It is the *content* to be represented as a token—for example, placed into the payload of a signed **JWS**. A recipient must never accept a bare JSON Claims Set lacking integrity protection and treat it as a valid token.

### 1.3. "A Set of Claims" Does Not Mean "Everything in the JSON Is Trustworthy"

A user could craft JSON containing `"role": "admin"`. That only shows *they wrote an assertion*; it does not prove the organization granted admin privileges.

For an API to trust a claim, it must verify that:

1. The token is protected by a cryptographic mechanism accepted by the system.
2. The token was issued by the expected **issuer** and is intended for the expected **audience**.
3. The token is still valid and satisfies constraints on token type, client, scope, or required policies.
4. The claim has a meaning agreed upon by the Resource Server and Authorization Server.

Those steps belong to **validation and authorization**, and do not happen automatically just because JSON is present.

## 2. Three Layers to Keep Separate: Claims Set, JOSE, and Application Semantics

To avoid confusing JWT with a complete authentication mechanism, separate three layers:

| Layer | Question it answers | Example |
| --- | --- | --- |
| **Claims Set (JWT, RFC 7519)** | What information does the token assert? | `iss`, `sub`, `aud`, `exp`, `scope` |
| **JOSE (JWS/JWE/JWK)** | How is the information packaged, signed, integrity-protected, or encrypted? | Compact JWS with RS256 signature; JWK/JWKS containing public keys |
| **OAuth 2.0 / OIDC / Application** | What is the token used for and which permissions are enforced? | Access token for Orders API; ID token for Client; `orders.read` scope |

**JWT** does not itself define the full login flow, token issuance, refresh tokens, revocation, company roles, or per-record ownership. It is a format for representing claims; the remaining rules come from profiles, protocols, and system policies.

Common foundational standards:

- **RFC 7519 (JWT):** JWT structure/semantics and registered claim names.
- **RFC 7515 (JWS):** JSON Web Signature, how to protect data integrity and authenticate the source via digital signatures or MACs.
- **RFC 7516 (JWE):** JSON Web Encryption, how to encrypt data to protect confidentiality.
- **RFC 7517 (JWK):** JSON Web Key, how to represent cryptographic keys in JSON.
- **RFC 7518 (JWA):** JSON Web Algorithms, algorithm identifiers.
- **RFC 8725 (JWT Best Current Practices):** Security considerations when creating and validating JWTs.

## 3. What Does a Typical JWT Look Like?

The most common JWT form in Resource Servers is a **JWT signed using JWS Compact Serialization**, represented as three dot-separated text segments:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Where:

1. **JOSE protected header** specifies cryptographic/format parameters such as `alg`, `kid`, and `typ`.
2. **Payload** contains the JWT Claims Set encoded into bytes and Base64URL.
3. **Signature** protects the integrity of the header and payload; the signing/MAC algorithm and key must be trusted by the verifier.

~~~mermaid
flowchart TD
    JWT["JWT as JWS Compact"]
    Header["JOSE header\nalg, typ, kid"]
    Payload["Claims Set\niss, sub, aud, exp, scope..."]
    Signature["Signature/MAC\nprotects header + payload"]
    JWT --> Header
    JWT --> Payload
    JWT --> Signature
    Header --> EncHeader["Base64URL"]
    Payload --> EncPayload["Base64URL"]
    EncHeader --> Joined["header.payload.signature"]
    EncPayload --> Joined
    Signature --> Joined
~~~

Example decoded header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026-01"
}
~~~

Example decoded payload:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893459600,
  "iat": 1893456000,
  "scope": "orders.read"
}
~~~

And the token string when sent over HTTP looks similar to:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer eyJhbGciOi...eyJpc3MiOi...HkQ8...
~~~

The string above is illustrative only, not a complete usable JWT. **Dots and Base64URL are data encoding; token trustworthiness comes from cryptographic verification combined with token acceptance rules.**

### 3.1. The Header Is Not the Claims Set

This is an important distinction:

| Component | What does it contain? | Verification considerations |
| --- | --- | --- |
| **JOSE header** | `alg`, `kid`, `typ`, possibly `cty` | Helps determine how to process the token structure; values supplied by the token must fall within the allowed algorithm/key policy. |
| **JWT Claims Set** | `iss`, `sub`, `aud`, `exp`, application claims | Only used after the token is verified and issuer/audience/lifetime and related conditions are checked. |
| **JWS signature** | Result of signing/MAC over the specified input | Proves the payload/header were not altered by a party lacking a valid key; does not by itself grant data access. |

For example, `alg = RS256` resides in the **header**, not in the `scope` claim in the payload. `kid` helps the Resource Server pick a key from a trusted JWKS when multiple keys exist, but **must never allow the token to point to an arbitrary location to fetch a key and implicitly trust it**.

### 3.2. Base64URL Is Representation Encoding, Not Secret Encryption

The header and payload segments of a compact JWS can normally be **Base64URL-decoded without any key**. Therefore:

~~~text
Base64URL ≠ Encryption
Signed JWT ≠ Secret payload
Decode JWT ≠ Verify JWT
~~~

A digital signature protects **integrity and authenticity with a trusted key**, not confidentiality of the contents. Do not place passwords, access keys, card numbers, system secrets, or unnecessary sensitive information into a JWT payload merely because the token is signed.

**HTTPS/TLS is still required**, even with a validly signed JWT: a leaked Bearer token can be used by anyone else while the token remains valid.

## 4. Must a JWT Be a Three-Segment JWS?

No. A JWT can be represented using **JWS** (signed/MACed for integrity protection), **JWE** (encrypted for confidentiality protection), or combinations defined by JOSE.

### 4.1. Signed JWT (JWS)

Standard JWS Compact Serialization consists of **3 segments**:

~~~text
protectedHeader.payload.signature
~~~

In Spring Security Resource Server applications, configuring `oauth2ResourceServer().jwt()` typically handles **signed JWTs** issued by an Authorization Server. The Resource Server verifies the signature using a trusted key, such as a public key retrieved from the JWKS published by the issuer.

### 4.2. Encrypted JWT (JWE)

JWE Compact Serialization consists of **5 segments**:

~~~text
protectedHeader.encryptedKey.iv.ciphertext.authenticationTag
~~~

With JWE, claims cannot be read directly without the appropriate decryption key. Tokens can also be **nested** (nested JWT), such as signing content with JWS and then encrypting it with JWE; the recipient then decrypts the outer layer and verifies the inner layer according to policy. A nested JWT can use the header parameter `cty = "JWT"` to indicate the nested inner content.

**A Spring Security JWT decoder configured for signed JWTs will not by default decrypt arbitrary JWEs.** JWE requires dedicated processing and key management designed to match the issuer/token profile.

### 4.3. "Unsecured JWT" and the `none` Algorithm

The JWT specification describes an **Unsecured JWT** with header `"alg": "none"`, having no protective signature. This is not a token type that a typical Resource Server trusts to authenticate API requests. For Bearer access tokens, **accept only the protection algorithms, keys, and token types configured for the specific use case**; never let the token itself disable cryptographic verification.

In other words, three dot-separated segments or valid JSON **does not guarantee that a token has been signed and properly verified**.

## 5. Claims Defined by the JWT Standard

RFC 7519 registers the following seven common claim names:

| Claim | Name | Meaning | Notable type / rules |
| --- | --- | --- | --- |
| `iss` | Issuer | Party that issued the JWT | StringOrURI; Resource Server checks against trusted issuer |
| `sub` | Subject | Principal described by the JWT | StringOrURI; exact semantics defined by profile and issuer |
| `aud` | Audience | Recipients that the JWT is intended for | String or array of strings; must contain the receiving Resource Server |
| `exp` | Expiration Time | Time after which the token is no longer accepted | NumericDate; token is expired after this time |
| `nbf` | Not Before | Earliest time the token is accepted | NumericDate |
| `iat` | Issued At | Time at which the token was issued | NumericDate |
| `jti` | JWT ID | Unique identifier for the JWT if used | String; aids token management/auditing per design |

These claims are **registered claim names**, which does not mean RFC 7519 requires every JWT to include all seven. A **JWT usage profile** (such as JWT access tokens under RFC 9068, ID tokens under OIDC, or internal contracts) may require specific claims. The Resource Server must enforce the requirements of the profile/agreement in use.

### 5.1. Time-Related Claims

`exp`, `nbf`, and `iat` use **NumericDate**: the number of seconds since 1970-01-01T00:00:00Z, optionally with a fractional part. This is **not milliseconds like `System.currentTimeMillis()` in Java**.

Example:

~~~json
{
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600
}
~~~

Meaning:

- The token was issued at `iat`.
- The token should not be accepted before `nbf`.
- The token must be rejected at or after `exp` (with an appropriate clock skew tolerance during verification if configured).

To handle clock drift, systems may use a small **clock skew**, governed by policy. Avoid using the wrong time unit, ignoring `exp`, or setting an overly large skew just to mask transient errors.

### 5.2. `iss`, `sub`, and `aud` Do Not Replace One Another

Example access token:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "shop-web",
  "scope": "orders.read"
}
~~~

- **`iss`** answers **who issued it**.
- **`sub`** answers **which subject the token is about**.
- **`aud`** answers **which recipient the token is intended for**.
- **`client_id`** (per profile/issuer) indicates which Client was involved in obtaining the token.
- **`scope`** answers **what permission scope was granted**.

If you verify only the signature without checking `aud`, the Orders API risks accepting tokens issued by the same issuer for a different API. If you check only `sub` without checking scope and data permissions, the API risks letting the subject perform unauthorized operations.

### 5.3. Subject Is Not Necessarily a Human User

In an **Authorization Code** flow involving a user, `sub` usually corresponds to the authenticated user; in a **client_credentials** flow, the token represents a Client/service and may follow a different subject convention. Never assume every `sub` in an access token maps to a user account in a `users` table.

When associating a durable identity with application data, the pair **(`iss`, `sub`)** is generally safer than `sub` alone because different issuers may emit identical subject strings. Claims like `email` or `preferred_username` are not by default stable identifiers or sufficient for authorization.

## 6. Registered, Public, and Private Claims

A JWT is not restricted to `iss`, `sub`, `aud`, etc. Three categories of claim names should be distinguished:

1. **Registered claim names:** Names registered in the JWT specification, such as `iss`, `sub`, and `exp`. They have standardized semantics.
2. **Public claim names:** Public names defined/registered with collision-resistant mechanisms, such as names under a controlled namespace/URI.
3. **Private claim names:** Names agreed upon between two parties, such as `tenant_id` or `department`. They may collide in name or differ in meaning across issuers.

Example system payload:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893459600,
  "https://claims.example.test/tenant_id": "tenant-7",
  "https://claims.example.test/permissions": ["order:read"]
}
~~~

The URIs above **are claim names**; they do not mean the Resource Server should make an Internet request to that address. This naming approach reduces collisions across claim namespaces; values and interpretation still require an agreement between the parties.

**Note:** Two systems using the same claim name does not prove they share the same meaning. `roles: ["admin"]` from an issuer must not be treated as system-wide admin unless the API has explicitly agreed on which roles exist, within which tenant, and who is permitted to grant them.

## 7. JWT and OAuth 2.0/OIDC: Format vs. Intended Purpose

You must distinguish **what format a token uses** from **what the token is used for**:

| Concept | Purpose-level definition | Must it be a JWT? |
| --- | --- | --- |
| **JWT** | Token format for representing a claims set within JOSE | This is the format itself; it does not specify the business purpose of the token |
| **OAuth 2.0 access token** | Credential used to access a Resource Server according to granted permissions | **No**; can be opaque or another format, though JWT is a common choice |
| **OIDC ID token** | Token describing the user authentication result for an OIDC Client | **Yes** under OIDC; uses the JWT structure per OIDC rules |
| **OAuth 2.0 refresh token** | Credential for a Client to request a new access token when permitted | **No** general requirement to be a JWT |

A token does not become a **valid access token** simply by being a JWT. Conversely, an access token can be completely valid in OAuth 2.0 even if it is an opaque token whose claims cannot be read by splitting on dots.

### 7.1. An ID Token Is Not an API Access Token

An OIDC ID token typically has `aud` set to the **`client_id` of the OIDC Client**. For example, the Client `shop-web` receives an ID token with audience `shop-web` to confirm user sign-in.

The Orders API, however, expects an access token with audience **`orders-api`** and a scope like `orders.read`. Because both tokens can contain `iss` and `sub`, applications frequently make the mistake of sending an ID token as a Bearer token to an API.

An API must reject tokens intended for the wrong purpose, even when the JWT is signed by the same issuer. Depending on the token profile, validation policy can check `aud` and appropriate token-type indicators (such as `typ` for an access token profile). **Never use a shared signing key as an excuse to skip distinguishing between the two token types.**

### 7.2. JWT Access Tokens Have Their Own Profile

**RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens** defines a standard profile for JWT access tokens. This profile specifies its own requirements for headers, claims, and validation—for example, `typ` may be `at+jwt`, distinct from a generic JWT with `typ: "JWT"`.

Therefore, before writing a validator, you need to know **which profile the Authorization Server uses to issue tokens**, how scopes are formatted, what the audience value is, and which attributes the Resource Server is required to validate. Do not assume that JWT access tokens from every Identity Provider have identical payloads.

## 8. How Does a Resource Server Use the Claims Set?

In the Spring Security OAuth 2.0 model, a Resource Server typically receives a JWT via:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.test
Authorization: Bearer <access-token>
~~~

Conceptual processing flow:

~~~mermaid
flowchart TD
    Request["HTTP request + Bearer token"] --> Extract["Extract token"]
    Extract --> Verify["Verify signature, algorithm, and trusted key"]
    Verify --> Claims["Read claims after token verification"]
    Claims --> TokenRules["Check iss, aud, exp, nbf, token type"]
    TokenRules --> Authn["Create Authentication / principal / authorities"]
    Authn --> Scope["Check scope at endpoint"]
    Scope --> DataPolicy["Check owner, tenant, business policies"]
    DataPolicy --> Response["Return resource or deny"]
~~~

In practice, the library may perform signature verification and claim checks within the same `JwtDecoder` step; the diagram simply expresses **the conditions** a token must satisfy before the API returns data.

### 8.1. The Claims Set Is Mapped to a Java Object

Once the JWT has been verified, Spring Security can expose `Jwt` via `Authentication` or `@AuthenticationPrincipal`:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class IdentityController {

    @GetMapping("/api/whoami")
    UserInfo whoAmI(@AuthenticationPrincipal Jwt jwt) {
        return new UserInfo(
                jwt.getIssuer().toString(),
                jwt.getSubject(),
                jwt.getAudience());
    }

    record UserInfo(String issuer, String subject,
                    java.util.List<String> audience) {}
}
~~~

This example shows how to read claims **after the verification performed by the security filter**. Do not expose it as a public endpoint without API protection configured. In a real application, carefully decide which identity details may be returned to the Client and avoid leaking unnecessary claims.

### 8.2. Configuring a Resource Server for Signed JWTs

Spring Boot dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Declaring the trusted issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
~~~

With a properly configured issuer, Spring Security supports discovering the appropriate metadata/verification keys and validating the signature, expiration, and issuer as configured. **Checking the Orders API's own audience is an independent requirement**: do not assume that a token issued by the right issuer is always meant for this API.

Example configuration of a validator that checks `aud = orders-api` alongside issuer and expiration:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwks-uri}") String jwksUri,
            @Value("${app.security.expected-audience}") String audience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> standardValidation =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidation = jwt ->
                jwt.getAudience().contains(audience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error("invalid_token",
                            "Unexpected audience", null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    standardValidation, audienceValidation));
        return decoder;
    }
}
~~~

Assuming the application has configuration:

~~~yaml
app:
  security:
    issuer: https://identity.example.test
    jwks-uri: https://identity.example.test/.well-known/jwks.json
    expected-audience: orders-api
~~~

**The JWKS path is illustrative only**; you must use the URI published by the Authorization Server in your real environment. Constraints on algorithms, token type, and other required claims should be configured according to the agreed token profile. When defining a custom `JwtDecoder`, preserve the required default validators rather than accidentally replacing them with a validator that checks only audience.

To protect endpoints based on scope:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
~~~

In Spring Security, for scope claims in default supported formats—such as `scope: "orders.read"`—the framework typically converts the scope into the authority `SCOPE_orders.read`. If the issuer uses `permissions`, `roles`, or a custom `scp` format, agree on the mapping and configure a suitable `JwtAuthenticationConverter`.

The code above shows Bearer token protection under `/api/**`. If the application also serves browser clients via cookies/sessions, design CSRF protection and filter chains to match the actual authentication model.

### 8.3. A Scope in a JWT Does Not Replace Per-Record Permissions

Even when a verified token contains:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

the Resource Server must still check whether order `42` belongs to `user-123` or to a tenant the user is allowed to view. The `scope` claim expresses a granted permission scope; it **does not by itself prove ownership, tenant membership, order status, or data-level authorization policies**.

This keeps a clear boundary between:

- **Authentication:** Confirming that the token/principal can be trusted in the context of the request.
- **Authorization:** Deciding whether the request is permitted to perform the operation and access the specific object.

## 9. Why Is Merely "Decoding a JWT" Not Enough?

This is the most common mistake when learning JWT. A snippet can do:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

String payloadJson = new String(
        Base64.getUrlDecoder().decode(token.split("\\.")[1]),
        StandardCharsets.UTF_8);
~~~

This snippet only **decodes a text segment** of the three-part string. It **does not verify the signature, issuer, audience, expiration, token type, or permissions**. Never use this output to authenticate a caller, decide roles, or grant access to data.

To see the difference:

| Operation | What can be concluded | What cannot be concluded |
| --- | --- | --- |
| Split on dots and Base64URL-decode | Header/payload of a compact JWS can be read | Does not prove the token is authentic |
| Parse the JSON Claims Set | Which field names and values are present | Does not prove who asserted them |
| Verify JWS with a trusted key | Header/payload match a valid signature/MAC under an accepted key | Does not prove right audience, lifetime, token type, or permissions |
| Verify issuer, audience, lifetime, token profile | Token meets the API's acceptance conditions | Does not prove caller has permission on individual records |
| Check scope and object-level policies | Decides whether to allow a specific operation | Does not replace token lifecycle governance and other data controls |

In production code, let `JwtDecoder` and the standard security layer perform verification, and only then use the validated claims.

## 10. What Does a JWT Not Provide Automatically?

### 10.1. JWTs Are Not Encrypted Confidentially by Default

The payload of a signed JWS is normally readable. If claim confidentiality must be protected from unauthorized observers, design the issued data accordingly and/or use JWE with appropriate key distribution. Never put sensitive claims into a token merely because it is "signed."

### 10.2. JWTs Do Not Automatically Expire Immediately Upon User Logout

A locally verified signed JWT can remain valid until `exp` unless an additional revocation/session-control mechanism exists. Logging out of a website, revoking a refresh token, or changing a password **does not automatically** invalidate all previously issued JWT access tokens across every Resource Server.

Depending on requirements, solutions may include short-lived access tokens, token status lookups, revocation lists, introspection, or up-to-date session/permission management mechanisms.

### 10.3. JWTs Do Not Guarantee Recipients Interpret Claims Correctly

Two Authorization Servers may use `roles` with two different data types or role definitions. A Client may request `orders.read` while the issuer only issues `orders.summary`. An API must check the **actual claims and accepted profile**, rather than relying on what the Client requested or assuming values.

### 10.4. JWTs Do Not Eliminate the Need to Protect Bearer Tokens

A Bearer token is a credential: anyone holding a valid token can generally present it to call the API with the permissions the token carries. Always transmit over HTTPS, keep tokens out of logs, avoid exposing them in URLs, choose storage appropriate for the Client type, and limit scopes/permissions/lifetimes.

## 11. Security Considerations When Accepting External JWTs

When a Resource Server accepts JWTs, the following conditions are typically part of the contract:

| Condition | Purpose |
| --- | --- |
| Trust only a preconfigured **issuer** | Avoid accepting tokens from unauthorized parties |
| Trust only allowed **keys** and **algorithms** | Prevent the token from choosing an unsafe verification mechanism |
| Validate **`aud`** for the API | Avoid accepting tokens meant for other APIs |
| Validate **`exp`**, `nbf`, and time | Avoid accepting expired or not-yet-valid tokens |
| Distinguish **access tokens from ID tokens** | Avoid confusing user authentication context with API access delegation |
| Enforce **scopes/authorities** per policy | Permit only granted actions |
| Enforce **tenant/owner/business roles** | Prevent access to unauthorized data |
| Limit claim contents and logging | Reduce leakage of sensitive data |
| Rotate keys and govern tokens | Support secure operations over time |

In particular, guard against **algorithm confusion**: never choose the verification method solely from the `alg` value supplied by an unverified token, never accept `alg: none` for tokens requiring cryptographic protection, never confuse a public key with a shared secret for MAC algorithms, and never fetch keys from an arbitrary URI specified by the token. Reputable JOSE/JWT libraries paired with explicit per-issuer allowlists of algorithms and keys mitigate these risks.

In multi-issuer architectures, bind each issuer to its own key set, audience, algorithms, and claim rules. Never pool keys from multiple sources into one store and check only that "the signature matches any key."

## 12. Example: From Token to API Decision

Suppose the Authorization Server issues a signed **JWT access token** with payload:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "exp": 1893459600,
  "iat": 1893456000,
  "scope": "orders.read",
  "tenant_id": "tenant-7"
}
~~~

The Client sends the token to the Orders API to call `GET /api/orders/42`. The Resource Server processes it across these boundaries:

1. **Token data protection:** Signature and algorithm are verified with a trusted public key provided by the issuer.
2. **Lifecycle and recipient claim checks:** `iss` matches, `aud` contains `orders-api`, the token is not expired, does not violate `nbf`, and satisfies profile conditions.
3. **Subject authentication:** `sub = user-123` and tenant/Client metadata are placed into context per contract, without inferring admin rights.
4. **Operation scope check:** Scope `orders.read` satisfies the GET endpoint for reading orders.
5. **Record-level check:** Order 42 is genuinely permitted to be viewed by `user-123` in `tenant-7` according to authoritative data.
6. **Response:** If all conditions pass, return the data; otherwise, return the appropriate error.

| Case | Typical outcome |
| --- | --- |
| Missing token or invalid signature/issuer/audience | **401 Unauthorized** |
| Expired or not-yet-valid token | **401 Unauthorized** |
| Valid token but missing `orders.read` | **403 Forbidden** |
| Sufficient scope, but Order 42 belongs to another user/tenant | **403 Forbidden** or **404 Not Found** per non-disclosure policy |
| Valid token and full permission for Order 42 | **200 OK** if the order exists |

**Correctness in steps 1–2 does not replace correctness in steps 4–5.** This is why Spring Security separates token authentication, authority mapping, and endpoint/business authorization.

## 13. Three Contrasting Examples to Remember

**Example A — A Claims Set Is Not Yet a Verified Token**

~~~json
{"sub": "user-123", "role": "admin"}
~~~

This is merely JSON with two claims. It lacks issuer, integrity protection, lifetime, and target recipient; the API has no basis to trust that the sender is an admin.

**Example B — A JWT with a Valid Signature but Wrong Audience**

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["billing-api"],
  "scope": "billing.read"
}
~~~

Even if the signature is valid, the **Orders API** must reject the token because `aud` does not contain `orders-api`.

**Example C — A JWT with Matching Issuer/Audience but Insufficient Permissions**

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

If the token is valid and verified, it can satisfy the read-orders scope requirement. However, a request to view someone else's order must still be denied if unauthorized under data access policies.

These three examples reinforce the distinction between **assertions (claims)**, **a protected token format (JWT/JWS/JWE)**, and **actual access permissions (OAuth 2.0/Spring Security authorization)**.

## 14. Self-Check Questions

**1. If you see three dot-separated segments and can decode the payload, can you conclude the token is valid?**

No. That is merely a common indicator of a compact JWS. You must verify the signature/MAC and trust conditions such as issuer, audience, lifetime, token profile, and permissions.

**2. Is the `scope` claim one of the seven registered JWT claims?**

No. `scope` typically belongs to the OAuth 2.0 profile/token contract. Its semantics and representation are agreed upon by the issuer and the API.

**3. A token has `aud = profile-api` and scope `orders.read`—should the Orders API accept it?**

No, unless the Orders API is listed among the valid audiences under the contract. Having a plausible-sounding scope does not fix a wrong audience.

**4. Does a signed JWT keep an email address or phone number in the payload confidential?**

No. A JWS payload is usually readable via Base64URL; signing protects integrity, not confidentiality. Put only necessary data into the token, or use an appropriate confidentiality mechanism.

**5. Is JWT synonymous with an OAuth 2.0 access token?**

No. JWT is a format for representing a claims set. An access token is an OAuth 2.0 credential that can be a JWT or an opaque token; an OIDC ID token also uses JWT, but serves a different purpose.

**6. Once the Resource Server has verified the signature and `exp`, can it skip business-level authorization checks?**

No. A token may be valid yet hold only limited scopes, target a different API, or lack permission to access a specific record.

---

**Conclusion:** JWT should be understood primarily as a **Claims Set represented in a standardized token format**, commonly as a signed JWS or encrypted JWE. Claims such as `iss`, `sub`, `aud`, and `exp` have standard semantics but **do not create trust by themselves**. In Spring Security OAuth 2.0 Resource Server, read and use claims only after verifying the token against the appropriate keys, issuer, audience, lifetime, and token profile; actual authorization still depends on scopes and the API's resource access policies.
