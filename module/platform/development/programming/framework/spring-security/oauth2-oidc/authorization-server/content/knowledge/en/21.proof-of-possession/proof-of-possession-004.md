# Binding an Access Token to a Key with `cnf.jkt`

## 1. Objective and Real-World Scenario

In the **DPoP** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson explains how the Authorization Server binds an Access Token to a public key whose possession the client proves, via the **cnf.jkt** claim. This material supports **designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application**.

With a standard Bearer Access Token, any party that obtains the token can attempt to use it until it expires or is revoked. If the token is leaked through logs, browser storage, a lost device, or an intermediary proxy, an attacker can replay the token without proving they are the original client.

**DPoP (Demonstrating Proof of Possession)** adds an application-layer proof at the HTTP level. The client generates a key pair, keeps the private key, and sends a DPoP Proof JWT signed with that key. When issuing an Access Token, the Authorization Server extracts the public key from the proof, computes the JWK SHA-256 Thumbprint, and embeds the result into the token:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-8f2a91",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "cnf": {
    "jkt": "CQMknzRoZ5YUi7vS58jck1q8TmZT8wiIiXrCN1Ny4VU"
  }
}
~~~

When the client calls the Orders API, it must send both the Access Token and a new DPoP Proof. The Resource Server verifies the proof, computes the thumbprint of the public key inside the proof, and compares it against **cnf.jkt** in the Access Token. It also checks that the proof is bound to the exact Access Token being sent.

After this lesson, you will be able to:

1. Explain the role of the **cnf.jkt** claim and the **cnf** structure in an Access Token.
2. Compute a JWK thumbprint per RFC 7638 and understand why the thumbprint is not the hash of the entire proof JWT.
3. Distinguish a DPoP Proof sent to the Token Endpoint from a proof sent to a Resource Server.
4. Describe how Spring Authorization Server binds a public key to an Access Token.
5. Configure a Resource Server to verify DPoP-bound Access Tokens and test mismatched key, invalid `ath`, replay, and nonce cases.
6. Understand the limitations of DPoP, private key lifecycle, replay caches, and multi-instance operations.

## 2. What Problem Does DPoP Solve?

### 2.1. Bearer Tokens vs. Sender-Constrained Tokens

A Bearer Token has one defining property: **anyone holding the token can present it**. The Resource Server cannot tell from the Bearer Token string alone whether the sender is the original client.

DPoP produces a **sender-constrained Access Token**. At issuance, the Authorization Server binds the token to the client's public key. At usage time, the client must sign a fresh proof with the corresponding private key.

| Characteristic | Bearer Access Token | DPoP-Bound Access Token |
| --- | --- | --- |
| How token is presented | Authorization: Bearer | Authorization: DPoP |
| Additional proof | Not required | DPoP Proof JWT in the DPoP header |
| Binding to client | Whoever holds the token can use it | Requires both the token and the corresponding private key |
| Confirmation claim in JWT | `cnf.jkt` not required | `cnf.jkt` holds the public key thumbprint |
| Resistance to standalone token theft | Limited | Reduces token usability as long as the private key stays safe |
| Resource Server requirements | Verify token per profile | Verify token, proof, `ath`, and key binding |

DPoP is an **application-layer** sender-constraining mechanism. It does not replace HTTPS, does not encrypt JWT payloads, and does not by itself protect the private key from malicious code running inside the same client context.

### 2.2. Actors and Artifacts in a Transaction

- **Client:** generates or manages the key pair; retains the private key and never sends it to the server.
- **DPoP Proof:** short-lived JWT signed with the private key; carries the public JWK in its JOSE header.
- **Authorization Server:** verifies the proof at the Token Endpoint, extracts the public key, and binds the Access Token to that key.
- **Access Token:** the issued token; if JWT, it contains `cnf.jkt`.
- **Resource Server:** verifies both the Access Token and proof on every DPoP-protected request.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server
    Note over C: Generate key pair, keep private key
    C->>AS: POST /oauth2/token + DPoP Proof
    AS->>AS: Verify proof signature, htm, htu, iat, jti
    AS->>AS: Compute JWK thumbprint (SHA-256)
    AS->>AS: Embed cnf.jkt in Access Token
    AS-->>C: Access Token, token_type=DPoP
    Note over C: Generate new proof for API request
    C->>RS: Authorization: DPoP token + DPoP proof (ath)
    RS->>RS: Validate Access Token
    RS->>RS: Verify proof, ath, and cnf.jkt
    RS-->>C: Return resource if all conditions are valid
~~~

**Key takeaway:** The DPoP Proof during token acquisition proves the client holds the private key at issuance time. The `cnf.jkt` claim stores the link to that public key so the Resource Server can verify subsequent requests.

## 3. What Does the `cnf.jkt` Claim Mean?

RFC 9449 defines the public key confirmation method named **jkt** (*JWK SHA-256 Thumbprint confirmation method*) used inside the **cnf** (*confirmation*) claim. For a JWT Access Token:

~~~json
{
  "cnf": {
    "jkt": "CQMknzRoZ5YUi7vS58jck1q8TmZT8wiIiXrCN1Ny4VU"
  }
}
~~~

- **cnf** is an object holding confirmation information about the key or token-binding mechanism.
- **jkt** is the base64url-encoded SHA-256 JWK Thumbprint per RFC 7638.
- The referenced public key is the public key inside the verified DPoP Proof's JWK.
- **`cnf.jkt` does not contain the private key, is not the full JWK, and is not the hash of the DPoP Proof JWT.**

### 3.1. Why Store Only the Thumbprint?

The Access Token does not need to embed the entire public JWK for the Resource Server to verify binding. The client sends the public JWK inside the proof on every API call. The Resource Server computes the thumbprint of that JWK and compares it against the value signed by the Authorization Server inside the Access Token.

This enables:

1. The token carries a short, stable identifier for the public key.
2. The Resource Server does not need to fetch a public key from a client-specified URL.
3. Key comparison follows uniform canonicalization rules per RFC 7638.
4. A stolen token alone is insufficient to craft a valid proof without the private key.

### 3.2. `cnf.jkt` Is None of the Following

| Commonly confused value | Why it is incorrect |
| --- | --- |
| Hash of the entire DPoP JWT | The proof changes on every request; the token must bind to a stable key |
| Hash of the private key | The private key is never sent to the server; the thumbprint is computed from the public JWK |
| JWK `kid` | `kid` is an issuer-chosen key identifier, not an RFC 7638 JWK Thumbprint |
| Hash of the Access Token | The Access Token hash inside a Resource Server DPoP Proof is the `ath` claim, serving a different purpose |
| Client ID | Client ID identifies the application, not possession of a private key |
| TLS certificate thumbprint | That is a separate certificate-bound token mechanism, typically related to RFC 8705 |

## 4. Computing the JWK SHA-256 Thumbprint per RFC 7638

DPoP uses the **JWK Thumbprint** to identify a public key. RFC 7638 specifies how to build a canonical JSON representation from the required members of the JWK and hash it with SHA-256.

Overview of the process:

1. Extract the public JWK from the JOSE header of the DPoP Proof.
2. Identify the key type and the required member set for that key type.
3. Construct canonical JSON containing only the required members, with member names sorted lexicographically.
4. Encode the JSON as UTF-8.
5. Compute SHA-256 over the UTF-8 bytes.
6. Base64url-encode the result without padding.

~~~mermaid
flowchart TD
    A["Public JWK in DPoP Proof"] --> B["Select required members by kty"]
    B --> C["Sort member names lexicographically"]
    C --> D["Serialize canonical JSON, UTF-8"]
    D --> E["SHA-256"]
    E --> F["Base64url, strip = padding"]
    F --> G["cnf.jkt"]
~~~

### 4.1. Example with an RSA Public JWK

An RSA public JWK may include multiple attributes such as:

~~~json
{
  "kty": "RSA",
  "n": "0vx7agoebGcQSuuPiLJXZptN9nndrQmb...",
  "e": "AQAB",
  "kid": "client-key-2026",
  "alg": "RS256",
  "use": "sig"
}
~~~

For RSA, the required members for computing the thumbprint are **e**, **kty**, and **n**. The canonical JSON takes the illustrative form:

~~~json
{"e":"AQAB","kty":"RSA","n":"0vx7agoebGcQSuuPiLJXZptN9nndrQmb..."}
~~~

The **kid**, **alg**, and **use** fields do not participate in the RSA thumbprint calculation per RFC 7638. The `n` value in the example is truncated for illustration and cannot be used to compute an actual thumbprint.

### 4.2. Other JWK Types

| Key type | Required members for thumbprint calculation |
| --- | --- |
| RSA | `e`, `kty`, `n` |
| EC | `crv`, `kty`, `x`, `y` |
| OKP | `crv`, `kty`, `x` |

Never arbitrarily include extra members in the canonical JSON. If two parties include **kid** or **alg** in the hash input, the output will diverge from RFC 7638 and key binding will break interoperability.

### 4.3. Distinguishing the Thumbprint from the Proof Signature

The DPoP Proof JWT is signed with the private key. The signature proves the proof creator holds the private key. The thumbprint is computed from the public JWK and attached to the Access Token. These two operations serve distinct roles:

- **JWS signature:** verifies the proof was signed by the private key corresponding to the public JWK.
- **JWK thumbprint:** creates a stable identifier for the public JWK to bind the token.

A thumbprint cannot replace a signature. An attacker can compute a thumbprint for their own public key, but without an Access Token bound to that thumbprint, the Resource Server will reject the request.

## 5. DPoP Proof JWT: Header and Claims

A DPoP Proof is a JWT sent in the **DPoP** HTTP header. Per RFC 9449, the JOSE header must include these core fields:

| Header | Requirement | Meaning |
| --- | --- | --- |
| `typ` | Must be `dpop+jwt` | Identifies the JWT as a DPoP Proof |
| `alg` | Supported asymmetric signature algorithm; never `none` or MAC | Proves possession of the private key |
| `jwk` | Public JWK | Key to verify the signature; must not contain private key material |

Core claims in the proof:

| Claim | Meaning |
| --- | --- |
| `htm` | HTTP method of the request |
| `htu` | Target HTTP URI; ignore query and fragment when comparing per RFC |
| `iat` | Time the proof was created |
| `jti` | Unique ID of the proof |
| `ath` | Hash of the Access Token, required when the proof accompanies an Access Token to a Resource Server |
| `nonce` | Nonce supplied by the Authorization Server or Resource Server, if required by the server |

Example header and payload of a proof at the Token Endpoint:

~~~json
{
  "header": {
    "typ": "dpop+jwt",
    "alg": "ES256",
    "jwk": {
      "kty": "EC",
      "crv": "P-256",
      "x": "public-x-coordinate",
      "y": "public-y-coordinate"
    }
  },
  "payload": {
    "htm": "POST",
    "htu": "https://auth.example.com/oauth2/token",
    "iat": 1794823200,
    "jti": "proof-id-unique-001"
  }
}
~~~

This is an illustrative structure; the JWK coordinates are not real public keys. A proof at the Token Endpoint usually does not require the **ath** claim because an Access Token is not yet being presented to a Resource Server. If the server supplies a nonce, the proof must include the corresponding nonce.

### 5.1. Never Include the Private Key in the JWK Header

The JWK in the proof contains only public components. For RSA, never send private fields such as **d**, **p**, **q**, **dp**, **dq**, **qi**, or **oth**. For EC, never send the private scalar **d**. If a private key is placed in the request, the client leaks DPoP's most critical credential.

### 5.2. Each Request Needs a Fresh Proof

A proof needs a fresh `jti` and appropriate `iat` for each request. Never reuse a single proof JWT across multiple HTTP requests. If a client retries, it must generate a new proof with the proper method/`URI`/`iat`/`jti`; never merely resend the old JWT.

## 6. Binding an Access Token at the Token Endpoint

To receive a DPoP-bound Access Token, the client sends a DPoP Proof in the **DPoP** header alongside the token request:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
DPoP: <signed-dpop-proof-jwt>

grant_type=authorization_code&
client_id=orders-bff&
code=<authorization-code>&
redirect_uri=https%3A%2F%2Fportal.example.com%2Fcallback&
code_verifier=<pkce-verifier>
~~~

The example uses Authorization Code; RFC 9449 allows DPoP to apply to other Access Token requests such as Refresh Token or Client Credentials if the server supports the corresponding flows.

The Authorization Server must:

1. Read a single `DPoP` header and parse the proof JWT.
2. Verify `typ` is `dpop+jwt`.
3. Verify `alg` is an allowed asymmetric algorithm.
4. Verify the JWK contains only a public key.
5. Verify the signature using the public JWK in the proof.
6. Compare `htm` with the HTTP method and `htu` with the Token Endpoint URI.
7. Verify `iat` is within the accepted time window; track `jti` to detect replay.
8. Verify `nonce` if required by the server.
9. Only after the proof is valid, bind the verified public key to the issued token.

When issuing a JWT Access Token, the Authorization Server puts the thumbprint of the public JWK into the claim:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-8f2a91",
  "aud": ["orders-api"],
  "iat": 1794823200,
  "exp": 1794823800,
  "scope": "orders.read",
  "cnf": {
    "jkt": "CQMknzRoZ5YUi7vS58jck1q8TmZT8wiIiXrCN1Ny4VU"
  }
}
~~~

The token response indicates the token type:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "<dpop-bound-access-token>",
  "token_type": "DPoP",
  "expires_in": 600,
  "scope": "orders.read"
}
~~~

**token_type=DPoP** informs the client that the Access Token is bound to the DPoP key. The client must store the Access Token together with a reference to the private key used to generate the proof. Never send this token using the Bearer scheme expecting the Resource Server to infer the key.

## 7. Spring Authorization Server and `cnf.jkt`

The Spring Authorization Server **1.5.x** release line documents DPoP-bound Access Tokens. When a valid DPoP Proof is processed at the Token Endpoint, the proof's public key is bound to the Access Token. The **OAuth2TokenContext.DPOP_PROOF_KEY** API exists starting in version 1.5 to expose the key used for the DPoP Proof JWT, if present.

This has two implications:

- For framework-supported DPoP flows, **you do not need to invent a `cnf.jkt`** by reading a raw public key from the request and adding it manually to the JWT.
- When writing a custom token generator or customizer, preserve the binding information the framework puts into the context; do not overwrite or erase the generated `cnf` object.

### 7.1. Why Should You Not Manually Add `cnf.jkt` from `client_id` or Parameters?

Code such as the following is insecure:

~~~java
claims.put("cnf", Map.of("jkt", request.getParameter("jkt")));
~~~

A client could submit an arbitrary string as `jkt`. If the Authorization Server signs that string without verifying the proof and computing the thumbprint from the validated public JWK, the token becomes bound to a value with no proof of possession.

Similarly, never use:

- `client_id` as `jkt`.
- The JWK's `kid` as `jkt`.
- The hash of the DPoP Proof JWT as `jkt`.
- The thumbprint of a key submitted by the client in a form parameter rather than inside a verified proof.

### 7.2. Checking the Token Context When Customizing

`OAuth2TokenContext` has the **DPOP_PROOF_KEY** attribute, describing the key used for the DPoP Proof JWT if present. This is a useful extension point when building a custom integration following your version's API. However, applications should prefer the framework's built-in DPoP mechanism and only read the context attribute when strictly necessary.

Do not add a generic customizer that overwrites the `cnf` claim for all token types. If you need to add other claims, modify only your application-specific claims and preserve `cnf.jkt` generated by the verified DPoP mechanism.

### 7.3. Checking Versions

Current Spring Authorization Server documentation includes a section on DPoP-bound Access Tokens; the `OAuth2TokenContext.DPOP_PROOF_KEY` API is marked as available since 1.5. For projects on older versions, do not assume this API or behavior exists. Inspect your actual dependencies, consult version-matched documentation, and run Token Endpoint integration tests before enabling DPoP in production.

## 8. How Does the Resource Server Verify `cnf.jkt`?

When the client calls an API, the request must include:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.com
Authorization: DPoP <dpop-bound-access-token>
DPoP: <fresh-signed-dpop-proof-jwt>
~~~

The proof sent to the Resource Server must contain the **ath** claim:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.com/api/orders",
  "ath": "fUHyO2r2Z3DZ53EsNrWBb0xWXoaNy59IiKCAqksmQEo",
  "iat": 1794823260,
  "jti": "proof-id-for-this-resource-request"
}
~~~

`ath` is computed as follows:

~~~text
ath = BASE64URL-NOPAD(SHA-256(ASCII(access_token_value)))
~~~

The Resource Server must perform these checks:

1. Verify the Access Token via JWT or introspection: issuer, signature, expiry, audience, scope, and status.
2. Verify the DPoP Proof JWT: `typ`, `alg`, public JWK, signature, `htm`, `htu`, `iat`, and `jti`.
3. Compute the SHA-256 thumbprint of the public JWK in the proof per RFC 7638.
4. Compare the computed thumbprint against **cnf.jkt** in the Access Token or introspection response.
5. Compute the hash of the Access Token and compare it with the **ath** claim in the proof.
6. Verify the nonce if the Resource Server issued one.
7. Verify the proof `jti` has not been used within the replay protection window.

Only when all required checks pass does the Resource Server accept the token for the request.

### 8.1. Why Are Both `cnf.jkt` and `ath` Needed?

These two values protect two distinct links:

| Value | What does it prove? |
| --- | --- |
| `cnf.jkt` | The proof's public key is the exact key bound to the Access Token at issuance |
| `ath` | The current proof was created for the exact Access Token present in the Authorization header |

If only `cnf.jkt` were checked, a valid proof from the same key could be mismatched with a different token bound to that same key. The `ath` claim binds the proof to the specific Access Token value.

### 8.2. `DPoP` Scheme Instead of `Bearer` Scheme

For a DPoP-bound Access Token, the client sends:

~~~http
Authorization: DPoP <access-token>
DPoP: <proof-jwt>
~~~

Do not send:

~~~http
Authorization: Bearer <dpop-bound-access-token>
~~~

The Resource Server must distinguish DPoP-bound tokens from Bearer tokens. If a token carrying `cnf.jkt` is presented with the Bearer scheme, never ignore the confirmation claim and accept it as an ordinary Bearer Token.

## 9. Opaque Access Tokens and Introspection

Not all Access Tokens are JWTs. If an Access Token is opaque, the Resource Server cannot read the `cnf.jkt` claim by decoding the token. RFC 9449 allows the Authorization Server to return key-binding metadata in the **Token Introspection Response**.

Example response:

~~~json
{
  "active": true,
  "sub": "user-8f2a91",
  "iss": "https://auth.example.com",
  "scope": "orders.read",
  "token_type": "DPoP",
  "cnf": {
    "jkt": "CQMknzRoZ5YUi7vS58jck1q8TmZT8wiIiXrCN1Ny4VU"
  }
}
~~~

The Resource Server retrieves `cnf.jkt` from introspection and compares it locally against the proof public key's thumbprint. The Resource Server **does not send the DPoP proof in the introspection request**; the Authorization Server returns binding metadata for the Resource Server to validate locally.

If the `token_type` field is present in the introspection response for a DPoP-bound token, RFC 9449 requires its value to be **DPoP**. Introspection caching must be carefully designed so active/binding state is not cached longer than revocation policy allows.

## 10. Configuring a Resource Server with Spring Security

Spring Security documents support for DPoP-bound Access Tokens. In the **Spring Security 7.1.x** release line, the Resource Server can enable DPoP via **dPoP(...)** on the OAuth2 Resource Server configurer.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class OrdersResourceServerConfiguration {

    @Bean
    SecurityFilterChain ordersApiSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/orders/**").hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults())
                .dPoP(Customizer.withDefaults())
            );

        return http.build();
    }
}
~~~

This is a skeleton configuration for Spring Security 7.1.x; the application must still configure issuer/JWK or `JwtDecoder`, audience validation, scope mapping, and other authorization rules. The **dPoP** method was added per that version's API; when using 6.x or another version, consult the documentation for that exact version and verify DPoP is actually enforced. Do not rely solely on the application starting without errors.

### 10.1. `JwtDecoder` Still Needs to Verify Issuer and Audience

Enabling DPoP does not replace standard JWT validations. The Resource Server must still verify:

- Signature using trusted JWKs.
- Exact issuer.
- Audience containing the current API.
- `exp` and `nbf` per clock policy.
- Scope/authority appropriate for the endpoint.
- `cnf.jkt` and DPoP Proof binding.

DPoP proves possession of the key bound to the token; it does **not** prove the token is authorized to call every API.

### 10.2. Do Not Write a Custom Filter That Only Compares `jkt` Strings

A custom filter that merely compares `jkt` values without verifying the DPoP Proof signature, `htm`, `htu`, `iat`, `jti`, `ath`, and nonce is insufficient. Use the built-in DPoP mechanism of your Spring Security version or build a complete RFC 9449 implementation with independent tests.

## 11. Nonce and Replay Protection

### 11.1. `jti` Alone Does Not Prevent Replay

Every proof has its own `jti`. However, the mere presence of a `jti` claim does not automatically prevent a proof from being replayed. The server must store or check received `jti` values within an appropriate time window to detect repeated proofs.

~~~mermaid
flowchart TD
    A["Receive DPoP Proof"] --> B["Verify signature and claims"]
    B --> C["Read jti + proof iat"]
    C --> D{"jti already seen in replay window?"}
    D -->|Yes| E["Reject replayed proof"]
    D -->|No| F["Record jti in replay cache"]
    F --> G["Continue checking ath, cnf.jkt, nonce"]
    G --> H["Allow request if all conditions are valid"]
~~~

In multi-instance systems, the replay cache must be shared or use a mechanism ensuring a request cannot be independently validated on multiple nodes. A per-JVM in-memory cache can allow the same proof to be accepted on two different nodes.

### 11.2. Nonce Challenge

The Authorization Server or Resource Server may return the **DPoP-Nonce** header to require the client to include a fresh nonce in its next proof. Nonces help the server enforce proof recency and reduce the risk of pre-generated proofs being replayed later.

Example response requiring a nonce:

~~~http
HTTP/1.1 401 Unauthorized
DPoP-Nonce: server-nonce-value
WWW-Authenticate: DPoP error="use_dpop_nonce"
Cache-Control: no-store
~~~

The client creates a new proof and adds the claim:

~~~json
{
  "htm": "GET",
  "htu": "https://api.example.com/api/orders",
  "ath": "fUHyO2r2Z3DZ53EsNrWBb0xWXoaNy59IiKCAqksmQEo",
  "iat": 1794823265,
  "jti": "new-proof-id",
  "nonce": "server-nonce-value"
}
~~~

If the server provides a nonce, the proof must carry an appropriate nonce. Clients should not reuse a nonce indefinitely; track fresh nonces per server and handle challenges/retries properly.

### 11.3. `iat` Window and Clock Skew

The server must bound proof age using `iat` or a nonce mechanism. Too wide a window increases the duration a proof can be replayed; too narrow a window causes failures due to clock skew and network latency. Synchronize clocks, measure latency, and configure sensible windows across client, Authorization Server, and Resource Server.

## 12. Binding an Authorization Code to a DPoP Key

RFC 9449 also defines the **dpop_jkt** parameter in the Authorization Request to bind the Authorization Code to a DPoP public key right from the code request step.

In the Authorization Code Flow:

1. The client generates a key pair and computes the JWK thumbprint.
2. The client sends `dpop_jkt` in the Authorization Request.
3. The Authorization Server associates the issued code with that thumbprint.
4. When exchanging the code at the Token Endpoint, the client sends a DPoP Proof signed by the same private key.
5. The Authorization Server verifies that the proof's thumbprint matches the stored `dpop_jkt`; if different, reject.
6. The Access Token is issued and continues carrying `cnf.jkt`.

This binding helps reduce the risk of a stolen code being exchanged using a different key. It complements PKCE; **`dpop_jkt` does not replace `code_challenge`/`code_verifier`**.

~~~text
Authorization Request:
    code_challenge=...
    code_challenge_method=S256
    dpop_jkt=<JWK thumbprint>

Token Request:
    code=...
    code_verifier=...
    DPoP: <proof signed by the same key>
~~~

This is an optional capability in RFC 9449. Use it only if both your Authorization Server and client library support the profile properly; do not simply append `dpop_jkt` and assume the server bound the code.

## 13. Key Lifecycle and Private Key Storage

DPoP is only effective if the private key is protected. Design a key lifecycle tailored to each client type:

| Client | Key storage to consider | Primary risks |
| --- | --- | --- |
| Native/mobile app | Keystore/Keychain or hardware-backed key when available | Rooted/jailbroken device, insecure backups, malware |
| SPA | Web Crypto and appropriate runtime protection policies | XSS or in-origin malicious code can request signing proofs |
| Backend/BFF | Secret manager, HSM, or keystore with least privilege | Host compromise, logs, memory dumps, or overly broad service permissions |
| CLI/desktop | OS credential store or hardware key | Config files, backups, other processes reading the private key |

### 13.1. Do Not Share One Private Key Across Unrelated Clients

Each client or security principal should have its own key per trust boundary. If multiple applications share a private key, key compromise in one application affects all others and blurs accountability.

### 13.2. Key Rotation

Already-issued Access Tokens remain bound to the old thumbprint. When a client rotates its private key:

- Still-valid tokens do not automatically migrate to the new key.
- The client cannot alter `cnf.jkt` inside a token.
- It must request a new token through an allowed flow with a proof signed by the new key, or use a well-defined re-binding mechanism.
- Old tokens/refresh tokens must be revoked or allowed to expire per policy.

Never automatically accept any new key merely because the client still sends the same `client_id`.

### 13.3. DPoP Does Not Protect If Both Token and Private Key Are Compromised

If an attacker obtains both the Access Token and private key, they can generate valid proofs. DPoP reduces the value of a standalone leaked token; it does not replace device security, XSS defenses, secret management, or anomalous behavior monitoring.

## 14. Security Limitations to Understand

1. **Does not replace TLS:** DPoP does not encrypt HTTP requests/responses. Always use HTTPS.
2. **Does not sign the entire request body:** proofs bind method and URI, not general body content signing.
3. **Does not stop malware in the client context:** malicious code can ask the client environment to sign proofs if it controls the runtime.
4. **Cannot save a stolen private key:** an attacker holding both token and private key can create fresh proofs.
5. **Does not revoke tokens automatically:** `cnf.jkt` only binds the key; revocation/introspection remain separate policies.
6. **Does not replace authorization:** the Resource Server must still check audience, scope, tenant, and resource permissions.
7. **Does not prevent all replays automatically:** you must validate `jti`, `iat`, nonces, and use a replay cache.
8. **Not equivalent to mTLS:** DPoP operates at the application layer; certificate-bound tokens per RFC 8705 are a separate mechanism.

## 15. Testing `cnf.jkt` and the DPoP Flow

A test suite must verify **both issuance and protected resource access**. Seeing `cnf.jkt` in a payload alone does not prove the Resource Server actually enforces key binding.

### 15.1. Test Matrix

| # | Scenario | Expected Result |
| --- | --- | --- |
| 1 | Token request with valid DPoP proof | Issues `token_type` DPoP bound to the right key |
| 2 | Issued JWT Access Token | Contains `cnf.jkt` matching thumbprint of proof public JWK |
| 3 | Token request without DPoP proof when client/flow requires DPoP | Rejected per policy |
| 4 | Proof with `typ` other than `dpop+jwt` | Reject |
| 5 | Proof using `alg=none` or symmetric algorithm | Reject |
| 6 | JWK header contains private key | Reject |
| 7 | Invalid proof signature | Reject |
| 8 | `htm` or `htu` does not match request | Reject |
| 9 | Proof `iat` too old or future beyond window | Reject |
| 10 | Replayed proof `jti` | Reject within replay window |
| 11 | Access Token presented with proof from a different key | Reject due to `cnf.jkt` mismatch |
| 12 | `ath` does not hash the exact sent Access Token | Reject |
| 13 | DPoP token sent with Bearer scheme | Do not accept as Bearer token |
| 14 | Server requires nonce but proof lacks valid nonce | Reject and require a new proof |
| 15 | Opaque token introspection returns `cnf.jkt` | Resource Server verifies binding from metadata |
| 16 | JWT has right key but wrong issuer/audience/scope | Reject per normal OAuth2 validation |
| 17 | Two nodes receive the same proof `jti` concurrently | Shared replay protection permits at most one valid request per policy |
| 18 | Client rotates key but keeps using token bound to old key | Reject proofs signed by new key with old token |

### 15.2. Verifying the Thumbprint of an Issued Token

In an integration test:

1. Generate a test key pair.
2. Create a DPoP Proof JWT with the public JWK.
3. Send a Token Request with the `DPoP` header.
4. Receive the Access Token.
5. Decode and **verify the signature** of the JWT Access Token using the Authorization Server's public key.
6. Read `cnf.jkt`.
7. Compute the JWK Thumbprint from the client's public JWK per RFC 7638.
8. Assert the two values are equal.

Do not merely decode the JWT and assert against a hardcoded string. The test must prove the Authorization Server bound the exact key from the actual proof.

### 15.3. Resource Server Testing

Send the same DPoP-bound Access Token across scenarios:

- Proof signed by the right private key, valid `htm`/`htu`/`ath`, fresh `jti` → request authenticated.
- Proof signed by a different key → reject.
- Proof with right key but `ath` from a different token → reject.
- Proof with right key but mismatched `htu`/`htm` → reject.
- Replay an old proof → reject per replay policy.
- Missing `DPoP` header → reject DPoP-bound token.
- Expired Access Token or wrong audience → reject even with a valid proof.

## 16. Diagnostics and Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Token response is still Bearer | Request lacks a valid DPoP proof or flow does not enable/support DPoP | Check `DPoP` header, server version, and `token_type` |
| JWT lacks `cnf.jkt` | Token not issued as DPoP or customizer/generator stripped claim | Check proof validation and token customizer |
| `cnf.jkt` differs from client-computed thumbprint | Wrong JWK canonicalization, wrong key, or customizer overwrite | Check RFC 7638, key, and context |
| Resource Server reports invalid proof | Invalid `typ`/`alg`/signature/`htm`/`htu`/`iat`/`jti`/nonce | Verify proof created for that exact request |
| Resource Server reports key mismatch | Proof uses a key different from the bound key | Check key lifecycle and token cache |
| `ath` mismatch | Proof bound to another Access Token or wrong hash encoding | Compute SHA-256 over ASCII token, then unpadded base64url |
| First request succeeds, retry fails | Proof `jti` already consumed | Generate a new proof, do not replay old JWT |
| Only some nodes accept proof | Replay cache or nonce store not shared | Check distributed state and clocks |
| Client fails to handle nonce | Client does not store `DPoP-Nonce` or include it in new proof | Inspect challenge/retry logic |
| DPoP token rejected by API despite valid `cnf` | Missing Resource Server `dPoP` support or wrong issuer/`aud`/scope validator | Inspect Resource Server config and token validation |

## 17. Production Deployment Checklist

1. **Key pair:** private key stored securely; public JWK contains only public components.
2. **Proof header:** `typ=dpop+jwt`, allowed asymmetric `alg`, no `none`/MAC.
3. **Proof claims:** `htm`, `htu`, `iat`, `jti` verified; `ath` present on resource requests.
4. **Thumbprint:** `cnf.jkt` computed per RFC 7638 from the verified public JWK.
5. **Token response:** `token_type=DPoP` when the token is sender-constrained.
6. **Resource Server:** compares `cnf.jkt` with proof key and verifies `ath`.
7. **Token validation:** still checks `iss`, `aud`, `exp`, `nbf`, scope, and status.
8. **Replay protection:** stores `jti` for an appropriate window; uses shared state across multiple nodes.
9. **Nonce:** clear challenge policy; client handles `DPoP-Nonce` properly.
10. **Key lifecycle:** processes for rotation, revocation, and lost devices.
11. **Customizers:** never remove or overwrite framework-generated `cnf.jkt`.
12. **Observability:** log validation outcomes, error categories, and correlation IDs; never log tokens, proof JWTs, or private keys.
13. **Version compatibility:** verify DPoP support in your exact Spring Authorization Server/Spring Security versions.
14. **Integration tests:** test token issuance, key mismatch, `ath`, replay, nonce, and a real Resource Server.

## 18. Exercises and Self-Assessment Questions

**Exercise A — Computing a thumbprint.** Given an RSA public JWK with members `kty`, `n`, `e`, `kid`, and `alg`. Identify which members participate in canonical JSON, then describe the steps to produce the SHA-256 thumbprint.

**Exercise B — Mismatched key binding.** A client receives a token with `cnf.jkt` for key A but sends a proof signed by key B. Explain exactly what the Resource Server must compare and why the token is rejected.

**Exercise C — Distinguishing `ath` and `jkt`.** A proof has the correct `jkt` but an incorrect `ath`. Why must the Resource Server still reject it? Write the formula for computing `ath`.

**Exercise D — Token Endpoint vs. Resource Server.** List the required claims of a proof at the Token Endpoint and the additional elements when a proof accompanies an Access Token to a Resource Server.

**Exercise E — Replay cache.** Two nodes receive the same proof `jti` nearly simultaneously. Design a replay cache to prevent both nodes from accepting the proof.

**Exercise F — Key rotation.** A client rotates from key A to key B while still holding an Access Token bound to A's `cnf.jkt`. Design a safe token/key transition process.

**Review Questions:**

1. What roles do `cnf` and `jkt` play in a JWT Access Token?
2. Why is `jkt` the thumbprint of the public JWK rather than the hash of the DPoP Proof JWT?
3. How does RFC 7638 specify canonicalization and hashing?
4. Why must the JWK inside a DPoP Proof never contain private key material?
5. How does a proof sent to the Token Endpoint differ from a proof sent to a Resource Server?
6. From what data is the `ath` claim computed, and is it required on every DPoP Proof?
7. Why is `token_type=DPoP` important for the client?
8. What must the Resource Server verify besides `cnf.jkt`?
9. Why does `jti` require a replay cache instead of preventing replays on its own?
10. How does a nonce help a DPoP Proof?
11. How does DPoP differ from mTLS certificate-bound tokens?
12. If both the token and private key are stolen, what can DPoP still protect?
13. Why should a customizer not manually overwrite the `cnf` claim?
14. When upgrading Spring Security, what should be re-checked regarding `dPoP` configuration?

## 19. References

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449)
- [RFC 9449, Section 4 — DPoP Proof JWTs](https://www.rfc-editor.org/rfc/rfc9449#section-4)
- [RFC 9449, Section 6 — Public Key Confirmation](https://www.rfc-editor.org/rfc/rfc9449#section-6)
- [RFC 9449, Section 7 — Protected Resource Access](https://www.rfc-editor.org/rfc/rfc9449#section-7)
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638)
- [RFC 7800 — Proof-of-Possession Key Semantics for JWTs](https://www.rfc-editor.org/rfc/rfc7800)
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515)
- [Spring Authorization Server — Protocol Endpoints: DPoP-bound Access Tokens](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
- [Spring Authorization Server — OAuth2TokenContext API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/token/OAuth2TokenContext.html)
- [Spring Security 7.1 — DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html)
- [Spring Security — OAuth2ResourceServerConfigurer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.html)

**Takeaway:** **`cnf.jkt` is the SHA-256 JWK Thumbprint of the public key verified inside the DPoP Proof**, not the hash of the token or proof. The Authorization Server embeds that thumbprint in the Access Token upon issuance; the Resource Server recomputes the thumbprint from the proof and compares them, while verifying `ath`, method, URI, timestamps, nonces, and replay. A standalone stolen token becomes much harder to abuse while the private key remains protected, though DPoP does not replace TLS, authorization, key management, or monitoring.
