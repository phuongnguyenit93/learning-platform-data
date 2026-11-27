# Bearer Tokens and DPoP-Bound Access Tokens

> **Chapter: DPoP.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, which covers designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server. This lesson focuses on the differences between **Bearer access tokens** and **DPoP-bound access tokens**, the mechanism for binding a token to a public key, how the client proves possession of the private key, and the verification responsibilities of the Authorization Server/Resource Server.

## 1. Why Are Bearer Tokens Risky When Stolen?

In OAuth 2.0, an access token is commonly sent to a Resource Server via an HTTP header:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.vn
Authorization: Bearer ACCESS_TOKEN_REDACTED
~~~

A Bearer token means that **any party holding the token can present it for use**, as long as the token is still valid and meets other policies. The Resource Server does not require the requesting party to prove that the token was issued to the exact device or application sending the request.

This is very convenient for API integration, but if the token is leaked via logs, browser storage, crash dumps, proxies, telemetry, or a compromised workstation, an attacker can use the token from another device. A valid JWT signature only proves that the token was issued by a trusted issuer and has not been tampered with; it **does not prove that the sender of the request holds a private secret bound to the token**.

Example in this module:

- **Authorization Server:** `https://login.example.vn`.
- **Client:** `portal-web`, a web application or BFF.
- **Resource Server:** `https://api.example.vn`.
- **Access token:** issued to `portal-web` to call the API with scope `orders.read`.
- **Scenario:** token `A0` is copied from an error log. The attacker sends `A0` from their machine before the token expires.

With a Bearer token, the Resource Server can accept the request above if the signature, issuer, audience, expiry, and permissions are all valid. The Resource Server has no proof that the attacker is using the original device/client.

**DPoP (Demonstrating Proof of Possession, RFC 9449)** adds an application-layer cryptographic proof: the token is bound to a public key, and the client must sign a fresh DPoP Proof for each HTTP request using the corresponding private key. A stolen token alone is therefore insufficient to call the API.

## 2. How Do Bearer Tokens and DPoP-Bound Access Tokens Differ?

| Criterion | Bearer access token | DPoP-bound access token |
|---|---|---|
| Condition to present token | Holding the token is sufficient at the Bearer mechanism layer | Must have the token and a valid DPoP Proof demonstrating possession of the bound private key |
| Authorization header | `Authorization: Bearer <token>` | `Authorization: DPoP <token>` |
| Per-request proof | None | Contains a JWT in the `DPoP` header |
| Key binding | No sender-binding in the Bearer mechanism | `cnf.jkt` or introspection metadata identifies the thumbprint of the public key |
| Resistance to using a stolen token alone | Limited by TTL, revocation, and storage protection | Stronger: the attacker also needs the corresponding private key or the ability to create a proof |
| Proof replay protection | Not applicable since there is no proof | Uses `iat` time, `jti`, request validation, and optionally nonce/replay cache |
| Client requirements | Token management | Token management, key pair management, and generating a new proof per request |
| Resource Server requirements | Verify token and authorization | Verify token, proof, key binding, and authorization |
| Compatibility | Broad, supported by default in many libraries | Client, Authorization Server, and Resource Server must all support DPoP |
| Overhead | Minimal cryptographic processing per request | Adds proof signing/verification and anti-replay state management |

Traditional Bearer model:

~~~text
Client has ACCESS_TOKEN
        |
        v
Authorization: Bearer ACCESS_TOKEN
        |
        v
Resource Server verifies token
        |
        v
Allow if token/permissions are valid
~~~

DPoP model:

~~~text
Client has ACCESS_TOKEN + private key
        |
        +--> Create DPoP Proof for current HTTP request
        |
        v
Authorization: DPoP ACCESS_TOKEN
DPoP: SIGNED_PROOF
        |
        v
Resource Server verifies token + proof
        |
        +--> cnf.jkt matches public key in proof?
        +--> ath matches access token?
        +--> htm/htu/iat/jti/nonce valid?
        |
        v
Allow if all checks and authorization pass
~~~

DPoP is an application-layer **sender-constraining** mechanism. It does not replace client authentication, user authentication, scopes, audience, business authorization, or TLS. A valid DPoP Proof only proves possession of a key; the proof itself does not grant access permissions.

## 3. Components of DPoP

### 3.1. Client Key Pair

The client generates an asymmetric key pair:

- **Private key:** kept in the client environment and used to sign DPoP Proofs. Never send the private key to the Authorization Server or Resource Server.
- **Public key:** included in the JOSE header of the DPoP Proof as a JWK. The server uses this key to verify the signature.
- **JWK Thumbprint:** the SHA-256 value computed from the public JWK according to RFC 7638. The Authorization Server uses this thumbprint to bind the access token to the key.

The DPoP key is the **client's** key, not the Authorization Server's JWT access token signing key. The two key pairs serve different purposes:

| Key | Owner | Used for |
|---|---|---|
| DPoP private key | OAuth client/device | Signing proofs to demonstrate possession |
| DPoP public key | Public inside the proof | Verifying proofs and computing the thumbprint |
| Authorization Server signing key | Authorization Server | Signing JWT access tokens/ID Tokens |
| Resource Server key (if any) | Resource Server | Does not replace the DPoP client key |

Do not reuse the Authorization Server's access token signing private key for DPoP. The client should generate and protect the private key according to the device/application lifecycle; on supported devices, prefer a keystore or hardware-backed key protection.

### 3.2. A DPoP Proof Is a Per-HTTP-Request JWT

A DPoP Proof is a JWT signed with the client's private key and sent in the `DPoP` HTTP header. The JOSE header must contain these basic fields:

| Field | Meaning |
|---|---|
| `typ` | Must have the value `dpop+jwt` to explicitly identify the proof type |
| `alg` | An allowed asymmetric signature algorithm, such as `ES256` or `RS256`; must not use `none` or symmetric MAC algorithms |
| `jwk` | The public JWK corresponding to the private key that signed the proof; must not contain private key material |

The proof payload must contain these claims:

| Claim | Meaning |
|---|---|
| `jti` | Unique identifier of the proof; supports replay detection |
| `htm` | HTTP method of the request, e.g., `GET` or `POST` |
| `htu` | Target URI of the request, excluding query string and fragment |
| `iat` | Time the proof was created (NumericDate) |
| `ath` | Hash of the access token; required when the proof is sent with an access token to a protected resource |
| `nonce` | Server-provided nonce if required by the server |

Example proof payload used at the token endpoint:

~~~json
{
  "jti": "dpop-proof-id-unique",
  "htm": "POST",
  "htu": "https://login.example.vn/oauth2/token",
  "iat": 1794825600
}
~~~

Example proof payload used when calling a Resource Server:

~~~json
{
  "jti": "another-unique-proof-id",
  "htm": "GET",
  "htu": "https://api.example.vn/api/orders",
  "ath": "BASE64URL_SHA256_OF_ACCESS_TOKEN",
  "iat": 1794825610
}
~~~

These are illustrative payloads, not signed JWTs. Each HTTP request requires its own proof; do not cache and resend the same proof across multiple requests. `ath` binds the proof to the exact access token being presented. `htm` and `htu` bind the proof to the method and target URI, preventing the proof from being arbitrarily replayed against another endpoint.

### 3.3. Why Does `htu` Omit the Query and Fragment?

According to RFC 9449, `htu` contains the HTTP target URI **without query and fragment**. Example:

~~~text
Request URL:
https://api.example.vn/api/orders?status=open&page=2#result

htu in DPoP Proof:
https://api.example.vn/api/orders
~~~

The method and target URI must be normalized/matched according to RFC rules. For systems behind a reverse proxy, the Resource Server needs to know the actual public URL the client called. Do not blindly trust `X-Forwarded-Host` or `X-Forwarded-Proto` from untrusted sources; configure trusted proxies so the server computes `htu` accurately.

## 4. Flow for Issuing a DPoP-Bound Access Token

DPoP does not create a new OAuth2 grant type. The client still uses Authorization Code, Refresh Token, Client Credentials, or any supported grant; the difference is that the client attaches a DPoP Proof at the token endpoint so the Authorization Server binds the issued token to the public key.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant AS as Authorization Server
    participant RS as Resource Server

    C->>C: Generate key pair Kpriv/Kpub
    C->>AS: Token request + DPoP Proof(Kpriv, Kpub)
    AS->>AS: Verify proof, htm, htu, iat, jti, nonce
    AS->>AS: Compute JWK Thumbprint of Kpub
    AS->>AS: Issue access token with cnf.jkt
    AS-->>C: access_token + token_type=DPoP
    C->>C: Store access token and Kpriv
    C->>RS: Authorization: DPoP token + new DPoP Proof
    RS->>RS: Verify access token and proof
    RS->>RS: Match cnf.jkt, ath, htm, htu, iat, jti
    RS-->>C: Return resource if token and authorization are valid
~~~

### 4.1. Request at the Token Endpoint

Example of a client exchanging an authorization code using DPoP:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_CREDENTIALS_REDACTED
DPoP: SIGNED_DPOP_PROOF_REDACTED

grant_type=authorization_code&code=AUTHORIZATION_CODE_REDACTED&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&code_verifier=PKCE_VERIFIER_REDACTED
~~~

- The `DPoP` header contains a proof signed with the client's private key.
- `htm` must be `POST` and `htu` must match the public token endpoint the client is calling.
- The proof has a fresh `jti`, an appropriate `iat`, and a `nonce` if required by the Authorization Server.
- `ath` is used when a proof is bound to an access token presented at a protected resource; it is not a required claim to prove the code exchange request at the token endpoint.
- `Authorization: Basic` is just an example of a confidential client using `client_secret_basic`. DPoP does not replace client authentication; a public client may not have a client secret.

After verifying the proof, the Authorization Server computes the thumbprint of the public key and binds the token to that thumbprint. A successful response indicates the token type:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "access_token": "DPOP_ACCESS_TOKEN_REDACTED",
  "token_type": "DPoP",
  "expires_in": 300,
  "scope": "orders.read"
}
~~~

The client must read `token_type=DPoP` to use the correct authentication scheme when calling the API. Do not switch the scheme to `Bearer` merely for compatibility with an older HTTP client.

### 4.2. Binding Information in the Access Token

For a JWT access token, the public key thumbprint is expressed via the `cnf.jkt` claim:

~~~json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1794825900,
  "cnf": {
    "jkt": "JWK_SHA256_THUMBPRINT"
  }
}
~~~

`cnf.jkt` does not contain the private key or the entire public JWK; it is the thumbprint for the Resource Server to compare against the public key in the DPoP Proof. If the access token is an opaque/reference token, the Resource Server can obtain binding information via token introspection. According to RFC 9449, the introspection response can return `cnf.jkt`; the Resource Server verifies the proof and binding itself and does not send the DPoP Proof in the introspection request.

## 5. Calling a Resource Server with a DPoP-Bound Access Token

When calling an API, the client sends **both the access token and a fresh proof**:

~~~http
GET /api/orders HTTP/1.1
Host: api.example.vn
Authorization: DPoP DPOP_ACCESS_TOKEN_REDACTED
DPoP: SIGNED_DPOP_PROOF_WITH_ATH_REDACTED
~~~

The proof must be generated for this specific request, containing:

- `htm=GET`.
- `htu=https://api.example.vn/api/orders` (without query/fragment).
- `iat` close to the time the request is sent.
- A unique `jti`.
- `ath` as the unpadded Base64URL encoding of the SHA-256 hash over the ASCII bytes of the sent access token value.
- `nonce` if required by the Resource Server.

### 5.1. Computing `ath` in Java

Example helper computing the hash per RFC 9449:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;

final class DPoPProofSupport {

    private DPoPProofSupport() {
    }

    static String accessTokenHash(String accessToken)
            throws NoSuchAlgorithmException {

        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(accessToken.getBytes(StandardCharsets.US_ASCII));

        return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
    }
}
~~~

Do not hash a URL-encoded string, do not use UTF-8 instead of ASCII for the token value, and do not place the raw access token into a proof claim. `ath` is signed inside the proof so the Resource Server can confirm the proof is bound to the exact token.

### 5.2. Checks at the Resource Server

The Resource Server must verify both the access token and the DPoP Proof:

1. **Access token:** signature or introspection, issuer, audience, expiry, scope, active status, and business authorization.
2. **Proof JWT:** signature using the public JWK, `typ=dpop+jwt`, and an asymmetric algorithm on the allowlist.
3. **Request binding:** `htm` and `htu` match the actual request.
4. **Token binding:** JWK thumbprint of the proof public key matches `cnf.jkt` of the access token.
5. **Token hash:** `ath` matches the SHA-256 hash of the sent access token.
6. **Freshness/replay:** `iat` is within the accepted time window; `jti` has not been reused within the replay detection scope.
7. **Nonce:** if the Resource Server requires a nonce, the proof must contain a fresh/valid nonce issued by that Resource Server.

Only when all checks pass does the Resource Server proceed with authorization based on scopes and resource permissions. DPoP does not replace API permission checks.

## 6. Generating a DPoP Proof with Nimbus and Spring Security

The following example illustrates the structure using `NimbusJwtEncoder` to sign a proof. The key in the example is the **OAuth Client's** key; production must obtain the private key from a keystore/hardware-backed storage or appropriate protection mechanism, never creating a shared hardcoded key in source code.

### 6.1. Generating a Proof for the Token Endpoint

~~~java
import java.time.Instant;
import java.util.UUID;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;

import org.springframework.security.oauth2.jose.jws.JwsHeader;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

final class DPoPProofFactory {

    private final JwtEncoder encoder;
    private final RSAKey dpopKey;

    DPoPProofFactory(RSAKey dpopKey) {
        this.dpopKey = dpopKey;

        JWKSource<SecurityContext> jwkSource =
                (selector, context) -> selector.select(new JWKSet(dpopKey));

        this.encoder = new NimbusJwtEncoder(jwkSource);
    }

    Jwt createTokenEndpointProof(String method, String tokenEndpoint) {
        JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
                .type("dpop+jwt")
                .jwk(dpopKey.toPublicJWK().toJSONObject())
                .build();

        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuedAt(Instant.now())
                .claim("htm", method.toUpperCase())
                .claim("htu", tokenEndpoint)
                .id(UUID.randomUUID().toString())
                .build();

        return this.encoder.encode(
                JwtEncoderParameters.from(header, claims));
    }
}
~~~

This is an example for a token endpoint proof and does not yet include nonce challenges, server-side replay storage, or key lifecycle management. `tokenEndpoint` must be the public URL the client calls, e.g., `https://login.example.vn/oauth2/token`. Do not infer the URL from untrusted proxy headers.

### 6.2. Generating a Proof for a Protected Resource

For a resource request, create a new proof and add `ath`:

~~~java
JwtClaimsSet claims = JwtClaimsSet.builder()
        .issuedAt(Instant.now())
        .claim("htm", "GET")
        .claim("htu", "https://api.example.vn/api/orders")
        .claim("ath", DPoPProofSupport.accessTokenHash(accessToken))
        .id(UUID.randomUUID().toString())
        .build();

JwsHeader header = JwsHeader.with(SignatureAlgorithm.RS256)
        .type("dpop+jwt")
        .jwk(dpopKey.toPublicJWK().toJSONObject())
        .build();

Jwt proof = jwtEncoder.encode(JwtEncoderParameters.from(header, claims));
~~~

The snippet only illustrates the claims and header; the token-signing helper should be built with the same client private key as in the previous example. Each request requires a different `jti`. Never reuse a proof from a previous request, even if the previous request failed with a network error.

## 7. Nonce and Replay Protection

A DPoP Proof includes a unique `jti` and `iat` to limit reuse. The server must restrict the proof acceptance window (typically only seconds or minutes). The server can store seen `jti` values within that window to reject replayed proofs.

### 7.1. Replay Cache

A multi-instance Resource Server needs to consider sharing replay state:

- Store a hash of `jti` along with issuer/resource context with a short TTL.
- Upon receiving a proof, check that `jti` does not already exist and record it in an atomic operation.
- If it already exists, reject the request.
- The TTL of the replay record should not exceed the window during which the proof is still accepted.
- Limit `jti` size and the number of records to prevent memory exhaustion.
- If nodes do not share replay state, a proof could be sent to another node; assess the risk and design appropriate storage.

DPoP binds a proof to a method and URI, but a stolen proof can still be replayed at the **same endpoint and same method** while it remains within the acceptance window if the server does not detect replays.

### 7.2. Server-Provided Nonce

The Authorization Server or Resource Server may require a nonce. The server sends the `DPoP-Nonce` header; the client adds this value to the `nonce` claim of the subsequent proof.

Example when the Authorization Server requires a nonce:

~~~http
HTTP/1.1 400 Bad Request
DPoP-Nonce: SERVER_NONCE_VALUE

{
  "error": "use_dpop_nonce",
  "error_description": "Authorization Server requires a nonce"
}
~~~

The client must create a **new proof** containing the new nonce and resend the request as instructed. Do not modify the payload of an already-signed proof or reuse the same proof with a new nonce.

A nonce issued by the Authorization Server is only used with that Authorization Server; a Resource Server's nonce is only used with the Resource Server that issued it. Do not confuse a DPoP nonce with the OIDC `nonce` in an ID Token. For browser clients using CORS, if JavaScript needs to read the `DPoP-Nonce` header, the server must expose that header in the CORS response.

## 8. Combining DPoP with Authorization Code, PKCE, and PAR

DPoP and PKCE protect different stages:

| Mechanism | Protects |
|---|---|
| PKCE | Binds the authorization code to `code_verifier` to mitigate code interception/injection |
| DPoP | Binds the access token (and optionally refresh token) to the client's key |
| `state` | Links the authorization response to the client-initiated transaction, preventing CSRF/transaction mix-ups |
| OIDC `nonce` | Links the ID Token to the OIDC login transaction |
| `dpop_jkt` | Optionally binds the authorization code to the thumbprint of the DPoP public key |

### 8.1. Authorization Code Binding with `dpop_jkt`

The client can send the `dpop_jkt` parameter in the authorization request. Its value is the JWK SHA-256 Thumbprint of the DPoP public key the client intends to use. When the token request arrives, the Authorization Server computes the thumbprint from the public key in the DPoP Proof and compares it with the stored `dpop_jkt`. If they do not match, the server must reject the token request.

Example:

~~~http
GET /oauth2/authorize?response_type=code&client_id=portal-web&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&scope=orders.read&state=STATE_VALUE&code_challenge=PKCE_CHALLENGE&code_challenge_method=S256&dpop_jkt=PUBLIC_KEY_THUMBPRINT
Host: login.example.vn
~~~

`dpop_jkt` is optional according to RFC 9449. It can be combined with PKCE; when used, generate a separate DPoP key per authorization request if you want key binding similar to PKCE. DPoP does not replace PKCE.

### 8.2. Combining with PAR

When using Pushed Authorization Requests (PAR), the client can include `dpop_jkt` in the POST body of the PAR request. Alternatively, it can send a `DPoP` header on the PAR request; the Authorization Server verifies the proof and treats the thumbprint in the proof as the supplied `dpop_jkt`. If both are used, both thumbprints must match.

This binds the authorization code itself to the DPoP key right from authorization initiation, after which the token endpoint must receive a proof from that exact key.

## 9. DPoP with Refresh Tokens

DPoP can bind refresh tokens, which is especially useful for public clients without a client secret. According to RFC 9449, if an Authorization Server issues a refresh token to a public client, the refresh token is also bound to the DPoP public key.

When refreshing:

1. The client sends `grant_type=refresh_token` and the refresh token over HTTPS.
2. The client generates a new proof for the token endpoint, with `htm=POST`, the exact endpoint `htu`, `iat`, `jti`, and `nonce` if required.
3. The Authorization Server validates the proof and verifies that the key matches the refresh token's binding.
4. If valid, the server issues a new DPoP-bound access token; refresh token rotation policies still apply independently.
5. The client continues creating a new proof for each Resource Server call.

DPoP does not eliminate the need for rotation, replay detection, TTL, and revocation for refresh tokens. If the private key is compromised, an attacker can create proofs; a procedure is needed to revoke tokens/key bindings and issue new authorizations.

## 10. DPoP and Other Protection Mechanisms

| Mechanism | Where is binding? | Strengths | Difference from DPoP |
|---|---|---|---|
| Bearer token | No sender-binding | Simple, broad compatibility | Anyone holding the token can present it |
| DPoP | HTTP/application layer, bound to a public key | Suitable for SPA/native clients; no client certificate needed | Requires a proof JWT per request; does not sign the entire request body/headers |
| mTLS-bound token | TLS/certificate layer | Binds token to client certificate on the TLS connection | Requires mutual TLS infrastructure and certificate management |
| PKCE | Authorization code exchange | Prevents code interception/injection | Does not bind the access token after issuance |
| Client authentication | OAuth client identity at the AS | Verifies client via secret/private key/certificate | DPoP is not client authentication |
| TLS | Transport channel | Secures data in transit | DPoP does not replace TLS; HTTPS is still required |

DPoP is typically suitable when clients run in browsers/native apps where mTLS is hard to deploy. mTLS may fit service-to-service communication in infrastructure with solid certificate management. Both mechanisms can coexist by policy, but you must understand which binding the Resource Server is verifying.

## 11. Security Limitations and Threat Model

DPoP reduces the risk of **standalone access token theft**, but it does not solve all attack types:

- **XSS or malicious code in the client context:** an attacker can invoke the key-signing API while the application is running, even with non-exportable keys. CSP, XSS defenses, dependency review, and runtime protection are still required.
- **Stolen private key:** an attacker possessing both the token and the private key can generate valid proofs. Use a keystore/HSM, restrict export, and rotate/revoke upon compromise.
- **Replayed proof:** a stolen proof can be replayed briefly at the same endpoint/method if the server does not detect used `jti` values. Apply freshness checks, a replay cache, and nonces per the threat model.
- **Tampered request body/headers:** DPoP binds the method and URI, not the entire body or all HTTP headers. TLS is still required to protect request integrity and confidentiality.
- **URL mismatch behind a reverse proxy:** if the client signs the public URI while the server checks against an internal URI or vice versa, valid requests may be rejected; if untrusted forwarded headers are accepted, attackers can cause bypasses or DoS.
- **Overly broad key sharing:** sharing one private key across multiple devices increases the blast radius when one device is compromised and complicates individual revocation.
- **Downgrade to Bearer:** the Resource Server must never accept a DPoP-bound token as a Bearer token merely for "compatibility." Enforce token type and confirmation binding strictly.
- **Incorrect authorization:** a valid proof does not mean the user has permission to read/modify data. The Resource Server must still check scopes, roles, tenant, audience, and object-level permissions.
- **Lost private key:** the client can no longer use tokens bound to the old key; new authorization/tokens must be issued according to policy.

DPoP is an additional defense layer for bearer credentials, not an excuse to store tokens longer, drop TLS, or skip access control checks.

## 12. Integration with Spring Authorization Server and Spring Security

### 12.1. Spring Authorization Server

Spring Authorization Server **1.5.x** adds DPoP support per RFC 9449. The token endpoint receives the DPoP Proof in the `DPoP` header; when the proof is valid, the server binds the public key to the access token and returns `token_type=DPoP`. For JWT access tokens, the binding is represented in `cnf.jkt`; for opaque tokens, the Resource Server can retrieve the information via introspection.

Filter chain skeleton for the Authorization Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServer.getEndpointsMatcher())
                .with(authorizationServer, Customizer.withDefaults())
                .authorizeHttpRequests(authorize ->
                        authorize.anyRequest().authenticated());

        return http.build();
    }
}
~~~

This is a filter chain configuration skeleton. DPoP is handled in the token endpoint of supported versions; the application still needs `RegisteredClient`, `AuthorizationServerSettings`, authorization/token services, JWK signing for JWTs, client authentication, and user authentication. Do not build a custom token endpoint controller to replace standard filters/providers.

Check Authorization Server metadata per RFC 9449. The `dpop_signing_alg_values_supported` field advertises supported JWS algorithms for signing DPoP Proofs. Do not manually add metadata advertising an algorithm that the token endpoint does not actually accept.

### 12.2. Spring Security Resource Server

Spring Security **7.1 and later** provides a DSL to configure DPoP for the Resource Server. Example when using JWT access tokens:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
class ResourceServerSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurityChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                    .requestMatchers("/health").permitAll()
                    .anyRequest().authenticated())
                .oauth2ResourceServer(resourceServer -> resourceServer
                    .jwt(Customizer.withDefaults())
                    .dPoP(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

The example assumes a JWT decoder is already configured (e.g., via issuer URI or a corresponding bean) and the dependency version includes the DPoP DSL. For opaque tokens, configure introspection and DPoP according to your version's API; the introspection response must provide the `cnf.jkt` confirmation claim.

**Compatibility note:** Spring Authorization Server 1.5.x supports issuing DPoP-bound access tokens; the Resource Server DPoP DSL was added in Spring Security **7.1**. If your project uses Spring Security 6.x, do not copy the DSL example above verbatim assuming the API exists. Verify BOM/dependency alignment and the actual APIs of your Spring Boot/Security/SAS versions; you may need to upgrade the stack in sync or configure appropriate extension points.

### 12.3. OAuth2 Client Side

The client must generate proofs for both token requests and protected resource requests. Do not assume that merely enabling `oauth2Login()` or `oauth2Client()` makes the library automatically create DPoP Proofs, manage private keys, handle nonces, and attach `ath`.

When integrating:

- Use a client library with explicit DPoP support, or build an HTTP client/interceptor layer that handles keys and proofs per the RFC.
- Ensure proofs at the token endpoint and Resource Server use the same public key bound to the token.
- Generate a fresh proof for every request; do not retry a request using an old proof.
- Handle `DPoP-Nonce` and the `use_dpop_nonce` error.
- Never place private keys in plaintext configuration, browser local storage, or logs.
- For SPAs, protect the execution context and use Web Crypto/keystore capabilities as supported by the platform; non-exportable keys do not prevent XSS from calling signing APIs.

## 13. Testing Bearer and DPoP-Bound Tokens

A good test suite must prove that **a stolen token alone is insufficient** and that the Resource Server properly enforces binding. Use dummy keys/tokens in staging and never write raw credentials to logs.

| Case | Action | Expected Result |
|---|---|---|
| 1 | Call API with a valid Bearer token against a Bearer Resource Server | Accepted per scope/policy |
| 2 | Call API with a DPoP token and valid proof | Accepted |
| 3 | Send DPoP token without `DPoP` header | Rejected |
| 4 | Send DPoP token with `Bearer` scheme | Not accepted as Bearer |
| 5 | Proof signed by a different key | Rejected due to thumbprint mismatch with `cnf.jkt` |
| 6 | Modify proof payload while keeping old signature | Rejected due to signature failure |
| 7 | `typ` other than `dpop+jwt` | Rejected |
| 8 | Send `alg=none` or symmetric MAC | Rejected |
| 9 | `htm` does not match HTTP method | Rejected |
| 10 | `htu` does not match target URI | Rejected |
| 11 | Missing `ath` at protected resource | Rejected |
| 12 | `ath` computed from a different token | Rejected |
| 13 | `iat` too old or outside window | Rejected |
| 14 | Resend the same `jti`/proof | Rejected per replay policy |
| 15 | Server requires nonce but proof lacks nonce | Returns `use_dpop_nonce`/nonce challenge per policy |
| 16 | Send stale nonce or nonce from another server | Rejected |
| 17 | Access token expired or wrong audience | Rejected even with a valid proof |
| 18 | Valid proof but insufficient scope | Authorization rejected |
| 19 | Public client refreshes token with wrong key | Rejected |
| 20 | Authorization Code has `dpop_jkt` but token proof uses different key | Rejected |
| 21 | DPoP behind reverse proxy | `htu` matched against exact public URI |
| 22 | Multiple Resource Server instances | Replay detection works according to cluster design |
| 23 | Simulated XSS calling WebCrypto sign | Protection boundaries assessed; do not assume DPoP blocks in-origin code execution |
| 24 | Lost private key | Client cannot use old bound token; requires new authorization |

### 13.1. Checking Token Response and JWT Claims

After a successful token exchange, verify:

- The response contains `token_type=DPoP`.
- The JWT access token contains `cnf.jkt` and the thumbprint matches the client's public key.
- Opaque token introspection returns `cnf.jkt` per contract.
- `iss`, `aud`, `exp`, scope, and subject remain accurate.
- No private key or secret is present in the access token.

Do not merely decode the JWT to read claims; in tests, verify the signature and issuer before trusting the payload.

### 13.2. Testing Replay and Nonce

Send a proof with a fixed `jti` twice within the accepted time window. The first request may succeed; the second request must be detected as a replay if the server implements a replay cache. Also test the case where two requests hit two different nodes.

For nonces, test the flow: server returns `DPoP-Nonce` → client generates a new proof with the `nonce` claim → resends → server accepts if the nonce is still valid. Never reuse an old proof when receiving a new nonce.

## 14. Troubleshooting and Operational Checklist

| Symptom | Common Cause | Resolution |
|---|---|---|
| Token endpoint returns `invalid_dpop_proof` | Invalid signature, typ/alg/JWK, `htm`/`htu`, or `iat` | Decode proof in test environment, check key and public URL |
| Token response is still `Bearer` | Client did not send proof, proof was not processed, or server/version does not support it | Check DPoP header, token endpoint, and versions |
| Resource Server returns 401 | Missing proof, wrong authentication scheme, or invalid token | Use `Authorization: DPoP` and a fresh proof |
| `cnf.jkt` mismatch | Client changed key after token issuance or sent wrong key | Use the bound private key; issue a new token if the key changed |
| `ath` mismatch | Token hashed with wrong encoding or proof created for another token | Hash ASCII access token with unpadded Base64URL |
| `htu` mismatch behind proxy | App sees internal URI instead of external URI | Configure trusted forwarded headers and canonical public URL |
| Repeated `use_dpop_nonce` | Client fails to update nonce or uses nonce from wrong server | Store nonce per issuer/resource server and generate a new proof |
| One proof accepted multiple times across pods | Replay cache not shared or not enabled | Design shared replay store/nonce with TTL |
| Spring Resource Server rejects DPoP DSL | Spring Security version prior to 7.1 or dependency mismatch | Check BOM and API versions |
| XSS still calls API successfully | Malicious code in client context can request key to sign proof | Prevent XSS, enforce CSP, minimize third-party code, protect keys |

### 14.1. Production Checklist

- [ ] Choose DPoP for clients/APIs with appropriate token theft risk; assess compatibility across client, AS, and RS.
- [ ] Private keys are generated and protected on the client; public JWK in proofs contains no private parameters.
- [ ] Proof JWT contains `typ=dpop+jwt`, allowlisted asymmetric `alg`, public `jwk`, `jti`, `htm`, `htu`, and `iat`.
- [ ] Each HTTP request has a fresh proof, non-repeating `jti`, and timestamp within a short window.
- [ ] Proofs at protected resources include the exact `ath` hash of the access token.
- [ ] Access tokens have `cnf.jkt` binding or equivalent introspection info; Resource Server matches the thumbprint.
- [ ] DPoP tokens are sent exclusively with the `DPoP` authentication scheme; never downgrade to Bearer.
- [ ] Nonce challenges are handled properly and isolated per AS/RS.
- [ ] Replay cache/nonce state works across multiple instances.
- [ ] TLS remains enabled; DPoP is not treated as body/header protection or a TLS replacement.
- [ ] PKCE, state, client authentication, audience, scope, and business authorization are still enforced.
- [ ] Procedures exist for key rotation, key compromise, token revocation, and re-authorization.
- [ ] Test XSS and key storage, especially for SPA/browser clients.
- [ ] Spring Authorization Server and Spring Security versions are aligned; verify actual behavior rather than relying solely on sample code.
- [ ] Never log access tokens, refresh tokens, DPoP proofs, private keys, or Authorization headers.

**Self-Check Questions**

1. Why can a Bearer token be used by anyone who obtains the token string?
2. Which claim binds a DPoP-bound access token to a public key?
3. Why must a DPoP Proof have `typ=dpop+jwt` and an asymmetric signature algorithm?
4. What is the difference between `jti`, `ath`, `htm`, and `htu`?
5. Why is `ath` only required when a proof is sent alongside an access token to a protected resource?
6. Why is a DPoP Proof not client authentication?
7. How does a DPoP nonce differ from an OIDC ID Token nonce?
8. Does DPoP prevent XSS within an SPA's origin from calling APIs on the user's behalf?
9. Why does DPoP not replace TLS and PKCE?
10. If a Resource Server runs across multiple pods, what is needed to detect replays of the same proof?
11. How does `dpop_jkt` bind an authorization code to a DPoP key?
12. Why must a DPoP-bound access token never be sent using the `Bearer` scheme?

## References

- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): proof JWT, public key confirmation, access token binding, nonce, replay, `dpop_jkt`, and security considerations.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): Bearer access token usage and bearer credential risks.
- [RFC 7638 — JSON Web Key (JWK) Thumbprint](https://www.rfc-editor.org/rfc/rfc7638.html): computing the thumbprint of a public JWK.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html): comparison with certificate-bound tokens.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636.html): PKCE and authorization code binding.
- [Spring Authorization Server — Protocol Endpoints: DPoP-bound Access Tokens](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): issuing DPoP-bound access tokens and the `cnf.jkt` claim.
- [Spring Authorization Server 1.5 GA](https://spring.io/blog/2025/05/20/spring-authorization-server-1-5-goes-ga/): DPoP support added in the 1.5 release line.
- [Spring Security — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/dpop-tokens.html): DPoP proof verification and DPoP Resource Server.
- [Spring Security — OAuth2 Resource Server API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.html): DPoP configuration DSL and supported versions.
