# Testing Tampered, Replayed, Wrong-Key, or Mismatched-Request Proofs

## 1. Why Test Proof-of-Possession?

In an OAuth 2.0 Resource Server, a Bearer access token can be used by any party holding the token string. If the token leaks through logs, browser storage, a proxy, or a downstream service, whoever obtains it can attempt to use it while it remains valid.

**Proof-of-possession (PoP)** adds evidence that the caller possesses a private key corresponding to the key bound to the access token. With **DPoP — Demonstrating Proof of Possession**, the client creates a proof JWT for each HTTP request. The Resource Server verifies the proof signature, checks that the key matches the access token, and verifies that the proof describes the exact current request.

This lesson focuses on testing scenarios such as:

- A proof tampered with after signing.
- A proof signed with a different key than the one bound in the access token.
- An old proof being replayed.
- A proof describing the wrong HTTP method or target URI.
- A proof containing the wrong access-token hash.
- A proof with an invalid issue time, nonce, or key ID.
- A client sending a Bearer token to an endpoint requiring DPoP.
- A reverse proxy altering how the Resource Server observes the scheme/host/path.
- Key rotation causing old tokens and new proofs to no longer share a key pair.

**The testing goal** is to prove the Resource Server accepts only a valid proof for the exact access token and exact HTTP request, while rejecting variants that are tampered with, replayed, or used in the wrong context.

## 2. DPoP Proofs Bind an Access Token to a Key

### 2.1. Participating Components

DPoP has three main components:

1. **Access token:** issued by the Authorization Server. The token is bound to a public key via the `cnf.jkt` confirmation claim.
2. **DPoP proof JWT:** signed by the client with the corresponding private key. The proof contains the public JWK and request metadata.
3. **Resource Server:** verifies the access token, proof signature, key binding, and claims describing the request.

Simplified flow:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>AS: Token request + DPoP proof
    AS->>AS: Verify proof and record key thumbprint
    AS-->>C: DPoP-bound access token (cnf.jkt)
    C->>RS: Authorization: DPoP access_token + DPoP proof
    RS->>RS: Verify access token and cnf.jkt
    RS->>RS: Verify proof signature, htm, htu, ath, iat, jti, nonce
    RS-->>C: Resource response or DPoP error
~~~

At the token endpoint, the DPoP proof proves the client holds the private key while requesting a token. When the access token is issued, the AS binds the token to the corresponding public key. At the Resource Server, a fresh proof is sent on **every request** to prove the client still holds that private key.

### 2.2. How Does DPoP Differ from a Bearer Token?

| Characteristic | Bearer | DPoP-Bound Access Token |
|---|---|---|
| Credential sent to API | `Authorization: Bearer ...` | `Authorization: DPoP ...` |
| Proof of key possession | Not required | Includes DPoP proof JWT |
| Key binding in access token | Not required | `cnf.jkt` holds JWK thumbprint |
| Per-request proof | No | Yes |
| Protection against standalone token theft | Limited | Attacker also needs the matching private key |
| Replay protection | Relies on token lifetime/revocation and other controls | Needs freshness, nonces, and replay policy |
| TLS | Still mandatory | Still mandatory |

DPoP does not encrypt the access token and does not replace TLS. Nor does it determine user identity or resource permissions on its own; those still belong to access-token validation and authorization.

### 2.3. Request Headers

An illustrative request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <DPoP_PROOF_JWT>
~~~

The two values have distinct roles:

- `Authorization` carries the key-bound access token.
- `DPoP` carries the proof JWT for the current request.

Never send the proof JWT in the access token's position. Never assume an arbitrary Bearer token becomes DPoP-bound merely because a request carries a `DPoP` header.

## 3. Structure of a DPoP Proof JWT

### 3.1. JOSE Header

A DPoP proof is an asymmetrically signed JWT. Typical header:

~~~json
{
  "typ": "dpop+jwt",
  "alg": "ES256",
  "jwk": {
    "kty": "EC",
    "crv": "P-256",
    "x": "<PUBLIC-X>",
    "y": "<PUBLIC-Y>"
  }
}
~~~

Points to enforce:

- `typ` must be `dpop+jwt` per the DPoP profile.
- `alg` must be an asymmetric algorithm permitted by the server; reject `none` or any algorithm outside the allowlist.
- `jwk` contains the public key used to verify the proof.
- Never place private JWK members such as `d`, `p`, or `q` in the proof header.
- `jwk` is a client-supplied public key; it is not trusted on its own until its thumbprint matches the access token's confirmation claim.

### 3.2. Payload Claims

A proof for a request to the Orders API may contain:

~~~json
{
  "jti": "proof-8b9c1d",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1794700800,
  "ath": "<BASE64URL-SHA256-OF-ACCESS-TOKEN>",
  "nonce": "<SERVER-PROVIDED-NONCE>"
}
~~~

Meaning:

| Claim | Meaning | Key Test |
|---|---|---|
| `jti` | Unique ID of the proof | Replaying the same proof must be detected |
| `htm` | HTTP method | Must match the actual method |
| `htu` | HTTP target URI, excluding query and fragment per DPoP | Must match the actual URI per normalization rules |
| `iat` | Proof creation timestamp | Reject proofs too old or in the future beyond clock skew |
| `ath` | Hash of the access token sent with the request | Different token or wrong hash must be rejected |
| `nonce` | Server-issued nonce, if required by server | Missing, stale, or wrong nonce must be rejected |

For Resource Server requests carrying an access token, `ath` is a mandatory part of the DPoP proof under RFC 9449. Never hash a decoded token string or JSON claims; the hash is computed over **the actual access token value** sent in the Authorization header.

### 3.3. Access Token Confirmation Claim

A DPoP-bound JWT access token may contain:

~~~json
{
  "iss": "https://id.example.test/realms/shop",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "<JWK-THUMBPRINT>"
  }
}
~~~

`cnf.jkt` is the thumbprint of the public JWK used by the client to sign DPoP proofs. With opaque access tokens, the Resource Server must obtain confirmation information from the introspection response per the AS contract.

**Never validate a proof merely by verifying its signature against the embedded JWK.** An attacker can generate their own key pair and sign proofs with their own key. The Resource Server must also compute the thumbprint of that public JWK and match it exactly against `cnf.jkt` in the verified access token.

## 4. JWK Thumbprint and Key-Binding Verification

### 4.1. The Thumbprint Identifies the Public Key

DPoP uses the RFC 7638 JWK thumbprint. For a public JWK, the thumbprint is computed from the required member set and canonical JSON representation for the key type, followed by SHA-256 and Base64URL encoding.

For EC P-256, the relevant canonical members are:

~~~json
{
  "crv": "P-256",
  "kty": "EC",
  "x": "<PUBLIC-X>",
  "y": "<PUBLIC-Y>"
}
~~~

For RSA, the primary members are `e`, `kty`, and `n`. Do not include private parameters or optional members outside the canonical set in the thumbprint calculation.

Do not concatenate JSON strings arbitrarily and hash them. Member ordering and canonicalization must obey RFC 7638.

### 4.2. Two Key Errors That Must Be Distinguished

**Case A — Invalid proof signature:**

- Proof header contains public key K1.
- Proof is signed with private key K2.
- Signature fails to verify against K1.
- Result: invalid proof signature.

**Case B — Valid signature, but access token bound to a different key:**

- Proof header contains public key K2.
- Proof is validly signed with private key K2.
- Access token has `cnf.jkt` of K1.
- Proof signature is valid, yet thumbprint K2 does not match token binding K1.
- Result: reject due to key binding mismatch.

Both cases need separate fixtures and assertions. Testing only an invalid signature fails to prove the `cnf.jkt` comparison step works.

### 4.3. Key Matrix

| Access Token `cnf.jkt` | Proof Public JWK | Proof Signature | Expected |
|---|---|---|---|
| K1 thumbprint | K1 | Signed by K1 | Proceed to remaining claim checks |
| K1 thumbprint | K1 | Signed by K2 | Reject: signature invalid |
| K1 thumbprint | K2 | Signed by K2 | Reject: key binding mismatch |
| K2 thumbprint | K2 | Signed by K2 | Proceed to remaining claim checks |
| Missing `cnf.jkt` | K1 | Signed by K1 | Reject if endpoint requires DPoP-bound tokens |
| Malformed `cnf.jkt` | K1 | Signed by K1 | Reject token/binding per contract |

A proof is verified with the public key in the proof header only after validating structure and algorithm policy. Signature verification alone is never sufficient to accept a request.

## 5. Layers of Proof Verification at the Resource Server

A clear pipeline can be structured into steps:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Parse DPoP scheme + proof header"]
    B --> C["Validate access token"]
    C --> D{"Token valid and DPoP-bound?"}
    D -->|No| X["Reject token"]
    D -->|Yes| E["Parse proof JOSE header"]
    E --> F["Check typ, alg, public JWK"]
    F --> G["Verify proof signature"]
    G --> H["Compute JWK thumbprint"]
    H --> I{"Thumbprint == cnf.jkt?"}
    I -->|No| Y["Reject key binding"]
    I -->|Yes| J["Validate htm, htu, ath, iat, nonce"]
    J --> K["Atomic replay check for jti"]
    K --> L{"Proof fresh and unused?"}
    L -->|No| Z["Reject replay/invalid proof"]
    L -->|Yes| M["Continue authorization"]
~~~

Exact execution order may vary by implementation, yet all security conditions must be enforced before business handlers run.

### 5.1. Verify the Access Token First

The Resource Server must verify the token per issuer/audience/signature/expiry or introspection contract. For DPoP-bound tokens, check `cnf.jkt` and confirm the right token type.

Never read `cnf.jkt` from an unverified token and treat it as a trust anchor. If the access token is a JWT, the decoder must verify signature and claims first. If opaque, introspection must return active status and confirmation data per contract.

### 5.2. Verify Proof Header and Signature

- Accurate `typ`.
- `alg` in asymmetric algorithm allowlist.
- `jwk` uses a supported key type/curve/size.
- No private key material present.
- Signature verifies against the embedded public JWK.
- Never fetch keys via `jku` or arbitrary URLs sent inside the proof.
- Public JWK thumbprint matches `cnf.jkt`.

### 5.3. Verify Request-Binding Claims

- `htm` equals the actual HTTP method.
- `htu` equals the actual target URI per DPoP URI comparison rules.
- `ath` equals the hash of the sent access token.
- `iat` lies within the freshness window.
- `jti` has not been used yet.
- `nonce` is valid if the server required a nonce.

Only after these steps should the request proceed to URL authorization, method security, and business ACLs.

## 6. Testing Proofs Tampered With After Signing

### 6.1. Altering the Payload While Keeping the Old Signature

A DPoP proof JWT has the compact form:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

If `htm` is changed from `GET` to `DELETE` while keeping the old signature, the signed input changes and signature verification must fail.

Fixture:

~~~text
1. Create a valid proof for GET /api/orders/42.
2. Decode the payload in the test.
3. Change htm to DELETE.
4. Keep the original signature untouched.
5. Send the tampered proof to the verifier.
6. Expected: signature validation failure.
~~~

Do not build a fixture that modifies the payload and re-signs it with the same private key to represent "tampering." A re-signed proof is a new proof with a valid signature; that belongs to claims, binding, and replay tests.

### 6.2. Altering the JOSE Header

Create variants:

- `typ` changed from `dpop+jwt` to `JWT`.
- `alg` changed to `none`.
- `alg` changed to a disallowed algorithm.
- `jwk` swapped for another public key while keeping the original signature.
- `jwk` containing private members.
- Malformed header or missing `jwk`.

Expected result: reject the proof before business authorization. Never let the parser fall back to a generic JWT validator that accepts non-DPoP tokens.

### 6.3. Modifying the Signature

Flip one byte in the signature or sign with a key that does not correspond to the JWK in the header. The verifier must reject it.

It is not necessary for every mutation to return the exact same error string; what matters is that **no mutation is accepted** and error categories are clear enough for diagnosis without leaking credentials.

## 7. Testing Replayed Proofs

### 7.1. Why Does `jti` Matter?

A DPoP proof is created for a specific request. `jti` supplies a unique identifier so the Resource Server can detect previously used proofs.

A basic replay test:

~~~text
Request A:
  token = T
  proof = P (jti = J)
  Expected: accepted

Request B:
  token = T
  proof = P (same compact proof, same jti = J)
  Expected: rejected as replay
~~~

If the second request is accepted, the server may not be storing replay state, may be storing it in the wrong scope, or the cache is not shared across instances.

### 7.2. What Properties Should a Replay Cache Have?

A real replay store needs:

- **Atomic insert-if-absent:** two concurrent requests with the same proof must never both win.
- **Bounded TTL:** entries persist at least as long as the proof can still be accepted, accounting for clock skew.
- **Key namespace:** typically combines thumbprint and `jti` to avoid collisions across clients.
- **Distributed visibility:** multiple Resource Server instances must share replay state if a load balancer can route a replay to another node.
- **Capacity control:** prevent attackers from sending unbounded proof IDs to exhaust memory.
- **Failure policy:** if the replay store is unavailable, never silently skip replay protection when it is a mandatory security control.

Pseudocode:

~~~java
String replayKey = thumbprint + ":" + proofJti;

boolean firstUse = replayStore.putIfAbsent(
    replayKey,
    expiresAt
);

if (!firstUse) {
    throw new InvalidDpopProofException("Proof was already used");
}
~~~

`putIfAbsent` must be atomic at the storage layer. A separate `get` followed by `put` has a race condition: two threads can simultaneously see the key as absent and both accept.

### 7.3. TTL and Clock Skew

Suppose a server accepts proofs whose `iat` is no older than 5 minutes with 30 seconds of clock skew. Replay entries must survive long enough that the proof cannot be accepted again within that window.

Never delete a replay entry immediately once a request finishes. Immediate deletion allows an attacker to resend the compact proof within the same freshness window.

The exact TTL depends on freshness policy, distributed clocks, and storage behavior. Record this value in configuration/test manifests rather than hardcoding an example number as a universal rule.

### 7.4. Concurrent Replay Across Multiple Nodes

Concurrency test:

~~~text
Node A receives proof P
Node B receives proof P at almost the same time

Expected:
  exactly one request may pass replay check
  the other request must be rejected
~~~

Use a shared replay store or an abstraction with equivalent semantics. A per-JVM local in-memory map is insufficient if the system runs multiple instances.

### 7.5. Nonces and Replay Caches Complement Each Other

The server can require a nonce via the `DPoP-Nonce` response header. The client includes the nonce in its next proof. Nonces make proofs harder to pre-generate or reuse outside the server context.

Nonces should not be treated as a total replacement for replay detection if policy requires blocking repeated submission of the exact same proof. Test both nonce validation and `jti` replay behavior.

## 8. Testing Proofs with the Wrong HTTP Method (`htm`)

### 8.1. Method Must Match the Actual Request

Proof:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42"
}
~~~

Actual request:

~~~http
DELETE /api/orders/42 HTTP/1.1
~~~

Expected: reject the proof due to method mismatch.

### 8.2. Test Matrix

| Proof `htm` | HTTP Request Method | Expected |
|---|---|---|
| GET | GET | Passes method check |
| GET | POST | Reject |
| POST | DELETE | Reject |
| PATCH | PATCH | Passes method check |
| get | GET | Reject if not matching canonical method representation |
| Missing | GET | Reject |
| Wrong type (number/array) | GET | Reject |

Compare according to DPoP and HTTP method representation rules; never arbitrarily lowercase/uppercase to force a broken proof to pass. Clients should set `htm` to the actual method, typically an uppercase token.

### 8.3. Do Not Test Only via Controller Methods

Proof validation must run before controllers execute. Integration tests must send real HTTP requests through the security chain and verify the handler is never invoked when `htm` is wrong. Unit testing a string-comparison helper alone does not prove the filter is ordered properly.

## 9. Testing Proofs with the Wrong Target URI (`htu`)

### 9.1. DPoP `htu` Is Not an Arbitrary URL

`htu` describes the request's target URI. Under DPoP, this URI excludes query and fragment. The server must compare it against the request's target URI using appropriate URI comparison rules, including scheme, authority, path, and normalization handling.

Example proof:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42"
}
~~~

Requests to test:

- Different host.
- Different scheme (HTTP instead of HTTPS).
- Different port.
- Different path.
- Different path encoding.
- Path prefix added/stripped by reverse proxy.
- Proof URI uses internal host while client called external host.
- Different query string while standard `htu` omits query.
- Fragment appearing inside proof.

### 9.2. Query Strings Do Not Belong in `htu`

Example:

~~~text
Actual request:
https://api.example.test/api/orders/42?view=compact

DPoP htu:
https://api.example.test/api/orders/42
~~~

Do not reject merely because the query string differs if the implementation compares strictly per DPoP URI rules. Conversely, never ignore differing paths or hosts by dismissing them as proxy details.

### 9.3. Reverse Proxies and Forwarded Headers

In production, clients may call:

~~~text
https://api.example.test/api/orders/42
~~~

yet the backend behind the proxy receives the connection:

~~~text
http://orders-service:8080/api/orders/42
~~~

If the Resource Server builds `htu` from the internal scheme/host, valid client-created proofs may be rejected. More dangerously, if the server trusts arbitrary client-sent `Forwarded` or `X-Forwarded-Host` headers, an attacker can manipulate URI comparison.

You need to:

- Trust forwarded headers only from configured trusted proxies.
- Have the proxy strip client-sent forwarded headers before adding its own trusted headers.
- Reconstruct external scheme/host/port/path after proxy rewrites.
- Test context paths and path prefixes accurately.
- Never leave a public access path to the backend that bypasses the proxy trust boundary.
- Never normalize URIs more permissively than the specification just to let invalid proofs pass.

Integration tests should run with the same proxy configuration used in production or faithfully simulate trusted forwarded headers.

## 10. Testing `ath` — The Proof Must Bind to the Exact Access Token

### 10.1. Computing the Access-Token Hash

`ath` is computed as:

~~~text
BASE64URL(SHA-256(ASCII(access_token)))
~~~

The hash applies to **the actual access token value** sent with the request, without the `DPoP ` prefix and without extra whitespace.

Pseudocode example:

~~~java
byte[] digest = MessageDigest.getInstance("SHA-256")
    .digest(accessToken.getBytes(StandardCharsets.US_ASCII));

String ath = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString(digest);
~~~

OAuth access tokens are ASCII strings per contract. Never use arbitrary UTF-8 if the implementation contract specifies ASCII representation; never hash a decoded JWT payload string.

### 10.2. Testing Mismatches

| Access Token in Authorization | `ath` in Proof | Expected |
|---|---|---|
| Token T1 | Hash(T1) | Passes `ath` check |
| Token T1 | Hash(T2) | Reject |
| Token T2 | Hash(T1) | Reject |
| Token T1 | Missing | Reject at Resource Server |
| Token T1 | Hash altered by 1 character | Reject |
| Token T1 | Invalid Base64URL hash | Reject |

This is an essential test: a validly signed proof with the right key must still be rejected if it is bound to a different access token.

### 10.3. Do Not Reuse Proofs for a Refreshed Token

If the client refreshes the access token, the old proof carries the `ath` of the old token. The client must generate a new proof with the hash of the new access token, along with a fresh `jti` and matching request claims.

## 11. Testing Freshness of `iat` and Nonces

### 11.1. Stale or Future `iat`

Servers typically bound the time window in which a proof is accepted. Cases:

- `iat` too old.
- `iat` in the future beyond clock skew.
- Missing `iat`.
- Wrong data type for `iat`.
- Server clock skewed.
- Proof right on the boundary of the freshness window.

Use a fixed clock in tests so expected results are deterministic. Never use `Thread.sleep` to wait for a proof to expire.

### 11.2. Nonce Challenge Flow

The server may return a response requiring a nonce:

~~~http
HTTP/1.1 401 Unauthorized
DPoP-Nonce: <NEW-NONCE>
WWW-Authenticate: DPoP error="use_dpop_nonce"
~~~

The client must create a **new proof** containing the server-required nonce, never patch a previously signed proof and reuse the old signature.

Tests:

| Scenario | Expected |
|---|---|
| Server does not require nonce | Follows active nonce policy |
| Server requires nonce, proof omits nonce | Challenge `use_dpop_nonce` |
| Proof contains latest nonce | Passes nonce check |
| Proof contains stale nonce | Reject/challenge per policy |
| Nonce from another server | Reject if nonces are server-scoped |
| Client receives challenge and resends exact old proof | Reject; new proof must have fresh `jti`/`iat` and nonce |
| Nonce header stripped by proxy | Integration test detects client cannot complete flow |

Nonces should have adequate entropy, be tied to the right server context, and contain no sensitive info. Test nonce rotation/expiry against real policy.

## 12. Testing Wrong Keys and Key Rotation

### 12.1. Wrong Proof Key Compared to `cnf.jkt`

This is a core test:

~~~text
Access token:
  cnf.jkt = thumbprint(K1)

DPoP proof:
  jwk = public(K2)
  signature = valid under private(K2)

Expected:
  signature check passes
  key-binding check fails
  request rejected
~~~

Do not write tests that use only a malformed `cnf.jkt`; include the case with two valid yet non-matching keys to prove the binding comparison actually works.

### 12.2. Client-Side Key Rotation

Suppose the client uses K1 and holds token T1 bound to K1. When the client rotates to K2:

- T1 + proof K1: can remain valid within T1's lifetime and policy.
- T1 + proof K2: must be rejected because T1's `cnf.jkt` is still K1.
- New access token T2 bound to K2 + proof K2: valid.
- T2 + proof K1: must be rejected.

Never mutate `cnf.jkt` on an old token at the Resource Server to "support rotation." Binding is a property of the token issued by the AS. The client must obtain a new token bound to the new key via the appropriate flow.

### 12.3. Testing Old and New Key Pairs

| Access Token | Proof Key | Expected |
|---|---|---|
| T1 bound to K1 | K1 | Accept if token/proof are unexpired |
| T1 bound to K1 | K2 | Reject |
| T2 bound to K2 | K2 | Accept |
| T2 bound to K2 | K1 | Reject |
| T1 revoked/expired | K1 | Reject token |
| T1 active, yet K1 deleted by client | K2 | Reject; client needs a new token |

### 12.4. Distinguish Issuer Rotation from DPoP Client Key Rotation

There are two distinct key types:

- **Issuer signing key:** used by the AS to sign JWT access tokens; the Resource Server fetches public keys from JWKS.
- **DPoP client key:** private key used by the client to sign proofs; the access token contains `cnf.jkt` of the client's public key.

Rotating the issuer signing key does not automatically change the DPoP client key. Rotating the DPoP client key does not change the issuer JWKS. Test suites must keep these two axes separate.

## 13. Testing Downgrades from DPoP to Bearer

An endpoint requiring DPoP-bound access tokens must not accept those tokens via the Bearer scheme as if they were ordinary bearer tokens.

Cases:

| Request | Token | Expected |
|---|---|---|
| `Authorization: DPoP T` + valid proof | T with `cnf.jkt` | May accept |
| `Authorization: DPoP T`, missing proof | DPoP-bound | Reject |
| `Authorization: Bearer T` | Same DPoP-bound T | Reject if endpoint requires DPoP |
| `Authorization: DPoP T` + different proof key | T bound to K1, proof K2 | Reject |
| `Authorization: Bearer B` | Separate Bearer token permitted by endpoint | Accept only if allowed by contract |
| Same request sends both Bearer and DPoP credentials | Conflicting credentials | Reject/handle per explicit policy |

Never downgrade a DPoP-bound token to Bearer simply because the proof parser errors, the `DPoP` header is missing, or the nonce flow fails. If an API genuinely supports both Bearer and DPoP, clearly define token/endpoint types and test each branch independently.

## 14. Distinguishing Proof Errors from Access Token Errors

A Resource Server should respond clearly enough for clients without leaking sensitive info.

| Scenario | Error Layer | Typical Result |
|---|---|---|
| Access token invalid/expired | Token authentication | 401, `invalid_token` |
| Proof signature invalid | DPoP proof validation | 401, `invalid_dpop_proof` |
| Wrong `htm`/`htu`/`ath` | DPoP proof validation | 401, `invalid_dpop_proof` |
| Proof replay | DPoP replay protection | Reject proof, typically `invalid_dpop_proof` |
| `cnf.jkt` mismatches proof key | Token/proof binding | Reject; classify per DPoP/token error contract |
| Server requires fresh nonce | Nonce validation | 401, `use_dpop_nonce` and `DPoP-Nonce` |
| Valid token, valid proof, missing scope | Authorization | 403, possibly `insufficient_scope` |
| Replay store/JWKS dependency error | Infrastructure | Fail closed, record dependency failure |
| Endpoint accepts only DPoP, request sends Bearer | Authentication scheme mismatch | Reject per endpoint contract |

Never turn infrastructure errors into "invalid proof" if availability must be tracked. Never return 200 with a JSON body describing a 401/403 error. For DPoP challenges, preserve required response headers, especially `DPoP-Nonce` when asking the client to submit a fresh proof.

## 15. Designing Reproducible Test Fixtures

### 15.1. What Should a Fixture Declare?

~~~yaml
fixtureSet:
  id: orders-dpop-proof
  version: 2
  issuer: https://id.example.test/realms/orders
  audience: orders-api
  proofProfile: rfc9449
  clock: 2026-11-15T00:00:00Z

keys:
  clientKey:
    kid: dpop-client-k1
    algorithm: ES256
  wrongKey:
    kid: dpop-client-k2
    algorithm: ES256

scenarios:
  - id: valid-get
    accessTokenBinding: clientKey
    proofKey: clientKey
    method: GET
    uri: https://api.example.test/api/orders/42
    expected: ACCEPT

  - id: wrong-proof-key
    accessTokenBinding: clientKey
    proofKey: wrongKey
    expected: REJECT_BINDING

  - id: replay
    proofKey: clientKey
    reuseSameJti: true
    expectedSecondRequest: REJECT_REPLAY
~~~

This is a project-defined example schema. Never store production access tokens or production private keys in manifests. Key pairs and proofs can be generated at test runtime while storing only scenario metadata.

### 15.2. Separating Expected Results

~~~text
tokenValidation: ACCEPT | REJECT
proofSignature: ACCEPT | REJECT
keyBinding: MATCH | MISMATCH
requestBinding: MATCH | MISMATCH
freshness: FRESH | STALE | FUTURE
nonce: VALID | MISSING | INVALID | NOT_REQUIRED
replay: FIRST_USE | REPLAY
authorization: ALLOW | DENY
httpExpected: 200 | 400 | 401 | 403
errorExpected: none | invalid_token | invalid_dpop_proof | use_dpop_nonce
~~~

A test can verify that the token is valid and the proof signature is valid, yet key binding mismatches. That result is far more useful than a fixture stating only a generic `expected: REJECT`.

### 15.3. Use Test Keys, Never Real Credentials

- Generate EC P-256 or another implementation-permitted key type via a test-only key factory.
- Public JWK goes into the proof.
- Private key stays inside the test process.
- Access token fixture sets `cnf.jkt` computed from the public JWK.
- Use a fixed clock and deterministic IDs when reproducibility is needed.
- Never log compact proofs or access tokens in CI.

## 16. Test Factories and Helpers for DPoP Proofs

A DPoP proof factory should take the request context and access token instead of hardcoding claims.

Pseudocode:

~~~java
DpopProof createProof(
        PrivateKey privateKey,
        PublicJwk publicJwk,
        String accessToken,
        String httpMethod,
        URI targetUri,
        Instant issuedAt,
        String jti,
        String nonce) {

    String ath = base64UrlSha256(accessToken);

    return signDpopJwt(
        header("dpop+jwt", allowedAlgorithm, publicJwk),
        claims(
            "jti", jti,
            "htm", httpMethod,
            "htu", dpopTargetUri(targetUri),
            "iat", issuedAt,
            "ath", ath,
            "nonce", nonce
        ),
        privateKey
    );
}
~~~

This is pseudocode describing responsibilities, not a Spring Security API. `signDpopJwt` and `dpopTargetUri` must follow JOSE/RFC 9449 rules.

### 16.1. Helpers Should Easily Construct Deliberately Invalid Proofs

Do not provide only a `validProof()` method. The test suite should be able to build:

- `tamperPayloadAfterSigning`.
- `signWithDifferentKey`.
- `useWrongHtm`.
- `useWrongHtu`.
- `useWrongAth`.
- `useOldIat`.
- `useFutureIat`.
- `omitNonce`.
- `useWrongNonce`.
- `reuseJti`.
- `includePrivateJwkMember`.
- `useUnsupportedAlgorithm`.

Helpers can be split into a valid factory and mutation builders. Mutations should have clear names so readers know exactly what the test proves.

### 16.2. Do Not Accidentally Make a Fixture Invalid in Multiple Layers

For example, a "wrong `htm`" test must have:

- Valid signature.
- Proof key matching `cnf.jkt`.
- Accurate `htu`.
- Accurate `ath`.
- Valid `iat`.
- Unused `jti`.
- Valid nonce if required.

Only `htm` is wrong. If the fixture also has a broken signature, the test passes because the decoder rejects early and never exercises method-binding verification.

This is a key rule of negative testing: **each scenario mutates one primary condition**, keeping all other conditions valid.

## 17. Testing with Spring Security and the Web Stack

### 17.1. Keep the Proof Validator Out of Controllers

DPoP proof validation belongs to the security/authentication boundary. Integrate it into the Resource Server authentication pipeline or a security component invoked before authorization/handlers.

Do not scatter proof verification logic across controllers. If one endpoint forgets to call a helper, the API develops a bypass path.

### 17.2. Do Not Assume All Spring Security Versions Share the Same DPoP API

Standard Spring Security OAuth2 Resource Server abstractions handle JWT/opaque access tokens. DPoP proof validation and replay protection must be implemented via **the DPoP mechanism supported in your exact version** or an appropriate application extension point.

Before choosing an implementation, check the version-matched Spring Security reference/API. Do not invent a class name like `DpopAuthenticationFilter` and assume the framework provides it. If you must build a custom integration, establish a cohesive design to:

- Resolve the access token and token type.
- Verify the token and `cnf.jkt`.
- Parse/verify the proof JWT.
- Validate request binding/freshness/nonce.
- Run an atomic replay check.
- Map errors to the right HTTP challenges.
- Order the filter properly before authorization and handlers.

### 17.3. Servlet and WebFlux Differ

| Servlet | WebFlux |
|---|---|
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| Servlet `Filter` | Reactive `WebFilter` |
| `HttpServletRequest` | `ServerWebExchange` |
| Common `OncePerRequestFilter` pattern | Reactive filter composition |
| Blocking replay store may need thread management | Replay store must use reactive I/O or a boundary that never blocks the event loop |

Do not copy a Servlet filter into a WebFlux app. In WebFlux, replay stores and proof validators must preserve reactive/non-blocking behavior; never call `block()` inside the request pipeline.

### 17.4. Processing Placement

General model:

~~~text
HTTP request
  -> Resolve access token
  -> Validate access token / cnf.jkt
  -> Validate DPoP proof
  -> Check replay state
  -> Create authenticated principal
  -> URL authorization / method authorization
  -> Controller
~~~

A request with an invalid proof must never create an authenticated principal and wait for a controller to decide. Test that controllers/services are never invoked when a proof is rejected.

## 18. Testing with `MockMvc` or `WebTestClient`

### 18.1. Unit Tests for the Proof Validator

Unit tests should invoke the validator with:

- A verified access token or test token principal.
- Confirmation thumbprint.
- Compact proof.
- HTTP method/URI context.
- `Clock`.
- Nonce policy.
- Replay store.

These tests run quickly and pinpoint exactly which layer rejects.

### 18.2. Integration Tests Through the Security Chain

For Servlet, use `MockMvc`; for WebFlux, use `WebTestClient`. Send real requests through the security chain with `Authorization: DPoP ...` and a real `DPoP` header signed by a test private key.

Do not rely solely on helpers like `jwt()` or mock `Authentication` and conclude DPoP is tested. Those helpers can bypass the proof parser, signature verification, and replay store.

### 18.3. Integration Matrix

| Test | Token | Proof | Expected |
|---|---|---|---|
| Valid request | DPoP-bound | Right key, `htm`, `htu`, `ath` | Handler invoked |
| Missing proof | DPoP-bound | No `DPoP` header | Reject |
| Tampered payload | DPoP-bound | Invalid signature | Reject |
| Wrong key | `cnf.jkt`=K1 | Proof signed by K2, JWK K2 | Reject binding |
| Wrong method | DPoP-bound | `htm` differs from request | Reject |
| Wrong URI | DPoP-bound | `htu` differs from target | Reject |
| Wrong token hash | DPoP-bound | `ath` of another token | Reject |
| Replay | DPoP-bound | Resend same proof | Second request rejected |
| Stale proof | DPoP-bound | `iat` too old | Reject |
| Future proof | DPoP-bound | `iat` exceeds skew | Reject |
| Nonce required | DPoP-bound | Missing nonce | Challenge |
| Nonce retry | DPoP-bound | New proof with valid nonce | Passes nonce check |
| Bearer downgrade | DPoP-bound | Sent with Bearer scheme | Reject per contract |
| Insufficient scope | DPoP-bound | Valid proof, missing scope | 403 |
| Wrong tenant | DPoP-bound | Valid proof, tenant ACL fails | Deny domain authorization |

### 18.4. Checking Side Effects

For all proof-invalid cases, also assert:

- Controllers/handlers are not invoked.
- Business services perform no writes.
- The replay store records exactly one use when a proof is valid.
- No access tokens or private keys appear in logs.
- Responses do not leak raw proofs/payloads.
- HTTP status/challenges match expectations.

## 19. Distributed Replay Protection and Resilience

### 19.1. An In-Memory Cache Is Insufficient for Clusters

Suppose a load balancer distributes traffic:

~~~text
Request 1 -> Node A -> local cache empty -> accept
Replay    -> Node B -> local cache empty -> accept
~~~

Both nodes can accept the exact same proof. If the system requires cluster-wide replay prevention, use a shared store or a distributed mechanism with atomic uniqueness semantics.

### 19.2. Testing Race Conditions

~~~text
submit(P) concurrently to node-A and node-B

assert acceptedCount == 1
assert rejectedReplayCount == 1
~~~

Do not test only sequentially against a single instance. A local synchronized map does not prove distributed behavior.

### 19.3. Replay Store Unavailable

If replay protection is a mandatory requirement, when the store fails:

- Never silently bypass the replay check.
- Never accept a request simply because the proof signature is valid.
- Return an error matching the defined availability/error policy.
- Emit a dedicated metric for replay store failures.
- Enforce timeouts and capacity controls.

Test timeouts, connection refused, store errors, and recovery. Never turn a Redis/database outage into `invalid_dpop_proof` when the true cause is an unavailable dependency.

### 19.4. TTL and Storage Abuse

An attacker can send floods of proofs with random `jti` values. The replay cache needs:

- Finite TTL aligned with the freshness window.
- Size/rate limits per client and network policy.
- Key length / claim length limits.
- Rejection of malformed IDs.
- Monitoring of cache size/evictions.
- No infinite TTLs.

If eviction drops an entry before the proof leaves the freshness window, a replay may be accepted again. Test eviction behavior and sizing assumptions.

## 20. Testing URIs and Proxies in Realistic Environments

DPoP `htu` is where integrations frequently break when applications sit behind a reverse proxy or API gateway.

### 20.1. The External URI Must Be Determined Consistently

A proxy test matrix might include:

| Client Sees | Backend Sees | Expected `htu` Comparison |
|---|---|---|
| Public HTTPS host | Internal HTTP host | Use external URI derived from trusted proxy config |
| HTTPS + port 443 | HTTPS without explicit port | Follow URI normalization rules |
| Public prefix `/gateway/orders` | Backend path `/orders` | Match external target URI signed by client |
| Spoofed `Host` header from client | Proxy stripped/replaced it | Never use spoofed value |
| `Forwarded` proto from untrusted client | Untrusted | Reject or ignore that header |
| Different query | Same target path | Query is excluded from `htu` |
| Different path | Same host | Reject |

### 20.2. Trust Forwarded Headers Conditionally

Never enable a mode that trusts every forwarded header from every source. Accept headers only from trusted ingresses/proxies and ensure the ingress strips client-sent headers before adding its own values.

Test through the real proxy configuration or an equivalent integration harness. Testing only directly against an embedded server misses production bugs caused by path rewriting.

### 20.3. Canonicalization Must Be Consistent

Client and Resource Server must agree on the target URI. Do not decode/re-encode paths repeatedly or convert `%2F` to `/` in a way that merges two distinct URIs into one. Use standard-compliant URI parsing/comparison and test encoded paths, default ports, schemes, hosts, and context paths.

## 21. Observability and Error Classification

Metrics/logs should distinguish:

| Category | Example |
|---|---|
| `token_invalid` | Access token signature/issuer/audience/expiry error |
| `proof_malformed` | Malformed compact JWT/header/claim |
| `proof_signature_invalid` | Signature fails verification |
| `proof_key_mismatch` | JWK thumbprint mismatches `cnf.jkt` |
| `proof_method_mismatch` | Wrong `htm` |
| `proof_uri_mismatch` | Wrong `htu` |
| `proof_ath_mismatch` | Wrong token hash |
| `proof_stale` | `iat` too old |
| `proof_nonce_invalid` | Missing/wrong/stale nonce |
| `proof_replay` | `jti` already used |
| `replay_store_unavailable` | Replay backend failure |
| `authorization_denied` | Missing scope/role/ACL |

Safe log example:

~~~text
event=dpop_validation_failed
category=proof_key_mismatch
issuer_alias=orders-sandbox
request_id=req-1024
client_key_thumbprint_prefix=8b31...
~~~

Never log compact access tokens, compact proof JWTs, private JWKs, or raw nonces if nonces are treated as short-lived secrets. Never put full `jti` or subjects into unbounded metric labels; choose appropriate redaction/aggregation.

## 22. Rollout and Testing Workflow for Key-Bound Tokens

When rolling out DPoP or changing policies:

1. Verify whether the issuer/token profile supports DPoP and how the AS emits `cnf.jkt`.
2. Define permitted client key algorithms and public JWK types.
3. Implement proof validation, request binding, nonces, and the replay store.
4. Run unit tests with valid/invalid fixtures.
5. Run integration tests through the security chain and reverse proxy.
6. Verify client retry behavior: every request/retry generates a fresh proof.
7. Test client key rotation with old and new tokens.
8. Deploy to sandbox/canary and observe error categories.
9. Transition endpoints to require DPoP per published policy.
10. Revoke or expire legacy tokens/keys per migration plan.

Do not enable DPoP enforcement on the Resource Server before both the AS and clients support the token binding/proof contract. Also do not accept DPoP-bound tokens over Bearer during transition if doing so defeats the sender-constraint goal.

## 23. Testing Checklist

- [ ] Access token is verified before trusting `cnf.jkt`.
- [ ] Token has an appropriate confirmation thumbprint.
- [ ] Proof header `typ` equals `dpop+jwt`.
- [ ] Only allowlisted asymmetric algorithms are accepted.
- [ ] JWK contains only public key members.
- [ ] Proof signature is verified.
- [ ] JWK thumbprint is computed accurately per RFC 7638.
- [ ] Wrong key signature and key-binding mismatch have separate tests.
- [ ] `htm` must match the HTTP method.
- [ ] `htu` must match the target URI per DPoP rules.
- [ ] Query/fragment handling follows `htu` rules.
- [ ] `ath` is computed from the actual access token.
- [ ] `iat` has freshness window and clock skew tests.
- [ ] `jti` replay is rejected.
- [ ] Replay checks are atomic and work across multiple nodes.
- [ ] Nonce challenges, retries, expiry, and stale nonces are tested.
- [ ] DPoP-bound tokens cannot downgrade to Bearer.
- [ ] Client retries generate fresh proofs with new `jti`s.
- [ ] Old/new key rotation is tested independently of issuer signing key rotation.
- [ ] Reverse proxy/forwarded headers are trusted properly and tested through ingress.
- [ ] Invalid proofs never invoke controllers or cause business side effects.
- [ ] Replay store outages do not disable replay protection.
- [ ] Error responses distinguish token, proof, nonce, and authorization failures.
- [ ] Logs contain no access tokens, proof JWTs, or private keys.

## 24. Summary

A DPoP proof is not merely a signed JWT. It is **evidence for a specific request**, signed with the private key bound to the access token. Therefore, the Resource Server must verify all of the following together:

1. **Access token:** issuer, audience, signature/active state, expiration, and `cnf.jkt`.
2. **Proof signature:** header type, algorithm, public JWK, and signature.
3. **Key binding:** JWK thumbprint matches `cnf.jkt`.
4. **Request binding:** `htm`, `htu`, and `ath` match the request/token.
5. **Freshness/replay:** `iat`, `jti`, and `nonce` per policy.
6. **Authorization:** scopes, tenant, owner, and ACLs after authentication completes.

The most important tests isolate each condition: tampered proof with the old signature; proof signed with another key; validly signed proof with the wrong `cnf.jkt`; the same proof sent twice; wrong method/URI/token hash; missing nonce; proxied requests; and DPoP-bound tokens sent with the Bearer scheme.

When these tests run deterministically in CI and are verified through the real security chain, the system catches bugs in proof validation, replay handling, key rotation, and request binding before they impact production data.

### References

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security Reference — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
