# Reading Token Contents for Diagnostics Does Not Mean the Token Is Verified

When developing a **Spring Security OAuth 2.0 OIDC Resource Server**, developers often need to inspect a JWT access token to check `iss`, `aud`, `scope`, `exp`, or `kid` for troubleshooting. That is helpful, yet there is a mandatory security boundary to remember:

> **Being able to read a JWT's header and payload proves only that those segments can be decoded into data. It does not prove that the token was issued by a trusted Authorization Server, has not been altered, is still valid, or is permitted for the current API.**

In a standard JWS-formatted JWT, the header and payload are **Base64URL-encoded**, not confidentially encrypted. Anyone holding the token string can read its claims without needing a private key or public key. **Signature verification** and **claim policy validation** are separate steps that must be performed by trusted components of the Resource Server.

This lesson focuses on distinguishing the three actions **decode → verify → authorize**, what can and cannot be concluded from an unverified JWT, and how to handle this properly in Spring Security.

## 1. A Debugging Scenario That Very Easily Misleads

Suppose a client calls an order management API:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIn0...
~~~

The developer pastes the JWT into a decoder tool and sees hypothetical contents:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 2000000000
}
~~~

This data **helps form a hypothesis**: the token looks intended for `orders-api`, carries order read/write scopes, and has a future expiration timestamp. Yet you cannot conclude that the API should return `200 OK`.

An attacker can easily construct the exact same payload and Base64URL-encode it. Without signing it using the issuer's real key, that token must be rejected by the Resource Server. Even a token with a valid signature can still be rejected for **wrong issuer, wrong audience, expiration, not-yet-valid timing, or failing application policies**.

| Action | What do you learn? | What is NOT yet proven? |
|---|---|---|
| **Decode** header/payload | What algorithm, subject, permissions, and timestamps the token *self-declares* | Origin, integrity, validity, and actual permissions |
| **Verify** signature/MAC | Data is protected by a valid key under the configured algorithm and trust settings | Whether the token is unexpired, meant for this API, or has sufficient permissions |
| **Validate** claims | Token satisfies conditions such as `iss`, `aud`, `exp`, `nbf`, and token type | Whether the user is authorized for a specific record/resource |
| **Authorize** request | A specific operation is permitted given the principal, authorities, and policy | Does not mean other operations are allowed |

In Spring Security documentation, the word "decode" in **`JwtDecoder`** covers far more than "Base64URL-decoding": a `JwtDecoder` implementation is responsible for processing the JWT according to verification and validation configuration. Never equate it with `Base64.getUrlDecoder()`.

## 2. JWT Belongs to the JOSE Standard Family

**JOSE (JSON Object Signing and Encryption)** is a family of standards specifying how to protect JSON data via signatures, MACs, or encryption. When working with JWT, distinguish several concepts:

- **JWT (JSON Web Token, RFC 7519):** token structure carrying claims.
- **JWS (JSON Web Signature, RFC 7515):** protects integrity/signing origin with a digital signature or MAC.
- **JWE (JSON Web Encryption, RFC 7516):** protects content confidentiality via encryption.
- **JWK (JSON Web Key, RFC 7517):** JSON representation of cryptographic keys.
- **JWA (JSON Web Algorithms, RFC 7518):** defines algorithm identifiers used in JOSE.

A Resource Server's JWT access token is typically a **signed JWT represented in JWS Compact Serialization**:

~~~text
<base64url(protected-header)>.<base64url(payload)>.<base64url(signature)>
~~~

Three dot-separated parts:

~~~text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIn0
.
eyJpc3MiOiJodHRwczovL2lkcC5leGFtcGxlLmNvbSJ9
.
<signature-segment>
~~~

This illustrates structure only; abbreviated segments are not an authenticatable JWT.

### What Does the JWS Header Say?

Example header after Base64URL-decoding:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "at+jwt"
}
~~~

- `alg` **self-declares** the JWS protection algorithm, such as `RS256`.
- `kid` **self-declares** a hint for the key identifier to use when verifying the signature.
- `typ` **self-declares** the object type; `at+jwt` indicates an RFC 9068 JWT access token profile when the issuer uses that profile.

The header is **untrusted input before verification**, even when it looks right for your system. The Resource Server must never see `alg=RS256` and blindly assume the token was validly signed with RS256, nor see `kid` and fetch keys from any arbitrary address suggested by the token.

### What Does the JWT Payload Say?

Example payload:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "sub": "alice",
  "aud": ["orders-api"],
  "iat": 1980000000,
  "nbf": 1980000000,
  "exp": 2000000000,
  "scope": "orders.read",
  "client_id": "shop-web"
}
~~~

These are **claims** carried by the token. Prior to verification, every claim is merely **data read from an untrusted source**. For example, `sub=alice` is not enough to confirm the request belongs to Alice, and `scope=orders.read` does not yet grant permission to read orders.

### Signature Is Not Like Payload

For JWS using `RS256`, the Authorization Server signs with a private key; the Resource Server verifies with a trusted public key. The signature depends on **the exact signed bytes**, consisting of the JWS-encoded header and payload.

~~~text
Base64URL(header) + "." + Base64URL(payload)
                   |
           signing algorithm
                   |
               signature
~~~

If the payload is changed from `orders.read` to `orders.write` without valid signing capability, the data still Base64URL-decodes cleanly, yet **signature verification must fail**.

**Signing is not secret encryption:** anyone holding a JWS-formatted JWT can read the payload without a key. Therefore, never put passwords, session secrets, or unnecessary sensitive data into a JWT.

## 3. What Does Base64URL Decoding Actually Do?

Base64URL is a way to turn binary data into characters safe for URLs and tokens. It is reversible without knowing any secret key.

Simple example:

~~~text
eyJzdWIiOiJhbGljZSJ9
          |
   Base64URL decode
          v
{"sub":"alice"}
~~~

Any program with a Base64URL decoder can do this. Being "readable valid JSON" proves only that the data format appears plausible.

### Java Snippet for Diagnostic Use Only

The example below reads the header and payload **of a three-part compact JWS**. It **performs no signature verification and checks no issuer, audience, expiration, or scope**:

~~~java
package com.example.security.debug;

import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class JwtInspectOnly {

    private JwtInspectOnly() {
    }

    public static void inspectUntrusted(String compactJws) {
        String[] parts = compactJws.split("\\.", -1);

        if (parts.length != 3) {
            throw new IllegalArgumentException(
                "Expected a three-part compact JWS");
        }

        System.out.println("UNTRUSTED header: " + base64UrlDecode(parts[0]));
        System.out.println("UNTRUSTED payload: " + base64UrlDecode(parts[1]));
    }

    private static String base64UrlDecode(String segment) {
        byte[] bytes = Base64.getUrlDecoder().decode(segment);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
~~~

This code is suitable for **exploring synthetic token structures in a controlled development environment**. It does not validate JSON schemas, bound input sizes, or verify any security properties of the token. Therefore, never use it as an authentication handler, authorization middleware, or public "debug JWT" endpoint.

In real systems, avoid `System.out.println` with sensitive tokens or claims because stdout may be collected into centralized logs. When investigating, extract only permitted low-sensitivity fields and clearly mark them **unverified**.

### Thought Experiment: Forged Payloads Are Still Readable

Consider two payloads:

~~~json
{
  "sub": "alice",
  "scope": "orders.read"
}
~~~

and:

~~~json
{
  "sub": "admin",
  "scope": "orders.write"
}
~~~

Both can be encoded into valid Base64URL. A decode-only program prints both. It cannot tell which payload was signed by the issuer, which was tampered with, or which was fabricated by the sender.

Only **cryptographic verification combined with claim validation policies** separates what "the token says about itself" from data the Resource Server can trust in the system.

## 4. Why Can Web or Browser JWT Decoders Mislead?

A JWT viewer typically performs three tasks with varying trustworthiness:

1. **Splits three segments** on dots.
2. **Base64URL-decodes** the header and payload.
3. **May** verify the signature if configured with the right key and algorithm; many tools only decode by default.

A UI displaying readable content or saying "JWT decoded" is not proof that the token was verified. Even a tool reporting "signature verified" does not guarantee the token has the right `iss`, `aud`, `exp`, or token type accepted by **this Resource Server**.

When troubleshooting:

- Prefer **local/offline** tools with test tokens; never paste live active access tokens into unauthorized websites.
- Never paste tokens into tickets, chats, screenshots, issue trackers, or logs.
- Check whether a tool **genuinely uses a trusted public key** or merely renders JSON strings.
- Treat all unverified data as **untrusted claims**, even familiar fields like `role`, `scope`, or `email`.
- If a token is an opaque string or JWE, splitting into three parts and Base64URL-decoding the payload will not apply.

**A debug tool is not a trust anchor.** The trust anchor is the key source, issuer, and verification policy configured on the Resource Server from trusted infrastructure.

## 5. Signature Verification: Which Step Makes Data Trustworthy?

Consider a JWT issued by an Authorization Server. With standard asymmetric signing:

~~~text
Authorization Server                         Resource Server
      |                                             |
      | Private key: signs JWT                      |
      |                                             |
      +------------- JWT -------------------------->|
                                                    |
                                        Fetch trusted public key
                                        from AS config / JWKS
                                                    |
                                        Verify JWT signature
                                                    |
                                              true / false
~~~

After choosing an allowed algorithm and matching key, the Resource Server performs cryptographic verification. **Only when this check succeeds** is there evidence that the header/payload contents were not modified since being signed by a party holding a valid key.

Still, signature verification alone is not enough. You must know **which issuer owns the key** and **whether the token is meant for this API**.

### JWK Set and `kid`

The Authorization Server may publish public keys at a **JWKS endpoint**. Illustrative JWK Set example:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-rsa-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

The Resource Server uses `kid` from the header as a **hint to select a key** within **the preconfigured trusted key set**. `kid` alone does not prove issuance authority. If a client sends `kid=some-random-key`, the server must never automatically trust it or synthesize a key from that value.

Headers such as `jku` or `x5u` can propose URLs for keys or certificates in some JOSE formats. In a Resource Server API, **never automatically fetch arbitrary URLs specified by a token**. Doing so can lead to trusting attacker keys or SSRF attacks. Enforce issuer, key source, and algorithm policies from trusted configuration.

### Algorithm Enforcement

Even when the header states `"alg": "RS256"`, the application needs a policy accepting only algorithms agreed upon with the issuer.

Design flaws that have occurred in the JWT ecosystem include:

- Accidentally accepting **unsigned** JWTs, such as `alg=none`, where signed access tokens are required.
- **Algorithm confusion**: treating an RSA public key as an HMAC shared secret when a token switches `alg` from `RS256` to `HS256`.
- Letting the token choose algorithms and key sources outside trusted policy.
- Using weak keys or keys for the wrong purpose.

[RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725) requires applications to define the permitted algorithm set and verify that the executed algorithm matches both expectations and key usage. On a Resource Server requiring signed JWTs, reject any token failing the signing contract, even if its payload decodes to valid JSON.

**Never hand-roll JWS algorithms or trust the `alg` header to pick dangerous verification paths.** Use a maintained JOSE implementation and configure explicit allowlists for algorithms, keys, and issuers.

## 6. Claim Validation: A Valid Signature Can Still Be Rejected

Suppose signature verification succeeded. The Resource Server continues evaluating claims against the **access token contract**.

| Claim | Validation question | Risk if omitted |
|---|---|---|
| `iss` — issuer | Did the token come from the Authorization Server this API trusts? | Accepting tokens from another domain/tenant/AS |
| `aud` — audience | Is this token intended for this API? | Using a token meant for API A to call API B |
| `exp` — expiration | Has the token expired? | Accepting tokens beyond their allowed lifetime |
| `nbf` — not before | Has the token become valid yet? | Accepting tokens earlier than allowed |
| `iat` — issued at | Does it meet issuance-time policies if required by the app? | Unable to enforce token age or detect time anomalies |
| `typ` / token type | Is this an accepted access token rather than another token kind? | Confusing ID tokens, refresh tokens, or other JWTs |
| `scope` / `scp` | Which permissions were actually granted by the issuer? | Wrong authority mapping or over-privileged access |
| `sub` / `client_id` | Which principal/client is described by the issuer? | Confusing user and client; broken permission model |
| Custom claims | Do tenant, organization, or auth context match policy? | Crossing tenant boundaries or violating business rules |

Not all claims must appear in every access token format. **Required claims and validation logic depend on the profile, issuer, and API contract.** For example, in an RFC 9068 JWT access token, the right `typ` prevents token-type confusion, though reading `typ` alone is insufficient; the token must still be verified and type policies enforced.

### Valid Signature, Wrong Audience

An Authorization Server can issue two tokens signed with the same key set:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["inventory-api"],
  "scope": "inventory.read"
}
~~~

and:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

Both can have valid signatures. However, `orders-api` must reject the token intended solely for `inventory-api`. Checking only signature validity while skipping `aud` opens the door to **token substitution / cross-service token confusion**.

### `exp` Is Not Validated Simply by Reading JSON

A decoder tool may display:

~~~json
{
  "exp": 1700000000
}
~~~

Seeing this number does not mean it has been compared against the current time, adjusted for clock skew, or checked for validity. `exp` is represented as a JWT NumericDate, normally seconds since the Unix epoch. A debug tool may format it into human-readable time for operators; **the acceptance decision must reside in a trusted validator**, not a debug UI.

### An ID Token Does Not Become an Access Token Because Both Are JWTs

In OIDC, an **ID token** serves the OIDC Client (relying party). An **access token** serves the Resource Server. An ID token with `sub`, `iss`, `aud`, and a valid signature still cannot be arbitrarily used to call an API if its audience/purpose is not meant for that API.

Establish a token-type separation policy; for the JWT Access Token Profile, validate the appropriate profile and type. The `typ` label is just one of several signals to verify, never a substitute for signature and audience checks.

## 7. "Decode" Semantics in Spring Security Differ from Base64URL Decoding

Spring Security provides `org.springframework.security.oauth2.jwt.JwtDecoder`. The interface declares:

~~~java
Jwt decode(String token) throws JwtException;
~~~

The method is named `decode`, yet the decoder contract for a JWT Resource Server is to process the JWT per **verification and validation configuration**. For example, `NimbusJwtDecoder` uses JOSE to verify signatures and runs configured validators to evaluate claims.

In a Spring Boot system, proper configuration yields the high-level flow:

~~~text
HTTP request
    |
    v
Authorization: Bearer <compact-JWT>
    |
    v
BearerTokenAuthenticationFilter
    |
    v
JwtAuthenticationProvider
    |
    v
JwtDecoder (typically NimbusJwtDecoder)
    |
    +-- validate token structure
    +-- select matching algorithm/key from trusted source
    +-- verify signature
    +-- run Jwt validators (issuer, timestamps, audience...)
    |
    v
Authenticated JwtAuthenticationToken
    |
    v
SecurityContext
    |
    v
Authorization rules / method security
    |
    v
Controller / service
~~~

If verification fails, the request normally fails to produce an authenticated JWT principal and takes the authentication failure path.

### Properly Configuring a JWT Resource Server

For a Spring Boot application using Servlet/Spring MVC, declare the appropriate starters:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

- `issuer-uri` specifies the trusted issuer and supports metadata/JWKS discovery per Spring Security/Authorization Server mechanics.
- `audiences` requires the JWT to target this Resource Server. This property is supported in modern Spring Boot versions; if using an older version without it, configure a custom audience validator.
- Never accept an issuer or JWKS URI proposed by the request or JWT header.
- If the AS does not support metadata discovery or requires explicit JWKS configuration, use a trusted `jwk-set-uri` alongside issuer and required validators.

Example filter chain:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

In this configuration, **authentication runs before authorization**: the API never reads `scope` from an unverified token to make access decisions. For standard scope claims supported by Spring, `scope=orders.read` normally becomes authority `SCOPE_orders.read` after JWT authentication.

For apps with session/cookie or CSRF considerations, adjust HTTP policies to match your specific architecture; this snippet focuses solely on the JWT processing path.

### Reading Claims from the Authenticated Principal

A controller can receive the `Jwt` already authenticated by the Resource Server:

~~~java
package com.example.orders.api;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/me")
    public Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString()
        );
    }
}
~~~

This example assumes the route is protected, the JWT is valid, and `issuer` is required by policy. Claims retrieved from a `Jwt` constructed by the Resource Server after authentication are trustworthy, unlike data manually decoded from an unverified string.

Even so, **an authenticated principal does not replace data-level authorization checks**. Even with `sub=alice` and `SCOPE_orders.read`, the service must still check whether Alice is allowed to read a specific order.

### Invoking `JwtDecoder` Directly in Java

When you genuinely need to validate a token at a clearly designed boundary (for example, processing a message carrying an access token under an internal contract), use a `JwtDecoder` configured with the proper issuer/keys/validators:

~~~java
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;

public final class JwtValidationExample {

    private final JwtDecoder jwtDecoder;

    public JwtValidationExample(JwtDecoder jwtDecoder) {
        this.jwtDecoder = jwtDecoder;
    }

    public String validatedSubject(String untrustedToken) {
        try {
            Jwt verifiedAndValidated = jwtDecoder.decode(untrustedToken);
            return verifiedAndValidated.getSubject();
        } catch (JwtException ex) {
            throw new IllegalArgumentException(
                "JWT failed configured verification/validation", ex);
        }
    }
}
~~~

The variable name `verifiedAndValidated` in this example comes with a condition: **the decoder must be properly configured**. If you replace `JwtDecoder` with a custom implementation that only parses payloads, its result carries none of that trust. In normal HTTP controllers, let the Spring Security filter chain authenticate requests and retrieve the principal from `SecurityContext` rather than manually re-decoding tokens.

## 8. A Classic Security Bug: Trusting Decoded Payloads in a Custom Filter

Suppose an application writes a filter like this:

~~~java
// WRONG: pseudocode solely to highlight the design flaw
String token = resolveBearerToken(request);
String payloadJson = base64UrlDecode(token.split("\\.")[1]);
String role = jsonObject(payloadJson).getString("role");

if ("ADMIN".equals(role)) {
    allowAdminRequest();
}
~~~

This code is broken because:

1. A client can craft JSON containing `role=ADMIN`.
2. A client can Base64URL-encode that JSON without knowing any signing key.
3. The filter uses unverified data as the basis for authorization.
4. A missing or invalid signature does not stop this path if the filter skips verification.

A similar flawed pattern:

~~~java
// WRONG: parsing an untrusted claim and placing it into SecurityContext
String userId = parseJwtWithoutVerification(token).get("sub");
Authentication authentication =
    createTrustedAuthentication(userId);
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

In Spring Security's architecture, never construct a trusted `Authentication` merely from parsing a token. Let the configured `JwtAuthenticationProvider` and `JwtDecoder` run verification and validation first, then map authorities from trusted claims.

### Opposite Mistake: Valid Signature While Skipping Audience Validation

A system may verify JWT signatures with the organization's public key yet omit checking `aud`, causing it to accept tokens issued for a different API.

Example:

~~~text
JWT: iss=https://idp.example.com
     aud=reporting-api
     scope=reports.read
     signature=valid

orders-api:
     signature=valid
     issuer=trusted
     audience NOT validated     <-- missing check
~~~

You cannot conclude this token is meant for `orders-api`. **Signature verification and intended-purpose validation are both separate required conditions.**

## 9. Do Not Confuse Cryptographic Verification Failures with Authorization Failures

When a client receives `401` or `403`, decoding the token can suggest clues without settling the root cause.

| Symptom | What does decoding show? | What to check on the Resource Server |
|---|---|---|
| Missing token or malformed header | No token to read, or malformed string | Bearer token resolver, filter chain, endpoint auth rules |
| Payload looks right, yet signature is forged | Header/payload still decode fine | Permitted algorithms, signature, trusted public key |
| Header contains a new `kid` | `kid` renders normally | JWKS cache, key rotation, matching key from issuer |
| `iss` looks right, yet token is rejected | `iss` text matches expectation | Post-verification issuer comparison, metadata, and issuer config |
| `aud` omits current API | Claim decodes cleanly, yet mismatches | Audience validator must reject the token |
| `exp` is past or `nbf` is in the future | NumericDates still decode cleanly | Claim validators, clock sync, and clock skew |
| Valid JWT token, yet missing scope | `scope` only contains `orders.read` | Authority mapping, `hasAuthority`, endpoint policy |
| Token is not a JWS JWT | Cannot split/parse three parts cleanly | Distinguish opaque token, JWE, invalid input |
| Valid token, yet accessing wrong tenant | Claim has a valid `tenant_id` | Tenant isolation and per-resource permissions |
| Issuer keys could not be loaded | Decoding itself still works | JWKS endpoint health, TLS, DNS, timeouts, and configuration |

Typical error distinction:

- **`401 Unauthorized`**: no valid authentication; malformed/expired token, failed signature or validator.
- **`403 Forbidden`**: authentication succeeded, yet insufficient scope/authority or resource policy denies access.
- **AS/JWKS outage**: can surface differently depending on Spring Security version, config, and exception handling; inspect server telemetry for root cause.

A common debugging mistake is seeing `scope=orders.write` in a token while the request still returns `403` and assuming Spring Security checked wrongly. Verify whether the token was actually authenticated, how the scope claim is mapped, and whether the authorization rule matches the HTTP path and method. Specifically, `ROLE_ADMIN` and `SCOPE_orders.write` are not the same authority.

## 10. A Safe and Effective JWT Debugging Workflow

When an API rejects a request carrying an access token, follow this workflow:

### Step 1 — Identify the Token Format First

Check what token format the Authorization Server issues:

- **Compact JWS (signed JWT)** typically has three dot-separated segments.
- **Compact JWE (encrypted JWT)** typically has five segments.
- **Opaque access token** may be a string that cannot be decoded into JSON claims like a JWT.

The segment count and "looking like a JWT" are only formatting cues; **they do not prove the token is authentic or safe**.

### Step 2 — Decode Header/Payload to Form Hypotheses

If the token is a compact JWS and operational policy allows, decode **locally** to observe:

- Which `alg` and `kid` the token declares.
- Whether `iss` and `aud` *look like* expected values.
- Whether `exp` or `nbf` suggest a timing failure.
- Which permissions appear in `scope`/`scp`.
- Whether `typ` suggests an unexpected token type.

Mark these observations as **unverified**. A header/payload read from an untrusted source may also contain wrong types, huge JSON, or malformed structures. Bound sizes and field counts when writing practical inspection tools.

### Step 3 — Inspect API-Side Trust Configuration

Check the Resource Server configuration:

- Issuer URI and expected audience.
- Trusted JWKS URI / metadata endpoint.
- Permitted signing algorithms.
- Time validation and clock skew.
- Any custom `OAuth2TokenValidator` or custom decoder added.
- `SecurityFilterChain` authorization rules, method security, and authority mapping.

Never use unverified claims to choose the issuer or JWKS endpoint for the current request, unless a secure multi-tenant design explicitly restricts allowed issuers.

### Step 4 — Trace the Real Verification Outcome

Inspect what happens at the Resource Server's authentication boundary:

~~~text
Unverified token
      |
      +--> signature/algorithm/key valid?
      |        |
      |        +-- no  -> reject
      |
      +--> issuer/audience/time/type valid?
      |        |
      |        +-- no  -> reject
      |
      +--> authenticated principal + authorities
               |
               +--> endpoint/resource policy allows?
                        |
                        +-- no  -> forbidden
                        +-- yes -> controller/service
~~~

Being able to read JSON **must never skip** any of the decision gates above.

### Step 5 — Log Only Minimal Information

Log non-sensitive operational details per policy:

~~~text
event=jwt_authentication_failed
path=/api/orders
reason=audience_invalid
expectedAudience=orders-api
traceId=a5c8...
token=[REDACTED]
~~~

As needed, also log error codes or non-secret configuration identifiers. **Never log raw JWTs, payloads containing PII, secrets, access tokens, refresh tokens, or token signatures.** Suppress exception messages containing raw tokens if a library embeds the token in the error text.

If real tokens must be handled during an investigation, follow organization-approved secure channels and procedures; prefer issuing test tokens with minimal scopes and audience.

## 11. Troubleshooting Signature and JWKS Errors: Reading `kid` Is Only the Starting Point

A common example during Authorization Server key rotation:

1. New tokens carry header `kid=key-2026-02`.
2. The Resource Server caches a JWKS containing only `key-2026-01`.
3. A decode tool still displays the header and payload completely normally.
4. The Resource Server cannot find a matching key to verify with, causing authentication failures until the key set refreshes properly.

The right conclusion is neither "the token must be invalid" nor "just skip signature checking." Inspect **JWKS rotation/refresh**, endpoint availability, caching, and allowed algorithms.

When the AS publishes multiple keys, `kid` helps locate a key yet **is not proof on its own**. The public key must belong to the right issuer and trusted source. When encountering an unknown key, the Resource Server must reject the token until a valid key is obtained via trusted mechanisms—never trust token contents blindly.

## 12. JWE and Opaque Tokens: Not Every Token Has a Directly Readable Payload

### JWE Can Contain Encrypted Claims

A JWT encrypted with JWE Compact Serialization typically has five segments:

~~~text
protected-header
.
encrypted-key
.
initialization-vector
.
ciphertext
.
authentication-tag
~~~

You cannot simply Base64URL-decode an arbitrary segment and see plaintext JSON claims. Reading JWE contents requires **proper decryption with the matching key**, and depending on token structure, handling nested JWT/JWS and other security checks.

A successfully decrypted JWE **still does not automatically grant access**: the Resource Server must still validate issuer, audience, lifetime, token type, and appropriate integrity/authenticity checks. Never equate "decryptable" with "authorized for use."

### Opaque Access Tokens Have No JWT Contract

An opaque token is treated by the Resource Server as a reference string. You cannot read `scope`, `sub`, or `exp` simply by "decoding." In Spring Security Resource Server, the corresponding mechanism is usually **introspection**:

~~~text
Bearer opaque token
       |
       v
OpaqueTokenIntrospector
       |
       v
Authorization Server introspection endpoint
       |
       v
active + attributes
       |
       v
authentication + authorization policy
~~~

Never force an opaque token through a JWT parser. Conversely, a JWT-formatted access token **can still be introspected** if the Authorization Server and Resource Server policy use introspection to check active status.

Key distinction: **token format** (JWS/JWE/opaque) and **verification method** (local/introspection) are two design decisions that must be aligned with the Authorization Server.

## 13. Be Careful with Tokens That Are Valid Yet Unusable for an API

Even when Spring Security has constructed an `Authentication` successfully, a token may still fail requirements for a specific action.

API example:

~~~text
GET    /api/orders/1001    requires SCOPE_orders.read
POST   /api/orders         requires SCOPE_orders.write
DELETE /api/orders/1001    requires SCOPE_orders.delete
~~~

A properly signed, unexpired token with `aud=orders-api` and `scope=orders.read` may call `GET`, yet must be denied on `POST` or `DELETE`.

Another requirement is **data ownership**: principal `alice` may read orders belonging to Alice, yet must not read orders belonging to Bob even though the token has the read-orders scope.

This illustrates three distinct gates:

~~~text
Is the token payload readable?
    |
    v
Is the token trustworthy and currently valid?
    |
    v
Does the request have endpoint permission?
    |
    v
Does the user/client have permission on the specific record?
    |
    v
Execute operation
~~~

Only the second gate onward provides security; the "readable" gate merely assists diagnostics.

## 14. Testing: A Mock JWT Test Does Not Verify Real Signatures

In Spring Security Test, applications can use utilities like `SecurityMockMvcRequestPostProcessors.jwt()` to inject a simulated JWT principal into MVC tests. This is very useful for testing **authorization rules**, principal mapping, or controller behavior in an authenticated context.

However, understand the boundary: such tests normally **do not pass a real JWS through JWKS signature verification**. Therefore, a passing test using a mock JWT does not prove the Resource Server has configured issuer, algorithm, audience, and signature verification properly.

Example of the behavioral layers to test:

~~~text
Authorization test:
- Authenticated Jwt principal has SCOPE_orders.read
- GET /api/orders returns expected result
=> Verifies access rules

Verification/integration test:
- JWS signed with real test issuer key
- RS uses matching public key + issuer + audience
- Accepts valid token, rejects bad signature/wrong issuer/wrong aud/expired
=> Verifies token validation pipeline
~~~

These two test categories serve different goals. Never use mock claims as proof that cryptographic verification is working.

## 15. Critical Misconceptions

**"Once the payload is Base64-decoded, the JWT is verified."** False. Decoding uses no key and verifies no integrity.

**"A JWT with `alg=RS256` means it was signed with RS256."** False. That is an untrusted header declaration; only verification with the right algorithm policy and key confirms it.

**"`kid` tells you which key to trust."** Incomplete. `kid` is a hint for picking a key inside a preconfigured trusted key set; it does not create trust itself.

**"If the signature is valid, the API must accept the token."** False. You must also check `iss`, `aud`, timestamps, token type, and application policies.

**"`sub=admin` means the request came from an admin."** False. Prior to verification it is untrusted data; even after verification it describes a principal/token per the issuer, not automatically proof that a human admin directly submitted the request.

**"Pasting a JWT into a web decoder has no risk because payloads are already public."** False. A token is a bearer credential; anyone holding a valid token can use it within its granted permissions. Sending the token string to an external system risks exposing the entire credential.

**"Just checking `exp` in JSON is enough."** False. Never rely on timestamps self-declared by an unverified token.

**"Spring Security `JwtDecoder` is just like `Base64.getUrlDecoder()`."** False. A properly configured `JwtDecoder` handles JWT verification and runs validators.

**"Every JWT has three readable parts."** False. Compact JWS typically has three parts; compact JWE typically has five parts; opaque tokens have no public JWT structure.

## 16. Thought Exercises

### Question 1: Two Tokens Share a Payload, One Has a Modified Claim

A real access token has `scope=orders.read`. Someone edits the payload to `scope=orders.write` while keeping the original signature segment. Both show up cleanly in a decode tool. Is the second token trustworthy?

**Answer:** No. Changing the payload changes the signed input. Without re-signing using a valid issuer key, verification must fail. That decoding still succeeds is irrelevant to signature validity.

### Question 2: Valid Signature, Yet `aud=inventory-api`

A token is signed by the same issuer and `exp` is unexpired, yet the called endpoint belongs to `orders-api`. Can the token be accepted?

**Answer:** No, if the token's audience does not include `orders-api`. The Resource Server must confirm the token was issued for its own resource.

### Question 3: `JwtDecoder.decode()` Returns a `Jwt`

Can claims retrieved from this `Jwt` be trusted?

**Answer:** They can be used per policy **when the decoder and validators are properly configured** with the right algorithms, issuer, keys, and required claims. If the decoder is replaced by a non-verifying implementation or omits audience checks, the result is insufficient for API trust.

### Question 4: A Spring MVC Test Uses `jwt()` and Returns `200`

Does the test prove production JWT signatures are verified properly?

**Answer:** No. Mock JWTs in tests simulate principal/authorities and bypass real JWT verification. Dedicated integration tests with a decoder and appropriate test keys are required.

### Question 5: A Debug Tool Shows Valid `iss` and `exp`, Yet the Server Returns `401`

Should you change the server to "read claims directly" instead of using the decoder?

**Answer:** No. Investigate the real verification step: algorithm, signature, JWKS, audience, issuer, timestamps, token type, and Spring Security configuration. Never replace verification with manual parsing.

## 17. References

- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): token format, claims, and NumericDate.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): compact serialization and signatures/MACs.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): tokens with encrypted content.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS key formats.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518): JOSE algorithms.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm verification, preventing token-type confusion, issuer/audience validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): standard profile structure and validation for JWT access tokens.
- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): configuring JWT, issuer, JWKS, validators, and authorities.
- [Spring Security — `JwtDecoder` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html): decoder contract.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): verification via introspection.

In real implementations, always remember the difference between **"reading a claim self-declared by a token"** and **"receiving a claim after the Resource Server has verified the token against its own trust configuration"**. Separating these two states cleanly is a foundational requirement for securing any OAuth 2.0/OIDC API.
