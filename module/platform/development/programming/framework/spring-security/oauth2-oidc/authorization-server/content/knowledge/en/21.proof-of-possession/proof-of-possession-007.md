# Impact of DPoP on Refresh Tokens and Client Key Lifecycle

## Lesson Objectives

In the **DPoP** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson examines the relationship between **Demonstrating Proof of Possession (DPoP)**, **refresh tokens**, and the lifecycle of client-managed key pairs. The material is set in the context of designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server using **Spring Security**, **Spring Authorization Server**, and **Spring Boot**.

DPoP binds tokens to the client's public key. The client must prove possession of the corresponding private key when requesting tokens or calling a Resource Server. Consequently, the private key's lifecycle directly affects the continued usability of access tokens and refresh tokens. In particular, RFC 9449 specifies different rules for **public clients** versus **confidential clients** when refresh tokens are issued.

After this lesson, you will be able to:

- Explain DPoP proof JWTs, public keys, private keys, and the `cnf.jkt` thumbprint.
- Distinguish DPoP keys from client authentication credentials, Authorization Server signing keys, and PKCE verifiers.
- Describe refresh token requests with a `DPoP` header and why public clients must reuse the exact key bound to the refresh token.
- Distinguish refresh token rules for public clients from confidential clients per RFC 9449 Section 5.
- Plan creation, storage, backup, rotation, revocation, and recovery of DPoP keys per device/client installation.
- Understand the impact of refresh token rotation, replay detection, lost keys, and key compromise.
- Integrate DPoP with the appropriate versions of Spring Authorization Server/Spring Security and validate access tokens at the Resource Server.
- Build a test matrix covering key continuity, key rotation, refresh token reuse, nonces, multiple devices, and security failures.

> **Running Scenario:** A native app `employee-mobile` uses Authorization Code + PKCE and DPoP. When exchanging the authorization code, the client sends a proof signed by the app installation's private key. The Authorization Server issues a DPoP-bound access token and, if policy permits, a refresh token. Months later, the app needs to rotate its key or the user loses their device. The system must decide which tokens remain usable and when to require user re-authentication.

## 1. How Does DPoP Bind Tokens to the Client's Key?

DPoP is an application-layer sender-constraining mechanism per **RFC 9449**. The client generates an asymmetric key pair and uses the private key to sign a **DPoP proof JWT** for each HTTP request. The public key is carried inside the proof's JOSE header as a public JWK.

The Authorization Server verifies the proof at the Token Endpoint. When valid, the server can bind the access token to that public key. Later, the Resource Server requires the client to send the access token alongside a fresh proof for the current request; stealing the access token string alone is insufficient to use the token.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>C: Create DPoP proof using private key K1
    C->>AS: Token request + DPoP header (public K1)
    AS->>AS: Verify proof, compute JWK thumbprint
    AS->>AS: Bind access token to thumbprint K1
    AS-->>C: access_token + token_type=DPoP
    C->>C: Create new proof for API request
    C->>RS: Authorization: DPoP token + DPoP proof
    RS->>RS: Check signature, htm, htu, jti, ath, and cnf.jkt
    RS-->>C: Allow if all checks pass
~~~

Differences from Bearer tokens:

| Bearer token | DPoP-bound access token |
|---|---|
| Any party holding the token can attempt to use it. | The caller must also prove possession of the bound private key. |
| Requests typically send `Authorization: Bearer <token>`. | Requests send `Authorization: DPoP <token>` and a `DPoP` header carrying a fresh proof. |
| No application-layer proof of possession. | Proof is signed and bound to method, URI, timestamp, and token hash when calling a Resource Server. |
| A leaked token can be replayed within its lifetime and scope. | A standalone leaked token is difficult to abuse without the private key. |

**DPoP is not a client authentication method.** It proves possession of a private key for a request. Confidential clients must still authenticate using their registered method such as `client_secret_basic`, `private_key_jwt`, or mTLS. DPoP can be combined with these methods.

### 1.1. Which Key Pair Belongs to the Client?

This lesson distinguishes three key groups:

| Key | Held by | Purpose |
|---|---|---|
| **DPoP client key** | Client/device | Signs proof JWTs; binds access tokens and, for public clients, refresh tokens. |
| **Authorization Server signing key** | Authorization Server/KMS/HSM | Signs JWT access tokens, ID Tokens, or AS-issued artifacts. |
| **Client authentication key/secret** | Confidential client | Authenticates the client to the Token Endpoint, e.g., `private_key_jwt` or shared secret. |

A client may use distinct private keys for DPoP and `private_key_jwt`. Separating the two purposes aids rotation, auditing, and limiting compromise blast radius. Never send the DPoP private key to the Authorization Server; proofs contain only the public JWK.

**A DPoP key is also not a PKCE verifier.** PKCE protects the authorization code exchange; DPoP binds tokens to a key. An Authorization Code + PKCE flow can use both PKCE and DPoP simultaneously.

## 2. DPoP Proof JWT Structure

Every HTTP request requires a new proof. The proof's JOSE header must include:

- `typ` equal to `dpop+jwt`.
- `alg` set to an accepted asymmetric signature algorithm; never `none` or symmetric MAC algorithms.
- `jwk` containing the client's **public key**, with no private key material.

The payload contains core claims:

| Claim | Meaning |
|---|---|
| `jti` | Unique ID for the proof, supporting replay detection. |
| `htm` | HTTP method of the request, e.g., `POST` or `GET`. |
| `htu` | HTTP target URI of the request, excluding query and fragment. |
| `iat` | Time the proof was created. |
| `nonce` | Present when the server requires a nonce and the client must embed the latest nonce in the proof. |
| `ath` | Access token hash; required when the proof accompanies an access token on a Protected Resource request. |

Abbreviated structural example:

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
.
{
  "jti": "a-unique-random-proof-id",
  "htm": "POST",
  "htu": "https://auth.example.com/oauth2/token",
  "iat": 1794859200
}
~~~

Values in the example are placeholders. The proof is signed with the private key corresponding to the public JWK in the header. The server must verify signature, proof type, algorithm, URI, method, timestamp, nonce if applicable, and replay.

### 2.1. Why Do Token Endpoint Proofs Differ from API Call Proofs?

When refreshing a token at the Token Endpoint, the request does not present an access token to access a Resource Server. Therefore, a refresh request proof **does not need `ath`**. The proof must still include `htm`, `htu`, `iat`, `jti`, and `nonce` if required by the server.

When calling an API with a DPoP-bound access token, the proof must include `ath` equal to `Base64URL(SHA-256(ASCII(access_token)))`. The Resource Server verifies that this hash matches the access token in the Authorization header and that the public key in the proof matches the token's binding.

Never reuse one proof across multiple requests. `jti` must have negligible collision probability; servers can store seen proof markers for a period to prevent replays.

### 2.2. DPoP Nonces

The Authorization Server or Resource Server may send a `DPoP-Nonce` header to require the client to include that nonce in the next proof. If receiving a `use_dpop_nonce` error with a fresh nonce, the client must:

1. Read the nonce from the response header.
2. Create a new proof JWT and sign it with the corresponding private key.
3. Embed the new nonce into the `nonce` claim.
4. Generate a fresh `jti` and fresh `iat`.
5. Resend the request per the server's retry rules.

Never resend the exact old proof simply because a nonce was missing. The nonce is part of the proof and must be signed.

## 3. How Does DPoP Affect Refresh Tokens?

Refresh tokens allow a client to obtain a new access token after the current access token expires without repeating the full authorization flow. With DPoP, you must distinguish **public clients** from **confidential clients**.

### 3.1. Public Clients: Refresh Tokens Bind to the DPoP Key

Per RFC 9449 Section 5, when an Authorization Server issues a refresh token to a **public client** that sent a valid DPoP proof to the Token Endpoint, that refresh token **MUST be bound to the public key in the proof**. Whenever the refresh token is used, the server **MUST verify the binding**. The client must send a proof signed by the **same private key** used when obtaining the refresh token.

In other words, a public client cannot simply keep the refresh token and arbitrarily switch to a new DPoP key. A refresh token is a long-lived credential bound to the key from initial issuance.

### 3.2. Confidential Clients: Refresh Tokens Are Bound via Client Authentication

RFC 9449 specifies that refresh tokens issued to **confidential clients** are not bound directly to the DPoP proof public key. The reason: the refresh token is already sender-constrained through client identity and requires the confidential client to re-authenticate when using the refresh token.

This allows a confidential client to switch DPoP keys when obtaining a new access token, provided the client still authenticates validly via its registered method and the server accepts the new proof. The new access token will be bound to the DPoP key in that request's proof.

| Subject | Refresh Token Binding | Which Key Must Be Used on Refresh? |
|---|---|---|
| Public client issued a DPoP-bound refresh token | Bound to the DPoP public key sent when acquiring the refresh token. | **Must use the exact same DPoP key** every time that refresh token is used. |
| Confidential client | Bound to the client via OAuth2 client authentication. | Must authenticate the client; the DPoP proof can use a new key to bind the new access token. |
| Public client receives a refresh token while access token response has `token_type=Bearer` | The refresh token may still be DPoP-bound if the server issued it to a public client with a valid proof. | Still must use the same key to refresh. |

**Do not confuse the access token's token type with refresh token binding.** `token_type=Bearer` indicates the access token in that response is not DPoP-bound. It does not by itself prove that the public client's refresh token lacks DPoP binding.

### 3.3. Does Spring Authorization Server Always Issue Refresh Tokens to Public Clients?

No. RFC 9449 defines how binding works **when the server issues a refresh token**; it does not require every public client to receive refresh tokens. Spring Authorization Server 1.5.8 documentation on configuring an SPA public client explicitly guides against issuing refresh tokens to public clients and recommends the Backend for Frontend (BFF) pattern where appropriate.

Therefore, when designing your system, clarify:

- Is the client public or confidential?
- Do server grants and policies permit refresh tokens?
- Does the server support DPoP proofs at the Token Endpoint?
- If refresh tokens are issued to public clients, are same-key binding and verification fully implemented?
- If refresh tokens are not issued, the client must re-run the authorization flow when the access token expires by design.

Do not assume that merely adding a `DPoP` header causes a public client to receive refresh tokens by default.

## 4. How Must Refresh Requests Use DPoP Proofs?

Example of a public client sending a refresh token bound to key `K1`:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
DPoP: <FRESH_PROOF_SIGNED_WITH_K1>

grant_type=refresh_token&
client_id=employee-mobile&
refresh_token=<REFRESH_TOKEN_BOUND_TO_K1>
~~~

`<FRESH_PROOF_SIGNED_WITH_K1>` is a new proof signed with private key K1. Every refresh must generate a new `jti`. If the Authorization Server has supplied `DPoP-Nonce`, the proof must include that nonce.

If the client sends a proof with key K2 while the refresh token is bound to K1, the Authorization Server must reject the request with the appropriate policy/token error. Never silently migrate the refresh token's binding to K2 merely because the new proof has a valid signature.

### 4.1. Confidential Client Combining DPoP

A confidential client must still perform client authentication. Illustrative example:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Authorization: Basic <CLIENT_AUTHENTICATION>
Content-Type: application/x-www-form-urlencoded
DPoP: <FRESH_PROOF_SIGNED_WITH_CURRENT_DPOP_KEY>

grant_type=refresh_token&
refresh_token=<REFRESH_TOKEN>
~~~

`<CLIENT_AUTHENTICATION>` represents the registered client authentication method, not the DPoP proof. When rotating DPoP keys, a confidential client still needs valid authentication credentials. If using `private_key_jwt` or mTLS, rotating client authentication credentials is a separate process.

### 4.2. Response and Key Binding

If the Authorization Server issues a DPoP-bound access token, the response sets `token_type` to `DPoP`:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "access_token": "<NEW_DPOP_BOUND_ACCESS_TOKEN>",
  "token_type": "DPoP",
  "expires_in": 300,
  "refresh_token": "<ROTATED_REFRESH_TOKEN>"
}
~~~

`refresh_token` is present only if the grant and policy actually issue/rotate it. For public clients, the new refresh token in the rotation chain remains bound to the same DPoP key per RFC requirements. Never treat the server returning a new refresh token as a sign that key binding has changed.

### 4.3. Where Is Binding Stored?

For JWT access tokens, the public key thumbprint is expressed in the claim:

~~~json
{
  "iss": "https://auth.example.com",
  "aud": "inventory-api",
  "exp": 1794861000,
  "cnf": {
    "jkt": "BASE64URL_JWK_SHA256_THUMBPRINT"
  }
}
~~~

`cnf.jkt` is the JWK SHA-256 thumbprint of the DPoP public key. For opaque access tokens, the Resource Server can obtain the corresponding binding via the Token Introspection response.

**Refresh token binding is not required to sit inside the refresh token string as a JWT or public claim.** The RFC leaves how refresh token binding is stored to the Authorization Server; the server can store the thumbprint or corresponding metadata in authorization/token state. Do not decode refresh tokens to infer keys unless the format explicitly specifies it.

## 5. Client-Side DPoP Key Lifecycle

The DPoP key is part of a client installation's security state. If the key is lost, the client can lose the ability to use currently bound access tokens and refresh tokens tied to that key.

### 5.1. Generating Keys per Installation

For public native clients, generate a dedicated key per installation or security context per product policy:

- Generate keys with a CSPRNG/secure platform API; use an asymmetric signature algorithm supported by the server.
- Prefer hardware-backed/non-exportable keys when supported by the platform and compatible with UX.
- Isolate keys per application/installation to limit compromise scope and cross-app correlation.
- Do not share one DPoP key across all devices belonging to the same user.
- Store public key metadata or thumbprint alongside the client-side session/authorization record so the client knows which token belongs to which key.
- Private keys must never be sent to the Authorization Server, Resource Server, analytics, or logging services.

A user with a phone and a tablet can have two separate authorization sessions, two DPoP keys, and two refresh tokens. Do not copy refresh tokens from one device to another if the corresponding private key is not managed inside the same security boundary.

### 5.2. Persisting the Private Key Safely

| Platform | Appropriate Storage | Notes |
|---|---|---|
| Android | Android Keystore, preferring hardware-backed when available. | Store key alias/metadata; do not export private keys unnecessarily. |
| iOS/iPadOS | Secure Enclave/Keychain per key type and API capability. | Bind access controls, device passcode/biometrics per UX. |
| Browser SPA | Web Crypto API with non-extractable `CryptoKey` when appropriate. | XSS can still invoke signing in runtime; DPoP does not replace XSS defenses. |
| CLI/Desktop | OS credential store, TPM/keystore, or encrypted file with tight permissions. | Never leave private keys in repos, publicly synced home folders, or command history. |
| Backend service | KMS/HSM or IAM-controlled secret/key store. | Separate DPoP keys from the Authorization Server's JWT signing keys. |

If an application keeps DPoP keys only in memory and regenerates them on each restart, a public client's refresh token becomes unusable after restart because the new key has a different thumbprint. Keys must persist at least as long as the client needs the tokens bound to them.

### 5.3. Keys and Refresh Tokens Must Be Persisted Consistently

The client needs to persist a recoverable state bundle:

| Data | Purpose |
|---|---|
| Private DPoP key handle | Creates proofs for active access tokens/refresh tokens. |
| Public JWK/thumbprint | Identifies binding and aids state debugging without exposing the private key. |
| Access token + expiry | Calls Resource Servers and schedules refreshes. |
| Refresh token + expiry/metadata | Requests new access tokens if grant/policy allows. |
| Per-server DPoP nonce | Builds subsequent proofs when AS/RS requires a nonce. |
| Issuer/client/authorization session ID | Avoids mixing up keys/tokens across multiple issuers or installations. |

Persist updated refresh tokens **durably immediately after a successful refresh**. If the server rotated the refresh token but the client crashed before writing the new token, the old refresh token may already be invalidated. Clients must handle lost responses with a safe recovery strategy rather than retrying indefinitely with the stale token.

## 6. Rotating DPoP Keys in Public Clients

This is the area with the most direct impact on refresh tokens.

Suppose a public client holds a refresh token `RT1` bound to key `K1`. Later, the client wants to switch to key `K2`.

### 6.1. Cannot Switch Proofs to a New Key and Keep Using the Old Refresh Token

~~~mermaid
sequenceDiagram
    participant C as Public Client
    participant AS as Authorization Server
    Note over C,AS: RT1 is bound to K1
    C->>AS: POST refresh_token + proof(K1)
    AS-->>C: new access token, RT2 still bound to K1
    Note over C: Client generates K2 but keeps RT2
    C->>AS: POST refresh_token + proof(K2)
    AS-->>C: Rejected due to binding mismatch
~~~

When the client replaces K1 with K2:
- Access tokens DPoP-bound to K1 cannot be used with K2 proofs.
- Public-client refresh tokens bound to K1 must continue being proven with K1.
- The server has no obligation to transfer RT1/RT2 binding to K2.
- RFC 9449 defines no standard endpoint for a client to "rebind" a refresh token to a new public key.

If K1 and the refresh token are still valid, the client can keep using the old session with K1 during a transition period. To use K2, it must establish a new authorization session via a supported flow, send a K2 DPoP proof, and obtain a new token set bound to K2. Once the new session works, the client can revoke the old authorization/refresh token per policy.

### 6.2. Proactive Rotation Workflow

1. **Generate K2:** create the new key and store it safely before replacing the current key.
2. **Initiate new authorization:** run Authorization Code + PKCE (or suitable grant) with a DPoP proof signed by K2.
3. **Receive new token set:** verify `token_type`/binding; if the public client receives a refresh token, confirm the new session belongs to K2.
4. **Persist new state:** durably store tokens, key handle, and K2 thumbprint.
5. **Switch traffic:** new requests use the K2 access token and K2 proof; never pair K1 tokens with K2 proofs.
6. **Revoke old session:** revoke the old RT/authorization once migration succeeds and per policy.
7. **Delete K1:** delete the old private key only when no valid tokens/sessions depend on it and rollback is no longer needed.

If the client cannot run two sessions concurrently, design a clean transition window and clear re-authentication UX. Never delete K1 before verifying the new K2 session works.

### 6.3. Rotation Due to Expiry or Algorithm Deprecation

DPoP keys are typically application keys and do not necessarily carry certificates like mTLS. Still, platforms may require key replacement due to deprecated algorithms, hardware changes, or new cryptographic policies. Treat these scenarios as key replacement: establish a new authorization/token set rather than assuming a public-client refresh token can migrate its binding automatically.

## 7. DPoP Key Lifecycle in Confidential Clients

Confidential clients have an additional sender-constraining mechanism through client authentication. Per RFC 9449, refresh tokens issued to confidential clients are bound to the client authentication mechanism rather than directly to the DPoP proof public key.

This creates a difference when rotating DPoP keys:

| Component | When a confidential client changes DPoP keys |
|---|---|
| Refresh token | Still belongs to the client via OAuth2 client authentication. |
| Client authentication credential | Must remain valid; if also rotated, handle via separate registration/overlap procedures. |
| Old access tokens | Remain bound to the old DPoP key until expiry or revocation. |
| Subsequent refresh request | Can use a DPoP proof signed by the new key if the AS accepts it; the new access token is bound to the new proof key. |
| Resource Server | Must verify each token against its exact thumbprint; never accept new-key proofs for old tokens. |

Example: backend `billing-service` uses `client_secret_basic` for authentication and DPoP key K1 for access tokens. When rotating to K2, the backend still sends the refresh token with valid client authentication while generating the DPoP proof with K2. If the AS supports and accepts it, the new access token is bound to K2. Old access tokens still require K1 proofs until they expire or are revoked.

### 7.1. Separate Rotation of DPoP Keys and Client Authentication

Do not bundle the following operations into a single change:

- Rotating the DPoP signing key.
- Rotating `client_secret`.
- Rotating the key used for `private_key_jwt`.
- Replacing the client certificate for mTLS.
- Replacing the Authorization Server signing key.

Each has different verifiers, metadata, and token impacts. If rotating simultaneously, plan overlap/rollback separately for each mechanism and test every combination.

## 8. Integration with Spring Authorization Server and Spring Security

**Spring Authorization Server 1.5.8** documentation includes a DPoP-bound Access Tokens section under Protocol Endpoints. Token requests to the Token Endpoint can carry a `DPoP` header; once the proof is valid, the Authorization Server binds the access token to the proof's public key. Responses use `token_type=DPoP` when the access token is DPoP-bound.

Spring Security Resource Server provides dedicated documentation on verifying DPoP-bound access tokens. Cross-check your running dependency versions because DPoP support, configuration APIs, and client integration capabilities vary across Spring Security/Spring Authorization Server lines.

### 8.1. Requests at the Token Endpoint

Protocol-level refresh request example:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
DPoP: <PROOF_SIGNED_BY_THE_REQUIRED_CLIENT_KEY>

grant_type=refresh_token&
refresh_token=<REFRESH_TOKEN>
~~~

For public clients, if the refresh token is DPoP-bound, the proof must use the same key. For confidential clients, the request must still include client authentication per registration. Token Endpoint proofs set `htu` to the public token endpoint URI and `htm=POST`; do not add `ath` to this refresh request.

### 8.2. Example Creating a Token Endpoint Proof with Spring Security JOSE

The snippet illustrates a client creating a proof JWT using `NimbusJwtEncoder`. `clientDpopJwk` is a JWK **held by the client**, with its private key in a keystore/secure storage. Never place this JWK on the Authorization Server and never put the private key in the proof header.

~~~java
import java.time.Instant;
import java.util.UUID;

import com.nimbusds.jose.jwk.ECKey;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

final class DpopProofFactory {

    private final ECKey clientDpopJwk;
    private final JwtEncoder jwtEncoder;

    DpopProofFactory(ECKey clientDpopJwk) {
        this.clientDpopJwk = clientDpopJwk;

        JWKSource<SecurityContext> keySource =
                (selector, context) ->
                        selector.select(new JWKSet(clientDpopJwk));

        this.jwtEncoder = new NimbusJwtEncoder(keySource);
    }

    String createTokenEndpointProof(
            String publicTokenEndpointUri,
            String nonce) {

        JwsHeader jwsHeader = JwsHeader
                .with(SignatureAlgorithm.ES256)
                .type("dpop+jwt")
                .jwk(clientDpopJwk.toPublicJWK().toJSONObject())
                .build();

        JwtClaimsSet.Builder claims = JwtClaimsSet.builder()
                .issuedAt(Instant.now())
                .claim("htm", "POST")
                .claim("htu", publicTokenEndpointUri)
                .id(UUID.randomUUID().toString());

        if (nonce != null && !nonce.isBlank()) {
            claims.claim("nonce", nonce);
        }

        return jwtEncoder.encode(
                JwtEncoderParameters.from(jwsHeader, claims.build())
        ).getTokenValue();
    }
}
~~~

Notes for this **Token Endpoint** proof example:
- `publicTokenEndpointUri` must be the public HTTPS URL the client actually calls, without query or fragment.
- `clientDpopJwk` must contain the private key for signing, while the JOSE header includes only `toPublicJWK()`.
- A fresh `jti` is generated per request; never cache or reuse proofs.
- Include `nonce` only when required or returned by the server.
- Restrict algorithms, protect the key source, synchronize clocks, and handle exceptions/nonce retries.
- The example uses ES256/P-256; actual algorithms must be among the DPoP algorithms advertised/accepted by the Authorization Server.

Do not use this snippet as an Authorization Server configuration. This is **client-side** code for signing proofs. Proof validation, refresh token binding persistence, and access token issuance must be performed by a DPoP-capable Authorization Server.

### 8.3. Resource Server Access Token Verification

When calling an API, the client sends:

~~~http
GET /api/inventory HTTP/1.1
Host: inventory-api.example.com
Authorization: DPoP <DPOP_BOUND_ACCESS_TOKEN>
DPoP: <FRESH_PROOF_WITH_ATH>
~~~

Here the proof must contain `ath` as the SHA-256 hash of the access token. The Resource Server verifies:
- Proof signature and public JWK.
- `typ=dpop+jwt` and allowed asymmetric `alg`.
- `htm`, `htu`, `iat`, `jti`, and nonce when applicable.
- `ath` matches the sent access token.
- Public key thumbprint of the proof matches `cnf.jkt` in the JWT access token or binding in the introspection response.
- Access token is unexpired, has valid issuer/audience/scope, and is authorized for the resource.

A DPoP proof does not replace business authorization checks. Having a valid proof does not mean the client is authorized to call every API.

### 8.4. Version-Specific Checks

| Component | Implementation Questions |
|---|---|
| Spring Authorization Server | Does your version support DPoP at the Token Endpoint? Does it verify proofs on refresh requests? |
| Refresh token provider | For public clients receiving RTs, how does the server store and verify DPoP key bindings? |
| Registered client policy | Are public clients issued refresh tokens? If yes, what are the conditions and TTL? |
| Spring Security Resource Server | Does it support the DPoP authentication scheme and verify `ath`/`cnf.jkt`? |
| Client SDK | Does it generate a unique proof per request, handle nonces, and use the right key on refresh? |
| Gateway/proxy | Does the public URL used for `htu` match the URL the server checks? |

Do not manually add a custom `cnf.jkt` claim to a JWT and treat that as full DPoP support. You need proof verification, replay protection, refresh token binding (if applicable), and Resource Server validation.

## 9. Refresh Token Rotation, Replay, and Concurrency

DPoP key binding and refresh token rotation solve two related but distinct problems:

- **DPoP binding:** a public client's refresh token can only be used when the client proves possession of the matching private key.
- **Refresh token rotation:** each refresh can issue a new token and invalidate the previous one per policy, helping detect reuse/replay.

A system can deploy both. For public clients, the newly rotated refresh token must remain bound to the token chain's DPoP key. Rotating the refresh token does not mean changing the key binding.

### 9.1. Updating the Refresh Token After Every Rotation

If the server configures rotation, the client must:
1. Allow only one refresh operation per authorization session at a time.
2. Send the current refresh token alongside a DPoP proof signed by the matching key.
3. Receive the response and verify access token/token type/expiry.
4. Persist the new refresh token durably before marking the request complete.
5. Update expiry/nonce metadata from the response.
6. Never reuse the old refresh token once the server has rotated it.

If multiple threads refresh the same token simultaneously, one request may succeed while the other triggers reuse/replay detection. Clients should serialize refreshes using a per-session/token-family single-flight/lock and avoid parallel retries.

### 9.2. DPoP Does Not Replace Replay Protection

The server must detect DPoP proof replays via `jti` within an appropriate time window. Refresh token rotation detects refresh token reuse across an authorization/token family. Both mechanisms should be tested independently.

| Scenario | Required Protection |
|---|---|
| Attacker steals only the access token | DPoP proof and key binding block token use without the private key. |
| Attacker steals only the public-client refresh token | DPoP refresh-token binding requires the corresponding private key. |
| Attacker steals the DPoP private key | Binding no longer stops an attacker who can sign proofs; revoke and reauthorize. |
| Captured proof replayed | `jti`, timestamp validity, nonce/replay cache, and request binding. |
| Old refresh token reused after rotation | Server enforces replay/reuse detection and token-family revocation policy. |
| Two concurrent refresh requests | Client serialization and server-side atomic state updates. |

## 10. Lost Keys, Damaged Devices, and Key Compromise

### 10.1. Client Loses the Private Key

For a public client with a DPoP-bound refresh token:
- The client cannot generate proofs with that key and therefore cannot refresh.
- Still-unexpired DPoP-bound access tokens are also unusable if proofs cannot be signed.
- There is no standard way to derive or re-download the private key from the Authorization Server.
- The client must initiate a new authorization, generate a new key, and obtain a new token set.
- The Authorization Server may need to revoke the old refresh token/authorization if state remains.

If the client has a secure key backup and can restore the exact key material, the old session may continue per policy. However, backups increase key-copying risk; evaluate encryption, device binding, access control, and revocation capabilities.

### 10.2. DPoP Key Exposure

If an attacker obtains both the private key and tokens, DPoP cannot stop the attacker from creating valid proofs. Handle it as a credential incident:

1. Mark the affected key/session compromised in the client.
2. Stop using the old key and generate a new key in secure storage.
3. Revoke the corresponding refresh token/authorization at the AS if an endpoint/workflow exists.
4. Assess issued access tokens; offline-verified JWTs may remain valid until `exp` without centralized revocation.
5. Apply revocation/denylist/introspection or shorten TTLs per architecture to shrink the exposure window.
6. Perform a fresh authorization with a clean key.
7. Audit logs, devices, malware, backups, and the scope of potentially accessed data.

Never merely swap the DPoP key on the client and keep using the old public-client refresh token; the server must verify binding and reject mismatched keys.

### 10.3. Key Expiry by Policy or Algorithm Deprecation

DPoP keys typically lack their own expiry claim like access tokens. However, an organization may set a maximum key age under cryptographic policy. When due:
- Generate a new key before retiring the old key.
- Public clients must establish a new authorization session/token set if the refresh token is bound to the old key.
- Confidential clients can use the refresh token with client authentication and a new proof key if supported by the server.
- Keep the old key only long enough for old tokens/sessions or revoke them as planned.
- Never allow a policy-expired key to keep signing proofs with algorithms the server no longer accepts.

## 11. Testing DPoP and the Refresh Token Lifecycle

Testing a single access token acquisition is insufficient. Verify behavior across multiple refresh cycles and key lifecycle transitions.

### 11.1. Public Client Matrix

| Scenario | Expected Result |
|---|---|
| Public client sends K1 proof and receives refresh token | AS stores RT binding to public key K1 per RFC 9449. |
| Refresh RT with valid K1 proof | AS verifies binding and can issue a new access token. |
| Refresh RT with K2 proof | Rejected; does not migrate binding to K2. |
| Proof has bad signature or missing required claim | Rejected with appropriate DPoP error, e.g., `invalid_dpop_proof`. |
| Proof carries already-used `jti` | Replay detected within server's check window. |
| Server returns `DPoP-Nonce` | Client creates a new proof with the nonce and a fresh `jti`. |
| Refresh token rotates | New refresh token remains bound to K1; old token cannot be reused per policy. |
| Client restarts | Reloads exact private key K1 and continues refreshing successfully. |
| Client loses K1 | Cannot refresh; requires new authorization or secure key recovery. |
| Client proactively switches K1 to K2 | Requires new authorization/token set for K2; old RT still requires K1. |

### 11.2. Confidential Client Matrix

| Scenario | Expected Result |
|---|---|
| Confidential client authenticates validly and sends DPoP proof K1 | Access token can be bound to K1. |
| Refresh token issued to confidential client | RT is sender-constrained via client authentication per RFC 9449, not directly bound to DPoP key K1. |
| Refresh with valid client auth and K2 proof | AS can issue a new access token bound to K2 if policy/version supports it. |
| Invalid client secret/`private_key_jwt` credential | Client authentication rejected, even if DPoP proof is valid. |
| DPoP key changes while client auth remains valid | Old access tokens require K1; new access tokens can use K2. |
| Client authentication credential rotates | Handled via separate registration and credential overlap, independent of DPoP key rotation. |

### 11.3. Resource Server Testing

- Send a DPoP-bound token with a matching-key proof and valid `ath`: request allowed if scope/authorization are valid.
- Send token with a proof from another key: reject.
- Send a DPoP-bound token using `Authorization: Bearer`: do not treat as valid DPoP proof.
- Missing `ath` or mismatched `ath`: reject.
- `htm` or `htu` does not match request: reject.
- Stale proof, replayed `jti`, or wrong nonce: reject.
- Token has wrong issuer/audience/expiry/scope: reject even if proof is valid.

### 11.4. Integration and Persistence Testing

1. Create an authorization for a public client with key K1.
2. Obtain access token/refresh token per policy.
3. Restart client and reload K1 from secure storage.
4. Refresh successfully with K1; verify token rotation if enabled.
5. Attempt a K2 proof with the old refresh token and confirm rejection.
6. Create a new authorization with K2; verify the new access token.
7. Run two concurrent refresh requests to test replay/atomicity.
8. Restart/scale out the Authorization Server; verify refresh token binding is read consistently across instances.
9. Simulate server nonces and retry with a fresh proof.
10. Revoke the old session and check access/refresh tokens per policy.

## 12. Common Errors and Diagnostics

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Valid refresh token fails after key change | Public-client refresh token is bound to the old key. | Reuse the old key or perform a new authorization with the new key. |
| Token Endpoint returns `invalid_dpop_proof` | Invalid proof signature, `alg`, `typ`, `htm`, `htu`, `iat`, `jti`, or nonce. | Inspect proof generator, public URL, clocks, and nonce. |
| Resource Server returns 401 for new access token | DPoP proof key mismatches `cnf.jkt` or `ath` is wrong. | Check thumbprint, token hash, and fresh proof. |
| Client reuses proof after timeout | Old proof may be flagged as replay or outside time window. | Generate a fresh proof with a new `jti`; handle grant request idempotency separately. |
| Refresh token becomes invalid after app crash | Server rotated before client saved the new refresh token. | Persist token responses durably, serialize refreshes, and plan recovery/reauthorization. |
| Public client does not receive a refresh token | Server policy does not issue RTs to public clients. | Check grant/registration/version; do not assume DPoP grants RTs automatically. |
| Confidential client rejected despite valid proof | Client authentication failed or registration mismatch. | Verify secret/`private_key_jwt`/mTLS independently of DPoP. |
| Proof breaks behind a reverse proxy | `htu` constructed from internal URL or bad proxy rewrite. | Use consistent public HTTPS URIs and configure trusted proxy headers. |
| Client loses key after reinstall | Key was not in persistent secure storage or wiped with app data. | Design key lifecycle/backup; plan reauthorization when keys are lost. |
| Refresh token triggers reuse detection | Two threads used the same token or client retried a rotated token. | Serialize refreshes, persist new tokens atomically, handle races. |
| DPoP fails to stop attacker after XSS | Malicious code can invoke private-key signing in the client context. | Prevent XSS, enforce CSP, maintain dependency hygiene, minimize token exposure; DPoP does not replace runtime protection. |

## 13. Hands-On Exercise

**Context:** `employee-mobile` is a public native client using Authorization Code + PKCE, DPoP, and refresh tokens per custom policy. Each installation has one DPoP key. A user switches phones after three months and wants to continue their login session without lowering security.

Requirements:

1. Design key storage for Android/iOS, generate a per-installation key, and persist the key handle durably.
2. Execute Authorization Code + PKCE, send a DPoP proof to the Token Endpoint, and check `token_type`/binding.
3. Determine whether the server issues refresh tokens to public clients; if so, document the binding per RFC 9449.
4. Make a refresh request with the same key, handling `DPoP-Nonce` and refresh token rotation.
5. Attempt a refresh using a new key K2 with a K1-bound refresh token; verify server rejection.
6. Perform a new authorization with K2, obtain a new token set, and migrate traffic.
7. Revoke the K1 session/refresh token once migration completes.
8. Simulate private key loss and key compromise; write a reauthorization/revocation runbook.
9. Test the Resource Server with `Authorization: DPoP`, `ath`, `cnf.jkt`, and nonces.
10. Test app restarts, reinstalls, backup/restore, multiple devices, and two concurrent refresh requests.

**Completion criteria:** the client knows which key owns each refresh token, never sends the wrong key, refresh rotation never drops state, new keys establish new sessions for public clients, and the AS/Resource Server properly enforce DPoP bindings.

## 14. Pre-Deployment Checklist

- [ ] Distinguished DPoP keys from AS signing keys, client authentication keys, and PKCE verifiers.
- [ ] Proof JWT has `typ=dpop+jwt`, asymmetric `alg`, public `jwk`, `jti`, `htm`, `htu`, and `iat`.
- [ ] Private keys are never sent in proofs, headers, logs, or telemetry.
- [ ] Token Endpoint proofs omit `ath`; Resource Server proofs include `ath` matching the access token.
- [ ] Client uses `Authorization: DPoP` for DPoP-bound access tokens.
- [ ] Resource Server verifies `cnf.jkt`/introspection binding, proof key, token hash, and claims.
- [ ] Distinguished public-client RT binding from confidential-client sender-constraining via client authentication.
- [ ] Public clients issued RTs retain the exact DPoP key for every refresh.
- [ ] Do not assume Spring Authorization Server issues refresh tokens to public clients by default.
- [ ] Refresh token rotation and DPoP binding are tested together.
- [ ] Client has secure storage and key persistence across restarts.
- [ ] Multi-device setups use separate keys/sessions per policy.
- [ ] Public-client key rotation defines new authorization, token cutover, and old session revocation.
- [ ] Confidential clients decouple DPoP key rotation from client credential rotation.
- [ ] Procedures exist for lost keys, compromise, revocation, reauthorization, and recovery.
- [ ] Nonces, `jti` replay detection, clock skew, and reverse-proxy `htu` are tested.
- [ ] Refresh operations are serialized; new tokens are persisted durably immediately after response.
- [ ] Logs/traces contain no private keys, refresh tokens, access tokens, or raw proof JWTs.

## Summary

DPoP ties the refresh token lifecycle to the client type. When an Authorization Server issues a refresh token to a **public client** alongside a valid DPoP proof, RFC 9449 requires binding the refresh token to that public key and verifying the same key on every refresh. Consequently, losing or changing the DPoP key renders old refresh tokens unusable; public clients must protect keys securely or perform a fresh authorization to obtain a token set bound to the new key.

For **confidential clients**, refresh tokens are sender-constrained via client authentication rather than bound directly to the DPoP proof key. The client must still authenticate using its registered credentials, but can switch DPoP keys for new access tokens if supported by the server. Regardless of client type, DPoP does not replace TLS, client authentication, PKCE, refresh-token rotation, replay protection, or Resource Server authorization checks.

## References

1. [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): DPoP proof JWT, token endpoint, public-client refresh token binding, confidential-client exception, nonce, key thumbprint, and protected resource access.
2. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): DPoP-bound access token requests and Token Endpoint.
3. [Spring Security 7.1 — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html): proof generation, `cnf.jkt`, `ath`, and Resource Server validation.
4. [Spring Authorization Server 1.5.8 — Authenticate using a Single Page Application with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): public client configuration and guidance against issuing refresh tokens to SPA public clients.
5. [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638.html): computing JWK SHA-256 thumbprints.
6. [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): JOSE headers and JWT signatures.
7. [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): public/private key representation.
8. [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): refresh token grant and client authentication.
9. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): refresh token protection, rotation, and replay detection.
