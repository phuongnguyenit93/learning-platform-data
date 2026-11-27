# Coordinating with the Resource Server to Verify Proofs and Token Binding

A **Bearer** access token operates on a simple rule: any party holding the token can send that token to an API. While convenient, this introduces serious risk if an access token leaks through logs, devices, proxies, browsers, or an intermediary system. **Demonstrating Proof of Possession (DPoP, RFC 9449)** adds cryptographic proof to bind an access token to a client key pair. When calling an API, the client must send both the access token and proof that it possesses the corresponding private key.

In that architecture, the **Authorization Server (AS)** is responsible for verifying DPoP proofs when issuing tokens and embedding the public-key thumbprint into the token. The **Resource Server (RS)** must verify each request's proof, verify the access token is bound to that exact public key, match the proof against the current HTTP request, and prevent proof replays. Both sides must share the same token-binding contract; if the AS issues a DPoP-bound token but the RS only handles Bearer tokens, the protection is incomplete.

This lesson belongs to the **DPoP** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module. It guides designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security, Spring Authorization Server, and Spring Boot, focusing on **coordinating with the Resource Server to verify proofs and token binding**.

> **Key principle:** A valid DPoP proof only proves the request was signed by the corresponding private key. The Resource Server must also verify the access token, verify the token is bound to that public key, check `ath`, `htm`, `htu`, timestamps, nonce/replay, and finally enforce scopes and business permissions.

## 1. What Problem Does DPoP Solve?

Suppose `orders-api` accepts a Bearer access token. If the token is copied from logs or a client machine, an attacker can send the token from another machine until it expires or is revoked. The RS has no evidence showing whether the caller holding the token is the original client to which it was issued.

DPoP adds a client-managed key pair:

- **Private key:** retained by the client and used to sign each DPoP proof; never sent to the AS or RS.
- **Public key:** placed by the client in the proof's JOSE header as a public JWK; used by the AS to bind the token.
- **Token binding:** AS stores the public key's fingerprint inside the access token or introspection metadata.
- **Per-request proof:** client signs a fresh proof for every HTTP request to the token endpoint or a protected resource.

When an access token is stolen without the private key, another party cannot produce a valid proof for the bound public key. DPoP thus reduces the reusability of exposed tokens in bearer fashion.

### 1.1. DPoP Is Application-Layer Sender-Constraining

DPoP is an **application-level sender-constraint** mechanism. It does not replace TLS, does not encrypt request bodies, does not authenticate users, and does not replace API authorization.

| Mechanism | What Is Proven/Bound |
|---|---|
| Bearer access token | Caller possesses the token string |
| DPoP | Caller holds the private key matching the public key bound to the token, and the proof matches the request |
| mTLS-bound token (RFC 8705) | Token is bound to the client certificate on the TLS session |
| PKCE | Authorization code is bound to the client's code verifier |
| OIDC ID Token | User authentication claims for the Relying Party |

DPoP can be combined with Authorization Code + PKCE, Client Credentials, Refresh Token, or other grants if supported by the AS. PKCE and DPoP protect different boundaries: PKCE protects the authorization code; DPoP binds the access token to the client's key.

### 1.2. What DPoP Does Not Solve on Its Own

- Does not prevent an attacker from using a token if the attacker also steals the private key or can ask a compromised device to sign proofs.
- Does not stop malicious XSS controlling a browser application that has permission to use the key, even when the key is non-exportable.
- Does not determine the user, tenant, scope, or record-level permissions on its own.
- Does not sign the entire HTTP body or arbitrary headers; proofs bind method, target URI, and access token via standard claims.
- Does not protect responses returned by the RS.
- Does not replace TLS or proxy, DNS, issuer, and trust configuration controls.

## 2. Components That Must Coordinate

Suppose there are three components:

- **portal-web:** OAuth2 Client, holding the private DPoP key.
- **identity.example.com:** Spring Authorization Server, verifying proofs when the client requests tokens.
- **orders-api:** Spring Security Resource Server, verifying access tokens and DPoP proofs on every request.

| Component | DPoP Responsibility |
|---|---|
| OAuth2 Client | Generates/retains key pair, signs proofs for token requests and resource requests |
| Authorization Server | Verifies proofs at the token endpoint, embeds the public-key thumbprint in access tokens, returns `token_type=DPoP` |
| Resource Server | Verifies access token, proof, thumbprint binding, `ath`, request method/URI, timestamp, and replay |
| Reverse proxy/API gateway | Preserves accurate external URI/method; supplies forwarded headers only from trusted proxies |
| Replay store | Tracks used proofs within the validity window; shared across nodes in clustered deployments |

**AS and RS must agree on the token binding format.** For JWT access tokens, RFC 9449 defines `cnf.jkt`. For opaque tokens, the AS must return equivalent confirmation info via introspection or an agreed trusted mechanism.

## 3. Flow from Token Issuance to Resource Server Call

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server

    Note over C: Generate key pair K (private kept at client)
    C->>AS: POST /oauth2/token + DPoP proof(K public)
    AS->>AS: Verify proof: signature, typ, alg, htm, htu, iat, jti, nonce
    AS->>AS: Compute JWK thumbprint (jkt)
    AS-->>C: access_token + token_type=DPoP
    Note over AS: Token contains cnf.jkt or binding via introspection
    C->>RS: Authorization: DPoP AT + DPoP proof(K, ath, htm, htu)
    RS->>RS: Verify access token and read cnf.jkt
    RS->>RS: Verify proof JWT using public JWK in proof
    RS->>RS: Compare proof key thumbprint with cnf.jkt
    RS->>RS: Check ath, htm, htu, iat, nonce, jti/replay
    alt Token and proof valid
        RS-->>C: Process business authorization and return response
    else Binding/proof/token invalid
        RS-->>C: 401 / DPoP challenge or token error
    end
~~~

The decisive point is that the RS **does not merely verify the proof signature**. It must verify the proof was signed by the exact public key bound to the access token. Without this check, someone holding a stolen token could use their own key pair to sign a valid proof for their own key.

## 4. A DPoP Proof Is a Separate JWT

A DPoP proof is a short-lived JWS/JWT generated by the client for each HTTP request. Its header has the form:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "PUBLIC_X_COORDINATE",
    "y": "PUBLIC_Y_COORDINATE"
  }
}
~~~

Illustrative payload for a request to a Resource Server:

~~~json
{
  "jti": "9f6b6e80-5c0c-4c82-9f17-4e1a3f0a9d01",
  "htm": "GET",
  "htu": "https://orders.example.com/api/orders/123",
  "iat": 1794850000,
  "ath": "BASE64URL_SHA256_OF_ACCESS_TOKEN"
}
~~~

Key values and claims in the example are placeholders, not a signed proof. The `jwk` header contains the **public key**; it must never contain private members such as RSA `d`, EC `d`, or symmetric secrets. DPoP proofs must use a supported and policy-approved asymmetric signature; never accept `alg=none` or MAC algorithms.

### 4.1. Claim Meanings

| Claim | Required in Proof? | Role |
|---|---|---|
| `jti` | Yes | Unique ID of the proof; supports replay detection |
| `htm` | Yes | HTTP method for which the proof was created |
| `htu` | Yes | Target HTTP URI, excluding query and fragment |
| `iat` | Yes | Time the proof was created |
| `ath` | When sending an access token to a protected resource | Hash of the access token being sent |
| `nonce` | When the server requires a nonce | Latest nonce value issued by that exact server |

`ath` is not the hash of the entire request. It is the hash of the **access token value**. When a proof is used solely at the token endpoint to obtain an access token, no access token accompanies the request, so `ath` is not required under protected-resource rules.

### 4.2. Proof Header `jwk` Must Be a Public JWK

The Resource Server needs the public key in the proof to verify the signature, but must reject private key material inside the JWK:

- RSA public: `kty`, `n`, `e`;
- EC public: `kty`, `crv`, `x`, `y`;
- OKP public: `kty`, `crv`, `x`.

Reject proofs containing private parameters. Never fetch keys from arbitrary URLs in the JWT header and never treat `kid` as a trust anchor. The proof carries its own public JWK; the RS must still verify the signature, algorithm, and binding to the token.

### 4.3. `typ` and `alg`

- `typ` must equal `dpop+jwt`.
- `alg` must be a registered, implementation-supported, and policy-allowed asymmetric signature algorithm.
- Never accept `none`.
- Never accept HMAC/MAC algorithms for DPoP proofs.
- Never allow the token header to force the verifier to use an algorithm outside the allowlist.

## 5. Token Binding: `cnf.jkt`

When the AS verifies a DPoP proof during token issuance, it takes the public JWK from the proof and computes the **JWK SHA-256 Thumbprint** per RFC 7638. That thumbprint value is attached to the access token under the `cnf.jkt` claim.

Example JWT access token payload:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1794850000,
  "exp": 1794850600,
  "cnf": {
    "jkt": "BASE64URL_SHA256_JWK_THUMBPRINT"
  }
}
~~~

`cnf` is the confirmation claim; `jkt` identifies the public key used to sender-constrain the token. This value is the thumbprint of the **public JWK**, not the thumbprint of the proof JWT, access token, or a certificate.

### 5.1. Computing the JWK Thumbprint

RFC 7638 defines the thumbprint based on a canonical JSON object containing only the required members for the key type. After constructing the canonical representation, compute SHA-256 and Base64URL-encode without padding.

Do not take an arbitrary JWK JSON string and hash the raw text as-is: member ordering, whitespace, or extra metadata would change the result. Use a vetted JOSE library's RFC 7638 implementation.

### 5.2. Where Does the RS Obtain the Binding?

| Token Format | Binding Source |
|---|---|
| JWT access token | `cnf.jkt` claim after RS verifies signature, issuer, and other claims |
| Opaque/reference token | Trusted introspection result containing `cnf.jkt` or contracted confirmation data |

Do not read `cnf.jkt` from an unverified token. For opaque tokens, do not decode the token string to guess claims; call introspection with the RS's credentials, verify `active`, and extract confirmation metadata from the response.

### 5.3. Comparing the Binding

~~~text
proofJkt = RFC7638_SHA256_Thumbprint(proof.header.jwk)
tokenJkt = verifiedAccessToken.cnf.jkt

if proofJkt != tokenJkt:
    reject request
~~~

Compare parsed and properly canonicalized values, not raw JWK JSON strings. If the access token lacks a confirmation binding while the request uses the `DPoP` scheme, never assume the token was bound.

## 6. HTTP Request to the Resource Server

A request using a DPoP-bound access token must carry **two headers**:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: DPoP ACCESS_TOKEN_VALUE
DPoP: SIGNED_DPOP_PROOF_JWT
Accept: application/json
~~~

Points to remember:

- The authentication scheme in `Authorization` is **DPoP**, not `Bearer`.
- The `DPoP` header holds a fresh proof JWT for the current request.
- The proof must include `ath` hashing the exact access token being sent.
- The proof must match the HTTP method and target URI.
- The access token and proof must bind to the same public key.

### 6.1. Do Not Swap `DPoP` and `Bearer`

If the access token was returned by the AS with `token_type=DPoP`, the client must send it using the `DPoP` scheme. Never send that token as `Authorization: Bearer` expecting the RS to infer a DPoP proof from another header. Similarly, an ordinary Bearer token cannot be upgraded to DPoP-bound merely by adding a proof header; the token must carry an AS-issued confirmation binding.

An RS may support both Bearer and DPoP, but must process each scheme according to the actual token type. Never allow a DPoP-bound token to fall through the Bearer authentication path when a proof is missing.

## 7. Verifying `ath`: The Proof Must Bind to the Exact Access Token

For protected resource requests, the `ath` claim is:

\[
ath = BASE64URL\_NO\_PADDING(SHA256(ASCII(access\_token)))
\]

Steps:

1. Extract the exact access token string from the `Authorization` header after parsing the `DPoP` scheme.
2. Encode the token value as ASCII per RFC 9449.
3. Compute SHA-256 over those bytes.
4. Base64URL-encode the result without padding.
5. Compare against the `ath` claim in the signature-verified proof.

### 7.1. Why Is `ath` Needed?

Suppose a client holds two access tokens `AT-A` and `AT-B`, both bound to the same key pair but representing different permissions or subjects. A proof that is not bound to the token could be captured from an `AT-A` request and attempted with `AT-B`. `ath` binds the proof to the **specific value** of the access token, mitigating token substitution.

`ath` does not replace `cnf.jkt`: the two checks answer different questions:

| Check | Question |
|---|---|
| `ath` | Was this proof created for the exact access token being sent? |
| `cnf.jkt` ↔ proof JWK thumbprint | Is the access token bound to the exact public key that signed the proof? |

## 8. Verifying `htm` and `htu`

A DPoP proof binds to the current HTTP request via two claims:

- `htm`: method, e.g., `GET`, `POST`, `PATCH`;
- `htu`: target URI without query and fragment.

For example, a proof created for:

~~~text
GET https://orders.example.com/api/orders/123
~~~

must not be accepted for:

~~~text
POST https://orders.example.com/api/orders/123
GET  https://billing.example.com/api/orders/123
GET  https://orders.example.com/api/orders/456
~~~

The RS must compare `htm` with the actual request method and `htu` with the actual target URI per RFC 9449/RFC 3986 URI normalization rules.

### 8.1. Query and Fragment Are Excluded from `htu`

`htu` strips the query and fragment. Example:

~~~text
Request URI:
https://orders.example.com/api/orders/123?expand=items#section

DPoP htu:
https://orders.example.com/api/orders/123
~~~

Because query parameters are not bound by `htu`, never treat query parameters as cryptographically authenticated inputs for sensitive decisions. If a query carries a resource identifier or business condition, the API must still perform authorization on the actual data and verify corresponding permissions.

### 8.2. Reverse Proxies and External URIs

In production, the RS often runs behind a load balancer/API gateway:

~~~text
Client
  -> https://api.example.com/orders/123
  -> ingress terminates TLS
  -> http://orders-service:8080/orders/123
~~~

The client signs `htu=https://api.example.com/orders/123`, while the internal application sees `http://orders-service:8080/orders/123`. If both sides do not agree on the external URI, valid proofs will be rejected; if the RS trusts `Forwarded`/`X-Forwarded-*` headers from arbitrary callers, an attacker can spoof host/scheme.

Design requirements:

- Accept forwarded headers only from authenticated proxies with a clear network boundary;
- Normalize scheme, host, port, and path according to the actual public URI;
- Never let clients set host headers to manipulate the URI the RS validates against;
- Test proxy prefixes, context paths, default ports, and URL normalization;
- Never disable `htu` checking just to work around proxy misconfigurations.

### 8.3. URI Normalization

RFC 9449 recommends syntax-based and scheme-based normalization prior to comparing `htu` to reduce false negatives. Apply consistent rules, and never write ad-hoc canonicalization that could collapse two distinct resources into the same URI.

## 9. Checking the `iat` Timestamp

`iat` indicates when the proof was created. The RS must reject proofs outside the accepted time window. The window is typically short—seconds or a few minutes depending on policy, clock skew, and nonce model.

Example:

~~~text
server time = 12:00:10
proof iat   = 12:00:08  -> may be valid within window
proof iat   = 11:40:00  -> too old, reject
proof iat   = 12:30:00  -> unreasonably in future, reject
~~~

Do not use hour-long TTLs for proofs. A proof is meant for one specific request, so a short lifetime shrinks the replay window.

### 9.1. Time Synchronization

RS and AS nodes must synchronize clocks. With large clock skew, valid proofs may be rejected or stale proofs accepted longer than intended. Use NTP/clock monitoring and set a deliberate clock-skew policy.

### 9.2. Server-Managed Nonces

If stricter recency control is required, the AS or RS can issue a nonce via the `DPoP-Nonce` response header. The client embeds that nonce in the next proof's `nonce` claim. Nonces are opaque values issued by **that exact server**; an AS nonce must never be carried to another RS and vice versa.

## 10. Replay Protection: `jti`, Cache, and Nonce

A captured proof can be replayed against the same endpoint/method within the `iat` window. DPoP therefore needs both a short window and reuse detection.

### 10.1. `jti` Must Be Sufficiently Random and Unique

RFC 9449 requires `jti` to have negligible collision probability within its context and validity period. Use at least 96 bits of pseudorandom data or a UUID version 4. The client must generate a fresh `jti` for every proof.

### 10.2. RS Recording Used Proofs

An implementation may store a replay key such as:

~~~text
replayKey = hash(jkt || jti || request-context)
value     = expiresAt
~~~

Upon receiving a proof:

1. Verify the proof before trusting its claims;
2. Build the replay key from the key identity and `jti`;
3. Atomically insert if absent;
4. If already present within the validity window, reject the replay;
5. Purge the record once the proof is guaranteed no longer acceptable.

Writes must be **atomic**. An `if-not-exists-then-put` pattern is unsafe when multiple concurrent requests check at the same time.

### 10.3. Multi-Node Deployments Need a Shared Replay Store

If a proof hits node A and is replayed to node B, per-node in-memory caches will not know the proof was already used. In clusters, use a distributed cache/store with atomic put-if-absent and matching TTLs.

Spring Security provides `DPoPProofReplayValidator` and `DPoPProofReplayValidator.InMemoryCache`; the API documentation explicitly states the in-memory cache is suitable only for a single node. Production clusters must deploy a suitable distributed cache rather than simply scaling out application instances.

### 10.4. Nonce and `jti` Do Not Replace Each Other

Server-issued nonces ensure proofs tie to a recent challenge. `jti` identifies individual proofs to prevent reuse. Per the RFC, a server may accept the same nonce across multiple proofs; uniqueness/replay control still relies on `jti` and timestamps.

## 11. Nonce Challenges and Client Retries

When the RS requires a nonce, a request lacking a valid nonce is rejected with:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: DPoP error="use_dpop_nonce", error_description="Resource server requires a nonce"
DPoP-Nonce: SERVER_ISSUED_NONCE
Cache-Control: no-store
~~~

The client must:

1. Read the nonce from `DPoP-Nonce`;
2. Create a **new proof JWT**, with a fresh `jti` and a `nonce` claim containing the server-supplied value;
3. Recompute `ath` for the access token in use;
4. Sign the proof with the private key bound to the token;
5. Resend the request within a reasonable retry cap.

Never resend the exact old proof while only altering headers. This nonce is neither the OIDC ID Token `nonce` nor OAuth `state`.

### 11.1. AS Nonces and RS Nonces Are Independent

The AS issues nonces for token endpoint requests; the RS issues nonces for protected-resource requests. Each server can maintain independent state, lifetimes, and policies. Clients should store nonces scoped per server/endpoint context and never share nonces across distinct issuers/resource servers.

### 11.2. Retries Must Not Duplicate Business Side Effects

If the RS requests a nonce after receiving a `POST` request with side effects, the client must handle retries according to the API's idempotency design. DPoP nonce challenges are normally returned during authentication before authorization/business handlers; however, clients must never assume every network error/challenge proves business logic did not execute. Use proper idempotency keys for write operations.

## 12. Verification Pipeline at the Resource Server

A testable pipeline should be structured into clear steps:

1. **Parse authentication scheme:** confirm the request uses `Authorization: DPoP`.
2. **Extract access token:** never read tokens from query parameters or body.
3. **Verify access token:** signature or introspection, issuer, expiry, audience, active status, and required policies.
4. **Extract confirmation binding:** read `cnf.jkt` from the verified JWT or trusted introspection result.
5. **Parse DPoP proof:** enforce a single `DPoP` header with one well-formed JWT.
6. **Verify proof header:** `typ=dpop+jwt`, allowed asymmetric `alg`, public-only JWK, valid signature.
7. **Verify request claims:** `htm`, `htu`, `iat`, `jti`, and `nonce` when required.
8. **Verify token binding:** proof JWK thumbprint equals `cnf.jkt`.
9. **Verify `ath`:** hash of the request's access token matches the `ath` claim.
10. **Prevent replay:** atomically insert `jti` into the replay store.
11. **Business authorization:** scope, role, tenant, resource ownership, and active policies.
12. **Return response:** never log raw access tokens/proofs; return a fresh nonce if policy requires.

### 12.1. Why Are Access Token Validation and Proof Validation Two Separate Tasks?

| Access Token Validation | DPoP Proof Validation |
|---|---|
| Was the token issued by a trusted issuer? | Was the proof signed by the matching private key? |
| Is the token unexpired/active? | Is the proof fresh and not replayed? |
| Is the token meant for this RS? | Is the proof meant for this HTTP method/URI? |
| Does the token hold the required scopes/claims? | Does the proof bind the exact access token and public key? |

Never skip access-token validation just because the proof is valid. A properly signed proof paired with an expired access token must still be rejected.

### 12.2. A DPoP Proof Is Not the User's Identity

The public key proves the client possesses the key pair, not who the end user is. User identity, tenant, and permissions still come from the verified access token and application data/policy. Never use the thumbprint as a user ID or substitute for `sub`.

## 13. Spring Security Resource Server

Spring Security has added DPoP components across releases. Distinguish between **having DPoP processing classes** and **having full filter-chain DSL integration**:

| Spring Security Version | DPoP Components | Integration Approach |
|---|---|---|
| **6.5.x** | Includes `DPoPAuthenticationProvider`, `DPoPAuthenticationToken`, `DPoPProofContext`, `DPoPProofJwtDecoderFactory`, `DPoPProofReplayValidator` | Requires version-specific wiring; no built-in Resource Server `dPoP(...)` DSL |
| **7.1+** | Adds `DPoPAuthenticationConverter` and `OAuth2ResourceServerConfigurer.DPoPConfigurer` | Provides `oauth2ResourceServer(...).dPoP(...)` DSL to enable DPoP-bound access token support |

This distinction matters when picking your Spring Boot BOM: do not copy a 7.1 configuration into a 6.5 project expecting it to compile.

### 13.1. Resource Server Configuration on Spring Security 7.1+

Example servlet Resource Server using JWT:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
            .dPoP(Customizer.withDefaults())
        );

    return http.build();
}
~~~

The example requires Resource Server and JOSE dependencies, issuer/JWKS configuration, and related beans. `jwt(...)` provides JWT access token verification; `dPoP(...)` enables DPoP-bound access token processing. Verify the actual configuration for your running version and run integration tests for the `DPoP` scheme, `cnf.jkt`, `ath`, `htu`, and replay.

If using opaque access tokens, configure token introspection instead of a JWT decoder and ensure the introspection result provides confirmation binding. Never use a custom decoder that fabricates `cnf.jkt` instead of trusted introspection.

### 13.2. Issuer Configuration for JWT

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.com
~~~

The Resource Server must still verify `iss`, signature, `exp`, `nbf`, audience, and system policy claims. DPoP does not replace those validators.

### 13.3. Spring Security 6.5: Low-Level Wiring

In 6.5, you can use `DPoPAuthenticationProvider` to verify a `DPoPAuthenticationToken` alongside a token authentication manager, but you must integrate request extraction/filter/entry point wiring yourself because the `dPoP(...)` DSL and `DPoPAuthenticationConverter` arrived in later versions.

Wiring diagram:

~~~text
HttpServletRequest
  -> custom AuthenticationConverter
  -> DPoPAuthenticationToken(accessToken, proof, method, resourceUri)
  -> AuthenticationManager
      -> DPoPAuthenticationProvider
          -> token AuthenticationManager (JWT or opaque)
          -> DPoPProofJwtDecoderFactory
          -> binding + proof validation
  -> SecurityContext
~~~

This is a wiring architecture, not copy-paste code. When implementing manually, preserve exact validation order, error/nonce handling, replay cache, response headers, and ensure no Bearer fallback path accepts DPoP-bound tokens. If you lack experience writing authentication filters, upgrade to a version with the official DSL or use a vetted implementation.

### 13.4. Spring's Replay Validator

`DPoPProofReplayValidator` controls proof reuse via a cache. `InMemoryCache` fits tests or a single node; clusters need a distributed cache with atomic put-if-absent and matching TTLs. Never derive cache keys from raw access tokens; store only necessary metadata such as a proof hash/identifier and expiration.

### 13.5. Do Not Drop Default Validators

If customizing `DPoPProofJwtDecoderFactory`, `JwtDecoder`, or providers:

- Preserve signature and public JWK verification;
- Preserve `typ`, `alg`, `htm`, `htu`, `iat`, `jkt`, `ath`, and `jti` validation;
- Preserve nonce validation when required by the server;
- Add custom validations without removing standard validators;
- Run independent negative tests to prove each condition is genuinely enforced.

## 14. Spring Authorization Server: Issuing DPoP-Bound Access Tokens

On the AS side, the client sends a DPoP proof in the header when calling the token endpoint. The AS verifies the proof per RFC 9449; if valid, the AS binds the issued access token to the proof's public key and returns `token_type=DPoP`.

Example:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Content-Type: application/x-www-form-urlencoded
DPoP: SIGNED_DPOP_PROOF_FOR_TOKEN_ENDPOINT

grant_type=authorization_code&code=AUTHORIZATION_CODE&redirect_uri=https%3A%2F%2Fportal.example.com%2Fcallback&code_verifier=PKCE_VERIFIER
~~~

Token endpoint proofs must have `htm=POST`, `htu` pointing to the actual token endpoint, `iat`, `jti`, and `nonce` if required by the AS. No access token is presented in this request, so `ath` is not required at this step.

Successful response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "REDACTED_DPOP_BOUND_ACCESS_TOKEN",
  "token_type": "DPoP",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

The AS must include the binding in the token or introspection metadata. For JWTs, the binding is typically:

~~~json
{
  "cnf": {
    "jkt": "BASE64URL_SHA256_JWK_THUMBPRINT"
  }
}
~~~

### 14.1. Binding Must Apply Across Supported Grants

DPoP proofs can be sent at the token endpoint for multiple grants such as Authorization Code, Refresh Token, and Client Credentials. The AS must apply the same proof verification and binding rules per policy for each corresponding grant. Do not secure only Authorization Code while accidentally letting Client Credentials or Refresh Token issue Bearer tokens.

### 14.2. Refresh Tokens and DPoP Keys

When the AS issues a DPoP-sender-constrained refresh token, subsequent refresh token usage also requires a proof matching that key binding. If a client loses its private key or rotates keys, refresh tokens bound to the old key cannot automatically transfer to the new key. The client needs a recovery/re-authorization flow per policy; never allow someone to simply supply a new public key to take over an old refresh token.

### 14.3. Metadata Discovery

The Authorization Server can advertise supported DPoP proof algorithms via metadata, e.g., `dpop_signing_alg_values_supported`. Clients should discover algorithms from a trusted issuer and choose from the advertised list. Never infer algorithms from a single token or caller-supplied configuration.

### 14.4. Custom Token Generation

In DPoP-capable Spring Authorization Server versions, the token context can carry proof key information (such as `OAuth2TokenContext.DPOP_PROOF_KEY` in the matching API version). When customizing a customizer or token generator:

- Never overwrite `cnf.jkt` produced by the DPoP mechanism;
- Never copy `jwk` from the request without proof verification;
- Never issue `token_type` Bearer when the token is DPoP-bound;
- Ensure both JWT and opaque/introspection paths preserve the binding;
- Test both the response `token_type` and the `cnf` contents.

Token context APIs change across Spring Security/Authorization Server versions; verify your dependency BOM and version Javadoc before writing customizers.

## 15. JWT and Opaque Access Tokens

The RS can obtain binding information in two ways:

| Issuance Format | How Does the RS Verify Binding? | What Must Be Protected |
|---|---|---|
| JWT access token | Verify JWT signature, issuer, time, audience; read verified `cnf.jkt` | JWKS, key rotation, claim validation |
| Opaque access token | Call introspection; check `active` and confirmation metadata | Introspection credentials, TLS, cache, and availability |

Opaque tokens do not mean the RS skips proof checks. The RS still needs `cnf.jkt` (or equivalent binding) from introspection and compares it against the public key in the DPoP proof. If introspection does not return binding metadata, the RS has no basis to prove the token is bound to the proof key.

### 15.1. Do Not Mix Bearer and DPoP Semantics

An ordinary access token without `cnf.jkt` is a Bearer token. A token with `cnf.jkt` is sender-constrained. Never automatically treat all tokens from an issuer as DPoP-bound; the RS must inspect actual token type/binding. Conversely, never accept a DPoP-bound token on the Bearer path merely because its JWT signature is valid.

## 16. Verification Errors and HTTP Responses

Errors can occur at the AS token endpoint or RS protected resource:

| Error | Example | Handling |
|---|---|---|
| Missing/malformed proof | Missing `DPoP` header, multiple `DPoP` headers, malformed JWT | Reject authentication |
| Wrong `typ` | Not `dpop+jwt` | Reject proof |
| Invalid `alg` | `none`, HMAC, disallowed algorithm | Reject proof |
| Private JWK or bad signature | Proof fails verification with public JWK | Reject proof |
| `htm`/`htu` mismatch | Proof signed for `POST` on a `GET` request | Reject proof |
| Stale proof | `iat` outside window | Reject proof |
| Missing/wrong nonce | RS requires a fresh nonce | Challenge `use_dpop_nonce` and `DPoP-Nonce` |
| Replay | `jti` already used | Reject proof |
| Key binding mismatch | `cnf.jkt` differs from proof JWK thumbprint | Reject access |
| `ath` mismatch | Proof created for another token | Reject request |
| Invalid token | Bad issuer/signature/audience/expired/inactive | Reject token |
| Insufficient scope/authorization | Proof and token valid but lacking permissions | Reject authorization (typically 403) |

Do not collapse all errors into `invalid_token`. Categorization tells clients when to request a new nonce, when to acquire a different token, and when to fix policy issues. However, never expose sensitive details about keys, tokens, accounts, or internal policies inside error bodies.

### 16.1. Nonce Challenge at the Resource Server

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: DPoP error="use_dpop_nonce", error_description="A fresh DPoP nonce is required"
DPoP-Nonce: NEW_OPAQUE_NONCE
~~~

The client creates a new proof containing `nonce=NEW_OPAQUE_NONCE`, a fresh `jti`, and recomputed `ath` for the access token being sent. Never use this nonce at the AS or another RS.

### 16.2. Distinguishing 401 and 403

- **401 Unauthorized:** authentication has not been established—access token/proof/binding is invalid or a nonce challenge must be satisfied.
- **403 Forbidden:** authentication succeeded, but principal/scope/tenant/business policy forbids the action.

A request with a valid proof that lacks `orders.write` must still be rejected at authorization; never prompt the client to generate a new proof to fix a missing scope error.

## 17. Security Limitations and Safe Deployment Practices

### 17.1. TLS Remains Mandatory

DPoP does not replace HTTPS. TLS protects token/proof confidentiality in transit and authenticates the server endpoint. If a client sends proofs to an impostor server, an attacker can harvest tokens or abuse the flow. Verify certificates, issuers, and endpoint discovery.

### 17.2. Protecting the Client-Side Private Key

- Generate keys with a CSPRNG and store them in platform-appropriate secure storage/keystore;
- Prefer hardware-backed/non-exportable keys when supported by the platform;
- Never write private keys to logs, config files, insecure local storage, or analytics;
- Establish procedures for key loss/rotation and new token issuance;
- Scope keys per client instance/device or appropriate boundary, avoiding a single org-wide private key unnecessarily;
- Delete keys on logout/device decommission per policy, understanding issued tokens still need expiry/revocation.

### 17.3. Replay Cache Must Be Bounded

An attacker can send proofs with extremely long `jti` values or flood proofs to exhaust cache memory. Enforce claim length limits, proof size limits, per-key request bounds, TTLs, memory/cache capacity, and rate limits. Store hashes of `jti`/identifiers where appropriate to avoid storing raw data.

### 17.4. Reverse Proxies Are Part of the Trust Boundary

If the RS uses forwarded headers to reconstruct `htu`, trust only authenticated/allowlisted proxies. Proxies must strip client-supplied forwarded headers from the Internet and rewrite canonical values. Otherwise, attackers can control the external URI used by the RS for verification.

### 17.5. Never Log Credentials

Never log raw access tokens, DPoP proof JWTs, `Authorization` headers, private keys, nonces, or full requests containing sensitive data. You may log pseudonymized `kid`/thumbprints, result codes, endpoints, request correlation IDs, and latencies per policy.

### 17.6. DPoP Does Not Sign Request Bodies

`htm` and `htu` bind the proof to method and URI (excluding query/fragment); `ath` binds to the access token. JSON bodies, query parameters, and other headers are not automatically signed by DPoP. APIs needing payload tamper protection must rely on TLS and appropriate authorization/business validation; never claim DPoP provides full HTTP message integrity.

## 18. Testing Coordination Between Authorization Server and Resource Server

Tests must prove that **issued tokens carry binding**, clients generate valid proofs, and the RS rejects every critical mismatch. Unit testing the `ath` hash function alone does not prove the filter chain enforces DPoP.

### 18.1. Test Matrix

| Case | Outcome to Verify |
|---|---|
| Token endpoint receives valid proof | Returns access token with `token_type=DPoP` |
| Issued JWT access token | Has `cnf.jkt` matching the proof's public key |
| Issued opaque token | Introspection returns binding metadata verifiable by RS |
| RS receives DPoP token + valid proof | Authentication succeeds; proceeds to scope/business authorization |
| Proof signed by a key different from token binding | Rejected |
| Proof missing `ath` when calling resource | Rejected |
| `ath` hashes a different token | Rejected |
| `htm` mismatches request | Rejected |
| `htu` has wrong host/path/scheme | Rejected |
| `htu` differs only by query | Query/fragment stripping applies; API still enforces data permissions |
| Proof `iat` too old/future | Rejected |
| Already-used `jti` | Replay rejected |
| Two nodes receive the same proof concurrently | Shared replay store lets only one request succeed |
| Nonce required but missing | Returns `use_dpop_nonce` and `DPoP-Nonce` |
| Client retries with new nonce, new `jti` | Succeeds if all other conditions pass |
| Public JWK contains private field | Proof rejected |
| Wrong `typ` or `alg=none` | Proof rejected |
| DPoP-bound token sent as Bearer | Rejected by Bearer path |
| Bearer token sent with proof lacking `cnf.jkt` | Does not elevate token into DPoP-bound |
| Token expired/wrong issuer/wrong audience | Rejected even with valid proof |
| Token/proof valid but insufficient scope | 403 per policy |
| Private key lost | Old token unusable with another key; requires reauthorization/reissue |
| DPoP proof/token logged | Tests/scanners catch and eliminate sensitive logging |

### 18.2. MockMvc Request-Shape Test

Example test skeleton with Spring Security 7.1+:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class DPoPResourceServerTests {

    @Autowired
    MockMvc mvc;

    @Test
    void acceptsDpopBoundTokenWithMatchingProof() throws Exception {
        String accessToken = fixtureDpopBoundAccessToken();
        String proof = fixtureProofFor(
            accessToken,
            "GET",
            "https://orders.example.com/api/orders/123");

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION, "DPoP " + accessToken)
                .header("DPoP", proof))
            .andExpect(status().isOk());
    }
}
~~~

This is a **test skeleton** requiring fixtures that generate properly signed and bound access tokens, proofs signed by the matching private key, accurate `ath`, `htu` matching the external request, and a clean replay store. When running behind a proxy or if MockMvc uses a different host/path, the fixture URI must match the URI the application actually validates.

### 18.3. Negative Binding Test

1. Issue access token `AT1` bound to key `K1`;
2. Create proof `P2` signed with key `K2`;
3. Send `AT1` together with `P2`;
4. Verify the RS rejects even though `P2`'s signature is completely valid.

This test proves the RS compares `cnf.jkt` against the proof JWK thumbprint rather than merely checking whether the proof has a valid signature.

### 18.4. Negative `ath` Test

1. Issue `AT1` and `AT2`;
2. Create a proof with `ath=hash(AT1)`;
3. Send that proof together with `AT2`;
4. The RS must reject.

Keep key, method, URI, and timestamp identical so the test fails solely due to `ath`, avoiding requests with multiple simultaneous errors where you cannot tell which validator triggered.

### 18.5. Testing Replay and Nonce

Send the same proof twice within the `iat` window. The first may succeed; the second must be rejected if replay detection is enabled per policy. For nonce challenges, verify RS nonces are rejected at the AS and vice versa. In a cluster, send the first request to node A and the second to node B to prove the cache is shared.

## 19. Operations and Monitoring

| Metric/Event | Purpose | Never Record |
|---|---|---|
| `dpop_proof_valid` / `invalid` | Track valid proof ratio | Raw proof JWT |
| `dpop_binding_mismatch` | Detect token/proof key mismatches | Access token |
| `dpop_ath_mismatch` | Detect proofs paired with wrong tokens | Token value |
| `dpop_htu_mismatch` | Detect proxy/canonical URI errors or altered requests | Full URL with PII queries |
| `dpop_iat_out_of_window` | Detect clock skew/stale proofs | Private key |
| `dpop_replay_detected` | Track replays | Raw `jti` if unnecessary |
| `dpop_nonce_challenge` | Measure nonce challenge frequency | Raw nonces in broad logs |
| Replay cache latency/capacity | Detect slow/full caches | Cache dumps |
| Token type/binding distribution | Track Bearer vs. DPoP adoption | Raw tokens |
| Key thumbprint rotation | Track client key lifecycle | Private key material |

### 19.1. Cluster and Consistency

All RS nodes must use a replay store with consistent semantics. If node A accepts `jti=J1`, node B must know `J1` has already been used within the validity window. If the distributed cache becomes unavailable, policy must specify fail-closed behavior for sensitive endpoints or an explicitly evaluated fallback; never silently drop replay protection.

### 19.2. Key Rotation Incidents

When a client loses or rotates its DPoP key:

- Old tokens remain bound to the old thumbprint;
- Proofs signed by the new key will not match `cnf.jkt`;
- The client typically must obtain new tokens via an AS-allowed flow;
- Never patch `cnf.jkt` of an already-issued token to point to the new key.

### 19.3. Observability Across AS and RS

The AS should track DPoP token issuance, proof/nonce errors, and proof algorithms; the RS tracks binding mismatches, replays, `ath`/`htu` mismatches, and authorization failures. Correlation IDs can link both sides, but raw access tokens or proofs must never flow into telemetry.

## 20. Production Deployment Checklist

1. **Key lifecycle:** does the client generate and protect private keys using proper secure storage?
2. **Token binding:** does the AS verify DPoP proofs at the token endpoint and attach `cnf.jkt` or introspection binding?
3. **Token type:** does the AS return `token_type=DPoP`; does the client use the `DPoP` scheme when calling the RS?
4. **Proof header:** does the RS enforce a single `DPoP` header, `typ=dpop+jwt`, asymmetric `alg`, and public-only JWK?
5. **Signature:** is the proof verified using the exact public JWK in the header?
6. **Key binding:** does the proof JWK thumbprint match `cnf.jkt` of the verified access token?
7. **Token validation:** are issuer, signature/introspection, `exp`, `nbf`, audience, scope, and active state still checked?
8. **Request binding:** are `htm`, `htu`, URI normalization, and external URIs behind proxies accurate?
9. **Access-token hash:** is `ath` equal to unpadded Base64URL of SHA-256 over the ASCII token value?
10. **Freshness:** is `iat` within a short window, with clocks synchronized?
11. **Replay:** is `jti` sufficiently random, and is the cache atomic and shared across nodes?
12. **Nonce:** are AS/RS nonces isolated, and do clients retry with fresh proofs?
13. **Opaque tokens:** does introspection return confirmation binding, and does the RS trust the right source?
14. **Spring version:** are you using version-matched DPoP DSLs without copying 7.1 APIs into 6.5?
15. **Proxy:** are forwarded headers trusted only from configured proxies?
16. **Testing:** are there negative tests for key mismatch, `ath`, `htm`, `htu`, expiry, nonces, and replay?
17. **Observability:** are tokens, proofs, private keys, and sensitive nonces excluded from logs?
18. **Incident response:** are procedures ready for exposed keys, lost client keys, replay cache outages, or compromised tokens?

## 21. Applied Exercises

**Scenario A — Stolen token:** An attacker extracts a DPoP-bound access token from logs without the private key. Explain why Bearer replay is no longer sufficient for access and what the RS must verify.

**Scenario B — Binding mismatch:** A token has `cnf.jkt=JKT-A`, while the proof contains a public JWK with thumbprint `JKT-B`, yet the proof signature is valid. What should the RS return and why?

**Scenario C — Two concurrent requests:** The exact same proof with `jti=J1` is sent to two RS nodes. Why is a local in-memory cache insufficient? How would you design an atomic replay store?

**Scenario D — Reverse proxy:** A client signs `htu=https://api.example.com/v1/orders/1`; the internal app observes `http://orders-service:8080/v1/orders/1`. Design how to verify the external URI and the trust boundary of forwarded headers.

**Scenario E — Nonce challenge:** The RS returns `DPoP-Nonce`. Why must the client create a new proof with a new `jti`? Can an RS nonce be used at the AS?

**Hints:** A requires proof key, token binding, `ath`, `htm`, `htu`, `iat`, and replay checks. B must be rejected due to binding mismatch. C needs a shared store with atomic insert-if-absent and TTL. D needs a trusted proxy supplying canonical external URIs; never trust client-supplied forwarded headers. E requires a new proof with the new nonce and a fresh `jti`; nonces are valid only at the server that issued them.

## 22. Summary

**DPoP (RFC 9449)** binds OAuth access tokens to a client's public key. The AS verifies the proof at the token endpoint, computes the JWK thumbprint, and attaches it to the token via `cnf.jkt` or introspection metadata. The client then sends the access token with the `DPoP` authentication scheme in the `Authorization` header, alongside a `DPoP` header carrying a fresh proof per request.

The **Resource Server** must verify the access token, proof JWT, public-key thumbprint binding, `ath`, `htm`, `htu`, `iat`, nonces when required, and replay state via `jti`. After authentication succeeds, the RS must still enforce scopes, audience, and business permissions.

In Spring Security, DPoP support evolves across versions: 6.5 provides foundational providers/validators; the Resource Server `dPoP(...)` DSL and integrated converter arrived in 7.1. When deploying, choose APIs matching your BOM and test end-to-end from AS to RS, especially in reverse-proxy and multi-node environments.

DPoP mitigates the risk of stolen tokens being reused like Bearer tokens, but only works effectively when private keys are protected, proofs are thoroughly validated, replay stores are consistent, and the entire system continues enforcing TLS and proper authorization policies.

## 23. References

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP proof, token binding, `cnf.jkt`, `ath`, nonces, protected-resource validation, and replay.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638): computing the thumbprint of a public JWK.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWT signatures, Base64URL, and JOSE headers.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): public JWKs and key members.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, access tokens, and error responses.
- [Spring Security — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html): DPoP requests, `cnf.jkt`, `ath`, and Resource Server.
- [Spring Security 6.5 — What's New](https://docs.spring.io/spring-security/reference/6.5/whats-new.html): milestone introducing DPoP support in Spring Security 6.5.
- [Spring Security — Protocol Endpoints](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/protocol-endpoints.html): DPoP-bound token support at the Authorization Server and token endpoint.
- [Spring Security API — DPoPAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/api/java/org/springframework/security/oauth2/server/resource/authentication/DPoPAuthenticationProvider.html): provider verifying DPoP-bound protected-resource requests.
- [Spring Security API — DPoPConfigurer](https://docs.spring.io/spring-security/reference/7.1-SNAPSHOT/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.DPoPConfigurer.html): Resource Server DPoP DSL from Spring Security 7.1.
