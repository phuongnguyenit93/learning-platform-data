# A DPoP Proof Differs from an Access Token and Is Signed with the Client's Key

In **Spring Security OAuth 2.0 / OIDC Resource Server**, a Bearer Access Token can be used by anyone holding it: the sender simply includes the token in the request. That is convenient, yet if the token is copied from logs, browser storage, a device, or a compromised connection, whoever obtains it can try using it just like the legitimate client until the token expires or is revoked.

**DPoP (Demonstrating Proof of Possession)** under **RFC 9449** adds proof that the request sender possesses the private key bound to the Access Token. The client creates a key pair, keeps the private key, and signs a **separate DPoP proof JWT for each HTTP request**. The Resource Server verifies the proof signature, checks that the proof is bound to the exact request and Access Token, and compares the public-key thumbprint in the proof against the token's binding information.

A DPoP proof and an Access Token serve different roles:

- **Access Token** is the credential carrying access permissions: subject/client, audience, scopes/authorities, and expiration per the token contract.
- **DPoP proof** is a short-lived JWT signed by the client with its private key, proving possession of the key for a specific request.
- **Public JWK** resides in the proof header so the recipient can verify the signature; the private key is never sent to the server.
- **Key binding** is represented inside the Access Token by the `cnf.jkt` (confirmation key thumbprint) claim. A proof is valid for the token only if the thumbprint matches.

Therefore, **a DPoP proof does not replace the Access Token and does not grant scopes/roles on its own**. A valid proof only proves the request was signed with the matching key; the Resource Server must still validate the Access Token, audience, issuer, expiration, endpoint permissions, and data-level permissions.

This lesson is part of the **Proof-of-Possession Tokens** chapter, using **Java 17+, Spring Boot 3.x, Spring Security 6.x** as context. It covers DPoP proof structure, token issuance flow, requests to the Resource Server, `ath`/`cnf.jkt`, nonces, replay protection, key lifecycle, Spring Security integration, and testing. Built-in DPoP support depends on the specific version/component; do not assume a regular JWT Resource Server configuration automatically enforces all of RFC 9449.

## 1. The Problem with Bearer Access Tokens

With the standard Bearer mechanism:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

The Resource Server validates the token. Anyone who has the token can send the request; the server has no cryptographic proof that the sender is the original client that received the token.

~~~text
Legitimate client ---- Access Token T ----> Resource Server
       |
       +---- Token T copied ----> Attacker
                                     |
                                     +---- Bearer T ----> Resource Server
~~~

If T has not expired, has not been revoked, and has the right scope, a Bearer API may accept both requests. TLS protects the token in transit over the connection, but **does not prevent the token from being stolen from storage or an endpoint system**.

DPoP changes the acceptance condition:

~~~text
Access Token T is bound to public key K

Client holds private key k
       |
       +-- creates proof P and signs with k
       |
       v
Request: DPoP token T + proof P
       |
       v
Resource Server checks:
  - Is Access Token valid?
  - Does proof signature match public key K?
  - Does Thumbprint(K) == token.cnf.jkt?
  - Is proof for the right HTTP method/URI?
  - Is proof fresh and not replayed?
       |
       v
Only then evaluate scopes and resource permissions
~~~

An attacker who copies only Access Token T **without the private key** cannot create a valid new proof for their requests. That is the **sender-constrained token** mechanism.

## 2. Three Objects That Must Not Be Confused

| Object | What Is It? | Who Creates/Signs It? | Role |
| --- | --- | --- | --- |
| **Access Token** | OAuth credential, either opaque or JWT. | Issued by Authorization Server; if JWT, signed by AS. | Carries resource access permissions. |
| **DPoP proof JWT** | Short-lived JWT, usually created per request. | Signed by the client with its DPoP private key. | Proves possession and binds proof to request/token. |
| **DPoP key pair** | Client's public key + private key. | Created/managed by the client. | Private key signs proofs; public key is bound to the token via thumbprint. |

A helpful mnemonic:

- **The Token answers:** "Which resources are you permitted to access?"
- **The Proof answers:** "Was this request signed by the party holding the key bound to the token?"
- **The Resource Server answers:** "Are the token and proof valid, and does the principal have permission to perform this operation?"

The DPoP key is **not** the Authorization Server's signing key. The DPoP private key belongs to the client; the DPoP public key is sent in the proof. The AS's signing key is still used to sign JWT Access Tokens if the system issues tokens as JWTs.

## 3. Client Key Pair and JWK

The client creates an asymmetric key pair:

~~~text
Private key k
  - held only by the client
  - used to sign DPoP proofs
  - never sent over HTTP

Public key K
  - may be shared publicly
  - placed in the DPoP proof header as a JWK
  - used by the Resource Server to verify the proof signature
~~~

Example EC P-256 public JWK:

~~~json
{
  "kty": "EC",
  "crv": "P-256",
  "x": "f83OJ3D2xF4...",
  "y": "x_FEzRu9v..."
}
~~~

This is an illustrative shape only; the coordinates are truncated so it is not a usable key. **Private members** such as `d` in an EC JWK or `d` in an RSA JWK must not be sent in a DPoP proof. The client must protect the private key in a keystore, secure enclave, TPM, OS credential store, or another mechanism appropriate for its environment.

### 3.1. Thumbprint of the Public Key

DPoP uses the **JWK Thumbprint** per RFC 7638 to identify a public key consistently. For an EC P-256 key, the thumbprint is computed from the canonicalized JWK members:

~~~text
{"crv":"P-256","kty":"EC","x":"...","y":"..."}
~~~

Then:

~~~text
jkt = BASE64URL-ENCODE(
        SHA-256(canonical-JWK-thumbprint-input)
      )
~~~

Do not hash an arbitrary JSON JWK serialization with random field ordering or whitespace. Use a canonicalization/serialization algorithm compliant with RFC 7638.

### 3.2. Why Use a Thumbprint Instead of the Full Public Key in the Access Token?

The Access Token only needs to carry a short binding value:

~~~json
{
  "cnf": {
    "jkt": "BASE64URL_JWK_THUMBPRINT"
  }
}
~~~

When the client sends a proof containing the public JWK, the Resource Server computes the thumbprint itself and compares it against `cnf.jkt` in the verified token. If they differ, the proof cannot be used with that token.

**Never read `cnf.jkt` from an unverified token and grant access.** Verify the Access Token first, or use a trusted opaque-token verification/introspection flow that returns `cnf` metadata.

## 4. Structure of a DPoP Proof JWT

A DPoP proof is a JWT with its own header and payload. The header typically contains:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "PUBLIC_KEY_X",
    "y": "PUBLIC_KEY_Y"
  }
}
~~~

Meaning:

- `typ` must be `dpop+jwt` per the DPoP profile.
- `alg` is an accepted asymmetric signature algorithm, e.g., `ES256` for EC P-256.
- `jwk` contains the public key corresponding to the private key used to sign the proof.
- Never put the private key in the JWK.
- Reject insecure algorithms, `none`, or downgrade configurations outside the allowlist.

The proof payload typically contains:

~~~json
{
  "jti": "unique-proof-id-7b2...",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1893452400,
  "ath": "BASE64URL_SHA256_OF_ACCESS_TOKEN"
}
~~~

Key claims:

| Claim | Meaning | Resource Server Checks |
| --- | --- | --- |
| `jti` | Unique ID of the proof. | Replay protection; the same proof must not be accepted again within the validity window. |
| `htm` | HTTP method the proof is intended for, e.g., GET/POST. | Matches the method of the current request. |
| `htu` | HTTP target URI the proof is intended for, excluding query and fragment per RFC. | Matches the request URI after proper canonicalization. |
| `iat` | Proof creation timestamp. | Lies within the accepted time window. |
| `ath` | Hash of the Access Token. | Binds the proof to the exact token sent in the resource request. |
| `nonce` | Server-provided nonce when required. | Proof must use a valid/unexpired nonce per server policy. |

Not every proof includes every claim in every context. In particular, `ath` binds a proof to an Access Token in a **resource request**; at the token endpoint when requesting a token, no new Access Token exists yet to hash, so `ath` is not sent for that token request.

## 5. What Do the Proof Claims Bind?

### 5.1. htm: HTTP Method

If the proof is generated for:

~~~http
GET /api/orders/42
~~~

then `htm` is:

~~~json
{"htm":"GET"}
~~~

An attacker cannot take that same proof, change the request to `DELETE`, and pass method binding, because the Resource Server must match the method. The method must reflect the actual HTTP method value and RFC rules; do not arbitrarily lowercase or transform it inconsistently between proxy and application.

### 5.2. htu: HTTP Target URI

The proof binds the target URI, for example:

~~~json
{
  "htu": "https://api.example.test/api/orders/42"
}
~~~

Under RFC 9449, `htu` represents the target URI with **query and fragment stripped**. Therefore, do not treat DPoP as a signature over the entire HTTP message:

- A DPoP proof does not sign the request body.
- A DPoP proof does not bind the query string the way a full-request signature does.
- TLS is still needed to protect request and response contents.
- The API must still validate queries/bodies and enforce business authorization.

When running behind a reverse proxy, reconstructing the public URI must rely on **trusted** proxies/gateways. Never blindly take `Host`, `X-Forwarded-Host`, or `Forwarded` from unauthenticated clients to compute `htu`, or an attacker can manipulate how the server matches URIs.

### 5.3. iat: Creation Timestamp

`iat` is usually a NumericDate (Unix epoch seconds). The Resource Server enforces a short time window, e.g., the proof must not be older than a configured interval:

~~~text
now - allowedAge <= iat <= now + allowedClockSkew
~~~

Numbers must fit clock synchronization and policy. Proofs that are too old or too far in the future beyond clock skew must be rejected.

### 5.4. jti: Unique Identifier and Replay Prevention

Each proof requires a unique `jti`, typically a random value with high entropy. The server can store the pair:

~~~text
(JWK thumbprint, jti)
~~~

in a replay cache with a TTL matching the valid proof window. If the same proof is submitted again, the server detects the already-used `jti` and rejects it.

Checking only `iat` is insufficient: an attacker can replay a proof within the same freshness window. **Freshness and replay detection are two distinct checks.**

### 5.5. ath: Binding the Proof to the Access Token

For requests to a Resource Server, `ath` is:

~~~text
ath = BASE64URL-ENCODE(
        SHA-256(ASCII(access_token))
      )
~~~

Base64url encoding uses the no-padding format per JOSE rules. The Resource Server computes this itself from the **Access Token received in the Authorization header** and compares it against `ath` in the proof.

Effect: a proof signed for token T1 cannot be paired with another token T2. If `ath` is missing or the hash mismatches, the proof is invalid for a resource request.

## 6. How Is a Proof JWT Different from an Access Token JWT?

Both can be serialized as compact JWTs:

~~~text
header.payload.signature
~~~

Yet sharing a format does not make them the same type of credential.

| Criterion | Access Token JWT | DPoP Proof JWT |
| --- | --- | --- |
| Purpose | Grants API access permissions. | Proves possession for a single request. |
| Signer | Authorization Server. | Client holding the DPoP private key. |
| Header type | Per Access Token profile, e.g., `at+jwt` when applying RFC 9068. | `dpop+jwt`. |
| Verification key | AS's public signing key. | Public JWK provided by the client in the proof, then matched by thumbprint. |
| Contents | Issuer, subject, audience, scopes, expiration, confirmation binding. | `htm`, `htu`, `iat`, `jti`, `ath`, and optionally `nonce`. |
| Lifetime | Typically reused across requests until expiry/revocation. | Short-lived, specific to a single request. |
| Grants scopes itself? | Can carry scopes/authorities per token contract. | **No.** |
| Usable as a Bearer token? | Only if the token was issued for that usage mode. | **No.** |

An Access Token may be **opaque** rather than a JWT. In that case, the RS introspects the token to obtain metadata, including the `cnf` confirmation claim if returned by the AS per contract; the DPoP proof is still a client-signed JWT.

## 7. Flow for Issuing a DPoP-Bound Access Token

DPoP starts before the client calls the Resource Server: the client must include a public-key proof in the **token request** so the Authorization Server can bind the new token to the key.

~~~text
Client                           Authorization Server
  |                                       |
  | Create DPoP key pair (k, K)           |
  | Keep private key k                    |
  |                                       |
  | POST /oauth2/token                    |
  | DPoP: proof-signed-by-k               |
  | grant_type=authorization_code ...     |
  |-------------------------------------->|
  |                                       |
  | AS verifies DPoP proof                |
  | - typ/alg/signature                   |
  | - htm/htu/iat/jti/nonce               |
  | - public JWK and thumbprint           |
  |                                       |
  | AS issues Access Token T              |
  | attaches cnf.jkt = thumbprint(K)      |
  |                                       |
  | access_token=T, token_type=DPoP       |
  |<--------------------------------------|
  |                                       |
~~~

### 7.1. Token Endpoint Request

Illustrative example:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: DPOP_PROOF_JWT_SIGNED_BY_CLIENT_KEY

grant_type=authorization_code&
code=AUTHORIZATION_CODE&
redirect_uri=https%3A%2F%2Fclient.example.test%2Fcallback&
code_verifier=PKCE_CODE_VERIFIER&
client_id=orders-web
~~~

The DPoP proof in the `DPoP` header is signed with the client's private key. It binds to the token endpoint request via `htm` and `htu`, includes `iat`/`jti`, and may need to include a server nonce.

In this request, **there is no `ath` for the new Access Token**, because the token has not been issued yet. Grant/PKCE/client authentication checks still apply per the OAuth flow; DPoP does not replace them.

### 7.2. Token Response

A response might look like:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "ACCESS_TOKEN_VALUE",
  "token_type": "DPoP",
  "expires_in": 600,
  "scope": "orders.read"
}
~~~

If the Access Token is a JWT, the claims signed by the AS may include:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "person-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000,
  "cnf": {
    "jkt": "BASE64URL_JWK_THUMBPRINT"
  }
}
~~~

For opaque tokens, binding info can be obtained by the RS via introspection. What matters is that **the AS issues the token bound to the public key for which the proof demonstrated possession**, and the RS has a reliable way to read the confirmation binding.

### 7.3. Why Is `token_type` Set to `DPoP`?

The token response specifies `token_type` as `DPoP`. When calling the Resource Server, the client uses the `DPoP` authorization scheme instead of `Bearer`:

~~~http
Authorization: DPoP ACCESS_TOKEN_VALUE
~~~

If a token was issued under a DPoP-bound profile, the client must not arbitrarily switch to `Bearer` and expect the API to still enforce the sender constraint. The Resource Server must properly distinguish token usage and policy; never silently downgrade a DPoP-bound token to Bearer.

## 8. Calling the Resource Server: Access Token and Proof Travel Together

Each protected-resource request sends two components:

1. **Access Token** in the Authorization header with the `DPoP` scheme.
2. **DPoP proof JWT** in the `DPoP` header.

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP ACCESS_TOKEN_VALUE
DPoP: DPOP_PROOF_JWT_FOR_THIS_REQUEST
Accept: application/json
~~~

The proof has an illustrative payload:

~~~json
{
  "jti": "request-proof-42-unique",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1893452400,
  "ath": "BASE64URL_SHA256_OF_ACCESS_TOKEN"
}
~~~

The proof header carries the public JWK and signature made with the private key:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "PUBLIC_KEY_X",
    "y": "PUBLIC_KEY_Y"
  }
}
~~~

### 8.1. Steps the Resource Server Must Verify

~~~text
1. Receive Authorization: DPoP <access-token>
2. Receive DPoP: <proof-jwt>
3. Validate Access Token via JWT decoder or introspection
4. Confirm token was issued for DPoP usage and contains cnf.jkt
5. Parse proof header:
     typ = dpop+jwt
     alg in asymmetric allowlist
     jwk is a valid public key
6. Verify proof signature using public JWK
7. Compute JWK thumbprint and compare with token.cnf.jkt
8. Check htm and htu against current HTTP request
9. Check iat within freshness window
10. Check jti has never been used (replay cache)
11. Check ath matches Access Token
12. Check nonce if required by server
13. Once authentication completes, check scope/role/domain
~~~

Detailed implementation order may vary by framework, but **no security condition may be omitted**. In particular, never create a successful Authentication merely because the Access Token is valid if the token requires a DPoP proof and the proof is missing or invalid.

### 8.2. Why Must the Proof Be Fresh for Every Request?

A proof has `htm`/`htu` bound to a specific method/URI and a unique `jti`. The client generates a fresh proof for every request, even two GET requests to the same endpoint:

~~~text
Request A: jti=proof-A, iat=t1, htm=GET, htu=/orders/42
Request B: jti=proof-B, iat=t2, htm=GET, htu=/orders/42
~~~

Do not cache a proof JWT for reuse across multiple HTTP requests. Reuse may be rejected by replay detection and does not reflect the new request.

## 9. DPoP Proofs Are Signed with the Client's Private Key

The client performs these general steps:

1. Generate a DPoP key pair using a supported algorithm.
2. Build a header containing `typ=dpop+jwt`, `alg`, and public `jwk`.
3. Build a payload with random `jti`, `htm`, `htu`, `iat`, `ath` when calling a resource, and `nonce` if applicable.
4. Sign `header.payload` with the **private key**.
5. Send the compact JWT in the `DPoP` header.

~~~text
proof = BASE64URL(header)
      + "."
      + BASE64URL(payload)
      + "."
      + SIGN(privateKey, signingInput)
~~~

This is a conceptual JOSE description. In production, use a maintained JOSE library, configure algorithms explicitly, and never hand-roll cryptography.

### 9.1. A Public JWK Is Not a Private Credential

The server needs the public key to verify the signature. If a client accidentally sends the private JWK member `d`, that is a severe bug: the private key has been leaked. The Resource Server must reject public JWKs containing private material per the appropriate profile/algorithm; the client must keep the private key in secure storage.

### 9.2. Keys Can Be Software- or Hardware-Backed

Depending on the client:

- Native mobile can use the OS keystore or hardware-backed keys.
- Desktop apps can use the platform credential store.
- Server-side confidential clients can use an HSM/keystore.
- Browser clients can use Web Crypto non-extractable keys, though XSS can still invoke signing APIs if running in the same origin.

**Non-extractable does not mean impossible to abuse**: malicious JavaScript unable to read the raw private key bytes can still invoke signing operations if it executes within the application context.

## 10. `ath`: Binding the Proof to the Exact Access Token

If a client sends:

~~~http
Authorization: DPoP TOKEN_A
DPoP: PROOF_FOR_TOKEN_A
~~~

the proof needs `ath` to be the hash of TOKEN_A itself:

~~~text
ath = BASE64URL_NO_PADDING(
        SHA-256(ASCII(TOKEN_A))
      )
~~~

If an attacker replaces the Authorization header:

~~~http
Authorization: DPoP TOKEN_B
DPoP: PROOF_FOR_TOKEN_A
~~~

the Resource Server recomputes the hash of TOKEN_B. It differs from `ath` in the proof, so the request is rejected.

### 10.1. Hashing the Access Token Does Not Re-Sign the Token

`ath` does not turn a proof into an Access Token and carries no scopes. It merely binds the proof to a specific token. The token must still be verified:

- JWT: signature, issuer, audience, expiration, token profile, and validators.
- Opaque: successful introspection, `active` true, and appropriate metadata.

Only then check `cnf.jkt` and the DPoP proof.

### 10.2. Do Not Omit `ath` in Resource Requests

If a proof has a valid signature but no token binding, there is a risk in some scenarios that a valid proof could be paired with a different credential. Under the DPoP profile, the Resource Server must verify `ath` against the Access Token of the protected-resource request. **Do not confuse this rule with token endpoint requests**, where no Access Token has been issued yet.

## 11. `cnf.jkt`: Which Key Is the Access Token Bound To?

In the verified Access Token:

~~~json
{
  "sub": "person-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "THUMBPRINT_OF_CLIENT_PUBLIC_JWK"
  }
}
~~~

The DPoP proof contains a public JWK. The Resource Server:

1. Verifies the Access Token or fetches trusted introspection metadata.
2. Reads `cnf.jkt`.
3. Reads the public JWK in the proof header.
4. Computes the JWK thumbprint per RFC 7638.
5. Compares the values.

~~~text
Access Token:
  cnf.jkt = thumbprint(K1)

DPoP proof:
  header.jwk = K1
  computed thumbprint = thumbprint(K1)

Compare: MATCH -> proceed to remaining proof checks
~~~

If the proof was signed by key K2:

~~~text
Access Token cnf.jkt = thumbprint(K1)
Proof JWK thumbprint  = thumbprint(K2)

K1 != K2 -> REJECT
~~~

### 11.1. With Opaque Access Tokens

If the Access Token is opaque, the RS cannot decode claims itself. It requires an introspection response or a trusted adapter supplying confirmation binding info per contract:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "sub": "person-42",
  "aud": ["orders-api"],
  "cnf": {
    "jkt": "THUMBPRINT_OF_CLIENT_PUBLIC_JWK"
  }
}
~~~

If a token is DPoP-bound yet the introspection adapter does not return `cnf` or distinguish token types, the RS **lacks sufficient information to verify the sender constraint**. Never fall back to Bearer acceptance simply because the token is active.

### 11.2. `cnf` Is Confirmation, Not Permission

`cnf.jkt` only states which public key the token is bound to. It does not indicate:

- That the client is allowed to read all tenants.
- That the user has admin privileges.
- That the request body is valid.
- That the token's scope permits write operations.

Those are separate authorization decisions.

## 12. Nonces: The Server Can Require Proofs to Use a Fresh Challenge

DPoP can use a **server-provided nonce** to strengthen replay protection and limit pre-generation of proofs by clients.

Flow:

~~~text
Client -> Resource Server
  Request with DPoP proof lacking a nonce

Resource Server -> Client
  DPoP-Nonce: SERVER_NONCE_VALUE
  response requiring a fresh proof

Client creates a new proof:
  jti = new value
  iat = current time
  nonce = SERVER_NONCE_VALUE
  htm/htu/ath = current request

Client -> Resource Server
  Request + new proof
~~~

The Resource Server can return a `DPoP-Nonce` response header for the client to use on its next attempt. The client must generate a **new proof**, rather than copying the old proof and patching its payload (modifying the payload invalidates the old signature).

### 12.1. Nonces Do Not Replace `jti`

Nonces and `jti` serve related yet distinct purposes:

- **Nonce** proves the proof uses a recent server-issued challenge.
- **jti** identifies a specific proof so the server can detect reuse.
- **iat** enforces freshness by clock time.

If you rely solely on a nonce while accepting the same `jti` multiple times, replay gaps may remain depending on how nonces are managed. If you check only `iat`, a proof can still be replayed within the allowed age window.

### 12.2. Nonces Must Be Scoped to the Right Server/Resource Context

Clients must not reuse a nonce from server A with server B. The server must generate, store, or verify nonces per its own policy, with appropriate TTLs and anti-tampering controls. With multiple replicas, nonce validation must be consistent across nodes that might handle subsequent requests, or use a mechanism supporting distributed verification.

## 13. Replay Protection and the `jti` Cache

A proof is a signed message. If an attacker steals **both the Access Token and an unused DPoP proof**, the attacker can try replaying the exact request within the proof's valid time window. DPoP requires replay detection.

A replay cache model:

~~~text
key = (JWK thumbprint, jti)
value = firstSeenAt
TTL = proof acceptance window + clock margin
~~~

When a request arrives:

1. Verify the proof signature.
2. Check `iat` and nonce per policy.
3. Compute the public JWK thumbprint.
4. Perform an **atomic insert-if-absent** for `(jkt,jti)`.
5. If the key already exists, reject the replayed proof.
6. If insertion succeeds, proceed to verify `htm`, `htu`, `ath`, and token binding per the designed pipeline.

**Atomicity matters:** two concurrent requests hitting two replicas with the same proof must not both pass simply because each node checks an independent local map. If cluster-wide replay protection is required, use a shared store or a deliberately designed routing/consistency strategy.

### 13.1. Why a Local In-Memory Cache Alone Has Limits

~~~text
Request proof P -> Node A: jti unseen -> accept
Replay proof P  -> Node B: jti unseen at B -> may accept
~~~

If a load balancer can send the same proof to multiple nodes, a local cache is insufficient for cluster-wide guarantees. You can:

- Use a distributed replay store with atomic inserts.
- Use a nonce/validation strategy verifiable across nodes.
- Enforce routing affinity within the needed scope, if permitted by your threat model and infrastructure.

Never claim "DPoP prevents cluster-wide replay" just because each node has a Caffeine cache.

### 13.2. Cache TTL Must Match Proof Freshness

Replay records must be retained long enough to cover the **entire window during which a proof can be accepted**. If a proof is accepted for 60 seconds yet the replay cache evicts after 10 seconds, an attacker can replay the proof during the remaining 50 seconds.

Conversely, an excessively long TTL increases memory consumption and invites DoS via large volumes of proof IDs. You need to:

- Bound proof age.
- Limit the size/rate of the replay cache.
- Use keys with proper namespacing/partitioning.
- Synchronize clocks and monitor cache availability.
- Fail closed when replay checks cannot be guaranteed per policy.

## 14. DPoP Does Not Replace TLS or Sign the Entire HTTP Request

DPoP binds specific attributes:

- HTTP method (`htm`).
- Target URI (`htu`) per RFC rules.
- Creation timestamp (`iat`).
- Proof identifier (`jti`).
- Access Token hash (`ath`) for resource requests.
- Client public key (JWK/`cnf.jkt`).

DPoP **does not sign the request body** and provides no data encryption. TLS is still required to protect:

- The Authorization header and DPoP header from eavesdropping.
- The request body, query parameters, and response.
- Confidentiality/integrity of application data.
- Client/server transport authentication per architecture.

If an API needs application-layer integrity over the body or payload, a separate appropriate message-signing mechanism is needed; do not interpret DPoP as signing every byte of the HTTP message.

### 14.1. DPoP Does Not Prevent Every Type of Compromise

DPoP reduces the risk of a **standalone stolen Access Token**. It does not protect on its own when:

- An attacker obtains the private key as well.
- An attacker controls the client application and can invoke the key-signing API.
- Malware/extensions have execution rights inside the browser profile.
- A valid request/proof is relayed within the allowed window before the replay cache records it.
- The Resource Server skips checking `ath`, `htu`, `htm`, or replay.
- A private key is shared uncontrollably across multiple users/devices.

Thus, DPoP is a sender-constraint layer, not a replacement for secure storage, TLS, XSS prevention, endpoint security, or authorization.

## 15. DPoP Compared to Bearer and mTLS-Bound Tokens

| Criterion | Bearer Token | DPoP-Bound Token | mTLS-Bound Token |
| --- | --- | --- | --- |
| Proof of possession | Holding the token is enough. | Client signs a proof with its private key per request. | Client proves private key possession via TLS handshake/certificate. |
| Key binding | Not required. | Public-key thumbprint in token (`cnf.jkt`). | Certificate binding, typically via the corresponding confirmation claim. |
| Per-request data | No DPoP proof. | `htm`, `htu`, `iat`, `jti`, `ath`, nonce when needed. | TLS connection/client certificate provides binding. |
| Best fit | Ubiquitous, easy to integrate. | Native apps, browser/public clients, environments where client certs are hard. | Service-to-service or well-managed certificate environments. |
| Replay defense | Relies mainly on protecting the token/TLS. | Proof freshness, `jti`, nonce, and token binding. | TLS handshake/connection binding; still requires protecting tokens and sessions. |
| Complexity | Lower. | Client and RS must generate/verify proofs and replay policies. | PKI, certificate lifecycle, and TLS termination complexity. |

DPoP and mTLS are both sender-constrained approaches, but they bind at different layers. Never fall back from DPoP to Bearer when a proof fails just to increase compatibility if the token was issued with a DPoP requirement.

## 16. Client Key Lifecycle

### 16.1. Key Creation and Storage

The client should:

1. Generate the key pair from a CSPRNG using a supported algorithm.
2. Never export private keys to logs, analytics, or the network.
3. Protect keys using an OS keystore/HSM/secure enclave or Web Crypto depending on environment.
4. Isolate keys by application installation/device/user context as appropriate.
5. Maintain backup/recovery/re-enrollment procedures per threat model; do not arbitrarily sync private keys over the cloud.

### 16.2. When a Key Is Lost

If the private key is lost, the client can no longer produce valid proofs for tokens bound to the old thumbprint. You must:

- Initiate an authorization/token issuance flow to bind a new token to a new key.
- Revoke the old token if it is still usable and policy requires it.
- Never modify `cnf.jkt` in an old token; that claim is issued/signed by the AS.
- Handle refresh tokens per the AS's sender-constraint policy.

### 16.3. When a Key Is Compromised

If an attacker obtains the private key:

- DPoP no longer stops the attacker from using tokens bound to that key.
- Revoke tokens/grants and require new tokens bound to a new key.
- Invalidate affected devices/sessions per policy.
- Audit logs for proof requests and resource access.
- Do not just delete the public JWK from the client; the AS/RS must update token state and key binding lifecycle.

### 16.4. Key Rotation

An old token bound to thumbprint K1 and a new token bound to K2:

~~~text
Token T1: cnf.jkt = thumbprint(K1)
Token T2: cnf.jkt = thumbprint(K2)
~~~

A proof signed with K2 cannot be used with T1. During transition, the client may need to retain K1 to use old tokens until they expire/are revoked while requesting new tokens bound to K2. How refresh tokens and re-binding work must follow the AS implementation and OAuth flow; do not swap keys and expect old tokens to update automatically.

## 17. DPoP with Spring Security Resource Server

Spring Security includes OAuth 2.0 Resource Server components for Bearer JWTs and opaque tokens. However, **merely configuring a JWT decoder or opaque introspector does not prove all of RFC 9449 is enforced**. A complete DPoP implementation must handle:

1. Distinguishing the `DPoP` scheme from `Bearer`.
2. Validating the Access Token according to its token format.
3. Verifying the DPoP proof JWT, public JWK, and asymmetric algorithm.
4. Matching `cnf.jkt`.
5. Checking `htm`, `htu`, `iat`, `jti`, `ath`, and `nonce`.
6. Replay detection with concurrency/cluster semantics.
7. Returning DPoP nonce challenges/response headers if applicable.
8. Only then creating an `Authentication` for the authorization layer.

**Built-in support depends on your Spring Security and Authorization Server versions.** Before choosing an API, verify the documentation for your exact version. If your version lacks full built-in support, you need a dedicated, reviewed integration or a gateway/authorization component that supports DPoP. Never conclude `oauth2ResourceServer().jwt()` handles proofs on its own.

### 17.1. JWT Access Token Validation Still Needs Standard Configuration

Spring Security Servlet example for a JWT Resource Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http)
            throws Exception {
        return http
            .csrf(AbstractHttpConfigurer::disable)
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This is a **standard JWT Resource Server configuration**, illustrating Access Token validation and authorization. It **does not automatically perform DPoP proof verification**. Do not use this configuration alone as proof that DPoP is enabled; a DPoP integration must sit properly in the authentication pipeline and block Bearer fallback for DPoP-bound tokens.

For opaque tokens, token validation can use `OpaqueTokenIntrospector`; the DPoP integration must still inspect `cnf` in the introspection metadata and verify the proof independently.

### 17.2. Conceptual Integration Pipeline

~~~text
HTTP request
  |
  v
Extract DPoP authorization scheme + DPoP header
  |
  v
Access Token authentication
  |   JWT decoder / opaque introspection
  |   issuer, audience, exp, active
  v
Get verified cnf.jkt
  |
  v
DPoP proof verifier
  |   typ / alg / public jwk / signature
  |   htm / htu / iat / jti / ath / nonce
  |   replay cache
  v
Create authenticated principal
  |
  v
Spring Security authorization
  |   scopes / roles / method security
  v
Domain tenant / owner / object checks
  |
  v
Controller
~~~

This is a **responsibility diagram**, not a built-in class/filter. Ensure DPoP failures are never downgraded to an anonymous request that passes an overly broad `permitAll` rule, and that no protected endpoint accidentally accepts DPoP-bound tokens via the Bearer scheme.

### 17.3. Filter Order and Error Handling

An integration must distinguish:

- **Invalid Access Token:** authentication fails.
- **Valid token but missing proof:** sender constraint unsatisfied; request rejected per DPoP protocol.
- **Invalid proof signature or wrong method/URI/ath:** invalid proof.
- **Replayed `jti`:** reject previously used proof.
- **Nonce required/missing:** may return a challenge with `DPoP-Nonce` per RFC.
- **Valid token, valid proof, but missing scope:** 403 authorization error.

Do not catch every exception and return a generic 401 if doing so strips required challenge/nonce semantics. At the same time, never leak private key details, tokens, or proof contents in responses/logs.

## 18. DPoP and Reverse Proxies

`htu` must be compared against the actual request URI per RFC rules. When the API sits behind a proxy:

~~~text
Client -- HTTPS --> API Gateway -- HTTP/internal TLS --> Spring App
~~~

Spring may see only:

~~~text
http://orders-service:8080/api/orders/42
~~~

while the client signed:

~~~text
https://api.example.test/api/orders/42
~~~

If the two strings are compared improperly, valid requests fail; if untrusted forwarded headers are accepted, an attacker can manipulate the URI used by the verifier.

Proper design:

- Determine the canonical external URI using trusted proxy configuration.
- Trust forwarded headers only from authenticated/configured proxies.
- Normalize scheme/host/port/path per the DPoP profile.
- Test URL encoding variants, default ports, path normalization, and redirects.
- Never strip paths or append query/fragments just to "make the proof pass."
- Test through the exact gateway/ingress topology used in production.

## 19. DPoP and HTTP Redirects

A proof created for URI A cannot arbitrarily be used for URI B:

~~~text
Client -> https://api.example.test/orders/42
  302 Location: https://other.example.test/orders/42
~~~

When following a redirect, the client must consider **creating a new proof** for the target request, with the matching `htu`/`htm` and appropriate token. Never forward Access Tokens/DPoP proofs to another host simply because of a redirect. Client libraries need clear policies on redirects and Authorization headers, especially cross-origin.

If a resource server redirects across hosts/schemes, test DPoP behavior; avoid designs that force clients to expose tokens to disallowed origins.

## 20. DPoP with OIDC and PKCE

DPoP, OIDC, and PKCE address different concerns:

| Mechanism | What Does It Protect? |
| --- | --- |
| **OIDC** | Authentication/identity layer and ID Token per OpenID Connect. |
| **OAuth Access Token** | Resource access permissions. |
| **PKCE** | Binds the authorization code to the client that started the flow, reducing code interception risk. |
| **DPoP** | Binds the Access Token to the client's public key and proves possession on each request. |
| **TLS** | Protects the transport channel and authenticates the server; can also authenticate clients via mTLS. |

These mechanisms can **coexist**. PKCE does not replace DPoP; DPoP does not replace PKCE; a DPoP proof is not an ID Token and does not prove a user logged in.

## 21. Attack Scenarios and Expected Outcomes

| Scenario | Why Must It Be Rejected? |
| --- | --- |
| DPoP-bound token sent with `Authorization: Bearer` | Wrong token usage/scheme; sender constraint must not be downgraded. |
| Missing DPoP header | No proof-of-possession. |
| Proof signed with a key other than `cnf.jkt` | Sender does not possess the key bound to the token. |
| Proof missing `ath` for a resource request | Proof is not bound to the accompanying Access Token. |
| `ath` hashes a different token | Proof was created for a different credential. |
| `htm` differs from HTTP method | Proof is not intended for the current request. |
| `htu` differs from target URI | Proof is not intended for the current resource URI. |
| Proof is too old / too far in the future | Fails freshness policy. |
| `jti` has already been used | Replay. |
| `nonce` required but missing/wrong | Does not satisfy the server's challenge. |
| Header `typ` is not `dpop+jwt` | Invalid DPoP proof profile. |
| `alg=none` or algorithm not in allowlist | Signature is not verified securely. |
| JWK contains private key material | Public proofs must not leak private credentials. |
| Access Token wrong issuer/audience/exp or inactive | Credential is invalid, even if the proof signature is valid. |
| Valid token/proof, but missing scope | Authentication may succeed; authorization returns 403. |

## 22. Layered DPoP Testing

Do not test only a JWT proof with a valid signature. Test the entire chain linking **token, key, request, time, and replay state**.

### 22.1. Unit Tests for the Proof Verifier

| Test | Expected |
| --- | --- |
| ES256 proof with right key | Signature passes. |
| Modify one byte of payload after signing | Signature fails. |
| Wrong `typ` | Rejected. |
| Disallowed algorithm or `none` | Rejected. |
| Invalid JWK / not a valid public key | Rejected. |
| JWK thumbprint differs from token `cnf.jkt` | Rejected. |
| `htm` differs from actual method | Rejected. |
| `htu` differs from canonical URI | Rejected. |
| `iat` too old / too far in the future | Rejected. |
| `jti` already recorded | Rejected as replay. |
| `ath` does not match token | Rejected. |
| Nonce required but missing/wrong | Challenged or rejected per RFC/policy. |
| `ath` absent in token endpoint proof | Do not mechanically apply resource-request rule. |

### 22.2. Integration Tests with Spring Security

Test setup:

1. Generate a test DPoP key pair.
2. Issue or construct an Access Token with `cnf.jkt` matching the test public key.
3. Send a request with `Authorization: DPoP ...` and a proof signed with the test private key.
4. Verify the JWT/introspection token via the real path.
5. Send a valid proof to an endpoint with the required scope.
6. Resend **the exact same proof** a second time to verify replay detection.
7. Mutate key/token/method/URI/ath/nonce to confirm each condition is rejected.
8. Verify there is no Bearer fallback path for DPoP-bound tokens.

### 22.3. Testing Multiple Replicas

If the replay cache uses a distributed store:

~~~text
Request P -> Node A -> jti insert success -> accept
Replay P  -> Node B -> jti already exists -> reject
~~~

If Node B still accepts P, replay defense is only local and fails cluster-wide requirements. Test atomic insert, TTL, store outages, and fail-closed behavior when replay state is unreachable.

### 22.4. Testing Through a Real Proxy

Send requests through the gateway/ingress, not just directly to localhost:

- External scheme/host/port are accurate.
- Spoofed forwarded headers from clients are not trusted.
- Path normalization / URL encoding do not break `htu`.
- Redirects do not send proofs/tokens to disallowed origins.
- Nonce responses and retries preserve proper request binding.

## 23. Observability and Operations

Useful metrics:

- DPoP proof verification successes/failures grouped by reason.
- Token validation failures separated from proof failures.
- Thumbprint binding mismatches.
- Replay detections and nonce challenge counts.
- Proof age distribution.
- Replay cache size/evictions/store errors.
- Clock skew and proxy-related URI discrepancies.
- Rate of clients mistakenly sending Bearer scheme with DPoP-bound tokens.

Never log:

- Verbatim Access Tokens.
- Verbatim compact DPoP proofs.
- Private JWK/key material.
- The Authorization header.
- Unnecessary full user claims.

You can log request correlation IDs, error categories, and non-sensitive metadata. If key-level investigation is needed, consider controlled fingerprints with restricted access and retention.

### 23.1. Replay Store Outage

If `jti` cannot be checked because the replay store is unavailable:

- For endpoints requiring DPoP replay protection, do not silently skip the replay check for availability.
- Reject requests under a fail-closed policy or use an approved fallback with equivalent guarantees.
- Alert promptly because replay store failures impact both security and availability.

### 23.2. Clock Synchronization

Proofs rely on `iat` and nonce lifetimes; clocks across client, gateway, and server can drift. You need to:

- Synchronize clocks across server nodes.
- Configure bounded allowed clock skew.
- Measure proof age and rejection reasons.
- Never widen the window excessively just to mask broken client clocks.

## 24. Common Pitfalls

| Pitfall | Consequence | Right Approach |
| --- | --- | --- |
| Treating a DPoP proof as an Access Token. | Uses proof JWT as a scope-bearing credential. | Token grants permissions; proof demonstrates possession. |
| Sending the private key in the JWK header. | Leaks private credential. | Include only the public JWK. |
| Signing proofs with the AS signing key. | Confuses two trust domains. | Client signs with its own DPoP private key. |
| Reusing one proof for multiple requests. | Replay and broken method/URI binding. | Generate a fresh proof per request. |
| Omitting `ath` on resource requests. | Proof is not bound to the accompanying token. | Hash the Access Token per RFC 9449. |
| Comparing `cnf.jkt` against an unverified public key profile. | Could accept a key not matching the token. | Compute the RFC 7638 thumbprint from the proof JWK. |
| Checking only the proof signature. | Skips htm/htu/iat/jti/ath/nonce. | Enforce full DPoP validation. |
| Checking only `iat` without a replay cache. | Proof can be replayed within the time window. | Atomic `jti` replay detection. |
| Local-only replay cache in a cluster. | Same proof can pass another node. | Shared/consistent replay defense. |
| Using DPoP instead of TLS. | Body/response remain unencrypted. | Keep HTTPS mandatory. |
| Assuming DPoP signs body/query. | Misunderstands `htu`/`ath` scope. | Validate payloads separately; DPoP does not sign the entire message. |
| Trusting `X-Forwarded-Host` from clients. | Bypasses URI binding. | Trusted proxy / canonical URI configuration. |
| Falling back to Bearer on proof errors. | Nullifies sender constraint. | Reject DPoP-bound tokens when proofs are missing/invalid. |
| Caching proofs for reuse. | Replay detection rejects or proofs mismatch requests. | Generate proofs per request. |
| Not handling nonce challenges. | Client/server fail to complete DPoP flow. | Create a new proof with a valid nonce. |
| Thinking non-extractable keys fully stop XSS. | XSS can still invoke signing APIs. | CSP, origin security, and secure client design. |
| Thinking DPoP proves user identity itself. | Confuses client key possession with user authentication. | Separate OIDC/OAuth authentication and authorization. |
| Configuring only `oauth2ResourceServer().jwt()` and assuming DPoP is on. | Access Token is verified, but proofs may be ignored. | Version-appropriate DPoP-aware integration and tests. |

## 25. Implementation Roadmap

1. **Identify client types:** browser, native mobile, desktop, or confidential backend; decide where private keys are created/stored.
2. **Confirm AS supports RFC 9449:** token endpoint accepts DPoP proofs, issues `DPoP` token types and `cnf.jkt` confirmation bindings.
3. **Align algorithm/key policy:** asymmetric algorithm allowlist, JWK thumbprints, and key rotation.
4. **Design token issuance:** proofs for token endpoint, nonce challenges, Access Tokens bound to the right public key.
5. **Design Resource Server validation:** token, `cnf.jkt`, proof signature, htm/htu/iat/jti/ath/nonce.
6. **Choose a replay store:** TTL aligned with proof acceptance window, atomic insert, and consistency across replicas.
7. **Integrate Spring Security per exact version:** do not assume default JWT/opaque Resource Server checks DPoP; place verifier before authorization.
8. **Configure proxy URI trust:** canonical external URI, forwarded headers from trusted proxies, redirects.
9. **Run negative tests:** missing proof, wrong key, wrong ath, replay, nonce, URI/method mismatch, Bearer downgrade.
10. **Protect key lifecycle:** secure storage, recovery, compromise handling, re-issuance, and token revocation.
11. **Measure operations:** proof failures, replay hits, nonce challenges, clock skew, replay store health.
12. **Maintain TLS and domain authorization:** DPoP does not replace confidentiality, scopes, or tenant/owner checks.

**Remember:** The **Access Token** carries access permissions; the **DPoP proof JWT** is signed by the client with its private key to prove key possession for a single HTTP request. The proof contains the public JWK and claims binding the method, URI, timestamp, unique ID, and Access Token hash. The Authorization Server binds the token to the key via **`cnf.jkt`**; the Resource Server must verify the token, proof signature, thumbprint, `htm`/`htu`/`iat`/`jti`/`ath`, and nonce/replay policy before evaluating permissions. DPoP reduces standalone token-theft risk, but **does not replace Access Tokens, TLS, secure key storage, or authorization**.

## References

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449).
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638).
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749).
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705).
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html).
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html).
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html).
