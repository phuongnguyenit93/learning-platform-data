# DPoP Capabilities, RFC 9068, and Version-Dependent Features

Spring Security Resource Server normally authenticates access tokens using the Bearer model: the client sends a token, the server verifies it, and the request is accepted if claims and permissions match. This model has an inherent limitation: anyone who obtains a bearer token can attempt to replay it until it expires or is revoked.

Two notable extension standards solve different problems:

- **DPoP — RFC 9449:** binds an access token to a client key pair. Each request must carry a proof JWT demonstrating that the client possesses the matching private key.
- **JWT Profile for OAuth 2.0 Access Tokens — RFC 9068:** standardizes JWT access token structure—including token type, required claims, and validation rules—so Authorization Servers and Resource Servers interoperate reliably.

Spring Security added APIs for both capabilities across successive releases. Upgrading from an older Security version to a newer one can introduce new validators, authentication providers, or converters; however, do not assume every version exposes identical APIs or identical Servlet/Reactive integration depth.

This lesson explains the protocols, how Spring Security supports them, notable version milestones, configuring RFC 9068, constructing DPoP proofs, deployment risks, and the test suite required before enabling these features in production.

> **Important distinction:** RFC 9068 defines JWT access tokens and how a Resource Server validates them. DPoP defines how to bind a token to a client's key and prove key possession on every request. An access token can simultaneously conform to RFC 9068 and be DPoP-bound.

## 1. Map of Standards and Components

| Component | Standard or API | Responsibility |
|---|---|---|
| JWT access token profile | RFC 9068 | Standardizes headers, claims, and validation for JWT access tokens |
| DPoP | RFC 9449 | Sender-constrains access tokens to a client's public key |
| JWT/JWS/JWK | RFC 7519, RFC 7515, RFC 7517 | Token claims, signatures, and key representations |
| Spring JWT decoder | `JwtDecoder` / `NimbusJwtDecoder` | Verifies signatures and decodes access tokens |
| RFC 9068 validator | `JwtValidators.createAtJwtValidator()` | Validates tokens against the RFC 9068 profile |
| DPoP authentication provider | `DPoPAuthenticationProvider` | Authenticates DPoP-bound access tokens |
| DPoP proof decoder factory | `DPoPProofJwtDecoderFactory` | Builds decoders and validators for proof JWTs |
| DPoP request converter | `DPoPAuthenticationConverter` | Extracts DPoP tokens/proofs from Servlet requests |
| DPoP replay validator | `DPoPProofReplayValidator` | Blocks replayed proof JWTs |
| OAuth2 Client / Authorization Server | Token endpoint and HTTP client integration | Generates/sends proofs and issues DPoP-bound tokens |

A complete system requires coordination across at least three parties:

```mermaid
flowchart LR
    C["OAuth2 Client"] -->|"DPoP proof + token request"| AS["Authorization Server"]
    AS -->|"Access token bound to public key"| C
    C -->|"Authorization: DPoP + DPoP proof"| RS["Resource Server"]
    RS -->|"Verify token, proof and key binding"| RS
    RS -->|"Authorize scope and business access"| API["Protected API"]
```

The Authorization Server binds the token to a public key. The client holds the private key and creates a proof for each request. The Resource Server verifies both the access token and the proof before constructing `Authentication`.

## 2. What Problem Does DPoP Solve?

With a standard Bearer token, a request looks like:

```http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Anyone who intercepts that token string can resend it. The JWT signature proves the Authorization Server issued the token, not that the presenter is the original client.

DPoP adds proof of key possession:
- The client generates a public/private key pair.
- The client sends a DPoP proof when requesting an access token.
- The Authorization Server records the public key's thumbprint and binds the access token to that key.
- When calling the Resource Server, the client sends the access token alongside a fresh proof JWT.
- The Resource Server verifies the proof was signed by the private key matching the public key bound to the access token.

A stolen access token alone is therefore unusable without the corresponding private key.

### 2.1. DPoP Is Application-Layer Sender-Constraining

DPoP uses a proof JWT inside an HTTP header. It does not replace TLS and does not encrypt request bodies. TLS remains essential to protect tokens, proofs, and payloads in transit.

Nor does DPoP prevent tokens from being stolen. Rather, it makes a stolen token far harder to abuse standalone because an attacker also needs the private key and must mint a proof matching the target request.

### 2.2. How DPoP Differs from mTLS

| Characteristic | DPoP | OAuth mTLS |
|---|---|---|
| Proof mechanism | Proof JWT signed by the client's private key | Client certificate in the TLS handshake |
| Request binding | Proof includes method, URI, and token hash | Binds token to certificate thumbprint |
| TLS termination dependency | Does not require per-hop client TLS certificates, though TLS is still required | Certificates must be handled properly at the TLS endpoint |
| Portability | Works across diverse HTTP stacks when proofs are built properly | Depends on certificate management and TLS |
| Replay protection | Uses timestamps, `jti`, nonce, and replay cache | TLS channel binding has different properties |
| Spring integration | DPoP Resource Server APIs by version | OAuth mTLS support and client cert config by version |

Choose the mechanism based on topology, key/certificate lifecycle capabilities, and security requirements. Never treat DPoP as a substitute for TLS.

## 3. DPoP Flow from Token Endpoint to Resource Server

### 3.1. Client Requests an Access Token

The client sends a DPoP proof in the `DPoP` header to the token endpoint:

```http
POST /oauth2/token HTTP/1.1
Host: issuer.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: <SIGNED_DPOP_PROOF>

grant_type=authorization_code&
code=...&
redirect_uri=...&
client_id=orders-web
```

The token-request proof typically includes:
- Header `typ` equal to `dpop+jwt`.
- Header `alg` set to an accepted asymmetric signature algorithm.
- Header `jwk` containing the client's public JWK.
- Claim `htm` set to `POST`.
- Claim `htu` set to the token endpoint URI.
- Claim `iat` set to the proof creation timestamp.
- Claim `jti` set to a unique identifier for the proof.

A token-request proof is not yet paired with an issued access token, so it omits the `ath` claim.

If the Authorization Server accepts the proof, it binds the client's public key to the access token. The response sets `token_type` to `DPoP`:

```http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "<ACCESS_TOKEN>",
  "token_type": "DPoP",
  "expires_in": 300
}
```

The client must store the access token together with its matching private key. If a token is bound to key A, proofs signed with key B will fail.

### 3.2. Client Calls a Protected Resource

When calling an API, the client creates a fresh proof for that exact request:

```http
GET /api/orders?state=open HTTP/1.1
Host: api.example.test
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <NEW_SIGNED_DPOP_PROOF>
```

The proof must bind to:
- The current HTTP method.
- The current HTTP target URI, stripping query and fragment when constructing `htu`.
- The proof creation time.
- A fresh `jti`.
- The hash of the access token in the `ath` claim.
- A `nonce` if the server required one.

Every request requires its own proof. Never cache and reuse a proof JWT across multiple requests.

### 3.3. What Must the Resource Server Verify?

The Resource Server must:
1. Validate the access token for issuer, audience, signature, expiry, and policy.
2. Verify the proof JWT signature using the public JWK in its header.
3. Verify the proof type is `dpop+jwt` and its algorithm is allowed.
4. Compare `htm` against the actual HTTP method.
5. Compare `htu` against the normalized request URI per spec rules.
6. Verify `iat` falls within the allowed time window.
7. Verify `jti` has not been seen before per replay policy.
8. If the server issued a nonce, verify the `nonce` in the proof.
9. Recompute the hash of the access token and compare it against `ath`.
10. Compare the thumbprint of the proof's public key against the key bound to the access token.

After DPoP authentication succeeds, Spring Security still enforces normal authorization: scopes, roles, method security, tenant checks, and object-level policies.

## 4. Structure of a DPoP Proof JWT

### 4.1. JOSE Header

Decoded header example:

```json
{
  "typ": "dpop+jwt",
  "alg": "RS256",
  "jwk": {
    "kty": "RSA",
    "e": "AQAB",
    "n": "<PUBLIC_MODULUS>"
  }
}
```

Points to remember:
- `typ` must be `dpop+jwt`.
- `alg` must be a supported and permitted asymmetric signature algorithm.
- `alg=none` must never be accepted.
- `jwk` must contain only public key material.
- Never place private exponents or private EC scalars inside the proof header.
- Never trust a JWK solely because it appears in a proof; verify both the signature and its binding to the access token.

The public JWK in the proof is the client's key proving possession. It is distinct from the Authorization Server's public signing key used to verify the access token signature.

### 4.2. Core Claims

```json
{
  "jti": "f5b52b5e-4db3-4cb5-9f6d-4a6a7f2b2f7e",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders",
  "iat": 1794744000
}
```

| Claim | Meaning | Verification |
|---|---|---|
| `jti` | Unique proof identifier | Must not repeat within the replay window |
| `htm` | Request HTTP method | Must match the actual method |
| `htu` | HTTP target URI without query or fragment | Must match the normalized request URI |
| `iat` | Proof creation timestamp | Must lie within the allowed time window |
| `ath` | Access token hash | Required when a proof accompanies an access token to a protected resource |
| `nonce` | Server-issued nonce | Required when the server has demanded a nonce |

`jti` requires high entropy. UUID v4 or at least 96 bits of random data is appropriate. Never use a bare timestamp as `jti` since multiple requests can arrive within the same time unit.

### 4.3. The `ath` Claim

When a proof accompanies an access token to a Resource Server, `ath` is the unpadded Base64URL encoding of the SHA-256 digest over the ASCII bytes of the access token:

```java
String accessTokenHash(String accessToken)
        throws NoSuchAlgorithmException {

    byte[] tokenBytes =
        accessToken.getBytes(StandardCharsets.US_ASCII);

    byte[] digest =
        MessageDigest.getInstance("SHA-256").digest(tokenBytes);

    return Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(digest);
}
```

Do not hash the JWT payload or decoded claims. `ath` is computed over the exact serialized access token string sent in the `Authorization` header.

### 4.4. The `cnf.jkt` Binding Claim

A JWT access token can carry:

```json
{
  "cnf": {
    "jkt": "<JWK_SHA256_THUMBPRINT>"
  }
}
```

`jkt` is the SHA-256 JWK thumbprint of the DPoP public key. The Resource Server compares this thumbprint against the public key in the DPoP proof.

If the access token is opaque, the Resource Server can obtain binding metadata from the introspection response. Whether using JWT or opaque tokens, the server must have a trusted way to identify the bound public key.

### 4.5. Proof Tokens and Access Tokens Are Two Distinct JWTs

| Property | Access Token JWT | DPoP Proof JWT |
|---|---|---|
| Purpose | Represents the authorization grant | Proves possession of the client key for a single request |
| `typ` | May be `at+jwt` if following RFC 9068 | `dpop+jwt` |
| Issuer | Authorization Server | Generated by the client |
| Signature | AS signing key | Client DPoP private key |
| Claims | `iss`, `aud`, `sub`, `exp`, `iat`, `jti`, `client_id`, `scope`... | `htm`, `htu`, `iat`, `jti`, `ath`, `nonce` |
| Lifetime | Typically minutes or per policy | Very short, bound to a single request |
| Reuse | Reusable across requests within lifetime if Bearer; DPoP-bound needs fresh proofs | Never reused |

## 5. Nonce and Replay Protection

### 5.1. Why Is Replay Protection Required?

`htm` and `htu` prevent a proof from being reused on another endpoint or method. `ath` binds the proof to a specific access token. However, if an attacker captures both the proof JWT and access token, they can attempt to replay that proof against the same endpoint while the proof remains valid.

DPoP therefore requires:
- A tight `iat` window.
- Unique `jti` values.
- A replay cache to reject previously seen `jti` values.
- Server nonces when deployments require tighter proof-freshness enforcement.

### 5.2. Replay Cache

The server stores used `jti` values for as long as a proof remains acceptable. If the same `jti` reappears within the replay window, the request is rejected.

An in-memory cache shares state only among threads in a single process. Across multiple instances:
- Two instances can receive the same proof in closely spaced requests.
- Without a shared cache, one instance will not know the proof was already spent on another.
- Replay protection therefore requires a shared cache or equivalent synchronization.
- Check-and-record must be atomic so two concurrent requests cannot both pass.

Spring Security includes `DPoPProofReplayValidator` starting in 6.5.12. The API offers `DPoPProofReplayValidator.InMemoryCache`, though documentation explicitly notes its single-node limitation. Production clusters should use a distributed cache such as Redis or Hazelcast suited to the deployment topology.

### 5.3. `DPoP-Nonce`

An Authorization Server or Resource Server can return a `DPoP-Nonce` header. The client includes the latest nonce in the `nonce` claim of subsequent proofs.

Example server nonce challenge:

```http
HTTP/1.1 400 Bad Request
DPoP-Nonce: <SERVER_NONCE>
Content-Type: application/json

{
  "error": "use_dpop_nonce",
  "error_description": "A fresh DPoP nonce is required"
}
```

The client mints a fresh proof containing the received nonce and retries per protocol. Nonces are opaque values; clients must never try to interpret or fabricate them.

Never retry indefinitely:
- Bound the number of nonce challenge retries.
- Update the stored nonce from the latest response.
- Never send an Authorization Server's nonce to a different Resource Server.
- Never share nonces across issuer/resource contexts unless permitted by protocol.
- Generate a fresh `jti` for every retry proof.

## 6. URIs and Reverse Proxies Are Common Failure Points

DPoP proofs bind to `htu`. If the client signs the public URI while the Resource Server observes an internal URI behind a reverse proxy, the two values diverge.

Example:
- Client calls `https://api.example.test/api/orders`.
- Load balancer forwards to `http://orders-service:8080/api/orders`.
- The Servlet request may observe the internal scheme/host if forwarded headers are not handled properly.

In that scenario, the proof's signature is valid, yet `htu` comparison fails.

You must:
1. Identify the canonical external URI used by clients.
2. Configure controlled forwarded-header handling.
3. Trust `Forwarded`/`X-Forwarded-*` headers only from authenticated/trusted proxies.
4. Prevent callers from spoofing headers to alter host/scheme.
5. Apply RFC 3986 URI normalization before comparison.
6. Test path prefixes, ports, schemes, and trailing slashes.
7. Exclude queries and fragments from `htu`.

In multi-hop proxy topologies, document which hop rewrites host, scheme, and path. Never blindly trust forwarded headers from arbitrary request sources.

## 7. Spring Security DPoP Support by Version

DPoP APIs follow specific version milestones. When reading examples, verify the exact Spring Security version managed by Spring Boot.

| API or Capability | Spring Security Milestone | Significance |
|---|---:|---|
| DPoP Resource Server building blocks | 6.5 | Provides `DPoPAuthenticationProvider`, `DPoPAuthenticationToken`, and `DPoPProofJwtDecoderFactory` |
| DPoP proof decoder factory | 6.5 | Builds `JwtDecoder` from `DPoPProofContext` |
| RFC 9068 validator builder | 6.5 | `JwtValidators.createAtJwtValidator()` |
| `DPoPProofReplayValidator` | 6.5.12 | Replay protection validator with `jti` cache |
| `DPoPAuthenticationConverter` | 7.1 | Converts Servlet requests into `DPoPAuthenticationToken` |
| DPoP default proof validation | Patch-dependent changes | Validates `htm`/`htu`/`iat`/`jti`/`jkt`/`ath` per active patch API |
| DPoP Resource Server reference | 6.5, 7.0, 7.1 | Dedicated reference pages per release line |
| RFC 9068 Servlet/Reactive examples | 6.5+ in current docs | `NimbusJwtDecoder` and `NimbusReactiveJwtDecoder` |

These milestones reflect the API documentation at the time of writing. Patch releases can add validators, adjust defaults, or introduce helpers. Always verify the API docs for your exact patch version before copying code.

### 7.1. Building Blocks for a DPoP Resource Server

Key classes:

- `DPoPAuthenticationProvider`: `AuthenticationProvider` validating DPoP-bound access tokens.
- `DPoPAuthenticationToken`: `Authentication` request/representation for DPoP-protected resource requests.
- `DPoPProofContext`: context passing proof and access token details.
- `DPoPProofJwtDecoderFactory`: creates decoders for DPoP proofs.
- `DPoPAuthenticationConverter`: extracts DPoP credentials from `HttpServletRequest`; available starting in Security 7.1.
- `DPoPAuthenticationEntryPoint`: handles authentication challenges for DPoP requests.
- `DPoPProofReplayValidator`: verifies proof `jti` values have not been replayed.

`DPoPAuthenticationProvider` accepts an `AuthenticationManager` to validate the access token and then processes the proof context. The default proof decoder factory supplies validation for proof JWTs; applications can replace the validator factory when extra policies are needed.

### 7.2. `DPoPAuthenticationConverter` Is Available Only Since 7.1

If code uses `DPoPAuthenticationConverter`, Spring Security 7.1 or newer is required. The converter inspects a Servlet request and extracts the DPoP-bound token/proof into a `DPoPAuthenticationToken`.

On 6.5 or 7.0, do not assume this class exists. Use that version's integration mechanism or write a converter matching the contract. Never copy an import from 7.1 docs into a 6.5 project and try to patch around it by adding a single stray JAR.

### 7.3. The Replay Validator Has Its Own Patch Milestone

`DPoPProofReplayValidator` was introduced in 6.5.12. On 6.5.0–6.5.11:
- Inspect the default validators of `DPoPProofJwtDecoderFactory` in that patch.
- Verify `jti` is checked per replay policy.
- If a single-use replay cache is needed, upgrade to a patch with support or implement a compatible validator.
- Do not assume the class exists merely because the project uses Security 6.5.

Earlier 6.5 API docs described the default proof validator checking `htm`, `htu`, `jti`, and `iat`. Newer API docs also include `jkt` and `ath` in the default validator factory. This clearly illustrates why patch-level behavior must be verified.

### 7.4. Do Not Assume Parity Between Servlet and Reactive

Current DPoP Resource Server documentation resides under Servlet, and `DPoPAuthenticationConverter` takes `jakarta.servlet.http.HttpServletRequest`. Meanwhile, RFC 9068 includes dedicated examples for `NimbusReactiveJwtDecoder`.

This means:
- RFC 9068 validators work in both Servlet and Reactive JWT decoders.
- Do not assume DPoP Reactive integration exists merely because JWT Reactive Resource Server exists.
- If a WebFlux application needs DPoP, check the exact API in your target version; if no built-in integration exists, design and test a custom reactive authentication path.
- Never call a blocking DPoP decoder/cache from the Netty event loop.

## 8. Integrating DPoP Proofs in Spring

Spring Security provides building blocks to generate and verify DPoP proofs. Clients still remain responsible for key management and producing a valid proof per request.

Example generating a token-endpoint proof with `NimbusJwtEncoder`:

```java
RSAKey dpopKey = ...; // private key stays on the client

JWKSource<SecurityContext> jwkSource =
    (selector, context) ->
        selector.select(new JWKSet(dpopKey));

NimbusJwtEncoder proofEncoder =
    new NimbusJwtEncoder(jwkSource);

JwsHeader header = JwsHeader
    .with(SignatureAlgorithm.RS256)
    .type("dpop+jwt")
    .jwk(dpopKey.toPublicJWK().toJSONObject())
    .build();

JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuedAt(Instant.now())
    .claim("htm", "POST")
    .claim("htu", "https://issuer.example.test/oauth2/token")
    .id(UUID.randomUUID().toString())
    .build();

Jwt proof = proofEncoder.encode(
    JwtEncoderParameters.from(header, claims)
);
```

This illustrates client-side generation. Never place the private JWK into the request; only the public projection goes into the JOSE header. Token-endpoint proofs omit `ath` because no access token has been issued yet.

### 8.1. Generating a Proof for a Protected Resource

Once an access token has been obtained, the proof must add `ath`:

```java
String ath = accessTokenHash(accessToken);

JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuedAt(Instant.now())
    .claim("htm", "GET")
    .claim("htu", "https://api.example.test/api/orders")
    .claim("ath", ath)
    .id(UUID.randomUUID().toString())
    .build();

Jwt proof = proofEncoder.encode(
    JwtEncoderParameters.from(header, claims)
);
```

If the Resource Server issued a `DPoP-Nonce`, add the `nonce` claim to the proof. Use the exact HTTP method and external URI the server will validate against.

### 8.2. Do Not Assume OAuth2 Client Generates Proofs Automatically

An application using `OAuth2AuthorizedClientManager` and `WebClient` does not automatically generate DPoP proofs unless configured/supported. Verify the exact version and token client implementation:
- Does the token request include a `DPoP` header?
- Does the client store the key binding alongside the authorized client?
- Does every resource request generate a fresh proof?
- Is `ath` computed over the exact access token?
- Is the `Authorization` scheme `DPoP`?
- Are nonce challenges handled properly?

If integrating manually, place proof generation in a component with access to the final HTTP method, canonical URI, token, and key. Never generate proofs before knowing the final target URI and method.

### 8.3. The Authorization Server Must Issue Bound Tokens

A Resource Server cannot turn an arbitrary Bearer token into a DPoP-bound token on its own. The Authorization Server must:
- Accept and verify the DPoP proof at the token endpoint.
- Extract the client's public key.
- Issue an access token with `token_type` `DPoP`.
- Attach the public key thumbprint via `cnf.jkt` or equivalent introspection metadata.
- Enforce consistent binding policies across token refreshes and exchanges.

Adding `DPoPAuthenticationProvider` on the Resource Server alone while the AS continues issuing unbound Bearer tokens leaves the two sides on incompatible protocol contracts.

## 9. How Does RFC 9068 Standardize JWT Access Tokens?

OAuth 2.0 does not mandate that access tokens be JWTs. Tokens can be opaque and introspected, or JWTs verified locally by the Resource Server.

RFC 9068 defines a JWT profile specifically for OAuth 2.0 access tokens. Its goal is to clarify:
- A header type distinguishing access tokens from other JWTs.
- Mandatory claims.
- Audience/resource semantics.
- How Resource Servers validate the token.
- Preventing OIDC ID tokens from being confused with access tokens.

### 9.1. The `typ` Header

An RFC 9068 JWT access token must carry `typ` set to one of:
- `at+jwt`
- `application/at+jwt`

`at+jwt` is recommended to omit the `application/` prefix.

Example:

```json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "as-signing-key-2026"
}
```

Do not confuse:
- `at+jwt`: RFC 9068 access token JWT.
- `dpop+jwt`: RFC 9449 proof JWT.
- `JWT`: generic type that does not identify token purpose.
- ID token: OIDC token describing an authentication event for a client.

### 9.2. Required Claims

RFC 9068 mandates the following claims:

| Claim | Required | Meaning |
|---|---|---|
| `iss` | Yes | Authorization Server that issued the token |
| `exp` | Yes | Expiration timestamp |
| `aud` | Yes | Resource Server or resource indicator authorized to accept the token |
| `sub` | Yes | Subject; may be a user or client depending on grant |
| `client_id` | Yes | OAuth client the token was issued to |
| `iat` | Yes | Issuance timestamp |
| `jti` | Yes | Token identifier |

The `scope` claim is recommended when the authorization request included scopes. Profiles may include additional identity/authorization claims per policy.

### 9.3. Signature Algorithms

RFC 9068 JWT access tokens must be signed and must never use `alg=none`. Conforming Authorization Servers and Resource Servers must support `RS256`; systems may support additional algorithms per policy and registry.

Asymmetric signing is recommended because the Resource Server needs only the public key for verification while the private key stays on the Authorization Server.

### 9.4. Audience Is a Resource Identifier

`aud` is not `client_id`. It identifies the resource the access token targets.

Example:

```json
{
  "iss": "https://issuer.example.test",
  "sub": "user-123",
  "aud": ["https://orders.example.test"],
  "client_id": "orders-web",
  "scope": "orders.read orders.write",
  "iat": 1794744000,
  "exp": 1794744300,
  "jti": "token-identifier-123"
}
```

The Orders API must verify its own audience. Never accept a token solely because the issuer is valid or `client_id` is allowlisted.

### 9.5. Subject Varies by Grant Type

Under authorization code or user-delegated grants, `sub` usually identifies the user. Under client credentials, `sub` may identify the client application.

Never write policies assuming every `sub` is a user ID. When service tokens carry a client identity in `sub`, object ownership logic must handle that principal type properly.

## 10. Why Does RFC 9068 Help Prevent ID Token Confusion?

Both OIDC ID tokens and OAuth access tokens can be signed JWTs containing `iss`/`sub`/`aud`/`exp`. However, they serve different purposes:

| Property | OIDC ID Token | RFC 9068 Access Token |
|---|---|---|
| Intended recipient | OIDC client | Resource Server/API |
| Audience | Client ID | Resource identifier |
| `typ` | Per OIDC/JWT profile | `at+jwt` or `application/at+jwt` |
| Purpose | Authentication proof for the client | API access credential |
| Claims | May carry `nonce`, `auth_time`, `acr`, `amr` | Carries `client_id`, `scope`, and authorization claims |
| Consumer | OIDC client | OAuth Resource Server |

An API should never accept an ID token just because its signature and issuer check out. RFC 9068 enforces `typ`, audience, and profile claims, reducing cross-JWT confusion risks.

## 11. Configuring the RFC 9068 Validator in Spring Security

Spring Security provides `JwtValidators.createAtJwtValidator()` starting in version 6.5. The builder requires at least audience and issuer; `clientId` and custom validators can be added.

Servlet Resource Server example:

```java
@Bean
JwtDecoder jwtDecoder(
        @Value("${security.issuer-uri}") String issuerUri) {

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withIssuerLocation(issuerUri)
            .validateTypes(false)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createAtJwtValidator()
            .issuer(issuerUri)
            .audience("https://orders.example.test")
            .clientId("orders-web")
            .build()
    );

    return decoder;
}
```

In this configuration:
- `withIssuerLocation` sets the issuer and metadata/JWKS discovery location.
- `validateTypes(false)` disables Nimbus's default type validation so the RFC 9068 validator handles checking `at+jwt`.
- `audience()` binds tokens to the Orders API.
- `issuer()` enforces the exact issuer.
- `clientId()` restricts `client_id` when the API accepts only a specific client.

Never call `validateTypes(false)` and forget to attach the RFC 9068 validator. Disabling type verification without replacing it strips a key defense against token confusion.

### 11.1. Should `client_id` Always Be Constrained?

Not necessarily. RFC 9068 requires the `client_id` claim to exist, yet an API may serve multiple OAuth clients. When multiple clients must be accepted:
- Do not pin a single `clientId`.
- Add a validator enforcing an allowlist per policy.
- Keep `audience` and `issuer` mandatory.
- Never substitute `client_id` for authorization scopes or user identity.

### 11.2. Adding Custom Claim Validators

The builder exposes a `validators` consumer to add or replace validators by claim name. For example, if the application requires `tenant_id`:

```java
JwtValidators.AtJwtBuilder builder =
    JwtValidators.createAtJwtValidator()
        .issuer(issuerUri)
        .audience("https://orders.example.test");

builder.validators(validators ->
    validators.put("tenant_id", jwt -> {
        String tenantId = jwt.getClaimAsString("tenant_id");

        if (tenantId != null && !tenantId.isBlank()) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required tenant_id claim is missing",
            null
        );

        return OAuth2TokenValidatorResult.failure(error);
    })
);

decoder.setJwtValidator(builder.build());
```

This illustrates a validator requiring a claim to have a value. If `tenant_id` is required only for certain operations, enforce it in the authorization/service layer instead of rejecting every token lacking that claim.

### 11.3. Composing Validators Intentionally

When constructing a `JwtDecoder` manually, verify all of the following remain enforced:
- Signature under allowed algorithms.
- Issuer.
- Audience.
- `exp` and `nbf`.
- RFC 9068 `typ` and required claims.
- Custom profile claims per contract.
- Clock skew per policy.

Never replace all default validators with a lambda that checks only audience. Replacing the validator can silently drop timestamp or issuer verification.

## 12. RFC 9068 in WebFlux

Spring Security provides the equivalent example with `NimbusReactiveJwtDecoder`:

```java
@Bean
ReactiveJwtDecoder jwtDecoder(
        @Value("${security.issuer-uri}") String issuerUri) {

    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withIssuerLocation(issuerUri)
            .validateTypes(false)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createAtJwtValidator()
            .issuer(issuerUri)
            .audience("https://orders.example.test")
            .build()
    );

    return decoder;
}
```

The RFC 9068 validator is shared at the `Jwt` level. Servlet and Reactive decoders differ in execution model and network retrieval, while profile claims must undergo the exact same validation.

Never wire `ReactiveJwtDecoder` into a Servlet `SecurityFilterChain` or `JwtDecoder` into a `SecurityWebFilterChain`. Use the abstraction matching your application model.

## 13. Combining DPoP and RFC 9068 in the Same Access Token

A JWT access token can satisfy RFC 9068 while also being DPoP-bound:

```json
{
  "iss": "https://issuer.example.test",
  "sub": "user-123",
  "aud": ["https://orders.example.test"],
  "client_id": "orders-web",
  "iat": 1794744000,
  "exp": 1794744300,
  "jti": "access-token-id",
  "scope": "orders.read",
  "cnf": {
    "jkt": "thumbprint-of-client-public-key"
  }
}
```

Access token header:

```json
{
  "typ": "at+jwt",
  "alg": "RS256",
  "kid": "authorization-server-key"
}
```

Separate DPoP proof header:

```json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<PUBLIC_X>",
    "y": "<PUBLIC_Y>"
  }
}
```

Proof claims:

```json
{
  "jti": "unique-proof-id",
  "htm": "GET",
  "htu": "https://orders.example.test/api/orders",
  "iat": 1794744010,
  "ath": "<BASE64URL_SHA256_OF_ACCESS_TOKEN>"
}
```

The access token is signed by the Authorization Server. The DPoP proof is signed by the client. The two signatures prove two distinct facts:
- Token signature: the Authorization Server issued the token.
- DPoP proof signature: the presenting client holds the private key matching the public key bound to the token.

The Resource Server must verify both signatures and the binding between them.

## 14. Version-Dependent Features to Cross-Check

When upgrading, look beyond major versions. Several capabilities were introduced in minor or patch releases:

| Capability | Documented Version | What to Verify |
|---|---:|---|
| `DPoPAuthenticationProvider` | 6.5 | Class and provider API presence |
| `DPoPProofJwtDecoderFactory` | 6.5 | Proof decoder factory presence |
| `JwtValidators.createAtJwtValidator` | 6.5 | RFC 9068 profile validator presence |
| `DPoPProofReplayValidator` | 6.5.12 | Single-use `jti` replay validator presence |
| `DPoPAuthenticationConverter` | 7.1 | Servlet request converter presence |
| DPoP default proof validation | Changes across patches | Verify `htm`/`htu`/`iat`/`jti`/`jkt`/`ath` claims are validated |
| DPoP Resource Server reference | 6.5, 7.0, 7.1 | Reference docs have per-release-line pages |
| RFC 9068 Servlet/Reactive examples | 6.5+ in current docs | `NimbusJwtDecoder` and `NimbusReactiveJwtDecoder` |

These milestones reflect the Spring Security documentation at the time of writing. Patch releases can add validators, adjust defaults, or introduce helpers. Always check the API docs for your exact patch version before copying code.

### 14.1. Spring Boot Manages Spring Security

In Boot applications:
- Pick the Boot release first.
- Check the Spring Security version managed by the Boot BOM.
- Verify the needed DPoP/RFC 9068 APIs exist in that version.
- If a feature from a newer patch is needed, prefer upgrading to the matching Boot patch/minor release.
- Avoid overriding `spring-security-oauth2-resource-server` or `spring-security-oauth2-jose` individually to another version.

Never mix `spring-security-core`, `web`, `config`, `oauth2-resource-server`, `oauth2-jose`, and `spring-security-test` across different versions.

### 14.2. Checking Resolved Dependencies

Gradle:

```powershell
.\gradlew dependencyInsight --dependency spring-security-oauth2-resource-server --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency spring-security-oauth2-jose --configuration runtimeClasspath
.\gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
```

Maven:

```powershell
mvn dependency:tree -Dincludes=org.springframework.security
```

Then check the API against the actually resolved dependencies rather than assuming behavior from "latest" docs.

### 14.3. Compile Probes for Version-Dependent APIs

When unsure which patch introduced a method, write a small compile probe on the upgrade branch:
- Import `DPoPAuthenticationProvider`.
- Import `DPoPAuthenticationConverter` if planning to use it.
- Import `DPoPProofReplayValidator`.
- Call `JwtValidators.createAtJwtValidator()`.
- Build `NimbusJwtDecoder` with `validateTypes(false)`.
- Build `NimbusReactiveJwtDecoder` if the app uses WebFlux.

A compile probe proves the classes/methods exist on the actual classpath. Follow up with integration tests.

## 15. Testing RFC 9068

A test suite should include separate positive and negative token cases:

| Case | Header/Claims | Result |
|---|---|---|
| Valid profile token | `typ` `at+jwt`, all required claims, valid signature | Authentication succeeds |
| Generic `typ` `JWT` | Does not satisfy RFC 9068 profile | Rejected |
| `typ` `dpop+jwt` | Proof token, not an access token | Rejected as access token |
| Missing `iss` | Missing required claim | Rejected |
| Missing `exp` | Missing required claim | Rejected |
| Missing `aud` | Missing required claim | Rejected |
| Missing `sub` | Missing required claim | Rejected |
| Missing `client_id` | Missing required claim | Rejected |
| Missing `iat` or `jti` | Missing required claim | Rejected |
| Wrong issuer | Valid signature but `iss` mismatch | Rejected |
| Wrong audience | Token meant for another API | Rejected |
| Expired token | `exp` in the past | Rejected |
| Invalid signature | Token fails verification | Rejected |
| ID token sent to API | Wrong token purpose/audience/type | Rejected |

With `MockMvc`/`WebTestClient`, use real signed compact JWTs and a real decoder for profile integration tests. `jwt()` or `mockJwt()` is great for authorization tests but does not prove the decoder validates `typ`/headers/required claims.

### 15.1. Testing Authority Mapping Separately

If tokens include `scope`, verify authorities map properly:
- `orders.read` maps to `SCOPE_orders.read`.
- Tokens lacking the scope lack the authority.
- Custom converters do not bypass profile validation.
- `client_id` is never mistaken for a scope.
- Service principal `sub` values are not treated as user IDs if policy distinguishes them.

### 15.2. Verifying ID Tokens Cannot Be Used as Access Tokens

Build an OIDC ID token fixture with:
- Valid `iss`.
- Valid signature.
- `aud` set to the OIDC client ID.
- Valid OIDC claims.

Send that ID token to the Resource Server. It must be rejected due to type/audience/profile mismatch. This is a high-value test against cross-JWT confusion.

## 16. Testing DPoP End-to-End

Use one test key pair for the DPoP client and a separate key pair for the Authorization Server. Never reuse a single key to test both signatures.

### 16.1. Positive Case

- Test Authorization Server issues an access token with `token_type` `DPoP`.
- Token contains `cnf.jkt` matching the client's public key.
- Client generates a proof with `typ` `dpop+jwt`.
- Proof has valid `htm`, `htu`, `iat`, `jti`, and `ath`.
- Client sends `Authorization: DPoP` and the `DPoP` header.
- Resource Server verifies both token and proof.
- Scope authorization rules allow the request.

### 16.2. Negative Cases

| Case | Mutation | Outcome |
|---|---|---|
| Missing DPoP proof | Send access token only | Rejected |
| Invalid proof signature | Sign proof with a different private key | Rejected |
| Key binding mismatch | `cnf.jkt` does not match proof public key | Rejected |
| Invalid `ath` | Hash does not match access token | Rejected |
| Wrong `htm` | Proof has `GET` for a `POST` request | Rejected |
| Wrong `htu` | Proof signed for a different URI | Rejected |
| Stale proof | `iat` too old | Rejected |
| Reused `jti` | Resend the exact same proof | Rejected per replay policy |
| Missing nonce | Server demanded a nonce | Rejected or returns nonce challenge |
| Wrong nonce | `nonce` claim mismatch | Rejected |
| Duplicate `DPoP` header | Multiple proof headers | Rejected |
| Wrong `typ` | `typ` is not `dpop+jwt` | Rejected |
| `alg=none` | Proof lacks a secure signature | Rejected |
| JWK contains private material | Header includes private key parameters | Rejected |
| Using Bearer scheme | Send DPoP-bound token as `Bearer` | Rejected per policy |

### 16.3. Testing Replay Across Multiple Instances

When running multiple Resource Server nodes:
- Send the proof first to node A.
- Replay the exact same proof to node B.
- Confirm node B also rejects it.
- Confirm the replay cache is shared and writes are atomic.
- Test cache eviction/expiry so `jti` entries do not grow unbounded.

`InMemoryCache` works for single-node or local tests. Production clusters require a shared cache.

### 16.4. Testing Reverse Proxies and `htu`

Run requests through the production proxy topology:
- TLS termination.
- Forwarded host/proto.
- Path prefix rewrites.
- Context paths.
- Port normalization.

A proof built from the public URI must be verified against the same canonical URI on the server. Tests calling `MockMvc` directly can miss proxy mismatches.

## 17. Testing Nonces and Client Retries

Simulate:
1. Client sends a proof without a nonce.
2. Server responds with `use_dpop_nonce` and `DPoP-Nonce`.
3. Client mints a new proof with a fresh `jti` and the new `nonce`.
4. Client retries.
5. Server accepts if all other validations pass.

Negative tests:
- Stale nonce.
- Nonce from another issuer.
- Nonce omitted after challenge.
- Retrying with the same proof/`jti`.
- Server continuously issuing new nonces.
- Client exceeding maximum retry attempts.

Nonce challenges must not trigger retry storms. Clients must cap retries and emit telemetry using error codes without logging raw proofs or tokens.

## 18. Combined DPoP and RFC 9068 Test Matrix

| Access Token | Proof | Outcome |
|---|---|---|
| Valid RFC 9068, DPoP-bound | Proof matches key, `htm`/`htu`/`ath`/`jti` | Passes authentication |
| Valid RFC 9068, no `cnf` binding | Valid proof signature, unbound token | Not treated as DPoP-bound |
| RFC 9068 wrong audience | Valid proof | Rejects token |
| RFC 9068 wrong `typ` | Valid proof | Rejects access token |
| Valid token, wrong `ath` | Access-token hash mismatch | Rejects proof |
| Valid token, wrong `jkt` | Key thumbprint mismatch | Rejects proof |
| Valid token, replayed proof | `jti` already spent | Rejects replay |
| Expired token, fresh proof | Valid proof | Rejects token |
| Valid token, valid proof, missing scope | Insufficient authorization | 403 |
| Valid token/proof, object policy denies | Ownership/tenant denial | 403/404 per policy |

Test each failure layer separately to pinpoint which validator is responsible.

## 19. Symptom-Based Troubleshooting

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `at+jwt` JWT rejected for type | Nimbus type validation not adjusted for RFC 9068 | `validateTypes` and `AtJwtValidator` |
| Valid profile token gets 401 | Wrong issuer/audience/time/signature or missing required claim | Decoder exception and claims |
| ID token is accepted | Only checks signature/issuer, missing type/audience profile | Add RFC 9068 validation |
| DPoP token rejected for scheme | Client sent `Bearer` instead of `DPoP` | `Authorization` header |
| Invalid DPoP proof signature | Mismatched key pair or tampered proof | Public JWK and signer |
| `jkt` mismatch | Key bound to access token differs from proof key | `cnf.jkt` and JWK thumbprint |
| `ath` mismatch | Incorrect token hash or modified token | SHA-256 over ASCII access token |
| `htm` mismatch | Proof generated before final HTTP method was known | Generate proof right before send |
| `htu` mismatch | Reverse proxy/path/scheme discrepancy | Canonical external URI |
| Replayed proof accepted on another node | Local replay cache | Shared atomic cache |
| Proof rejected for `iat` | Client/server clock skew | Clock sync and skew policy |
| Infinite nonce challenges | Client fails to store nonce or omits it in new proof | `DPoP-Nonce` handling |
| Converter class missing | Using 7.1 API on 6.5/7.0 | Resolved Security version |
| Replay validator class missing | Patch older than 6.5.12 | `dependencyInsight` and patch upgrade |
| Reactive DPoP integration missing | Assuming Servlet APIs have Reactive equivalents | Check exact Reactive APIs |

## 20. Common Design Mistakes

1. **Treating DPoP proofs as access tokens.** The two JWTs have different purposes and signing keys.
2. **Using the `Bearer` scheme for DPoP-bound tokens.** Requests must use the `DPoP` scheme per protocol.
3. **Reusing proof JWTs.** Every request requires a fresh `jti` and proof.
4. **Not computing `ath` over the full token string.** Hashing only the payload or decoded claims is wrong.
5. **Not checking `cnf.jkt`.** A valid proof signature alone does not prove the key is bound to the token.
6. **Not checking `htm`/`htu`.** Allows proofs to be replayed against other endpoints.
7. **Missing a shared replay cache.** Clusters can accept the same proof twice.
8. **Ignoring `DPoP-Nonce`.** Fails AS/RS freshness policies.
9. **Putting private JWKs in proof headers.** Leaks private keys.
10. **Trusting `Forwarded` headers from any client.** Attackers can manipulate `htu` comparisons.
11. **Allowing ID tokens at APIs.** Causes cross-JWT confusion.
12. **Disabling `typ` validation without adding an RFC 9068 validator.** Leaves token purpose unchecked.
13. **Checking only issuer and signature.** Omits audience and required profile claims.
14. **Assuming client libraries generate DPoP proofs automatically.** Verify HTTP/token client behavior.
15. **Assuming Reactive has identical DPoP APIs to Servlet.** Docs and APIs must be verified separately.
16. **Upgrading a single Security module alone.** Causes split versions.
17. **Running only decoder unit tests.** Misses header extraction, proxy URIs, and replay checks.
18. **Ignoring `token_type` from the AS.** Clients may mishandle DPoP tokens as Bearer tokens.
19. **Lacking a client DPoP key lifecycle.** Key rotation breaks existing bound tokens if binding is unmanaged.
20. **Logging proofs or access tokens.** Exposes credentials and request metadata.

## 21. Upgrade Roadmap to Enable RFC 9068 and DPoP

**Step 1 — Finalize the token contract.** Define issuer, audience, `client_id`, scope, `typ`, signing algorithm, DPoP binding, and nonce behavior.

**Step 2 — Pick the Spring Boot release train.** Identify the Spring Security patch managed by the Boot BOM.

**Step 3 — Verify feature APIs.** Confirm `createAtJwtValidator`, `DPoPAuthenticationProvider`, `DPoPProofJwtDecoderFactory`, replay validator, and converters exist in the dependency graph.

**Step 4 — Enable RFC 9068 validation.** Configure type, issuer, audience, and required claims; add custom validators if the token profile demands them.

**Step 5 — Verify the Authorization Server.** Confirm the token endpoint accepts proofs and issues `token_type` `DPoP` with `cnf.jkt` or introspection binding.

**Step 6 — Integrate client proof generation.** Manage keys and generate per-request proofs with `ath` and `nonce`.

**Step 7 — Integrate Resource Server DPoP.** Use the provider/converter/decoder factory compatible with your version; configure the replay cache.

**Step 8 — Run the test matrix.** Cover positive and negative signatures, claims, `jkt`, `ath`, `htm`, `htu`, `nonce`, and replay.

**Step 9 — Verify proxy topology.** Ensure `htu` comparison uses the exact public URI.

**Step 10 — Controlled rollout.** Monitor DPoP successes/failures, nonce challenges, replay rejections, 401/403 rates, and client compatibility.

**Step 11 — Keep a rollback plan.** Maintain client/server compatibility and a clear policy if falling back to Bearer is necessary for a client group. Never silently downgrade DPoP-bound tokens to Bearer.

## 22. Observability and Operations

Track signals such as:
- Valid vs. invalid DPoP proof request counts.
- Proof validation failure reasons: `typ`, signature, `htm`, `htu`, `iat`, `jti`, `ath`, `jkt`, `nonce`.
- Count of rejected replayed proofs.
- Nonce challenge rate.
- RFC 9068 validation failure rates by `typ`/issuer/audience/time/required claim.
- `DPoP` vs. `Bearer` token types by client registration.
- Proof validation and replay cache latency.
- Cache availability and eviction metrics.

Never log:
- Raw access tokens.
- Raw DPoP proofs.
- Private keys.
- Full JWT payloads containing PII.
- `Authorization` headers.

Use reason codes and correlation IDs. If logging `kid` or JWK thumbprints, check logging policies and avoid high-cardinality metric labels.

## 23. Pre-Release Checklist

- [ ] Both Authorization Server and Resource Server support DPoP.
- [ ] Token responses return `token_type` `DPoP` for DPoP-bound tokens.
- [ ] Access tokens carry `cnf.jkt` binding or equivalent introspection metadata.
- [ ] Clients store private keys securely and never transmit private material.
- [ ] Proofs have `typ` `dpop+jwt` and an allowlisted asymmetric `alg`.
- [ ] Proofs contain `jti`, `htm`, `htu`, and `iat`.
- [ ] Protected-resource proofs contain accurate `ath`.
- [ ] Nonces are handled when demanded by the server.
- [ ] `jti` replay detection is enabled with a cluster-safe cache.
- [ ] `htu` comparison handles reverse proxies and forwarded headers safely.
- [ ] DPoP tokens use the `DPoP` authorization scheme.
- [ ] RFC 9068 `typ` (`at+jwt`/`application/at+jwt`) is validated.
- [ ] RFC 9068 required claims are verified.
- [ ] Issuer, audience, signature, `exp`/`nbf`, and algorithm policies remain enforced.
- [ ] ID tokens are rejected at the Resource Server.
- [ ] `JwtValidators.createAtJwtValidator` is present in the resolved version.
- [ ] DPoP APIs match the Spring Security patch version.
- [ ] Servlet/Reactive support is verified separately.
- [ ] Negative tests cover `ath`, `jkt`, `htm`, `htu`, `nonce`, replay, and `typ`.
- [ ] Multi-node replay cache is tested.
- [ ] Real client token acquisition and downstream requests are tested.
- [ ] Logs contain no tokens, proofs, or private keys.
- [ ] Rollout and rollback plans exist for clients not yet supporting DPoP.

## 24. References

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): DPoP proofs, `htm`, `htu`, `ath`, `nonce`, key binding, and replay.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): `typ` `at+jwt`, required claims, and Resource Server validation.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JWS signing and compact serialization.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS and public key representations.
- [Spring Security — DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html): DPoP Resource Server flow and Java proof generation.
- [Spring Security 6.5 — DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/dpop-tokens.html): Security 6.5 APIs.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoders, algorithms, and RFC 9068 validation.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): RFC 9068 validator with `NimbusReactiveJwtDecoder`.
- [Spring Security API — JwtValidators](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html): `createAtJwtValidator` and version milestones.
- [Spring Security API — DPoPAuthenticationProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/DPoPAuthenticationProvider.html): DPoP authentication provider.
- [Spring Security API — DPoPProofJwtDecoderFactory](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofJwtDecoderFactory.html): proof decoder and validator factory.
- [Spring Security API — DPoPProofReplayValidator](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/DPoPProofReplayValidator.html): `jti` replay protection and cache.
- [Spring Security — What’s New in 6.5](https://docs.spring.io/spring-security/reference/6.5/whats-new.html): DPoP introduced in Spring Security 6.5.

**Conclusion:** RFC 9068 standardizes the JWT access token type and claims that a Resource Server must verify; DPoP binds tokens to a client's public key and requires a fresh proof per request. Spring Security added the RFC 9068 validator in 6.5 and DPoP Resource Server building blocks in 6.5, with the replay validator and request converter arriving in subsequent patch/minor milestones. Pick APIs matching your exact Spring Security version, verify Authorization Server, client, and Resource Server together, and test signatures, `typ`, claims, `jkt`, `ath`, `htm`, `htu`, `nonce`, and replay before rolling out. **Do not enable DPoP simply by attaching a header; token issuance, key binding, and request verification must all conform to RFC 9449.**
