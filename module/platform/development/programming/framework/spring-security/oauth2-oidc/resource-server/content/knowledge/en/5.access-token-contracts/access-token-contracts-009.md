# RFC 9068, `typ: at+jwt`, and the JWT Access Token Profile

In **OAuth 2.0**, an `access token` is the credential allowing a client to call a **Resource Server**. OAuth 2.0 does not require an access token to be a JWT: an Authorization Server may issue an **opaque** string or another format. When systems choose **JWT access tokens**, merely "having a valid signature" still does not establish a **compatible contract** between the Authorization Server and the Resource Server: different parties may name claims, declare intended recipients, and distinguish token types using different conventions.

**RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens** (October 2021) defines a standardized profile for issuing and validating **OAuth 2.0 JWT access tokens**. A key identifier is the JOSE header `typ: "at+jwt"` (or `"application/at+jwt"`). The profile also specifies mandatory claims, how to use `aud` with target resources, and validation steps at the Resource Server.

In this lesson, assume:

- **Authorization Server (AS):** `https://login.example.com`.
- **OAuth Client:** `web-orders` or `inventory-worker`.
- **Resource Server (RS):** Orders API, with resource identifier `https://api.example.com/orders`.
- **Illustrative business permissions:** `orders.read` and `orders.write`.

The hostnames, client IDs, and permission scopes are example data only; real systems must use registered values agreed upon between the AS and RS.

## 1. What Problem Does the "JWT Access Token Profile" Solve?

A JWT is a container for a set of JSON claims; an access token is a credential issued within the OAuth protocol. The two concepts are not identical:

| Concept | Meaning |
|---|---|
| **JWT (RFC 7519)** | A representation of claims that can be signed with JWS or encrypted with JWE. |
| **OAuth access token** | A credential used to access resources, regardless of internal format. |
| **RFC 9068 JWT access token** | An access token **in JWT form** conforming to a standard profile covering `typ`, claims, audience, signature, and validation rules. |
| **OIDC ID token** | A JWT intended for the **client** to verify login results; not a credential for calling the Orders API. |
| **Opaque access token** | A credential whose internal structure the client does not rely on; the RS typically validates it via an appropriate introspection mechanism. |

Never treat "a token has three `header.payload.signature` segments" as sufficient proof that it is an access token. An **ID token** can also have three segments and be signed with a key from the same issuer. If a Resource Server accepts any validly signed JWT, it may accidentally accept a token issued for a different purpose. This is the **cross-JWT confusion** risk.

RFC 9068 reduces confusion via two independent layers of information:

1. **Token type:** `typ` declares that this is an access token under the `at+jwt` profile.
2. **Target recipient and claims contract:** `aud` points to the permitted Resource Server, accompanied by standard fields `iss`, `exp`, `sub`, `client_id`, `iat`, `jti`, and relevant authorization details.

> **Scope note:** RFC 9068 does not force every OAuth Authorization Server in the world to issue JWTs, does not define all authorization rules of an API, and does not replace the security requirements of OAuth 2.0, JWT/JWS, or the application.

### 1.1. Normative Keywords in the RFC

The terms `MUST`, `MUST NOT`, `SHOULD`, and `MAY` carry specific meanings per RFC 2119/8174:

- **MUST / REQUIRED:** mandatory condition when claiming compliance.
- **MUST NOT:** prohibited when claiming compliance.
- **SHOULD / RECOMMENDED:** strong recommendation; exceptions must be understood and evaluated.
- **MAY / OPTIONAL:** optional feature that may be applied.

Accordingly, do not turn a recommendation like "should use asymmetric signatures" into "must use RSA," nor treat `scope` as mandatory in every token of the profile when the RFC specifies conditional rules for it.

## 2. `typ: at+jwt` — Declaring Token Type in the JOSE Header

### 2.1. Standard Header

An RFC 9068 access token signed with JWS may have a protected header:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "orders-signing-key-01"
}
```

- `alg` is the signing algorithm, e.g., `RS256`. **A signature is required**; `alg=none` is prohibited in the profile.
- `typ` indicates the **token type**. RFC 9068 registers the `application/at+jwt` media type, requires tokens to carry this type in the header, and **recommends the compact form `at+jwt`**.
- `kid` is an optional key identifier to select a key within the trusted key set. It does **not** establish trust on its own and does not permit the token to dictate an arbitrary JWKS source.

**An RFC 9068-compliant Resource Server must accept `typ` values `at+jwt` or `application/at+jwt` and reject any other value.** To avoid compatibility pitfalls, examples in this lesson use the normalized lowercase compact form `at+jwt`.

Fields commonly confused with `typ`:

| Field | Where Does It Appear? | Example Value | Meaning |
|---|---|---|---|
| JOSE `typ` | Header inside the JWT/JWS | `at+jwt` | This is a JWT access token per RFC 9068. |
| OAuth `token_type` | **Token endpoint** JSON response | `Bearer` | Client presents the token using the bearer scheme (`Authorization: Bearer ...`). |
| HTTP `Content-Type` | HTTP response/request header | `application/json` | Media type of the **HTTP body**, does not replace `typ` inside the JWT. |
| JOSE `cty` | Optional header, notably in nested JWTs | `JWT` | Inner content type when needed, does not replace `typ`. |

An example token endpoint response might look like:

```json
{
  "access_token": "eyJ...eyJ...SIGNATURE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "orders.read"
}
```

Here `token_type=Bearer` **does not prove** the enclosed JWT has `typ=at+jwt`; you must inspect and verify the access token's JOSE header.

### 2.2. Is `typ` Sufficient Proof to Trust a Token?

No. An attacker can construct an arbitrary JWT with header `{"typ":"at+jwt"}`. Before trusting any claims, the Resource Server must still verify:

- The signature using a key from the registered issuer, with an algorithm on the allowlist.
- `iss` equals the configured issuer exactly.
- `aud` actually contains a resource identifier accepted by the API.
- Validity window (`exp`, and `nbf` if present), claim structure, and permission policies.
- Other system-contract conditions such as grant type, allowed `client_id`, tenant rights, and permissions on specific records.

In other words: **`typ` classifies, signature verifies integrity/key origin, and `aud` plus claims determine whether the token matches the target and may be used.**

## 3. Structure of a JWT Access Token Under RFC 9068

JWS Compact Serialization typically has three segments:

```text
BASE64URL(protected-header).BASE64URL(claims).BASE64URL(signature)
```

A standard signed JWT **does not encrypt claims**, because Base64URL is merely encoding. Anyone holding the bearer token can decode the header and payload, though they cannot modify them while keeping the signature valid. If claims must be concealed, parties can agree on JWE; decryption and verification must both be handled properly.

An **illustrative** claims set to call the Orders API:

```json
{
  "iss": "https://login.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "exp": 2000000300,
  "iat": 2000000000,
  "jti": "token-b8b7e663-3f1a-4e24",
  "client_id": "web-orders",
  "scope": "orders.read"
}
```

The Unix timestamps are for illustration only, not a real-world usable token. Nor is the JSON above a **signed JWT** yet; it is the JSON payload to be encoded and signed by the issuer.

### 3.1. Seven Required Claims

RFC 9068 specifies the following **seven REQUIRED claims**, with meanings defined by the relevant RFCs:

| Claim | Required? | Meaning and Implementation Notes |
|---|---|---|
| `iss` | **Yes** | Issuer identifier, usually the Authorization Server's URL. The Resource Server must match it **exactly** against the configured issuer. |
| `exp` | **Yes** | Timestamp when the JWT expires (`NumericDate`). The Resource Server rejects expired tokens, permitting only a small policy-governed clock skew. |
| `aud` | **Yes** | Resource indicator / audience targeted by the token. The API must find **its own identifier** in this claim. |
| `sub` | **Yes** | Token subject; meaning differs depending on whether the grant involves a user or only a client. |
| `client_id` | **Yes** | Client ID of the OAuth client issued the token. Not synonymous with `aud` and not automatically a human user identity. |
| `iat` | **Yes** | Timestamp when the token was issued (`NumericDate`). |
| `jti` | **Yes** | ID of the JWT; useful for event logging, token identification, and designing replay/revocation handling when paired with supporting mechanisms. |

**`NumericDate`** is seconds since the Unix epoch, not an arbitrary date-time string. In a JWT, `exp` and `iat` are numeric; types and semantics must follow the JWT specification.

**`jti` alone does not prevent replay.** If a Resource Server verifies only the signature and expiration without tracking/evaluating replay, the same valid bearer token can still be presented multiple times. `jti` is an identifier for other mechanisms when needed, not an automatic "switch" against token theft.

### 3.2. `sub` Is Not Always a Human User

The profile requires `sub` to be present, yet **does not** mandate that it is always "the ID of the currently logged-in person":

| Grant / Scenario | Involved Party | Guidance for `sub` per RFC |
|---|---|---|
| `authorization_code` with Resource Owner | User completing authorization flow | `sub` **SHOULD** correspond to the user identifier at the issuer. |
| `client_credentials` without Resource Owner | Application / service requesting a token for itself | `sub` **SHOULD** correspond to the application identifier the issuer uses to represent the client. |
| Other grants / token exchange | Depends on subject and delegation model | Define the subject explicitly per the issuer–RS contract. |

If an RS treats a `client_credentials` token like a user session and uses `sub` for personal account authorization, **sub confusion** can occur. The AS must also prevent clients from choosing a `client_id` that collides with privileged user identifiers so the RS is not misled when `sub` is populated from `client_id`.

Design rules:

- Do not rely solely on `sub` to tell whether a grant involved a Resource Owner.
- Distinguish `sub`, `client_id`, and granted permission types.
- Define distinct authorization policies for machine-to-machine vs. user-delegated tokens.
- If the RS maps subjects to internal records, consider `(iss, sub)` pairs and identity/grant context, avoiding conflating subjects across issuers.

## 4. Optional Claims and Authorization Claims

### 4.1. `scope` Is Recommended When Scope Was Requested

`scope` **is not among the seven unconditionally REQUIRED claims**. RFC 9068 states that if an authorization request included `scope`, the issued JWT access token **SHOULD** contain the corresponding `scope` claim.

Example:

```json
{
  "scope": "orders.read orders.write"
}
```

Scopes in the `scope` string are space-separated. In Spring Security systems, `scope` is typically converted into authorities like `SCOPE_orders.read`, though the **scope → endpoint mapping** is Resource Server policy, not an automatic effect of RFC 9068.

A key requirement: **every scope in the token must be meaningful for the resources listed in `aud`**. Avoid issuing tokens bundling ambiguous scopes across multiple APIs.

Example:

| `aud` | `scope` | Assessment |
|---|---|---|
| `orders-api` | `orders.read` | Appropriate if Orders API defines this permission. |
| `inventory-api` | `inventory.read` | Appropriate if Inventory API defines this permission. |
| `orders-api` | `inventory.write` | Likely a contract violation; AS should not emit permissions meaningless to Orders API. |
| `orders-api` and `inventory-api` | `read` | **Ambiguous** if unclear which API `read` applies to; needs clear rules or separate tokens. |

### 4.2. User Authentication Context Claims

When a grant involves a Resource Owner, the AS **MAY** include:

- `auth_time`: timestamp when the user was authenticated.
- `acr`: authentication context class reference.
- `amr`: authentication methods references.

These claims convey authentication context if the RS has business requirements for them, but they are **not mandatory claims** in every RFC 9068 JWT access token. Values must come from the real authentication context, never blindly trusted from client-submitted inputs.

### 4.3. Claims for Groups, Roles, and Entitlements

RFC 9068 suggests a common set of claim names if an AS needs to carry authorization attributes beyond scopes:

| Claim | Used to Represent | Notes |
|---|---|---|
| `groups` | Groups the subject belongs to | Align structure/data types with an appropriate SCIM profile. |
| `roles` | Resource-related roles | There is no universal standard role-name set across products. |
| `entitlements` | Specific entitlements or privileges | Requires mutual agreement on meaning and audience between AS and RS. |

These names are inspired by the SCIM model in RFC 7643; they **do not create automatic authorization** in Spring Security. If an issuer uses `roles`, the application must decide which roles are valid, distinguish issuer/tenant/audience, and map them to authorities or business policies.

### 4.4. Personal and Private Data

A JWS-signed JWT **allows anyone holding the token to read its claims**. Do not embed email addresses, phone numbers, HR records, sensitive business data, or secrets into a token merely because the JWT is signed.

RFC 9068 further emphasizes that **OAuth Clients must not rely on parsing access token contents** for application logic; the contents are a contract between **AS and RS** and could switch to opaque tokens. If a web app needs user profile details, use proper OIDC mechanisms or an authorized API. Avoid stuffing full user profiles into access tokens just for frontend convenience.

## 5. `aud`: The Permitted Resource Server Contract

`aud` answers **"Which resource was this token issued for?"**, whereas `client_id` answers **"Which OAuth client received the token?"**. The two values can be completely different:

```json
{
  "aud": "https://api.example.com/orders",
  "client_id": "web-orders"
}
```

In this case:

- `web-orders` is the client.
- `https://api.example.com/orders` is the Resource Server identifier.
- A token issued to `web-orders` must still be rejected by the Inventory API if `aud` does not contain the Inventory API's identifier.

### 5.1. Resource Indicators per RFC 8707

A client can use the `resource` parameter per **RFC 8707** to specify the target recipient. Illustrative Authorization Code Flow example:

```http
GET /authorize?response_type=code&
  client_id=web-orders&
  redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback&
  state=RANDOM_STATE&
  code_challenge=PKCE_CHALLENGE&
  code_challenge_method=S256&
  scope=orders.read&
  resource=https%3A%2F%2Fapi.example.com%2Forders HTTP/1.1
Host: login.example.com
```

Real clients must fulfill all flow requirements: registered callbacks, `state`, PKCE, client policies, and session controls. This example focuses on `resource` and omits detailed login steps.

Per RFC 9068:

1. **With `resource`:** the issued JWT access token's `aud` **SHOULD** carry the same resource indicator requested by the client.
2. **Without `resource`:** the AS **MUST** select a **default resource indicator** for `aud`. If `scope` is present, the AS **SHOULD** use it to infer the default resource.
3. **Scope maps to multiple default resources ambiguously:** the AS **SHOULD** reject the request with `invalid_scope` rather than issuing ambiguous privileges.
4. **Multiple resource indicators:** the AS must evaluate the relationship between each scope and each resource; **never issue an access token whose granted privileges cannot be unambiguously interpreted**.

In practice, issuing separate access tokens per audience keeps permission boundaries and auditing clearer. If a contract allows multiple audiences, each Resource Server may still accept the token only when `aud` contains its own identifier and the scopes/claims genuinely apply to that resource.

### 5.2. Why Distinct Audience Namespaces Matter

RFC 9068 requires the AS to use **distinct `aud` identifiers for separate resources served by the same token issuer**, reducing the risk of one API mistakenly accepting another API's token. Never configure all APIs with a shared audience like `"all-apis"` merely for validation convenience when those APIs have distinct security boundaries.

A URI resource identifier is often helpful because it provides a clear namespace, yet `aud` is an **agreed identifier**, not necessarily a running endpoint URL or physical API address. The Resource Server must match the exact contract value rather than guessing audience from the `Host` header or rewriting strings arbitrarily.

## 6. End-to-End Flow Under RFC 9068

```mermaid
sequenceDiagram
    autonumber
    participant Client as OAuth Client
    participant AS as Authorization Server
    participant RS as Orders API / Resource Server
    Client->>AS: Authorization Request (scope, resource=Orders API)
    AS-->>Client: Authorization code after flow completes
    Client->>AS: POST /token (code + PKCE verifier; client auth when required)
    AS->>AS: Decide permissions, scope, aud, sub, client_id
    AS->>AS: Issue JWS with typ=at+jwt and required claims
    AS-->>Client: access_token, token_type=Bearer, expires_in
    Client->>RS: GET /api/orders, Authorization: Bearer access_token
    RS->>RS: Verify typ, signature, iss, aud, exp, and claims contract
    RS->>RS: Check scope/authority and business permissions
    alt Valid and authorized token
        RS-->>Client: 200 + permitted data
    else Invalid token or insufficient privilege
        RS-->>Client: 401 invalid_token or 403 insufficient_scope
    end
```

The profile also applies to access tokens issued via **`client_credentials`** or other grants; Authorization Code is simply one illustration of the relationship between client, AS, and RS. **Refresh tokens** (used to obtain new tokens from the AS) and **ID tokens** (intended for the OIDC client) retain separate purposes.

## 7. What Must the Resource Server Verify?

The single most important rule to prevent token confusion is **verifying both token type `typ` and audience `aud`, not just the signature**.

### 7.1. Verification Steps at the Resource Server

Per Section 4 of RFC 9068, an RS receiving a JWT access token must perform the following checks:

| Step | Condition | Failure Behavior |
|---|---|---|
| **1. Token type** | `typ` is `at+jwt` or `application/at+jwt`. | Reject; never accept ID tokens or non-conforming JWTs. |
| **2. If encrypted** | Decrypt with agreed key/algorithm; when encryption is required by agreement, unencrypted tokens **SHOULD** be rejected. | Reject if decryption fails or policy is unmet. |
| **3. Issuer** | `iss` must **match exactly** the trusted issuer identifier. | Reject tokens from non-matching issuers. |
| **4. Audience** | `aud` must contain the identifier the Resource Server expects for itself. | Reject tokens issued for other APIs. |
| **5. Signature** | Verify JWS per RFC 7515 using AS-provided keys; reject `alg=none`. | Reject tampered tokens or tokens signed with untrusted keys/algorithms. |
| **6. Expiration** | Current time must be before `exp`; allow only small clock skew if needed. | Reject expired tokens. |
| **7. Authorization** | Evaluate `scope`, roles/entitlements if present, and relevant business rules. | Deny operations lacking privilege. |

The profile also mandates the **presence** of `sub`, `client_id`, `iat`, and `jti`. Format checks, time bounds, and application-specific constraints must follow the contract. For instance, if `iat` is unusually far in the future or `client_id` is not allowed to call the API, the system can enforce additional rejection rules.

**Key and algorithm rules:**

- An RFC 9068-supporting AS and RS **MUST support `RS256`** in their supported signature algorithms. This does **not** mean every token must be signed with `RS256`; other algorithms may still be used per contract.
- Asymmetric signing (such as `RS256`, `ES256`) is **recommended** because the RS needs only the public key for verification. Never let the `alg` header expand the allowed algorithm list.
- You can use OAuth Authorization Server Metadata (RFC 8414) or OIDC Discovery to locate `issuer` and `jwks_uri`. These sources must be preconfigured/trusted; never fetch keys from arbitrary URLs declared inside a token.
- Do not rely solely on using different keys for ID tokens vs. access tokens to stop token confusion: the RS itself must verify `typ` and `aud`.

### 7.2. 401, 403, and Distinguishing Errors

When a token is missing, has an invalid signature, wrong `typ`, wrong issuer/audience, or is expired, the RS typically returns:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

When a token **authenticates validly** yet lacks `orders.read`, the RS typically returns `403 Forbidden`, optionally with `insufficient_scope` depending on configuration. OAuth Bearer error codes follow RFC 6750 and deployment config; avoid returning key details, claims, tokens, or internal reasons to the client.

Never fix a `401` by trying an **ID token** or **refresh token** against the API. If an access token has expired and the client holds a valid refresh token, the client must request a **new access token from the token endpoint**.

## 8. Configuring Spring Security Resource Server to Enforce RFC 9068

### 8.1. Does Spring Verify `typ: at+jwt` by Default?

The familiar Spring Boot configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
```

sets up the JWT decoder/verifier for the issuer. However, **never assume `issuer-uri` alone equals the full RFC 9068 contract**. The Resource Server must also enforce token type `at+jwt`, the right audience, and corresponding claims.

Spring Security provides **`JwtValidators.createAtJwtValidator()`** for configuring RFC 9068-compliant JWT access token validation. This API is available in recent Spring Security releases (e.g., 6.5; check your project's library version). The configuration below illustrates a **Spring MVC Resource Server with Spring Security 6.5**.

**Dependencies** in Spring Boot / Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

The Resource Server starter brings in the components needed to decode/validate JWTs from Spring Security OAuth2 Resource Server + JOSE. Your project must use a Spring Boot version compatible with the chosen Spring Security version.

### 8.2. Declaring `JwtDecoder` with the RFC 9068 Validator

The example only permits the illustrative `web-orders` client to call the Orders API. If a real API serves multiple clients, redesign the `client_id` policy around your system's client list/permissions rather than forcing every token to come from a single client.

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class AccessTokenDecoderConfig {

    private static final String ISSUER = "https://login.example.com";
    private static final String AUDIENCE = "https://api.example.com/orders";
    private static final String CLIENT_ID = "web-orders";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withIssuerLocation(ISSUER)
                    .validateTypes(false)
                    .build();

        decoder.setJwtValidator(
            JwtValidators.createAtJwtValidator()
                .issuer(ISSUER)
                .audience(AUDIENCE)
                .clientId(CLIENT_ID)
                .build()
        );

        return decoder;
    }
}
```

**Explaining two easily misunderstood details:**

- `.validateTypes(false)` **does not mean disabling type checking**. It delegates `typ` verification from Nimbus's default type processor to **`JwtValidators.createAtJwtValidator()`**, so that `at+jwt`/`application/at+jwt` is accepted per RFC 9068. Disabling Nimbus type checking **without adding a matching validator** would remove the token-type boundary.
- `.clientId(CLIENT_ID)` in this example is a **custom rule** restricting the Orders API to tokens issued for `web-orders`. RFC 9068 requires the `client_id` claim to be present, but does not require every RS to accept only a single client ID. With multiple OAuth clients, apply an allowlist policy aligned with their permissions.

`JwtValidators.createAtJwtValidator()` is a convenient Spring utility, yet implementers must still design **scopes/authorities and data permissions**. If the issuer supplies custom claims or stricter contracts (such as tenant bounds, application types, or grant restrictions), add corresponding validators and authorization policies.

**Version note:** The `validateTypes(false)` pattern reflects Spring Security 6.5 documentation; default type-checking behavior may vary across versions. When upgrading, consult your version's docs and never alter type-checking settings without ensuring `at+jwt` remains enforced.

### 8.3. Protecting Endpoints by Scope

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersSecurityConfig {

    @Bean
    SecurityFilterChain ordersSecurityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Spring Security typically maps space-delimited `scope` strings (or `scp` under default support) into authorities prefixed with `SCOPE_`:

```text
JWT claim:   "scope": "orders.read orders.write"
Authorities: SCOPE_orders.read, SCOPE_orders.write
```

If the Authorization Server uses `roles` or `entitlements` with a custom structure, configure a `JwtAuthenticationConverter` or corresponding permission-mapping solution. **RFC 9068 does not automatically turn `roles` into `ROLE_*` in Spring.** Every real API must still enforce order ownership, tenant, and data-state checks.

If the backend combines multiple authentication mechanisms (cookies, web login, bearer), configure filter chains and CSRF based on actual request paths; this example assumes a bearer-token API.

### 8.4. Should You Also Enable `audiences` in YAML?

If a Resource Server uses **only** standard auto-configuration, Spring Boot versions supporting `spring.security.oauth2.resourceserver.jwt.audiences` can validate audience via properties:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - https://api.example.com/orders
```

However, **enabling audience alone** is still not equivalent to the full RFC 9068 contract, since `typ` and other claims remain. Once you provide a custom `JwtDecoder` bean as in Section 8.2, configure all constraints inside that decoder's validator rather than expecting Spring Boot to merge every `jwt.*` property into your custom bean.

### 8.5. What If the Resource Server Receives a JWE or Opaque Token?

- **JWE:** RFC 9068 permits encrypted JWT access tokens. When AS and RS agree on encryption, the RS must be able to decrypt using the appropriate key/algorithm and continue validating the signed inner JWT. Standard `oauth2ResourceServer().jwt()` configuration **does not automatically guarantee** JWE support; integrate an appropriate decoder.
- **Opaque token:** has no JWS JOSE header `typ` to inspect. The Resource Server typically uses `opaqueToken()`/introspection and validates metadata/permissions appropriately. **Never apply an RFC 9068 JWT validator to an opaque token.**
- **Non-RFC 9068 JWT:** can still work with a different validator if a legacy contract permits it, but **never claim** a token conforms to RFC 9068 when `typ` or required claims are missing.

## 9. Issuing JWT Access Tokens at the Authorization Server

### 9.1. What the AS Must Agree On with the RS

The contract between the Authorization Server and the Orders API should specify:

| Component | Example / Condition |
|---|---|
| Issuer | `https://login.example.com`, matching metadata and `iss` exactly. |
| Token format | Signed JWT, RFC 9068 profile. |
| JOSE type | `typ: at+jwt`. |
| Signature | Allowed algorithms, public keys/JWKS source, rotation, and old-key retention. |
| Audience | `https://api.example.com/orders`. |
| Required claims | `iss`, `exp`, `aud`, `sub`, `client_id`, `iat`, `jti`. |
| Scope vocabulary | `orders.read`, `orders.write`; endpoint and resource permission mapping. |
| Client/grant policy | OAuth clients eligible for tokens, grant types, tenant and subject constraints. |
| Lifetime & revocation | Token TTL, clock skew, handling permission changes, and key/token incidents. |
| Privacy | Minimal claims; which personal data (if any) is permitted to appear. |

### 9.2. Example Customizer in Spring Authorization Server

If your organization operates **Spring Authorization Server**, you can customize JOSE headers and claims via an `OAuth2TokenCustomizer<JwtEncodingContext>` hook. The snippet below illustrates **part** of the contract, not a complete Authorization Server setup:

```java
package com.example.authorization;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration
public class AccessTokenCustomizerConfig {

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> jwtCustomizer() {
        return context -> {
            if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                context.getJwsHeader().type("at+jwt");

                // audience must be derived from authorized resources,
                // never taken arbitrarily from input unverified by the AS.
                context.getClaims().audience(
                    java.util.List.of("https://api.example.com/orders")
                );
                context.getClaims().claim(
                    "client_id",
                    context.getRegisteredClient().getClientId()
                );
            }
        };
    }
}
```

**Precondition:** This example assumes the Authorization Server **only issues JWT access tokens targeting the Orders API** in this code path. In real multi-resource/multi-audience setups, **never hardcode** the same `aud` for every client and every grant. Determine audience from authorized resources/scopes and AS policy, while ensuring `sub`, `iss`, `exp`, `iat`, and `jti` are present with accurate semantics. Register the customizer with the JWT generator per your Spring Authorization Server configuration.

If the AS also issues OIDC ID tokens, **apply `typ=at+jwt` strictly to access tokens**. Never force ID tokens to share the same type, since ID tokens target OIDC Clients and have their own rules.

## 10. Scenarios Prone to Contract Violations

### 10.1. Token Has `typ: JWT` with Valid Signature and Audience

```json
{
  "alg": "RS256",
  "typ": "JWT"
}
```

An **RFC 9068-compliant Resource Server must reject** it because `typ` is not `at+jwt` / `application/at+jwt`. This prevents another kind of JWT from being accepted as an access token. Do not work around this in the API by disabling type validation; if the AS is expected to issue RFC 9068 tokens, fix the contract **at the issuing side**.

### 10.2. ID Token Sent to the Orders API

An ID token has `aud=web-orders` and may be signed by the same issuer. Changing headers or reading `sub` **does not** grant `orders.read`. The API requires the right `typ`, right `aud`, and right permissions.

### 10.3. Access Token Issued for the Inventory API

Token:

```json
{
  "typ": "at+jwt",
  "aud": "https://api.example.com/inventory",
  "scope": "inventory.read"
}
```

Even with a valid signature and unexpired timestamp, the Orders API must reject it because `aud` lacks the Orders API identifier. Never assume "same issuer means interchangeable across APIs."

### 10.4. JWT Access Token Missing `jti` or `client_id`

The token may still be a valid JWT under RFC 7519, and a generic JWT decoder may verify its signature successfully. Yet it **fails the RFC 9068 profile** due to missing required claims. Enforce it with an RFC 9068 validator and require the AS to issue compliant tokens rather than treating every valid JWT as profile-compliant.

### 10.5. `client_credentials` Uses a `sub` Matching a Privileged User

If an AS lets clients pick their own `client_id` and copies that value into `sub`, the RS might confuse a machine token with a high-privilege human user. Govern client ID registration, subject modeling, grants/authorities, and API authorization; never treat `sub` alone as proof of a human user's privileges.

### 10.6. Valid JWT with Ambiguous Scope

A token carries both `aud=[orders-api, inventory-api]` and `scope=read`, where the two APIs define `read` differently. The AS must avoid issuing permissions that cannot be unambiguously bound to each resource; the RS also needs scope-parsing rules of its own and must reject scopes with unclear origin or target.

## 11. Sample Validation Scenario Matrix

Assume the Orders API accepts only issuer `https://login.example.com`, audience `https://api.example.com/orders`, RFC 9068 tokens, and `GET /api/orders/42` requires `orders.read`.

| Scenario | Observed Outcome |
|---|---|
| `typ=at+jwt`; valid signature; valid required claims; right `aud`; `scope=orders.read` | Passes token/scope layer; proceeds to check permission to view order 42. |
| `typ=JWT` despite valid signature | **401** / `invalid_token` due to wrong token type. |
| `typ=at+jwt` with invalid signature | **401** / `invalid_token`. |
| `iss` differs from configured issuer | **401** / `invalid_token`. |
| `aud=inventory-api` | **401** / `invalid_token`. |
| `exp` in the past | **401** / `invalid_token`. |
| Missing `client_id` or `jti` in token claiming RFC 9068 | Token fails profile; must be rejected by the profile validator. |
| Valid token lacking `orders.read` in `scope` | **403** / insufficient privilege, potentially `insufficient_scope`. |
| Valid token, sufficient scope, but subject does not own order | API must deny per **business policy** (typically `403` or `404` depending on design). |

When diagnosing failures, never log the raw access token. Useful fields include endpoint, request ID, general error category, expected issuer/audience, and sanitized authorization outcome.

## 12. Design Rules for Consistent Implementation

1. **Accept only the agreed profile.** If an API requires RFC 9068, verify `typ` and required claims with an appropriate validator rather than merely decoding a JWT.
2. **Audience is the boundary between APIs.** Every RS needs an explicit identifier; reject tokens with wrong `aud`.
3. **Do not confuse `client_id` with `sub`.** Especially in `client_credentials`, subject may be a machine/application; user-delegated and machine-to-machine policies differ.
4. **Scopes must be meaningful for the audience.** Reject ambiguous permissions and never map roles or scopes arbitrarily.
5. **Verify signatures with trusted keys.** Pin issuers, restrict algorithms, reject `none`, and manage JWKS/rotation.
6. **Distinguish access tokens from ID tokens.** Being signed by the same issuer does not make them interchangeable.
7. **Signed JWTs do not hide claims.** Minimize private data; use JWE or opaque tokens when data confidentiality requires it.
8. **Clients should treat access tokens as opaque.** Never make frontend logic depend on parsing `scope`, `roles`, or `sub` out of an access token.
9. **Choose validators matching your real Spring version.** `JwtValidators.createAtJwtValidator()` handles the profile; `oauth2ResourceServer().jwt()` integrates bearer JWT verification, while endpoint permissions require separate configuration.
10. **Do not equate profile compliance with full system security.** RFC 9068 defines format and validation; applications still need resource controls, tenant isolation, token flows, revocation, theft protection, and key operations.

## 13. Standard References

- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): primary specification, especially Sections `2` (header/claims), `3` (request/resource), `4` (validation), and `5–6` (security/privacy).
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): claim formats, `iss`, `sub`, `aud`, `exp`, `iat`, `jti`.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JWS header, signature, and integrity verification.
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707): `resource` parameter for clarifying target resources.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): protection against wrong algorithms, token confusion, and JWT validation pitfalls.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): transmitting bearer tokens and error handling.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): configuring JWT decoders and the "Configuring RFC 9068 Validation" section.
- [Spring Authorization Server — Core Model / Token Customizer](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): customizing headers/claims when the AS mints JWTs.

When designing the contract between an Authorization Server and a Resource Server, specify **token type `typ`, issuer `iss`, target `aud`, required claims, and `scope` privileges** together. RFC 9068 helps systems agree unambiguously that a token is an **OAuth access token for the intended purpose**, while Spring Security enforces that verification and the API's access policy.
