# Bearer Tokens Do Not by Themselves Prove the Caller Holds a Private Key

In OAuth 2.0, a **bearer token** is a credential with the property that *whoever holds it can use it*. The Resource Server can verify that the token is authentic, issued by the right Authorization Server, unexpired, and carries sufficient scopes, yet **those checks do not by themselves prove that the request sender possesses a private key**.

This is an important distinction between:

- **A valid token:** The Authorization Server issued the token and the Resource Server can validate it.
- **The party presenting the token is the bound subject/device:** The request sender supplies an additional cryptographic proof or certificate proving authorization to use the token, beyond merely knowing the token string.

This lesson explains the nature of bearer tokens, why JWT signatures and HTTPS do not turn a token into proof of possessing a private key, and how **sender-constrained access tokens** solve this problem using **DPoP** or **mutual TLS (mTLS)** in the context of Spring Security OAuth 2.0 Resource Server.

## 1. What does a bearer token confirm?

RFC 6750 describes a bearer token as a token that **any party in possession of the token can use**. The recipient does not require proving possession of a cryptographic key associated with the token.

Suppose an API protects a resource:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
```

With a Resource Server configured for JWT validation, Spring Security can:

1. Extract the string after `Bearer` from the `Authorization` header.
2. Use `JwtDecoder` to verify the JWT signature against trusted public keys.
3. Verify claims such as `iss`, `exp`, `nbf`, and `aud` if a validator is configured.
4. Convert scopes into authorities such as `SCOPE_orders.read`.
5. Match authorities against endpoint rules and allow or deny access.

**No step in the standard bearer flow forces the client to sign the request with its own private key.** The client only needs to present the right token string.

### What happens to a copied token?

```mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant C as Legitimate Client
    participant X as Party that obtained token
    participant RS as Resource Server

    AS-->>C: Access token T
    C->>RS: Authorization: Bearer T
    RS-->>C: 200 if T is valid and authorized

    Note over X: X obtains a copy of T from a leak
    X->>RS: Authorization: Bearer T
    Note over RS: Same token T; no proof of C's private key
    RS-->>X: May return 200 if T is still valid and authorized
```

The diagram illustrates **token replay risk**: someone else reuses a stolen token. Whether their access succeeds depends on expiration, audience, scopes, network conditions, and API policies, yet **pure bearer authentication cannot distinguish two requests that differ only in who holds the token**.

> Key point: **Knowing the token** is the requirement to use a bearer token. **Proving possession of a private key** is an additional requirement of proof-of-possession/sender-constraint mechanisms; the two are not synonymous.

## 2. Distinguishing three types of proof that are often confused

| Evidence | What does it prove? | What does it **not** prove by itself? |
|---|---|---|
| **Authorization Server's signature on the JWT** | The JWT was not tampered with and was signed by a trusted issuer's key. | That the caller holds a client private key; that the caller is the original party issued the token. |
| **TLS/HTTPS between client and Resource Server** | The channel is encrypted, integrity-protected within the TLS connection, and usually authenticates the server's identity. | That every received bearer token is bound to the caller's private key; that the token could not be stolen from logs, memory, or another system. |
| **Proof of caller's key possession** | The caller proves control over the key bound to the token, if the Resource Server verifies it properly. | That the token came from a valid issuer, targets the right audience, has enough scopes, or that the caller can access every record. Those still require separate checks. |

A signed JWT access token looks like:

```text
header.payload.signature
```

The `signature` segment is typically created using the **Authorization Server's private key**, not the private key of the application calling the API. A client can send that JWT without ever holding the Authorization Server's signing key.

Two distinct tasks:

- **Verifying the issuer:** The Resource Server uses the Authorization Server's public key to know the token is authentic and unaltered.
- **Verifying the sender:** The Resource Server uses separate proof to determine whether the caller controls the key/certificate to which the token is bound.

Having `sub=user-123` in a JWT proves that **the issuer placed this identifier into a validly signed token**. It does not prove the current request was sent directly by user `user-123`, or from the exact device that originally received the token.

## 3. How does Spring Security handle an ordinary bearer access token?

For a Servlet application using Spring Security OAuth 2.0 Resource Server, the logical path can be described as:

```mermaid
flowchart TD
    A["HTTP request with Authorization: Bearer T"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["BearerTokenResolver extracts T"]
    C --> D["AuthenticationManager and AuthenticationProvider"]
    D --> E{"Token validation type"}
    E -- "JWT" --> F["JwtDecoder: signature, issuer, timestamps, audience..."]
    E -- "Opaque" --> G["OpaqueTokenIntrospector: active status and token attributes"]
    F --> H{"Token accepted?"}
    G --> H
    H -- "No" --> I["Authentication failure / typically 401"]
    H -- "Yes" --> J["Create Authentication + GrantedAuthority"]
    J --> K["SecurityContext"]
    K --> L["AuthorizationFilter / method security"]
    L --> M{"Sufficient permissions?"}
    M -- "No" --> N["Typically 403"]
    M -- "Yes" --> O["Controller / service"]
```

Notable components:

**`BearerTokenAuthenticationFilter`** reads the bearer token and sends an authentication request to `AuthenticationManager`. The mere presence of `Authorization: Bearer` does **not** make the token trustworthy.

**`JwtAuthenticationProvider`/`JwtDecoder`** handles JWTs; **`OpaqueTokenAuthenticationProvider`/`OpaqueTokenIntrospector`** handles opaque tokens. Both can produce an `Authentication` used by Spring Security for authorization.

**`SecurityContext`** holds the authentication result for the request; **`AuthorizationFilter`** along with method security evaluates whether the caller is allowed to invoke the endpoint/operation.

This default flow **performs no separate check on a client's private key**. Therefore, configuring a JWT Resource Server and scopes does not equate to defending against reuse of a stolen bearer token.

### Baseline configuration example

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          audiences:
            - orders-api
```

```java
@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Key imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

The application needs appropriate Spring Security and OAuth 2.0 Resource Server dependencies. The example uses the `audiences` property supported by modern Spring Boot versions; if using another version or building a custom `JwtDecoder`, configure an equivalent validator.

In this configuration:

- `issuer-uri` identifies the trusted issuer and supports JWT decoding/validation.
- `audiences` restricts tokens to `orders-api`.
- `hasAuthority("SCOPE_orders.read")` requires the matching scope mapped to an authority.
- **No line verifies a DPoP proof or an mTLS certificate bound to the token.**

CSRF, sessions, gateways, and other filters must be designed according to the application architecture; this example focuses only on the bearer flow.

## 4. Why are HTTPS, client authentication, and PKCE still not enough to prove the caller holds a private key?

Several mechanisms are vital to OAuth 2.0, yet protect a **different stage or relationship** than access token sender constraining.

### HTTPS protects the connection, not binding tokens to clients

HTTPS prevents eavesdropping and tampering in transit, assuming TLS verification is performed properly. However, tokens can still leak through:

- HTTP logs of clients, reverse proxies, gateways, or applications.
- Debugging tools, telemetry, error logs, or traces.
- Unauthorized access to memory, config files, backups, or storage.
- Malware, XSS, malicious extensions, or third parties able to read tokens.
- Sending tokens accidentally to untrusted parties; never place access tokens in URLs.

Given a copy of the token, an attacker can open **their own HTTPS connection** to the API and send the exact same `Bearer` value. TLS protects that new connection without proving the attacker is the original client.

### Client authentication at the token endpoint does not automatically carry over to the Resource Server

The Authorization Server can authenticate an OAuth client using `client_secret_basic`, `private_key_jwt`, or mTLS when issuing tokens. That step verifies **who is requesting the token** at the Authorization Server's endpoint.

Once the access token is issued, the Resource Server only sees the token in the request. Unless **the token is sender-constrained** and the Resource Server enforces binding checks, the fact that the OAuth client authenticated with a private key at the token endpoint does not force the current caller to present that private key.

Specifically, **a client secret is not an asymmetric private key**, and a client having a secret does not turn an access token into a proof-of-possession token.

### PKCE protects the authorization code flow, not turning access tokens into key-bound tokens

PKCE uses `code_verifier`/`code_challenge` to prevent intercepting and reusing an authorization code during code-for-token exchange. PKCE does not force every API request to carry a fresh signature from a private key. A bearer access token obtained after a PKCE flow still has bearer properties unless a separate sender constraint is applied.

### An OIDC ID token does not prove authority to use an access token

An ID token is issued to an OIDC client to represent an identity authentication event, typically with the client ID as audience. A Resource Server receives an **access token** and must evaluate purpose, issuer, audience, and API permissions. The fact that a client received a valid ID token is not cryptographic proof that the sender of the current API request holds a private key linked to the access token.

## 5. Sender-constrained access tokens: two independent conditions required

To reduce the risk of reusing copied tokens, OAuth 2.0 can apply **sender constraints**: the Authorization Server binds the token to a specific key/certificate, and the Resource Server requires the caller to prove authority to use that key/certificate.

Example token issued with a key confirmation attribute:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "exp": 1900000000,
  "cnf": {
    "jkt": "<client-JWK-thumbprint>"
  }
}
```

`cnf` is the **confirmation claim**, describing the key/certificate bound to the token; it is **not proof that the private key was presented in the current request**. The Resource Server must also:

1. Validate the access token and trust the source containing `cnf`.
2. Validate the request's own proof: a DPoP signature or mTLS certificate.
3. Match the key/certificate used for the proof against the bound value in the token.
4. Continue checking issuer, audience, expiration, scopes, and resource access permissions.

```mermaid
flowchart TD
    AT["Valid access token with key/certificate binding"] --> BOTH{"Both conditions true?"}
    P["Request proof shows caller holds matching key/certificate"] --> BOTH
    BOTH -- "No" --> REJECT["Reject request"]
    BOTH -- "Yes" --> AUTHZ["Proceed to evaluate scope and resource permissions"]
```

Two common sender-constraint standards:

- **DPoP (RFC 9449):** The client signs a per-HTTP-request JWT proof with its private key. The token is bound to the **public JWK's thumbprint**.
- **OAuth 2.0 mutual-TLS certificate-bound access tokens (RFC 8705):** The token is bound to a **client certificate**. The caller proves possession of the private key during the mTLS handshake.

Actual protection depends on key generation, storage, copy handling, and verifier implementation. Sender constraints **reduce risk** from isolated token theft; they do not guarantee protection against every attack if the private key is also compromised or the client device is hijacked.

## 6. DPoP: a signed JWT proof per request

**Demonstrating Proof-of-Possession (DPoP)** under RFC 9449 enables an OAuth client to prove control over the private key corresponding to the public key bound to an access token. The client constructs a **DPoP proof JWT** and signs it with its own private key.

DPoP typically involves three stages:

1. **The client has an asymmetric key pair.** The public key is declared in the proof JWT header; the private key signs it.
2. **The Authorization Server binds the access token to the public key.** JWT tokens typically carry `cnf.jkt`; opaque tokens can return the corresponding binding via introspection.
3. **Every call to the Resource Server carries its own proof.** The Resource Server checks the signature and HTTP claims, prevents proof replay, and matches the public key's thumbprint against `cnf.jkt`.

### 6.1. When the client requests an access token

The client can send a proof to the Authorization Server at the token endpoint. The proof is signed with the private key and contains `htm=POST`, `htu` set to the token endpoint URL, a timestamp, and a unique identifier. At this step **there is no access token to hash yet**, so the initial token-issuance proof typically **omits `ath`**.

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: <signed-dpop-proof-for-token-endpoint>

grant_type=client_credentials&scope=orders.read
```

This request snippet only illustrates the format; OAuth client authentication and specific grants must match the Authorization Server.

Upon accepting the request, the Authorization Server binds the issued access token to the JWK thumbprint and may return:

```json
{
  "access_token": "<sender-constrained-access-token>",
  "token_type": "DPoP",
  "expires_in": 300,
  "scope": "orders.read"
}
```

The `token_type` of a DPoP access token is **`DPoP`**. Clients should not arbitrarily switch it to the `Bearer` scheme when presenting the token to a Resource Server.

### 6.2. Client calls the API with the access token and proof

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP <sender-constrained-access-token>
DPoP: <signed-dpop-proof-for-this-request>
Accept: application/json
```

Unlike pure bearer tokens, the request carries **two separate items**. `Authorization: DPoP ...` presents the access token; the `DPoP` header presents the client-signed JWT proof.

The header of a DPoP proof JWT may look like:

```json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<base64url-public-x>",
    "y": "<base64url-public-y>"
  }
}
```

This is a **public JWK**; private key parameters must never be placed in the header. `alg` must be an asymmetric signing algorithm permitted by verifier policy; never accept `none` or arbitrary algorithms merely because a token asks for them.

Illustrative payload:

```json
{
  "jti": "fe305a99-780d-4ab9-9142-54c1c1c2a8a7",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1794718800,
  "ath": "<base64url-SHA256-of-access-token>"
}
```

Example values only illustrate structure, not a usable proof.

| Field | Role | Critical checks |
|---|---|---|
| `typ: "dpop+jwt"` | Identifies the proof JWT type | Do not confuse this proof with an ID token or access token JWT. |
| `alg` | Proof signing algorithm | Permit only policy-approved asymmetric algorithms. |
| `jwk` | Client's public key | Reject private JWKs; use this key to verify the signature. |
| `jti` | Unique proof ID | Prevent reusing the same proof within the accepted time window. |
| `htm` | HTTP method | Must match the actual method, e.g., `GET`. |
| `htu` | Target HTTP URI | Must match the request URI per DPoP normalization rules. |
| `iat` | Proof creation timestamp | Must fall within an acceptable time window; limits proof validity. |
| `ath` | Access token hash | Must match the access token accompanying the request. |
| `nonce` (if required) | Server-issued value | Binds the proof to a valid nonce, reducing replay/precomputation risk. |

**`ath` is not a signature of the token.** It is computed as:

```text
ath = base64url( SHA-256( ASCII(access_token) ) )
```

`ath` binds the DPoP proof to the **specific access token string** being presented. The DPoP proof's signature proves the client controls the private key matching the header's public key.

**`cnf.jkt`** is the JWK thumbprint, computed per RFC 7638 from the canonical representation of the required public JWK members for the key type, hashed with SHA-256 and Base64URL-encoded. Do not arbitrarily hash the entire JSON string, as field ordering and extra attributes can break the thumbprint.

### 6.3. What must the Resource Server verify?

When receiving `Authorization: DPoP <token>` and `DPoP: <proof>`, the Resource Server must verify **both the token and the proof**:

1. **Valid access token:** trusted issuer, signature or introspection, timestamps, audience, token type, and required policies.
2. **Token has DPoP binding:** extract `cnf.jkt` from the validated token (or trusted introspection data).
3. **Proof is a valid DPoP JWT:** `typ`, public `jwk`, accepted `alg`, and valid signature under the declared public key.
4. **Proof matches the request:** `htm` and `htu` match the served HTTP request; handle proxies and external URIs according to trust config.
5. **Proof is fresh and not replayed:** `iat` is recent enough; check `jti` in an anti-replay window; enforce `nonce` if required by the server.
6. **Proof is bound to the token:** `ath` matches the hash of the received access token.
7. **Same key holder:** the JWK thumbprint of the proof's public signing key equals `cnf.jkt` bound to the access token.
8. **API permissions:** after authentication succeeds, evaluate scopes, roles, object permissions, and tenants.

Verifying the proof signature **without comparing `cnf.jkt`** lets anyone generate a new key pair and sign a fake proof for a stolen token. Matching `cnf.jkt` **without verifying the proof signature** likewise proves nothing about private key possession. Both checks must run together.

### 6.4. Why is a proof not easily copied to another request?

Suppose an attacker only obtains the access token `T`:

- They lack the private key that produced `cnf.jkt`, so they cannot sign a valid proof with the same public key.
- If they generate a different key pair, its public key thumbprint will not match `cnf.jkt`.
- If they grab an old proof, `jti`, `iat`, and possibly `nonce` block replay; `htm` and `htu` bind the proof to method/URI; `ath` binds it to `T`.

These bindings have limits:

- DPoP's `htu` is derived from the URI **excluding query and fragment**; DPoP also does not directly sign the HTTP request body. Thus `jti`, `iat`/nonce checks, and application policies remain essential.
- If the private key is **also stolen**, an attacker can mint new proofs; sender constraining cannot prevent that.
- If a proof is replayed concurrently across nodes whose per-node `jti` caches are unsynchronized, replay protection may be incomplete.
- If a malicious script can invoke signing functions inside a compromised client runtime, valid proofs can still be produced; defense against token exfiltration is not equivalent to defense against all malware.

### 6.5. A DPoP request traversing the flow

```mermaid
sequenceDiagram
    participant C as Client (holds private key)
    participant AS as Authorization Server
    participant API as Resource Server

    C->>AS: Token request + DPoP proof signed with key K
    AS->>AS: Verify proof, bind K's cnf.jkt
    AS-->>C: Access token T, token_type=DPoP

    C->>C: Sign new proof P with htm, htu, iat, jti, ath(T)
    C->>API: Authorization: DPoP T + DPoP: P
    API->>API: Verify T and read cnf.jkt
    API->>API: Verify P's signature using public JWK
    API->>API: Check htm/htu/iat/jti/ath/nonce if present
    API->>API: Match P's public key against T's cnf.jkt
    API->>API: Enforce scope and resource authorization
    API-->>C: 200 or appropriate error
```

DPoP failures may be reflected via codes/details such as `invalid_dpop_proof` or requiring a fresh nonce (`use_dpop_nonce`) per RFC 9449. Do not assume every DPoP error is `401 invalid_token`; error codes and handling locations depend on the token endpoint, Resource Server, and implementation.

## 7. mTLS certificate-bound access tokens: binding tokens to client certificates

**Mutual TLS (mTLS)** differs from ordinary TLS in that, besides the server authenticating to the client, the server also requires a **client certificate** and verifies during the TLS handshake that the client controls the matching private key.

RFC 8705 describes how to bind an OAuth 2.0 access token to a client certificate. The Authorization Server can embed the certificate thumbprint in the `cnf` claim:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1900000000,
  "cnf": {
    "x5t#S256": "<base64url-SHA256-of-DER-client-certificate>"
  }
}
```

`cnf["x5t#S256"]` is the Base64URL-encoded SHA-256 thumbprint of the **entire DER-encoded X.509 client certificate**, not a hash of the public key under JWK thumbprint rules.

At the Resource Server, checks must ensure:

1. The client established mTLS with an accepted certificate over a connection to a trusted authenticating component.
2. The API receives the client certificate **verified during the TLS handshake**.
3. That certificate's thumbprint matches `cnf["x5t#S256"]` in the validated access token.
4. The access token still passes issuer, time, audience, scope, and access permission checks.

The API request itself may still look like an ordinary bearer token:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <certificate-bound-access-token>
```

The deciding factor lies in the **TLS client certificate** and matching it against the token; inspecting only the `Bearer` header cannot tell whether a token is actually sender-constrained.

### Which systems typically use mTLS?

mTLS suits backend services and enterprise environments with certificate infrastructure and certificate lifecycle management. DPoP is often more practical when clients need application-layer proofs, such as mobile or public clients capable of generating and storing an appropriate private key.

Choosing between them depends on client model, network topology, and capabilities of the Authorization Server, Resource Server, and gateway.

### Note when using a reverse proxy or API gateway

If TLS terminates at the gateway and requests proceed to the backend over HTTP or a different mTLS connection, the backend **cannot automatically see** the client's actual certificate from the initial TLS connection.

Valid designs include:

- Having the gateway verify mTLS, check token binding, and enforce policy at the gateway; or
- Having the gateway forward **verified certificate information** to the backend over a protected internal mechanism so the backend checks token binding against that data.

Never trust an arbitrary header such as `X-Client-Cert` sent directly by external clients. When using a header to convey identity/certificate details, the gateway must strip externally supplied headers, populate trusted data itself, and restrict backend connections accepting that header. A backend blindly reading an unguarded header is vulnerable to mTLS spoofing.

## 8. Comparing pure bearer, DPoP, and mTLS

| Criterion | Ordinary Bearer access token | DPoP-bound access token | mTLS certificate-bound access token |
|---|---|---|---|
| Must know the access token string? | Yes | Yes | Yes |
| Must prove possession of client private key? | **No** | **Yes**, via DPoP proof signature | **Yes**, via mTLS handshake |
| What is the token bound to? | No mandatory sender binding | JWK thumbprint (`cnf.jkt`) | Certificate thumbprint (`cnf["x5t#S256"]`) |
| Typical transmission | `Authorization: Bearer T` | `Authorization: DPoP T` plus `DPoP: P` header | `Authorization: Bearer T` over an mTLS connection |
| Resists reuse of token stolen alone | Limited | Better if private key stays safe and verifier checks everything | Better if private key/certificate path stays safe and binding is checked |
| Binds proof to HTTP method/URI? | No | Yes via `htm` and `htu` | Not DPoP-style; bound to TLS connection |
| Proof replay protection via `jti`? | Not applicable | Must enforce replay/nonce policies | Does not use DPoP `jti`; TLS handles channel protections |
| Client complexity | Low | Must generate/store key and sign proof per request | Needs client certificate, key, and TLS infrastructure |
| Resource Server complexity | Validate access token, authorize | Adds DPoP proof, hashing/thumbprint, replay/nonce, and binding checks | Adds mTLS verification, certificate extraction, and thumbprint matching |
| If private key is stolen | Unrelated to token checks | Can mint valid proofs | Can impersonate certificate holder if other conditions permit |

**Sender-constraining is only effective when the Authorization Server issues properly bound tokens and the Resource Server checks the binding on use.** Supporting a mechanism only on the client or only on the issuer is insufficient.

## 9. What does Spring Security Resource Server need to check possession?

Spring Security supports validating bearer JWTs and opaque tokens, yet **simply configuring `oauth2ResourceServer().jwt()` by default does not implement full DPoP/mTLS token binding**. Exact built-in support may depend on the Spring Security version, extension libraries, and application configuration.

For **DPoP**, the receiving side needs a request-processing component responsible for:

- Accepting access tokens with the `DPoP` scheme and reading the `DPoP` header.
- Verifying the token via a trusted JWT decoder/introspection.
- Extracting `cnf.jkt` and validating the proof per RFC 9449: `typ`, signature, algorithm, `htu`, `htm`, `iat`, `jti`, `ath`, and nonce if used.
- Matching the proof's JWK thumbprint against the key in the token.
- Creating or accepting an `Authentication` with permissions only after all required conditions pass.

**Never simply add `DPoP` to a bearer filter's accepted schemes and ignore the proof header.** Doing so degrades an intended sender-constrained access token into an ordinary bearer token, defeating the security goal.

For **mTLS-bound tokens**, the receiving side needs:

- A client certificate **authenticated by the TLS layer** or received via a trusted path from the gateway.
- Computing the certificate thumbprint and comparing it with `cnf["x5t#S256"]` in the validated access token.
- Rejecting requests when no certificate is present, the certificate is unverified, or the thumbprint mismatches.
- Running all standard JWT/introspection and authorization checks.

Depending on architecture, sender-constraint enforcement can live in custom Spring Security filters/providers, at a trusted gateway layer, or via a full standards-compliant library. If handled at a gateway, clearly design the **trust boundary**, block direct backend calls bypassing the gateway, and never trust externally supplied proof/certificate metadata headers.

### Illustrative pseudocode for the authorization decision

This is **conceptual logic**, not runnable Java code and not a substitute for standard verification libraries:

```text
request -> extract_access_token_and_scheme()

token = validate_access_token(
    trusted_issuer,
    signature_or_introspection,
    expiry,
    audience
)

if token is DPoP-bound:
    require Authorization scheme == "DPoP"
    proof = require_and_parse_DPoP_header()
    verify_public_key_signature(proof)
    verify_typ_alg_htm_htu_iat_jti_ath_and_nonce(proof, request, token)
    require jwk_thumbprint(proof.public_jwk) == token.cnf.jkt

else if token is mTLS-certificate-bound:
    certificate = require_verified_tls_client_certificate()
    require certificate_sha256_thumbprint(certificate) ==
            token.cnf["x5t#S256"]

else:
    apply_policy_for_unbound_bearer_tokens()

authentication = map_claims_to_principal_and_authorities(token)
require_authorized(authentication, request, resource)
allow_request()
```

`apply_policy_for_unbound_bearer_tokens()` must enforce an **explicit policy**: which endpoints accept ordinary bearer tokens and which mandate sender-constrained tokens. Never silently allow tokens missing `cnf` through endpoints designed to require proof-of-possession.

In particular, **the Resource Server must still check the token's audience**. A valid sender proof never makes a token issued for another API valid at the current API.

## 10. Design mistakes that create a false sense of security

### Mistake 1: “The JWT has a digital signature, so the caller signed the request”

**Wrong signer.** A JWT access token is typically signed by the Authorization Server to prove token provenance. The client merely forwards the token string; it does not use its own private key to sign requests when using pure bearer tokens.

**Right approach:** Distinguish the issuer's signature from a caller's proof signature. When possession proof is needed, use an appropriate sender-constraint mechanism and verify it at the Resource Server.

### Mistake 2: “HTTPS encrypts everything, so a leaked token cannot be used”

HTTPS protects transit, but does not prevent leaks via endpoints, logs, or memory. Once someone has the token string, they can open a new HTTPS session and replay it.

**Right approach:** Minimize token leak surfaces, restrict audience/scope/lifetime, and consider DPoP/mTLS for high-value resources.

### Mistake 3: “Having a `cnf` claim is enough”

`cnf` describes the bound key/certificate; a bearer token containing `cnf` without the server verifying accompanying proof can still be replayed.

**Right approach:** Verify actual proofs, match thumbprints, and reject missing or mismatched requests.

### Mistake 4: “Any valid DPoP proof works with the token”

A client can generate its own key pair and sign a structurally valid JWT. Without comparing the proof's thumbprint to `cnf.jkt`, the server has not proven this is the exact key the Authorization Server bound.

**Right approach:** Verify the proof signature **and** the `cnf.jkt` binding, along with `ath`, `htm`, `htu`, `iat`, and `jti`.

### Mistake 5: “DPoP proofs are signed so they cannot be replayed”

A validly signed proof can still be captured and replayed verbatim if the server skips checking timestamps, unique IDs, or nonces. `htu` excludes query strings and proofs do not sign bodies.

**Right approach:** Enforce tight time windows, consistent system-wide `jti` replay checks, and nonces when needed; still enforce business permissions inside the request.

### Mistake 6: “mTLS at the token endpoint automatically makes every access token certificate-bound”

An AS can use mTLS **solely for client authentication** at the token endpoint. To make tokens certificate-bound, the AS must issue binding metadata and the Resource Server must match the request certificate against that binding.

**Right approach:** Inspect token metadata/claims or introspection, confirm the exact issued token type, and enforce API policy accordingly.

### Mistake 7: “If the gateway says the client had a certificate, the backend can just trust it”

A certificate header without a trusted origin can be spoofed. This is especially dangerous if the backend is directly reachable from the Internet or proxies fail to strip external headers.

**Right approach:** Trust only data authenticated by the gateway and sent over a protected internal channel, or have the backend terminate and verify mTLS directly.

## 11. Scenario exercise: can a stolen token be used?

Suppose `orders-api` requires `orders.read`; the token is unexpired, has the right audience, and there are no other business authorization flaws.

| Scenario | Ordinary Bearer | DPoP-bound (properly enforced) | mTLS-bound (properly enforced) |
|---|---|---|---|
| Legitimate user presents token and required proof | May be permitted | May be permitted | May be permitted |
| Attacker holds only the token string, no key/certificate | **Can replay** | **Rejected** because cannot sign proof with matching key | **Rejected** because cannot present bound certificate |
| Attacker holds token and matching **private key** | Key not needed | Can mint fresh proofs, so still at risk | Can prove possession if also holding certificate/key and meeting TLS conditions |
| Attacker holds token and **old DPoP proof**, no private key | Bearer uses no proof | Must be blocked when replay detection/time window/nonce work properly | Unrelated to mTLS |
| Validly signed token with wrong `aud` | Must be rejected if validator is right | Must be rejected | Must be rejected |
| Token lacks scope/permission to view order 42 | Must be rejected at authorization | Must be rejected at authorization | Must be rejected at authorization |

Fundamentally, DPoP/mTLS do not replace JWT validation, user authentication, or authorization. They add **a cryptographic factor** to access token usage, preventing an attacker holding only the token string from impersonating the authorized sender.

### Example analyzing a JWT access token

Token A:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1900000000
}
```

Even if validly signed and accepted by the Resource Server, this **may still be a pure bearer access token** because there is no possession binding in the example. Valid claims do not prove the client holds a private key.

Token B:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1900000000,
  "cnf": {
    "jkt": "<client-DPoP-key-thumbprint>"
  }
}
```

Token B carries a DPoP key binding. However, if the Resource Server only verifies the issuer signature and ignores `cnf.jkt` and the `DPoP` header, sender constraining **is not enforced**. Only when the Resource Server performs the full verification can the request be said to have proven control of the key bound to the token.

## 12. Choosing a solution that matches your threat model

Before adding sender constraints, pinpoint the specific risk to reduce:

**If the main concern is token leakage via logs or monitoring:** sender-constrained tokens reduce the risk of replaying a leaked token string alone, yet you still must stop logging tokens, mask credentials in telemetry, and restrict access to operational data.

**If the app is a browser or mobile client:** DPoP may fit because proofs are signed at the application layer. Still, private key protection depends on platform, XSS resistance, key storage, and which code can invoke signing. An attacker controlling the client runtime can tell the client to sign harmful requests even without reading the private key.

**If the system is service-to-service:** mTLS can leverage existing certificate infrastructure and service meshes. Distinguish mTLS between services from **certificate-bound access tokens**; having network mTLS does not automatically mean the token is bound to the caller's certificate.

**If an API gateway is involved:** align where checks execute, whether direct backend access is blocked, trusted data sources, and how external method/URI checks work for DPoP. Rewriting HTTP host, scheme, or path at a proxy can break `htu` if the verifier sees a different URL than the client.

**If early token revocation must be blocked:** sender constraints do not solve revocation by themselves. Locally verified JWTs do not automatically know a token was invalidated; opaque token introspection or another state check may be needed depending on system requirements.

**If both the token and private key are compromised:** both DPoP and mTLS lose effectiveness. Secure key management/storage, short token lifetimes, revocation, and anomaly detection are required.

Layer your defenses: HTTPS, issuer/audience validators, least-privilege scopes, short lifetimes, safe token storage, replay controls, object-level authorization, and sender constraints when warranted by the threat model.

## 13. Mental checklist when verifying a request requiring proof-of-possession

When an API claims “access tokens use proof-of-possession,” verify in order:

1. **Is the token actually bound?** Does the issuer-signed JWT contain `cnf`, or does introspection from a trusted AS return an equivalent binding?
2. **Which type of binding?** `cnf.jkt` for DPoP or `cnf["x5t#S256"]` for certificate-bound tokens?
3. **Did the caller present proof?** A freshly signed DPoP proof for the request, or a client certificate verified via mTLS?
4. **Was the proof properly verified?** Signature, algorithm, proof claims, anti-replay/nonce, or TLS client certificate validation?
5. **Was the right bound key/certificate used?** Match the thumbprint from the proof against `cnf` in the validated access token.
6. **Is the token used in the right context?** Appropriate issuer, audience, access token type, timestamps, and policies?
7. **Is this operation authorized?** Scope/authority, ownership, and tenant still require independent authorization decisions.
8. **Where is the trust boundary?** If a gateway performs verification, can the backend be called directly or tricked with spoofed proof/certificate headers?

The decisive question is: **If someone copies only the access token string, without the private key or certificate, can they call the API successfully?** If the answer is still “yes” for an endpoint needing sender constraint, the current setup does not enforce proof of key possession.

## 14. Standard references for further reading

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): defines bearer tokens and HTTP usage.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proofs, `htm`, `htu`, `ath`, `jti`, `cnf.jkt`, nonces, and validation.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): distinguishes mTLS client authentication from certificate-bound access tokens.
- [RFC 7800 — Proof-of-Possession Key Semantics for JSON Web Tokens](https://www.rfc-editor.org/rfc/rfc7800): `cnf` semantics and representing confirmation keys.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): deterministic thumbprint calculation for public JWKs.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): guidance on protecting access tokens, sender constraining, and mitigating OAuth risks.
- [Spring Security Reference — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): bearer JWT/opaque token authentication, filter chains, and version-specific configuration capabilities.

**Takeaway:** A JWT signature lets the API trust that the token was issued by the right issuer; DPoP or mTLS-bound tokens let the API verify whether the **current request** came from the party controlling the key/certificate bound to that token. Those are two different proofs, and neither replaces resource authorization.
