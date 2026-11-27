# Never Substitute Claim Checks for Signature or Token-Source Verification

In a **Spring Security OAuth 2.0/OIDC Resource Server**, an access token may carry very convincing claims: **`iss`** pointing to the right Authorization Server, **`aud`** matching the API, **`exp`** still in the future, **`scope`** holding the needed permission, and **`sub`** matching a real user ID. However, **checking those claims is not enough to conclude the token is valid**.

Why: claims are merely data carried by the token. A request sender can craft a brand-new JWT and put any values they like into the payload. If the API simply Base64URL-decodes and compares claims without verifying **the signature and trusted token source**, an attacker can forge a token never issued by the Authorization Server.

A proper JWT authentication flow must separate four questions:

1. **Can the structure be parsed?** Parse the JOSE header and JWT claims.
2. **Who had authority to issue this token?** Verify the signature/MAC using a key bound to a trusted issuer.
3. **Is this token valid for this API right now?** Validate **`iss`**, **`aud`**, **`exp`**, **`nbf`**, token type, and acceptance rules.
4. **Is the subject authorized to perform this action on this data?** Check scopes, roles, permissions, tenant, ownership, and domain policies.

In Spring Security, a properly configured **`JwtDecoder`** handles JWT verification before claims become an **`Authentication`**. For an **opaque token**, trust is established via **introspection** against a trusted Authorization Server rather than local JWT signature verification.

## 1. Claims Are Assertions, Not Proof

Suppose the Orders API accepts tokens satisfying:

~~~text
Trusted issuer:    https://login.example.com/realms/shop
Audience:          orders-api
Required scope:    orders.read
~~~

A payload might look like:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1893450000,
  "exp": 1893456000,
  "scope": "orders.read",
  "tenant_id": "tenant-a"
}
~~~

If an application simply reads the JSON and checks:

~~~text
iss == trustedIssuer       -> true
aud contains orders-api    -> true
exp > currentTime          -> true, assuming at check time
scope contains orders.read -> true
tenant_id == tenant-a      -> true
~~~

then a **self-crafted JWT created by an attacker** can pass every one of those comparisons. The sender does not need the Authorization Server's private key to write JSON values.

Security layers must be kept distinct:

| Layer | What Does It Check? | If This Layer Is Skipped |
|---|---|---|
| **Parse** | JWS/JWT format, Base64URL, JSON | Token cannot be read structurally |
| **Verify** | Signature/MAC matches a key from a trusted source | Self-signed or forged tokens may be accepted |
| **Validate** | Issuer, audience, timestamps, token type, acceptance rules | Genuine tokens that are expired or wrong-target may be accepted |
| **Authorize** | Permissions for specific actions and resources | Users gain access beyond their privileges |

**Checking `iss` does not replace verification. Checking `aud` does not replace verification. Checking `exp` does not replace verification.** Conversely, a valid signature does **not replace** issuer, audience, and timestamp validation.

## 2. Why Being Able to Read a JWT Does Not Mean It Is Verified

A JWT signed with JWS Compact Serialization typically has three segments:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
~~~

Example JOSE header:

~~~json
{
  "alg": "RS256",
  "kid": "shop-sign-2026-11",
  "typ": "at+jwt"
}
~~~

Example payload:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

**Base64URL is encoding, not encryption.** Anyone holding an ordinary JWS JWT can decode its header and payload without a secret key. JWS protects integrity with a **signature**, rather than hiding contents from the token holder.

With **`RS256`**, the Authorization Server uses its **RSA private key** to sign the signing input:

~~~text
ASCII(BASE64URL(header) + "." + BASE64URL(payload))
~~~

The Resource Server uses the **trusted issuer's RSA public key** to verify that signature. If someone edits **`scope = orders.read`** to **`scope = orders.write`** without producing a matching signature, verification fails.

If an attacker re-signs the JWT with their own private key, the signature will match **their own public key**. That is still **not enough**: the Resource Server must verify that the key itself was authorized by the trusted issuer to sign access tokens.

### 2.1. Parsing the Payload in Java Is Merely Data Manipulation

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class UntrustedJwtViewer {

    // FOR SYNTAX ILLUSTRATION ONLY; NEVER use for authentication or authorization.
    public static String readPayloadWithoutVerification(String compactJws) {
        String[] parts = compactJws.split("\\.", -1);
        if (parts.length != 3) {
            throw new IllegalArgumentException("Expected three JWS parts");
        }
        byte[] bytes = Base64.getUrlDecoder().decode(parts[1]);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
~~~

This code does **not**:

- Verify the signature or MAC.
- Verify the key source or trusted issuer.
- Enforce allowed algorithms.
- Validate **`iss`**, **`aud`**, **`exp`**, **`nbf`**, or token profile.
- Verify whether scopes, roles, tenant, or ownership were legitimately granted.

A forged token with valid JSON still decodes cleanly here. Adding a JSON parser to convert the payload into a Map or DTO adds zero authentication proof.

A common anti-pattern:

~~~java
// WRONG: pseudocode illustrating a security vulnerability.
String token = getBearerToken(request);
Map<String, Object> claims =
    parseJson(UntrustedJwtViewer.readPayloadWithoutVerification(token));

if (trustedIssuer.equals(claims.get("iss"))
        && claimHasScope(claims, "orders.write")) {
    allowOrderModification();
}
~~~

Helper names like **`getBearerToken`**, **`parseJson`**, **`claimHasScope`**, and **`allowOrderModification`** are illustrative placeholders, not a Spring Security API. The flaw is **every check relies on unverified claims**.

Adding **`exp`** or **`aud`** to that `if` statement does not fix the bug. You must replace the parsing logic with a **`JwtDecoder` performing real verification**.

## 3. Attack Scenario: Forged Token With Matching Claims

An unauthorized caller can:

1. Construct a JWT payload whose **`iss`** matches the real issuer.
2. Fill in **`aud = orders-api`** and **`scope = orders.write`**.
3. Set **`exp`** in the future and **`sub`** to an administrator's ID.
4. Attach a dummy signature, use **`alg = none`** against a weak implementation, or self-sign with their own key.
5. Send the token in **`Authorization: Bearer`**.

~~~mermaid
sequenceDiagram
    participant X as Attacker
    participant API as Misconfigured Resource Server
    X->>X: Craft forged JWT with desired iss, aud, scope, exp
    X->>API: Authorization: Bearer forged JWT
    API->>API: Parse JSON and compare claims
    Note over API: Skips token source/signature verification
    API-->>X: Unauthorized access granted
~~~

**Matching configured claim values can never turn a self-crafted JWT into a token issued by the real issuer.**

In a properly built Resource Server, forged tokens must be rejected **before claims ever construct a principal or `GrantedAuthority`**.

### 3.1. Checking `iss` From an Unverified Payload Can Be Spoofed

~~~java
// WRONG if claims have not been verified.
if ("https://login.example.com/realms/shop".equals(claims.get("iss"))) {
    authenticateUser();
}
~~~

Anyone can write that issuer string in JSON. **`iss` distinguishes which issuer a token claims, not a digital signature.**

### 3.2. Checking Audience Does Not Prove Token Authenticity

A payload can be crafted as:

~~~json
{
  "aud": ["orders-api", "payments-api"]
}
~~~

If the server checks only **`aud contains orders-api`**, a forged token passes too. Audience must be checked **after verifying the token source and signature**. Conversely, a genuine signed token whose audience targets another API must still be rejected.

### 3.3. Checking Timestamps Does Not Prevent Forgery Either

An attacker can easily set **`exp`** far in the future. Timestamp checks are meaningful only once claims are protected by a trustworthy token-verification mechanism. A validly signed but expired token must be rejected; a forged token with a future `exp` must also be rejected.

### 3.4. Scopes, Roles, and Tenants Are Permission Data Carried Inside the Token

A JWT payload may include:

~~~json
{
  "scope": "orders.read orders.write",
  "roles": ["ADMIN"],
  "tenant_id": "tenant-a",
  "email_verified": true
}
~~~

These fields are **not** independent proof of authority. Only after the token passes verification should the API run converters and policies to derive permissions. Even in a valid token, OIDC scopes like **`openid`**, **`profile`**, and **`email`** do not grant business privileges by themselves.

## 4. "Token Source" Has Three Meanings That Must Stay Separate

| Interpretation | Example | Does It Prove Token Authenticity? |
|---|---|---|
| **HTTP request origin** | Browser, mobile app, service, or API Gateway sending a Bearer token | **No**; network origin does not prove the issuer signed the token |
| **Self-asserted token issuer** | JSON **`iss`** claim inside an unverified JWT | **No**; the sender can write anything |
| **API-trusted issuer / key source** | **`issuer-uri`** and server-configured JWKS/key source | **Can serve as a trust anchor** when paired with signature verification and validation |

Receiving a request over **HTTPS** protects the Bearer token in transit, yet does not prove the Authorization Server issued it. Likewise, a proxy forwarding a JWT does not make the JWT's JSON trustworthy on its own.

If your architecture delegates authentication to an API gateway, the backend needs a **trusted delegation boundary/protocol** confirming the gateway actually validated it (e.g., blocking direct access, mTLS, gateway-overwritten internal headers, or signed internal assertions). Never trust an identity header simply because a client sent that header name.

## 5. Key Sources Must Be Bound to a Trusted Issuer

The Resource Server normally knows the issuer URI **before any request arrives**:

~~~text
https://login.example.com/realms/shop
~~~

Spring Security can use that issuer to discover OIDC/OAuth2 metadata, find **`jwks_uri`**, and download the public JWKS over HTTPS. The public key used to verify signatures comes from configuration and trusted issuer metadata—**never from an arbitrary hint supplied by the JWT sender**.

~~~mermaid
flowchart TD
    C[Trusted issuer in config] --> M[Metadata discovery over HTTPS]
    M --> J[jwks_uri in trusted metadata]
    J --> K[JWKS containing public keys]
    T[Bearer JWT] --> P[Parse untrusted header/claims]
    P --> S[Select key by kid in trusted JWKS]
    K --> S
    S --> V{Signature valid with allowed alg?}
    V -->|No| X[401]
    V -->|Yes| Q{iss, aud, time, and profile valid?}
    Q -->|No| X
    Q -->|Yes| A[Enforce endpoint and data permissions]
~~~

Public keys themselves can be publicly readable; **who publishes the key and how it binds to the issuer is the trust boundary**. An attacker's public key will happily verify a signature created by that same attacker.

### 5.1. `kid` Is Only a Key-Selection Hint

A JWT header may contain:

~~~json
{
  "alg": "RS256",
  "kid": "sign-2026-11"
}
~~~

An attacker can put any **`kid`**. The decoder uses `kid` strictly to look up a key **within the key set published by the trusted issuer**. If the signature does not match that key, the token is rejected.

Never let **`kid`** construct file paths, SQL queries, or hostnames for fetching keys. Never look up keys globally by **`kid`** while ignoring which issuer was configured in a multi-tenant setup.

### 5.2. `jku`, `jwk`, `x5u`, or `x5c` Are Not Automatically Trustworthy

JWS supports these JOSE Header Parameters:

- **`jku`**: URL pointing to a JSON Web Key Set.
- **`jwk`**: an embedded JWK inside the header.
- **`x5u`**: URL pointing to an X.509 certificate chain.
- **`x5c`**: embedded X.509 certificate chain inside the header.
- **`x5t`/`x5t#S256`**: thumbprints aiding certificate identification.

In an untrusted external JWT, none of these fields **establish a trust anchor on their own**.

A critical anti-pattern:

~~~text
JWT header.jku = https://attacker.example/keys.json

Resource Server:
  1. Downloads URL from jku.
  2. Retrieves attacker's public key.
  3. Verifies attacker's signature and sees it pass.
  4. Trusts forged issuer, audience, and scope payload.
~~~

This is **key substitution**. Fetching arbitrary URLs from JWT headers also introduces **SSRF** risk. An HTTPS URL with a valid TLS certificate proves transport security to that hostname—**not** that the hostname is authorized to sign OAuth access tokens for the real issuer.

### 5.3. Verified Against Which Key?

There are two independent questions:

1. Does the signature verify under the public key being used?
2. Does that public key belong to **the issuer authorized by this API to mint tokens**?

If the second question is not answered by an independent trust policy, the first is insufficient. **Verifying a signature with an arbitrary key is barely stronger than checking claims alone** if the attacker gets to pick the key.

## 6. Restrict Signing Algorithms—Do Not Follow the Sender's `alg`

The JWS header declares **`alg`**. The Resource Server must actively **allowlist** accepted algorithms and key types per its issuer contract.

Example policy:

~~~text
Trusted issuer:  https://login.example.com/realms/shop
Trusted JWKS:    https://login.example.com/realms/shop/certs
Accepted JWS:    RS256
~~~

A token claiming **`HS256`**, **`none`**, or anything else must never force the API to switch verification strategies dynamically.

Mistakes to avoid:

| Mistake | Consequence |
|---|---|
| Accepting **`alg = none`** in an API requiring signed JWTs | Allows unsigned tokens |
| Letting JWTs choose any algorithm freely | Opens algorithm confusion attacks |
| Using an RSA public key as an HMAC secret via buggy verification logic | Allows forging tokens without the RSA private key |
| Not constraining key type (`kty`), `alg`, or key-use | Keys can be misused outside their intended purpose |
| Skipping verification when `kid` is missing | Eliminates authenticity guarantees |

Spring Security's **`NimbusJwtDecoder`** lets you pin allowed algorithms and JWKS sources. Configure them to match your real issuer and token profile; never weaken them just to let a malformed token pass.

## 7. Spring Boot Resource Server: `issuer-uri`, `jwk-set-uri`, and `audiences`

A standard JWT Resource Server configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Meaning:

- **`issuer-uri`** pins the trusted issuer, drives discovery, and enforces issuer checks.
- Spring Security retrieves metadata and the issuer's public JWKS to verify signatures.
- **`audiences`** requires tokens to target **`orders-api`**.
- Tokens failing signature, source, or claim checks are rejected.

These addresses are examples. Specific configuration properties vary across Spring Boot / Spring Security versions; use properties supported by your project's version.

### 7.1. Specifying `jwk-set-uri` Directly When Needed

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

**`jwk-set-uri` here is system-governed configuration**, never taken from an unverified token's **`jku`** header.

Keeping **`issuer-uri`** avoids verifying signatures against a key set while forgetting to validate **`iss`**. **`audiences`** remains necessary to distinguish which API a token targets.

### 7.2. Resource Server Dependencies

| Spring Boot | OAuth2 Resource Server Starter |
|---|---|
| **3.x** | **`spring-boot-starter-oauth2-resource-server`** |
| **4.x** | **`spring-boot-starter-security-oauth2-resource-server`** |

The JWT Resource Server uses the Spring Security OAuth2 Resource Server and JOSE modules managed by Spring Boot's dependency BOM. Avoid manually mixing major Spring Security versions.

## 8. `JwtDecoder` Is the JWT Authentication Boundary in Spring Security

In a **Servlet Resource Server**, the typical flow is:

~~~mermaid
flowchart LR
    R[Authorization: Bearer] --> B[BearerTokenAuthenticationFilter]
    B --> P[JwtAuthenticationProvider]
    P --> D[JwtDecoder]
    D -->|Signature/validators error| E[401]
    D -->|Valid| C[JwtAuthenticationConverter]
    C --> A[JwtAuthenticationToken]
    A --> F[Authorize HTTP/method/resource]
    F -->|Insufficient permission| X[403/404]
    F -->|Authorized| O[Controller and service]
~~~

**`JwtDecoder`** is not a plain Base64URL decoder. With a properly configured **`NimbusJwtDecoder`**, it performs cryptographic verification and runs **`OAuth2TokenValidator<Jwt>`**. Only upon successful decoding should Spring Security convert claims into a principal and authorities.

### 8.1. Illustrative `SecurityFilterChain`

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

This is a Servlet/MVC example, not WebFlux. Scope **`orders.read`** on a verified token is mapped by the default converter to **`SCOPE_orders.read`**. Holding this scope **does not grant access to read every order**; service and domain policies must still enforce tenant and ownership rules.

### 8.2. Never Construct `Authentication` From Unverified Claims

A controller that manually Base64URL-decodes a JWT, reads roles, and builds a **`JwtAuthenticationToken`** bypasses the authentication boundary. Class names like **`Jwt`** or **`JwtAuthenticationToken`** do not make sender-crafted data trustworthy.

For real requests, let **`JwtAuthenticationProvider`** invoke a **`JwtDecoder`** configured with trusted keys and validators. Synthetic `Jwt` builders in unit tests are useful for testing rules, never as proof that signature verification took place.

## 9. Custom `NimbusJwtDecoder` Needs Both Signature and Claim Validators

Sometimes an API must explicitly pin signing algorithms or add an audience validator. The example below configures a **trusted JWKS URI**, restricts to **`RS256`**, and checks issuer, timestamps, and audience:

~~~java
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
class JwtDecoderConfig {

    private static final String ISSUER =
        "https://login.example.com/realms/shop";

    private static final String JWKS_URI =
        "https://login.example.com/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Token audience does not include orders-api",
                        null
                    )
                );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(issuerAndTime, audience)
        );
        return decoder;
    }
}
~~~

Role of each setting:

| Configuration | Purpose |
|---|---|
| **`withJwkSetUri`** | Fetches public keys from a trusted source |
| **`jwsAlgorithm(RS256)`** | Accepts only the agreed signing algorithm |
| **`createDefaultWithIssuer`** | Builds default validations including issuer and timestamps |
| **`audience` validator** | Requires the access token to target the Orders API |
| **`DelegatingOAuth2TokenValidator`** | Combines conditions that must all pass simultaneously |
| **`decode`** | Returns an accepted `Jwt` or throws `JwtException` |

When you define a **`@Bean JwtDecoder`**, Spring Boot may stop applying property-configured validators onto your custom decoder. The application is then responsible for preserving **`iss`**, **`aud`**, **`exp`/`nbf`**, algorithms, token type/profile, and all required constraints.

### 9.1. A Custom `JwtDecoder` That Only Parses JSON Is Still Unsafe

~~~java
// PSEUDOCODE ILLUSTRATING A BROKEN PATTERN, not a production class.
class ClaimsOnlyJwtDecoder implements JwtDecoder {

    @Override
    public Jwt decode(String token) {
        Map<String, Object> claims = parseJwtPayloadWithoutSignature(token);

        checkIssuer(claims);
        checkAudience(claims);
        checkExpiration(claims);

        return createJwtWithUntrustedClaims(token, claims);
    }
}
~~~

Function names here are illustrative placeholders. This decoder still accepts self-crafted JWTs whose claims look right, because it never checked the signature or key source. **No number of claim validators can replace verification.**

Never write custom parsers or crypto in production when maintained Spring Security / Nimbus JOSE implementations are available.

### 9.2. Replacing Validators Must Preserve Default Checks

~~~java
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(trustedJwksUri)
    .build();

// WRONG if setting only a custom scope rule drops issuer/time validators.
decoder.setJwtValidator(onlyCustomScopeValidator);
~~~

Here Nimbus may still verify signatures, yet **`iss`** and timestamps may no longer be checked as expected. Compose custom validators with default, issuer, audience, and required token-profile validators.

In short, there are two distinct flaws: **skipping signature verification** and **verifying signatures while skipping claim validation**. Both must be prevented.

## 10. Real JWTs With the Wrong Audience or Wrong Token Type Must Still Be Rejected

A token signed with the issuer's real private key can still be invalid for the Orders API.

Example JWT:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "aud": ["payments-api"],
  "scope": "payments.read",
  "exp": 1893456000
}
~~~

The signature is valid and **`iss`** matches, yet **`aud`** is **`payments-api`**. The Orders API expecting **`orders-api`** must reject it.

Similarly, an **OIDC ID Token** can be a JWT signed by the same OpenID Provider. ID Tokens are meant for OIDC Clients, not automatically valid as access tokens for calling Resource Servers. Always check **`aud`** and token type/profile—such as **RFC 9068** requirements for JWT access tokens when that profile is used.

Claims like **`sub`**, **`email`**, **`email_verified`**, **`openid`**, and **`profile`** help identify users without granting business permissions on their own.

## 11. For Opaque Tokens, Verify Source via Introspection

OAuth2 does not require every access token to be a JWT. An **opaque token** may be an arbitrary string without a JWT structure that the Resource Server can verify locally.

In that model, the Resource Server calls a **trusted configured introspection endpoint** with appropriate client credentials to ask the Authorization Server to validate the token.

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant RS as Resource Server
    participant AS as Trusted Authorization Server
    C->>RS: Authorization: Bearer opaque-token
    RS->>AS: POST introspection over HTTPS with client authentication
    AS-->>RS: active=true and token metadata
    RS->>RS: Validate active, aud/scope, and policies
    RS-->>C: Allow or deny
~~~

Key comparison:

| Signed JWT | Opaque Token |
|---|---|
| Verify signature with keys published by trusted issuer | Call trusted AS introspection endpoint |
| Read JWT claims only after verification | Read token metadata from introspection response |
| Typically uses `JwtDecoder` | Typically uses `OpaqueTokenIntrospector` |
| Never trust unverified Base64URL-decoded JSON | Never trust fake responses from an arbitrary client-specified endpoint |

Example Spring Boot configuration with placeholder secrets:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: example-introspection-client
          client-secret: configure-secret-outside-source-control
~~~

Client identity/secret values are illustrative; **never commit real secrets in source control**. Use a secret manager or secured environment variables, enforce HTTPS, and verify the introspection endpoint's TLS certificate.

An **`active=true`** response is trustworthy only when returned by a **trusted AS over a protected introspection channel**. Just like JWT signatures, a JSON body containing `active` and `scope` means nothing if the source is untrusted.

Some systems emit JWTs yet still use introspection to check live active/revocation status; the core principle is **having an issuer-authorized token verification mechanism**, never trusting raw JSON claims alone.

## 12. Never Substitute Reverse-Proxy Trust for Token Verification

Suppose a backend receives:

~~~http
Authorization: Bearer <access-token>
X-Authenticated-User: admin
X-User-Roles: ADMIN
~~~

If external clients can directly send **`X-Authenticated-User`** or **`X-User-Roles`**, the backend must never treat them as identity proof. Plausible-looking headers are no different from plausible-looking unverified JWT claims.

Two valid architectural choices exist:

**A. Resource Server verifies the token itself:** The API Gateway forwards the access token over a protected link; Spring Security verifies signatures/JWKS or performs introspection normally.

**B. Trusted gateway-delegated authentication:** The gateway verifies the token and passes an internal identity context through an independently secured mechanism; the backend blocks direct access, authenticates connections from the gateway, and trusts only internal headers/claims overwritten by the gateway per policy. Document the trust boundary clearly and enforce business authorization in the backend.

**A token arriving over HTTPS or a private network is not automatically valid.** HTTPS prevents eavesdropping in transit; it does not prove a JWT payload was minted by a trusted issuer.

## 13. Distinguishing HTTP 401 and 403

Common cases in a Bearer Resource Server:

| Case | Primary Failure | Typical HTTP Status |
|---|---|---|
| Missing Bearer token | Unauthenticated | **401** |
| Malformed JWT structure | Parse failure | **401** |
| Valid-looking claims, invalid signature | Authentication failure | **401** |
| JWT signed with attacker key claiming real issuer | Untrusted key source | **401** |
| Valid signature, wrong issuer | Claim validation | **401** |
| Valid signature, wrong audience | Claim validation | **401** |
| Token expired or before `nbf` | Claim validation | **401** |
| Valid token lacking **`orders.read`** | Authorization | **403** |
| Valid token with scope, order belongs to another tenant | Resource authorization | **403** or **404** per policy |
| Valid token, scope, and data permissions | Passed authentication/authorization | API proceeds; typically **200** |

In Bearer APIs, `401` usually includes **`WWW-Authenticate: Bearer`**. Exact responses depend on exception handling configuration.

Never fix a `401` from a forged JWT by disabling signature verification. Never fix a `401` from a wrong audience by removing the audience validator. Never fix a `403` from missing permissions by opening the endpoint with **`permitAll()`**.

## 14. Tests Must Separate Mocked Claims From Real Verification

Spring Security Test offers the **`jwt()` request post-processor** for Servlet tests. It is convenient for mocking `Authentication` and testing web/method authorization, yet in normal usage **it does not invoke the real `JwtDecoder` to verify signatures**.

Example:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@Test
void allowsReadScope() throws Exception {
    mockMvc.perform(get("/api/orders/42")
            .with(jwt().authorities(() -> "SCOPE_orders.read")))
        .andExpect(status().isOk());
}
~~~

This abbreviated test assumes `mockMvc`, controller, and fixtures return `200`. It tests **`SCOPE_orders.read`**, yet **does not prove the API rejects forged signatures**.

To test the token-verification boundary properly, maintain distinct test layers:

1. **Authorization tests** with mock principals/authorities for scopes, roles, tenants, and ownership.
2. **`JwtDecoder` tests** using JWTs signed by a test issuer's private key alongside tampered/forged JWTs.
3. **HTTP integration tests** sending real Bearer tokens through the security filter chain against a test-trusted issuer/JWKS.
4. **Operational tests** verifying TLS, JWKS caching, key rotation, introspection endpoints, and fail-closed behavior.

Conceptual `JwtDecoder` test:

~~~java
// Pseudocode: test fixtures supply tokens and test public key/JWKS.
Jwt jwt = jwtDecoder.decode(validSignedToken);

assertThrows(JwtException.class,
    () -> jwtDecoder.decode(tamperedPayloadToken));

assertThrows(JwtException.class,
    () -> jwtDecoder.decode(attackerSignedToken));

assertThrows(JwtException.class,
    () -> jwtDecoder.decode(wrongAudienceToken));
~~~

Here **`validSignedToken`** is signed by the test issuer's private key; **`tamperedPayloadToken`** has a modified payload without re-signing; **`attackerSignedToken`** uses a key outside the trusted set; **`wrongAudienceToken`** has a valid signature yet the wrong `aud`. Wire tests to the real `JwtDecoder` and validators.

### 14.1. An Especially Useful Test Case: Valid Claims, Invalid Signature

Craft a forged JWT with payload:

~~~json
{
  "iss": "https://login.example.com/realms/shop",
  "sub": "admin",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 4102444800
}
~~~

This JWT must be **rejected** if its signature does not match a key authorized by the trusted issuer. This single test catches the "claims-only check" flaw immediately.

Never commit real access tokens or production private signing keys into repositories or test fixtures. Use dedicated test keys and test tokens only.

## 15. Common Design Mistakes

### 15.1. Parsing JWTs Directly in a Controller

The controller reads **`Authorization`**, splits the token, decodes the payload, and makes role/scope decisions. This bypasses `JwtAuthenticationProvider` and `JwtDecoder`. Let Spring Security authenticate the access token first and inspect the established `Authentication`.

### 15.2. Custom `JwtDecoder` That Only Constructs `Jwt` From JSON

If a custom `JwtDecoder` merely parses JSON and checks a few claims, it satisfies the interface name while breaking the trust boundary. Never construct a `Jwt` from unverified input as authentication proof.

### 15.3. Verifying Signatures With a Token-Supplied Key

**`jku`**, **`jwk`**, **`x5u`**, or a URL built from **`kid`** must never replace your trusted JWKS. A signature matching an attacker's key proves nothing about a legitimate issuer.

### 15.4. Dropping Issuer or Audience Validators After Signature Verification

A JWT validly signed by the issuer with **`aud = payments-api`** must never be accepted by the Orders API. Likewise, a token from an unauthorized issuer must be rejected even if its other claims look right.

### 15.5. Skipping Expiration Because the Signature Is Valid

A valid signature persists after **`exp`**. Timestamps, appropriate clock skew, and revocation policies are independent of signature verification.

### 15.6. Using an ID Token as an Access Token

OIDC ID Tokens exist for clients verifying login; they are not default authorization tokens for APIs. Require proper audience, token type, and profile. Sharing the same issuer or JWKS does not make the two token types interchangeable.

### 15.7. Skipping Verification Because Traffic Came Through a Gateway

Skip backend token verification only when you have designed and verified an explicit trust-delegation boundary. Never grant `Authentication` based on private IPs, forwarded headers, or upstream hostnames alone.

### 15.8. Falling Back to Claims When JWKS Fails

If the Resource Server cannot verify tokens using trusted keys, never fall back to "parse and trust temporarily". Use proper caching and key-rotation handling while staying **fail-closed** whenever verification proof is unavailable.

### 15.9. Logging Raw Bearer Tokens

Bearer tokens can be replayed while valid. Never log raw JWTs, `Authorization` headers, refresh tokens, ID Tokens, or introspection client secrets. Log request IDs, general error codes, and non-sensitive metadata per policy.

## 16. Step-by-Step Analysis of a Bearer Token Request

Suppose the Orders API declares:

~~~text
Issuer:       https://login.example.com/realms/shop
Trusted JWKS: https://login.example.com/realms/shop/certs
Allowed alg:  RS256
Audience:     orders-api
Scope read:   orders.read
Scope write:  orders.write
Data policy:  operate only on orders within the authorized tenant
~~~

A **`POST /api/orders/42/approve`** request proceeds through these steps:

**Step 1 — Receive Bearer token.** The presence of an `Authorization` header proves nothing about token validity.

**Step 2 — Parse JOSE/JWT structure.** Initial headers and claims are untrusted raw data.

**Step 3 — Select key source.** The decoder looks up public keys strictly from the trusted JWKS/issuer, never accepting keys chosen by the token.

**Step 4 — Verify signature.** If the token was tampered with or signed by an untrusted key, return `401`.

**Step 5 — Validate claims.** Check issuer, audience, `exp`, `nbf`, and token type/profile. A validly signed token for another API still returns `401`.

**Step 6 — Build `Authentication`.** Construct the principal and authorities exclusively from claims accepted by the decoder.

**Step 7 — Authorization.** Enforce the scope required to approve, then check whether the order belongs to the authorized tenant/owner and is in a valid business state.

**Step 8 — Execute business logic.** Modify data only after all layers above pass.

This workflow keeps four boundaries crisp: **read data → verify source/signature → validate claims → authorize action**.

## 17. Questions to Ask When Reviewing a Resource Server

1. Is the token **JWT/JWS**, **JWE**, or **opaque**? Which verification mechanism genuinely fits?
2. Do trusted issuers come from **configuration/allowlists** or from arbitrary **`iss`** values inside incoming tokens?
3. Are public keys fetched from a **trusted JWKS URI** or from token-supplied **`jku`/`jwk`/`x5u`**?
4. How does the API restrict accepted **`alg`** values and key types?
5. Does **`JwtDecoder`** truly verify signatures, or does a custom implementation only parse JSON?
6. Do validators enforce **`iss`**, **`aud`**, **`exp`**, **`nbf`**, and token type/profile?
7. Did a custom decoder accidentally overwrite or drop default validators?
8. Are opaque tokens introspected through a **trusted endpoint**, and is **`active`** properly checked?
9. Are scopes, roles, and permissions read from a **verified `Authentication`**?
10. Where are tenant, owner, membership, and record-state permissions enforced?
11. Do tests include JWTs with **valid-looking claims and forged signatures**?
12. When JWKS or introspection is unavailable, does the system reject unverified tokens?
13. Are there any token leaks in logs or blind trust in client-supplied proxy headers?

## Conclusion

**Claim validation can never replace signature or token-source verification.** The **`iss`** claim is merely a string asserted by the token. The **`aud`** claim states who the token claims as recipient. The **`exp`** claim states a payload expiration timestamp. The **`scope`** claim describes permissions written in the token. **None of those claims proves the Authorization Server actually issued the token.**

For **JWT/JWS**, a Spring Security Resource Server needs a trusted issuer/JWKS, allowed algorithms, signature verification via **`JwtDecoder`**, and only then claim validation and authorization. For **opaque tokens**, it needs introspection results from a trusted Authorization Server rather than arbitrary JSON. Even a verified token must still pass audience, expiration, token-type, and resource-level business authorization checks.

### References

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security API — JwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html)
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
