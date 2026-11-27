# DPoP Proof Structure, Client Keys, and Public JWK

## 1. How Does DPoP Bind an Access Token to the Client's Key?

In OAuth 2.0 Bearer Tokens, any party holding the access token can attempt to use it while it remains valid. If the token is leaked via logs, memory, a browser, or an intermediary service, an attacker who obtains it can use it from another environment.

**Demonstrating Proof of Possession (DPoP)** per RFC 9449 adds an HTTP-level cryptographic proof. The client owns an asymmetric key pair, retains the private key, and sends a signed **DPoP proof** for each HTTP request. The Authorization Server or Resource Server verifies the signature using the public JWK embedded in the proof's JOSE header. The access token is bound to the thumbprint of that public key.

Consequently, someone who only steals the access token without the corresponding private key cannot generate a valid proof for a new request.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>C: Generate key pair (private/public)
    C->>AS: Token request + DPoP proof signed with private key
    AS->>AS: Verify proof, compute JWK thumbprint
    AS->>AS: Issue access token with cnf.jkt
    AS-->>C: DPoP-bound access token
    C->>RS: Authorization: DPoP + token, new DPoP proof
    RS->>RS: Verify proof, ath, htm, htu, iat, jti
    RS->>RS: Compare JWK thumbprint with cnf.jkt
    RS-->>C: Accept or reject request
~~~

This lesson belongs to the **Proof of Possession** chapter of the module on designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server. The focus is on **DPoP proof structure, client key pairs, and public JWKs**; from there, you will understand why the proof binds to the exact HTTP request and why the issued token requires the `cnf.jkt` claim.

DPoP does not replace TLS, user authentication, scopes, audience, or business authorization. It adds proof that the client holds the private key corresponding to the public key to which the access token is bound.

## 2. Three Components to Distinguish

| Component | Content | Secret? | Role |
| --- | --- | --- | --- |
| **Client's private key** | Proof signing key | **Yes** | Generates the signature for the DPoP proof |
| **Public JWK** | JSON Web Key representation of the public key | No | Included in the proof so the server can verify the signature |
| **JWK thumbprint** | Canonical hash computed from the required members of the JWK | No | Binds the access token to the public key via `cnf.jkt` |
| **DPoP proof JWT** | Signed JWT for a specific HTTP request | Signature and payload are observable; contains no private key | Proves possession and binds method/URI/time |
| **Access token** | Credential issued by the AS | Sensitive | Carries access permissions and key confirmation info |

**Do not confuse a public JWK with a proof JWT.** A JWK only describes the public key. A proof JWT is a signed message containing claims about the request. The server needs both: the JWK to verify the signature, and the claims to determine which request the proof applies to and whether it is still valid.

Also do not confuse `cnf.jkt` with `kid`:
- `kid` is an optional key identifier in JOSE/JWK, typically used to select a key.
- `jkt` is the JWK thumbprint, with cryptographic semantics defined by RFC 7638.
- Access token DPoP binding uses `cnf.jkt` to represent the public key attached to the token by the AS.

## 3. Structure of a DPoP Proof JWT

A DPoP proof is a **signed JWT (JWS Compact Serialization)**. Its header typically contains three key fields:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "BASE64URL_PUBLIC_X",
    "y": "BASE64URL_PUBLIC_Y"
  }
}
~~~

The payload at the Resource Server may look like:

~~~json
{
  "jti": "unique-proof-id-7e91",
  "htm": "GET",
  "htu": "https://api.example.com/orders/42",
  "iat": 1794823200,
  "ath": "BASE64URL_SHA256_OF_ACCESS_TOKEN"
}
~~~

This is an illustrative payload. Timestamps, key coordinates, and the token hash must be generated dynamically; do not use illustrative literals in production.

### 3.1. JOSE Header

| Header parameter | Requirement / meaning | What to verify |
| --- | --- | --- |
| `typ` | DPoP proof value is `dpop+jwt` | Must match the proof type; do not confuse with JWT access tokens |
| `alg` | Asymmetric signature algorithm | Must not accept `none` or symmetric MAC algorithms like HS256 |
| `jwk` | Public JWK corresponding to the proof signing private key | Must contain only public key material; must not include private parameters |
| `kid` | Optional key identifier per profile | Does not replace signature verification or thumbprint matching |

DPoP proofs do not use a shared secret known to both client and server to compute a MAC. The goal is to prove the client possesses the **private key**, so the server only accepts asymmetric signature algorithms on its allowlist.

The public JWK in the proof must be validated for proper type and structure. Never accept private parameters such as `d` for EC/OKP/RSA, or `p`, `q`, `dp`, `dq`, `qi`, `oth` for RSA. The private key must never be sent to the Authorization Server or Resource Server.

### 3.2. Required Claims in the Proof

| Claim | Meaning | Verification rules |
| --- | --- | --- |
| `jti` | Unique identifier of the proof JWT | Used to detect proof replay; generate a new proof per request |
| `htm` | HTTP method of the request | Must match the actual method, e.g., `GET`, `POST` |
| `htu` | HTTP target URI | Must match the request URI per normalization rules; must not contain query or fragment |
| `iat` | Time the proof was created (NumericDate) | Must fall within the accepted time window |
| `ath` | Hash of the access token | Required when the proof is sent alongside an access token to a Resource Server |

A proof used at the token endpoint typically **does not include `ath`** because the request is requesting a token, not presenting an access token to call an API. When the client presents an access token at the Resource Server, the proof must include `ath` computed from the exact access token sent with the request.

### 3.3. The `nonce` Claim

`nonce` is an optional server-provided claim that binds the proof to a recent challenge near the request time. The Authorization Server or Resource Server can return a `DPoP-Nonce` header; the client must include that nonce in the next proof when required by the server.

A nonce reduces the window for an attacker to pre-compute a proof and use it later. It does not replace `jti`, `iat`, or signature verification. The server must enforce a nonce policy per issuer/resource, including lifetime and handling of invalid/expired nonces.

## 4. Exact Meaning of `htm`, `htu`, `iat`, `jti`, and `ath`

### 4.1. `htm` — HTTP Method

`htm` is the method of the HTTP request protected by the proof. Examples:
- Resource read request: `GET`.
- Order creation request: `POST`.
- Update request: `PUT` or `PATCH`.

The value must reflect the actual method. If the proof was created for `GET` but the client sends a `POST` request, the server must reject it. Do not reuse one proof across different methods.

### 4.2. `htu` — HTTP Target URI

`htu` is the target URI of the HTTP request, **excluding the query string and fragment**. Example:

~~~text
Actual request:
https://api.example.com/orders/42?expand=items#details

DPoP htu:
https://api.example.com/orders/42
~~~

The server must compare values according to the URI normalization rules of RFC 9449/RFC 3986 and deployment configuration. It must account for the actual scheme, host, port, and path. Do not derive the URI from `Host` or `Forwarded` headers that are not controlled by a trusted proxy.

In reverse proxy/load balancer environments, the application may observe an internal URI like `http://service:8080` while the client called `https://api.example.com`. Trusted proxies and the exact external base URL must be configured. Otherwise, valid proofs may be rejected or an attacker could exploit server trust in forged proxy headers.

### 4.3. `iat` — Proof Creation Time

`iat` is a NumericDate. The server typically accepts proofs within a short time window to limit capturing and replaying proofs. You must define:
- Clock skew tolerance for client/server.
- Maximum proof age.
- Tolerance for timestamps slightly in the future.
- NTP synchronization across nodes.

Too wide a window gives a stolen proof more time to be replayed; too narrow a window causes requests to fail due to client clock drift or network latency.

### 4.4. `jti` — Unique Identifier and Replay Protection

Every proof must have a distinct `jti`; never reuse the same proof JWT for another request. The server can store a replay marker keyed by the combination of key thumbprint and `jti` for the duration the proof remains acceptable.

Example logic:

~~~text
replay_key = (jkt, jti)
if replay_cache.contains(replay_key):
    reject proof
else:
    replay_cache.put(replay_key, expiry = proof_acceptance_window)
~~~

This is pseudocode. The cache must be shared or have consistent semantics when the Resource Server runs across multiple instances. If each node maintains a local-only replay cache, an attacker can send the same proof to another node and bypass replay checks.

### 4.5. `ath` — Access Token Hash

When a DPoP proof is sent with an access token to a Resource Server, the `ath` claim binds the proof to that exact token:

~~~text
ath = BASE64URL-ENCODE(
        SHA-256(ASCII(access_token))
      )
~~~

Base64URL here omits padding (`=`). The hash is computed over the **actual access token string** in the Authorization header, not the decoded JWT payload, token ID, or refresh token.

If an attacker swaps the access token in the header while keeping the proof, `ath` will not match. If the client generates a proof for token A but sends token B, the Resource Server must reject it.

## 5. Public JWK and Thumbprint Computation

### 5.1. What Is a JWK?

JSON Web Key (RFC 7517) represents a cryptographic key in JSON. For DPoP, the public key is placed in the `jwk` JOSE header so the server can verify the proof signature.

Example EC P-256:

~~~json
{
  "kty": "EC",
  "crv": "P-256",
  "x": "PUBLIC_X_COORDINATE",
  "y": "PUBLIC_Y_COORDINATE"
}
~~~

Where:
- `kty`: key type, here Elliptic Curve.
- `crv`: curve name, e.g., `P-256`.
- `x` and `y`: Base64URL-encoded public key coordinates.
- No `d`: `d` is the EC private scalar and must never be included in a public JWK.

An RSA public JWK has `kty=RSA`, `n` (modulus), and `e` (public exponent). The JWK thumbprint is computed from the required set of attributes corresponding to the key type.

### 5.2. JWK Thumbprint per RFC 7638

The server needs to determine whether the public key in the DPoP proof matches the key bound to the access token. RFC 7638 defines the **JWK Thumbprint** by:
1. Selecting the exact required members for the `kty`.
2. Creating a JSON object containing only those members.
3. Sorting property names lexicographically and serializing per RFC 7638 canonicalization rules.
4. Hashing the UTF-8 bytes of that JSON with SHA-256.
5. Base64URL-encoding the result without padding.

For example, EC P-256 uses only `crv`, `kty`, `x`, and `y` in canonical JSON:

~~~json
{"crv":"P-256","kty":"EC","x":"PUBLIC_X_COORDINATE","y":"PUBLIC_Y_COORDINATE"}
~~~

The thumbprint must not be computed by arbitrarily hashing the entire original JWK JSON, as a JWK can contain extra metadata such as `use`, `kid`, or `alg`. Only the required members specified by RFC 7638 must be used.

### 5.3. `cnf.jkt` in the Access Token

After verifying the proof at the token endpoint, the AS computes the thumbprint of the public JWK and embeds it in the access token:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "alice",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1794826800,
  "cnf": {
    "jkt": "BASE64URL_JWK_THUMBPRINT"
  }
}
~~~

`cnf` is the confirmation claim. `jkt` contains the JWK thumbprint, indicating which public key the token is bound to. Upon receiving a new proof, the Resource Server will:
1. Verify the proof signature using the public JWK in the header.
2. Compute the thumbprint from that JWK.
3. Read `cnf.jkt` from the verified access token.
4. Compare the two values using constant-time comparison or an appropriately safe comparison.
5. Accept only when the thumbprint matches and all other proof claims are valid.

**Never trust `cnf.jkt` from an unverified JWT.** First verify the access token against issuer, key, signature, expiry, and audience policies.

## 6. Generating and Using Client Key Pairs

### 6.1. Client Asymmetric Key Generation

The client generates a key pair using a CSPRNG and selects an algorithm from the AS/RS allowlist. For example, EC P-256 with ES256 is a common choice. The key must:
- Be generated by a trusted cryptographic library.
- Meet policy key strength requirements.
- Keep its private key secret.
- Have a public key exportable as a JWK.
- Have a clear identifier/key lifecycle.

Do not use HS256 or a shared secret in place of a DPoP asymmetric proof. Never derive keys from passwords, timestamps, device IDs, or predictable strings.

### 6.2. Where Should the Private Key Be Stored?

| Client type | Recommended location | Notes |
| --- | --- | --- |
| Native mobile | iOS Keychain/Secure Enclave or Android Keystore where appropriate | Prefer non-exportable keys and control backup/restore behavior |
| Desktop | OS credential store, TPM, or hardware-backed keystore if available | Restrict export and process read permissions |
| Web SPA | Web Crypto API with non-extractable keys when feasible | XSS can still invoke signing operations; DPoP does not block XSS by itself |
| Backend confidential client | Controlled KMS/HSM or secret/key store | Enforce service account permissions, auditing, and rotation |
| Test automation | Dedicated keys for test fixtures | Never use test keys in production environments |

DPoP proves possession of the private key at signing time, not that the device/client is uncompromised. If an attacker can invoke the private key or control the runtime, they can generate valid proofs.

### 6.3. One Key per Client or per Installation?

DPoP binding ties tokens to a key, so you must define key scope:
- One key per installation/device isolates tokens across devices.
- One key per backend client may fit centrally operated services.
- Sharing a single key across all users increases the blast radius if that key is leaked.

When the key changes, old access tokens remain bound to the old thumbprint. The client cannot switch keys while continuing to use that token. It must obtain a new token via an appropriate authorization/exchange flow or follow an AS-supported key rollover procedure.

## 7. Generating a DPoP Proof in Java

The following examples illustrate using Nimbus JOSE + JWT to generate an EC key and sign a proof. Exact APIs may vary by Nimbus version; these examples focus on RFC 9449 structure, so verify against your project dependencies before going to production.

### 7.1. Generating a Key Pair and Public JWK

~~~java
import com.nimbusds.jose.jwk.Curve;
import com.nimbusds.jose.jwk.ECKey;
import com.nimbusds.jose.jwk.gen.ECKeyGenerator;

ECKey clientKey = new ECKeyGenerator(Curve.P_256)
        .keyID("client-dpop-key-01")
        .generate();

ECKey publicJwk = clientKey.toPublicJWK();

// clientKey holds private material; publicJwk contains only public material.
~~~

Do not send `clientKey` to the server. Only `publicJwk` is embedded in the proof. In a real application, the key should be persisted in a secure keystore rather than regenerated on every run.

### 7.2. Creating a Proof for the Token Endpoint

~~~java
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.ECDSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.time.Instant;
import java.util.Date;
import java.util.UUID;

String method = "POST";
String targetUri = "https://auth.example.com/oauth2/token";

JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.ES256)
        .type(new JOSEObjectType("dpop+jwt"))
        .jwk(clientKey.toPublicJWK())
        .build();

JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .jwtID(UUID.randomUUID().toString())
        .issueTime(Date.from(Instant.now()))
        .claim("htm", method)
        .claim("htu", targetUri)
        // Add nonce when required by the Authorization Server.
        .build();

SignedJWT proof = new SignedJWT(header, claims);
proof.sign(new ECDSASigner(clientKey));
String dpopProofJwt = proof.serialize();
~~~

At the token endpoint, the example omits `ath` because no access token is being presented yet. During a refresh token request, the client continues using the private key bound to the refresh token if the server enforces DPoP binding on refresh tokens.

### 7.3. Computing `ath` When Calling a Resource Server

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;

static String accessTokenHash(String accessToken) throws Exception {
    byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(accessToken.getBytes(StandardCharsets.US_ASCII));

    return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
}
~~~

Then add the `ath` claim to the proof before signing. The proof must have `htm` and `htu` matching the API request and a fresh `jti`.

### 7.4. Request to the Resource Server

~~~http
GET /orders/42 HTTP/1.1
Host: api.example.com
Authorization: DPoP ACCESS_TOKEN_VALUE
DPoP: SIGNED_DPOP_PROOF_JWT
~~~

The scheme in the Authorization header is **`DPoP`**, not `Bearer`, when presenting a DPoP-bound access token per RFC 9449. The `DPoP` header carries the per-request proof JWT. Do not put the access token inside the proof payload in place of the Authorization header.

## 8. How Does the Server Verify the Proof?

The Resource Server must execute an ordered verification pipeline. It can be structured as a verifier service and a filter integrated into the authentication flow.

~~~mermaid
flowchart TD
    A[Receive access token + DPoP proof] --> B[Verify access token]
    B --> C{Token valid and has cnf.jkt?}
    C -->|No| X[Reject]
    C -->|Yes| D[Parse DPoP JWS]
    D --> E[Check typ, alg, public jwk]
    E --> F[Verify signature with JWK]
    F --> G[Check htm, htu, iat, jti, nonce]
    G --> H[Compute ath from access token]
    H --> I[Compare JWK thumbprint with cnf.jkt]
    I --> J{All valid?}
    J -->|No| X
    J -->|Yes| K[Mark jti as used]
    K --> L[Proceed to authorization]
~~~

### 8.1. Validation Steps

1. Verify the access token: issuer, signature or introspection, expiry, audience, and status.
2. Confirm the token has a DPoP confirmation binding (`cnf.jkt`). A DPoP-bound token must never be downgraded to Bearer simply because a proof is missing.
3. Parse the proof as compact JWS; verify `typ=dpop+jwt`.
4. Accept only asymmetric algorithms on the allowlist; reject `none` and symmetric MACs.
5. Verify the JWK is public-only and conforms to allowed key type/curve/strength policies.
6. Verify the signature using the public JWK.
7. Verify `htm` equals the actual HTTP method.
8. Verify `htu` equals the actual normalized target URI, excluding query/fragment.
9. Verify `iat` is within the time window and `nonce` if required by the server.
10. Compute `ath` from the exact access token and compare it with the claim in the proof.
11. Compute the JWK thumbprint and compare it with `cnf.jkt` in the token.
12. Verify `jti` has not appeared in the replay cache; record it atomically before accepting the request.
13. Continue with normal scope/role/business authorization.

Steps may be optimized or reordered in an implementation, but none of the corresponding constraints may be skipped. Do not mark `jti` as used before basic verification succeeds; at the same time, prevent two concurrent requests from both accepting the same proof.

### 8.2. DPoP-Nonce Challenge

The server may require a nonce. Example response:

~~~http
HTTP/1.1 401 Unauthorized
DPoP-Nonce: SERVER_NONCE_VALUE
WWW-Authenticate: DPoP error="use_dpop_nonce"
~~~

The client generates a new proof with the `nonce` claim set to the server-provided value, a new `jti`, and a new `iat`. Never resend the old proof merely adding a nonce HTTP header; the nonce must be inside the JWT payload and the proof must be re-signed.

### 8.3. Proxies and URI Reconstruction

The Resource Server must determine the URI the client actually called. If a reverse proxy terminates TLS, the app must trust forwarded headers only from configured proxies. Never trust `X-Forwarded-Host` sent directly by arbitrary clients. Misconfigured URI reconstruction can cause `htu` validation to reject valid requests or create a bypass if the validator compares against an attacker-controlled URI.

## 9. How Do the Token Endpoint and Resource Server Differ?

| Check | Token Endpoint | Resource Server |
| --- | --- | --- |
| DPoP proof | Yes, when the client uses DPoP in the flow | Yes, when presenting a DPoP-bound access token |
| `htm` / `htu` | Matches POST and token endpoint URI | Matches method and URI of the API request |
| `ath` | Not sent in the proof for a token request | Required when the proof accompanies an access token |
| `cnf.jkt` | AS computes and embeds thumbprint in issued token | RS compares proof thumbprint with token confirmation |
| Client authentication | Still applied per RegisteredClient/method | Usually uses access token; not replaced by client auth |
| Nonce | AS may require its own nonce | RS may require its own nonce |
| Replay cache | Prevents proof replay at AS | Prevents proof replay at RS |

The DPoP proof at the token endpoint determines which key will be bound to the new access token. When a client uses a DPoP-bound refresh token, the AS must verify that the proof was created with the exact bound key per RFC rules. Never allow a client to swap the public key with a new proof without an authenticated binding transfer process.

## 10. Keys, Rotation, and Token Lifecycle

### 10.1. Key Rotation

When a private key is at risk of exposure or needs periodic rotation:
- Generate a new key pair using a secure process.
- Initiate an authorization/token issuance flow that binds new access tokens to the new key.
- Retain the old key only as long as needed for existing tokens, if policy permits.
- Revoke tokens bound to the old key in case of compromise.
- Delete the old key from the keystore once no valid tokens depend on it.

You cannot change `cnf.jkt` of an already-issued access token merely by sending a new public JWK. The old token remains bound to its original thumbprint.

### 10.2. Backup and Restore

If a key is lost after an app reinstall or backup restore, the client cannot generate proofs for bound tokens. Require reauthorization or provide a secure recovery mechanism. Never export private keys into uncontrolled cloud backups just for session convenience.

### 10.3. When a Key Is Compromised

An attacker holding both the private key and access token can produce valid proofs. DPoP cannot distinguish a legitimate client from an attacker controlling the same key. You must revoke tokens, rotate/re-register keys, investigate the device, and control refresh tokens/authorizations per policy.

## 11. DPoP in Spring Security and Spring Authorization Server Applications

DPoP is an HTTP/JWT-layer protocol. When integrating with Spring, separate responsibilities:
- **Client:** creates a proof JWT per request using its private key.
- **Authorization Server:** verifies proofs at the token endpoint, selects the proven public key, and binds issued tokens to its thumbprint.
- **Resource Server:** verifies DPoP proofs on each protected request and compares the thumbprint with the access token.
- **Persistence/operations:** stores/revokes token state, manages nonces, and maintains a replay cache when required.

### 11.1. Version-Specific Checks

Spring Security and Spring Authorization Server APIs evolve across releases. Do not infer full DPoP support merely because an application has OAuth2 Resource Server, a JWT decoder, or a token customizer.

On your actual dependency tree, check:
1. Whether the Resource Server has built-in DPoP authentication/proof validation or needs a custom filter/provider.
2. Whether the Authorization Server supports DPoP proofs at the token endpoint and populates `cnf.jkt` or needs a custom converter/provider/token customizer.
3. Whether refresh tokens are sender-constrained to the same key.
4. How DPoP nonces and replay detection are stored/propagated.
5. Whether JWT access tokens and opaque tokens share the same confirmation semantics.
6. How error responses, `WWW-Authenticate`, and `DPoP-Nonce` comply with RFC 9449.

**`JwtDecoder` only verifies the access token JWT.** It does not verify the proof JWT in the `DPoP` header, check `htm`/`htu`/`ath`, or prevent proof replay without a dedicated DPoP mechanism.

### 11.2. Extension Architecture at the Authorization Server

If your SAS version does not provide full built-in DPoP issuance, an extension design might include:
- A converter/endpoint integration reading the `DPoP` header on token requests.
- A proof verifier checking `typ`, `alg`, public JWK, signature, `htm`, `htu`, `iat`, `nonce`, and `jti`.
- Verification output returning the public JWK thumbprint.
- A token generator/customizer attaching `cnf.jkt` to the access token.
- For refresh tokens, persistence recording the binding and the provider verifying a proof with the same key before issuing subsequent tokens.

This is an **integration architecture**, not a copy-paste configuration guaranteed to work across all versions. Preserve all default SAS checks for grants, client authentication, scopes, authorization, and token lifecycle.

### 11.3. Extension Architecture at the Resource Server

If your Spring Security version does not yet include built-in DPoP validation matching your requirements, you need an authentication layer that combines:
1. Extracting the access token under the `DPoP` scheme.
2. Verifying the access token.
3. Parsing/verifying the DPoP proof.
4. Verifying claims and replay status.
5. Comparing `cnf.jkt`.
6. Producing a verified `Authentication` so Spring authorization continues checking scopes/authorities.

Do not add a filter that merely checks whether the `DPoP` header exists. A random string in the header does not prove possession.

## 12. Common Design Mistakes

**Mistake 1 — sending the private key in the JWK.** The public JWK must strip private parameters. Never serialize a private JWK into the proof header.

**Mistake 2 — reusing a proof multiple times.** Each HTTP request needs its own proof with a fresh `jti`, accurate method, and accurate URI. Retries must create a new proof.

**Mistake 3 — including query or fragment in `htu`.** The `htu` claim excludes query/fragment; the server must compare using URI normalization.

**Mistake 4 — omitting `ath` at the Resource Server.** Without binding the proof to a specific access token, an attacker could pair a proof with another token bound to the same key.

**Mistake 5 — verifying only the signature.** A valid signature is insufficient: you must also verify `htm`, `htu`, `iat`, `jti`, `ath`, `nonce`, and `cnf.jkt`.

**Mistake 6 — using the Bearer scheme for a DPoP-bound token.** The client must present the token with the `DPoP` scheme and a proof; the server must not fall back to `Bearer`.

**Mistake 7 — using a symmetric algorithm.** DPoP requires proofs signed with an asymmetric private key; reject `HS*` and `none`.

**Mistake 8 — keeping the replay cache only in per-node memory.** The same proof can be replayed against another node. Use a shared store or a mechanism with appropriate consistency.

**Mistake 9 — trusting forwarded headers from any source.** Attackers can manipulate URI reconstruction and corrupt `htu` validation. Trust only configured proxies.

**Mistake 10 — assuming DPoP blocks XSS or malware.** If an attacker controls the runtime or can invoke the key-signing operation, they can still generate valid proofs.

## 13. Test Matrix

| Category | Scenario | Expectation |
| --- | --- | --- |
| Header | Missing `typ` or `typ` other than `dpop+jwt` | Reject |
| Header | `alg=none` or symmetric MAC | Reject |
| Header | JWK contains private parameters | Reject |
| Signature | Invalid signature or mismatched key | Reject |
| Key binding | JWK thumbprint differs from `cnf.jkt` | Reject |
| Method | `htm` differs from actual HTTP method | Reject |
| URI | `htu` has wrong scheme/host/port/path | Reject |
| URI | `htu` contains query/fragment | Invalid proof |
| Time | `iat` too old or in the future beyond skew | Reject |
| Replay | Same `jti`/proof sent a second time | Reject |
| Token hash | `ath` computed from another token | Reject |
| Token hash | Missing `ath` when calling Resource Server with DPoP token | Reject |
| Nonce | Server requires nonce but proof is missing/invalid | Return challenge or reject per RFC |
| Token type | DPoP-bound token sent as Bearer | Reject |
| Token endpoint | Valid proof for POST token endpoint | Can issue token bound to `jkt` |
| Refresh | Bound refresh token used with a different key | Reject |
| Concurrency | Same proof sent simultaneously to two nodes | At most one request accepted |
| Proxy | Forged forwarded header from client | Does not alter trusted URI |
| Rotation | New key used with old access token | Reject |
| Revocation | Token revoked even though proof is valid | Reject token |
| Logging | Inspect logs after tests | No private keys/access tokens/sensitive proofs leaked |

### 13.1. Standalone `ath` Test

Create token A and token B. Generate a proof with `ath` for A, then send:
- Authorization header containing token A → should pass the `ath` check.
- Authorization header containing token B → must be rejected.
- Change one character in token A → `ath` mismatch.
- Send the proof to a different URI or with a different method → `htu`/`htm` mismatch.

### 13.2. Distributed Replay Cache Test

Send the same proof JWT to two Resource Server instances within the same time window. If both accept it, replay protection lacks the required consistency. Also test two nearly simultaneous requests to verify that the `(jkt, jti)` check-and-insert operation is atomic.

## 14. Scenario Exercise

An SPA calls `orders-api`. The Authorization Server issued an access token with the claim:

~~~json
{
  "aud": ["orders-api"],
  "cnf": {
    "jkt": "JKT_FOR_CLIENT_KEY_A"
  }
}
~~~

The client creates a DPoP proof using key A, `htm=GET`, `htu=https://api.example.com/orders/42`, and `ath` computed from the current token.

Analyze:

1. Why can an attacker who steals only the access token without key A not create a valid proof?
2. Why does embedding the public JWK in the proof not expose the private key?
3. If the client switches to key B while continuing to use the access token above, how must the server respond?
4. If an attacker puts access token B in the Authorization header while keeping the proof containing `ath` of token A, which check catches it?
5. If the same proof is replayed to two nodes, what must the replay cache guarantee?
6. If a reverse proxy terminates TLS, how does the Resource Server determine a trustworthy `htu`?
7. When `DPoP-Nonce` is required, how must the client construct a new proof?
8. Why does DPoP not by itself stop XSS controlling the browser from invoking the private key?

**Hint:** Token A is bound to key A's thumbprint via `cnf.jkt`; new proofs must be signed with private key A. `ath` binds the proof to the sent access token; `htm`/`htu` bind method/URI; `jti` and `iat` help prevent replay over time. The public JWK contains only public components. If the key changes, a new token or an AS-supported rollover process is required.

## 15. Production Implementation Checklist

1. **Key generation:** generate keys with a CSPRNG, using an allowed asymmetric algorithm and adequate key strength.
2. **Key storage:** keep private keys in an OS keystore/KMS/HSM or non-extractable WebCrypto where appropriate; never transmit private material.
3. **Public JWK:** include only public parameters in proofs; validate key type, curve, size, and algorithm.
4. **Proof header:** `typ=dpop+jwt`, allowlisted asymmetric `alg`, valid `jwk`.
5. **Proof claims:** unique `jti`, accurate `htm`/`htu`, fresh `iat`; `ath` when calling Resource Server; `nonce` when required.
6. **Token binding:** issue access tokens with `cnf.jkt` matching the thumbprint of the verified public JWK.
7. **Resource Server:** verify access token, proof, `ath`, `htm`, `htu`, `iat`, `jti`, `nonce`, and `cnf.jkt`.
8. **Replay:** shared/atomic cache keyed by `jkt`+`jti`, with TTL matching the proof window.
9. **Refresh:** if refresh tokens are DPoP-bound, verify the same key and disallow arbitrary binding changes.
10. **Proxy:** configure trusted proxies/external URI so `htu` cannot be spoofed.
11. **Lifecycle:** establish key rotation, revocation, backup/restore, and recovery plans.
12. **Spring integration:** verify capabilities against dependency versions; `JwtDecoder` does not replace a DPoP verifier.
13. **Testing:** negative tests, concurrent replay, multi-node, proxy, nonce, token hash, and key rotation.
14. **Operations:** never log private keys, access tokens, or raw proofs; track metrics for signature, `ath`, `htu`, replay, and nonce errors.

## 16. Reference Standards

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): proof structure, claims, headers, token binding, nonces, and validation.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): compact JWT serialization and signatures.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): public/private JWK structure.
- [RFC 7518 — JSON Web Algorithms (JWA)](https://www.rfc-editor.org/rfc/rfc7518.html): signature algorithms and key representations.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638.html): canonical JSON and thumbprint calculation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): JWT access token profile and claims.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT access token verification; DPoP proof validation is a separate responsibility if your version does not provide built-in integration.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): Java library used to create/verify JWS and JWK.

**Takeaway:** A DPoP proof is a JWT signed with the **client's private key**, containing a public JWK in its header and claims binding the method, URI, timestamp, and proof ID; when calling a Resource Server, it also includes `ath` binding the proof to the access token. The Authorization Server binds the token to the JWK thumbprint via `cnf.jkt`. The Resource Server accepts the request only when the signature, request claims, replay/nonce checks, and thumbprint are all valid. The public JWK can be shared openly; the private key must remain inside the client-controlled environment.
