# `private_key_jwt` and Client Public Key Distribution

> **Chapter: Client Authentication.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module and focuses on designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in Spring Boot. This material explains how a **confidential client** proves its identity using a JWT signed with its own **private key**, how the Authorization Server looks up the registered **public key** for verification, and how to manage keys across environments.

## 1. The Problem: Avoiding a Shared Client Secret for Client Authentication

In `client_secret_basic`, a confidential client proves its identity with `client_id` and a **shared secret** known to the Authorization Server. With **`private_key_jwt`**, the client signs a short-lived **JWT client assertion** using its private key and sends that JWT to the token endpoint. The Authorization Server retrieves the **trusted public key of that specific client** to verify the signature and claims; the server **never needs to hold the private key** and does not need a shared client secret to authenticate this client.

Running example throughout:

- **Authorization Server (AS):** `https://login.example.vn`, fixed issuer `https://login.example.vn`, token endpoint `https://login.example.vn/oauth2/token`.
- **Confidential client:** the `reporting-service` service, using `grant_type=client_credentials` to request scope `reports.read`.
- **Client's public JWKS:** `https://keys.example.vn/clients/reporting-service/jwks.json`.
- **Client private key:** stored in a secret store/keystore/HSM/KMS where only the `reporting-service` workload is authorized to sign.
- **Resource Server:** `https://reports-api.example.vn`, receiving **access tokens issued by the AS** and verifying API access permissions.

| Client authentication method | What the client holds | What the Authorization Server uses | When to consider |
|---|---|---|---|
| `client_secret_basic` | Shared secret | Secret hash in `RegisteredClient` | Simple confidential clients with secret distribution and rotation channels |
| `client_secret_jwt` | Shared secret used as MAC key | Corresponding secret to verify HMAC | Systems already supporting JWT client assertions that still use shared secrets |
| **`private_key_jwt`** | **Private key** to sign JWT assertions | **Public key** registered via JWKS / trusted source | Confidential services wanting separation between signing and verification, leveraging key management infrastructure |
| `tls_client_auth` / `self_signed_tls_client_auth` | Client certificate private key | Certificate/trust chain or registered public certificate | Environments with suitable TLS/mTLS infrastructure and certificate policies |
| `none` | No protectable secret credentials | Does not treat the client as confidential | Public clients (SPA/native) with Authorization Code + PKCE |

**Two things to keep separate:** `private_key_jwt` is a **client authentication mechanism**, not an OAuth grant type. The client still sends `grant_type=client_credentials` or `authorization_code` matching `RegisteredClient`. A JWT client assertion is also **not an access token** for calling APIs, and not an OIDC ID Token.

## 2. Flow of Keys and Authentication Messages

~~~mermaid
sequenceDiagram
    autonumber
    participant KeyMgr as Secret store / HSM
    participant Client as reporting-service (OAuth Client)
    participant JWKS as HTTPS Client JWKS Endpoint
    participant AS as Spring Authorization Server
    participant API as Resource Server

    KeyMgr->>Client: Grant signing access with client's private key
    Client->>Client: Build JWT: iss=sub=client_id, aud=AS issuer,<br/>exp, iat, jti, header kid and typ
    Client->>KeyMgr: Sign JWS (if key is in KMS/HSM)
    KeyMgr-->>Client: JWS signature
    Client->>AS: POST /oauth2/token<br/>grant_type=client_credentials + client_assertion
    AS->>AS: Look up RegisteredClient by client_id
    AS->>AS: Verify private_key_jwt method is registered
    AS->>JWKS: GET jwkSetUrl when needed to fetch/refresh keys
    JWKS-->>AS: Public JWK Set per registered policy
    AS->>AS: Verify JWS, kid, alg, iss, sub,<br/>aud, exp/nbf, and additional policies
    AS-->>Client: Access token if client and grant/scope are valid
    Client->>API: Authorization: Bearer ACCESS_TOKEN
    API->>API: Verify access token issued by AS
    API-->>Client: Return resource per scope/permissions
~~~

Typically signing occurs in the client process using a private key loaded from a keystore; with HSM/KMS, the private key **never leaves** the signing device/service and the client receives only the signature. Fetching the client's JWKS depends on the Authorization Server's caching mechanism and does not necessarily happen on **every** token exchange.

### 2.1. Who Owns Which Key?

| Key / endpoint | Owner | Who may read it? | Purpose |
|---|---|---|---|
| **`reporting-service` private key** | Client | Only authorized signing workloads/devices | Sign `client_assertion` for `private_key_jwt` |
| **`reporting-service` public JWK** | Client | AS and authorized JWKS consumers | Verify that an assertion was signed by the corresponding client |
| **Authorization Server private signing key** | AS | Only authorized token-issuing services/devices | Sign JWT access tokens or ID Tokens |
| **Authorization Server public JWKS** (`/oauth2/jwks`) | AS | Clients/Resource Servers verifying tokens | Verify JWT signatures **issued by the AS** |

Both key pairs may use RSA/EC, yet they **must never be confused**. `ClientSettings.jwkSetUrl` points to the **client's public JWKS**. `AuthorizationServerSettings.jwkSetEndpoint` or the AS's `jwks_uri` metadata refers to the **Authorization Server's public JWKS**. They serve two opposite directions of verification.

## 3. What Fields Are in a JWT Client Assertion?

A client assertion is a **signed JWT (JWS compact serialization)** sent in the form body of a token request. Example header:

~~~json
{
  "alg": "RS256",
  "kid": "reporting-2026-11",
  "typ": "client-authentication+jwt"
}
~~~

Illustrative payload (**not a signed JWT**, timestamps are structural examples only):

~~~json
{
  "iss": "reporting-service",
  "sub": "reporting-service",
  "aud": "https://login.example.vn",
  "iat": 1794790000,
  "exp": 1794790060,
  "jti": "d1a3c403-188a-4833-98a8-989598fbb204"
}
~~~

| Field | Rule to understand |
|---|---|
| `iss` (JWT issuer) | In the client authentication profile, **the client declares its own identity**, usually equal to `client_id`; **not** the AS's issuer |
| `sub` | Must be the `client_id` of the authenticating client; e.g., `reporting-service` |
| `aud` | **The Authorization Server's issuer identifier**, strictly the single value `https://login.example.vn`, per **RFC 10070** updating RFC 7523 |
| `exp` | Expiration timestamp of the JWT; keep the lifetime very short, e.g., 60 seconds per internal policy |
| `iat` | Issued-at timestamp; can help verify freshness and clock skew |
| `nbf` | If present, do not accept the assertion before this timestamp |
| `jti` | Unique identifier for the assertion, useful for replay prevention when the AS records used history |
| `alg` | JWS signing algorithm permitted by policy/registration; e.g., `RS256`, **never** `none` or an algorithm forced from untrusted input |
| `kid` | Identifies the **public key** to select in the client's own JWKS; key IDs must be consistent during rotation |
| `typ` | RFC 10070 **recommends** `client-authentication+jwt` to distinguish the JWT type; check compatibility with your implementation library |

### 3.1. Key Change in RFC 10070 (November 2026)

**The original RFC 7523** allowed using the token endpoint URL as an audience value in JWT assertions. However, **RFC 10070 (11/2026)** updated this rule to prevent audience-confusion attacks:

- For JWTs used for **client authentication**, `aud` **MUST contain only the AS's issuer identifier** per RFC 8414; the token endpoint URL **must not** be used as the audience, even though the token request is sent to that endpoint.
- The AS must reject any JWT assertion whose audience does not match **its exact single issuer**. Do not accept an audience array containing both the issuer and another URL.
- The RFC recommends `typ: client-authentication+jwt`, but **does not recommend rejecting solely for missing `typ`** so older clients that already use a safe audience remain compatible.
- **The assertion's `iss` is still the client ID**; **`aud` is the AS's issuer**. Do not confuse the two occurrences of "issuer" because they refer to two different entities.

**Correct example:**

~~~text
AS issuer:      https://login.example.vn
AS token URL:   https://login.example.vn/oauth2/token
assertion iss:  reporting-service
assertion sub:  reporting-service
assertion aud:  https://login.example.vn
~~~

Invalid examples under the updated rule: `"aud": "https://login.example.vn/oauth2/token"` or `"aud": ["https://login.example.vn", "https://other.example.vn"]`.

**Compatibility note:** Some older library versions or AS configurations may still validate audience using pre-RFC 10070 behavior. Upgrading or customizing validators to enforce **strictly a single-issuer** audience must be tested against your actual Spring Security/Spring Authorization Server version. Do not assume the framework already enforces the new rule just because a request with a valid JWT succeeds.

### 3.2. Do `jti` and Replay Protection Work Automatically?

RFC 7523 treats checking previously seen `jti` values as an **applicable safeguard**, but does not guarantee that default libraries store every `jti` to block replays. If replay protection is required, the AS should store keys such as `(client_id, jti)` with a TTL lasting at least until `exp` plus policy clock skew, using atomic writes in storage shared across pods. Reused assertions must be rejected.

Do not equate a unique `jti` with replay protection: if the server **does not check usage history**, an attacker with a stolen assertion within its validity window can replay it. HTTPS, short TTLs, and log controls remain essential.

## 4. Configuring `RegisteredClient` with `PRIVATE_KEY_JWT`

Spring Authorization Server supports `private_key_jwt` through its default client authentication mechanism. In Spring Authorization Server 1.5.x, register the client using the builder as follows:

~~~java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

@Configuration(proxyBeanMethods = false)
class ClientRegistrationConfig {

    @Bean
    RegisteredClientRepository registeredClientRepository() {
        RegisteredClient reporting = RegisteredClient
                .withId("registration-reporting-service")
                .clientId("reporting-service")
                .clientName("Reporting service")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.PRIVATE_KEY_JWT)
                .authorizationGrantType(
                        AuthorizationGrantType.CLIENT_CREDENTIALS)
                .scope("reports.read")
                .clientSettings(ClientSettings.builder()
                        .jwkSetUrl(
                          "https://keys.example.vn/clients/reporting-service/jwks.json")
                        .tokenEndpointAuthenticationSigningAlgorithm(
                                SignatureAlgorithm.RS256)
                        .build())
                .tokenSettings(TokenSettings.builder()
                        .accessTokenTimeToLive(Duration.ofMinutes(5))
                        .build())
                .build();

        return new InMemoryRegisteredClientRepository(reporting);
    }
}
~~~

**Explanation:**

1. `clientAuthenticationMethod(PRIVATE_KEY_JWT)` enables authenticating the client with an **asymmetrically signed** JWT assertion rather than HTTP Basic.
2. Do not set `clientSecret(...)`: the server only needs a trusted public key, and the client proves possession of the private key. Never add a dummy secret to appease the builder.
3. `ClientSettings.jwkSetUrl(...)` points to the **client's HTTPS JWKS**; the server uses the registered key source to verify signatures.
4. `tokenEndpointAuthenticationSigningAlgorithm(SignatureAlgorithm.RS256)` restricts accepted algorithms to match the private/public key. Never accept an algorithm chosen solely by the assertion outside policy.
5. `authorizationGrantType(CLIENT_CREDENTIALS)` is independent of the authentication method. A client registered with `AUTHORIZATION_CODE` can also use `private_key_jwt` at the token endpoint when exchanging an authorization code.
6. `InMemoryRegisteredClientRepository` is only for illustration/local tests. Production should use durable repositories, provisioning policies, and URL/key validation, while ensuring all AS instances read the same registration.

**Requirements for a complete setup:** The Spring Boot app still needs the Authorization Server bean/filter chain, `AuthorizationServerSettings` with a stable public issuer, access token generation, appropriate authorization/consent services, and the **AS's** private signing key (if issuing JWTs). This snippet only registers one client.

### 4.1. Enabling Client Authentication in SecurityFilterChain

In a standard Spring Authorization Server configuration, `OAuth2ClientAuthenticationFilter` supports `private_key_jwt` by default via `JwtClientAssertionAuthenticationConverter` and `JwtClientAssertionAuthenticationProvider`. You generally **do not need to write a custom filter to verify JWT client assertions**.

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, Customizer.withDefaults())
        .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
        .exceptionHandling(exceptions ->
                exceptions.defaultAuthenticationEntryPointFor(
                        new LoginUrlAuthenticationEntryPoint("/login"),
                        new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

    return http.build();
}

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://login.example.vn")
            .build();
}
~~~

This is an **Authorization Server-side** configuration skeleton (imports come from the corresponding Spring Security/Spring Authorization Server packages). `/oauth2/token` requires client authentication per grant/policy; when an assertion arrives, the provider retrieves the `RegisteredClient` and key settings to verify it. If OIDC is enabled, add the appropriate OIDC configurer; **`private_key_jwt` does not require enabling OIDC** since it is a standard OAuth 2.0 token endpoint client authentication method.

To tighten claims for RFC 10070 or `jti` policy, you can customize `JwtClientAssertionDecoderFactory` and provide validators to `JwtClientAssertionAuthenticationProvider` via `OAuth2ClientAuthenticationConfigurer.authenticationProviders(...)`. When doing so, **combine** your new validator with `DEFAULT_JWT_VALIDATOR_FACTORY` to retain default checks (`iss`, `sub`, `aud`, `exp`, `nbf`) while adding exact-audience rules and replay protection if needed. Replacing the default validator outright can easily omit critical checks.

## 5. Distributing the Client's Public Key via JWKS

### 5.1. A Properly Formed Public JWKS

A **JSON Web Key Set (JWKS)** is a JSON object containing a `keys` array. For an RSA key using `RS256`, the public JWK typically includes:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "reporting-2026-11",
      "use": "sig",
      "alg": "RS256",
      "n": "BASE64URL_RSA_PUBLIC_MODULUS",
      "e": "AQAB"
    }
  ]
}
~~~

The `n` value above is a **placeholder**, not a valid modulus, and cannot verify real tokens. The public JWKS must be generated from the **actual public key** matching the signing private key. Sharing one JWKS across multiple clients can complicate access control and rotation; this example assigns a dedicated path for `reporting-service`.

| Field | Meaning |
|---|---|
| `kty` | Key type, e.g., `RSA` or `EC` |
| `kid` | Identifier helping the server select the right public key from the JWT header |
| `use` | Intended usage `sig` (signing/verification) |
| `alg` | Matching algorithm, e.g., `RS256`; the server must still enforce registration policy |
| `n`, `e` | Base64url-encoded RSA public modulus and public exponent |

**Never publish private key parameters** such as RSA `d`, `p`, `q`, `dp`, `dq`, `qi`, or symmetric key `k`. A public JWKS does not need secrecy like a private key, but it must guarantee **integrity and trusted origin**: served over HTTPS, controlled registered hostnames, publishing/rotation policies, and certificate monitoring.

### 5.2. Generating Public JWKS JSON from a Public Key with Nimbus

Example on the **client service or provisioning team side**, where an `RSAPublicKey` is loaded from a keystore/secret manager:

~~~java
import java.security.interfaces.RSAPublicKey;
import java.util.Map;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;

static Map<String, Object> publicJwks(RSAPublicKey publicKey) {
    RSAKey jwk = new RSAKey.Builder(publicKey)
            .keyID("reporting-2026-11")
            .keyUse(KeyUse.SIGNATURE)
            .algorithm(JWSAlgorithm.RS256)
            .build();

    // true: serialize only the public parts of the JWK
    return new JWKSet(jwk).toJSONObject(true);
}
~~~

The output can be published to a managed JSON endpoint/static asset, such as `https://keys.example.vn/clients/reporting-service/jwks.json`. This example neither starts an HTTP server nor reads private keys. Configure TLS, `application/json` response content type, suitable HTTP cache lifetimes, and an update workflow when rotating keys.

**Distribute via URL or embed keys directly?** Spring Authorization Server provides standard `jwkSetUrl` configuration to fetch public JWKS; in environments where the server cannot fetch external URLs, you may need a carefully designed custom decoder/key resolver or alternative registration mechanism. Never pass a URL arbitrarily modifiable via HTTP requests straight to a decoder.

### 5.3. Preventing SSRF and Key Substitution

Because a public JWKS is **fetched over the network**, the key URL lies on a trust boundary:

- Allow only authorized admins/provisioning pipelines to register or change `jwkSetUrl`. Validate HTTPS, allowed hostnames/domains, private/loopback/link-local IP blocks, redirects, DNS, and egress policies.
- Never trust `jku`, `x5u`, or embedded JWKs inside an **unverified JWT** to fetch a new public key dynamically. Select keys from the **source registered for that client**, matching `kid` and allowed algorithms.
- Never trust a key solely because its `kid` matches: `kid` is only a hint to pick among trusted keys; the signature must actually verify.
- Handle missing keys, invalid JWKS, timeouts, or TLS failures with **fail-closed rejection**; never fall back to unauthenticated modes or bypass signature checks.
- Monitor public JWKS caches so rotated keys propagate promptly; exact refresh/cache behavior depends on library versions and HTTP client settings.

If multiple tenants share an Authorization Server, one tenant/client's key set **must never** verify assertions from another client. Trust must start from the authorized client registration.

## 6. Creating Client Assertions with Java/Nimbus JOSE + JWT

On the **client side** (`reporting-service`), the workflow consists of holding a protected private key, building claims, signing the JWS with the registered algorithm, and posting the JWT to the token endpoint over HTTPS.

Illustrative Java method creating a JWT assertion using an RSA private key **supplied by the key management layer**:

~~~java
import java.security.interfaces.RSAPrivateKey;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.UUID;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

static String newClientAssertion(
        RSAPrivateKey privateKey,
        String kid,
        String clientId,
        String authorizationServerIssuer) throws JOSEException {

    Instant now = Instant.now();

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(clientId)
            .subject(clientId)
            // RFC 10070: audience is a single issuer identifier.
            .audience(authorizationServerIssuer)
            .issueTime(Date.from(now))
            .expirationTime(Date.from(now.plus(Duration.ofSeconds(60))))
            .jwtID(UUID.randomUUID().toString())
            .build();

    JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
            .type(new JOSEObjectType("client-authentication+jwt"))
            .keyID(kid)
            .build();

    SignedJWT assertion = new SignedJWT(header, claims);
    assertion.sign(new RSASSASigner(privateKey));
    return assertion.serialize();
}
~~~

**Limitations:** this snippet only constructs the JWT; it does not execute an HTTP token request or show how the private key is loaded. In production, load keys through secret-management procedures, restrict file/keystore permissions, or use KMS/HSM with an appropriate signer instead of `RSASSASigner(privateKey)` so the private key never leaves the secure boundary into process memory. For RSA, pick key sizes/algorithms meeting security policies (e.g., at least 2048-bit RSA for RS256 per practical security requirements).

**Do not generate a new key pair per token request.** Signatures must use the private key matching the registered public key and exact `kid` in JWKS. Generate fresh `iat`, `exp`, and `jti` values on each request; never reuse an expired assertion or one exposed in logs.

### 6.1. Sending the JWT to the Token Endpoint

The HTTP example below uses `grant_type=client_credentials`. In practice, `client_assertion` is a three-segment string `base64url(header).base64url(payload).base64url(signature)`, and all form fields must be **URL-encoded**:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials
&scope=reports.read
&client_id=reporting-service
&client_assertion_type=urn%3Aietf%3Aparams%3Aoauth%3Aclient-assertion-type%3Ajwt-bearer
&client_assertion=SIGNED_JWT_ASSERTION_URL_ENCODED
~~~

Body line breaks are added for readability, **not valid raw body syntax**: when sending real requests, concatenate and form-encode parameter pairs. Never send `Authorization: Basic ...` containing a shared secret for a registration restricted to `PRIVATE_KEY_JWT`. Some OAuth2 client libraries do not automatically generate `private_key_jwt` assertions from a `client-authentication-method` setting alone; verify or explicitly configure assertion creation/signing in your token client version.

The AS performs two independent checks:

1. **Client authentication:** the assertion has a valid signature/key/claims, and this method is permitted for `reporting-service`.
2. **Grant authorization:** the client is allowed `client_credentials` and may request `reports.read`; final token issuance depends on Authorization Server policies.

When using Authorization Code + PKCE, after a valid redirect the client exchanges `code` with a token request carrying `grant_type=authorization_code`, `code`, `redirect_uri`, `code_verifier`, and **the `client_assertion_type`/`client_assertion` pair**, still authenticating via `private_key_jwt`. PKCE, `state`, and redirect URI validation remain mandatory by design; `private_key_jwt` does not replace them.

### 6.2. Distinguishing Client Assertion from JWT Bearer Authorization Grant

| Request component | **`private_key_jwt` client authentication** | **JWT bearer authorization grant** |
|---|---|---|
| Goal | Prove client identity to the AS | Use a JWT assertion as an **authorization grant** |
| JWT parameter | `client_assertion` | `assertion` |
| Type parameter | `client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer` | `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer` |
| Accompanying grant type | E.g., `client_credentials`, `authorization_code` | The JWT bearer grant itself |
| Typical Spring config | `ClientAuthenticationMethod.PRIVATE_KEY_JWT` | Requires verifying dedicated grant extension support; not implied by `PRIVATE_KEY_JWT` |

Both features are discussed in RFC 7523, yet their usage and policies **differ**. Never send a client authentication JWT inside the `assertion` parameter expecting the server to treat it as client authentication.

## 7. In What Order Does the AS Verify Assertions?

Library implementations may organize internal steps differently, yet the outcome must satisfy these conditions:

1. Identify the presented `client_id` and **look up `RegisteredClient`** in the trusted repository. Reject unknown clients or clients not permitted `PRIVATE_KEY_JWT`.
2. Fetch the JWKS from **that specific client's** `ClientSettings.jwkSetUrl`, never from an arbitrary header/URL supplied in the assertion.
3. Determine accepted algorithms from registration and policy; verify `alg`, `kid`, key type, and JWS signature using the matching public key.
4. Verify `iss` and `sub` equal `client_id` per the client authentication profile.
5. Verify `aud` **solely equals** the AS's issuer per RFC 10070 using exact string matching (including scheme, host, path, and trailing slashes).
6. Verify `exp`, `nbf`, and possibly `iat`, within allowed clock skew; reject expired assertions or anomalous timestamps.
7. Apply `jti` replay policy if required by the system; consider `jti` anti-replay active only when the server actually stores and checks seen values.
8. Finally, validate grant type, scopes, authorization code/PKCE, or token-issuance policies.

Be especially careful about **algorithm confusion**: never let a JWT switch `RS256` to `HS256` and treat public key bytes as a shared secret; never allow `alg=none`. If a client is configured for multiple algorithms, allow only a governed and individually tested set.

**Limitations of the JWT type header:** `typ: client-authentication+jwt` is a helpful signal for token typing. Practical rules must match decoder version compatibility; never rely on `typ` alone to trust a JWT with an invalid audience or signature.

## 8. Key Rotation: Changing Private Keys Without Dropping Token Issuance

Using `kid` to select keys in JWKS allows clients to transition from an old key to a new key in a planned manner.

~~~mermaid
sequenceDiagram
    autonumber
    participant Ops as Key operator
    participant JWKS as Client JWKS endpoint
    participant Client as reporting-service
    participant AS as Authorization Server

    Ops->>JWKS: Publish old public key kid=v1 and new kid=v2
    AS->>JWKS: Refresh/reload JWKS
    JWKS-->>AS: v1 + v2
    Ops->>Client: Grant signing access with new private key
    Client->>AS: Assertion signed with v2, header kid=v2
    AS->>AS: Verify with public v2; issue token
    Note over Client,AS: Ensure old client instances switched,<br/>v1 assertions expired, and caches refreshed
    Ops->>JWKS: Remove public v1 after safe confirmation
    Ops->>Client: Revoke/delete private key v1
~~~

Operational sequence:

1. Generate a new key pair in KMS/HSM or a standard keystore and assign a unique new `kid`.
2. **Publish the new public JWK alongside the old public JWK** in the client's JWKS so the AS can verify both during transition.
3. Verify all AS instances successfully fetch the updated JWKS or trigger cache refresh if needed.
4. Roll out the client to sign new assertions with the new `kid`; monitor authentication success rates.
5. Wait for old assertions to expire and confirm all client instances have stopped using the old key, accounting for cache TTLs and clock skew.
6. Remove the old public key from JWKS and revoke the old private key per runbook; record audit metadata (version, owner, timestamp).

**If a private key is compromised:** prioritize revoking the key from the trusted source and performing emergency replacement; evaluate access tokens already issued to the affected client (separate revocation mechanisms may be required). Do not merely wait for short-lived assertions to expire, because an attacker holding the private key can keep minting **new** assertions until the key is revoked.

### 8.1. Common Rotation Failure Modes

- Client switches to `kid=v2` while JWKS still serves only `v1` ⇒ AS cannot find the verification key.
- AS caches stale JWKS without refreshing ⇒ new rollout fails even though the endpoint already publishes the new key.
- Public JWK `v2` was exported from **the wrong key pair** ⇒ `kid` matches, but signature verification fails.
- Key `v1` is removed while some client instances still sign with `v1` ⇒ intermittent token endpoint failures.
- `jwkSetUrl` is moved to a new domain without checking TLS/egress/allowlists ⇒ AS fails to fetch JWKS or exposes an SSRF risk.
- Two clients share the same private key ⇒ loss of independent revocation and forensics; each client should have its own key pair and policy.

## 9. Securing Private Keys and Public Key Distribution Systems

### 9.1. Private Keys Must Be Protected Throughout Their Lifecycle

- Generate keys using a sufficiently strong cryptographic RNG, enforce policy-compliant key sizes/algorithms, and use separate keys per client and per environment.
- Store private keys in a controlled secret store, HSM/KMS, or encrypted keystore; prefer workload identity and **sign-only** permissions where supported by the platform.
- Never place private keys, PEMs, PKCS#12 passwords, or raw JWT assertions in Git, Docker images, container arguments, `application.yml`, CI logs, heap dumps, or bug reports.
- When signing errors occur, logs should include only `client_id`, `kid`, error category, correlation ID, and timestamp; **never** log signatures, full assertions, or keys.
- Enforce least-privilege read access and access lifetimes per environment. When scaling a service, ensure instances of the same client share authorized keys and JWKS publishes all active keys.
- Audit key creation, signing-permission grants, public JWKS publishing, registration URL changes, and key revocations.

### 9.2. Public Does Not Mean Harmless

Public keys **may be publicly readable**, but the ability to **modify JWKS contents** must be protected like changing authentication configuration. If an attacker replaces the JWKS with their own public key, they can forge assertions and impersonate the client to any AS trusting that JWKS.

Enforce write-access controls, deployment approvals, HTTPS/TLS, DNS integrity, CDN cache governance, HTTP redirect restrictions, artifact signing/verification where appropriate, and monitoring for unplanned changes. Never allow users to register arbitrary JWKS URLs pointing to internal hosts or cloud metadata services.

## 10. Testing `private_key_jwt` and JWKS

### 10.1. Inspecting Public JWKS Without Exposing Private Keys

~~~bash
curl -fsS https://keys.example.vn/clients/reporting-service/jwks.json \
  | jq '{kids: [.keys[].kid], key_types: [.keys[].kty], public_only: (all(.keys[]; has("d") | not))}'
~~~

**Note on the check syntax:** the `public_only` expression above only checks RSA's `d` field; for thorough security checks, also verify private fields such as `p`, `q`, `dp`, `dq`, `qi`, or symmetric `k` depending on `kty`. Recording `kid` is helpful, yet you still must test with a real signed assertion to confirm the public/private key pair matches.

Make sure `curl` hits the **client's JWKS**, distinct from:

~~~bash
curl -fsS https://login.example.vn/oauth2/jwks \
  | jq '{as_key_count: (.keys | length)}'
~~~

The second URL is the **AS's public JWKS** used to verify access tokens/ID Tokens signed by the AS; it does not replace the JWKS configured in `RegisteredClient`.

### 10.2. Key Test Matrix

| Test case | Input variation | Expected outcome |
|---|---|---|
| Standard success | Valid RS256 assertion, `iss=sub=client_id`, `aud` strictly single issuer, valid lifetime | Token endpoint accepts client and continues checking grant/scope |
| Missing registration | Non-existent `client_id` | Rejected, no token issued |
| Wrong authentication method | Client only registered `CLIENT_SECRET_BASIC` but sends assertion | Rejected with `invalid_client` or appropriate error |
| Invalid signature | JWT with modified payload/signature | Rejected, never falls back to keys outside the registry |
| Wrong `kid` | Header `kid` not published in client JWKS | Rejected or controlled JWKS refresh triggered, never accepts invalid token |
| Wrong `alg` | Assertion uses `HS256` or `none` instead of registered `RS256` | Rejected |
| Wrong `iss` or `sub` | Does not match registered `client_id` | Rejected |
| Wrong `aud` | Uses token endpoint URL instead of issuer | Rejected per RFC 10070 |
| Multi-valued `aud` | `aud` contains issuer plus another URL | Rejected per RFC 10070 |
| Expired | `exp` in the past | Rejected |
| Not yet valid | `nbf` in the future beyond clock skew | Rejected |
| Replayed assertion | Resend same `jti`/assertion | Rejected **if replay protection is enabled**; explicitly test policy rather than assuming default |
| JWKS unreachable | TLS fail, timeout, 404 key endpoint | Client fails authentication; logs/alerts do not expose credentials |
| Key rotation | Publish `v1`+`v2`, client switches to `v2` | AS verifies `v2`; `v1` remains accepted during transition window |
| Wrong grant/scope | Valid client auth requesting unregistered grant or scope | Token not issued with unauthorized permissions |
| Issuer change | Public AS issuer differs from `aud` sent by client | Rejected; client and policy must update after migration |

**Spring version compatibility testing:** given the 2026 RFC 10070 update, specifically verify that your running Spring Authorization Server version's validator **actually rejects** token-endpoint URLs or multi-valued audiences. If it does not, implement an appropriate custom validator rather than marking tests as PASS just because a valid assertion works.

### 10.3. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `invalid_client` even with a signed JWT | Wrong `client_id`, registered method, `iss/sub/aud`, signature, or `alg` | Inspect `RegisteredClient`, issuer metadata, and **redacted** headers/claims |
| `kid` not found | Public JWKS lacks the `kid`, or stale cache | Check client JWKS, publish-before-rollout order, and cache/TTL settings |
| Invalid JWT `aud` claim | Used token endpoint URL instead of AS issuer, or trailing-slash mismatch | Set `aud` strictly to the single AS issuer per RFC 10070 |
| Signing algorithm mismatch | `tokenEndpointAuthenticationSigningAlgorithm` mismatches key/JWT header | Align registered RS256/EC algorithm; never use `none` |
| JWKS fetch fail | Wrong URL, TLS/DNS failure, proxy block, or egress policy | Check `jwkSetUrl`, HTTPS, allowlist, DNS, and network policy |
| JWT assertion expired | Clock skew between client and server, or `exp` too tight for network latency | Sync NTP and choose reasonable TTL/skew; do not loosen lifetimes recklessly |
| New `typ` incompatible with older library | Decoder/validation does not yet support explicit typing | Test library compatibility; upgrade or configure type verification appropriately |
| `private_key_jwt` registered, yet client still sends Basic | OAuth Client library does not auto-sign assertions or method config is incomplete | Add client-side assertion signing and inspect actual outbound requests |
| Client authenticates successfully, but API returns 403 | Access token lacks required scope/audience/authorization | Inspect Resource Server policy; `private_key_jwt` only authenticates the client at the AS |

## 11. Operational Checklist and Self-Check Questions

Before promoting a `private_key_jwt` client to production:

- [ ] Each client has its own `client_id`, `PRIVATE_KEY_JWT` explicitly registered, and least-privilege grant types and scopes.
- [ ] `ClientSettings.jwkSetUrl` points to **that specific client's HTTPS JWKS**, controlled by trusted admins/automation.
- [ ] Private keys signing JWT assertions never leave the trust boundary; public JWKS contains **only** public keys with stable `kid`s.
- [ ] Algorithms are pinned to the registration; `alg=none`, self-supplied `jku`/JWK headers, and non-registry keys are rejected.
- [ ] `iss=sub=client_id`, `aud` **solely equals AS issuer**, short `exp`, sensible `iat`, unique `jti`; evaluate stateful replay protection.
- [ ] Test RFC 10070 behavior against your actual Spring version, especially token-endpoint audiences, multi-valued audiences, and JWT `typ`.
- [ ] Maintain a rotation plan: publish new public key first, switch signing key second, remove old key once all clients/AS nodes have updated.
- [ ] Maintain a compromise runbook: block key, rotate key, assess issued access tokens, audit, and notify per incident procedures.
- [ ] Observability tracks `invalid_client` errors, JWKS fetches, `kid`, latency, and rotations; **never** logs assertions or keys.
- [ ] Local/staging/production environments use independent keys, issuers, registrations, and policies.

**Self-check questions:**

1. Why does the Authorization Server only need a public key to verify `private_key_jwt`, while the client must possess the private key?
2. How do `iss` and `aud` differ in a JWT client assertion, especially when the AS also has its own issuer identifier?
3. After RFC 10070, is it permissible to use `https://login.example.vn/oauth2/token` as `aud` instead of issuer `https://login.example.vn`?
4. Which two key sets do `ClientSettings.jwkSetUrl` and `Authorization Server jwks_uri` point to?
5. Why is `kid` in a JWT insufficient on its own to authenticate a client, and what is the risk of trusting a `jku` URL from an assertion?
6. If a JWT already has a unique `jti` but the server does not store/check seen `jti` values, is the assertion protected against replay?
7. During private key rotation, why must the new public key be published before the client begins signing with the new key?
8. Does `private_key_jwt` replace `grant_type=client_credentials` or work alongside a grant type?

## References

- [RFC 7523 — JSON Web Token (JWT) Profile for OAuth 2.0 Client Authentication and Authorization Grants](https://www.rfc-editor.org/rfc/rfc7523).
- [RFC 10070 (11/2026) — Updates to OAuth 2.0 JWT Client Authentication and Assertion-Based Authorization Grants](https://www.rfc-editor.org/rfc/rfc10070.html): mandatory update on `aud` and recommendation on `typ`.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer identifier and metadata.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517); [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515); [RFC 7519 — JWT](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm restrictions and JWT confusion risks.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): client authentication filter/provider and customizing JWT assertion validation.
- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `ClientSettings`, and JWKS.
- [Spring Authorization Server — ClientSettings.Builder API (1.5.8)](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/ClientSettings.Builder.html): `jwkSetUrl` and `tokenEndpointAuthenticationSigningAlgorithm`.
