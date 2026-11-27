# Do Not Infer Trust Solely from Token Shape or Dot Count

## 1. The Problem in a Resource Server with Multiple Authentication Mechanisms

An API using **Spring Security OAuth 2.0 / OIDC Resource Server** may receive JWT access tokens, opaque access tokens, or tokens issued by different Authorization Servers. Some applications also simultaneously support browser sessions, HTTP Basic, service-to-service tokens, or token profiles for other purposes.

When developers want to choose how to authenticate, a tempting idea quickly comes to mind:

```java
// WRONG: string structure does not prove issuer or trustworthiness.
boolean looksLikeJwt = token.split("\\.").length == 3;

if (looksLikeJwt) {
    return jwtAuthenticationManager.authenticate(authentication);
}
return introspectionAuthenticationManager.authenticate(authentication);
```

The hidden assumptions here are:

- Having **two dots** means it is a JWT that deserves the JWT branch.
- Not having two dots means it is an opaque token to introspect.
- Just looking at the string shape tells you which authentication policy to apply.
- If trying JWT fails, simply trying introspection is enough.

**All four assumptions are unsafe.** Two dots can appear in a random string. A three-part compact JWS may contain a forged signature, a payload that is not JWT claims, or an **ID Token** rather than an OAuth access token. An opaque access token can still contain dots. A JWT can be encrypted as a compact JWE with **five parts**, not three. And even a token that truly is a JWT must still have its **signature, algorithm, issuer, audience, expiration, token type, and authorization policy** verified.

This lesson belongs to the **Multiple Authentication Mechanisms** chapter of the **Spring Security OAuth 2.0 OIDC Resource Server** module. The goal is to design **trust boundaries** when supporting multiple mechanisms/token profiles, without confusing *format detection* with *authentication* or *authorization*.

Running example throughout:

- Resource Server: `orders-api`.
- Trusted issuer: `https://auth.example.test/realms/orders`.
- JWT access-token audience: `orders-api`.
- JWT-only endpoint: `/api/jwt/orders/**`.
- Introspection-only endpoint: `/api/opaque/orders/**`.
- Read order scope: `orders:read`.
- Subjects: `alice-123` and `bob-456`.
- Opaque introspection endpoint: `https://auth.example.test/oauth2/introspect`.

Domain names, tokens, and credentials are illustrative. The code targets **Spring Boot 3.x, Spring Security 6.x, Java 17+ Servlet/MVC**, with differences for **WebFlux** noted afterward.

> **Invariant principle:** **Token shape may help route parsing, but it grants zero trust.** Trust is established only after the token is verified against a **predefined policy** and bound to the right issuer/resource/token profile.

---

## 2. Distinguish Five Concepts Before Writing Code

| Concept | Question | Can it be concluded from dots? |
|---|---|---|
| **Token format** | Does the string *resemble* compact JWS, JWE, or a reference token? | Only a rough syntactic guess. |
| **Token parsing** | Does the string have header/payload/base64url/JSON structure per the serializer? | No; it must be parsed properly. |
| **Token authentication** | Was the token issued by a trusted source, and are signature/`active`/issuer/time valid? | **No.** |
| **Token applicability** | Is this actually an access token allowed for `orders-api`? | **No.** |
| **Authorization** | Does the caller have the scope, roles, tenant, and permissions for this object? | **No.** |

A token can be parsed successfully yet fail authentication. A token can authenticate validly yet be an **ID Token** for a frontend app and thus inappropriate for the Resource Server. An access token can be valid for `orders-api` yet lack permission to read Bob's order.

### 2.1. Three Terms to Use Accurately

- **Syntax/format recognition:** observing dot positions, JSON-like headers, string length, or prefixes.
- **Verification/validation:** using trusted public keys/JWKS or a trusted introspection endpoint to decide whether a token is accepted by validators.
- **Access control:** after authentication, checking scopes/authorities, tenant, owner, ACL, delegated permissions, and business rules.

**Never turn a syntax recognition result into `Authentication.isAuthenticated() == true`.** Access policy must rely on the principal produced by the verification mechanism, not unverified data.

### 2.2. Safe and Unsafe Branch Diagram

```mermaid
flowchart TD
    A["Authorization: Bearer <token>"] --> B{"Registered API/route/issuer policy?"}
    B -->|JWT-only| C["JwtDecoder with trusted keys/alg/issuer/aud"]
    B -->|Introspection-only| D["OpaqueTokenIntrospector to trusted AS"]
    B -->|No contract| E["Deny: do not choose based on dot count"]
    C --> F{"Signature, claims, profile valid?"}
    D --> G{"active + metadata + resource binding valid?"}
    F -->|No| H["Authentication failure"]
    G -->|No| H
    F -->|Yes| I["Authenticated principal per token policy"]
    G -->|Yes| I
    I --> J{"Sufficient scope and object permission?"}
    J -->|No| K["403/404 per policy"]
    J -->|Yes| L["Allow business processing"]
```

Crucially, **policy is determined before trusting the token**. There is no branch for "if JWT verification fails, automatically switch to an easier mode" or "if opaque introspection fails, trust the JWT payload directly".

---

## 3. What Do Two Dots Say About a JWS?

A JWS in **compact serialization** has the general structure:

```text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
```

Three components separated by **two dots**.

Illustrative example, not a valid signature:

```text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0.eyJzdWIiOiJhbGljZS0xMjMifQ.fake-signature
```

In this example:

- The first segment *might* decode to a JWS protected header.
- The second segment *might* decode to a payload.
- The third segment is just an illustrative string, **not cryptographic proof**.
- The header may claim `alg=RS256`, yet there is **zero proof** the signature was actually created by a trusted issuer.

Counting dots alone does not prove:

1. The segments are valid Base64URL syntax.
2. The header specifies an allowed `alg`.
3. The signature is valid against a **trusted key**.
4. The payload content is a JWT Claims Set.
5. Payload `iss` belongs to the issuer allowlist.
6. `aud` matches the API.
7. `exp` and `nbf` are still valid.
8. The JWT is an **OAuth 2.0 access token** rather than another kind of assertion.
9. The token has not been revoked or restricted by AS policy.
10. The caller has sufficient permissions for the requested resource.

**Counting dots is merely string manipulation, not an authentication algorithm.**

### 3.1. Not Every JWS Is an Access Token

A JWS can sign:

- A JWT claims set.
- Other data that is not JWT claims.
- An assertion meant for client authentication.
- A token for another purpose, such as an ID Token/OIDC.
- An application document or message wrapped in JWS.

Therefore, "three-part compact JWS" does not mean "valid JWT access token for the Resource Server".

A JWT only carries meaning when issued under a specific token profile. RFC 9068 defines an OAuth 2.0 **JWT Access Token** profile, but not every three-part JWT on the Internet follows that profile.

### 3.2. A Three-Part JWT Can Be a Forged Token

An attacker crafts:

```json
{
  "alg": "RS256",
  "kid": "some-key"
}
```

and payload:

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "sub": "admin",
  "aud": ["orders-api"],
  "scope": "orders:admin",
  "exp": 1890003600
}
```

Then the attacker puts arbitrary bytes in the signature segment. The resulting string has two dots, a plausible-looking header/payload, and an admin scope, yet **fails JWS signature verification** when the Resource Server behaves properly.

Code like the following is a critical bug:

```java
// DO NOT USE: parsing unverified claims to grant privileges.
Map<String, Object> claims = parseBase64UrlJwtPayload(rawToken);

Authentication auth = new UsernamePasswordAuthenticationToken(
    claims.get("sub"),
    null,
    List.of(new SimpleGrantedAuthority("ROLE_ADMIN"))
);
SecurityContextHolder.getContext().setAuthentication(auth);
```

A client-crafted JSON payload is never proof for granting authorities.

### 3.3. `alg=none` Does Not Make a Token a "Valid JWT"

JWS includes the concept of an **Unsecured JWT** in special standard contexts, with a header containing `alg="none"` and an empty signature segment:

```text
header.payload.
```

It still has **two dots**. Yet a normal Bearer API must never accept a token without cryptographic protection as a login credential. Never write code saying "if there are two dots, skip verify as JWT" or "empty signature is fine if the header says none".

The decoder mechanism must enforce an **algorithm allowlist**; never let an attacker-sent JWT header decide the verification level.

---

## 4. Four Dots: Compact JWE Is Not Automatically More Trusted Than JWT

JWE compact serialization has five parts:

```text
protected-header.encrypted-key.iv.ciphertext.authentication-tag
```

Five parts separated by **four dots**.

JWE provides **content confidentiality** using encryption and integrity protection in the JOSE model. However, a string looking like a JWE does not prove:

- It actually decrypts with a key trusted by the API.
- The issuer is an authorized Authorization Server.
- Claims are protected according to the API's token profile.
- The token has the right audience, expiry, and scopes.
- The party that encrypted the token is also authorized to issue access tokens.

A JWT can be protected by JWS or JWE, including **nested JWTs**. A compact JWE-formatted JWT cannot be handled like a three-part JWS simply by switching branches based on dot count.

### 4.1. Does Spring Security Resource Server Automatically Decrypt JWE?

The standard JWT Resource Server configuration path with `NimbusJwtDecoder` focuses on **verifying JWS-signed JWTs**. You should not assume default `issuer-uri`/`jwk-set-uri` configuration can **decrypt JWEs** or verify an entire nested-JWT profile.

If the system genuinely uses encrypted JWTs/JWE:

1. Establish clear contracts for issuer, encryption key management, and decryption algorithms.
2. Verify JOSE headers, signing/encryption layers, and token claims per profile.
3. Never use dot count to decide to "upgrade trust".
4. If the token is treated as **opaque to the Resource Server**, you can use introspection **if the AS has a supporting contract**.
5. Never put private decryption keys in code or logs; access control and rotation must be designed separately.

**A five-part JWE is not inherently safer than a three-part JWS** in the role of access token. Encryption and authentication/authorization answer different questions.

### 4.2. Neither "Three Parts" Nor "Five Parts" Is Enough

| Appearance | Valid conclusion | Must not be inferred |
|---|---|---|
| Two dots | Looks like compact JWS shape. | Valid JWT access token. |
| Four dots | Looks like compact JWE shape. | JWE successfully decrypted and issued by trusted issuer. |
| Zero dots | Does not look like three-part compact JWS. | Active opaque token or from an allowed issuer. |
| Ten dots | Just an unusual string. | Token definitely not used by an issuer as an opaque reference. |
| Prefix `eyJ` | Likely a Base64URL JSON segment starting with `{"`. | Valid signature or trusted issuer. |

Dot count is useful only as an **untrusted syntactic observation**; it cannot replace a trust policy.

---

## 5. Opaque Tokens Can Contain Dots

In OAuth 2.0, an **opaque token** is a token whose contents the Resource Server **cannot or should not reliably interpret itself**. It is often a random string/reference token looked up with the Authorization Server via RFC 7662 Token Introspection or an agreed contract.

Some opaque strings may look like:

```text
xH8m7N2aQfKL0sT1
abc.def.ghi
ref.2026.q4.54bad1
a.b.c.d.e
```

The dots in these examples **do not turn the token into a JWT/JWS/JWE**. An issuer may choose an alphabet/encoding containing `.`; representation does not create authentication data.

Bearer token transport also permits a range of characters, including dots, under RFC 6750 syntax. Thus, **counting dots is not a reliable way to tell JWTs apart from opaque tokens**.

### 5.1. Introspection Can Also Apply to JWTs

RFC 7662 does not restrict introspection to opaque strings "without dots". An Authorization Server can support introspection for JWT access tokens or many other token types.

What decides is **the contract between Authorization Server and Resource Server**:

- Does the introspection endpoint have authority to check that token type?
- Is the requester authorized to introspect tokens for this resource?
- How is `active` defined with respect to token status/revocation/issuer?
- Does the endpoint return `aud`, `iss`, `scope`, or other claims the API needs?
- Is it guaranteed that only access tokens intended for `orders-api` are considered usable?

If every access token for an API is supported for introspection by the AS under **a strict contract**, the Resource Server can introspect all of them **regardless of how many dots the string has**.

### 5.2. `active=true` Does Not Grant Every Permission

Example:

```json
{
  "active": true,
  "iss": "https://auth.example.test/realms/orders",
  "aud": ["payments-api"],
  "scope": "orders:read",
  "sub": "alice-123"
}
```

Even though introspection reports active, this token **is not intended for `orders-api`** if the audience contract requires `orders-api`. Do not accept it simply because the token "didn't look like a JWT", was treated as opaque, and the AS returned active.

If the introspection response omits `aud`/`iss`, the API must have **resource binding** enforced by the AS based on the introspection requester's credentials or an equivalent contract; never drop this requirement.

---

## 6. JWT, ID Token, Access Token, and Token Confusion

### 6.1. An OIDC ID Token Is Not an API Access Token

An OIDC ID Token can be a **validly signed three-part JWT** issued by **the same issuer** as the access token. Its purpose is to give user authentication information to an **OIDC client**, not implicitly to serve as a credential at an OAuth 2.0 Resource Server.

For example, an ID Token has:

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "sub": "alice-123",
  "aud": ["web-portal"],
  "exp": 1890003600,
  "nonce": "random-login-nonce"
}
```

Whereas the expected API access token has:

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "exp": 1890003600
}
```

Even when both tokens have valid signatures, an ID Token with audience `web-portal` must not be accepted at `orders-api`. A valid signature proves an issuer created the assertion; **it does not permit repurposing the assertion**.

A program that only calls `jwtDecoder.decode(token)` and forgets audience/token-type validation risks **cross-JWT confusion** or **token substitution**.

### 6.2. `typ` and Explicit Token Profiles

RFC 9068 defines a JWT access-token profile using a header type such as `at+jwt`, along with other requirements. For example:

```json
{
  "alg": "RS256",
  "kid": "signing-key-2026-11",
  "typ": "at+jwt"
}
```

Do not use an unverified `typ` as standalone proof. It is one **condition to verify per configured contract**, combined with signature, issuer, audience, and claims. Some issuers use other profiles or `typ="JWT"`; the Resource Server must align with and test the actual profile rather than inferring the whole contract from the header.

When an application accepts multiple JWT types, RFC 8725 recommends **mutually exclusive validation rules** for each type: an ID Token and an access token should never both pass the same validator set merely because both are JWTs.

### 6.3. Unverified JWT `iss` Can Only Be a Hint Inside an Allowlist

Some multi-issuer systems read `iss` from the payload to **select a decoder**. That is acceptable **only as a lookup step within a preconfigured set of trusted issuers**, never as proof that the issuer is trusted.

Wrong:

```java
// DO NOT USE: attacker supplies their own iss and JWKS endpoint.
String issuer = decodeWithoutVerifying(token).getIssuer();
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
return decoder.decode(token);
```

Right in principle:

```text
unverified iss = hint
    ↓
find issuer in static/trusted allowlist?
    ├─ no  -> reject
    └─ yes -> select pre-approved decoder/key source
                   ↓
              verify signature and iss == expected issuer
                   ↓
              verify aud, exp, typ/profile and authorities
```

Never feed an arbitrary issuer URL into discovery/JWKS fetching; beyond authentication bypass, it creates **SSRF** and outbound network abuse risks.

---

## 7. The "Downgrade" Risk: Failing One Mechanism and Trying Another

A very dangerous anti-pattern in systems supporting both JWT and opaque tokens:

```java
// DO NOT USE: "rescuing" a failed JWT with another mechanism.
try {
    return validateAsJwt(rawToken);
} catch (Exception ignored) {
    return introspectAsOpaque(rawToken);
}
```

The problem is not merely "having an extra way to check tokens". It can **blur security boundaries**:

- A JWT rejected for wrong issuer/audience/type at the decoder might get `active=true` from an introspection endpoint under a different standard.
- A JWT with an invalid signature might have a raw string that happens to be an active reference token in another AS.
- A token revoked in one source might be accepted by another due to caching or inconsistent policy.
- One branch enforces audience/tenant, while the other only checks `active`.
- Error responses/token downgrades become a probing tool to discover which token types are accepted.
- Every request might trigger two upstream calls, adding load/latency and complicating auditing.

**A failing mechanism must never automatically downgrade to a less restrictive mechanism.** If the same API **intentionally** supports two access token types, that must be a bounded, reviewed policy ensuring every path meets the **same minimum verification bar** for that resource.

### 7.1. When Is Retrying a Mechanism Valid?

Short **network retries** for transient errors against the same introspection endpoint are an availability concern, distinct from "trying a different authentication provider". Distinguish:

| Action | Acceptable? | Conditions |
|---|---|---|
| Retry HTTPS introspection after transient timeout | Possibly. | Bounded retries/backoff; fail closed if no result. |
| Refresh JWKS from **trusted JWKS URL** on unknown `kid` | Possibly. | Stick to key-source allowlist; never take URL from token header. |
| JWT wrong audience → call opaque introspection to find an accepting path | **Should not**. | Avoids bypassing resource binding. |
| JWT invalid signature → parse payload and build principal | **No**. | No proof of issuance. |
| Introspection returns `active=false` → decode raw token to allow through | **Should not**. | Avoids defeating revocation/provider semantics. |
| Use one introspection endpoint contracted by AS for both JWT and reference tokens | Possibly. | Single shared validation policy, resource binding, and strict schema. |
| Split JWT-only/opaque-only by API route | Possibly. | No route aliases leading to privilege escalation or bypass. |

### 7.2. Do Not Catch `Exception` Too Broadly

A custom resolver might write:

```java
try {
    return jwtDecoder.decode(token);
} catch (Exception exception) {
    return null;  // continue trying Basic/session/opaque
}
```

This masks:

- Genuinely invalid JWTs.
- JWKS endpoint timeouts.
- Parsing/serialization bugs.
- Misconfigured trusted keys.
- Dependency outages.

Do not conflate token errors with infrastructure errors, and never return `null` as a signal to "let another mechanism try" unless the contract explicitly permits it. Even if external error mapping returns 401 or 5xx, an unverified request **must not reach business logic**.

---

## 8. Which Sources Are More Trustworthy for Mechanism Selection?

A safe design should answer **before looking at the token**: which credential scheme does this endpoint accept, which issuer issues it, for which audience/resource, and which scopes are required?

### 8.1. Explicitly Published Route/Path

Example:

```text
/api/jwt/orders/**     -> signed JWT access tokens only, trusted issuer A
/api/opaque/orders/**  -> introspection only at AS B
```

Clients can choose the URL, but **each URL is a resource with a fixed policy**. There must be no secret route to the same data with weaker authentication. If two endpoints access the same set of orders, they must enforce equivalent authorization/business checks and never become a bypass for unauthorized access.

### 8.2. Registry-Approved Host/Tenant

Example:

```text
acme.api.example.test -> tenant Acme -> allowlisted issuer
beta.api.example.test -> tenant Beta -> allowlisted issuer
```

Host is still **client-selected input**, so it is not proof that the caller belongs to that tenant. Yet it can select a **registered issuer policy**; the token must then verify the right issuer and tenant. `Forwarded` and `X-Forwarded-Host` headers may only be used when the gateway strips/overwrites untrusted client headers.

Never dynamically build issuer/JWKS URLs by interpolating an untrusted host into a string like `https://{host}/.well-known/jwks.json` and trusting arbitrary hosts.

### 8.3. API Audience/Resource Contract

An API may accept only tokens intended for `orders-api`. This condition must be enforced across **every mechanism**:

- JWT: check `aud` in verified claims.
- Opaque: check `aud` in trusted introspection metadata, or rely on AS policy binding tokens to the introspection requester per contract.
- Service credentials: have distinct client-specific privileges and resource binding.
- User tokens: have clear subject and resource-owner semantics.

If one mechanism requires only `active=true` while another requires `iss`/`aud`/`typ`, the API risks creating an **assurance gap** between paths.

### 8.4. An Issuer Allowlist for Multiple JWT Issuers

A system may use `JwtIssuerAuthenticationManagerResolver` or an equivalent resolver to select an `AuthenticationManager` from an issuer hint **inside a trusted allowlist**. Mandatory conditions:

1. The issuer is pre-registered/onboarded.
2. The key source comes from trusted metadata/registry, never from the attacker.
3. The token is verified against the exact selected issuer.
4. Audience and token type/profile match the API.
5. Subject/tenant namespaces are distinct.
6. The resolver rejects any issuer outside the catalog.

Never conclude that "a JWT whose `iss` matches the tenant name must be valid"; verification and policy must still execute.

---

## 9. Safe Pattern A: Splitting `SecurityFilterChain` for Two API Areas

With Spring Security Servlet, an easy-to-control approach is **two filter chains** using distinct matchers. No dot-count token classification needed.

### 9.1. Dependencies

If the project uses Spring Boot parent/BOM for version management:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
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
</dependencies>
```

`spring-boot-starter-oauth2-resource-server` provides Resource Server support; JWT signature validation needs JOSE libraries managed by the BOM in the appropriate dependency graph.

### 9.2. Configuring Issuer/JWKS and Introspection

`application.yml`:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.test/realms/orders
          jwk-set-uri: https://auth.example.test/realms/orders/jwks
          audiences:
            - orders-api
        opaquetoken:
          introspection-uri: https://auth.example.test/oauth2/introspect
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Placeholders resolve from runtime property sources. **Never store real client secrets in Git or Java code.**

- JWT mode uses a trusted key source + validators.
- Opaque mode uses an introspection endpoint + client authentication.
- Having both property groups present **does not prove** they are applied to the right routes; the `SecurityFilterChain` beans below must explicitly choose their mode.
- The introspection client ID is the Resource Server's credential **to query the AS**, distinct from a token's `client_id` metadata.

### 9.3. Two Chains with Fixed Matchers

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class MultiMechanismSecurity {

    @Bean
    @Order(1)
    SecurityFilterChain jwtOrdersApi(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/jwt/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/jwt/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/jwt/orders")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain introspectedOrdersApi(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher("/api/opaque/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .requestCache(cache ->
                cache.requestCache(new NullRequestCache()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/opaque/orders/**")
                    .hasAuthority("SCOPE_orders:read")
                .requestMatchers(HttpMethod.POST, "/api/opaque/orders")
                    .hasAuthority("SCOPE_orders:write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth
                .opaqueToken(Customizer.withDefaults()))
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain rejectUndeclaredRoutes(HttpSecurity http)
            throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll())
            .build();
    }
}
```

**This is a learning example for API partitioning, not a complete production config.** Specifically:

- `@Order` and `securityMatcher` select **the first matching filter chain**; it does not automatically try the second chain if JWT authentication fails in the first chain.
- The first chain uses **JWT**, without sniffing dot counts.
- The second chain uses **opaque introspection**, also without sniffing dot counts.
- The final chain denies by default so routes outside the two zones do not accidentally run unprotected. Design catch-all error handling suitable for the API.
- `csrf(...disable)` applies only to stateless APIs that do not use cookie/session authentication. Web login endpoints need separate CSRF and session policies.
- If the API needs public health or actuator endpoints, define an appropriately scoped policy and filter chain rather than applying `permitAll()` carelessly across all paths.
- If both areas read the same database, **services/repositories must enforce identical tenant/owner checks**; placing JWT/opaque on different URLs does not automatically make the data safe.

### 9.4. What Happens When a "JWT-Looking" Token Hits the Opaque Branch?

```http
GET /api/opaque/orders/42 HTTP/1.1
Authorization: Bearer a.b.c
```

The `/api/opaque/**` chain still calls `OpaqueTokenIntrospector`. It **does not** switch to `JwtDecoder` just because the string has two dots. The Authorization Server decides whether the token is active and matches the resource/token profile; if inactive or lacking scope, the request is rejected per policy.

Conversely:

```http
GET /api/jwt/orders/42 HTTP/1.1
Authorization: Bearer opaque-value-without-dots
```

The JWT chain requires `JwtDecoder` to verify a JWS; a string that cannot be validated as a JWT access token is rejected. It **does not** automatically forward to the opaque endpoint to try to get through.

### 9.5. Two Routes Must Not Become Bypasses for Each Other

If an order can be accessed via:

```text
/api/jwt/orders/42
/api/opaque/orders/42
```

both must enforce **the exact same resource requirements**: valid issuer/AS contract, `orders-api` audience, read scope, tenant, and owner. Never give the opaque branch `.anyRequest().authenticated()` while the JWT branch enforces `SCOPE_orders:read`, because an attacker can simply pick the weaker URL.

Do not build a "JWT-only admin API" and an "opaque legacy API" with equivalent privileges where one branch skips object authorization.

---

## 10. Safe Pattern B: A Single Introspection Mechanism for an API Supporting Multiple Access Token Formats

Another valid option is **the API has a single authentication policy: RFC 7662 introspection**. The AS ensures tokens are introspected properly and returns metadata the Resource Server is permitted to use, regardless of whether the token looks like a JWT or a reference token.

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .sessionManagement(session -> session
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders:read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth ->
            oauth.opaqueToken(Customizer.withDefaults()))
        .build();
}
```

This approach has an advantage: **one authentication protocol for both token formats**, with no format sniffing needed. Yet it is only safe when the AS honors this contract:

- Returns `active=true` only for **valid access tokens** that the introspection requester is authorized to use/inspect.
- Enforces resource binding for `orders-api` (via `aud` or introspection client policy).
- Enforces clear issuer/profile/token-type checks.
- Clearly defines `scope`/`roles`/tenant fields.
- Distinguishes inactive tokens from HTTP client-credential/network errors.
- Defines introspection caching and revocation latency decisions.

**Never treat `active=true` as permission to call all endpoints**. The Resource Server must still enforce authorities and object-level permissions.

### 10.1. What You Should Not Assume About RFC 7662

Under RFC 7662, the response must include the `active` boolean. Metadata fields `iss`, `aud`, `sub`, `exp`, `client_id`, `scope`, and `token_type` are **optional in the protocol**.

If the application requires checking audience and issuer, you must agree on an explicit required contract or ensure the AS restricts tokens to the right resource. Never invent a default audience/issuer when the response omits the field.

An opaque introspection endpoint is not a "JWT verification fallback" by default; it is **an authentication policy chosen upfront**.

---

## 11. When the Same URL Must Accept Multiple Mechanisms

A legacy product may be unable to change URLs and must accept both JWT access tokens and reference tokens on `GET /api/orders/**`. In that case, the design question is **not** "how to count dots" but "how to define the allowed set of issuers/token profiles and which mechanism verifies each profile without permitting token substitution or downgrades".

### 11.1. Preferred Choice: One Shared Introspection Contract

If the Authorization Server can introspect both JWTs and reference tokens, use one `OpaqueTokenIntrospector` for that URL. That way tokens are evaluated against a single state/policy source without format sniffing.

### 11.2. If Two Verification Pipelines Are Required

You must design a policy-driven resolver, such as:

- A fixed registry of trusted issuers and JWKS endpoints.
- A registry defining accepted profiles, token types, audiences, signing algorithms, and client authentication.
- Rules to **identify and bind a token to a profile** that do not rely merely on "two dots".
- Pre-verification metadata (if read at all) used solely to **look up in an allowlist**, never becoming proof itself.
- Once a token is assigned to a profile, **invalid signature/issuer/audience/time is a final failure**, never trying another provider with looser rules.
- If there is ambiguity between two profiles, reject or apply the same agreed strong policy—never choose an "easy pass" branch.
- Negative integration tests for every token substitution across profiles.
- Never allow different JWT/opaque clients to grant higher privileges than intended just because both produce `Authentication`.

**If a reliable disambiguation rule cannot be established**, you may need to change the API/token contract rather than accepting an unprovable heuristic.

### 11.3. Do Not Blindly Build "Try All Providers Until One Passes"

Spring Security has many types of authentication providers/managers. However, a `ProviderManager` with multiple providers **does not automatically turn everything into a safe JWT/opaque design**:

- Some providers support only one authentication token class.
- Provider ordering and exception handling matter.
- One provider might be tried after another in certain scenarios.
- If providers accept the same credential under different conditions, policy becomes hard to audit.
- Fallbacks can make issuer/audience/type checks inconsistent.

The design must state **exactly which provider is allowed to verify which token/profile**, rather than adding two providers to a list and hoping the framework picks accurately.

### 11.4. Do Not Use `BearerTokenResolver` to Authenticate

`BearerTokenResolver` is responsible for **extracting the Bearer token from the HTTP request** (typically from the `Authorization` header), not verifying signatures, issuers, audiences, or scopes.

A custom resolver can restrict how tokens are transmitted, but cannot answer "which token is trustworthy" just because a string has three segments. Do not confuse **extraction** with **authentication**.

---

## 12. Spring Security Multi-Issuer JWT: Using Issuer Hints Properly

When **all allowed tokens on a route are JWT access tokens** from a set of trusted issuers, you can use an issuer resolver—this is **not** a strategy for distinguishing JWTs from opaque tokens by dot count.

Conceptual example in Spring Security Servlet:

```java
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtIssuerAuthenticationManagerResolver;

import jakarta.servlet.http.HttpServletRequest;

AuthenticationManagerResolver<HttpServletRequest> resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://idp-a.example.test/realms/orders",
        "https://idp-b.example.test/realms/orders"
    );
```

You can then wire the resolver into the corresponding `oauth2ResourceServer(...)` or `BearerTokenAuthenticationFilter` DSL for your version. Some builder/factory APIs vary across Spring Security versions; consult the exact library version's documentation when implementing.

**Key meaning:**

- An issuer hint from a token **is rejected if not in the allowlist**.
- Select the right manager/JWKS by trusted issuer.
- The manager must verify signature and expected issuer, audience, time, and token type/profile.
- A JWT with a forged `iss` from an unregistered issuer is rejected.
- An opaque token is not a profile handled by this resolver and must not "jump over" to opaque auth on parse failure.

### 12.1. Adding Audience and Token Profile

Even with a trusted issuer resolver, the Resource Server must ensure the token is intended for `orders-api`. If a customized `JwtDecoder` omits an audience validator, you could accept a `payments-api` token signed by the same keyset.

In a multi-issuer environment, configure per issuer:

| Issuer | JWK source | Audience | Allowed alg | Token profile |
|---|---|---|---|---|
| `idp-a.example.test/realms/orders` | Trusted JWKS A | `orders-api` | RS256 | JWT access token A |
| `idp-b.example.test/realms/orders` | Trusted JWKS B | `orders-api` | ES256 | JWT access token B |

This set is **pre-declared policy**. Never derive JWKS URLs dynamically from unverified `jku`, `x5u`, or `iss` in a JWT.

### 12.2. One Issuer per Tenant

If `/t/acme/**` requires tokens from the Acme issuer, tenant routing can select the **trusted issuer policy** and the decoder verifies the token matches that issuer. Host/path remains a request target, not proof of membership; the token must verify issuer/resource/tenant, and data queries must be tenant-scoped.

If an Acme request carries a Beta token, reject it. Do not fix the mismatch by switching the query to Beta just because the token verified under another issuer.

---

## 13. Validation Requirements Across Every Mechanism

### 13.1. For JWT JWS Access Tokens

A properly configured `JwtDecoder` must verify:

1. Acceptable JWS/JWT syntax.
2. Valid **JWS signature** against a trusted public key.
3. **Algorithm allowlist** (e.g., RS256 only per contract).
4. **Issuer** in allowlist / expected issuer.
5. **Audience** contains `orders-api`.
6. **Time**: `exp`, `nbf`; clock skew per policy.
7. **Token type/profile**: reject ID Tokens and other-purpose JWTs.
8. Required claims `sub`/`client_id`/`scope` per user/workload profile.
9. Principal and authorities created only from verified claims.
10. HTTP/method/object authorization applied separately.

Never let unverified `kid`, `jku`, or `alg` establish trust. An unknown `kid` may only trigger a refresh from a **trusted JWKS endpoint** per policy, never fetching keys from an arbitrary URL inside the token.

### 13.2. For Opaque/Introspection Access Tokens

An `OpaqueTokenIntrospector` must:

1. Call only a **fixed/allowlisted trusted introspection endpoint**.
2. Authenticate the introspection requester with appropriate credentials.
3. Enforce HTTPS/TLS, timeouts, rate limits, and log masking.
4. Check the response has boolean `active`; `false` → reject.
5. Enforce **resource/audience binding** per metadata or AS policy.
6. Check issuer/token type/profile per contract.
7. Parse `scope`/roles/tenant with a strict schema; never grant defaults.
8. Never create a principal on HTTP/network/schema errors.
9. Apply bounded, fail-closed caching/revocation policies.
10. Apply HTTP/method/object authorization separately.

RFC 7662 can introspect many token types, so **a request with two dots is not automatically an error** on the opaque branch. Mechanism selection follows resource policy, not token string shape.

### 13.3. For Web Sessions or HTTP Basic

If the system also has web login sessions:

- Partition `/web/**` and `/api/**` cleanly using matchers/filter chains.
- Bearer-only APIs must not reuse `JSESSIONID` to authenticate when Bearer is invalid/absent.
- `SessionCreationPolicy.STATELESS` generally fits Bearer APIs, though verify no custom filter/session fallback exists.
- Browser cookie authentication requires CSRF protection per threat model.
- HTTP Basic, if allowed, needs clear policy and TLS transport; never "try Basic" when a Bearer JWT fails.
- A client sending both cookies and Bearer must follow an explicit policy; never let a high-privilege cookie override a lower-privilege Bearer user.

Never use "multiple mechanisms" as an excuse to let **any credential that looks valid** into the same service without distinguishing assurance levels.

---

## 14. Spring Security: JwtDecoder Is Not a Text Parser

A JWT Resource Server configuration:

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

The goal is for `JwtDecoder` to perform **verification + validation**, not merely split a string into three parts.

A custom decoder:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class TrustedJwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder() {
        String issuer =
            "https://auth.example.test/realms/orders";
        String jwks =
            "https://auth.example.test/realms/orders/jwks";

        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(jwks)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains("orders-api")) {
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
                issuerAndTime,
                audience
            )
        );

        return decoder;
    }
}
```

**This is an issuer + audience + algorithm validation example.** When declaring a custom `JwtDecoder` bean, Spring Boot may **no longer apply** validators from YAML `issuer-uri`/`audiences`. Do not omit `JwtValidators.createDefaultWithIssuer` or the audience validator. For the RFC 9068 JWT access-token profile, you also need to check `typ`/required claims per the actual token contract; do not assume the snippet above satisfies every profile.

A token with exactly two dots and a forged signature **will not** pass this decoder. A validly signed JWT with `aud=web-portal` must also be rejected.

### 14.1. `NimbusJwtDecoder` Does Not Automatically Accept Every JWE Type

The `withJwkSetUri(...)` configuration above is for JWS signature verification against a trusted keyset. It **does not imply** support for decrypting five-part compact JWEs or nested JWTs. If the AS issues encrypted tokens, design the appropriate pipeline and crypto keys per profile, or use introspection if supported by the AS.

### 14.2. Do Not Fetch Public Keys from the JWT Header

An attacker can send:

```json
{
  "alg": "RS256",
  "kid": "attacker-key",
  "jku": "https://attacker.example.test/jwks.json"
}
```

Do not turn `jku` into an HTTP request just because the token header says so. The JWKS URL must come from **trusted configuration/discovery**, never attacker input. This protects against key substitution and SSRF.

---

## 15. Testing Strings That Easily Fool Parsers

A valuable test suite must include data that deliberately **contradicts shape and reality**. If you only test "real JWT has two dots, real opaque has zero dots", format-sniffing bugs can go unnoticed.

### 15.1. Test Matrix Separating Format from Trust

| Input / token | Shape | Endpoint/profile | Expected behavior |
|---|---|---|---|
| Three-part JWS, valid signature, right issuer/aud/profile | Two dots | JWT-only | Authentication succeeds, then check scope/owner. |
| Three-part JWS, tampered payload, old signature | Two dots | JWT-only | Rejected, typically 401. |
| Three-part JWS, random signature | Two dots | JWT-only | Rejected. |
| `a.b.c` | Two dots | JWT-only | Must not be treated as a verified JWT. |
| `a.b.c` | Two dots | Opaque-only, AS reports `active=false` | Rejected by introspection. |
| `a.b.c` | Two dots | Opaque-only, AS confirms active access token for right resource | Can authenticate if contract is met. |
| `abcDEF123` | Zero dots | Opaque-only, active=true right resource | Can authenticate. |
| `abcDEF123` | Zero dots | JWT-only | Rejected; no automatic fallback. |
| `a.b.c.d.e` | Four dots | JWT JWS-only | Rejected if decoder does not support JWE. |
| `a.b.c.d.e` | Four dots | Opaque-only, active=true right resource | Can authenticate per AS contract. |
| JWS header `alg=none`, empty signature | Two dots | JWT-only | Rejected under signed access-token policy. |
| JWT signed by attacker private key | Two dots | JWT-only | Rejected even if claims look valid. |
| JWT issuer not in allowlist | Two dots | JWT-only | Rejected. |
| JWT right issuer, another API's audience | Two dots | JWT-only | Rejected. |
| Validly signed OIDC ID Token, `aud=web-portal` | Two dots | API access-token profile | Rejected. |
| Valid JWT access token missing `orders:read` | Two dots | Read endpoint | Authenticated, but 403 for missing permission. |
| Active opaque token right resource, missing scope | Any | Read endpoint | No read authority granted → 403. |
| Valid JWT, right scope, wrong tenant | Two dots | Read endpoint | Tenant authorization denied. |
| Valid JWT, right scope, Bob's order | Two dots | Read endpoint | Object permission denied. |
| Introspection HTTP 503 error | Any | Opaque-only | Fail closed; do not try local parse to let through. |
| JWKS endpoint error with missing key | Two dots | JWT-only | Fail closed; do not arbitrarily switch to introspection. |

**Key testing takeaway:** a three-part token can be rejected in JWT mode; a three-part token **can be a valid opaque token** when confirmed by the AS per contract; a dotless token is not automatically accepted. Both 401 and 403 must come from **authentication/authorization outcomes**, not string length or shape.

### 15.2. Test Fixture Set Against Token Confusion

You should create:

```text
jwt-valid-orders-read
jwt-valid-orders-write-only
jwt-valid-payments-audience
jwt-valid-web-portal-id-token
jwt-expired
jwt-forged-signature
jwt-alg-none
opaque-active-orders-read-without-dots
opaque-active-orders-read-with-two-dots
opaque-active-orders-read-with-four-dots
opaque-inactive-with-two-dots
opaque-active-payments-audience
opaque-active-no-scope
arbitrary-string-with-two-dots
arbitrary-string-with-zero-dots
```

Fixture names are **descriptive**, not actual token values. For JWT signing tests, use a test RSA/EC keypair and a test JWKS endpoint. For opaque tests, use a mock AS introspection endpoint capable of returning metadata for the test tokens.

---

## 16. Integration Testing: Ensuring Routes Do Not Format-Sniff

### 16.1. Testing with `MockMvc` Using Real Bearer Headers

`spring-security-test` provides `jwt()`/`opaqueToken()` to build mock principals. They are very useful for HTTP authorization, but **skip the decoder/introspection pipeline**. Therefore, do not use them to prove route-based token selection.

To test real format confusion:

1. Send a real `Authorization: Bearer ...` HTTP header through `MockMvc` or an embedded server.
2. Use a test `JwtDecoder` with an explicit policy, or better yet, real signed JWTs + local JWKS.
3. Use a test `OpaqueTokenIntrospector` endpoint/spy to prove opaque routes call the right AS.
4. Assert **the unselected mechanism** was not called.
5. Assert status, authorities, and domain data are correct.
6. Never use production client secrets in tests.

### 16.2. Scenario-Level Test Example

```java
@Test
void jwtShapedOpaqueTokenStillGoesToIntrospectionRoute()
        throws Exception {

    // Given introspection endpoint recognizes only token "a.b.c"
    // with active=true, aud=orders-api, scope=orders:read.

    mvc.perform(get("/api/opaque/orders/42")
            .header("Authorization", "Bearer a.b.c"))
        .andExpect(status().isOk());

    // Spy/mock AS must verify introspection was called.
    // JwtDecoder must not be called for this request.
}
```

This test is a **skeleton** and passes only with a controller/fixtures granting access to order 42. Asserting `isOk()` requires matching tenant/owner fixtures. Real tests can assert spy interactions and the corresponding principal/subject in the response.

Conversely:

```java
@Test
void opaqueLookingTokenIsNotRoutedToIntrospectionFromJwtApi()
        throws Exception {

    mvc.perform(get("/api/jwt/orders/42")
            .header("Authorization",
                "Bearer opaque-test-token"))
        .andExpect(status().isUnauthorized());

    // Verify introspection endpoint was not called.
}
```

This is also a skeleton assuming the JWT decoder rejects strings that are not signed JWT access tokens. If the test only uses `jwt()`, it will not actually test route/token extraction.

### 16.3. Testing Malformed Bearer Headers and Transport

Never allow two token channels at once just because format is unclear:

```http
GET /api/jwt/orders/42?access_token=token-B HTTP/1.1
Authorization: Bearer token-A
```

Verify `BearerTokenResolver`/server policy and RFC 6750. By default, prefer the `Authorization` header and do not enable query-string tokens since they easily leak into proxy logs and browser history. A token containing dots in the header must still be passed intact to **the configured mechanism**; do not strip dots or manually Base64URL-decode to "clean" the credential.

### 16.4. Do Not Test Only One Side

If you only test `GET /api/jwt/orders/**`, you might miss that `/api/opaque/orders/**` is a weaker path. The test suite must verify:

- Valid JWT → JWT route allows per scope/owner.
- Invalid JWT → JWT route 401, **no introspection**.
- Active opaque → opaque route allows per contract.
- Inactive opaque → opaque route 401, **no JWT attempt**.
- Token with two dots → opaque route still introspects.
- Token without dots → JWT route still requires decoder.
- Token with wrong scope → 403 on **both routes**.
- Token with wrong audience → denied on **both routes**.
- Cross-tenant caller → denied on **both routes**.
- Undeclared URL → denied by default.

---

## 17. Cryptographic Testing with Real Signed JWTs

### 17.1. Why Is a Mock Decoder Not Enough?

A test with a stubbed `JwtDecoder` can return fake claims for `a.b.c` without verifying a signature. It helps test **Spring filter routing**, but does not prove the production decoder is secure.

To test the trust root:

1. Generate an RSA test keypair `K1`.
2. Publish `K1`'s public JWK via a trusted local JWKS endpoint.
3. Use the test private key to sign a JWS access token.
4. Configure `NimbusJwtDecoder` with the test JWKS and issuer/audience validators.
5. Send the signed token via `Authorization: Bearer` to the JWT route.
6. Flip one byte of the payload while keeping the signature; assert 401.
7. Sign a token with private key `K2` not in the trusted JWKS; assert 401.
8. Create an ID Token with `aud=web-portal` validly signed by `K1`; assert the API rejects it.
9. Try `alg=none`, `HS256`, or attacker `jku`; assert no bypass.
10. Never use production private signing keys in tests.

**You cannot prove cryptographic verification** simply by calling Base64URL decode and asserting `sub`. Trust comes from the signature combined with a trusted key source and validators.

### 17.2. Do Not Use JWE Shape as a Shortcut

When testing five-part strings, verify the real contract:

- JWT-only signed-JWS route does not support JWE → reject.
- Purpose-built JWE route → decrypt/validate per profile and keys.
- Opaque introspection route → AS decides whether token is active and resource-bound.
- No mechanism allowed → reject.

Do not add "JWE accepted" to a decoder just because a test happens to encounter four dots.

---

## 18. Successful Authentication Does Not Mean Resource Access

A valid token containing:

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "sub": "alice-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "tenant_id": "tenant-a"
}
```

still must not be allowed to view orders belonging to Bob or tenant B.

You should enforce at the data layer:

```java
public OrderDto readOrder(
        String orderId,
        VerifiedActor actor) {

    return repository
        .findByIdAndTenantIdAndOwnerIssuerAndOwnerSubject(
            orderId,
            actor.tenantId(),
            actor.issuer(),
            actor.subject())
        .map(this::toDto)
        .orElseThrow(OrderNotFoundException::new);
}
```

`VerifiedActor` must be built from an **authenticated principal** that passed JWT/introspection and schema validation; tenant/user fields must never come from raw unverified tokens or client-sent HTTP headers.

For workload tokens (Client Credentials), `sub` may be a service identity rather than a human user. Thus the actor profile and access policy may differ, yet **it must still bind to the right resource/tenant and scopes**.

### 18.1. An AccessDenied Does Not Make a Token "Invalid"

Distinguish:

| Outcome | Meaning | Typical response |
|---|---|---|
| JWT invalid signature | Authentication failed. | 401, Bearer `invalid_token`. |
| Opaque introspection `active=false` | Authentication failed. | 401. |
| Valid token but wrong `aud` for API | Token is not accepted for this resource. | 401. |
| Valid token missing `orders:read` | Authentication may succeed, authorization failed. | 403, possibly `insufficient_scope`. |
| Valid token, has read, wrong owner/tenant | Object authorization failed. | 403 or 404 per API policy. |

Do not collapse all five cases into a "whether the token has three parts" rule. In Spring Security, `BearerTokenAuthenticationEntryPoint` and `BearerTokenAccessDeniedHandler` typically handle challenges corresponding to the authentication/authorization context.

---

## 19. Common Implementation Mistakes

### 19.1. Using `String.split("\\.")` Without Understanding Its Semantics

`String.split(...)` also drops trailing empty segments by default. Therefore:

```text
header.payload.
```

can yield the wrong segment count if `split("\\.")` is called without an appropriate limit. Yet **fixing the split technique does not solve the security problem**: a parser counting parts accurately still does not verify the token.

If you need serialization diagnostics, use a standard JOSE library instead of manually splitting/decoding base64. **Never use parser output to grant trust.**

### 19.2. Allowing `alg=none` Because the JWT Is Structurally Valid

This is an authentication flaw. The decoder must reject tokens without integrity protection under a signed-access-token contract. Never let attackers pick the algorithm or public key.

### 19.3. Fetching Keys from `jku`/`x5u` in the Header

This enables key-source confusion and SSRF. Use only configured JWKS URLs or URLs from trusted issuer metadata, never from JWT input.

### 19.4. Treating Every `eyJ...` as a JWT

`eyJ` is merely a common prefix when Base64URL-decoding JSON starting with `{"...`. An attacker can craft an opaque string or forged string starting with `eyJ`. Never use a prefix as a trust signal.

### 19.5. Treating Dotless Tokens as Active Opaque Tokens

An opaque token is active only when verified by the Authorization Server via introspection (or an equivalent contracted mechanism). A random string without dots **is not automatically valid**.

### 19.6. Invalid JWT Falling Back to Opaque Mode

This risks bypassing strict validators and exposing tokens to unintended endpoints. Policy must define the mode upfront; failed authentication must not switch modes.

### 19.7. Treating Every `active=true` as an Access Token for the API

An introspection response may omit audience/token-type under RFC 7662. You need an AS–API contract for resource binding, issuer, token type, and scopes. Never let a `payments-api` token call `orders-api`.

### 19.8. Accepting OIDC ID Tokens Because They Are Also RSA-Signed

An ID Token is an assertion for an OIDC client; you must check access-token profile/audience. Signing by the same issuer does not turn an ID Token into an API access token.

### 19.9. Taking Issuer from Unverified Payload for Auto-Trust

A JWT self-declaring `iss` cannot instruct the app to fetch keys from an arbitrary issuer. Trust only a registry/allowlist of onboarded issuers.

### 19.10. Using Basic/Session as a Fallback

A Bearer-only API must not fall back to a web session or HTTP Basic after a Bearer token fails without an explicit policy. That creates an opportunity to use another user's identity via browser cookies.

### 19.11. Skipping Tenant/Owner Checks

Authentication via JWT or introspection does not replace object-level authorization. The `orders:read` scope does not grant access to every order across every tenant.

### 19.12. Testing Only with `jwt()` or `opaqueToken()`

Test post-processors construct mock authentication without testing JWT signatures, issuer/audience, token extraction, or HTTP introspection. Dedicated signed-token and mock-AS integration tests are required.

### 19.13. Classifying by URL Extension

`/tokens/abc.jwt`, a filename ending in `.jwt`, or a `format=jwt` query parameter is also client-controlled, not proof of token format or trust. If an API has separate routes, define independent policies and verify tokens against those policies.

### 19.14. Checking `isAuthenticated()` on a Manually Constructed Token

An `Authentication` object can be manually constructed with `isAuthenticated=true` while holding unverified claims. Only create authenticated tokens through a provider/manager that performed genuine verification; never set the verified flag by inferring from dot count.

### 19.15. Caching "Last Validated Token" by Connection or IP

The same IP or TCP connection can serve multiple users. Never reuse the previous request's principal for a request missing a token or carrying a different token. For introspection caches, key by token/issuer/resource/policy with an explicit TTL, and never store raw Bearer credentials where they might be logged.

---

## 20. Observability and Troubleshooting Without Leaking Tokens

A multi-mechanism system should distinguish failures:

```text
AUTHN_JWT_SIGNATURE_INVALID
AUTHN_JWT_ISSUER_MISMATCH
AUTHN_JWT_AUDIENCE_MISMATCH
AUTHN_JWT_TOKEN_TYPE_INVALID
AUTHN_OPAQUE_INACTIVE
AUTHN_INTROSPECTION_SCHEMA_INVALID
AUTHN_INTROSPECTION_UPSTREAM_FAILURE
AUTHN_MECHANISM_NOT_ALLOWED_FOR_ROUTE
AUTHZ_SCOPE_MISSING
AUTHZ_TENANT_DENIED
AUTHZ_OBJECT_DENIED
```

These are **reason codes for internal logs/metrics**, not RFC 6750 Bearer error codes. When responding to clients, keep HTTP statuses/challenges context-appropriate and limit information leakage.

### 20.1. Do Not Log Raw Tokens to Debug Dot Counts

An anti-pattern:

```java
log.info("raw token={} dotCount={}", token, countDots(token));
```

A Bearer token is a **credential**, so logging it creates token-theft risk if logs are accessed. Observe only:

- Matched API route template, security chain ID.
- Authentication mechanism **selected by policy**, not "format guess".
- Issuer configuration ID from the registry.
- Bounded-cardinality error reasons.
- JWT validation failure rate, introspection failure rate.
- JWKS latency/cache refresh, introspection latency.
- Client correlation/request ID.

Never put `sub`, `jti`, raw tokens, or unverified payloads into metric labels. Never put full introspection responses containing PII into error logs.

### 20.2. Signs of a Downgrade Bug

If internal logs record:

```text
jwt_verification_failed → fallback_to_opaque → authenticated
```

on the same request when policy does not define that behavior, investigate immediately. Steps:

1. Identify which route/chain was actually selected.
2. Identify which mechanism produced the final `Authentication`.
3. Inspect issuer/audience/type/scope validators of each provider.
4. Check for catch-all/fallback code or token-format regexes.
5. Check whether AS introspection returns `active=true` for tokens from another resource.
6. Test forged three-part tokens, ID tokens, and bad-signature JWTs.
7. Close the route bypass with explicit policy configuration and regression tests.

Never "fix" this by logging production raw tokens or disabling JWT signature validation to avoid 401s.

---

## 21. Practice: Analyzing Six Requests

### Scenario A — Forged JWT with Two Dots

```http
GET /api/jwt/orders/42 HTTP/1.1
Authorization: Bearer header.payload.fake
```

**Right:** the JWT decoder verifies the signature against trusted keys and rejects it. **Wrong:** the system only counts two dots and builds a principal.

### Scenario B — Valid Opaque Token with Two Dots

```http
GET /api/opaque/orders/42 HTTP/1.1
Authorization: Bearer a.b.c
```

The AS-authorized introspection endpoint checks `a.b.c`. If it returns `active=true` with sufficient contracted audience, scope, and actor, authentication can succeed. Having two dots does not make it a JWT.

### Scenario C — Valid JWT Sent to the Wrong Route

```http
GET /api/opaque/orders/42 HTTP/1.1
Authorization: Bearer <valid-jwt>
```

If the opaque route is introspection-only, the AS decides whether this token can be introspected. Do not switch to the JWT branch; do not assume "valid JWT" under some issuer suffices for every API.

### Scenario D — Validly Signed ID Token

```http
GET /api/jwt/orders/42 HTTP/1.1
Authorization: Bearer <valid-oidc-id-token>
```

If `aud=web-portal` and token type/profile is ID Token, the Resource Server must reject it. A valid signature does not change audience or purpose.

### Scenario E — JWT with Right Issuer but Wrong Audience

```json
{
  "iss": "https://auth.example.test/realms/orders",
  "aud": ["payments-api"],
  "scope": "orders:read"
}
```

The `orders-api` rejects it even though signature and scope are valid. A two-dot JWT does not prove applicability.

### Scenario F — Valid Token for Another Tenant's Order

```text
Token: JWT signed, aud=orders-api, scope=orders:read, tenant=t-acme
URL:   /api/jwt/orders/42
Order: id=42, tenant=t-beta
```

The API must reject per tenant/object policy. This is an **authorization boundary**, not format detection.

---

## 22. Handoff Checklist for a Multi-Mechanism Resource Server

| Question | Requirement to meet |
|---|---|
| **Which mechanisms does this API accept?** | JWT-only, introspection-only, or contracted multi-profile; never guess from dots. |
| **What drives mechanism selection?** | Trusted route/host/issuer registry, or one shared introspection policy. |
| **Are there provider fallbacks?** | No downgrade when a token is invalid; all exceptions/paths explicitly designed. |
| **What is the JWT key trust root?** | JWKS/public keys from trusted issuer/config; never attacker `jku`. |
| **JWT alg allowlist?** | Only configured algorithms; reject `none` when policy requires signed JWS. |
| **Issuer/audience/time?** | Verified from validated token, matching `orders-api` and token lifetime. |
| **Token type/profile?** | Reject ID Tokens/refresh tokens/assertions not intended for the API. |
| **Introspection contract?** | Boolean `active`, proper client auth, resource binding, metadata schema. |
| **Scope/authority mapping?** | Never auto-add privileges when scope is missing or claims have the wrong type. |
| **Tenant/object checks?** | Enforced in service/repository, not only HTTP routes. |
| **Two-route parity?** | No alternative endpoint for the same data with weaker policy. |
| **Multi-issuer allowlist?** | Issuer hint must not trust arbitrary URLs. |
| **HTTP challenges?** | 401 vs 403, `WWW-Authenticate`, and errors per RFC 6750. |
| **Caching/revocation?** | Bounded TTL, no identity reuse across requests. |
| **Testing?** | Forged JWT/ID token/dotted opaque/JWE shape/AS errors, signed JWT and introspection integration. |
| **Observability?** | Reason codes, request IDs; never log raw Bearer tokens/secrets/PII. |

---

## 23. Final Decision Model

```text
API Resource Server receives:
  Authorization: Bearer <arbitrary string>
                         │
                         ▼
   Choose predefined security policy for resource
    ├─ JWT access-token profile
    │    └─ trusted issuer/JWKS + signature/alg/iss/aud/exp/typ validation
    │
    ├─ Opaque/introspection access-token profile
    │    └─ trusted AS + authenticated introspection + active/resource metadata
    │
    └─ Unsupported mechanism
         └─ DENY
                         │
                         ▼
           Did selected mechanism verify?
                  ├─ No  → reject
                  └─ Yes → authenticated principal
                                │
                                ▼
                    Check scope / actor / tenant / object
                             ├─ Deny
                             └─ Permit
```

**There is no step that "counts dots to decide trust level".** If format recognition exists for performance, it is solely **unverified input** for an internal parser and must never alter trust policy or produce a successful authentication.

## 24. Technical References

- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): compact serialization, protected header, signature, and `kid`.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516.html): five parts of JWE compact serialization, encryption/integrity.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): JWT claims, issuer, audience, time, and unsecured JWT.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): trusted public key sets.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): cross-JWT confusion, token substitution, mutually exclusive validation rules, algorithm/key trust.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): `at+jwt`, access-token-specific claims, and profile.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662.html): active metadata, introspection request, and resource binding policy.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer token syntax, HTTP transport/challenge.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): distinguishing OIDC ID Token and OAuth access token.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, verified JWT, issuer/audience validation.
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): `OpaqueTokenIntrospector` and introspection.
- [Spring Security — OAuth 2.0 Resource Server Multitenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): trusted issuers and resolvers.
- [Spring Security — Java Configuration / SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): multiple chains, `securityMatcher`, and matching order.
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): route-level authorization.
- [OWASP — JSON Web Token Cheat Sheet for Java](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html): common risks when implementing JWT.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, resource-level permission checks.

**Conclusion:** **A token with two dots is not trustworthy as a JWT for that reason; a token without dots is not a valid opaque token for that reason.** Compact JWS, JWE, reference tokens, and ID Tokens may look similar or different, yet **no shape proves identity, issuer, audience, or permissions**. In Spring Security supporting multiple mechanisms, choose the mechanism by **predefined policy**, verify the token completely within that branch, never fall back to downgrade checks, and always enforce scope/tenant/object authorization after authentication succeeds.
