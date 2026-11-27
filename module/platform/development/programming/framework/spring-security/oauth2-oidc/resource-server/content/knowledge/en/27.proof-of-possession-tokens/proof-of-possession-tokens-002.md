# DPoP Under RFC 9449 and Support Scope Across Spring Security Versions

**DPoP (Demonstrating Proof of Possession)** is an OAuth 2.0 sender-constraining mechanism standardized in **RFC 9449**. Instead of allowing anyone who possesses an access token to use it like a regular Bearer token, DPoP binds the access token to a **public key**. The Client must prove it holds the **corresponding private key** every time it uses the access token.

In a request to a Resource Server, the Client sends both:

- The access token with the **§DPoP§** authentication scheme in the §Authorization§ header.
- A fresh **DPoP proof JWT** in the §DPoP§ header.

The Resource Server verifies the proof, compares the public key in the proof against the key bound in the access token, and verifies the request method/URI and the hash of the access token itself. As a result, a stolen access token on its own is much harder to use from a Client that lacks the private key.

**Spring Security version support scope must be read accurately.** The API includes the §DPoPAuthenticationProvider§ class starting in **6.5**; DPoP Resource Server documentation exists in the 6.5 and 7.0 branches. The fluent configurer §OAuth2ResourceServerConfigurer.dPoP(...)§ is marked **§@since 7.1§**, used to explicitly configure the request matcher, converter, and handlers. In the official documentation referenced here, DPoP Resource Server is described for the **Servlet stack**; do not infer that §ServerHttpSecurity§/WebFlux has equivalent support merely because Reactive Resource Server supports JWT and opaque tokens.

> **Keep in mind:** DPoP is not a new kind of JWT access token, does not replace signature/issuer/audience/scope validation, and does not automatically invalidate an access token when leaked. It adds **per-request proof of key possession**. The Client, Authorization Server, and Resource Server must all properly support RFC 9449 for the mechanism to work end-to-end.

## 1. The Problem DPoP Solves

A standard Bearer access token has the following property:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token>
~~~

The server accepts the token if it is valid and has sufficient permissions. However, if an attacker obtains the token from logs, a compromised machine, browser storage, a proxy, or an intermediate system, the attacker can replay the token from another machine until it expires or is revoked.

**DPoP reduces the risk of a token being used independently of the original Client.** When the token is issued, the Authorization Server binds it to the Client's public key. When the Client calls the API, it signs a proof JWT with its private key. The Resource Server verifies the proof and checks that the public key matches the key bound to the access token.

~~~mermaid
sequenceDiagram
    actor U as User
    participant C as OAuth2 Client
    participant AS as Authorization Server
    participant RS as Resource Server

    U->>C: Start authorization
    C->>AS: Token request + DPoP proof
    AS->>AS: Verify proof and extract public key
    AS-->>C: Access token token_type=DPoP, cnf.jkt
    C->>RS: Authorization: DPoP token + new DPoP proof
    RS->>RS: Verify proof signature, htm, htu, iat, jti, ath
    RS->>RS: Compare public-key thumbprint with access-token cnf.jkt
    RS->>RS: Verify access token and authorization policy
    RS-->>C: Resource response
~~~

If an attacker obtains only the access token without the private key, requests lack a valid proof. If an attacker captures an old proof, that proof is bound to the HTTP method, URI, timestamp, and access-token hash, and replay can be blocked via §jti§/nonce.

### 1.1. Comparing Bearer and DPoP-Bound Tokens

| Property | Bearer access token | DPoP-bound access token |
| --- | --- | --- |
| Authorization scheme | §Bearer§ | §DPoP§ |
| Credential sent to Resource Server | Access token | Access token + DPoP proof |
| Proof of right to use token | Possession of token | Possession of token and bound private key |
| Public-key binding | Not required | §cnf.jkt§ or corresponding introspection metadata |
| Per-request proof | No | Yes, bound to method/URI/token |
| Protection against standalone token theft | Limited | Stronger if the private key is not leaked |
| Protection against proof replay | No proof | §jti§, time window, and policy-based nonce |
| Replaces TLS | No | No |

### 1.2. DPoP Is Not PKCE, mTLS, or JWT Encryption

The following mechanisms solve different problems:

| Mechanism | What Does It Bind? | Primary Stage |
| --- | --- | --- |
| **PKCE (RFC 7636)** | Authorization code to a verifier held by the Client | Authorization Code flow |
| **DPoP (RFC 9449)** | Access token to a public key and proof of the private key | Token request and each resource request |
| **OAuth mTLS (RFC 8705)** | Access token to a client TLS certificate/identity | TLS connection and token/resource usage |
| **JWT signature** | Token claims to the issuer's signing key | Token validation |
| **JWE/encryption** | Token contents to a decryption key | When token confidentiality is needed |

A Client can use **PKCE and DPoP together**. PKCE protects the authorization code during the code exchange; DPoP sender-constrains the access token after it is issued. DPoP can also be combined with other controls according to the threat model.

## 2. Components of DPoP

DPoP uses an asymmetric key pair:

- **Private key**: kept secret by the Client and used to sign proof JWTs.
- **Public key**: placed in the proof's JOSE header under the §jwk§ field; used by the Authorization Server to bind the token.
- **JWK thumbprint**: an identifier value for the public key, typically represented by the §cnf.jkt§ claim in a JWT access token.

The private key must be protected like a high-value credential. For native/mobile applications, consider appropriate secure hardware/keystores; for server-side Clients, use server-side secret/key management. Never send the private key to the Authorization Server, Resource Server, browser logs, or telemetry.

### 2.1. Header of a DPoP Proof JWT

An illustrative JOSE header for a proof JWT:

~~~json
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
~~~

Key requirements:

- §typ§ must be §dpop+jwt§.
- §alg§ must be a registered, supported asymmetric signature algorithm accepted by policy; never use §none§.
- §jwk§ contains the public key; do not include private parameters in the header.
- The signature must be verifiable using the public key in §jwk§.
- Allow only algorithms and key types compliant with policy; do not accept every algorithm just because a library can parse it.

### 2.2. Claims of a DPoP Proof

Proofs at the token endpoint and proofs on protected-resource requests differ in several respects:

| Claim | Meaning | Token endpoint | Protected resource |
| --- | --- | --- | --- |
| §jti§ | Unique ID of the proof | Required | Required |
| §htm§ | HTTP method of the request | Required | Required |
| §htu§ | HTTP target URI, without query and fragment | Required | Required |
| §iat§ | Proof creation timestamp | Required | Required |
| §ath§ | Hash of the access token | Not used for normal token requests | **Required** |
| §nonce§ | Recent nonce provided by AS/RS | When required by server | When required by server |

Example proof payload for a token request:

~~~json
{
  "jti": "a5e91f10-4b74-4b72-a23b-cfe21df1c81b",
  "htm": "POST",
  "htu": "https://identity.example.test/oauth2/token",
  "iat": 1893456000
}
~~~

Example proof payload for a resource request:

~~~json
{
  "jti": "b6f02a21-5c85-4c83-b34c-d0f32ef2d92c",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1893456015,
  "ath": "<base64url-sha256-of-access-token>"
}
~~~

§jti§ must have an extremely low probability of collision within the proof's validity window; RFC 9449 describes using at least 96 bits of random data or a UUID version 4. Do not reuse a fixed §jti§ value across multiple requests.

### 2.3. §htu§ Excludes Query and Fragment

If the request is:

~~~text
https://api.example.test/api/orders/42?view=compact#details
~~~

then §htu§ in the proof excludes the query and fragment:

~~~text
https://api.example.test/api/orders/42
~~~

The server must compare URIs according to the normalization rules in RFC 9449/RFC 3986. Do not arbitrarily strip path segments, alter the host, or change the scheme without an agreed contract. For systems behind a reverse proxy/load balancer, ensure the server compares the **public URI actually called by the Client** against a URI reconstructed from trusted request metadata.

### 2.4. §ath§ Is the Hash of the Access Token

When sending an access token to the Resource Server, the proof must include:

~~~text
ath = BASE64URL-NOPAD(SHA-256(ASCII(access_token_value)))
~~~

This hash binds the proof to the **exact access token being presented**. If the Client sends token A while the proof was created for token B, the Resource Server must reject it.

Do not confuse §ath§ with:

- The hash of the public key.
- The hash of the entire HTTP request body.
- The hash of the refresh token.
- The hash of the §Authorization: DPoP ...§ string.

### 2.5. §cnf.jkt§ in the Access Token

When the Authorization Server accepts a proof during token issuance, it binds the access token to the public key. For a JWT access token, the structure typically looks like:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893459600,
  "cnf": {
    "jkt": "<RFC7638-JWK-SHA256-THUMBPRINT>"
  }
}
~~~

§jkt§ is the **RFC 7638 JWK SHA-256 thumbprint** of the public key used to sign the DPoP proof. Do not substitute an arbitrary hash of PEM, DER, or a JSON string serialized in a non-standard order. For opaque access tokens, the Resource Server must retrieve the corresponding binding information from the introspection response according to the Authorization Server's contract.

## 3. DPoP Access Token Issuance Flow

DPoP starts right at the token endpoint. The Client creates a proof for the authorization code exchange or other grant request:

~~~http
POST /oauth2/token HTTP/1.1
Host: identity.example.test
Content-Type: application/x-www-form-urlencoded
DPoP: <signed-dpop-proof-jwt>

grant_type=authorization_code&
code=<authorization-code>&
redirect_uri=https%3A%2F%2Fshop.example.test%2Fcallback&
client_id=shop-web&
code_verifier=<pkce-verifier>
~~~

The Authorization Server:

1. Verifies the DPoP proof JWT.
2. Checks §typ§, §alg§, public JWK, signature, and claims.
3. Checks method/URI/timestamp/nonce if required.
4. Computes the JWK thumbprint of the public key.
5. Issues an access token bound to that thumbprint.

Illustrative response:

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

**§token_type§ must report §DPoP§** so the Client knows the token must be presented using the DPoP scheme along with a proof. The Client should not change `token_type` to Bearer or send the same token via another scheme.

### 3.1. Token Request Proofs Differ from Resource Request Proofs

At the token endpoint, the proof is bound to the token-issuing endpoint and the grant exchange request. It does not contain §ath§ for the new access token, because the token has not been issued yet before the request completes.

On a protected resource request, the access token already exists, so the proof must include §ath§ to bind the proof to that specific token.

### 3.2. Refresh Tokens Also Require Proofs

RFC 9449 applies DPoP proofs to access-token requests, including the §refresh_token§ grant. The Client must continue using the bound key or follow a key/token rotation workflow supported by the Authorization Server. Do not send a refresh token through a proofless flow if the AS requires DPoP.

## 4. Calling the Resource Server with DPoP

After receiving the access token, the Client generates a **new proof for each protected request**:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: DPoP <dpop-bound-access-token>
DPoP: <new-signed-dpop-proof-jwt>
Accept: application/json
~~~

The Resource Server verifies:

1. Exactly one DPoP header and one valid proof JWT are present.
2. The proof has §typ=dpop+jwt§, a valid asymmetric algorithm, and a public JWK containing no private key.
3. The proof signature verifies with the public JWK.
4. §htm§ matches the actual method.
5. §htu§ matches the actual URI after normalization and removing query/fragment.
6. §iat§ is within the accepted time window.
7. §jti§ has not been reused within the proof acceptance window.
8. If the server requires a nonce, §nonce§ matches a recent nonce issued by that exact server.
9. §ath§ matches the hash of the sent access token.
10. The public-key thumbprint in the proof matches §cnf.jkt§ in the access token or corresponding introspection metadata.
11. The access token remains valid according to issuer, audience, expiry, scope, and other validators.

~~~mermaid
flowchart TD
    A["Authorization: DPoP token + DPoP proof"]
    B["Parse access token and proof"]
    C{"Proof JWT valid format, typ, alg?"}
    D{"Proof signature valid?"}
    E{"htm, htu, iat, and nonce valid?"}
    F{"jti not replayed and ath matches?"}
    G["Verify access token"]
    H{"cnf.jkt matches proof public key?"}
    I["Create DPoP Authentication"]
    J["401 / DPoP challenge"]
    K["HTTP authorization: scope/role"]
    L["Business/resource authorization"]
    M["Return resource"]

    A --> B --> C
    C -->|No| J
    C -->|Yes| D
    D -->|No| J
    D -->|Yes| E
    E -->|No| J
    E -->|Yes| F
    F -->|No| J
    F -->|Yes| G --> H
    H -->|No| J
    H -->|Yes| I --> K --> L --> M
~~~

This is a conceptual diagram. Implementations may execute steps in a different order, but must not omit any check required by the RFC or token contract.

## 5. Handling Nonces and Replay

### 5.1. Nonces Are Server-Issued Challenges

The Authorization Server or Resource Server can require the Client to use a fresh nonce. The server returns the header:

~~~http
DPoP-Nonce: <opaque-server-nonce>
~~~

The Client must create the next proof with the claim:

~~~json
{
  "jti": "new-unique-proof-id",
  "htm": "GET",
  "htu": "https://api.example.test/api/orders/42",
  "iat": 1893456015,
  "ath": "<token-hash>",
  "nonce": "<opaque-server-nonce>"
}
~~~

The nonce is an opaque value to the Client. The Client does not decode, modify, or reuse server A's nonce for server B.

### 5.2. Authorization Server and Resource Server Have Separate Nonces

A nonce from the Authorization Server must only be used for requests to that Authorization Server. A nonce from a Resource Server must only be used with the Resource Server that issued it. If the Client calls multiple APIs or multiple issuers, nonces must be stored per **server origin/endpoint context**; do not use a single global variable for all servers.

### 5.3. §jti§ and the Replay Cache

A DPoP proof can be stolen and replayed at the same endpoint within the time window. The RFC requires servers to limit proof age; storing used §jti§ values is a strong control to reject duplicate proofs.

In multi-instance environments:

- An in-memory replay cache on a single instance may be insufficient if the second request hits a different instance.
- Use a shared cache/store or a distributed anti-replay mechanism matching your SLA and threat model.
- The replay entry TTL must cover at least the proof acceptance window.
- Cache keys should be scoped to the appropriate proof context to prevent collisions across issuers/servers.
- Bound §jti§ length and entry count to prevent memory exhaustion.
- Evict entries only after the proof is no longer accepted.

A nonce can reduce the window in which a proof can be pre-generated too far in advance, but **a nonce does not replace §jti§-based replay tracking**.

### 5.4. Clock Skew

§iat§ relies on the Client's clock. The server must define a reasonable acceptance window, and system clocks must be synchronized. A window that is too wide allows proofs to be replayed longer; one that is too narrow causes valid requests to fail due to clock drift.

Server-provided nonces can help reduce reliance on Client clocks. Monitor clock drift and test cases where proofs are too old or too far in the future.

## 6. DPoP Does Not Bypass Normal Authorization

DPoP only proves the Client possesses the private key bound to the token. It **does not grant business permissions**.

For example, a token contains:

~~~json
{
  "scope": "orders.read",
  "aud": ["orders-api"],
  "cnf": {
    "jkt": "<client-key-thumbprint>"
  }
}
~~~

A valid proof lets the request pass authentication, but an order-cancellation endpoint still requires §SCOPE_orders.cancel§ or the appropriate permission. The user must also have authorization on the specific Order, owner, tenant, and business state.

| Layer | Question |
| --- | --- |
| Token validation | Was the token issued by a trusted issuer, for the right audience, and is it unexpired? |
| DPoP proof | Does the Client hold the matching private key, and is the proof bound to the right request/token? |
| Scope/authority | Does the token have permission to perform this type of operation? |
| Tenant/resource policy | Does the caller have permission on the specific resource? |
| Business rule | Does the order's state allow the operation? |

**Do not treat DPoP authentication as authorization.** A valid proof does not turn a reader user into an order admin.

## 7. Support Scope by Spring Security Version

The milestones below distinguish the **DPoP authentication classes**, **configuration APIs**, and **Servlet/WebFlux scope**. These are frequently conflated during upgrades.

| Version | DPoP Resource Server | Dedicated DPoP Config API | Notes |
| --- | --- | --- | --- |
| **6.4.x and older** | No built-in §DPoPAuthenticationProvider§ | No | Requires custom integration or another solution; do not assume the default Bearer Resource Server automatically verifies proofs |
| **6.5.x** | Includes DPoP Resource Server classes; §DPoPAuthenticationProvider§/§DPoPAuthenticationToken§ marked §@since 6.5§ | No fluent §dPoP(...)§ configurer yet | The 6.5 branch includes DPoP documentation; resource-server tests use the JWT DSL and DPoP scheme/proof |
| **7.0.x** | DPoP-bound access tokens remain documented | No §DPoPConfigurer§ API (§@since 7.1§) | Do not copy new 7.1 DSL syntax into 7.0 |
| **7.1.x** | Includes DPoP Resource Server | Includes §OAuth2ResourceServerConfigurer.dPoP(...)§ | Allows customizing request matcher, authentication converter, and success/failure handlers |
| **7.2.0-RC1 / preview** | Inherits prior support | Adds proof verifier factory customization via preview API | Use only per actual release status; do not treat RC as stable |

### 7.1. Spring Security 6.4 and Older

The official API for §DPoPAuthenticationProvider§ states §Since: 6.5§. Therefore, 6.4 and earlier releases do not include the same built-in DPoP Resource Server provider. An application configured only with:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults()))
~~~

is still using **JWT Bearer validation**. Do not claim an endpoint verifies DPoP merely because requests carry an extra §DPoP§ header. If DPoP support is mandatory on an older release, you must implement or integrate a reviewed solution: proof decoder, binding check, replay/nonce policy, scheme downgrade protection, and corresponding tests.

### 7.2. Spring Security 6.5

This is the milestone introducing DPoP Resource Server support in Spring Security:

- §DPoPAuthenticationProvider§ is added with §@since 6.5§.
- §DPoPAuthenticationToken§ represents the authentication for a protected resource request.
- §DPoPProofJwtDecoderFactory§ is available for verifying proof JWTs.
- The 6.5 documentation includes the **OAuth 2.0 DPoP-bound Access Tokens** page.
- DPoP Resource Server tests in the 6.5 line demonstrate §Authorization: DPoP§ requests and the §DPoP§ header; test configurations use the JWT Resource Server DSL.

Example JWT Resource Server configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ResourceServerSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This snippet shows a basic JWT Resource Server configuration. In 6.5, **do not add §.dPoP(...)§** because that fluent configurer does not yet exist in the 6.5 API. In production deployments, test DPoP requests against the exact patch version and your system's token profile/issuer; do not test only regular Bearer JWTs.

### 7.3. Spring Security 7.0

The 7.0 branch continues to document DPoP-bound access tokens for Servlet Resource Server. However, the nested class §OAuth2ResourceServerConfigurer.DPoPConfigurer§ is marked **§Since: 7.1§**. Therefore, do not take a §.dPoP(...)§ example and expect it to compile on 7.0.

When deeper configuration is required on 7.0, check the API and behavior of the exact minor/patch version in use. Do not invent a fake extension method named §dPoP§ and treat it as framework API.

### 7.4. Spring Security 7.1

Spring Security 7.1 adds the fluent API:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DPoPResourceServerSecurity {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
                .dPoP(Customizer.withDefaults()))
            .build();
    }
}
~~~

The API method name is **§dPoP§** (with an uppercase P in the middle), not §dpop§. §DPoPConfigurer§ in 7.1 allows customizing:

- §requestMatcher(...)§: determines which requests belong to the DPoP flow.
- §authenticationConverter(...)§: converts requests into a §DPoPAuthenticationToken§.
- §authenticationSuccessHandler(...)§: handles post-authentication success.
- §authenticationFailureHandler(...)§: handles proof/token errors.

These options do not replace access-token validators and do not configure the Authorization Server. Use them when you need integration with specific request routing, failure responses, or custom converters.

### 7.5. Spring Security 7.2 Preview

The 7.2 preview API adds the ability to configure a §JwtDecoderFactory<DPoPProofContext>§ for the proof verifier via the DPoP configurer. This is useful if a deployment requires a custom proof validation policy, decoder factory, or context-specific clock/skew controls.

**However, RC/SNAPSHOT releases are not stable releases.** Before using them in production, verify the GA version, final API, compatibility matrix, and release notes for the corresponding patch. Do not copy preview APIs into a project still running 7.1.

### 7.6. WebFlux/Reactive Resource Server

WebFlux Resource Server documentation describes §ReactiveJwtDecoder§ and §ReactiveOpaqueTokenIntrospector§ for JWT/opaque tokens. However, the DPoP configurer API is exposed on **Servlet/HttpSecurity's** §OAuth2ResourceServerConfigurer§, using synchronous §HttpServletRequest§, §AuthenticationFilter§, and §AuthenticationProvider§.

Therefore, for the versions referenced here:

- Do not assume §ServerHttpSecurity.oauth2ResourceServer().jwt()§ automatically verifies DPoP proofs.
- Do not send a proof to a WebFlux API and assume the token is sender-constrained.
- If DPoP is needed in WebFlux, verify support in the specific release/library in use or implement a reactive authentication pipeline with full proof validation, binding, nonce/replay handling, and tests.
- Do not call §block()§ to invoke a synchronous DPoP verifier on the Netty event loop as a shortcut.

### 7.7. Spring Security OAuth2 Client and Authorization Server Are Separate Components

The DPoP protocol involves three roles:

1. **Client** generates proofs for the token endpoint and each resource request.
2. **Authorization Server** verifies the proof at the token endpoint and binds the key thumbprint into the access token.
3. **Resource Server** verifies the proof and access-token binding on protected requests.

Spring Security's DPoP documentation in the Resource Server section demonstrates support on the **API side receiving tokens**. Do not assume §oauth2Client()§ automatically generates DPoP proofs for every token request or WebClient call. Verify the specific client/provider or use a custom token-response client/request interceptor.

Similarly, **Spring Authorization Server is a separate project**. Its Protocol Endpoints documentation includes a DPoP-bound Access Tokens section; the Authorization Server's version and configuration must be checked independently of the Spring Security Resource Server version.

## 8. Configuring DPoP on Servlet Resource Server

### 8.1. Dependencies

With Spring Boot, the Resource Server dependency is typically:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

For JWT decoding, Spring Security uses the corresponding JOSE module via dependency management. To maintain compatibility, use the **Spring Boot BOM or Spring Security BOM** rather than mixing Spring Security modules from different minor/patch versions.

### 8.2. Configuring the JWT Issuer

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
          jwk-set-uri: https://identity.example.test/oauth2/jwks
~~~

These are illustrative values. The Resource Server must still verify the issuer, signature, expiration, audience, and access token profile according to the contract. A valid DPoP proof cannot rescue an access token with the wrong issuer or intended for a different API.

### 8.3. 7.1+ Configuration with the DPoP Configurer

~~~java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
            .dPoP(Customizer.withDefaults()))
        .build();
}
~~~

This is a 7.1+ Servlet configuration illustrating the DPoP path. For applications that accept DPoP-bound tokens only on certain routes, configure §requestMatcher§ per contract and test the remaining routes. Avoid configuring a route that accidentally allows Bearer fallback and strips away the sender constraint.

### 8.4. Customizing the Matcher

Conceptual example:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
    .dPoP(dpop -> dpop
        .requestMatcher(request ->
            request.getRequestURI().startsWith("/api/dpop/"))))
~~~

This snippet only illustrates where to customize. In a real application, the matcher must account for HTTP method, routes, proxy/path normalization, and token policy. Do not use a broad matcher if other endpoints still accept Bearer tokens for the same resources unintentionally.

### 8.5. DPoP and the JWT Decoder Are Two Separate Layers

§JwtDecoder§ verifies the access token JWT. The DPoP verifier verifies the proof JWT. The two JWTs have different purposes, issuers/keys, and validation rules:

| JWT | Who Signs It? | Who Verifies It? | Purpose |
| --- | --- | --- | --- |
| Access token JWT | Authorization Server | Resource Server | Token claims and permissions |
| DPoP proof JWT | Client | Authorization Server or Resource Server | Proves the Client holds the private key and binds the request |

Do not use the regular access-token decoder to accept a proof as an access token, and do not use the public key inside the proof in place of the issuer's key when verifying an access-token signature.

## 9. JWT and Opaque Token Binding

### 9.1. JWT Access Tokens

For JWTs, the Resource Server reads §cnf.jkt§ from the verified claims:

~~~json
{
  "iss": "https://identity.example.test",
  "aud": ["orders-api"],
  "sub": "user-42",
  "scope": "orders.read",
  "exp": 1893459600,
  "cnf": {
    "jkt": "abc123..."
  }
}
~~~

The proof contains the public JWK. The server computes the RFC 7638 thumbprint and compares it with §cnf.jkt§. If they differ, reject the request.

### 9.2. Opaque Access Tokens

For opaque tokens, the Resource Server cannot read JWT claims directly. The introspection endpoint must provide metadata identifying which key the token is bound to, typically via §cnf.jkt§:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "aud": ["orders-api"],
  "sub": "user-42",
  "cnf": {
    "jkt": "abc123..."
  }
}
~~~

This response is a contract example; not every introspection response has the exact same fields. If the AS does not provide the required binding metadata, the Resource Server cannot properly verify the proof key against the access token.

### 9.3. Active Does Not Mean DPoP-Bound

An introspection response with §active=true§ only indicates the token is still active according to the AS. If the token lacks §cnf.jkt§ or contract-defined binding metadata, you cannot assume it is a DPoP-bound token. The Resource Server needs to distinguish:

- Regular Bearer tokens.
- DPoP-bound tokens with key binding.
- Invalid tokens or tokens with insufficient metadata.

## 10. Example: Creating a DPoP Proof with Nimbus

A proof JWT can be created with a JOSE library such as Nimbus. The following example illustrates the **structure**, not a complete production client:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.UUID;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

import java.time.Instant;

public final class DPoPProofFactory {

    private final RSAKey clientKey; // Holds both private/public key on the Client side
    private final JwtEncoder proofEncoder;

    public DPoPProofFactory(RSAKey clientKey) {
        this.clientKey = clientKey;
        JWKSource<SecurityContext> jwkSource =
            (selector, context) ->
                selector.select(new JWKSet(clientKey));
        this.proofEncoder = new NimbusJwtEncoder(jwkSource);
    }

    public String createResourceProof(
            String method,
            String targetUriWithoutQueryOrFragment,
            String accessToken) throws Exception {

        String ath = sha256Base64Url(accessToken);

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .type("dpop+jwt")
            .jwk(clientKey.toPublicJWK().toJSONObject())
            .build();

        JwtClaimsSet claims = JwtClaimsSet.builder()
            .id(UUID.randomUUID().toString())
            .issuedAt(Instant.now())
            .claim("htm", method)
            .claim("htu", targetUriWithoutQueryOrFragment)
            .claim("ath", ath)
            .build();

        return this.proofEncoder
            .encode(JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    private static String sha256Base64Url(String token)
            throws Exception {
        MessageDigest sha256 = MessageDigest.getInstance("SHA-256");
        byte[] digest = sha256.digest(
            token.getBytes(StandardCharsets.US_ASCII));
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);
    }
}
~~~

Notes when using this code:

- The example uses RSA/RS256 for readability; the actual algorithm must comply with RFC 9449, key type, and AS/RS policy.
- §clientKey§ must be loaded from a key store/secure storage; never hardcode private keys in source code.
- §targetUriWithoutQueryOrFragment§ must be the actual request URI per RFC, not an arbitrary unrelated URL.
- Generate a **new proof for every request**; do not reuse proofs from previous requests.
- For the token endpoint, generate a dedicated proof for the token endpoint's method/URI and do not add §ath§ as in a protected-resource proof.
- If the server returns §DPoP-Nonce§, include the §nonce§ claim with the exact value provided by the server.
- The thumbprint compared against §cnf.jkt§ must be calculated as an **RFC 7638 JWK thumbprint**, not with the §sha256Base64Url§ helper shown here; that helper is solely for §ath§.

## 11. How to Test DPoP

DPoP testing should not stop at a single successful request. You must prove the token is bound to the right key and the proof is bound to the right request.

### 11.1. Test Matrix

| Test | Access token | Proof | Result |
| --- | --- | --- | --- |
| Happy path | DPoP-bound token, valid §cnf.jkt§ | Proof with matching key, method, URI, iat, jti, ath | Authenticated; proceeds to authorization |
| Missing proof | DPoP-bound | No §DPoP§ header | Rejected |
| Wrong scheme | DPoP-bound | Token sent under §Bearer§ | Rejected, prevents downgrade |
| Different public key | §cnf.jkt§ of key A | Proof signed with key B | Rejected |
| Invalid signature | Valid token binding | Invalid proof signature | Rejected |
| Wrong typ | Valid token binding | §typ§ is not §dpop+jwt§ | Rejected |
| Disallowed algorithm | Valid token binding | §alg=none§ or disallowed algorithm | Rejected |
| Private JWK leaked in header | Valid token binding | §jwk§ contains private parameters | Rejected |
| Wrong method | Valid token binding | §htm§ differs from HTTP method | Rejected |
| Wrong URI | Valid token binding | §htu§ differs from target URI | Rejected |
| Wrong token hash | Token A | Proof has §ath§ of token B | Rejected |
| Proof outside time window | Valid token | §iat§ too old / too far in the future | Rejected |
| Replay | Valid token | Previously used §jti§ | Rejected per replay policy |
| Missing nonce | Server requires nonce | Proof lacks §nonce§ | Challenged/rejected per RFC |
| Wrong nonce | Server issued nonce N | Proof uses nonce M | Rejected |
| Duplicate header | Valid token | Multiple §DPoP§ headers | Rejected |
| Expired token | Expired token | Valid proof | Rejected by token validation |
| Missing scope | Valid DPoP-bound token | Valid proof | Authentication may pass; authorization returns 403 |

### 11.2. Testing §cnf.jkt§ Mismatch

Setup:

- Client key A.
- Client key B.
- Access token with §cnf.jkt§ of A.
- Proof signed with A and proof signed with B.

Expected:

~~~text
Token cnf.jkt = thumbprint(A)
Proof public JWK = A -> pass DPoP authentication
Proof public JWK = B -> fail DPoP authentication
~~~

This is the single most important test to prove sender constraint enforcement works. If tests only check that the proof signature is valid without comparing against the access token binding, an attacker could use any arbitrary key to generate proofs.

### 11.3. Testing Downgrade Prevention to Bearer

A dangerous flaw occurs when a DPoP-bound token is still accepted if the Client sends:

~~~http
Authorization: Bearer <dpop-bound-access-token>
~~~

A DPoP-bound token must be presented using the DPoP scheme along with a proof. If the same endpoint allows Bearer fallback without verifying the binding, an attacker can bypass the proof check. Tests must confirm that **a DPoP-bound token cannot be downgraded** to Bearer.

### 11.4. Testing Replay Across Multiple Instances

Suppose proof P is accepted at instance A. Resend P to instance B within the valid time window. If the system guarantees replay protection using a shared store, the second request must be rejected. Single-node tests are insufficient to prove distributed replay protection.

### 11.5. Testing Nonces

A test sequence:

1. Send a request without a nonce while the RS requires a nonce.
2. Verify the response contains §DPoP-Nonce§ and error §use_dpop_nonce§ per contract.
3. The Client generates a new proof containing the received nonce.
4. Resend the request with the new proof.
5. Verify success if all other conditions hold.
6. Try a nonce from a different Resource Server; it must be rejected.

### 11.6. MockMvc and Signed Proofs

In the Servlet stack, you can use MockMvc with a test key pair:

~~~java
mockMvc.perform(get("/api/orders/42")
        .header("Authorization", "DPoP " + accessToken)
        .header("DPoP", proof))
    .andExpect(status().isOk());
~~~

This is only the request portion of the test; §accessToken§ must be signed by a test issuer key and contain the right §cnf.jkt§, while §proof§ must be signed by the matching private key with the right §htm§/§htu§/§ath§. Do not use fake JWT strings or mock `Authentication` directly if the goal is to verify proof validation.

## 12. Proxies, Load Balancers, and URI Canonicalization

DPoP proofs are bound to §htu§. When the Client calls:

~~~text
https://api.example.test/orders/42
~~~

but the reverse proxy forwards to the backend:

~~~text
http://orders-service:8080/orders/42
~~~

the Resource Server may observe a different scheme/host than the URI signed by the Client. If the comparison mismatches, valid requests are rejected; if attacker-controlled forwarded headers are trusted, an attacker can manipulate the URI context.

You need to:

- Configure trusted proxies and proper forwarded-header handling.
- Trust §Forwarded§/§X-Forwarded-*§ only from trusted proxies.
- Reconstruct the external URI under the same contract used by the Client.
- Test HTTPS termination, host rewriting, path prefixes, and ports.
- Never disable §htu§ validation just to bypass proxy errors.
- Apply RFC URI normalization rather than stripping components arbitrarily.

## 13. Limitations and Risks of DPoP

### 13.1. If an Attacker Obtains Both the Token and the Private Key

DPoP does not protect when an attacker compromises the Client or obtains **both the access token and the private key**. Private key protection is central to the design.

### 13.2. XSS Can Still Abuse the DPoP Key Through the Application

In an SPA/browser, if a malicious script runs on the same origin and can call the signing API or invoke the proof-signing code, it can construct valid DPoP requests even without exporting the private key. DPoP mitigates token replay from other devices; it does not eliminate XSS.

### 13.3. Does Not Replace TLS

DPoP is an application-layer mechanism. HTTPS/TLS must still be used to protect the confidentiality and integrity of requests/responses, tokens, proofs, and user data.

### 13.4. Does Not Replace Access-Token Lifetime and Revocation

Tokens still require TTLs, minimal scopes, proper audiences, and policy-based rotation/revocation. If a key is lost or compromised, the Client may need to revoke tokens and register a new key. DPoP does not provide a key lifecycle management process on its own.

### 13.5. Proof Replay Can Still Occur Within the Acceptance Window

If an attacker captures a proof before it expires and the server does not track replay, the attacker can attempt to replay the proof against the exact same endpoint/method. Time windows, a §jti§ store, and nonces help mitigate this risk.

### 13.6. CORS Is Not DPoP Validation

DPoP does not replace CORS, CSRF, or authorization. CORS controls browser cross-origin access; DPoP verifies proof keys; scope/resource policies govern permissions. If an API uses cookies/sessions as credentials, CSRF must still be addressed.

## 14. Implementation Responsibilities by Role

| Role | DPoP Responsibility | What Must Be Tested |
| --- | --- | --- |
| OAuth2 Client | Hold private key, create proofs for token/resource requests, handle nonces | Fresh proofs, accurate URI/method/ath, key rotation |
| Authorization Server | Verify proofs at token endpoint, bind public-key thumbprint into tokens | §token_type=DPoP§, §cnf.jkt§, nonces, grants/refreshes |
| Resource Server | Verify proofs and access-token binding | §htm§, §htu§, §ath§, §jti§, nonces, token validation |
| API gateway/proxy | Forward headers and external URI accurately | Do not drop DPoP header, do not corrupt forwarded host/scheme |
| Key management | Protect private keys, rotation, and revocation | Do not log/export keys, handle key loss |

A system that enables DPoP only at the Resource Server while the Authorization Server still issues **standard Bearer tokens** has not created DPoP-bound tokens. Likewise, if the Client sends a §DPoP§ header while the AS does not attach §cnf.jkt§ and the RS does not verify binding, it is merely a header with no sender-constraining value.

## 15. Common Implementation Mistakes

### 15.1. Using §Bearer§ for a DPoP-Bound Token

A DPoP-bound token must be presented with the §DPoP§ scheme. Accepting it as Bearer without a proof creates a downgrade path.

### 15.2. Reusing One Proof Across Multiple Requests

A proof is bound to a specific method/URI/token hash and unique ID. Generate a new proof for each request; do not cache proofs like access tokens.

### 15.3. Omitting §ath§ on Resource Requests

If the proof is not bound to the current access token, the proof could be misused with another token. §ath§ is a required claim when a DPoP proof accompanies an access token to a protected resource.

### 15.4. Using the Wrong Hash for §ath§

§ath§ is base64url-without-padding of SHA-256 over the **ASCII bytes of the access-token value**. Do not hash a JSON string, the Authorization header, or a JWK.

### 15.5. Using an Arbitrary Hash Instead of §cnf.jkt§

§jkt§ must be an RFC 7638 JWK thumbprint. An arbitrary DER/PEM hash is not equivalent.

### 15.6. Failing to Verify URIs Behind a Reverse Proxy

If the server compares §htu§ against an internal URI while the Client signed the external URI, valid requests may fail. Do not solve this by disabling the check; configure proxy trust and URI reconstruction.

### 15.7. Checking Only the Proof Signature

A valid proof signature is not enough. You must also verify §typ§, §alg§, public-only §jwk§, §htm§, §htu§, §iat§, §jti§, §ath§, nonce, and key binding.

### 15.8. Not Persisting Replay State Across a Cluster

A local replay cache will not detect a proof already used at another instance. Design storage and TTL to fit your topology.

### 15.9. Using a Nonce from the Wrong Server

The AS nonce and RS nonce are separate namespaces. Do not share nonces across issuers or resource servers.

### 15.10. Confusing DPoP with PKCE

PKCE does not sender-constrain access tokens. DPoP does not replace authorization code protection. Both can—and often should—be used together.

### 15.11. Confusing DPoP Resource Server with OAuth2 Client

§DPoPAuthenticationProvider§ authenticates incoming requests on the Resource Server. Do not assume §oauth2Client()§ automatically generates proofs for token endpoints or downstream requests.

### 15.12. Using the 7.1 DSL on 6.5/7.0

§OAuth2ResourceServerConfigurer.dPoP(...)§ has §@since 7.1§. Do not use this method when compiling against 6.5 or 7.0.

### 15.13. Assuming WebFlux Has DPoP Just Because It Supports JWT

Reactive JWT decoding and DPoP proof validation are two different features. Verify reactive DPoP APIs in the exact version you use; do not run Servlet providers on the Netty event loop.

### 15.14. Letting Regular Access Tokens Pass DPoP Endpoints Without Clear Policy

An endpoint may support multiple token types, but there must be a clear policy on schemes and bindings. Do not configure a matcher/filter chain that lets a DPoP-bound token fall back onto the Bearer path.

### 15.15. Treating DPoP as a Replacement for All Other Protections

DPoP does not replace TLS, scopes, audience checks, tenant/owner authorization, CSRF when using cookies, XSS protection, key management, or revocation.

## 16. Implementation Checklist

### Authorization Server

- [ ] Accept DPoP proofs at the token endpoint per RFC 9449.
- [ ] Verify §typ§, §alg§, public JWK, signature, §htm§, §htu§, §iat§, §jti§, and nonce when required.
- [ ] Attach the key thumbprint to the access token via §cnf.jkt§ or introspection metadata.
- [ ] Return §token_type=DPoP§.
- [ ] Enforce appropriate nonce and replay policies.
- [ ] Handle the refresh-token grant according to DPoP policy.

### OAuth2 Client

- [ ] Generate and protect the private key.
- [ ] Create a fresh proof for the token request and each resource request.
- [ ] Use the correct method and URI; omit query/fragment from §htu§.
- [ ] Include §ath§ for protected-resource proofs.
- [ ] Send §Authorization: DPoP§ and the §DPoP§ header.
- [ ] Handle §DPoP-Nonce§ scoped to the issuing server.
- [ ] Never log tokens, proofs, or private keys.
- [ ] Have a key rotation/revocation process.

### Resource Server

- [ ] Use a Spring Security version with appropriate DPoP support.
- [ ] Verify the access token independently of the proof.
- [ ] Verify the proof JWT and public-key binding.
- [ ] Check §ath§, §htm§, §htu§, §iat§, §jti§, and nonce.
- [ ] Reject duplicate DPoP headers.
- [ ] Prevent downgrading DPoP-bound tokens to Bearer.
- [ ] Use a suitable replay cache when running in a cluster.
- [ ] Configure proxies and forwarded headers properly.
- [ ] Check scopes, audience, tenant, owner, and business policies after authentication.

### Spring Security Version

- [ ] 6.5+: verify the API/provider exists in your patch version.
- [ ] 7.0: do not use fluent §dPoP(...)§ if the 7.1 API is not present.
- [ ] 7.1+: use the §dPoP§ DSL properly and test matcher/handlers.
- [ ] 7.2 preview: use proof verifier customization only if the release is approved.
- [ ] WebFlux: verify separate reactive DPoP support; do not infer it from reactive JWT support.

## 17. Practice Scenarios

**Scenario A — Stolen access token:** An attacker has the access token but not the Client's private key. With DPoP, can the attacker use the token via a Bearer header?

**No.** A DPoP-bound token must be presented using the §DPoP§ scheme and a valid proof bound to the key. If the API still accepts it through the Bearer path, check downgrade protection.

**Scenario B — Valid proof, wrong token audience:** The proof has a valid signature and correct §htm§/§htu§/§ath§, but the access token is for §billing-api§. Will the Orders API allow it?

**No.** A DPoP proof does not replace audience validation. The token must be issued for the Resource Server receiving the request.

**Scenario C — Client sends a GET proof for a POST:** Token and key are right, but §htm§ is GET while the request is POST. Result?

**Rejected.** The proof is bound to the request's HTTP method.

**Scenario D — Client adds a query parameter:** The request has §?page=2§, yet §htu§ omits the query. Is that wrong?

Not necessarily. Per the RFC, §htu§ omits the query and fragment. The remaining parts of the URI must still match after normalization.

**Scenario E — Replaying the same proof:** A proof succeeds on instance A, then is replayed with the same method/URI/token to instance B. What if the system guarantees distributed replay detection?

The second request must be rejected because §jti§ has already been used. A per-instance in-memory replay cache may be insufficient.

**Scenario F — AS requires a nonce:** The Client receives §DPoP-Nonce§ from the AS. Can it reuse that nonce when calling the Orders API?

**No.** A nonce belongs to the server that issued it; an AS nonce is not a Resource Server nonce.

**Scenario G — Spring Security 6.5:** A developer copies §.dPoP(Customizer.withDefaults())§ from a 7.1 example. What happens?

That method does not belong to the 6.5 API. Use APIs available in your version or upgrade; do not add fake extensions to mimic framework APIs.

**Scenario H — Spring Security 7.1:** The API needs a custom request matcher and failure handler for DPoP. Which API should be used?

Use §OAuth2ResourceServerConfigurer.dPoP(...)§ and customize §DPoPConfigurer§. This API is available from 7.1.

**Scenario I — WebFlux:** An application uses §ReactiveJwtDecoder§, so a developer assumes DPoP proofs are automatically verified as well. Conclusion?

That cannot be inferred. Verify DPoP support for the exact WebFlux release or build a custom reactive authentication pipeline.

**Scenario J — XSS:** A malicious script running inside the Client can call the API via the DPoP signing code without exporting the private key. Does DPoP stop it?

Not necessarily. DPoP reduces token misuse from devices without the key, but a script controlling the Client can abuse the application's proof-signing capability. XSS defenses and key protection remain essential.

**Scenario K — Missing scope:** Proof and token are both valid and key binding matches, yet the token only has §orders.read§. Is an order-cancellation request allowed?

No. Successful DPoP authentication does not grant §orders.cancel§. Authorization must still deny it.

**Scenario L — Opaque token:** AS introspection returns §active=true§ without §cnf.jkt§ or key binding info. Can the Resource Server confirm the token is DPoP-bound?

No, unless another trusted metadata contract provides the binding. §active=true§ does not prove the token is bound to the public key in the proof.

---

## Conclusion

**DPoP under RFC 9449 binds an access token to a public key and requires the Client to sign a proof for every request.** The proof must bind the method, URI, timestamp, unique ID, and access token hash; the Resource Server must also compare the public-key thumbprint in the proof against §cnf.jkt§ or introspection metadata. This mechanism reduces the risk of standalone access-token theft, but does not replace TLS, access-token validation, scopes, tenant/resource authorization, key management, or XSS protection.

In Spring Security, **6.5 is the milestone that introduces §DPoPAuthenticationProvider§ and DPoP Resource Server support**; DPoP documentation continues in 7.0. **Fluent §OAuth2ResourceServerConfigurer.dPoP(...)§ and §DPoPConfigurer§ are available from 7.1**, allowing customization of matchers/converters/handlers; a proof-verifier factory API appears in the 7.2 preview. The documentation/APIs referenced are for **Servlet Resource Server**; do not treat Reactive JWT support as evidence that WebFlux already supports DPoP. Test your exact version, the §Authorization: DPoP§ scheme, key binding, §ath§, nonce/replay handling, and downgrade protection before claiming an API is sender-constrained.

## References

1. [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html)
2. [Spring Security 6.5 — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/dpop-tokens.html)
3. [Spring Security 6.5 — What's New](https://docs.spring.io/spring-security/reference/6.5/whats-new.html)
4. [Spring Security 6.5 API — DPoPAuthenticationProvider](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/DPoPAuthenticationProvider.html)
5. [Spring Security 7.1 — OAuth 2.0 DPoP-bound Access Tokens](https://docs.spring.io/spring-security/reference/7.1/servlet/oauth2/resource-server/dpop-tokens.html)
6. [Spring Security 7.1 API — DPoPConfigurer](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.DPoPConfigurer.html)
7. [Spring Authorization Server — Protocol Endpoints / DPoP-bound Access Tokens](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)
