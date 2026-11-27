# The DPoP Authorization Scheme and the Header Containing the DPoP Proof

**Demonstrating Proof of Possession (DPoP)** is an application-layer OAuth 2.0 mechanism that binds an access token to a key pair owned by the client. When calling an API, the client does not send only the access token; it also signs a fresh **DPoP proof** for the request using the corresponding private key. The Resource Server verifies the proof, confirms the proof was signed with the exact key bound to the token, and only then evaluates access permissions.

The most common source of confusion is that DPoP uses **two separate HTTP components**:

- The `Authorization` header carries the **`DPoP`** scheme and the key-bound access token.
- The **`DPoP`** header carries a proof JWT signed for the current HTTP request itself.

Example request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP <DPoP_BOUND_ACCESS_TOKEN>
DPoP: <SIGNED_DPOP_PROOF_JWT>
~~~

The access token and the proof JWT are not the same token. The access token carries the granted permissions; the proof is short-lived evidence showing that the client holds the private key bound to the access token and is generating the proof for this method/URI.

This lesson is part of the **Proof-of-Possession Tokens** chapter of the **Spring Security OAuth 2.0 OIDC Resource Server** module. It covers RFC 9449, DPoP proof structure, how the Authorization Server issues key-bound tokens, how clients construct requests, and how the Resource Server verifies proofs, prevents replay, and integrates/tests within the Spring ecosystem.

> DPoP does not replace TLS, does not encrypt access tokens, and does not by itself solve XSS or private-key theft. It reduces the ability to reuse a stolen access token **without the corresponding private key**. All example URLs, tokens, keys, and client IDs below are illustrative dummy data.

## 1. Why Do Bearer Tokens Need Proof of Possession?

With a traditional Bearer access token, whoever holds the token can usually present it to access the API:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN>
~~~

The Resource Server checks token validity and permissions. However, if the token leaks in logs, browser storage, crash dumps, proxies, or is stolen by malware, an attacker can replay the token from another machine for as long as it remains valid. With Bearer, possession of the token string is the primary condition for using it.

DPoP adds **proof of private key possession**:

~~~text
Client creates key pair:
    public key  (can be shared)
    private key (must be kept secret)

Authorization Server:
    binds access token to public key thumbprint

Client calls Resource Server:
    sends access token + proof JWT signed with private key

Resource Server:
    verifies access token
    verifies proof signature and claims
    compares proof key thumbprint with token binding
    checks for replay
~~~

If an attacker obtains only the access token without the private key, they cannot generate a valid new proof for their own request. That is the core benefit of a **sender-constrained access token**.

### 1.1. Bearer and DPoP Differ in the Request

| Property | Bearer token | DPoP-bound access token |
|---|---|---|
| Authorization scheme | `Bearer` | `DPoP` |
| Credential in `Authorization` | Access token | Access token bound to a key |
| Dedicated proof header | Not required | `DPoP: <proof JWT>` |
| Per-request proof of key possession | No | Yes |
| Replayability with leaked token alone | Higher | Restricted if private key is safe |
| TLS/HTTPS | Practically mandatory for security | Still required |

Do not send a DPoP-bound access token with `Authorization: Bearer` if the server issued/defined it as token type DPoP. The scheme is part of how the client presents the credential and how the Resource Server processes the token.

### 1.2. DPoP Is an Application-Layer Sender Constraint

DPoP is designed to operate over HTTP at the application layer, without requiring TLS certificate binding like mutual TLS. Each proof signs selected properties of the request and can bind to the access token via `ath`. The Resource Server verifies that the proof was signed by the public key linked to the token.

DPoP does not mean:

- The access token is encrypted with the client's public key.
- Every request can reuse the same proof JWT.
- The client sends its private key in a header.
- The Resource Server only needs to check the `DPoP` header without validating the access token.
- HTTPS can be dropped because the request is signed.

### 1.3. Two Goals to Distinguish

**Token binding** answers: "Which public key is this access token bound to?"

**Proof validation** answers: "Was the current request signed with the corresponding private key, for the right method/URI/token, within the accepted time window, and not replayed?"

Only by satisfying both do you establish proper proof of possession.

## 2. Components and Terminology of DPoP

| Term | Meaning |
|---|---|
| DPoP key pair | Public/private key pair generated and managed by the OAuth client |
| DPoP proof | Short-lived JWT signed with the private key to prove possession |
| DPoP HTTP header | Header carrying the compact-serialized DPoP proof JWT |
| DPoP authorization scheme | The `DPoP` scheme in the `Authorization` header |
| DPoP-bound access token | Access token bound to a public key thumbprint |
| `jkt` | JWK thumbprint of the public key bound to the token |
| `cnf` | Confirmation claim in the token, which can contain `jkt` |
| `ath` | Hash of the access token to which the proof is bound |
| `jti` | Unique identifier of the proof JWT |
| `nonce` | Server-issued value so the next proof proves the client received a recent challenge |

### 2.1. Who Creates the Proof and Who Verifies It?

~~~text
OAuth Client
  ├─ generates private/public key
  ├─ signs DPoP proof with private key
  └─ sends public JWK in proof header

Authorization Server
  ├─ verifies proof at token endpoint
  ├─ computes public key thumbprint (jkt)
  └─ issues token with confirmation binding

Resource Server
  ├─ verifies access token
  ├─ reads token confirmation (cnf.jkt)
  ├─ verifies proof JWT
  ├─ compares proof public key thumbprint with cnf.jkt
  └─ checks method/URI/ath/iat/jti/nonce
~~~

Depending on token format and architecture, the Resource Server may read `cnf.jkt` from a JWT access token or receive binding metadata from a trusted introspection response. **Never accept binding data self-declared by the client**.

### 2.2. Where Can a Key Pair Be Stored?

The client must protect the private key:

- An SPA can use the Web Crypto API and store the key within an appropriate browser scope; protection level depends on the browser, origin, and XSS exposure.
- Native/mobile clients can use the OS keystore or secure enclave when available.
- A BFF/confidential client can manage keys server-side in a keystore/HSM or secret/key service.
- Key rotation must be coordinated with new token issuance, because old access tokens remain bound to the old thumbprint.

Never include the private key in the `DPoP` header, JSON payload, source control, or logs. The public JWK is sent in the proof header; **private parameters must be absent**.

## 3. Two HTTP Headers That Must Not Be Confused

DPoP uses both the `Authorization` header and the `DPoP` header simultaneously in a request to the Resource Server.

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP eyJhbGciOiJFUzI1NiIs...
DPoP: eyJ0eXAiOiJkcG9wK2p3dCIs...
Accept: application/json
~~~

| Header | Value | Role |
|---|---|---|
| `Authorization` | `DPoP <access-token>` | Presents the DPoP-bound access token |
| `DPoP` | `<compact-proof-jwt>` | Proves possession for the HTTP request |

### 3.1. `Authorization: DPoP` Does Not Contain the Proof

The following is **scheme + access token**:

~~~http
Authorization: DPoP <ACCESS_TOKEN>
~~~

The following is **the proof JWT**:

~~~http
DPoP: <SIGNED_DPOP_PROOF_JWT>
~~~

If you put the proof JWT into `Authorization` instead of the access token, the Resource Server has no token credential to check scopes/audience. If you put the access token into the `DPoP` header, the server receives no valid proof.

### 3.2. Bearer and DPoP Requests Are Not Arbitrarily Interchangeable

~~~http
# Bearer access token
Authorization: Bearer <ACCESS_TOKEN>

# DPoP-bound access token
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <PROOF_JWT>
~~~

An API may support both Bearer and DPoP during migration, but it needs a clear policy on token types and how each scheme is validated. Do not silently treat a DPoP-bound token as a Bearer token if the goal is to maintain sender constraints.

### 3.3. A DPoP Proof Is a JWT, Not an Access Token

A DPoP proof is an **asymmetrically signed JWT** with a JOSE header and claims defined by RFC 9449. The proof is short-lived, bound to a single request, can be bound to an access token via `ath`, and is checked for replay.

The proof does not represent user permissions. It carries no scopes to grant authorization. After verifying the proof, the Resource Server must still verify the access token, audience, issuer, expiration, and authorization as usual.

## 4. Structure of a DPoP Proof JWT

A DPoP proof is a compact JWT with three parts:

~~~text
BASE64URL(protected header)
.
BASE64URL(payload claims)
.
BASE64URL(signature)
~~~

Example JOSE header:

~~~json
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
~~~

Example payload for an API request:

~~~json
{
  "jti": "b7d9f2a8-unique-proof-id",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1924989000,
  "ath": "<BASE64URL_SHA256_OF_ACCESS_TOKEN>",
  "nonce": "<SERVER_NONCE_IF_REQUIRED>"
}
~~~

This is an illustrative payload. `nonce` may be absent if the server has not required a nonce; `ath` is required for proofs used alongside an access token at the Resource Server. Token timestamps must be generated at the actual request time, not copied from this fixed number.

### 4.1. JOSE Header

| Field | Requirement/Meaning |
|---|---|
| `typ` | Must identify proof type `dpop+jwt` |
| `alg` | Accepted asymmetric signature algorithm; never `none` |
| `jwk` | Public JSON Web Key used to verify the proof |

The `jwk` header contains the **public key**, never the private key. The Resource Server must validate the structure/algorithm/key type and allowed policy. Do not accept any arbitrary algorithm declared by the proof if it is not allowlisted by the server.

### 4.2. The `htm` Claim — HTTP Method

`htm` records the HTTP method of the request the proof represents:

~~~json
{
  "htm": "GET"
}
~~~

If the client signs a proof for `GET` while the actual request is `POST`, the Resource Server must reject it. Comparison must follow HTTP/DPoP method rules without arbitrarily normalizing two different methods into one.

### 4.3. The `htu` Claim — HTTP Target URI

`htu` records the target URI of the request. Under DPoP, query and fragment components are excluded from `htu`. Example request:

~~~http
GET https://api.example.test/api/orders/42?expand=items HTTP/1.1
~~~

The proof may carry:

~~~json
{
  "htu": "https://api.example.test/api/orders/42"
}
~~~

Do not include `?expand=items` or fragments in `htu`. URI matching must follow RFC 9449 normalization rules, especially when a reverse proxy, scheme/host rewrite, or port mapping is involved. The client and Resource Server must derive the same target URI according to contract, never trusting a URL string dictated by an untrusted header.

### 4.4. The `iat` Claim — Proof Creation Time

`iat` is when the proof was created, represented as a Unix NumericDate. The Resource Server checks that the proof is sufficiently fresh within an allowed time window.

~~~json
{
  "iat": 1924989000
}
~~~

Old proofs or timestamps too far in the future/past must be rejected by policy. Clock skew must be bounded; an overly wide window increases the time during which a replay attack can occur.

### 4.5. The `jti` Claim — Proof Identifier

`jti` is the unique identifier of the proof. Clients should generate an unpredictable/non-repeating value per proof, such as a high-quality random UUID or suitable random identifier.

The Resource Server can store (key thumbprint, `jti`) in a replay cache for the acceptance window. If the same proof is sent again, the server detects replay and rejects it. `jti` does not replace the signature or the `iat` check.

### 4.6. The `ath` Claim — Access Token Hash

When a proof accompanies an access token at a Resource Server, `ath` binds the proof to the exact token being presented. The value is computed from the access token:

~~~text
ath = BASE64URL-ENCODE(SHA-256(ASCII(access_token)))
~~~

Do not add padding to the Base64URL output. You must hash **the exact access token string sent in `Authorization`**, not the proof JWT, decoded payload, token prefix, or a modified representation.

If an attacker swaps the access token in the Authorization header while keeping the same proof, `ath` mismatches and the request is rejected.

### 4.7. The `nonce` Claim — Server Challenge

The Resource Server or Authorization Server can require the client to use a recent nonce. The server sends the nonce in the `DPoP-Nonce` response header; the client places that value in the `nonce` claim of its next proof.

Nonces help the server prove the proof was created after the client received the challenge, reducing the usefulness of pre-generated proofs. Nonces do not replace `jti`/replay caches and are not access tokens.

## 5. DPoP Flow at the Authorization Server and Resource Server

DPoP has two critical stages: **obtaining an access token** and **using the access token to call an API**. Both can use DPoP proofs, with each proof generated for its respective endpoint/method.

### 5.1. Initial Step: Client Generates a Key Pair

The client generates an asymmetric key pair:

~~~text
Private key: used to sign proofs, kept within the client
Public key:  represented as a public JWK, included in the proof header
~~~

The client must keep the key pair consistent while tokens remain bound to that key. If the client loses the private key or swaps keys, tokens already bound to the old key do not automatically work with the new key.

### 5.2. Client Sends a Token Request with a DPoP Proof

Example Authorization Code grant:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: <TOKEN_ENDPOINT_DPOP_PROOF>

grant_type=authorization_code&
code=<AUTHORIZATION_CODE>&
redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback&
client_id=shop-spa-client&
code_verifier=<PKCE_CODE_VERIFIER>
~~~

The proof at the token endpoint must bind to:

~~~json
{
  "htm": "POST",
  "htu": "https://login.example.test/oauth2/token",
  "iat": 1924989000,
  "jti": "<UNIQUE_PROOF_ID>"
}
~~~

**There is no `ath` in a standard token-request proof** because the request is asking for an access token, not presenting that access token to a Resource Server yet. If the AS requires a nonce, the proof also includes the `nonce` claim.

For confidential clients, client authentication (e.g., client secret/`private_key_jwt`/mTLS per registration) may still be required concurrently. A DPoP proof does not automatically replace all client authentication methods; it provides the **proof-of-possession key** for token binding.

### 5.3. Authorization Server Verifies the Proof and Binds the Token

The Authorization Server needs to:

1. Parse the compact DPoP JWT and require `typ=dpop+jwt`.
2. Accept only asymmetric signing algorithms allowed by policy.
3. Extract the public JWK from the proof header and verify the signature.
4. Check `htm`, `htu`, `iat`, `jti`, and `nonce` if required.
5. Compute the JWK thumbprint per RFC 7638.
6. Attach the thumbprint to the access token under the `cnf.jkt` confirmation claim.
7. Return the token with `token_type=DPoP` when issuing a DPoP-bound access token.

Illustrative JWT access token:

~~~json
{
  "iss": "https://login.example.test",
  "sub": "user-123",
  "aud": "https://api.example.test/orders",
  "scope": "orders.read",
  "cnf": {
    "jkt": "<THUMBPRINT_OF_CLIENT_PUBLIC_JWK>"
  },
  "exp": 1924992000
}
~~~

For opaque tokens, the binding can be retrieved by the Resource Server via an introspection response or an equivalent trusted mechanism. Whether the token is JWT or opaque, what matters is that **the server has a confirmation binding guaranteed by the issuer**.

Illustrative token endpoint response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<DPoP_BOUND_ACCESS_TOKEN>",
  "token_type": "DPoP",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

### 5.4. Client Calls the Resource Server with Both Headers

The client signs a fresh proof for each request:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP <DPoP_BOUND_ACCESS_TOKEN>
DPoP: <NEW_PROOF_FOR_THIS_REQUEST>
~~~

The proof payload for the API request contains:

~~~json
{
  "jti": "<FRESH_UNIQUE_PROOF_ID>",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1924989050,
  "ath": "<HASH_OF_THE_ACCESS_TOKEN>"
}
~~~

The client **must not reuse the token endpoint's proof** for an API call; the endpoint, method, and token hash differ. Clients must also not cache a single proof and attach it to multiple requests, even if the requests share the same method/URL.

### 5.5. Resource Server Verifies Token and Proof

The Resource Server verifies:

- The access token is valid: issuer, signature/introspection, audience, expiry, scopes, and confirmation binding.
- The proof JWT is valid: typ, alg, public JWK, signature.
- `htm` and `htu` match the request being handled.
- `iat` is within the freshness window.
- `jti` has not been used within the replay window.
- `ath` matches the access token in the Authorization header.
- `nonce` is valid if the server required a nonce.
- The public key thumbprint in the proof matches `cnf.jkt` in the access token.

Only after completing all mandatory checks does the server create the authentication context and apply authorization for the endpoint.

### 5.6. Overall Sequence Diagram

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>C: Generate/hold DPoP key pair
    C->>AS: Token request + DPoP proof
    AS->>AS: Verify proof and calculate JWK thumbprint
    AS-->>C: Access token (token_type=DPoP, cnf.jkt)
    C->>C: Sign new proof (htm, htu, iat, jti, ath)
    C->>RS: Authorization: DPoP token + DPoP proof
    RS->>RS: Validate access token and cnf.jkt
    RS->>RS: Validate proof signature/claims/replay/nonce
    alt Token and proof valid
        RS-->>C: API response
    else Invalid token/proof
        RS-->>C: Authentication error / DPoP nonce challenge
    end
~~~

## 6. How to Create Proofs for Each Request Type

### 6.1. Proof at the Token Endpoint

The token endpoint receives the `DPoP` header, where the proof has `htm=POST` and `htu` set to the token endpoint URI. No access token has been issued yet, so there is no `ath` bound to a new token. The proof still needs `jti` and `iat`; the server may require `nonce`.

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
DPoP: <PROOF_SIGNED_BY_CLIENT_PRIVATE_KEY>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=orders.read
~~~

With the Client Credentials grant, the AS must still check that the client is authorized for the requested scopes/resource and bind the access token to the request's DPoP key if issuing a DPoP-bound token. DPoP does not turn a client into a user principal with user permissions.

### 6.2. Proof at the Resource Server

An API request already has an access token, so the proof must include `ath`:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <PROOF_WITH_ATH>
~~~

If `ath` is missing, the hash mismatches, or the proof is bound to another token, the Resource Server rejects the request.

### 6.3. Every New Request Needs a New Proof

Example of two requests:

~~~text
Request A:
    GET /api/orders/42
    jti = proof-001
    ath = hash(access-token-A)

Request B:
    GET /api/orders/43
    jti = proof-002
    ath = hash(access-token-A)
~~~

Two requests may share the same access token/key, but `jti` must differ and each proof must be signed specifically for its method/URI. If an HTTP client or gateway retries a request, a new proof must be generated for the retry; resending the exact same proof may be rejected by replay detection.

### 6.4. Redirects and Proxy Rewriting

DPoP proofs are bound to `htu`. If a client signs for URL A but the HTTP client automatically follows a redirect to URL B, the old proof no longer represents the target URI. Do not automatically forward access tokens/proofs across redirects to another host. Clients must apply secure redirect policies, verify origins, and generate a new proof if the redirect is permitted.

A reverse proxy may receive HTTPS at the edge and forward HTTP to the application. If the Resource Server sees only the internal URI, it can compare `htu` incorrectly against the public URL the client signed. A clear trusted-proxy configuration is needed to reconstruct the external URI accurately; **never blindly trust `Forwarded`/`X-Forwarded-*` from arbitrary clients**.

## 7. JWK Thumbprint and the `cnf.jkt` Confirmation Claim

The DPoP proof header contains the public JWK. The Resource Server cannot simply see "proof has a valid signature" and accept it; an attacker could generate their own key pair and sign a proof with that key. The server must prove that the public key in the proof is the exact key the Authorization Server bound to the access token.

### 7.1. What Is a JWK Thumbprint?

A **JWK thumbprint** is a fingerprint computed from the required public-key members of a JWK per RFC 7638, serialized canonically and then hashed. DPoP uses SHA-256 to compute the key thumbprint `jkt`.

For EC P-256, the members used to calculate the thumbprint are:

~~~json
{
  "crv": "P-256",
  "kty": "EC",
  "x": "<PUBLIC_X>",
  "y": "<PUBLIC_Y>"
}
~~~

For RSA, the corresponding public members are `e`, `kty`, and `n`. Auxiliary fields like `kid`, `alg`, or private parameters must not be arbitrarily included to alter thumbprint calculation; use an RFC 7638-compliant JWK thumbprint implementation.

### 7.2. Token Binding in the `cnf` Claim

A DPoP-bound JWT access token may contain:

~~~json
{
  "cnf": {
    "jkt": "BASE64URL_SHA256_JWK_THUMBPRINT"
  }
}
~~~

`cnf` is the **confirmation claim**. `jkt` identifies the public key thumbprint to which the token is bound. When the Resource Server reads the verified token:

~~~text
accessToken.cnf.jkt
        ==
thumbprint(proof.header.jwk)
~~~

If they are not equal, the proof was signed with a different key than the one required by the token; the server rejects it, even if the proof signature under that key is valid on its own.

### 7.3. Example with Two Different Client Keys

~~~text
Client key A:
    public JWK = JWK-A
    thumbprint = JKT-A
    access token cnf.jkt = JKT-A

Request proof signed by private key A:
    header.jwk = JWK-A
    signature valid
    thumbprint = JKT-A
    → binding matches

Request proof signed by private key B:
    header.jwk = JWK-B
    signature valid under B
    thumbprint = JKT-B
    → binding mismatch, reject
~~~

### 7.4. Never Trust Self-Asserted `cnf` from Clients

Clients cannot inject `cnf.jkt` into an access token and expect the Resource Server to trust it. For JWT access tokens, `cnf` must reside inside a token signed by a trusted issuer. For opaque tokens, the Resource Server must obtain the binding from introspection/metadata authenticated by the Authorization Server.

Because the proof header `jwk` is sent by the client, it becomes evidence only when:

1. The proof signature is verified with that exact public JWK.
2. The public JWK thumbprint matches the verified `cnf.jkt` from the access token.
3. All proof claims and replay checks pass.

### 7.5. Tokens Missing Confirmation Binding

If the Resource Server processes a token expected to be DPoP-bound that lacks `cnf.jkt` or an equivalent binding, never extract the JWK from the proof and treat it as the binding. When the server has no proof of which key the token is tied to, **proof possession is not bound to the access token**.

If an API supports both Bearer and DPoP tokens, separate schemes/policies must be defined for each. A regular Bearer access token cannot become DPoP-bound simply because a client adds a `DPoP` header.

## 8. Creating a DPoP Proof JWT with Java and Nimbus JOSE/JWT

To understand how a client constructs both headers, we can use Nimbus JOSE/JWT. The example below creates an EC P-256 key pair, public JWK, `ath`, and proof for an HTTP request. It illustrates the **proof-signing portion**, not a complete OAuth client or production-grade DPoP library.

### 8.1. Generating an EC Key Pair

~~~java
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.spec.ECGenParameterSpec;

KeyPairGenerator generator = KeyPairGenerator.getInstance("EC");
generator.initialize(new ECGenParameterSpec("secp256r1"));
KeyPair dpopKeyPair = generator.generateKeyPair();
~~~

`secp256r1` corresponds to the P-256 curve used for ES256. Keep `dpopKeyPair.getPrivate()` in appropriate key storage. Never serialize the private key into requests.

### 8.2. Computing `ath` from the Access Token

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

This is how `ath` is computed under DPoP: SHA-256 over the ASCII bytes of the access token, then Base64URL without padding. Do not hash the `"Bearer "`/`"DPoP "` prefix from the HTTP header; hash only the **access token value**.

### 8.3. Building the Public JWK and Signing the Proof

~~~java
import java.security.interfaces.ECPrivateKey;
import java.security.interfaces.ECPublicKey;
import java.security.KeyPair;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.ECDSASigner;
import com.nimbusds.jose.jwk.Curve;
import com.nimbusds.jose.jwk.ECKey;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

static String createDpopProof(
        KeyPair keyPair,
        String httpMethod,
        String htu,
        String accessToken,
        String nonce) throws Exception {

    ECKey publicJwk = new ECKey.Builder(
            Curve.P_256,
            (ECPublicKey) keyPair.getPublic())
        .build();

    Instant now = Instant.now();
    JWTClaimsSet.Builder claims = new JWTClaimsSet.Builder()
        .jwtID(UUID.randomUUID().toString())
        .claim("htm", httpMethod)
        .claim("htu", htu)
        .issueTime(Date.from(now));

    if (accessToken != null) {
        claims.claim("ath", accessTokenHash(accessToken));
    }

    if (nonce != null && !nonce.isBlank()) {
        claims.claim("nonce", nonce);
    }

    JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.ES256)
        .type(new JOSEObjectType("dpop+jwt"))
        .jwk(publicJwk)
        .build();

    SignedJWT proof = new SignedJWT(header, claims.build());
    proof.sign(new ECDSASigner((ECPrivateKey) keyPair.getPrivate()));
    return proof.serialize();
}
~~~

`accessToken` can be `null` when creating a proof for the token endpoint (no access token exists yet to hash). For Resource Server requests, pass the access token to generate `ath`. `htu` must be the target URI following DPoP rules without query/fragment; `httpMethod` must be the actual method.

The snippet above uses `UUID` as an illustrative `jti`. Production needs a strong random source, collision avoidance, and key lifecycle management. Nimbus library versions may vary in overloads; when applying this, match the API to the dependency version pinned in your project.

### 8.4. Sending the Request with Both Headers

Once you have `accessToken` and `proof`:

~~~java
String proof = createDpopProof(
    dpopKeyPair,
    "GET",
    "https://api.example.test/api/orders/42",
    accessToken,
    serverNonce
);

// Pseudocode: use the application's HTTP client.
request.header("Authorization", "DPoP " + accessToken);
request.header("DPoP", proof);
~~~

The two `request.header(...)` lines are **pseudocode**, not a specific HTTP client API. For Spring `WebClient`, Java `HttpClient`, or an OAuth client SDK, use the corresponding request builder API. Do not log either header value while debugging.

### 8.5. Creating a Proof for the Token Endpoint

~~~java
String tokenEndpointProof = createDpopProof(
    dpopKeyPair,
    "POST",
    "https://login.example.test/oauth2/token",
    null,            // No access token yet, so no ath
    serverNonce      // null if the AS has not required a nonce
);
~~~

The token endpoint request still places the proof in the **`DPoP` header**:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: <TOKEN_ENDPOINT_PROOF>

grant_type=authorization_code&code=<AUTHORIZATION_CODE>&...
~~~

## 9. How Does the Resource Server Verify a DPoP Proof?

Do not build validation logic solely around a signature check. A proof with a valid signature can still:

- Use the wrong HTTP method or URI.
- Be bound to a different access token.
- Have been created too long ago or in the future.
- Have already been used before.
- Be signed with a key that does not match the token binding.
- Lack a nonce required by the server.

### 9.1. Conceptual Validation Sequence

~~~text
1. Parse Authorization: DPoP <access-token>
2. Extract DPoP proof JWT from DPoP header
3. Validate access token:
     signature/introspection
     issuer, audience, expiry, scope
     confirmation binding cnf.jkt
4. Validate proof JOSE header:
     typ=dpop+jwt
     allowed asymmetric alg
     public jwk only
     verify signature
5. Validate proof claims:
     htm == current HTTP method
     htu == current target URI (without query/fragment)
     iat within accepted time window
     ath == hash(presented access token)
     nonce valid when required
6. Check jti has not been used (replay detection)
7. Compare thumbprint(proof jwk) == access token cnf.jkt
8. Only then establish authenticated principal
9. Apply scope/role and domain authorization
~~~

Actual execution order may be optimized to reduce DoS/cost, but **no mandatory check may be skipped**. For instance, a server may parse token headers/claims only after signature checks; never trust `cnf.jkt` before verifying the token.

### 9.2. Validating `typ` and `alg`

The server must require the proof JWT type to be exactly `dpop+jwt` and use a supported asymmetric algorithm. Symmetric algorithms such as HS256 are unsuitable because the server would need a shared secret, breaking the public-key proof model. `alg=none` must never be accepted.

The public JWK must have a valid key type/curve/parameters for the chosen algorithm. Reject any private parameters in the proof's `jwk` header; the proof needs only the public key for the verifier to check the signature.

### 9.3. Verifying the Signature with the Proof's Public JWK

Unlike a JWT access token, the proof key is sent by the client in the `jwk` header. The server parses the public JWK, verifies the proof's own signature, and then computes its thumbprint to compare with the binding in the access token.

Having the proof carry its own public JWK does not establish trust on its own. **Trust comes from matching the key thumbprint against the confirmation binding issued by the issuer in the verified access token**.

### 9.4. Checking `htm`

Compare `htm` with the actual HTTP method. A `GET` proof is invalid for a `POST` request; do not treat `GET` and `get` as identical proof claims unless normalized strictly per RFC contract/implementation.

### 9.5. Checking `htu`

Compute the target URI from the request following DPoP rules:

- Scheme and authority/host must accurately reflect the target URI.
- Query and fragment are excluded from `htu`.
- Normalization/comparison must follow RFC 9449, not arbitrary string matching.
- Behind a reverse proxy, use forwarded metadata only from trusted proxies.
- Never use an arbitrary request-supplied host to pick a different audience/issuer.

### 9.6. Checking `iat` and Timestamps

The server must enforce a freshness window that is tight enough while allowing reasonable clock skew. For example, an illustrative policy might accept proofs created within the last 60 seconds, though real figures depend on clock synchronization, latency, and threat model.

Do not set an excessively long window; it extends how long a stolen proof can be replayed. At the same time, large client/server clock drift can cause valid requests to fail. System time synchronization is part of operating DPoP.

### 9.7. Checking `ath`

The Resource Server extracts the access token from the Authorization header, computes `BASE64URL(SHA-256(token))`, and compares it strictly against the proof's `ath` claim. If it differs or is missing, reject the request.

This prevents attackers from pairing a valid proof for token A with access token B. Never read `ath` from another header or from client-supplied fields outside the signed proof.

### 9.8. Matching `cnf.jkt`

After verifying the access token and the proof:

~~~text
token.cnf.jkt
    ==
RFC7638_SHA256_JWK_THUMBPRINT(proof.header.jwk)
~~~

If there is a mismatch, the proof key is not the key bound to the token. **Do not fall back to Bearer authentication** merely because DPoP binding failed.

### 9.9. Replay Detection with `jti`

The server stores accepted proof identifiers in a replay cache whose TTL matches the freshness window. Cache keys typically need to include the thumbprint (or trusted namespace) and `jti` to avoid collisions across clients:

~~~text
replay-cache-key = thumbprint + ":" + jti
ttl              = proof acceptance window
~~~

The check-and-write operation must be **atomic** in multi-node systems. If each instance maintains its own local cache, an attacker can send the same proof to node A and then node B and have both accept it. Use a shared/distributed cache or a sufficiently strong synchronization mechanism; if the replay store is unavailable, policy must be explicit and must not silently skip replay detection.

### 9.10. Checking the Nonce

If the server requires a nonce, the subsequent proof must include a `nonce` claim matching a server-issued nonce. Nonces need sufficient entropy and an appropriate lifetime/validation policy. The server may issue a new nonce in a response header for the client to use on the next request.

Nonces and `jti` serve two distinct purposes:

| Mechanism | Prevents / Enforces |
|---|---|
| `jti` + replay cache | Detects proofs that have already been reused |
| `iat` freshness | Limits the age of a proof |
| `nonce` | Binds the proof to a recent server-generated challenge |

Do not treat nonces as a reason to skip `jti` or `iat` validation.

## 10. Nonce Challenges and How Clients Handle Them

Nonces are part of the request/response protocol between client and server. Clients do not invent nonces for the server; the server issues a nonce and the client embeds it into a **new proof**.

### 10.1. Resource Server Requires a Nonce

Suppose a client sends a request without a server-accepted nonce:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <PROOF_WITHOUT_REQUIRED_NONCE>
~~~

The Resource Server may return a challenge:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: DPoP error="use_dpop_nonce"
DPoP-Nonce: <SERVER_GENERATED_NONCE>
Cache-Control: no-store
~~~

The client reads `DPoP-Nonce` and constructs a new proof:

~~~json
{
  "jti": "<NEW_UNIQUE_PROOF_ID>",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders",
  "iat": 1924989100,
  "ath": "<HASH_OF_ACCESS_TOKEN>",
  "nonce": "<SERVER_GENERATED_NONCE>"
}
~~~

Then the client resends the request with the same access token (if still valid) and the **new DPoP proof**:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: DPoP <ACCESS_TOKEN>
DPoP: <NEW_PROOF_WITH_NONCE>
~~~

### 10.2. Nonces at the Token Endpoint

The Authorization Server can also require a nonce when obtaining/refreshing a token. The token endpoint typically returns the OAuth error `use_dpop_nonce` along with a `DPoP-Nonce` header; the client must create a new proof containing the `nonce` claim and retry the token request.

Illustrative response:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
DPoP-Nonce: <AS_NONCE>
Cache-Control: no-store

{
  "error": "use_dpop_nonce",
  "error_description": "A fresh DPoP proof with the supplied nonce is required."
}
~~~

HTTP status codes and response details must follow the contract/RFC and endpoint implementation; clients should distinguish token endpoint challenges from Resource Server challenges.

### 10.3. Clients Must Not Resend the Old Proof

After a challenge, generate a brand-new proof JWT:

- New `jti`.
- New `iat`.
- Latest `nonce` claim provided by that exact server.
- `htm`/`htu` still matching the retried request.
- `ath` still hashing the presented access token.
- Signed with the private key bound to the access token.

Do not simply append `nonce` to the old JWT payload while keeping the old signature. Any payload change requires re-signing. Never reuse an Authorization Server nonce for another Resource Server unless the contract explicitly defines sharing scope.

### 10.4. Nonces Can Rotate Across Responses

The server may issue fresh nonces in responses; clients should manage nonces per **server/authority and context** rather than using a single global variable across all issuers/resources. An old nonce may expire or be replaced by the server. Clients must be ready to handle challenges without entering an infinite loop if the server repeatedly returns `use_dpop_nonce`.

### 10.5. Retries After a Nonce Challenge Must Be Bounded

A single retry after `use_dpop_nonce` is normal protocol behavior, but you must:

- Bound consecutive challenge retries to avoid infinite loops.
- Generate a fresh proof on every retry.
- Preserve the same resource/issuer trust policy.
- Avoid retrying endlessly when the nonce is wrong, the proof is invalid, or the token has expired.
- Avoid logging nonces alongside raw tokens in HTTP wire logs if treated as sensitive data.

## 11. Error Handling and HTTP Responses

DPoP distinguishes access token errors, proof errors, and nonce errors. The Resource Server should map errors according to cause without leaking unnecessary internal details.

| Error | Meaning | Typical Handling |
|---|---|---|
| `invalid_token` | Access token invalid/expired/mismatched binding | Authentication fails |
| `invalid_dpop_proof` | Invalid proof: signature, claims, method, URI, `ath`, replay... | Reject request |
| `use_dpop_nonce` | Server requires a fresh nonce in the proof | Return nonce challenge |
| Missing DPoP header | Request uses DPoP scheme without a proof | Reject |
| Bearer scheme with DPoP-bound token | Client uses wrong authorization scheme or violates policy | Reject per token binding/scheme policy |
| Replay detected | `jti` was previously accepted | Reject proof |

### 11.1. Example of an Invalid Proof Response

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: DPoP error="invalid_dpop_proof"
Cache-Control: no-store
~~~

This is an illustrative response; APIs may use their own error body format. Never expose full public JWKs, access tokens, signature bytes, private-key data, or internal stack traces in public responses.

### 11.2. Invalid Token vs. Invalid Proof Are Not the Same

For example:

~~~text
Access token expired:
    → invalid_token

Access token valid, but proof htm=POST while request is GET:
    → invalid_dpop_proof

Access token valid, proof signed by another key:
    → binding mismatch / invalid_dpop_proof

Access token valid, nonce required but absent:
    → use_dpop_nonce challenge (if that is the nonce policy)
~~~

Classification helps clients and metrics. Regardless of the error, however, the request must never continue into controllers/services with an authenticated principal.

### 11.3. `WWW-Authenticate` Scheme Must Reflect DPoP

When a Resource Server issues a challenge for DPoP authentication, the challenge scheme should align with DPoP, for example:

~~~http
WWW-Authenticate: DPoP error="invalid_token"
~~~

Do not default every DPoP failure to emitting `Bearer error=...`. Clients rely on the proper scheme to execute the nonce flow or handle token/proof errors.

## 12. Integrating DPoP with Spring Security

Spring Security provides building blocks for an OAuth 2.0 Resource Server: authentication filters, token converters, `JwtDecoder`/`ReactiveJwtDecoder`, authentication providers/managers, and authorization rules. However, **a standard JWT configuration does not automatically mean DPoP is fully implemented**.

### 12.1. A Standard JWT Resource Server Is Not Enough

Example standard JWT configuration:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()));
~~~

or WebFlux:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()));
~~~

These configurations represent JWT resource server authentication. They **must not be assumed to**:

- Accept the `Authorization: DPoP` scheme.
- Read and verify the `DPoP` header.
- Validate `htm`/`htu`/`ath`/`jti`/nonce.
- Compare `cnf.jkt` against the proof key.
- Maintain a distributed replay cache.

Native DPoP capabilities, APIs, and DSLs depend on the **Spring Security/Spring Boot version** and implementation in use. Verify the official documentation for your exact version before choosing a configuration. If the version has full DPoP support, use the documented API and still test the boundaries below. Otherwise, an explicit DPoP integration layer is required.

### 12.2. Responsibilities Required in an Integration Layer

A custom architecture needs at least:

| Component | Responsibility |
|---|---|
| Authorization header converter | Parses the `DPoP` scheme and extracts the access token |
| Proof header resolver | Extracts exactly one DPoP proof JWT from the `DPoP` header |
| Access token verifier | Verifies JWT or introspection: issuer, audience, expiry, scopes |
| DPoP proof verifier | Verifies JOSE, signature, `htm`, `htu`, `iat`, `ath`, `nonce` |
| JWK thumbprint verifier | Compares the proof key thumbprint with `cnf.jkt` |
| Replay store | Checks/records `jti` atomically |
| Nonce service | Issues, stores, or verifies nonces per policy |
| Authentication provider/manager | Creates a principal only when both token and proof are valid |
| Authorization layer | Enforces scopes/roles and business permissions |

### 12.3. Conceptual Servlet Flow

~~~text
HTTP request
    |
    v
DPoP Authentication Converter
    |-- Authorization: DPoP <access-token>
    |-- DPoP: <proof>
    v
DPoP Authentication Token (unauthenticated)
    |
    v
AuthenticationManager / Provider
    |-- verify access token
    |-- verify proof signature + claims
    |-- compare cnf.jkt
    |-- check replay / nonce
    v
Authenticated principal
    |
    v
HTTP / method / domain authorization
~~~

In Servlet, a custom `AuthenticationConverter` paired with an `AuthenticationManager`/provider can serve as integration points depending on architecture. An appropriate filter in the security chain can also be used, provided it runs **before authorization** and sets the SecurityContext only after all DPoP validation succeeds.

### 12.4. Conceptual WebFlux Flow

~~~text
ServerWebExchange
    |
    v
ServerAuthenticationConverter
    |-- parse Authorization: DPoP
    |-- parse DPoP proof header
    v
Unauthenticated DPoP Authentication
    |
    v
ReactiveAuthenticationManager
    |-- ReactiveJwtDecoder / introspector
    |-- DPoP proof validation (Mono)
    |-- reactive replay/nonce store
    v
Authenticated Authentication
    |
    v
Reactive authorization rules
~~~

In WebFlux, replay/nonce store operations, remote introspection, and JWKS retrieval should maintain reactive/non-blocking behavior. Never block the event loop with `Thread.sleep` or synchronous remote cache/database calls.

### 12.5. Do Not Downgrade the DPoP Scheme to Bearer and Drop the Proof

Anti-pattern:

~~~java
// ANTI-PATTERN: DPoP scheme is downgraded to Bearer.
String token = authorizationHeader.substring("DPoP ".length());
return bearerAuthenticationManager.authenticate(
    new BearerTokenAuthenticationToken(token)
);
~~~

This snippet extracts the access token and calls Bearer authentication; it **completely discards the proof header and sender constraint**. The token may still validate as Bearer if the decoder does not enforce `cnf`/DPoP, defeating the protection goal.

If you need to support both Bearer and DPoP:

- Handle the Bearer scheme under a dedicated Bearer policy.
- Handle the DPoP scheme with full proof/binding validation.
- Never automatically fall back from an invalid DPoP request to Bearer.
- Never accept a DPoP-bound token over Bearer if issuer/server policy requires DPoP.

### 12.6. DPoP Proofs Must Be Checked Before Creating a Principal

Never create an `Authentication` and defer proof checking to a controller. If a subsequent controller/filter forgets to check, or a public endpoint bypasses it, the token is already treated as authenticated despite an invalid proof. **DPoP is part of authentication**, not an optional controller parameter.

### 12.7. The Authorization Server and OAuth Client Must Also Support It

Resource Server support alone is insufficient if the Authorization Server does not issue DPoP-bound tokens or the client cannot create proofs. The entire chain requires:

~~~text
OAuth client:
    key management + proof generation + token request

Authorization Server:
    proof validation + token binding + DPoP token_type

Resource Server:
    access token validation + proof validation + replay defense
~~~

If any link processes only Bearer, the DPoP sender constraint cannot be upheld.

## 13. DPoP on the OAuth Client Side: Key and Proof Lifecycle

The client is responsible for generating proofs, so it needs a dedicated component rather than scattering JWT-signing logic across controllers.

### 13.1. Managing Keys per Client Instance

A client instance should manage:

~~~text
DpopKeyManager
  ├─ generate or load key pair
  ├─ expose public JWK
  ├─ sign DPoP proof
  ├─ calculate JWK thumbprint
  ├─ track token -> bound key
  └─ rotate/retire keys
~~~

If an application serves multiple users/sessions or devices, decide whether keys are scoped to a **browser profile, app installation, client instance, service identity, or session**. Do not share private keys more broadly than necessary; if one key is shared across many users/instances, a key leak has a much wider blast radius.

### 13.2. Tracking the Link Between Access Tokens and Keys

The client must track which access token was issued with which key to create valid proofs:

~~~text
Token record:
    access_token = ...
    token_type   = DPoP
    expires_at   = ...
    dpop_key_id  = key-alias-17
~~~

Do not store the private key inside the token record; reference only a key alias/handle in a secure key store. Access tokens and refresh tokens remain sensitive credentials and must be encrypted/protected according to the client model.

### 13.3. Generate the Proof After Finalizing the Request URL and Method

The HTTP client interceptor needs to know:

- The final method (GET/POST/PUT/PATCH/DELETE...).
- The final target URI after base URL and path resolution.
- The exact access token being placed in the Authorization header.
- The latest nonce for that exact server, if any.

Only then should it sign the proof and attach both headers. If an interceptor signs the proof before the client finalizes the URL, `htu` may not match the final request.

### 13.4. Generate a New Proof for Every Retry/Redirect

When an HTTP client automatically retries due to a network error or 503, the previous proof was already sent or may have been received by the server. A retry must:

1. Recompute the actual method/URI.
2. Generate a new `jti`.
3. Update `iat`.
4. Recompute `ath` if the access token changed.
5. Include the current nonce if required.
6. Sign a new proof using the private key bound to the token.

Never cache a proof as a static header on a default request builder. If a token refresh or key rotation occurs, ensure the proof is generated with the exact key matching the token being sent.

### 13.5. DPoP for Refresh Tokens

When the Authorization Server issues a refresh token bound to a DPoP key, the client must continue using the corresponding key when sending refresh requests per contract. Refreshing may return a new access token with the same or updated binding depending on the AS mechanism; clients must not assume the new token is bound to a different key unless the response/protocol specifies so.

If the private key is lost:

- The client may no longer be able to use access/refresh tokens bound to that key.
- A new token issuance flow with a new key is typically required per Authorization Server policy.
- Do not swap the public JWK in the proof while keeping the old access token and expect the token binding to update itself.
- Handle revocation/re-authentication according to token lifecycle and issuer policy.

### 13.6. Key Rotation

An access token already bound to thumbprint `JKT-A` continues to require proofs from key A. When the client switches to key B:

~~~text
Old token:
    cnf.jkt = JKT-A
    proof must be signed by private key A

New token:
    cnf.jkt = JKT-B
    proof must be signed by private key B
~~~

Do not immediately discard key A while old tokens are still in use unless a transition process exists. You can keep both keys active while old tokens remain valid, provided the mapping of which token uses which key is stored and looked up accurately.

## 14. DPoP and Reverse Proxies, Gateways, and CORS

DPoP binds proofs to URI and method. This requires careful configuration of intermediate layers.

### 14.1. HTTPS Termination

Example:

~~~text
Client
  → https://api.example.test/orders/42
  → Gateway terminates TLS
  → http://orders-service:8080/orders/42
~~~

The client signs `htu` based on the public HTTPS URL. The backend sees only HTTP and an internal host. If the backend compares directly against the internal URL, valid proofs will fail.

Architectural solution:

- Make the gateway the sole trusted proxy or maintain a trusted proxy list.
- Have the gateway forward the external scheme/host/path under an explicit contract.
- Have the backend trust forwarded headers only from authenticated/network-restricted proxies.
- Configure the framework to reconstruct the external request URI safely, preventing client-spoofed headers.
- Test both direct requests and gateway-routed requests matching the deployment architecture.

### 14.2. Path Rewriting

If the gateway rewrites:

~~~text
Public:  /api/orders/42
Internal: /orders/42
~~~

then `htu` compared by the Resource Server must be determined from the target URI used by the client and how the proxy preserves the original path info. Do not arbitrarily add/strip prefixes; align URI canonicalization across the client, gateway, and verifier.

### 14.3. Never Trust Forwarded Headers from the Internet

If an attacker can send:

~~~http
Forwarded: proto=https;host=api.example.test
X-Forwarded-Host: api.example.test
X-Forwarded-Proto: https
~~~

and the application directly treats them as `htu`, the attacker can manipulate how the server checks the proof URI. Accept forwarded metadata only from trusted proxies; gateways must strip client-sent headers before adding their own values.

### 14.4. CORS for the `DPoP` Header

Browser clients must be allowed to send custom headers in CORS preflight. Illustrative policy:

~~~http
Access-Control-Allow-Headers: Authorization, DPoP, Content-Type
Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS
~~~

This is not a complete CORS configuration; declare specific origins, credentials policy, allowed methods, and appropriate response headers. If the client must read server-returned nonces:

~~~http
Access-Control-Expose-Headers: DPoP-Nonce, WWW-Authenticate
~~~

The browser must be allowed to read `DPoP-Nonce` in order to build the next proof. Never use `Access-Control-Allow-Origin: *` unconditionally with credentials. CORS is strictly a browser policy; **it does not replace authentication or DPoP proof validation**.

### 14.5. The Gateway Must Not Drop Either Header

Verify that the proxy/gateway:

- Properly forwards `Authorization: DPoP`.
- Properly forwards the `DPoP` header.
- Does not write raw tokens/proofs to access logs.
- Does not rewrite the Authorization scheme to Bearer.
- Does not merge or drop duplicate headers outside policy.
- Preserves the exact request method and URI mapping.

If the gateway validates DPoP and downstream services also require DPoP, the gateway must preserve or use an appropriate delegation/token mechanism. Never forward a DPoP-bound access token downstream without maintaining its binding.

## 15. What DPoP Does Not Protect Against

DPoP strengthens defense against replaying stolen tokens, but it is not a silver bullet for all client/API risks.

### 15.1. Does Not Protect Against a Stolen Private Key

If an attacker steals both the access token and the private key, they can forge valid proofs. Protecting keys in secure storage, limiting read permissions, restricting export, monitoring anomalies, and having rotation/revocation procedures remain essential.

### 15.2. Does Not Automatically Defend Against Client-Controlling XSS

In an SPA, XSS running in the same origin can invoke the proof-signing function using the application's key, even when the key is non-exportable. DPoP makes it harder to take a token to another machine, but does not prevent a hijacked browser from making requests on the user's behalf.

You still need CSP, output encoding, dependency hygiene, avoiding unnecessary token storage, script controls, and session management practices.

### 15.3. Does Not Encrypt Access Tokens or Proofs

Proof JWTs and access tokens can be read by request-inspection layers if logged. DPoP is not encryption. Use TLS and redaction in logging, tracing, and proxies.

### 15.4. Does Not Sign the Entire Request Body

A standard proof binds specified claims such as method, URI, and access-token hash; it **does not sign JSON bodies or arbitrary custom headers by default**. TLS is still required for transport confidentiality/integrity. If the application requires application-level payload integrity, use a separate request-signing/message-integrity mechanism aligned with your threat model.

### 15.5. Does Not Replace Authorization

A valid proof only demonstrates the client holds the private key bound to the token. It does not permit a user to read every order, does not replace scope/role/tenant/owner checks, and does not turn an expired token into a valid one.

### 15.6. Does Not Replace Mutual TLS in Every Architecture

DPoP and mTLS have different deployment models:

| DPoP | mTLS certificate-bound token |
|---|---|
| Proof JWT at the application layer | TLS client certificate at the transport layer |
| Proof-signing key belongs to the OAuth client | Client certificate/private key used in TLS handshake |
| Proof contains `htm`/`htu`/`ath`/`jti` | Token bound to certificate thumbprint |
| Can work through proxies if proofs/URIs are forwarded accurately | TLS termination/proxies directly affect client certificates |

The choice depends on client platforms, proxy/network architecture, operational requirements, and AS/RS support. Do not treat the two mechanisms as interchangeable without re-evaluating the trust model.

## 16. Testing DPoP: Verify Both Token Binding and Proofs

A DPoP test suite cannot stop at generating a valid JWT access token and calling the API. You need a **positive control** with an access token containing `cnf.jkt` and a proof signed with the matching key, followed by mutating each attribute to confirm the server rejects it.

### 16.1. Test Fixture Set

A test fixture should construct:

~~~text
Trusted issuer signing key:
    used to sign the access token JWT (if testing JWT)

Client DPoP key pair A:
    public JWK A
    private key A
    thumbprint JKT-A

Client DPoP key pair B:
    public JWK B
    private key B
    thumbprint JKT-B

Access token A:
    iss = trusted issuer
    aud = orders-api
    exp = future
    scope = orders.read
    cnf.jkt = JKT-A

Valid proof A:
    signed by private key A
    header.jwk = public JWK A
    htm/htu match request
    ath = hash(access token A)
    fresh iat, unused jti
~~~

Key pair B lets you test a proof with a valid signature that is **not the key bound to the token**. Keep the access-token signing key and the client's DPoP key separate: they serve two different roles.

### 16.2. Resource Server Matrix

| Case | Change from Positive Control | Result |
|---|---|---|
| P-01 | Valid access token, proof with matching key/claims | Passes authentication; succeeds if scope is sufficient |
| P-02 | Missing `DPoP` header | Rejected |
| P-03 | `Authorization` missing scheme/token | Rejected |
| P-04 | Using `Bearer` when token policy requires DPoP | Rejected per policy |
| P-05 | Malformed proof / not a compact JWT | Rejected |
| P-06 | `typ` other than `dpop+jwt` | Rejected |
| P-07 | `alg=none` or symmetric algorithm | Rejected |
| P-08 | Invalid proof signature | Rejected |
| P-09 | Proof signed by key B while token has `cnf.jkt=JKT-A` | Rejected (binding mismatch) |
| P-10 | `htm` differs from HTTP method | Rejected |
| P-11 | `htu` differs from target URI | Rejected |
| P-12 | `htu` contains query/fragment violating rules | Rejected per RFC validation |
| P-13 | `iat` too old or too far in the future | Rejected |
| P-14 | `jti` already used | Rejected (replay) |
| P-15 | Missing `ath` on resource request | Rejected |
| P-16 | `ath` hashes a different token | Rejected |
| P-17 | Nonce required but proof missing/wrong nonce | `use_dpop_nonce` challenge or rejected per policy |
| P-18 | Expired access token | Token rejected |
| P-19 | Access token wrong audience/issuer | Token rejected |
| P-20 | Token missing scope | Authentication may succeed, authorization rejects |
| P-21 | Replay of same proof sent to two nodes | Only first request accepted |
| P-22 | Token lacks `cnf.jkt` while client sends proof | Do not fabricate binding; reject DPoP authentication |

### 16.3. Authorization Server Matrix

| Case | Token endpoint request | Result to verify |
|---|---|---|
| AS-01 | Valid DPoP proof, valid token grant | Token type DPoP, `cnf.jkt` bound to matching key |
| AS-02 | Invalid proof signature | Do not issue DPoP-bound token |
| AS-03 | Wrong `htm`/`htu` | Reject proof |
| AS-04 | Old/future `iat` | Reject proof |
| AS-05 | Replayed `jti` | Reject per replay policy |
| AS-06 | Nonce required but omitted | Return challenge/nonce |
| AS-07 | New proof with matching nonce | Token request can proceed if grant/client are valid |
| AS-08 | Token refresh using wrong key | Disallow refreshing a token bound to another key |
| AS-09 | Client not allowed for resource/scope | Do not issue token even if proof is valid |

A valid proof **does not replace the authorization grant**. After proof validation, the AS must still check code/PKCE/client authentication, consent, scopes, resource, and grant policy before issuing tokens.

### 16.4. Testing Right Key vs. Wrong Key

Test logic:

~~~text
token.cnf.jkt = JKT-A

proof A:
    signature verifies with JWK-A
    thumbprint(JWK-A) = JKT-A
    → accept (if claims/replay/token are all valid)

proof B:
    signature verifies with JWK-B
    thumbprint(JWK-B) = JKT-B
    → reject (binding mismatch)
~~~

What needs to be proven is that proof B **has its own valid signature** yet is still rejected because it does not match the token binding. If proof B is generated with a broken signature, the test proves only signature validation, not the `cnf.jkt` comparison.

### 16.5. Testing `ath`

Create a proof with access token A and send it alongside access token B:

~~~text
proof.ath = BASE64URL(SHA-256(token A))
Authorization: DPoP token B
~~~

The Resource Server must recompute `ath` from token B and reject the mismatch. Also test missing `ath` and a hash modified by a single character. Do not only assert that token B decodes validly; assert that the **proof/token association** fails.

### 16.6. Testing Replay

Send the exact same proof request twice:

~~~text
First request:
    jti = proof-123
    → accepted (if other conditions are valid)

Second request:
    jti = proof-123
    → replay rejected
~~~

If the API is idempotent and the client needs to retry a business request, the retry must still generate a **new proof** with a new `jti`. Replay tests must run against a replay store with the same semantics as the deployment environment, especially when multiple instances exist.

## 17. Testing DPoP with Spring WebFlux/Servlet

Once the Spring integration layer supports DPoP, use real HTTP tests running through the filter chain. Do not call only the proof validator directly.

### 17.1. Conceptual WebFlux HTTP Test

~~~java
// Pseudocode: specific helpers/APIs depend on the application's DPoP support.
String accessToken = issueDpopBoundToken(
    clientKeyPairA,
    "https://api.example.test/orders",
    "orders.read"
);

String proof = createDpopProof(
    clientKeyPairA,
    "GET",
    "https://api.example.test/api/orders",
    accessToken,
    null
);

webTestClient.get()
    .uri("/api/orders")
    .headers(headers -> {
        headers.set("Authorization", "DPoP " + accessToken);
        headers.set("DPoP", proof);
    })
    .exchange()
    .expectStatus().isOk();
~~~

`issueDpopBoundToken(...)` and `createDpopProof(...)` are test/issuer fixture helpers, not built-in Spring Security methods. The test app must configure a real DPoP authentication layer and an existing controller route.

### 17.2. Testing a Proof with the Wrong Method

Keep the token, key, `htu`, `ath`, and all other claims valid; only create a proof with `htm=POST` while sending a GET:

~~~java
String wrongMethodProof = createDpopProof(
    clientKeyPairA,
    "POST",
    "https://api.example.test/api/orders",
    accessToken,
    null
);
~~~

Send that proof with a GET request and expect authentication to fail. Do not also change the key/token/nonce in the same test, which makes root-cause identification unclear.

### 17.3. Testing Nonce Challenges

Scenario:

1. Send a valid proof request without a nonce to a Resource Server that requires a nonce.
2. Check that the response includes `DPoP-Nonce` and a `use_dpop_nonce` challenge per contract.
3. Generate a new proof with a new `jti` and the `nonce` obtained from the response.
4. Resend the request with the new proof.
5. Confirm the request passes if the token/proof are otherwise valid.

Do not replay the same proof after the challenge. Nonce tests must verify client handling of the response, not just that the server returns a header.

### 17.4. Testing Two Nodes Sharing a Replay Store

~~~text
Request 1 → Resource Server node A → replay store → accept
Same proof → Resource Server node B → same replay store → reject
~~~

If node B accepts the same proof, replay detection is either local-only or the check/insert operation is not atomic. This is an essential test for clustered deployments.

### 17.5. Testing Authorization After DPoP Authentication

A valid DPoP proof only authenticates the token. Use a token with:

~~~text
aud = orders-api
cnf.jkt = JKT-A
scope = orders.create
~~~

with a GET request requiring `orders.read`. Expect authentication to succeed while HTTP authorization rejects (typically 403). This separates **invalid proof/token** from **valid token lacking permission**.

### 17.6. Testing That Bearer Scheme Fallback Is Disallowed

If a token is DPoP-bound and the endpoint requires DPoP:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <DPoP_BOUND_ACCESS_TOKEN>
~~~

with no proof header. The Resource Server must reject per policy; never accept merely because the JWT signature/claims are valid. This test ensures the sender constraint cannot be bypassed via a Bearer fallback path.

## 18. Replay Cache, Nonce Store, and Multi-Node Deployments

DPoP proofs are typically short-lived. To prevent a valid proof from being re-submitted, the Resource Server needs to record used `jti` values for the acceptance window.

### 18.1. Replay Keys

A replay record might use:

~~~text
replayKey = "dpop:" + jkt + ":" + jti
expiresAt = now + proofAcceptanceWindow
~~~

`jkt` namespaces by key; `jti` distinguishes individual proofs. There is no need to store the entire proof JWT or access token in the cache. Store only the minimal fingerprint/identifier needed for replay detection and troubleshooting.

### 18.2. Check-and-Set Must Be Atomic

Broken logic:

~~~text
if cache does not contain replayKey:
    cache.put(replayKey)
    accept
~~~

Two nodes can simultaneously observe "absent" before either writes, and both accept. You need an atomic primitive like `SET key value NX EX ttl` or an equivalent compare-and-insert operation in an appropriate datastore:

~~~text
insert replayKey if absent with TTL

insert succeeded → proof has not been used, proceed
insert failed    → proof replay, reject
~~~

The command names merely illustrate semantics; choosing Redis, a database, a cache cluster, or another store depends on your system. What matters is atomicity and TTL.

### 18.3. Replay Store Unavailable

If policy relies on a replay cache to enforce DPoP, an unavailable cache prevents the server from proving `jti` has not been used. Do not automatically skip the replay check and accept every proof.

Options to design up front:

- Fail closed for DPoP requests while the store is down.
- Use a highly available store with suitable consistency/atomic operations.
- Accept a controlled risk window only when explicitly approved by the threat model and security owner.

Never turn an infrastructure failure into a silent bypass.

### 18.4. Replay Entry TTL

The TTL must cover the period during which the server could accept a proof based on `iat` and clock skew. If proofs are accepted within a 60-second window, entries must remain at least long enough so an old proof cannot be replayed and slip through after the record expires.

For example:

~~~text
accepted proof iat = 12:00:00
server accepts until = 12:01:00
replay record expiry must not precede acceptance end
~~~

Do not set a 5-second TTL just because "DPoP proofs are short-lived" if the server still accepts 60-second-old proofs. TTL and freshness policies must be designed together.

### 18.5. Nonce Store and Nonce Scope

Nonces must be bound to the exact server/authority or context by design. Never share a single global nonce across:

- The Authorization Server token endpoint.
- The Orders API.
- The Payments API.
- Different issuers/tenants.

Nonces must be generated with sufficient randomness, be unpredictable, and have a defined lifecycle. If using one-time nonces, the server must record/consume them atomically; if using time/session-bounded nonces, define validation and refresh mechanics. Clients must store nonces per corresponding origin/authority.

### 18.6. Latency and Capacity

At high request volumes, each DPoP request may require one atomic write for replay detection. Estimate:

~~~text
replay write rate ≈ accepted DPoP request rate
retained entries ≈ accepted proof rate × replay TTL
~~~

For example, 5,000 DPoP requests/s with a 90-second TTL could retain around 450,000 replay records at any moment, excluding datastore overhead. This calculation is illustrative; real numbers depend on throughput and policy.

Do not optimize by turning off replay detection under load. Choose an appropriate store/partitioning/TTL, monitor latency and capacity, or shed load according to policy.

## 19. Operating DPoP: Metrics, Logging, and Incidents

DPoP introduces several new failure modes. Metrics must separate token validation from proof validation and replay detection.

### 19.1. Metrics to Monitor

| Metric | Meaning |
|---|---|
| `dpop_proof_validation_total` | Count of accepted/rejected proofs by reason |
| `dpop_proof_validation_duration_seconds` | Proof verification latency |
| `dpop_replay_detected_total` | Count of proofs flagged as replay |
| `dpop_nonce_challenge_total` | Number of times server requested a nonce |
| `dpop_nonce_validation_failed_total` | Missing/invalid/expired nonce |
| `dpop_jkt_mismatch_total` | Proof key does not match token binding |
| `dpop_ath_mismatch_total` | Proof not bound to the presented token |
| `dpop_replay_store_errors_total` | Replay datastore errors |
| `dpop_missing_header_total` | Missing DPoP proof header |
| `dpop_scheme_mismatch_total` | Bearer/DPoP scheme violates policy |

Use bounded labels such as API alias, issuer alias, outcome reason, and environment. Never use raw `jti`, raw JWK, tokens, subjects, or nonces as metric labels.

### 19.2. Structured Logs

Example safe log entries:

~~~text
event=dpop_validation result=accepted api=orders issuer=shop
event=dpop_validation result=rejected reason=htm_mismatch api=orders
event=dpop_validation result=rejected reason=jkt_mismatch api=orders
event=dpop_replay result=detected api=orders
event=dpop_nonce result=challenge api=orders
event=dpop_replay_store result=unavailable api=orders
~~~

Never log:

~~~text
Authorization: DPoP <full-access-token>
DPoP: <full-proof-jwt>
privateKey=...
nonce=<full-secret-nonce>
~~~

Although proof JWTs contain a public JWK, they are still security-sensitive data requiring control; access tokens and nonces can also be abused if leaked. Never enable full HTTP wire logging in production just to debug DPoP.

### 19.3. Incident Triage

| Signal | Likely Causes to Investigate |
|---|---|
| `invalid_dpop_proof` spike | Client signing wrong method/URI, key issues, clock drift, proof parser |
| `jkt mismatch` spike | Token and key paired incorrectly, key rotation / token mapping bug |
| `ath mismatch` spike | Token/proof mismatch, Authorization header rewritten, client bug |
| `htm/htu mismatch` spike | Proxy path rewrite, redirects, canonicalization |
| `use_dpop_nonce` spike | Nonce rotation/challenge policy or client failing to update nonce |
| Replay detected spike | Client reusing proofs, retry logic not regenerating proofs, or actual replay attack |
| Replay store errors | Datastore/cluster/network/capacity issues |
| DPoP token sent as Bearer | OAuth client lacks DPoP support or caches wrong token type |

A spike in replay detections does not automatically prove an attacker is present; HTTP clients can accidentally resend proofs during retries. Correlate request IDs, client versions, and retry behavior without logging tokens.

### 19.4. Clock Synchronization

`iat` and nonce freshness depend on time. Resource Server nodes with skewed clocks can produce inconsistent results for the same proof. Synchronize system clocks, monitor clock offset, and apply a uniform skew policy across nodes.

Do not set a huge freshness window to mask an NTP issue; that widens the replay window.

## 20. Common Implementation Mistakes

### 20.1. Verifying Only the Proof Signature

A valid proof signature is not enough. If `htm`, `htu`, `ath`, `jti`, or `cnf.jkt` is skipped, proofs can be reused on the wrong request or paired with another token.

### 20.2. Reusing One Proof Across Multiple Requests

A proof is tied to method/URI/iat/jti and token. Resending the same proof may be rejected by replay detection; sending it to a different URL/method must be rejected by claim validation. Generate a fresh proof for every transmission.

### 20.3. Omitting `ath` at the Resource Server

Without `ath`, the proof is not directly bound to the access token being presented. A client could accidentally or maliciously pair a proof from token A with token B. The Resource Server must check the hash per RFC.

### 20.4. Skipping the `cnf.jkt` Comparison

If the server verifies the signature solely against the JWK supplied in the proof, anyone can generate their own key pair and sign their own proof. You must compare the public JWK thumbprint against the issuer-verified binding inside the token.

### 20.5. Accepting `alg=none` or HMAC

DPoP relies on public/private keys. Never use unsigned or symmetric algorithms for proofs. Maintain an allowlist of appropriate algorithms and key types.

### 20.6. Skipping Replay Checks Because `jti` Is Already Unique

The client generating a unique `jti` does not mean the server automatically knows whether it has seen that ID before. The server needs a replay store and atomic check-and-set. Without state persistence or with isolated cluster caches, replayed proofs can be accepted multiple times.

### 20.7. Comparing `htu` Against the Internal URI

Gateway TLS termination/path rewriting can cause the backend to observe a different URL than the one the client signed. Configure external URI trust explicitly rather than blindly trusting forwarded headers.

### 20.8. Using an Old Nonce or a Nonce from the Wrong Server

An AS nonce is not automatically valid for a separate RS. Clients must store nonces per authority/context, update to the latest nonce, and generate a new proof after a challenge.

### 20.9. Falling Back from DPoP to Bearer

If a proof is invalid, never retry the same access token under the Bearer scheme to "rescue the request." That bypasses the sender constraint.

### 20.10. Dropping TLS

DPoP does not encrypt tokens/proofs, does not prevent all traffic interception, and does not replace TLS. Always use HTTPS with proper certificate validation.

### 20.11. Thinking DPoP Signs the Entire Request Body

Standard proofs bind specified claims such as method, URI, and access-token hash; they do not protect JSON bodies by default. Never claim DPoP replaces application payload signing.

### 20.12. Allowing Proof Keys to Contain Private Parameters

The `jwk` header must contain only the public JWK. If `d` or RSA private parameters appear, reject the request and investigate the client implementation; never write private material to logs.

### 20.13. Using a Local-Only Replay Cache in Multi-Node Systems

An attacker can send the same proof to another node if the cache is not shared. Use a clustered/shared atomic store or sticky routing with matching guarantees; sticky routing alone does not protect against replay during failover.

### 20.14. Running DPoP Middleware After Authorization

If an access token is treated as authenticated before the proof is verified, endpoints can unintentionally grant access. DPoP proof validation belongs at the authentication boundary, before the principal is trusted.

## 21. Migrating from Bearer to DPoP

A system running on Bearer tokens must not enable DPoP simply by changing header strings on the frontend. Coordination is required across the client, Authorization Server, and Resource Server.

### 21.1. Defining Rollout Phases

~~~text
Phase 0 — Baseline:
    Bearer access tokens
    existing JWT/introspection validation

Phase 1 — Capability:
    AS can issue DPoP-bound tokens
    clients can generate proofs
    RS can validate DPoP

Phase 2 — Controlled adoption:
    selected clients request DPoP tokens
    APIs accept DPoP scheme for bound tokens
    observe proof/replay/nonce metrics

Phase 3 — Policy enforcement:
    require DPoP for chosen clients/resources
    reject Bearer presentation of DPoP-bound tokens
    maintain explicit policy for legacy Bearer clients if needed
~~~

This is a reference rollout model. Supporting Bearer and DPoP concurrently requires separating token types and client policies, ensuring a DPoP-bound token can never be downgraded to Bearer.

### 21.2. Old Tokens Cannot Become DPoP-Bound via Client Code Alone

A Bearer token issued without `cnf.jkt` does not automatically become DPoP-bound when the client starts sending a proof header. The client must obtain a **new token** from an AS supporting DPoP binding. The Resource Server must read the binding from the verified token/issuer metadata.

### 21.3. Client Migration by Capability

A client may need to:

- Generate a key pair and store the key securely.
- Send a DPoP proof at the token endpoint.
- Handle `token_type=DPoP` and persist the token-to-key binding.
- Send the `Authorization: DPoP` scheme along with the proof header.
- Handle nonce challenges.
- Generate fresh proofs on retries.
- Refresh tokens using the matching bound key.

Do not merely add an interceptor that emits a `DPoP` header without checking the response token type or confirmation binding.

### 21.4. Resource Server Migration

The API must:

- Identify DPoP-bound tokens by token type/binding per contract.
- Parse the authorization scheme properly.
- Verify the token, proof, and thumbprint.
- Enable the replay cache and nonce policy if used.
- Verify reverse proxy/canonical URI handling.
- Confirm observability does not log credentials.
- Maintain separate tests for legacy Bearer and DPoP-bound paths.

### 21.5. Migrating API by API

DPoP does not have to be enabled across all microservices at once. You can start with sensitive APIs, controlled clients, and issuers with full support. However, token relay/downstream calls must be designed so bindings are not stripped as requests traverse other services.

### 21.6. Rollback

Rollback plans must account for already-issued tokens:

- Active DPoP-bound tokens still require the key/proof.
- Never allow those tokens over Bearer just to roll back client code.
- New tokens may be issued under the legacy mechanism if policy permits, while revoking/expiring old tokens per plan.
- Keep metrics to identify which clients have not yet migrated.

Rollback must never become a shortcut that removes sender constraints required by the organization.

## 22. Symptom-Based Troubleshooting Guide

### 22.1. AS Rejects Token Request Despite a Valid Grant

Check:

1. Does the token request include the `DPoP` header?
2. Is the proof `typ` equal to `dpop+jwt` and `alg` supported?
3. Is `htm` equal to POST?
4. Is `htu` the exact token endpoint URI, without query/fragment?
5. Is `iat` within the freshness window?
6. Has `jti` been used previously?
7. Is a nonce required, and did the client include the latest nonce?
8. Does the public JWK match the private key that signed the proof?

A valid proof does not guarantee the grant/client/resource is authorized; after proof validation, the AS still enforces its authorization policy.

### 22.2. Token Endpoint Repeatedly Returns `use_dpop_nonce`

Possible causes:

- The client is not saving `DPoP-Nonce` from the response.
- The client is resending the old proof instead of signing a new one.
- The nonce is stored under the wrong host or taken from another issuer.
- A reverse proxy causes the client to hit a different endpoint than the signed `htu`.
- The server issued a new nonce, yet the client continues sending the stale nonce.

Bound the number of retries and log the reason/request ID; never enter an infinite loop.

### 22.3. Resource Server Reports `invalid_dpop_proof`

Check claim by claim:

| Claim/header | Question |
|---|---|
| `typ` | Is it exactly `dpop+jwt`? |
| `alg` | Is it in the asymmetric allowlist? |
| `jwk` | Is it a valid public key with no private parameters? |
| Signature | Does it verify with the public JWK? |
| `htm` | Does it match the actual method? |
| `htu` | Does it match the normalized URI? |
| `iat` | Is it within the freshness window? |
| `jti` | Does it collide in the replay cache? |
| `ath` | Does it hash the exact access token? |
| `nonce` | Is it required and matching the server nonce? |
| `cnf.jkt` | Does it match the proof JWK thumbprint? |

Never enable full token/proof logging in production to troubleshoot errors.

### 22.4. Proof Signature Is Valid, but `jkt` Mismatches

Common causes:

- The client signed with private key B while the access token is bound to key A.
- The token cache stored the wrong key alias.
- Key rotation occurred while the client kept using an old token.
- The AS bound the token to a different thumbprint than the public JWK sent by the client.
- The server calculated the thumbprint inconsistently with RFC 7638 or used the wrong JWK members.

Compare key aliases and observable thumbprint fingerprints without printing private keys.

### 22.5. `ath` Mismatch

Verify whether the client hashed:

- The exact access token?
- Its ASCII bytes with SHA-256?
- Base64URL without padding?
- Did it accidentally hash the `DPoP `/`Bearer ` prefix?
- Did it use an old token in the proof while putting a refreshed token in the header?

If a proxy alters the Authorization header or the client retries after a token refresh, the proof must be regenerated for the token actually sent.

### 22.6. `htu` Mismatch After Deploying a Gateway

Compare:

~~~text
Client target URI
Public gateway URI
Forwarded scheme/host
Rewritten path
Backend request URI
DPoP verifier canonical URI
~~~

Trust forwarded metadata only from authenticated proxies. Run integration tests through the same gateway/path rewriting as production.

### 22.7. Sudden Spike in Replay Detections

Possible reasons:

- The HTTP client is retrying the exact same request object/headers.
- The gateway is retrying and forwarding the original proof verbatim.
- Middleware is caching proofs by URL.
- The client derives `jti` from a fixed timestamp.
- An actual replay attack.

Fix the client/gateway to generate a fresh proof on every attempt, while keeping replay detection enabled. Never disable the replay store just to lower the metric.

### 22.8. One Node Accepts, Another Node Rejects

Check:

- Node clocks.
- Shared/atomic replay store.
- Nonce state shared within the proper scope.
- Consistent trusted-proxy / URI canonicalization config.
- Consistent key/algorithm allowlists and token validation settings.
- Caches and issuer metadata.

DPoP across a cluster requires **the same trust policy**, not just the same code.

## 23. Practice Exercises

### Exercise 1 — Reading Both Headers Correctly

Given the request:

~~~http
GET /api/orders HTTP/1.1
Authorization: DPoP eyJ...
DPoP: eyJ...
~~~

The value in `Authorization` is the **DPoP-bound access token**; the value in `DPoP` is the **DPoP proof JWT**. Do not swap the two values.

### Exercise 2 — Token Request or API Request?

A proof has `htm=POST` and `htu=https://login.example.test/oauth2/token`, with no `ath`. This proof is appropriate for a **token endpoint request**. When calling the Resource Server with an access token, the proof must contain `ath` hashing the access token.

### Exercise 3 — Right or Wrong Proof Key?

~~~text
Access token cnf.jkt = JKT-A
Proof signature valid with JWK-B
thumbprint(JWK-B) = JKT-B
~~~

The Resource Server must reject due to **binding mismatch**, even though the proof signature is valid.

### Exercise 4 — Changing the Method

A client generates a proof with `htm=GET` but sends a POST request. The server must reject the proof. A valid signature alone must never be treated as sufficient.

### Exercise 5 — Query Parameters

For `GET https://api.example.test/orders?status=open`: the `htu` claim omits the query string. Both client and server must apply DPoP URI rules consistently.

### Exercise 6 — Replay

Send the same proof twice. The first request may succeed; the second must be caught as a replay if the proof was already used and remains within the replay window. Valid retries must create a new proof.

### Exercise 7 — Nonce Challenge

The server returns `DPoP-Nonce` and `use_dpop_nonce`. The client builds a new proof with that `nonce`, a new `jti`, and a new signature; it does not patch the old proof payload.

### Exercise 8 — API Scope

A valid DPoP token/proof carrying only `orders.create` calls a GET endpoint requiring `orders.read`. Authentication succeeds, authorization denies (typically 403).

### Exercise 9 — Bearer Fallback

A token has `cnf.jkt`, yet the client sends `Authorization: Bearer` with no proof. If policy requires DPoP, the server rejects; do not ignore the binding.

### Exercise 10 — Proxy

The client signs the public HTTPS URI while the backend sees an internal HTTP URI. Describe how a trusted gateway forwards the external URI securely and write an end-to-end proxy test proving `htu` matches.

## 24. Pre-Production Checklist

### 24.1. Authorization Server

- [ ] Supports DPoP per RFC 9449.
- [ ] Verifies proofs at the token endpoint.
- [ ] Requires `typ=dpop+jwt` and enforces an asymmetric algorithm allowlist.
- [ ] Verifies `htm`, `htu`, `iat`, `jti`, and `nonce` when applicable.
- [ ] Computes the thumbprint from the public JWK per RFC 7638.
- [ ] Binds the access token with `cnf.jkt` or equivalent metadata.
- [ ] Returns `token_type=DPoP` for DPoP-bound tokens.
- [ ] Has a clear policy for refresh tokens / key binding.
- [ ] Does not issue tokens if the grant/client/resource/scope is disallowed.

### 24.2. OAuth Client

- [ ] Generates and protects the private key.
- [ ] Includes only the public JWK in the proof header.
- [ ] Generates a fresh proof for every resource/token request.
- [ ] Uses accurate `htm`/`htu`.
- [ ] Includes `ath` for Resource Server proofs.
- [ ] Places `Authorization: DPoP` and `DPoP` headers in their proper positions.
- [ ] Handles `DPoP-Nonce` and `use_dpop_nonce`.
- [ ] Generates fresh proofs on retries/redirects.
- [ ] Persists the token ↔ key alias relationship.
- [ ] Handles key rotation / key loss / refresh tokens.
- [ ] Never logs access tokens, proofs, or private keys.

### 24.3. Resource Server

- [ ] Verifies access token issuer/signature/audience/time/scope.
- [ ] Reads confirmation binding from a trusted token/introspection response.
- [ ] Parses the `DPoP` scheme and `DPoP` header.
- [ ] Verifies proof type/algorithm/public JWK/signature.
- [ ] Checks `htm`, `htu`, `iat`, `ath`, and nonce.
- [ ] Compares the proof key thumbprint against `cnf.jkt`.
- [ ] Prevents replay using `jti` + an atomic store.
- [ ] Defines policy when the replay/nonce store is unavailable.
- [ ] Never falls back from invalid DPoP to Bearer.
- [ ] Creates `Authentication` only after all validation passes.
- [ ] Still enforces scopes/roles/tenant/owner checks afterward.

### 24.4. Infrastructure and Testing

- [ ] TLS is enabled and certificates are validated properly.
- [ ] Trusted proxies / URI reconstruction are configured.
- [ ] CORS allows the `DPoP` header and exposes `DPoP-Nonce` when needed.
- [ ] Gateway forwards both headers properly and does not log credentials.
- [ ] Replay cache operates atomically across multiple nodes.
- [ ] Clocks are synchronized across client/AS/RS within acceptable bounds.
- [ ] Positive/negative tests exist for token binding, method, URI, `ath`, nonce, and replay.
- [ ] Cross-node replay and gateway rewriting tests exist.
- [ ] Metrics separate token errors, proof errors, replay, and nonces.
- [ ] Key rotation and incident response have been rehearsed.

## 25. Conclusion

DPoP adds proof of key possession to how an OAuth client presents an access token. Both headers must be understood accurately:

~~~http
Authorization: DPoP <DPoP_BOUND_ACCESS_TOKEN>
DPoP: <SIGNED_PROOF_JWT>
~~~

`Authorization` carries the token bound by the issuer to a public key; `DPoP` carries a fresh proof signed with the corresponding private key for the current request.

A Resource Server should create an `Authentication` only when:

~~~text
Access token valid:
    issuer + signature/introspection + audience + time
    + scope/profile + cnf.jkt

DPoP proof valid:
    typ + asymmetric alg + public jwk + signature
    + htm + htu + iat + ath + jti/replay
    + nonce when required

Binding:
    thumbprint(proof.jwk) == access-token.cnf.jkt
~~~

Afterward, the API still enforces authorization by scope, role, tenant, and per-resource permissions. DPoP does not replace TLS, does not automatically protect private keys against XSS/malware, and does not sign the entire HTTP body. It provides a **sender constraint** for access tokens, reducing the chance that a stolen token can be used independently without the bound private key.

When integrating with Spring Security, verify your exact version and actual DPoP support. A standard JWT configuration should not be assumed to verify proofs. If a custom integration is required, scheme parsing, proof verification, thumbprint comparison, and replay/nonce checks must all occur inside the authentication pipeline before creating a principal.

## References

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Nimbus JOSE + JWT — Documentation](https://connect2id.com/products/nimbus-jose-jwt)
