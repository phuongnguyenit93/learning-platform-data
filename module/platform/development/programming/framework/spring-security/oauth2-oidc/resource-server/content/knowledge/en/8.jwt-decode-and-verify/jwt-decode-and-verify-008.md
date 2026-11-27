# Unsigned, Invalidly Signed, or Unexpectedly Formatted Tokens

## 1. Why must a Resource Server reject these tokens?

In **Spring Security OAuth 2.0/OIDC Resource Server**, HTTP clients typically send an access token as a Bearer credential:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
```

If an API is configured to accept **JWS-signed JWT access tokens**, the token string must satisfy multiple independent conditions:

1. Be presented in the **format** expected by the Resource Server.
2. Use an **accepted signature algorithm** and a verification key from a trusted source.
3. Carry a **valid signature** over the exact issued data.
4. Carry **valid claims**, such as issuer, audience, lifetime, and matching token type.
5. Possess the **access permissions** required by the endpoint.

An unsigned token, a token with an invalid signature, or a token in an unexpected format must be rejected **before the application relies on its claims to authenticate or grant permissions**. Merely reading the JSON payload, seeing `sub` or `scope`, or recognizing that a string “looks like a JWT” never proves the token is trustworthy.

Three closely related yet distinct failure categories:

| Category | Nature | Example | Outcome for a JWT Resource Server requiring valid JWS |
| --- | --- | --- | --- |
| **Unsigned** | Lacks required cryptographic proof protecting the content. | Unsecured JWT with `alg: none`; JWS claiming `RS256` with an empty signature segment. | Reject. |
| **Invalid signature** | Has a signature field, but verification fails. | Payload tampered with; token signed by a different key; mismatched public key. | Reject. |
| **Unexpected format** | Token cannot be processed by the parser/decoder for the configured token type. | Opaque token passed to a JWT decoder; five-part JWE; invalid Base64URL/JSON string. | Reject or route to the **appropriate mechanism** if the API intentionally supports that token format. |

> **Scope:** This lesson focuses on JWS-protected JWTs and how Spring Security Servlet Resource Server handles them. Example tokens illustrate structure only and contain no usable credentials. **OIDC ID tokens** and **OAuth 2.0 access tokens** may both be JWTs, yet their purposes are not interchangeable: an API must accept an access token meant for that Resource Server itself.

## 2. Recognizing JWS Compact and understanding what the signature protects

Commonly signed JWTs use **JWS Compact Serialization**, consisting of three dot-separated segments:

```text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
```

Illustrative structure example:

```text
eyJhbGciOiJSUzI1NiIsImtpZCI6ImtleS0xIn0.
eyJpc3MiOiJodHRwczovL2xvZ2luLmV4YW1wbGUudGVzdCJ9.
<base64url-encoded-signature>
```

In real wire protocol usage, everything sits on **one line**, without line breaks or angle-bracket placeholders. The protected header might decode to:

```json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "key-1"
}
```

Illustrative payload:

```json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders:read",
  "iat": 1893452400,
  "exp": 1893456000
}
```

The signature protects the **signing input** string:

```text
signingInput =
  BASE64URL(protected-header) + "." + BASE64URL(payload)
```

For an asymmetric algorithm like `RS256`:

```text
signature = SIGN(issuerPrivateKey, signingInput)
valid     = VERIFY(issuerPublicKey, signingInput, signature)
```

For a symmetric algorithm like `HS256`, both signing and verification use the **same HMAC secret key**, not a private/public key pair:

```text
signature = HMAC-SHA256(sharedSecret, signingInput)
valid     = VERIFY_MAC(sharedSecret, signingInput, signature)
```

**Do not confuse Base64URL with cryptography:** Header and payload can be decoded to read their contents without any key. You must verify **the signature over the exact received header and payload** before treating claims as trustworthy data.

### 2.1. Trusted token-processing flow

```mermaid
flowchart TD
    R["HTTP request with Bearer token"] --> X{"Token accepted by Bearer resolver?"}
    X -- "No" --> E1["Credential transport error or missing token"]
    X -- "Yes" --> P{"Parser recognizes valid JWS Compact?"}
    P -- "No" --> E2["Reject: malformed / unexpected format"]
    P -- "Yes" --> A{"Algorithm + key allowed?"}
    A -- "No" --> E3["Reject: disallowed alg/key"]
    A -- "Yes" --> S{"Signature verification succeeds?"}
    S -- "No" --> E4["Reject: signature invalid"]
    S -- "Yes" --> C{"Claims and token profile valid?"}
    C -- "No" --> E5["Reject: issuer/audience/time/type..."]
    C -- "Yes" --> Z["Create Authentication"]
    Z --> O{"Endpoint permission satisfied?"}
    O -- "No" --> E6["403 or access denied"]
    O -- "Yes" --> OK["Allow to business logic"]
```

This is a **conceptual** diagram: a JOSE library may combine or order certain parser/validator operations differently. What matters is **never using unverified claims to make access decisions**.

## 3. Case 1: unsigned tokens

### 3.1. JWT with `alg: none`

The JWT/JWS standard defines an **Unsecured JWT**: the protected header specifies algorithm `none` and the signature is an empty string. For example:

```text
eyJhbGciOiJub25lIn0.eyJzdWIiOiJhbGljZSJ9.
```

Decoding the header and payload:

```json
{ "alg": "none" }
```

```json
{ "sub": "alice" }
```

A JWT in this form has **no cryptographic authentication** of its content. The specification includes unsecured JWT representation for contexts protected by some external mechanism, but an OAuth 2.0 Resource Server configured to **require signed JWT access tokens** must **reject `alg: none`**. Never allow `none` just to avoid managing keys.

If any client can craft:

```json
{
  "sub": "admin",
  "scope": "orders:write"
}
```

and the API accepts an unsigned payload as an authenticated user/permission, an attacker can assign themselves arbitrary roles or scopes. That is a severe flaw at the **token authentication boundary**.

### 3.2. Header declares a signing algorithm, yet the signature is missing

Example string pattern:

```text
BASE64URL({"alg":"RS256"}).BASE64URL({"sub":"user-123"}).
```

This example uses symbolic notation for readability, **not a real Base64URL string**. The header claims `RS256`, yet the signature segment is empty. The token cannot pass RSA signature verification under a JWT Resource Server's policy.

Do not confuse an **empty signature of an unsecured JWT** with an **empty signature in a token claiming a signed algorithm**:

- `alg: none` is a separately defined unsigned JWS form that **must not be accepted** in APIs requiring signed JWS.
- `alg: RS256`, `PS256`, `ES256`, `HS256`, etc., without the required signature are simply **invalid**.

### 3.3. Why should there never be a “skip-verification mode”?

Some JWT tutorials online merely Base64URL-decode the payload or call a parser in **unverified** mode to print claims. That can be handy when **inspecting formats in a test environment**, yet it is not authentication.

Never write:

```java
// WRONG: no signature / issuer / audience verification step.
String[] pieces = bearerToken.split("\\.");
String payloadJson = new String(
        Base64.getUrlDecoder().decode(pieces[1]),
        StandardCharsets.UTF_8);
// Trusting "scope", "sub" in payloadJson to grant access: UNSAFE.
```

An attacker-crafted token can contain completely valid-looking JSON. **The mere presence of a claim does not prove the issuer granted that permission.** In Spring Security Resource Server, let `JwtDecoder` verify the token before building a principal and authorities.

## 4. Case 2: signature present, yet verification fails

This is when the token has all three segments, yet the signature fails verification under the trusted key and algorithm.

### 4.1. Payload modified after signing

Suppose the issuer emits an access token with:

```json
{ "scope": "orders:read" }
```

A client or attacker changes the payload to:

```json
{ "scope": "orders:write" }
```

If only the Base64URL(payload) segment is replaced while keeping the old signature, the signing input changes and the signature **no longer matches**. A properly verifying JWS API must reject the token before treating `orders:write` as a privilege.

Similarly, altering `iss`, `aud`, `sub`, or `exp` in the payload also changes the signing input. You cannot extend a token's lifetime by editing `exp` and keeping the original signature.

### 4.2. Token signed with a non-matching key

For example, the issuer signs with private key A, while the Resource Server checks with public key B. If A and B are not from the same key pair, signature verification fails. Causes may include:

- The API is configured with the wrong issuer or JWKS URL.
- The Authorization Server **rotated keys**, yet the new public key has not been fetched/updated by the Resource Server.
- The token was issued using a test key or a different key pair.
- Both sides use keys with the same name/ID that are actually two different key materials.
- The client sent a token from another environment, such as a staging token to a production API.

**Do not work around this by disabling signature verification.** Locate the exact issuer, key ID, and key source.

### 4.3. Algorithm and key type mismatch

For example, the token declares `alg: HS256` while the Resource Server trusts only `RS256`-signed JWTs. Those two algorithms have completely different key models:

| JWS `alg` | Material used by issuer to sign | Material needed by Resource Server to verify |
| --- | --- | --- |
| `HS256` | Shared HMAC secret key. | **The exact same HMAC secret**. |
| `RS256` | RSA private key. | Matching RSA public key. |
| `PS256` | RSA private key with RSASSA-PSS. | Matching RSA public key, matching PSS parameters/profile. |
| `ES256` | EC P-256 private key. | Matching EC P-256 public key. |
| `EdDSA` | Private key in a supported EdDSA profile. | Matching EdDSA public key. |
| `none` | No signature. | **Rejected** when the contract requires signed access tokens. |

The token declares `alg` in its header. **That is unverified input**; the Resource Server must enforce an **allowed-algorithm policy on the server side**. Never infer an arbitrary algorithm from the token string and dynamically switch verification mechanisms to match it.

An **algorithm confusion** flaw historically seen in custom verifiers is accepting a JWT claiming `HS256` while feeding the RSA public key as the HMAC secret. Because the public key is public, an attacker can forge a valid MAC if the verifier uses the wrong key type. Use a trusted JOSE library and strictly bind algorithms to the right key type.

### 4.4. Validly signed JWT sent to the wrong Resource Server

For instance, the issuer emits a properly signed JWT, yet `aud` is `payments-api` while the API expects tokens meant for `orders-api`. Here:

- **The signature may be completely valid.**
- **Claim validation fails** because the token is not directed at this Resource Server.

Do not label every 401 response “invalid signature”. An invalid signature and an invalid claim may both be reported to clients as `invalid_token`, yet they require different troubleshooting paths.

## 5. Case 3: token not in the expected format

A Resource Server must know which credential type it handles. An API configured for JWT expects a **JWS/JWT with a valid structure and header**, whereas an API using opaque tokens has its own introspection mechanism.

### 5.1. Common structural errors

| Input example | Problem | Accurate interpretation |
| --- | --- | --- |
| `abc.def` | Only two segments. | Lacks the three segments required for JWS Compact. |
| `abc.def.ghi.jkl` | Four segments. | Matches neither three-part JWS Compact nor five-part JWE Compact. |
| `abc.def.ghi` | Has three segments, yet may not be a JWT. | **Segment count alone is insufficient**: valid Base64URL, valid JSON, JOSE header, signature, and proper claims are required. |
| `abc.def.ghi.jkl.mno` | Five segments. | May be **JWE Compact**, not a three-part JWS; requires a dedicated JWE decryption mechanism if supported. |
| `randomOpaqueToken123` | No JWS structure. | May be an opaque access token; must be introspected per provider contract rather than JWT-decoded. |
| String contains characters disallowed in Base64URL | Decoding/parsing fails. | Cannot be treated as a valid JWT. |
| Header/payload decodes, yet is not valid JSON | Does not satisfy JSON structure/profile. | Reject at parser/decoder. |
| JSON header omits `alg` when signing is required | Cannot determine required JWS algorithm. | Reject; never guess an algorithm from the payload. |
| Header declares `alg: none` while API accepts signed JWTs only | Lacks signature protection per policy. | Reject. |
| Signature missing or truncated | Cannot verify signature properly. | Reject. |

A standard signed JWT must have **two dots** separating three segments, yet you should never write a rule saying “if it has two dots, it is valid”. The JOSE library itself must parse and verify format, algorithm, key, and signature.

### 5.2. Opaque access token sent to a JWT decoder

An Authorization Server may issue an access token like:

```text
Xg32sAj4hQ9m...opaque-value...
```

A Resource Server configured with `oauth2ResourceServer().jwt()` will attempt to process it as a JWT/JWS and typically reject it as malformed. **An opaque token is not “broken” just because it is not a JWT**: it may be a completely valid credential for the Authorization Server, requiring **token introspection** or an appropriate verification mechanism.

In Spring Boot Resource Server, two typical configuration styles:

**JWT access token:**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
```

**Opaque access token:**

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.test/oauth2/introspect
          client-id: resource-server
          client-secret: replace-with-secure-secret
```

These are **two illustrative configuration options**, not two blocks always placed side by side expecting Spring to guess the token type automatically. Introspection credentials must be loaded from a secret manager or secure environment in real operations.

When both formats must be supported in the same system, explicitly define the **authentication flow and trust boundary**: separate Resource Servers/endpoints/filter chains or design a trusted `AuthenticationManagerResolver`/routing mechanism. Do not simply drop both a JWT provider and an opaque provider into one `ProviderManager` and assume fallback ordering is safe.

### 5.3. JWT encrypted with JWE

A JWT can be protected using **JWE (JSON Web Encryption)**. JWE Compact normally has **five parts**, unlike three-part JWS Compact:

```text
protected-header.encrypted-key.iv.ciphertext.authentication-tag
```

An API with only a **JWT signature decoder** will not automatically understand a five-part JWE token, even if the JWE is valid in its issuing context. If encrypted JWTs are required, implement JWE decryption support with appropriate keys/rules and enforce protection, issuer, audience, and claim checks per contract. If the system uses **nested JWTs**, process signing/encryption in the proper order and validate each layer per profile.

**Never switch to manual string decoding** or bypass protection layers just to “extract the payload”. Moving between JWS and JWE is a major change to the access token contract.

### 5.4. Accidentally passing the `Bearer` prefix to the decoder

Valid HTTP header:

```http
Authorization: Bearer eyJ...signed.jwt...
```

`JwtDecoder` receives the extracted **token string**, not the full `"Bearer eyJ..."` string. In Spring Security, `BearerTokenAuthenticationFilter` and `BearerTokenResolver` normally strip the scheme. If custom code passes the entire header directly to the decoder, the parser will report a malformed token.

This is why you should use the built-in Resource Server mechanism instead of manually parsing the `Authorization` header inside controllers.

### 5.5. Valid JSON does not guarantee the right token profile

A token can be a valid JWS, properly signed by the issuer, yet not be **the kind of access token the API accepts**:

- An **OIDC ID token** has the OIDC client ID as `aud`, not the resource API.
- An access token meant for another resource has a different `aud`.
- A JWT carries a permission claim of the wrong type or omits a required claim.
- A token has a `typ` or claims failing the agreed profile, such as a system enforcing the JWT Access Token Profile.

Here the JOSE formatting may be valid, yet the **token contract** fails. The system must distinguish **parsing errors**, **signature errors**, **claim errors**, and **authorization errors**.

## 6. Checking `alg`, `kid`, and JWKS properly

A typical JWS protected header:

```json
{
  "alg": "RS256",
  "typ": "at+jwt",
  "kid": "rsa-2026-02"
}
```

`typ: at+jwt` follows the **OAuth 2.0 JWT Access Token Profile** style; not every JWT access token from every issuer carries this `typ` value. Enforcing `typ` must align with the published issuer profile/contract.

To verify a JWS, the Resource Server needs:

1. An allowlist of **trusted issuers** and **allowed algorithms**.
2. To fetch the **JWKS from a configured endpoint or trusted discovery**, never from an arbitrary URL dictated by the token.
3. To use `kid` (if present) as a **key-lookup hint** within the matching issuer's key set, alongside key-type and algorithm checks.
4. To verify the signature with the corresponding public key (or shared secret if an HMAC model was intentionally designed).
5. Then to enforce issuer, audience, lifetime, token profile, and permissions.

`kid` is not a trust certificate and does not by itself prove the issuer emitted the token. An attacker can craft an arbitrary header with `kid: "admin"` or `jku: "https://attacker.example/keys"`. The Resource Server must never use `kid` as an arbitrary filename/path or fetch `jku`/`x5u` from an unverified token without strict source controls.

### 6.1. Behavior after key rotation

Suppose the issuer signed older tokens with private key A and signs new tokens with private key B. The JWKS publishes public keys A and B during a transition window:

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant JWKS as Trusted JWKS
    participant API as Resource Server
    AS->>JWKS: Publish public key B alongside A
    AS-->>API: New JWT (kid=B), signed with private key B
    API->>JWKS: Fetch/refresh public keys per cache policy
    JWKS-->>API: Public keys A and B
    API->>API: Select B and verify signature
    API->>API: Check claims/permissions
```

If the API has not yet fetched key B due to caching, networking, or the issuer failing to publish the updated JWKS in time, new tokens can be rejected even though the issuer signed them validly. Fix this by synchronizing key rotation, caching, and JWKS configuration. Never accept an unverified signature automatically just because the header carries a new `kid`.

Conversely, removing public key A too early can cause **unexpired** older tokens to be rejected. A rotation plan must account for access token lifetimes, cache TTLs, clock skew, and propagation delays.

### 6.2. Verification keys vs. signing keys

| Algorithm | Issuer signs with | Resource Server verifies with | Safe to publish verification material? |
| --- | --- | --- | --- |
| `RS256` / `PS256` | RSA private key | RSA public key | Yes, once bound to a trusted issuer. |
| `ES256` | EC private key | EC public key | Yes, once bound to a trusted issuer. |
| `HS256` | Shared HMAC secret | Same shared HMAC secret | **No**, because knowing the secret enables creating MACs. |

If the API verifies `RS256`, it **does not need the Authorization Server's private key**. If the API verifies `HS256`, it holds the secret key and signing capability is cryptographically inseparable from verification capability. Never publish HMAC secrets in a public JWKS.

## 7. How Spring Security handles invalid tokens in Servlet Resource Server

A minimal API configuration:

```java
@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/public/**").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders:read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

With a JWT Resource Server, the typical flow is:

```mermaid
sequenceDiagram
    participant C as Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as JwtAuthenticationProvider
    participant D as JwtDecoder
    participant A as AuthorizationFilter
    C->>F: Authorization: Bearer <token>
    F->>F: Extract Bearer credential
    F->>M: authenticate(BearerTokenAuthenticationToken)
    M->>P: Route to appropriate JWT provider
    P->>D: decode(token)
    alt Malformed, alg none, wrong signature, invalid claims
        D-->>P: JwtException / validation failure
        P-->>F: AuthenticationException
        F-->>C: 401 and WWW-Authenticate Bearer
    else Verified JWT
        D-->>P: Jwt
        P-->>F: Authenticated Authentication
        F->>A: SecurityContext
        A-->>C: Allow or 403 per permissions
    end
```

`BearerTokenAuthenticationFilter` is not the JWT decoder. It extracts the credential and invokes `AuthenticationManager`. `JwtAuthenticationProvider` uses `JwtDecoder` to parse, verify, and validate the JWT. On failure, Spring Security translates the authentication error into the corresponding Bearer response.

### 7.1. Explicit decoder and validator configuration

Example API accepting only `RS256`-signed JWTs from one issuer, audience `orders-api`:

```java
@Configuration
class JwtDecoderConfig {

    private static final String ISSUER =
            "https://login.example.test/realms/demo";
    private static final String JWKS =
            "https://login.example.test/realms/demo/protocol/openid-connect/certs";
    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(JWKS)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Token audience is not this API",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        issuerAndTime, audience));

        return decoder;
    }
}
```

This example uses APIs such as `NimbusJwtDecoder`, `SignatureAlgorithm`, `JwtValidators`, `OAuth2TokenValidator`, `OAuth2TokenValidatorResult`, `DelegatingOAuth2TokenValidator`, and `OAuth2Error`. Imports are omitted; verify exact packages/builders against your Spring Security version. The JWKS URL is a **provider-style example**; obtain the exact path from trusted issuer metadata/contract. If a custom `JwtDecoder` bean is defined, Boot's auto-configuration may no longer control the decoder; explicitly manage the active bean.

Key points:

- `withJwkSetUri(...)` points to a **trusted verification key source**; never derive it from an unverified token.
- `jwsAlgorithm(SignatureAlgorithm.RS256)` pins the accepted algorithm in this example.
- `JwtValidators.createDefaultWithIssuer(...)` includes default validators alongside issuer validation—not signature verification alone.
- The audience validator accepts only tokens whose `aud` targets `orders-api`.
- After the decoder succeeds, authorization must still check `SCOPE_orders:read` and data conditions.

Never remove the audience validator to fix a 401 caused by a validly signed ID token. An OIDC ID token is issued for the client and does not replace an access token for calling a resource API.

### 7.2. If using HMAC `HS256`

If the token contract truly requires `HS256`, the decoder needs a sufficiently strong **shared secret** instead of a JWKS of RSA public keys:

```java
@Bean
JwtDecoder hmacJwtDecoder(SecretKey sharedSecret) {
    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withSecretKey(sharedSecret)
                    .macAlgorithm(MacAlgorithm.HS256)
                    .build();

    decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(
                    "https://issuer.example.test"));
    return decoder;
}
```

This is an **alternative** to an asymmetric JWT decoder—do not register both decoder beans simultaneously as standalone beans without an explicit selection mechanism. The shared secret must be randomly generated with sufficient strength, protected by a secret manager, and granted least-privilege access. The HMAC example also needs its own **audience validator** if required by the API, just like section 7.1; do not check only the issuer.

### 7.3. When to use JwtDecoder vs. introspection?

| What the Authorization Server issues | Mechanism Resource Server typically uses |
| --- | --- |
| JWS-signed JWT access token with matching JWKS/public keys or HMAC secret | `JwtDecoder` and validators. |
| Opaque access token | `OpaqueTokenIntrospector` / token introspection. |
| Encrypted JWT (JWE) | JWE decryptor designed/approved per contract; not a default JWT signature decoder. |
| OIDC ID token | Verified by OIDC Client to handle login; **not** an API Bearer access token. |

A token string not in JWT format **does not automatically mean a forged token**; it may be a valid token sent to the wrong kind of Resource Server. In all cases, an API must never accept a token without a verification mechanism matching its contract.

## 8. 401, 400, and 403 errors: do not conflate them

Per OAuth 2.0 Bearer Token Usage, responses differ by stage:

| Scenario | Typical outcome | Typical `WWW-Authenticate` |
| --- | --- | --- |
| No Bearer credential sent to a protected endpoint | **401 Unauthorized** | `Bearer`, usually without `error`. |
| JWT present with `alg: none` when API requires signing | **401 Unauthorized** | `Bearer error="invalid_token"`. |
| JWT present with invalid/expired signature | **401 Unauthorized** | `Bearer error="invalid_token"`. |
| Bearer token present, yet JWT decoder cannot parse it | **401 Unauthorized** | `Bearer error="invalid_token"`. |
| Malformed Bearer transport syntax or multiple disallowed token methods | Usually **400 Bad Request** | `Bearer error="invalid_request"`. |
| Verified access token lacking endpoint scope | **403 Forbidden** | May include `Bearer error="insufficient_scope"`. |

Example for an invalidly signed token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

The server may add a description:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token", error_description="The token is invalid"
```

`error_description` is optional and clients should not depend on its exact wording. Returning details like “signature mismatch”, “unknown key ID”, or “issuer X not trusted” externally can leak security information. APIs typically return generic error codes while recording technical details in controlled internal logs.

**Regarding `permitAll()`:** Within the same `SecurityFilterChain`, a public endpoint may allow requests **without a token** yet still return 401 when a client **sends a broken Bearer token**: the Bearer filter can reject the credential before authorization runs. `permitAll()` does not automatically disable the authentication filter.

## 9. Separating parser, signature, claim, and authorization failures

In real operations, keep **four layers of responsibility** in mind:

| Layer | Examples | How to handle |
| --- | --- | --- |
| **Parsing/format** | Two-part string, malformed payload JSON, JWE token sent to JWS decoder. | Cannot construct a JWT in a permitted format; reject credential. |
| **Signature/JOSE** | `alg: none`, disallowed algorithm, `kid` key not found, signature mismatch. | Cannot verify origin/integrity; reject. |
| **Claim/profile validation** | Wrong `iss`, `aud` for another resource, expired `exp`, ID token instead of access token. | Signature may be valid, yet token is still unacceptable. |
| **Authorization** | Verified token lacking `orders:write` or tenant permission. | Usually 403 or denial per data policy. |

Spring Security Resource Server may collapse many errors from the first three layers into `AuthenticationException` and respond with HTTP `401 invalid_token`. To diagnose root causes, inspect the **appropriate exception source** in a controlled environment without exposing tokens.

### 9.1. Common exceptions in the Spring ecosystem

| Exception type | Meaning hint |
| --- | --- |
| `JwtException` | Family of JWT decoder/validation errors. |
| `BadJwtException` | Rejected JWT due to structure, signature, or other invalid-JWT cause. |
| `JwtValidationException` | Claim validators rejected the token; usually carries `OAuth2Error` details explaining validation failures. |
| `OAuth2AuthenticationException` | Failure during OAuth 2.0/Bearer authentication. |
| `BearerTokenError` | Carries Bearer error details such as `invalid_token` or `invalid_request` at its layer. |

Do not write business logic against exact exception message text from JOSE libraries; messages can change across versions. Classify based on **processing stage, exception type, and standardized error codes**, alongside controlled internal logs.

## 10. HTTP examples to distinguish failure modes

The following requests assume:

- The API is configured as a JWT Resource Server.
- Trusted issuer is `https://login.example.test`.
- Required audience is `orders-api`.
- Only `RS256` is permitted in these examples.
- Endpoint `GET /api/orders` requires `SCOPE_orders:read`.

### Scenario A: no token sent

```bash
curl -i https://api.example.test/api/orders
```

Response is typically `401` with a Bearer challenge lacking `invalid_token`:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

### Scenario B: unsigned token sent

```bash
curl -i \
  -H 'Authorization: Bearer eyJhbGciOiJub25lIn0.eyJzdWIiOiJhbGljZSJ9.' \
  https://api.example.test/api/orders
```

The example token has `alg: none`; the API requires `RS256` and must reject it, typically `401 invalid_token`.

### Scenario C: string is not an expected JWT/JWS

```bash
curl -i \
  -H 'Authorization: Bearer not-a-jws' \
  https://api.example.test/api/orders
```

When the Bearer resolver extracts the credential and passes it to the JWT decoder, it cannot decode into an accepted JWS/JWT. Typical result is `401 invalid_token`. If the request violates syntax at the **Bearer token transport level**, the error type may differ.

### Scenario D: validly signed token, wrong audience

The client sends a valid `RS256` JWT from the trusted issuer, yet `aud: ["payments-api"]`. Signature passes, audience validator fails → **401 invalid_token**. Never accept a token merely because the decoder loaded the right JWKS.

### Scenario E: right access token, missing scope

Valid `RS256` JWT with `aud: ["orders-api"]`, yet scope is only `orders:read`; the client calls `POST /api/orders`, which requires `orders:write`. Authentication succeeds, then authorization denies → typically **403 insufficient_scope**. Changing the JWT decoder will not grant extra permissions to the token.

### Scenario F: client sends an ID token

A client logs in via OIDC and sends `id_token` instead of `access_token` to the API. The ID token may be signed with the same JWKS, yet `aud` is usually the OIDC client ID. The API must reject it if audience/token profile does not match. The client must acquire a **resource-scoped access token**, rather than weakening validation to accept ID tokens.

## 11. Testing what you actually mean to test

A parser test and a security endpoint test exercise different layers. For a JWT Resource Server, test scenarios can be organized as follows:

| Test | Input | Expectation |
| --- | --- | --- |
| Unsigned token | JWS with `alg: none`, empty signature. | Reject authentication. |
| Empty signature | Header declares `RS256` with missing signature. | Reject authentication. |
| Tampered payload | Validly signed `RS256` token with modified payload and old signature. | Reject signature. |
| Tampered header | Modify `alg` or `kid` after signing without re-signing. | Reject via algorithm/key/signature validation. |
| Wrong public key | Token signed with private key A, API holds only public key B. | Reject signature. |
| Unexpected algorithm | API allows `RS256`, token signed with `HS256` or `ES256`. | Reject per allowlist. |
| Malformed compact token | Missing dots, invalid Base64URL, or invalid JSON. | Reject at parser/decoder. |
| Opaque token sent to JWT decoder | Opaque token from issuer. | Reject at JWT decoder; if opaque is supported, handle in dedicated introspection flow. |
| JWE sent to JWS decoder | Five-part JWE Compact. | Reject if no matching JWE profile/decoder exists. |
| Valid signature, wrong issuer | JWT with verifiable signature but wrong `iss`. | Reject at validator. |
| Valid signature, wrong audience | JWT meant for another resource. | Reject at validator. |
| Valid signature, expired token | `exp` in the past. | Reject at validator. |
| Valid access token, missing scope | Valid token lacking endpoint authority. | Authentication succeeds, authorization denies. |

### 11.1. Distinguishing mock JWT tests from real signature verification tests

`spring-security-test` provides MockMvc utilities like `jwt()` to attach a simulated `JwtAuthenticationToken` to the request. These are very useful for testing **authorization based on mocked authorities/claims**, yet **they do not necessarily pass through JwtDecoder or perform real JWS signature verification**.

Therefore:

- Use `jwt()` in MockMvc when testing endpoints requiring `SCOPE_orders:read` or specific roles.
- To prove that **`alg: none`, signature mismatches, and malformed JWTs are rejected**, test the real authentication path with `JwtDecoder`/the filter chain or decoder unit tests using intentionally forged/modified tokens.
- Tests should use **test key pairs**, a properly configured test JWKS/decoder, and tokens intentionally mis-signed or tampered with.
- Never put production keys or real user access tokens in fixtures.

Example **permission check with MockMvc** (illustrating authorization, not claiming to test the decoder):

```java
mockMvc.perform(get("/api/orders")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders:read"))))
        .andExpect(status().isOk());
```

In an actual signature test suite, never present the `jwt()` example above as proof that the endpoint rejects unsigned tokens: that test injects a simulated authentication onto the request.

## 12. Operational troubleshooting

When an API returns 401, first determine whether the request falls under **missing credentials, wrong format, invalid signature, or invalid claims**:

| Symptom | Where to check |
| --- | --- |
| Request lacks `Authorization` | Did the client attach the header properly? Did a proxy/gateway strip it? |
| Header has Bearer, yet API cannot decode JWT | Is the token truly a JWT access token? Is an opaque/JWE/ID token or the literal `Bearer` prefix being passed to the decoder? |
| JWT has three parts, yet decoder reports malformed | Are header/payload valid Base64URL/JSON? Was the token truncated, padded, or corrupted in transit? |
| Token has `alg: none` | Why is the client sending unsecured JWTs? The API must keep its signed-token requirement. |
| JWT validly signed at issuer, yet API reports signature failure | Compare issuer, JWKS URL, `kid`, key rotation, environment, algorithm, and whether token data was altered. |
| Errors appear only after key rotation | Was the new public key published before the issuer began signing? Did JWKS caches refresh properly? |
| JWT signature passes, yet API still returns 401 | Check issuer, audience, `exp`/`nbf`, token type, and required-claim validators. |
| JWT passes authentication, yet API returns 403 | Check scope/authority mapping, method security, and tenant/ownership policies. |
| A public endpoint returns 401 when client sends a broken Bearer token | Is the Bearer authentication filter rejecting the token before `permitAll()`? |

Diagnostic logging can be enabled **in controlled environments**:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

In production, follow proper logging policies. Never log **raw access tokens**, ID tokens, refresh tokens, private keys, shared HMAC secrets, or full claim sets containing sensitive data. Log request IDs, error categories, verified issuers, validated key IDs, and standardized outcome codes when needed.

### 12.1. Remediation by root cause

| Root cause | Proper fix |
| --- | --- |
| Client sent ID token by mistake | Acquire an access token with the API's audience/scope. |
| Client received opaque token, API configured for JWT | Align access token format with issuer or configure appropriate introspection. |
| JWT altered in transit/storage | Fix token transport/storage path; never disable verification. |
| JWT signed with new key, API lacks public key | Fix JWKS/key rotation and cache synchronization. |
| Issuer algorithm changed | Update contract and safe algorithm allowlist per plan; never accept arbitrary token `alg` values. |
| JWT has `alg: none` | Configure issuer to emit valid signed access tokens; keep rejecting unsigned tokens. |
| Valid signature, wrong `aud` | Request a token intended for the right resource; keep audience validation. |
| Valid JWT, insufficient `scope` | Request/grant the needed scope or update authorization rules; do not alter the decoder. |

Avoid creating a **401 → refresh → 401** loop when the root cause is a bad format or wrong audience. Refreshing helps only when a token expired and the client is authorized for a refresh flow; it will not fix a mismatched token contract or JWKS configuration.

## 13. Security anti-patterns to avoid

### 13.1. Only `decode` the payload to build a user

Reading JSON from Base64URL does not verify signatures. Application code must never take unverified `sub`/`scope` claims to build an `Authentication` with `authenticated=true`.

### 13.2. Allowing `alg: none` to support “internally issued tokens”

No signature means the payload can be altered undetected. Any API accepting Bearer JWTs over a network must require signatures and approved algorithms.

### 13.3. Trusting arbitrary `kid`, `jku`, or key URLs in headers

JWT headers are controlled by the sender prior to verification. Look up keys solely within trusted sets bound to configured issuers; never fetch keys dynamically from token-proposed URLs.

### 13.4. Automatically accepting both HMAC and RSA with the same key data

HMAC secrets and RSA public keys have completely different semantics. Mixing algorithms and key types can lead to **algorithm confusion**.

### 13.5. Dropping audience validation because the signature is valid

An issuer may sign tokens for many clients and resources. Another API's access token or an ID token can bear a valid signature while still being unauthorized at the current API.

### 13.6. Falling back to “grant minimal access” when token verification fails

An invalidly signed token proves zero identity or permissions. If an endpoint is genuinely public, define explicit rules for anonymous requests; never construct a principal from an untrusted token and assign fallback privileges.

### 13.7. Catching decoder exceptions and letting controllers read claims anyway

When `JwtDecoder` throws an exception, that signals the token is unacceptable. Never catch the error and continue using a manually decoded payload; doing so nullifies the security boundary.

### 13.8. Logging raw tokens or putting them in URLs for debugging

Bearer tokens are credentials: anyone holding an unexpired token can use it within its granted scope. Avoid logs, query strings, and unprotected error trackers; use redacted data and access controls.

## 14. Applied troubleshooting scenarios

### A. “I see the right scope claim, why does the API still return 401?”

A developer decodes the JWT with a payload-inspection tool and sees:

```json
{ "scope": "orders:read", "aud": "orders-api" }
```

However, the client accidentally modified one character in the payload after the token was signed. The signature is no longer valid. The API must return 401; seeing the right scope means nothing because the payload is unauthenticated.

### B. “The token has dots, so it must be a JWT”

The API receives a three-part string whose header is not valid JSON. Counting dots does not validate JOSE structure. The decoder properly rejects it; the client must send the right token format issued by the Authorization Server.

### C. “The issuer just rotated keys; all APIs report signature invalid”

The Authorization Server began signing with private key B, yet the JWKS has not published public key B or Resource Servers have cached A. Resolve by coordinating key publication timing, JWKS caching, `kid`, and the transition window. Never roll back by turning off verification.

### D. “Valid JWT from an OpenID Provider fails to call the API”

The client sent the ID token from OIDC login, with `aud=web-client`. The Resource Server requires an access token with `aud=orders-api`. Rejecting the token even though the same OP signed it is the correct behavior.

### E. “The API receives an opaque token while the developer tries to JWT-decode it”

The Authorization Server returned an opaque access token; `JwtDecoder` cannot recognize three JWS segments. The system must select `OpaqueTokenIntrospector` configured with introspection credentials rather than attempting string-parsing tricks.

### F. “JWT verified cleanly, yet POST still returns 403”

The JWT has a valid signature, right issuer/audience, and is unexpired, yet holds only `orders:read`. Authentication succeeded; `POST /api/orders` requires `orders:write`, so authorization denies it. This is not a signature error.

## 15. Self-check questions

**1. Does being able to Base64URL-decode the payload prove a JWT was signed by the issuer?** No. Decoding only converts representation; it verifies neither integrity nor origin.

**2. Is a JWT with `alg: none` suitable for an API requiring signed access tokens?** No. Unsecured JWTs provide no signature proof under that contract.

**3. Is a three-part JWT guaranteed to be valid?** No. Header/payload parsing, algorithm, key, signature, and claims must all be verified.

**4. Which key signs `RS256` and which key verifies it?** The issuer signs with an RSA private key; the Resource Server verifies with a trusted public key.

**5. Can a JWT with a valid signature but wrong `aud` be used?** No. The token was not issued for that resource API.

**6. Does a JWT Resource Server automatically verify opaque tokens?** No. Opaque tokens require introspection or a matching verification mechanism.

**7. Is a five-part JWE a corrupted three-part JWS?** Not necessarily. JWE is a separate encrypted format; the API must support its profile if JWEs are exchanged.

**8. When encountering 401, is it always due to an invalid signature?** No. 401 can stem from a missing token, bad format, issuer/audience mismatch, expiration, bad signature, or wrong token profile.

**9. When is 403 returned?** Typically when the token authenticated validly, yet the caller lacks the required scope/permission.

**10. Does MockMvc `jwt()` prove Spring rejects invalid signatures?** No. It can inject a simulated authentication to test authorization without running real signature decoding.

## 16. Related standards and references

- **RFC 7515 — JSON Web Signature (JWS):** signed/unsecured JWS, JWS Compact Serialization, and protected headers.
- **RFC 7518 — JSON Web Algorithms (JWA):** JOSE algorithms such as `none`, `HS256`, `RS256`, `PS256`, and `ES256`.
- **RFC 7519 — JSON Web Token (JWT):** JWTs, standard claims, and the unsecured JWT concept.
- **RFC 7516 — JSON Web Encryption (JWE):** encrypted JWT format and JWE Compact structure.
- **RFC 7517 — JSON Web Key (JWK):** JWK/JWKS and verification key management.
- **RFC 8725 — JWT Best Current Practices:** preventing algorithm confusion, separating token types, binding issuer/audience and algorithms.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** profile for OAuth 2.0 JWT access tokens where applicable.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** Bearer challenges, `invalid_token`, `invalid_request`, and `insufficient_scope`.
- **Spring Security — OAuth 2.0 Resource Server JWT:** `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider`, `JwtDecoder`, `NimbusJwtDecoder`, and access-token authentication configuration.

**Rule to remember:** A JWT may be used by an API only when it **matches the committed format, uses an accepted signature protection mechanism, passes signature verification, passes claim/token-profile validators, and satisfies access permissions**. Unsigned, invalidly signed, or unexpectedly formatted tokens must be rejected; the fix belongs in token issuance/selection and verification configuration, never in skipping authentication.
