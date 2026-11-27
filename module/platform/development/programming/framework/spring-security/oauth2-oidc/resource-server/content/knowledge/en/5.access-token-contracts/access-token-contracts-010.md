# Designing Checks to Distinguish Access Tokens from Other-Purpose Tokens

## 1. Why Must a Resource Server Distinguish **Token Type**, Even When the Signature Is Valid?

In OAuth 2.0 and OpenID Connect (OIDC), an Authorization Server / OpenID Provider can issue multiple kinds of tokens or protocol artifacts (*protocol artifacts*) to different recipients. They may share the same JWT format, signing algorithm, public key, and issuer. However, a validly signed token **is not automatically an access token permitted to call an API**.

For example, an identity provider might issue:

- **Access token** for the `orders-api` Resource Server: presented in `Authorization: Bearer ...` or an appropriate scheme to call the API, with `orders.read`.
- **ID token** for the `web-client` OIDC Client: helps the client confirm the user's login result.
- **Refresh token** for the OAuth Client: sent back to the Authorization Server's *token endpoint* to obtain new tokens.
- **Logout token** for the Relying Party: signals a logout event under OIDC Back-Channel Logout.
- **Client assertion JWT** used to authenticate a client to the Authorization Server, or another JWT assertion used in another grant.
- **Authorization code**, **DPoP proof JWT**, or tokens exchanged via Token Exchange—each serving a distinct step.

The **access token contract** (*access-token acceptance contract*) is the explicit set of rules a Resource Server applies to answer:

> "Is this credential actually an access token **issued for my API**, in this context, with the required permissions?"

Crucially, the API must not answer this merely by checking "does the JWT decode?" or "is the signature valid?". Authenticating a JWT while ignoring the intended recipient or token profile exposes the system to **cross-JWT confusion / token substitution**: using a token meant for purpose A to perform an action reserved for a token meant for purpose B.

## 2. Distinguishing Token Types by **Recipient and Purpose**

| Token / Artifact Type | Issued To and Used By | Purpose | Usable as a Bearer Access Token for Business APIs? |
|---|---|---|---|
| **OAuth 2.0 access token** | Client holds it; Resource Server validates when client accesses resources | Grants access to one or more resources within issued scope | **Yes**, if the token targets that API and satisfies the contract |
| **OIDC ID token** | OIDC Client / Relying Party | Attests subject authentication; client checks `aud=client_id` and OIDC rules | **No** |
| **Refresh token** | Client holds it; Authorization Server accepts at token endpoint | Obtains new access tokens while grant remains valid | **No** |
| **Authorization code** | Client exchanges at token endpoint, typically with PKCE | Completes authorization-code grant | **No** |
| **OIDC logout token** | Relying Party receives per logout protocol | Signals logout event | **No** |
| **JWT client assertion** | Authorization Server / token endpoint | Authenticates client or executes assertion grant per config | **No** |
| **DPoP proof JWT** | Authorization Server or Resource Server validates per DPoP protocol | Proves sender possesses key bound to request/token | **No**; proof is checked alongside access token, never replaces it |
| **Opaque token** | Depends on issuer contract; could be an access token or another type | Purpose cannot be inferred from surface appearance | Only when introspection/contract proves it is an access token for the API |

A common point of confusion: `token_type: "Bearer"` in an OAuth 2.0 response states **how the access token is presented under the Bearer scheme**, not an assertion that every JWT associated with "Bearer" has access-token semantics. Similarly, OAuth Token Exchange parameters `requested_token_type` or `subject_token_type` identify protocol-level token types; they differ from the JOSE `typ` header.

### Who Is the "Audience" in Each Case?

- An access token for `orders-api` needs an audience matching the **Resource Server** if the JWT uses `aud`, or equivalent resource-binding info in an opaque/introspection contract.
- An OIDC ID token usually has `aud` containing the **Relying Party's client ID**.
- A client assertion JWT usually has `aud` pointing to the **Authorization Server / token endpoint**, per the applicable profile.
- A logout token carries the **Relying Party's** audience and a specific logout event structure.

Thus, an `aud` valid for **this recipient** is not valid for **another recipient**. `sub` indicates the described subject, **not** the endpoint permitted to accept the token.

## 3. Security Boundary: Cryptographic Validity Differs from Business Validity

Three verification layers must remain distinct:

1. **Cryptographic and origin validation**: JWS signature is valid under a trusted key, issuer matches, algorithm is allowed, token is within validity window; for opaque tokens, valid status via introspection or equivalent mechanism.
2. **Purpose and target recipient validation**: the token is an access token type supported by the API; audience/resource, client binding, claims, and JOSE type per profile must match.
3. **Authorization**: does the request to read/modify a specific resource have the right scope, authority, tenant, object ownership, and business conditions?

Outcomes can diverge:

| Scenario | Signature / Validity | API Access Token Contract | Resource Privileges | Conclusion |
|---|---|---|---|---|
| Valid JWT access token for `orders-api`, `orders.read` | Pass | Pass | Pass | Allow reading within permitted resources |
| Validly signed OIDC ID token, `aud=web-client` | Pass | **Fail** | Not evaluated | Reject token authentication for API request |
| JWT access token for `billing-api` | Pass | **Fail audience** | Not evaluated | Reject |
| Access token with tampered payload | **Fail signature** | Not evaluated | Not evaluated | Reject |
| Access token for right API, missing `orders.write` | Pass | Pass | **Fail** | Typically returns 403 |
| Access token with right scope, wrong tenant | Pass | Pass | **Fail object privilege** | Deny data access |

If the framework creates an `Authentication` after checking the signature while skipping audience or purpose checks, the application may be **authenticating a technically valid token in the wrong protocol context**.

## 4. Defining the Access Token Acceptance Contract

Before writing a `JwtDecoder` or `OpaqueTokenIntrospector`, document the exact profile the API accepts. An initial design for `orders-api` might state:

| Contract Property | Example Policy | Rationale |
|---|---|---|
| **Token transport** | `Authorization: Bearer <access-token>` over HTTPS | Prevent clients from arbitrarily passing ID/refresh tokens or tokens in multiple locations |
| **Format** | Signed JWT access token per RFC 9068, or issuer-verified opaque token | Select the right validator; format does not imply purpose |
| **Issuer** | `https://id.example.com/realms/demo` | Establish trust domain and JWKS/introspection source |
| **JWS algorithms** | `RS256` | Prevent token-declared `alg` from widening trusted algorithms |
| **Key source** | JWKS endpoint bound to the trusted issuer | Never fetch keys from `jku` or arbitrary URLs in the token |
| **JOSE `typ`** | Under RFC 9068: `at+jwt` or `application/at+jwt` | Distinguish tokens by access token profile |
| **Audience/resource** | `aud` contains `orders-api` | Block tokens issued for other APIs or clients |
| **Required claims** | Per profile: `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, `client_id` for RFC 9068 | Accept only tokens fulfilling the agreed contract |
| **Subject/client** | Allow user tokens and/or service tokens per endpoint | Avoid assuming every access token represents a human user |
| **Scope/authority** | `orders.read`, `orders.write` per operation | Control allowed actions |
| **Object-level checks** | Order belongs to matching tenant/account | Prevent privilege escalation when scope is coarse-grained at the API level |
| **Lifetime & clock skew** | Bounded per system policy | Reject expired tokens or abnormal lifetimes |
| **Revocation/sender binding** | Separate policy if needed; DPoP/mTLS when issued with binding | Do not equate unexpired tokens with permanently authorized access |

This table is a **policy design**, not a Spring Boot config file to paste verbatim into `application.yml`. An application may support multiple issuers or token types, provided each case has an **explicitly defined acceptance rule set**.

### Example Documenting Two Different Contracts

```yaml
# PSEUDO-CONFIG: describes the contract only, not Spring Boot configuration.
ordersApi:
  acceptedFormat: signed-jwt
  issuer: https://id.example.com/realms/demo
  allowedJwsAlgorithms: [RS256]
  requiredJoseTyp: [at+jwt, application/at+jwt]
  requiredAudience: orders-api
  acceptedScopes: [orders.read, orders.write]

legacyPartnerApi:
  acceptedFormat: opaque
  trustedIntrospectionServer: https://partners.example.com/oauth2/introspect
  requiredResource: partner-orders-api
  acceptedScopes: [partner.orders.read]
```

Never write a single shared handler saying "if a valid JWT exists, let it into both APIs," because the APIs have distinct audiences and profiles.

## 5. Which Signals Actually Distinguish an Access Token?

### 5.1. `iss`: Authenticating the Issuing Party

`iss` must match a **preconfigured trusted issuer**. If a system trusts multiple issuers, an unverified issuer string may be used to *tentatively select* a configuration from an allowlist, but never take an issuer URL from a token to dynamically fetch metadata/JWKS and trust that source.

Even when `iss` matches, the same issuer may have issued ID tokens, logout tokens, and access tokens using the same key. **A matching issuer alone is not enough.**

### 5.2. `aud`: Who the Token Was Issued to Serve

`aud` is one of the most important boundaries:

```json
{
  "iss": "https://id.example.com/realms/demo",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1910000000
}
```

The `orders-api` Resource Server must verify that `aud` contains **the expected resource identifier**. If a token carries `aud=web-client` or `aud=billing-api`, the API must reject it under its contract.

Never substitute audience with signals like the presence of `sub`, `email`, or plausible-looking scopes. A token may contain multiple audiences; multi-audience tokens should be accepted **only when permitted by both the issuer and API contracts**.

### 5.3. `typ`: Token Type in the JOSE Protected Header

Under **JWT Profile for OAuth 2.0 Access Tokens (RFC 9068)**, a JWT access token's JOSE header must use the appropriate `typ`:

```json
{
  "alg": "RS256",
  "kid": "signing-key-2026",
  "typ": "at+jwt"
}
```

Or:

```json
{
  "typ": "application/at+jwt",
  "alg": "RS256",
  "kid": "signing-key-2026"
}
```

The examples above illustrate only the **JSON header**, not a signed token.

`typ` helps prevent token confusion in RFC 9068 contexts. Yet it is not sufficient on its own to grant access: a JWT with `typ=at+jwt` can still have an invalid signature, wrong issuer, wrong audience, expired timestamp, or missing scope.

Conversely, **not every JWT access token in the industry follows RFC 9068**. A provider may issue access tokens with `typ=JWT` or omit `typ`. In that case, the API must follow the actual profile agreed with the issuer and enforce supplemental distinctions. Do not mechanically equate "missing `at+jwt` = not an access token" on a system that does not implement that profile.

### 5.4. Provider-Specific Token-Type Claims

Some issuers include custom claims in the payload, such as:

```json
{
  "token_use": "access",
  "iss": "https://identity.example.com",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1910000000
}
```

If the issuer contract guarantees `token_use=access`, the API can **require checking that claim**. An ID token from the same issuer might carry `token_use=id` and must be rejected. The claim name and allowed values depend on the provider; `token_use` **is not a mandatory standard claim of every OAuth 2.0 access token**.

Never rely on an unverified self-named claim as standalone proof. Check it only after verifying the token against trusted keys and issuer.

### 5.5. `client_id`, `azp`, `sub`, and Scope

- `client_id` in an RFC 9068 JWT access token identifies the client that requested the token; it **does not replace `aud`** for the Resource Server.
- `azp` has specific semantics in certain profiles, such as OIDC ID tokens; do not assume every issuer uses `azp` identically to `client_id`.
- `sub` is the subject. With `client_credentials`, the token may represent a client/service rather than an end user. Never infer "has `sub` = ID token" or "lacks email = machine access token."
- `scope` expresses granted permissions, yet **scope alone does not verify token type**. An ID token or custom vendor JWT might accidentally carry permission-like fields; conversely, an access token might not use the exact claim name `scope`.

If an API serves only a specific set of clients, add a policy checking `client_id`; this is an **additional condition**, not a rule that identifies access tokens via a single claim.

## 6. RFC 9068 Profile vs. Custom Profile: Choose Consistently

### 6.1. When the Authorization Server Supports RFC 9068

RFC 9068 establishes the JWT access token profile for OAuth 2.0. When properly implemented, the API has grounds to verify:

- JOSE `typ` is `at+jwt` or `application/at+jwt`.
- Signing algorithm and key match policy; token is verified before trusting claims.
- Issuer `iss` matches a trusted issuer.
- `aud` points to the expected resource server.
- Profile-required claims such as `sub`, `client_id`, `iat`, `exp`, and `jti` are present and processed per profile rules.
- Scopes/authorization details relevant to the API are enforced per contract.

This contract clarifies the boundary between a JWT access token and an OIDC ID token when both come from the same OP.

**Enforce the profile as a whole.** Checking only `typ` or adding only `aud` does not automatically make an application compliant with every RFC 9068 requirement.

### 6.2. When the Issuer Uses Custom JWT Access Tokens

Some issuers may return:

```json
{
  "alg": "RS256",
  "kid": "issuer-key-1",
  "typ": "JWT"
}
```

Along with the payload:

```json
{
  "iss": "https://id.example.com",
  "aud": "orders-api",
  "sub": "user-123",
  "token_use": "access",
  "scope": "orders.read",
  "exp": 1910000000
}
```

In this case, you can establish a **provider-specific** contract: valid signature and issuer, `aud=orders-api`, `token_use=access`, valid expiration and scope. However, the API must not claim RFC 9068 compliance merely because the payload shares many similar claims.

In particular, if an issuer **provides no reliable way to distinguish** ID tokens from access tokens for the same audience, relying solely on "valid signature" creates an ambiguity zone. Adjust the Authorization Server design or clearly separate audiences, keys, or profiles before letting APIs consume those tokens.

### 6.3. Do Not Combine Profiles with Overly Broad OR Conditions

A dangerous design:

```text
Accept JWT if:
  signature valid
  AND issuer valid
  AND (
       typ == at+jwt
       OR token_use == access
       OR scope contains orders.read
       OR sub exists
  )
```

That `OR` condition allows the weakest branch to bypass the stronger ones: merely having `sub` lets a token slip through. Instead, define **a mandatory AND rule set per profile**, and apply a profile only when an allowed issuer, endpoint, or authentication path is identified:

```text
Profile A / RFC 9068:
  signature AND issuer AND at+jwt AND audience
  AND required claims AND time AND authorization

Profile B / provider-specific:
  signature AND issuer AND token_use=access
  AND audience AND required claims AND time AND authorization
```

If an API genuinely supports two token styles, maintain two independent policies and select the profile **without trying them sequentially until one happens to pass**.

## 7. Examples of Cross-JWT Confusion

### 7.1. ID Token Sent in the API's Authorization Header

An OIDC flow completes and the client receives **two distinct JWTs**. Example ID token:

```json
{
  "iss": "https://id.example.com",
  "sub": "user-123",
  "aud": "web-client",
  "iat": 1909996400,
  "exp": 1910000000,
  "nonce": "client-login-nonce"
}
```

And the JWT access token:

```json
{
  "iss": "https://id.example.com",
  "sub": "user-123",
  "aud": "orders-api",
  "client_id": "web-client",
  "scope": "orders.read",
  "iat": 1909996400,
  "exp": 1910000000,
  "jti": "grant-token-id-1"
}
```

In this example, both tokens may share `alg=RS256`, the same `kid`, `iss`, `sub`, and neither is expired. Yet the **ID token** is meant for the RP with `aud=web-client`; only the **access token** targets the `orders-api` Resource Server.

If an API verifies signature and issuer while skipping audience, the ID token can be accepted by mistake. The API must verify the **right purpose and audience**, regardless of whether a token contains email, username, or `nonce`.

### 7.2. Logout Token Is Also a Validly Signed JWT

OIDC Back-Channel Logout uses a JWT **logout token** to signal logout events. This token follows the logout claim structure, potentially containing `events`, `sid`, `sub`, `iat`, `jti`, and an RP-targeted audience.

It grants no API privileges. A verifier checking only "signed by the OP and has `sub`" could mistake a logout token for an access token. Verifying token profile, audience, and intended purpose prevents this confusion.

### 7.3. Client Assertion JWT

A confidential client may use a signed JWT assertion to authenticate to the token endpoint. The assertion's audience typically points to the AS/token endpoint per the corresponding profile, with `iss` and `sub` identifying the client. This token may also use the same JWT signing algorithm yet confers no rights to call business APIs.

Never use `sub` or `client_id` to decide that a token is an access token; both can appear across multiple JWT types.

### 7.4. Refresh Token or Authorization Code Sent by Mistake

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer REFRESH_TOKEN_VALUE
```

A refresh token is designed for the **Authorization Server's token endpoint**, not for a Resource Server. If an API uses a JWT decoder, an opaque refresh token is usually rejected because it is not a JWT. However, a *JWT-shaped* refresh token must still be rejected under the **access token contract**, never relying on the assumption that refresh tokens are always opaque.

Likewise, an authorization code is a temporary value the client exchanges at the token endpoint; it is not an access token, regardless of how the code string is structured.

### 7.5. DPoP Proof Is Not a DPoP-Bound Access Token

With **DPoP** (RFC 9449), a client might send:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: DPoP ACCESS_TOKEN
DPoP: SIGNED_DPOP_PROOF_JWT
```

The DPoP proof is a JWT demonstrating sender key possession bound to the request (such as method, URI, timestamp, and nonce/jti as applicable). It **never replaces the access token**. The Resource Server must validate the access token per contract **and** verify binding against the DPoP proof, including the key thumbprint in the confirmation claim when the profile uses it.

Accidentally accepting a DPoP proof JWT as a Bearer access token confuses two protocol roles. Similarly, never accept an mTLS/DPoP-bound token as a plain bearer token when the contract requires sender proof.

## 8. Designing the Request Verification Flow at the Resource Server

A logical model:

```mermaid
flowchart TD
    A["HTTP request arrives at API"] --> B["Extract credential per supported scheme"]
    B --> C{"Exactly one token per transport contract?"}
    C -- "No" --> U["Reject input / require authentication"]
    C -- "Yes" --> D{"Committed token format?"}
    D -- "JWT access token" --> E["Select issuer/decoder from configured allowlist"]
    D -- "Opaque access token" --> F["Introspect at configured trusted AS"]
    D -- "Wrong format" --> U
    E --> G["Check alg, key, signature, and expiration"]
    G --> H{"Passes cryptographic validation?"}
    H -- "No" --> U
    H -- "Yes" --> I["Verify issuer, typ/profile, aud, claims"]
    F --> J["Verify active, audience/resource, metadata, and profile"]
    I --> K{"Right token type and intended for API?"}
    J --> K
    K -- "No" --> U
    K -- "Yes" --> L["Map principal and authorities"]
    L --> M{"Has scope and resource privileges?"}
    M -- "No" --> V["Deny authorization"]
    M -- "Yes" --> N["Allow endpoint processing"]
```

The diagram depicts **mandatory policy conditions**; a JWT library may perform several checks in one step or in varying implementation orders. Never use claims to **grant access** before the validator has established trust in the token.

### Key Implementation Principles

1. **Each issuer must be bound to trusted keys or introspection endpoints.** Never trust a JWK URL self-declared inside a token.
2. **Distinguish token type before creating an API identity.** For signed JWTs, classification relies on the token profile and verified data; for opaque tokens, on trusted metadata from the AS.
3. **No single heuristic works across all providers.** A three-part JWT, `sub`, `email`, `scope`, or `token_type=Bearer` alone does not prove "this is an access token."
4. **Never freely fall back between token types.** If JWT validation fails, never treat it as an ID token, refresh token, or try an issuer outside the contract.
5. **Never accept both ID tokens and access tokens interchangeably at the same API endpoint.** If an endpoint must support both browser sessions and bearer APIs, define explicit boundaries and filter configurations to avoid scheme ambiguity.
6. **Always enforce business authorization after token authentication.** `orders.read` may not suffice to read orders belonging to another tenant.

## 9. Spring Security Resource Server: JWT Access Tokens

A Spring Security Servlet Resource Server typically consists of:

- `BearerTokenAuthenticationFilter` extracts the Bearer token from the request.
- `JwtAuthenticationProvider` uses `JwtDecoder` to decode and verify the JWT.
- `NimbusJwtDecoder` checks the signature with configured keys/JWK and applies `OAuth2TokenValidator<Jwt>` instances.
- `JwtAuthenticationConverter` builds `Authentication` from the JWT and converts scopes into `SCOPE_`-prefixed authorities by default.
- `SecurityFilterChain` and the business layer enforce authorization.

Merely configuring `issuer-uri` does not make the API automatically enforce every **token purpose** or **audience**. Explicitly implement the access token contract your API requires.

### 9.1. Configuring Issuer and Audience

Basic example:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/demo
```

With an appropriate Spring Boot / Spring Security setup, the application can retrieve metadata/JWKS from the issuer and verify JWTs. However, if the API must accept only access tokens for `orders-api`, add explicit audience checks or framework-supported audience configuration.

Checking `iss` and signature alone is insufficient: ID tokens issued by the same OP would also pass those checks.

### 9.2. Strict Example: Resource Server Accepting RFC 9068 Tokens

The following example targets Spring Security versions providing `validateType(false)` and `JwtValidators.createAtJwtValidator()`. It sets the **RFC 9068 JWT access token profile** as the ingress contract, pinning `client_id` to a single illustrative application client. Ensure your specific library version and issuer actually support the profile before applying.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersResourceServerConfig {

    private static final String ISSUER =
            "https://id.example.com/realms/demo";
    private static final String API_AUDIENCE = "orders-api";
    private static final String ALLOWED_CLIENT = "web-client";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withIssuerLocation(ISSUER)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                // Allow JWT type to be checked by the access-token profile validator.
                .validateType(false)
                .build();

        decoder.setJwtValidator(
                JwtValidators.createAtJwtValidator()
                        .issuer(ISSUER)
                        .audience(API_AUDIENCE)
                        .clientId(ALLOWED_CLIENT)
                        .build());

        return decoder;
    }

    @Bean
    SecurityFilterChain ordersApi(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .requestMatchers(HttpMethod.POST, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.write")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

How to read this example:

- `withIssuerLocation(ISSUER)` binds the decoder to the issuer and trusted key source discovered from that issuer.
- `jwsAlgorithm(RS256)` explicitly specifies the signing algorithm the API allows; a JWT's `alg` header cannot widen the configuration.
- `validateType(false)` disables the **default Nimbus-decoder-layer type check** so the profile validator checks the type instead; it **does not mean skipping type checks altogether**.
- `createAtJwtValidator()` is the framework mechanism for checking access token profile constraints; `issuer`, `audience`, and `clientId` bind the token to the right source, API, and client for this example scenario.
- `hasAuthority("SCOPE_orders.read")` and `SCOPE_orders.write` are **API authorization rules**, independent of whether the authenticated JWT had the right token type.

**Limitations to understand:** The example API accepts tokens from only one client ID. If multiple clients are authorized, do not fake a single client ID; design a valid multi-client policy per your framework/Authorization Server capabilities. Never copy RFC 9068 profile code into a system whose issuer does not emit profile-compliant access tokens. Older Spring Security versions may lack these exact builder APIs; use the equivalent validation mechanism for your version.

### 9.3. Example When the Issuer Uses a Custom `token_use=access` Claim

If a provider emits JWT access tokens with a custom `token_use` claim, design a validator matching the provider contract. The example below demonstrates **AND-combined checks for type, issuer, and audience**. The snippet focuses on the validator; `JwtDecoder` must still verify the signature using allowed keys and algorithms.

```java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;

public final class JwtAccessTokenContracts {

    private JwtAccessTokenContracts() {}

    static OAuth2TokenValidator<Jwt> forOrdersApi(String trustedIssuer) {
        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(trustedIssuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains("orders-api")
                    ? OAuth2TokenValidatorResult.success()
                    : invalid("Token audience is not orders-api");

        OAuth2TokenValidator<Jwt> accessPurpose = jwt ->
                "access".equals(jwt.getClaimAsString("token_use"))
                    ? OAuth2TokenValidatorResult.success()
                    : invalid("Token purpose is not access");

        return new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audience, accessPurpose);
    }

    private static OAuth2TokenValidatorResult invalid(String message) {
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", message, null));
    }
}
```

Attach the validator via `decoder.setJwtValidator(JwtAccessTokenContracts.forOrdersApi(ISSUER))` **after** creating the decoder configured with trusted keys and algorithms. Note that `setJwtValidator(...)` replaces the registered validator; preserve all required checks for issuer, timestamps, audience, and token purpose inside the composite validator.

If the default decoder **already requires `typ=JWT`** and the provider emits a different `typ`, adjust JOSE type checking using your Spring Security version's API while retaining `token_use` and audience checks per policy. Never call `validateType(false)` as a "quick fix" without a profile validator or equivalent rule replacing it.

The goals of this design differ from the RFC 9068 example:

- **RFC 9068:** relies on `at+jwt` and claims/validations defined by the standard profile.
- **Provider-specific:** relies on the **actual issuer contract**, such as `token_use=access`, and the right audience.
- Never combine both profiles with a permissive OR if the provider does not guarantee how tokens are issued.

## 10. If the Access Token Is Opaque, How Do You Distinguish It?

Not every access token is a JWT. An Authorization Server can issue opaque tokens, for example:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer XoU6Dk...opaque-value...
```

The Resource Server cannot tell whether this token is an access token merely by decoding the string. Under OAuth 2.0 Token Introspection (RFC 7662), the API calls the Authorization Server's trusted endpoint to query **status and metadata**.

Illustrative introspection response:

```json
{
  "active": true,
  "iss": "https://id.example.com",
  "sub": "user-123",
  "client_id": "web-client",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1910000000,
  "token_type": "Bearer"
}
```

Understand each field:

- `active=true` means the introspection endpoint considers the token active in the request context; **it does not replace audience and authorization checks**.
- `aud` or resource-binding metadata, if provided, must target the appropriate API.
- `scope`/permission metadata must be mapped accurately and does not replace resource-level permission checks.
- `token_type=Bearer` specifies Bearer-scheme presentation only, **not standalone proof separating ID tokens from access tokens**.
- Optional fields depend on the Authorization Server; if insufficient information exists to prove the token has the right type and audience, align the contract with the issuer rather than guessing.

Spring Security Resource Server configuration for introspection:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: YOUR_SECRET_FROM_SECURE_CONFIGURATION
```

This wires up opaque token validation. The API must still enforce the **recipient and privilege contract** against metadata guaranteed by the Authorization Server. If custom audience/token-purpose checks are needed, wrap `OpaqueTokenIntrospector` or apply authorization policies on the attributes returned by introspection; do not assume the configuration above enforces every API policy automatically.

Security note: client credentials used to call introspection are **Resource Server secrets**; grant least privilege and store them via secret management rather than committing real values into the repository.

## 11. When a System Uses Both OIDC Login and API Resource Server

A single backend may simultaneously:

- Use **`oauth2Login()`** to act as an OIDC Client, verify ID tokens from the OP, and establish login sessions.
- Use **OAuth2 Client** to call other APIs with access tokens.
- Use **`oauth2ResourceServer()`** to protect its own API endpoints with client-supplied access tokens.

All three roles can coexist in the same application, provided you establish clear **path boundaries and security filter chains**. For instance, browser UI accesses `/app/**` with session cookies, while `/api/**` accepts access tokens per the API contract.

```text
Browser              Web Backend / OIDC RP             OpenID Provider
   |                      |                                |
   |--- login ----------->|------ OIDC authorization ----->|
   |                      |<----- ID token ----------------|
   |                      |  Verify ID token,
   |                      |  create session/cookie
   |
   |--- UI request with session cookie -------------------> RP
   |
   |--- API request with access token --> Resource Server
                                         ^            |
                                         |            v
                                      issuer/JWKS   API authorization
```

The diagram illustrates roles only, not a complete HTTP exchange. In a Backend-for-Frontend architecture, the browser may **never hold the access token directly**, while the backend holds tokens and makes API calls. Regardless of where tokens reside, **an ID token must never substitute for an access token sent to a Resource Server**.

Having both mechanisms produce an `Authentication` in Spring Security does not make one mechanism's credential valid for the other. If an API endpoint permits both sessions and bearer tokens, decide explicitly whether that is intentional and how to handle requests where both appear simultaneously.

## 12. Common Design Mistakes

| Bad Design | Consequence | Proper Design |
|---|---|---|
| API accepts any JWT validly signed by the OP | ID tokens / logout tokens / client assertions can be accepted by mistake | Enforce the access token profile and API audience |
| Checking only `sub` or email | Identity authentication tokens are mistaken for authorized API tokens | `sub` is only the subject; access requires the access token contract and authorization |
| Checking only `orders.read` scope | Skips issuer, audience, purpose, and signature | Tokens must pass the entire validation chain before evaluating scopes |
| Treating `typ=JWT` as an access token | Generic JWTs serve many purposes | Under RFC 9068 require `at+jwt`; if custom, use an explicit profile |
| Skipping `aud` checks because the issuer signed it | Tokens meant for other APIs/clients can be accepted | Audience is the recipient boundary |
| Trusting `kid` or `jku` in the token to fetch keys | Key confusion, SSRF, trust domain bypass | Use only keys/JWKS from configured trusted issuers |
| Allowing JWTs with any `token_use` | Fails to block ID/refresh tokens when provider separates token use | Require `token_use=access` when the issuer guarantees that claim |
| Treating `token_type=Bearer` from introspection as sufficient | Bearer transport scheme confused with token purpose | Verify resource/purpose per the introspection contract |
| Falling back to another issuer decoder when a validator fails | Lowers trust bar until some token slips through | Each issuer/profile has a pre-established trust policy |
| Accepting a DPoP proof JWT as an access token | Confuses proof of key possession with API authorization | Verify access token and DPoP proof as two distinct tasks |
| Opening every endpoint just because JWT carries `admin` role | Object-level and tenant privilege escalation | Enforce authorization per API and actual target object |
| Ignoring revocation when immediate revocation is required | Unexpired JWT continues working after revocation | Choose revocation/short-TTL/introspection strategy matching system requirements |

### A Concrete Anti-Pattern Example

```java
// NEVER validate tokens by merely decoding claims.
// jwt.getSubject() != null does NOT prove this is an access token.
// jwt.getHeaders().containsKey("kid") does NOT prove the signature was verified.
//
// Never write a condition like:
// if (jwt.getSubject() != null) allowRequest();
```

To authorize requests, the Resource Server must validate the token with a real verifier and then check issuer, audience, purpose, and permissions per the contract. Never turn the snippet above into a "manual JWT filter."

## 13. Scenarios with Multiple Resources, Multiple Issuers, or Token Exchange

### 13.1. One Access Token with Multiple Audiences

Some access tokens target multiple resources under the Authorization Server's contract. If `orders-api` receives a token with `aud=["orders-api","reporting-api"]`, acceptance must follow **the API's resource policy**, never a gut feeling that multi-audience tokens are always wrong or always fine.

In strongly segmented environments, issuing tokens whose audience covers only the target resource reduces the blast radius of a leaked token. If an issuer mints multi-audience tokens, the API must evaluate scopes, client, tenant, and resource constraints accordingly.

### 13.2. Multi-Issuer / Multi-Tenant

Suppose a system trusts two issuers, `issuer-A` and `issuer-B`. Each issuer has its own JWKS, and audiences or claim mappings may differ. Never merge keys and ignore issuer identity.

```text
issuer-A -> JWKS-A -> access-token contract A -> orders-api
issuer-B -> JWKS-B -> access-token contract B -> orders-api
```

An unverified JWT may carry `iss=issuer-B` to help select **one of the preconfigured decoders**, yet after signature verification `iss` must still match the selected decoder/profile. Never let a token introduce a new issuer or key source outside the trusted list.

### 13.3. OAuth 2.0 Token Exchange

In a microservice call chain, service A may need to exchange an access token meant for A into a new access token meant for service B via the Authorization Server, per OAuth Token Exchange design.

```text
Client -> Service A [access token aud=service-a]
Service A -> Authorization Server [token exchange per policy]
Authorization Server -> Service A [access token aud=service-b]
Service A -> Service B [access token aud=service-b]
```

Never forward the raw `aud=service-a` access token to service B and ask B to turn off audience validation. When B accepts wrong-audience tokens, boundaries between APIs collapse.

### 13.4. User Tokens and Machine Tokens

An API may accept both user-context tokens and `client_credentials` tokens. Specify explicitly which endpoints permit service principals and which require user principals.

For example, `POST /api/orders/sync` may allow the `sync-worker` service with `orders.sync`, while `GET /api/orders/me` requires a user context. A machine token's `sub` is not a logged-in human user. Never write policies assuming email or session presence simply because every request carries a JWT.

## 14. Designing Appropriate Error Responses

When a token has the wrong purpose or wrong recipient, that is a **credential authentication failure** for the API:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

When a token has been authenticated and accepted as an access token for the API, yet lacks operation privileges:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

This is the standard distinction per RFC 6750 and common Resource Server behavior. Exact status codes and challenges depend on your configured security chain, entry point, access denied handler, and transport (Bearer/DPoP).

Never return raw JWTs or sensitive metadata in error responses. Logs should separate categories like `wrong_issuer`, `invalid_signature`, `wrong_audience`, `wrong_token_type`, `missing_scope`, and `tenant_policy_denied`, without writing raw bearer credentials, refresh tokens, or authentication secrets to application logs.

**End-user message:** "Unable to access resource" may suffice. **Operational diagnostics:** distinguishing wrong-audience tokens from missing-scope tokens helps fix issuer/client config without weakening API protections.

## 15. Scenario Matrix to Cover When Designing the Contract

This table is a **scenario matrix for deriving validation requirements**, not the output of a test run:

| Input Sent to `orders-api` Resource Server | Signature / Issuer | Recipient / Purpose | Design Outcome |
|---|---|---|---|
| RFC 9068 access JWT `typ=at+jwt`, `aud=orders-api`, `orders.read` | Valid | Matches | Passes authentication; evaluate object permissions |
| OIDC ID token `aud=web-client` | Valid | Wrong audience/type | Reject |
| Access JWT `typ=at+jwt`, `aud=billing-api` | Valid | Wrong audience | Reject |
| JWT `typ=JWT`, `aud=orders-api` when policy **requires RFC 9068** | Valid | Fails `typ` profile | Reject |
| JWT with `token_use=id` when provider policy requires `access` | Valid | Wrong purpose | Reject |
| Client assertion `aud=token-endpoint` | Valid | Wrong target recipient | Reject |
| RP logout token | Valid | Wrong purpose | Reject |
| Opaque refresh token sent as Bearer API token | Not validated as access token | Wrong purpose | Reject |
| Self-declared `alg=none` JWT | Fails signed-JWT requirement | Not evaluated | Reject |
| JWT with invalid signature despite `typ=at+jwt` | Invalid | Not evaluated | Reject |
| Expired access JWT | Expired | Not evaluated | Reject |
| Contract-compliant access JWT missing `orders.write` | Valid | Matches | Deny authorization on POST |
| Access JWT with `orders.read` for another tenant | Valid | Matches | Deny object-level access |
| DPoP-bound access token without valid proof | Access token signature may be valid | Fails sender-binding check | Reject |
| Opaque token `active=true` whose metadata fails to prove right resource | Active per AS | Fails API contract | Reject or require additional metadata/contract |

### Separation of Responsibilities Across Components

| Component | Responsibility |
|---|---|
| **Authorization Server / OP** | Issue tokens with the right profile, audience, and scopes; publish trusted metadata/JWKS or introspection |
| **OAuth Client** | Present access tokens when calling APIs; use ID tokens for login handling; send refresh tokens to the AS |
| **API Gateway** | Enforce transport security, ingress credential policies, and edge-level constraints |
| **Resource Server JWT decoder / opaque introspector** | Verify origin, signature or token status; enforce token profile and audience |
| **Spring Security authorization** | Map scopes/authorities and specify which endpoint requires which privileges |
| **Application service / domain** | Enforce object, tenant, account, and business-rule permissions |

This contract should be documented explicitly across the Authorization Server, client, and API teams—never relying on "it looks like a JWT" or "same OP means it works for every API."

## 16. Key Takeaways

1. **An access token is recognized by its issuance and usage contract**, not merely by JWT format or the presence of a single claim.
2. **Signature + issuer + expiry are necessary but insufficient** when multiple JWT types are issued by the same issuer.
3. **Audience is the API boundary**: tokens meant for OIDC Clients, token endpoints, or other APIs must be rejected at the Resource Server.
4. **Token profile is the purpose boundary**: under RFC 9068 verify `at+jwt` and profile constraints; with provider-specific JWTs check the access-token signal guaranteed by the issuer.
5. **Refresh tokens, ID tokens, logout tokens, authorization codes, client assertions, and DPoP proofs are not API access tokens**, even when encoded as strings or JWTs.
6. **For opaque tokens, introspection must supply or bind enough metadata for the API to confirm the right resource and purpose.** `active=true` or `token_type=Bearer` alone does not replace the full contract.
7. **Scope and object permissions are evaluated after the token satisfies the contract.** Accepting a valid access token does not automatically permit every operation.
8. **Never weaken the contract just to "make the token work."** If a token has the wrong audience or type, fix the client/issuer configuration or use an appropriate token exchange flow.

A properly implemented Resource Server verifies **the right source**, **the right token type**, **the right recipient**, **the right validity state**, and **the right permissions** before opening an API. That is how you prevent cryptographically valid tokens from being reused for the wrong purpose.

## 17. Foundational References

- **RFC 6749 — The OAuth 2.0 Authorization Framework**: access tokens, refresh tokens, and grant semantics. https://www.rfc-editor.org/rfc/rfc6749
- **RFC 6750 — OAuth 2.0 Bearer Token Usage**: presenting bearer access tokens and error codes. https://www.rfc-editor.org/rfc/rfc6750
- **OpenID Connect Core 1.0**: ID tokens and Relying Party recipient rules. https://openid.net/specs/openid-connect-core-1_0.html
- **OpenID Connect Back-Channel Logout 1.0**: logout tokens with dedicated purpose. https://openid.net/specs/openid-connect-backchannel-1_0.html
- **RFC 7519 — JSON Web Token**: claims, headers, and JWTs. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 8725 — JWT Best Current Practices**: cross-JWT confusion, audience, and explicit typing. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens**: `at+jwt` profile for JWT access tokens. https://www.rfc-editor.org/rfc/rfc9068
- **RFC 7662 — OAuth 2.0 Token Introspection**: verifying opaque token status and metadata. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 8693 — OAuth 2.0 Token Exchange**: exchanging tokens by resource/audience and purpose. https://www.rfc-editor.org/rfc/rfc8693
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)**: verifying proofs and key-bound tokens. https://www.rfc-editor.org/rfc/rfc9449
- **Spring Security Reference — OAuth 2.0 Resource Server**: authenticating JWT or opaque tokens and declaring authorization. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
