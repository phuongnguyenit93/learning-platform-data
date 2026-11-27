# Applying a JWT Access Token Profile Compatible with Resource Servers

## 1. Context: A JWT with a Valid Signature Can Still Serve the Wrong Purpose

In an OAuth 2.0/OpenID Connect (OIDC) system using **Spring Security**, **Spring Authorization Server**, and Spring Boot, the Authorization Server (AS) issues access tokens for clients to call Resource Servers (RS). Many systems choose JWTs because the RS can verify signatures and claims locally without calling the AS for every request.

However, **not every JWT is an access token**. An OIDC ID token, a JWT client assertion, a JWT used for Token Exchange, or an internal JWT can all be validly signed yet carry different purposes and audiences. If the RS checks only the signature without verifying the right profile, issuer, audience, token type, and required claims, the API could accept a credential never meant for it.

For example, a booking system has `booking-bff`, `booking-api`, and `inventory-api`. A token issued for the Booking API must not be accepted by the Inventory API just because both APIs trust the same signing key. The two APIs need an explicit token contract, especially around **audience**.

The **JWT Access Token Profile** is standardized in **RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens**. This profile defines how to represent an access token as a JWT, including the JOSE header and required claims so Resource Servers interpret it consistently.

After this lesson, you will be able to:

1. Distinguish RFC 9068 JWT access tokens from general JWTs and OIDC ID tokens.
2. Recognize the JOSE header `typ=at+jwt` and its meaning.
3. Identify required claims such as `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, and `client_id`.
4. Design subject, audience, and scope semantics by grant type.
5. Configure Spring Authorization Server to issue profile-compliant JWT access tokens.
6. Configure Spring Security Resource Server to validate issuer, audience, algorithm, token type, and claims.
7. Map scopes to authorities and enforce authorization at the API.
8. Manage JWKS/key rotation, TTLs, revocation, and custom claims.
9. Build a positive/negative test matrix for the token profile.

## 2. What Is a JWT Access Token Profile?

JWT is a format for representing claims. It can be signed (JWS) or encrypted (JWE), yet **the JWT format alone does not say what the token is used for**. A JWT access token profile adds a contract for JWTs used as OAuth 2.0 access tokens.

RFC 9068 standardizes this contract so that Resource Servers recognize the token as a JWT access token rather than another kind of JWT; foundational claims have consistent names and meanings; issuer and audience are verified in the right context; and client ID, subject, issuance time, and token identifier are interpreted uniformly.

| Concept | Answers the question | Example |
|---|---|---|
| JWT | Is the credential structured as a JSON Web Token? | Header.payload.signature |
| OAuth access token | Does the credential authorize access to a Resource Server? | Bearer token calling an API |
| RFC 9068 JWT access token | Does the JWT access token conform to the header/claims profile? | JWS with `typ=at+jwt` and profile claims |

An RS256-signed JWT is **not automatically** an RFC 9068 access token. Likewise, an OAuth access token can be an opaque token rather than a JWT.

### 2.1. Why Is Signature Verification Alone Insufficient?

Suppose an API only parses the JWT, verifies the signature with the AS public key, and checks that `exp` has not passed. That still leaves questions unanswered:

- Was the token issued by the expected issuer?
- Is the token intended for the current API?
- Is this JWT an access token or an ID token?
- Which client requested the token?
- Is the token's subject a human user or a workload?
- Are the scopes sufficient for the endpoint?
- Did the token use an algorithm or key outside the allowlist?

**The profile defines the contract; the Resource Server must actively verify that contract.** Simply enabling a JWT decoder does not prove all RFC 9068 requirements are enforced.

## 3. Distinguishing Access Tokens from OIDC ID Tokens

OIDC builds on OAuth 2.0, yet ID tokens and access tokens serve different purposes.

| Property | JWT access token | OIDC ID token |
|---|---|---|
| Primary recipient | Resource Server | OIDC Client / Relying Party |
| Purpose | Grants API access | Delivers user authentication facts to the RP |
| Audience | Intended Resource/API receiving the token | RP's Client ID |
| Profile header type | `at+jwt` per RFC 9068 | Typically `JWT` per OIDC |
| Key claims | `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, `client_id` | `iss`, `sub`, `aud`, `exp`, `iat`, `nonce` when requested |
| Sent to APIs as Bearer | When issued for the API and allowed by policy | **No** |

A validly signed ID token for `booking-bff` does not mean `inventory-api` may accept it. An ID token's audience is the client; an API requires an access token issued for the right audience.

### 3.1. The `typ` Header

RFC 9068 requires JWT access tokens to carry the JOSE header parameter:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "as-signing-key-2026-01"
}
```

- `alg`: signing algorithm used by the AS.
- `typ`: identifies the JWT kind as an access token per profile.
- `kid`: identifier of the signing key in the JWK Set if the AS uses key IDs.

`typ=at+jwt` does not replace verifying signature, issuer, audience, expiry, or scopes. It is an additional disambiguation check. **Never accept a token merely because its header claims `at+jwt`**; an attacker can put that header on a forged JWT.

## 4. Required Claims Under RFC 9068

| Claim | Required | Meaning |
|---|---|---|
| `iss` | Yes | Issuer that issued the token |
| `exp` | Yes | Token expiration timestamp |
| `aud` | Yes | Resource Server or audience the token is meant for |
| `sub` | Yes | Subject represented by the token |
| `client_id` | Yes | OAuth client that requested the token |
| `iat` | Yes | Token issuance timestamp |
| `jti` | Yes | Unique JWT identifier |
| `scope` | Optional | Space-separated list of scopes as a string |
| `nbf` | Optional | Timestamp before which the token is not valid |
| `cnf` | Optional | Confirmation binding the token to a key/certificate |
| `auth_time`, `acr`, `amr` | Per use case | User authentication context when meaningful |

Additional claims must have clear semantics. Never invent claim names that collide with standards or reuse ID token claims without defining their access-token meaning.

### 4.1. `iss` — Issuer

`iss` identifies the issuing Authorization Server. The RS must compare it against a trusted configured issuer, typically a stable URI:

```text
iss = https://auth.example.com
```

Do not derive the issuer from the `Host` header of the incoming API request or from a caller-supplied claim. If the system supports multiple issuers, configure an explicit trust mapping and avoid accepting arbitrary issuers.

The issuer URL must match the metadata/JWKS used by the RS. Mismatches in scheme, host, or path should cause token rejection; never loosen validators to substring checks containing a domain name.

### 4.2. `sub` — Subject

`sub` identifies the subject represented by the token. Its semantics depend on the grant:

- With Authorization Code on behalf of a user, `sub` is usually a stable AS-managed user identifier.
- With Client Credentials, the token represents a workload/client; subject should reflect the appropriate client identity per profile.
- With Token Exchange/delegation, `sub` may be the represented user while the actor is expressed separately per policy.

Do not use mutable emails or usernames as subject if a stable, less revealing identifier meets requirements. Subject is not an access permission; the API must still check scopes and business authorization.

### 4.3. `aud` — Audience

`aud` indicates the intended recipient of the token:

```json
{
  "aud": [
    "https://booking-api.example.com"
  ]
}
```

The Booking API's RS must verify its own audience appears in `aud`. Tokens intended for the Inventory API must be rejected by the Booking API, even when issuer and signature are valid.

A system may use a single string or an array of audiences. Agree on exact identifiers between AS and RS. Never use `client_id` as the audience merely because it is the client's ID; the requesting client and receiving Resource Server have distinct roles.

### 4.4. `exp`, `iat`, and `nbf` — Lifecycle

- `iat` is when the token was issued.
- `exp` is when the token expires.
- `nbf` (if present) is the time before which the token must not be used.

The RS must verify the token is not expired, falls within its validity window, and handles clock skew within a deliberately small bound. Never configure huge clock skew just to mask infrastructure clock drift.

The AS should issue tokens with risk-appropriate TTLs, and the RS must synchronize clocks via NTP/reliable time services. An `iat` far in the future can signal an anomalous token.

### 4.5. `jti` — Token Identifier

`jti` is the JWT identifier. It helps with auditing, correlation, supplementary denylists/revocation, and incident investigation without logging raw tokens.

`jti` must be unique within the appropriate issuer scope. Never reuse the same `jti` across independently issued tokens. `jti` is neither a secret nor a bearer credential.

### 4.6. `client_id` — Requesting Client

`client_id` identifies the OAuth client that requested the token. This claim differs from `sub`:

- In user authorization, `sub` can be the user while `client_id` is the BFF/client.
- In Client Credentials, `sub` can represent the workload, while `client_id` still identifies the requesting client.
- In delegated flows, `client_id` helps trace which client made the request while `sub` can be the user.

The RS can use this claim for per-client policies, auditing, or quotas, but **never grant business permissions based solely on `client_id`**. Always check audience, scopes, and subject/context.

## 5. The `scope` Claim and Permission Mapping

RFC 9068 represents scopes using the `scope` claim as a **space-separated string of scopes**:

```json
{
  "scope": "bookings.read bookings.cancel"
}
```

Do not confuse this string with a custom JSON array, a `roles` claim, resource ownership, or internal admin roles.

Spring Security normally maps scopes to authorities prefixed with `SCOPE_`:

```text
bookings.read   -> SCOPE_bookings.read
bookings.cancel -> SCOPE_bookings.cancel
```

### 5.1. Configuring Scope Mapping

```java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter authoritiesConverter =
        new JwtGrantedAuthoritiesConverter();

    authoritiesConverter.setAuthoritiesClaimName("scope");
    authoritiesConverter.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(authoritiesConverter);
    return converter;
}
```

This snippet is for the **Resource Server**. When `scope` is issued per profile, the converter parses the space-separated scope string. If the system uses dedicated `roles` or `permissions`, write a separate converter with clearly defined semantics.

### 5.2. Scopes Do Not Replace Business Authorization

A token carrying `bookings.read` does not necessarily allow reading every booking. The API must still verify whether the user owns the booking, which tenant owns it, and whether business state allows the action.

```java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(HttpMethod.GET, "/bookings/**")
        .hasAuthority("SCOPE_bookings.read")
    .requestMatchers(HttpMethod.POST, "/bookings/*/cancel")
        .hasAuthority("SCOPE_bookings.cancel")
    .anyRequest().denyAll());
```

This is HTTP route-level authorization. The service/domain layer must still enforce permissions on the specific data objects, especially in multi-tenant systems.

## 6. Choosing a Profile Tailored to Each Resource Server

One Authorization Server can serve multiple Resource Servers, each with its own identifier and scopes:

| Resource Server | Example audience | Example scopes |
|---|---|---|
| Booking API | `https://booking-api.example.com` | `bookings.read`, `bookings.cancel` |
| Inventory API | `https://inventory-api.example.com` | `inventory.read` |
| Payment API | `https://payment-api.example.com` | `payments.status.read` |

### 6.1. Is One Token for Multiple APIs Always Good?

No. If a token carries multiple audiences, every listed API may accept the token according to policy. That widens the blast radius if the token leaks and creates token substitution risks.

Prefer tokens with a **narrow audience**, scoped solely to the API needed. If a workflow calls multiple APIs, request separate tokens per Resource Server or use Token Exchange to exchange tokens for the target audience under policy.

### 6.2. Audience Must Be Decided Server-Side

Never copy `aud` straight from an arbitrary request parameter into the JWT. The AS needs a trusted mapping among client registration, grant, permitted resources, and audience. If the AS supports a `resource` or `audience` parameter, verify the client is allowed to request a token for that resource and corresponding scopes. Caller-sent parameters are **requests**, not entitlements.

## 7. Configuring RegisteredClient to Issue JWT Access Tokens

In Spring Authorization Server, `RegisteredClient` defines grants, client authentication, scopes, and token settings. To use JWT access tokens, configure the `SELF_CONTAINED` format:

```java
RegisteredClient bookingBff = RegisteredClient
    .withId("booking-bff-internal-id")
    .clientId("booking-bff")
    .clientSecret(passwordEncoder.encode(secretFromSecureStore))
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("https://app.example.com/login/oauth2/code/booking-bff")
    .scope(OidcScopes.OPENID)
    .scope("bookings.read")
    .scope("bookings.cancel")
    .tokenSettings(TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .build())
    .build();
```

This is a client model snippet, not an entire Authorization Server. The application still requires `RegisteredClientRepository`, `OAuth2AuthorizationService`, issuer, JWK source/signing keys, and a compatible `SecurityFilterChain`.

- `SELF_CONTAINED` selects self-contained tokens; JWT signer/JWK configuration must be present.
- The 5-minute TTL is illustrative only.
- Scopes on the registration are only the permissions the client may request, not a guarantee every token gets all scopes.
- `clientSecret` must come from a secret manager and be protected properly.
- Client authentication and user authentication are two separate operations.

### 7.1. `SELF_CONTAINED` Does Not Automatically Enable RFC 9068

`OAuth2TokenFormat.SELF_CONTAINED` selects the self-contained token format. It **does not automatically guarantee** full RFC 9068 compliance.

You must verify or customize:

- Header `typ=at+jwt`.
- Required claims.
- Semantics of `sub`, `aud`, and `client_id`.
- `scope` as a space-delimited string when required by the profile.
- Asymmetric signing algorithm and key management.
- RS validation of issuer, audience, token type, and claims.

Never claim "RFC 9068 compliant" merely because your access tokens are JWTs.

## 8. Customizing JWTs with OAuth2TokenCustomizer

Spring Authorization Server provides `OAuth2TokenCustomizer<JwtEncodingContext>` to add claims/headers when the generator creates a JWT. The example below illustrates a profile for Booking API access tokens:

```java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> accessTokenProfileCustomizer() {
    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }

        context.getJwsHeader().type("at+jwt");

        context.getClaims().claim(
            "client_id",
            context.getRegisteredClient().getClientId());

        context.getClaims().audience(
            List.of("https://booking-api.example.com"));

        context.getClaims().claim(
            "scope",
            String.join(" ", context.getAuthorizedScopes()));

        if (AuthorizationGrantType.CLIENT_CREDENTIALS.equals(
                context.getAuthorizationGrantType())) {
            context.getClaims().subject(
                context.getRegisteredClient().getClientId());
        }
    };
}
```

Imports are omitted. This is a **profile customization pattern**; check the exact API of your Spring Authorization Server version and pair it with real JWK/issuer configuration.

### 8.1. Customize Only Access Tokens

`OAuth2TokenCustomizer` can be called for multiple token types. Guarding on `OAuth2TokenType.ACCESS_TOKEN` prevents accidentally adding `typ=at+jwt` or access token claims to ID tokens.

Never change an ID token's header to `at+jwt`. ID tokens must follow OIDC, with different audiences and semantics.

### 8.2. Claims the Generator May Already Supply

Spring Authorization Server may generate standard claims such as issuer, subject, audience, issued-at, expiration, token ID, and scopes from context. **Exact defaults depend on version and configuration.**

Therefore, the customizer should explicitly set required profile claims that the implementation does not already produce properly; avoid generating a new `jti` overwriting framework-managed values unless necessary; avoid arbitrarily overwriting `iss`, `iat`, or `exp`; and inspect the signed token payload in integration tests.

In the example, `client_id` is explicitly set, audience comes from a server-side mapping, and scope is serialized as a string. In multi-API systems, never hardcode a single audience for all clients/grants; use a server-side policy resolver.

### 8.3. `sub` Semantics by Grant

Example setting `sub` only for Client Credentials:

```java
if (AuthorizationGrantType.CLIENT_CREDENTIALS.equals(
        context.getAuthorizationGrantType())) {
    context.getClaims().subject(
        context.getRegisteredClient().getClientId());
}
```

For Authorization Code representing a user, keep the authenticated subject from the trusted identity source. For Token Exchange, keep subject/actor per delegation policy. Never apply `sub=client_id` across all grants, as that erases user identity.

### 8.4. Do Not Copy All Claims from the ID Token

An access token may need some identity information for RS authorization, yet should not copy every claim from the ID token. Minimize PII; avoid exposing email, phone, address, or unnecessary profile attributes; avoid oversized tokens; use UserInfo or a dedicated API when the client needs profile data.

## 9. Defining Claim Contracts per API

Sample contract for the Booking API:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": [
    "https://booking-api.example.com"
  ],
  "exp": 1794825600,
  "iat": 1794825300,
  "jti": "a-unique-token-id",
  "client_id": "booking-bff",
  "scope": "bookings.read bookings.cancel"
}
```

This is an **illustrative payload**, not a signed token.

| Claim | JSON type | API rule |
|---|---|---|
| `iss` | string | Matches configured issuer |
| `sub` | string | Stable subject; never treated as automatic permission |
| `aud` | string or string array | Must contain the API's audience |
| `exp` | number | NumericDate and not expired |
| `iat` | number | NumericDate; not unreasonably in the future |
| `jti` | string | Required, token identifier |
| `client_id` | string | Required, client that requested the token |
| `scope` | string | Space-delimited; only scopes understood by the API |

Do not check only for claim presence; validate data types and appropriate length/range bounds. When `aud` is an array, the API must perform exact membership checks rather than comparing serialized JSON strings.

### 9.1. Custom Claims and Namespaces

If you need tenant, organization, entitlement, or actor context, define the trusted data source, who may receive the claim, which Resource Server may interpret it, schema/version, change procedure, and whether it contains PII.

Namespace example:

```json
{
  "https://claims.example.com/tenant_id": "tenant-a",
  "https://claims.example.com/policy_version": "2026-11"
}
```

The names above are examples only. Avoid generic claims like `role` or `permissions` without a shared schema and clear ownership.

## 10. Configuring Resource Server to Verify Issuer, Audience, and Type

The Resource Server must verify the signature using public keys from a trusted source, along with issuer, timestamps, audience, and profile. Example using `NimbusJwtDecoder` with a JWK Set URI:

```java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://auth.example.com";
    String jwkSetUri = "https://auth.example.com/oauth2/jwks";
    String expectedAudience = "https://booking-api.example.com";

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwkSetUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audience =
        jwt -> jwt.getAudience().contains(expectedAudience)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Required audience is missing",
                    null));

    OAuth2TokenValidator<Jwt> accessTokenType =
        jwt -> "at+jwt".equalsIgnoreCase(
                String.valueOf(jwt.getHeaders().get("typ")))
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "JWT is not an access token profile",
                    null));

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndTime,
            audience,
            accessTokenType,
            requiredProfileClaims()));

    return decoder;
}
```

This is a **Resource Server snippet**; imports and `SecurityFilterChain` configuration are omitted. The JWK Set URI must belong to a trusted Authorization Server. This example allows only RS256; if the AS uses ES256, configure the corresponding allowlist and test it.

### 10.1. Validator for Required Claims

```java
private OAuth2TokenValidator<Jwt> requiredProfileClaims() {
    return jwt -> {
        boolean valid =
            jwt.getIssuer() != null
            && jwt.getSubject() != null
            && !jwt.getSubject().isBlank()
            && jwt.getAudience() != null
            && !jwt.getAudience().isEmpty()
            && jwt.getExpiresAt() != null
            && jwt.getIssuedAt() != null
            && jwt.getId() != null
            && !jwt.getId().isBlank()
            && jwt.getClaimAsString("client_id") != null
            && !jwt.getClaimAsString("client_id").isBlank();

        return valid
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Required JWT access token claim is missing",
                    null));
    };
}
```

This supplementary validator enforces claim presence per contract. `JwtValidators.createDefaultWithIssuer` handles default validations including issuer and timestamps; still verify behavior against your actual version.

If a profile token omits `scope`, endpoints requiring scopes must deny it at the authorization layer. Not every token in a system must contain `scope` if there are valid use cases issuing no scopes.

### 10.2. Pinning Algorithms

Do not let the token header decide which algorithms are accepted. The RS must enforce an allowlist aligned with key material and policy, rejecting:

- `alg=none`.
- Algorithms disallowed by your organization.
- Key type/algorithm mismatches.
- Weak or deprecated legacy algorithms.

RFC 9068 requires asymmetric signatures for the JWT access token profile. Do not substitute an HMAC shared secret when targeting RFC 9068 compliance.

### 10.3. Never Fetch JWK Set URIs from the Token

The RS must fetch public keys only from a trusted configured URI or verified issuer metadata. Never read `jku` or `x5u` from a token and download keys from that URL; doing so enables SSRF and lets attackers control the key source.

## 11. Scopes and Endpoint Authorization in Spring Security

A Resource Server configuration can wire the decoder and converter:

```java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtDecoder jwtDecoder,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.GET, "/bookings/**")
                .hasAuthority("SCOPE_bookings.read")
            .requestMatchers(HttpMethod.POST, "/bookings/*/cancel")
                .hasAuthority("SCOPE_bookings.cancel")
            .anyRequest().denyAll())
        .oauth2ResourceServer(resourceServer ->
            resourceServer.jwt(jwt -> jwt
                .decoder(jwtDecoder)
                .jwtAuthenticationConverter(jwtAuthenticationConverter)));

    return http.build();
}
```

This is the **Booking Resource Server** chain, not the Authorization Server. If a single application both runs the AS and exposes APIs, separate the `SecurityFilterChain` beans and matchers properly for the two roles.

### 11.1. Do Not Map Every Claim to an Authority

Never automatically turn `tenant_id` into `ROLE_ADMIN` or `groups` into authorities without an explicit mapping. Claims are issuer-signed data, while their semantics are defined by the application contract.

Keep clear boundaries among authentication, coarse-grained scope authorization, and fine-grained per-record/tenant authorization.

## 12. `cnf` and Sender-Constrained Access Tokens

Ordinary Bearer JWT access tokens can be used by anyone who possesses the token before expiration. If your threat model requires reducing stolen-token risks, consider mTLS certificate-bound access tokens per RFC 8705 or DPoP per RFC 9449.

Example claim structure:

```json
{
  "cnf": {
    "x5t#S256": "BASE64URL_CERTIFICATE_THUMBPRINT"
  }
}
```

This is only a claim structure example, not a complete mTLS configuration. The Resource Server must verify that the request is genuinely bound to the matching certificate/key. **Checking `cnf` without verifying the proof/certificate does not create a sender constraint.**

Never emit a `cnf` claim from a caller-sent header. The claim must come from trusted binding verification at the AS.

## 13. JWT TTL, Revocation, and Privilege Changes

Self-contained JWTs allow local RS verification, yet issued tokens remain valid until `exp` unless the RS checks revocation state.

| Event | Typical impact |
|---|---|
| Lowering `accessTokenTimeToLive` | New tokens are shorter; existing tokens do not change their `exp` |
| Revoking refresh token | Stops that refresh token from minting new tokens; living access tokens need their own policy |
| Disabling client | Blocks new issuance; old JWTs do not vanish automatically |
| Removing scope from client | Old tokens may still hold previously issued scopes |
| Rotating AS signing key | RS must fetch the new key while still validating living tokens signed by the old key during overlap |
| Revoking JWT by `jti` | Takes immediate effect only if the RS checks a denylist/introspection or equivalent mechanism |

Options include short TTLs, opaque/reference tokens with introspection, `jti` denylists, token versions, or sender-constrained tokens. Each carries distinct latency/state/availability costs.

**Plain JWT signature validation does not provide immediate revocation.**

## 14. JWKS and Signing Key Rotation

The AS signs JWTs with a private key; the RS verifies them with public keys published via JWKS. The `kid` header helps the RS pick the right key.

Safe key rotation workflow:

1. Generate a new signing key in KMS/HSM or a protected key store.
2. Publish the new public key in JWKS alongside the old key.
3. Wait long enough for RSs/caches to fetch the new key.
4. Switch the AS to sign new tokens with the new key.
5. Monitor signature verification failures and cache misses.
6. Keep the old public key long enough to verify living old tokens and accommodate cache/rollout policies.
7. Remove the old key only when no valid tokens remain to verify or an explicit revocation plan exists.

Never delete the old public key immediately upon starting to sign with the new key; old tokens will fail verification before `exp`.

### 14.1. `kid` Is Not Proof of Trust

`kid` is solely a selector. The RS must still fetch keys from a trusted JWK Set and validate key type, algorithm, and signature. Never treat `kid` as a URL or let it control file paths.

### 14.2. JWKS Caching and Key Lookup Incidents

When an RS encounters an uncached `kid`, libraries may refresh JWKS. Enforce timeouts/retries and rate limits so forged tokens with random `kid` values cannot flood the AS with requests.

Use framework-managed JWK sources, verify caching behavior, and monitor key retrieval errors. Never fetch JWKS manually on every API request.

## 15. Sensitive Claims, Privacy, and Token Size

JWTs are normally signed but **not encrypted** in standard JWS profiles. Token holders can decode the payload. Therefore, never place passwords, client secrets, API keys, private keys, payment details, or unnecessary PII into claims.

Prefer stable, low-disclosure subject identifiers, minimal scopes, narrow audiences, and custom claims genuinely required for authorization. If an API needs mutable data, query a trusted data source instead of stuffing everything into tokens.

### 15.1. Do Not Use JWTs as a Database Snapshot

Suppose a user is removed from a tenant while their JWT with `tenant_role=admin` still has 30 minutes left. If the RS trusts stale claims alone, access persists after the business state changed.

For fast-changing data or immediate revocation requirements, check live status at a service/authorization store or reduce TTL appropriately.

## 16. Separating the Access Token Profile from the Token Response

The Token Endpoint returns an OAuth response such as:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "SIGNED_JWT_VALUE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "bookings.read"
}
```

Two easily confused `typ`/`token_type` concepts:

- JOSE header inside the JWT: `typ=at+jwt` — JWT type per RFC 9068.
- Token response: `token_type=Bearer` — how the client sends the token in the HTTP Authorization header.

**`token_type` does not replace JOSE `typ`.** A response saying `Bearer` does not prove the token is an RFC 9068 JWT access token. Token responses require appropriate cache directives, typically `Cache-Control: no-store` and `Pragma: no-cache`.

## 17. Common Implementation Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Verifying only the signature | Accepts tokens with wrong issuer/audience/purpose | Validate the full profile |
| Accepting any JWT signed by the same AS | ID tokens/assertions can be misused | Verify `typ=at+jwt` and audience |
| Skipping `aud` | Tokens for API A work on API B | Dedicated audience validator per RS |
| Using `client_id` as audience | Confuses requesting client with target resource | Use resource identifiers |
| Missing `client_id` or `jti` | Violates profile claim contract | Ensure required claims and test |
| `scope` as array when profile requires string | Inconsistent interoperability | Serialize space-delimited string |
| Setting `sub` to email | Changing email changes identity; exposes PII | Stable, low-disclosure subject |
| Setting `sub=client_id` for all grants | Loses user subject in user flows | Choose semantics by grant |
| Access token customizer alters ID token | OIDC RP may break | Customize only when token type is ACCESS_TOKEN |
| Selecting `SELF_CONTAINED` and claiming RFC 9068 | JWT format alone is not the profile | Verify header and required claims |
| Using HMAC shared secret while claiming RFC 9068 | Violates asymmetric signature requirement | Use asymmetric signing |
| RS fetches `jku` from token | SSRF / arbitrary key trust | Use trusted JWKS URI only |
| Deleting old key immediately after rotation | Old tokens fail verification | Overlap keys across TTL/cache window |
| Trusting `cnf` without verifying proof | Fake sender constraint | Verify certificate/DPoP proof |
| Embedding PII and overly broad privileges | Token leak causes severe blast radius | Data minimization, narrow audience/scope |
| Testing only happy-path tokens | Fails to catch token substitution | Test ID tokens and wrong issuer/audience/type |

## 18. Testing the Profile on the Authorization Server

Test tokens **after the generator creates and signs them**, not merely the customizer bean in isolation.

### 18.1. Checking Header and Claims

| Element | Required result |
|---|---|
| JOSE `typ` | `at+jwt` |
| JOSE `alg` | Asymmetric algorithm on allowlist |
| JOSE `kid` | Matches a key in trusted JWKS |
| `iss` | Configured issuer |
| `sub` | Subject appropriate to the grant |
| `aud` | Target Resource Server |
| `exp` | Valid expiration timestamp |
| `iat` | Issuance timestamp |
| `jti` | Non-empty and unique identifier |
| `client_id` | Requesting client |
| `scope` | Space-delimited string if issued |

If the framework already generates a claim, tests must still assert it is accurate; do not re-customize it just to pass tests.

### 18.2. Testing per Grant

- Authorization Code: `sub` is the authenticated user, `client_id` is the requesting client, `aud` is the intended API.
- Client Credentials: `sub` reflects the workload/client per profile, `client_id` identifies the client.
- Token Exchange: `sub` and actor context follow delegation policy, new audience is strictly checked.
- Refresh Token: new access token preserves subject/client semantics and applies current scopes/TTL.

Do not expect identical claim values across every grant. The core contract must stay consistent while subject values and permissions fit the context.

## 19. Testing the Resource Server with Spring Security

### 19.1. Positive/Negative Matrix

| Case | Token | Expected result |
|---|---|---|
| Valid profile token | Valid issuer, key, `typ`, audience, expiry, claims | Authenticated; authorized by scope |
| Wrong issuer | `iss` from untrusted source | 401 |
| Wrong audience | `aud` lacks current API | 401 |
| ID token | `typ` is not `at+jwt` or audience is client | 401 |
| JWT assertion | Validly signed JWT with wrong purpose/audience/type | 401 |
| Invalid signature | Tampered payload | 401 |
| `alg=none` | No trusted signature | 401 |
| Disallowed algorithm | Algorithm outside policy | 401 |
| Expired | `exp` in the past | 401 |
| Before `nbf` | Token not yet active | 401 |
| Missing `client_id` | Violates profile contract | 401 |
| Missing `jti` | Violates profile contract | 401 |
| Missing `sub` | Violates profile contract | 401 |
| Missing scope | Token lacks endpoint's required permission | 403 |
| Different scope | Holds `inventory.read` while calling Booking API | 403 or 401 per policy/audience |
| Old token after key rotation | Old `kid` still in JWKS overlap | Verified while otherwise valid |
| Token with `cnf` but request lacks proof | Sender-constrained policy | Rejected |

### 19.2. Testing the Audience Validator

You can construct mock Jwt objects to unit-test validator success/failure. However, integration tests with a real `JwtDecoder` are needed to verify signature, header, issuer, audience, and timestamps together.

Do not mock every validator and conclude the Resource Server complies with RFC 9068. Tests must exercise the real decoder configuration.

### 19.3. Testing Scope Authorization

Use `MockMvc`/HTTP integration tests to verify:

- Token with `bookings.read` succeeds on GET.
- Token with only `inventory.read` is rejected on Booking GET.
- Token with `bookings.read` but without `bookings.cancel` is rejected on POST cancel.
- Valid token whose subject does not own the record is rejected at the domain layer.
- Token with valid scope but wrong tenant cannot read another tenant's records.

These tests prove authentication and authorization act as two distinct layers.

## 20. Operations, Observability, and Troubleshooting

### 20.1. Metrics to Track

- Token rejection rates by reason: signature, issuer, audience, expiry, type, missing claim.
- `401` and `403` rates by Resource Server/route.
- JWKS cache miss rates by key ID and JWKS fetch latency.
- Token issuance latency and signing/KMS errors.
- Token size distribution and oversized-header errors.
- Time from AS key rotation until RS verifies the new key.
- Active/expiring token counts by profile and audience if safely measurable.

Never put raw JWTs, subject PII, unbounded token IDs, or dynamic full audiences into metric labels. Use error categories, normalized issuer/resource names, and safe correlation IDs.

### 20.2. Auditing Without Logging Tokens

You can log event types `ACCESS_TOKEN_ISSUED`, `JWT_VALIDATION_FAILED`, `SIGNING_KEY_ROTATED`; client ID and issuer per policy; normalized audience, grant type, and scopes; `jti` or an appropriate pseudonym for investigation; timestamp, correlation ID, error code, and key ID.

Never log raw access tokens, ID tokens, refresh tokens, client secrets, or private signing keys.

### 20.3. When the RS Suddenly Returns Mass 401s

Investigate in order:

1. Did the AS change its issuer or `iss` configuration?
2. Do newly issued tokens carry the right `aud` and `typ`?
3. Can the RS fetch JWKS; is the new `kid` present?
4. Is the signing algorithm still in the RS allowlist?
5. Are AS/RS clocks skewed, causing tokens to be not yet valid or prematurely expired?
6. Did a customizer alter `sub`/`scope` semantics or serialize a claim with the wrong type?
7. Is any deployment accidentally sending ID tokens instead of access tokens?
8. Are caches/JWKS/decoders holding stale configuration?

Never fix 401s by removing audience validation or accepting any issuer. Fix the contract or key rollout root cause.

## 21. RFC 9068 Adoption Checklist

- [ ] AS issues JWT access tokens when required by use case and token format.
- [ ] JOSE header uses `typ=at+jwt` for the access token profile.
- [ ] JWTs are signed using an allowlisted asymmetric algorithm.
- [ ] `iss` is a trusted, stable issuer.
- [ ] `sub` represents the right subject for each grant.
- [ ] `aud` names the target Resource Server; RS verifies exact membership.
- [ ] `exp` and `iat` are valid; clock skew is tightly bounded.
- [ ] `jti` has an appropriately unique value.
- [ ] `client_id` identifies the requesting client.
- [ ] `scope` uses correct semantics and encoding; RS maps scopes to authorities.
- [ ] ID tokens are never accepted in place of access tokens.
- [ ] Tokens are never accepted solely because their signature is valid.
- [ ] JWKs are never fetched from token-supplied URLs.
- [ ] JWKS/key rotation process maintains adequate overlap duration.
- [ ] Revocation/TTL policies match access-termination requirements.
- [ ] Custom claims are minimal and omit secrets or unnecessary PII.
- [ ] Tests cover valid tokens, wrong issuer/audience/type/alg/exp, and missing claims.
- [ ] Tests cover 401/403, scopes, and ownership/tenant checks at the API.
- [ ] Metrics/audits never store raw JWTs or secrets.

### Core Takeaways

**RFC 9068 defines a profile for OAuth 2.0 access tokens represented as JWTs.** This profile is not equivalent to any signed JWT and must not be confused with OIDC ID tokens. A Resource Server must verify the signature with trusted keys, allowed algorithms, issuer, audience, timestamps, JOSE `typ=at+jwt`, and required claims.

In Spring Authorization Server, `SELF_CONTAINED` selects the JWT format; `OAuth2TokenCustomizer<JwtEncodingContext>` completes the header and claims per contract. In Spring Security Resource Server, `JwtDecoder`, validators, and authority converters enforce verification. Only when **the AS issues and the RS verifies the same explicit profile** can JWT access tokens be used safely and consistently across services.

## References

- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705)
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
