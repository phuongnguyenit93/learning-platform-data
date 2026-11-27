# Threat Modeling and Applying OAuth 2.0 Security Best Current Practice

## Lesson Objectives

The Authorization Server is a security component that directly affects every application and API that consumes the tokens it issues. A single flaw in redirect URI validation, client authentication, signing keys, refresh-token lifecycle, or audience validation can turn into unauthorized access across multiple systems.

This lesson builds a threat model for an OAuth 2.0/OpenID Connect Authorization Server and translates the recommendations from the OAuth 2.0 Security Best Current Practice (RFC 9700) into design, configuration, and operational measures with Spring Authorization Server 1.5.8 and Spring Security 6.5.x.

The focus is on protecting Authorization Codes, client authentication, redirects, token issuance, refresh, introspection, revocation, discovery, and key management. It also covers PKCE, Pushed Authorization Requests (PAR), DPoP, mutual TLS (mTLS), sessions, CSRF, CORS, rate limiting, and incident response.

After this lesson, you will be able to:

1. Identify the assets, actors, trust boundaries, and attack surface of an Authorization Server.
2. Analyze authorization code interception/injection, redirect manipulation, mix-up, CSRF, token replay, refresh-token theft, and client impersonation.
3. Apply the Authorization Code Grant with PKCE S256 and exact redirect URI matching.
4. Distinguish between public clients and confidential clients and choose appropriate client authentication.
5. Protect access tokens and refresh tokens using TTL, rotation, revocation, DPoP, or mTLS.
6. Use PAR to reduce exposure of authorization request parameters over the front channel.
7. Configure Spring Authorization Server endpoints and Spring Security filter chains securely.
8. Protect login, consent, session, CSRF, CORS, and HTTP response headers.
9. Design key lifecycle, metadata, discovery, logging, rate limiting, and incident response processes.
10. Build a threat-based test matrix to verify security controls.

> Version scope: examples use Spring Authorization Server 1.5.8 and Spring Security 6.5.x. RFC 9700 was published in January 2025 and is the current Best Current Practice for OAuth 2.0. MUST/SHOULD requirements in the RFC are preserved with their standard normative semantics; configuration examples should be tested against your specific deployment.

## 1. Why Does an Authorization Server Need a Threat Model?

An Authorization Server is not just a place that generates JWTs. It is the party that decides:

- Which clients are allowed to request permissions.
- Which users can grant consent.
- Which scopes and resources are granted to a client.
- Which tokens are issued, what audience those tokens have, and how long they live.
- Which clients are allowed to exchange refresh tokens, revoke, or introspect tokens.
- Which keys are used for signing and which Resource Servers are allowed to trust those keys.

When an Authorization Server is compromised, an attacker can issue tokens that are cryptographically valid in signature yet carry unauthorized permissions. Therefore, successfully verifying a signature only proves that a token was signed by a trusted key; it does not prove that the token has the right audience, scope, subject, or intended purpose.

RFC 9700 updates the older OAuth 2.0 threat model, clarifies attacks that have appeared in real-world deployments, and deprecates several less secure modes. This BCP applies to the client, the Authorization Server, and the Resource Server; security is achieved only when all components coordinate properly.

## 2. Identifying Assets to Protect

Before selecting controls, list the assets and the consequences if they are disclosed, modified, or become unavailable.

| Asset | Security value | Impact if compromised |
|---|---|---|
| Authorization code | Short-lived, single-use secret | Attacker exchanges the code for tokens if PKCE/client binding is missing |
| Access token | Credential for API access | Unauthorized data access or actions |
| Refresh token | Credential for obtaining new access tokens | Prolonged unauthorized access that is harder to detect |
| ID Token | Authentication proof for an OIDC client | Login session spoofing if the client validates incorrectly |
| Client secret/private key | Client authentication credential | Client impersonation and requesting tokens under the client's privileges |
| Signing private key | Root of trust for JWTs | Token forgery for the affected issuer |
| User session/cookie | Maintains login and consent state | Session hijacking, fixation, or CSRF |
| RegisteredClient/configuration | Client ID, redirect URI, grants, scopes, auth method | Policy tampering to escalate permissions or redirect codes to an attacker |
| Authorization/consent store | Grants, token metadata, revocation state | Reading/modifying authorizations or bypassing revocation |
| Issuer/JWKS/metadata | Server identity and verification key source | Mix-up, key substitution, or trusting the wrong issuer |
| Audit/security events | Detection and forensic evidence | Inability to determine the scope of an incident |

Classify data by sensitivity level. Do not log raw authorization codes, access tokens, refresh tokens, ID Tokens, client secrets, private keys, or DPoP proofs. If correlation is needed, use a request ID, client ID, issuer, a safely sanitized token ID, or a one-way hash according to policy.

## 3. Actors and Trust Boundaries

### 3.1. Actors

A threat model should consider at least the following actors:

- Malicious client: a legitimate client that attempts to request excessive scopes/audiences or abuse grants.
- Compromised client: a client whose client secret, private key, or token-storing device has been stolen.
- Malicious end-user: a user attempting to manipulate redirects, consent, account linking, or workflows.
- Network attacker: eavesdropping, modifying, or replaying traffic when TLS/proxy configuration is flawed.
- Compromised Resource Server: an API that accepts tokens with the wrong audience or leaks tokens.
- Rogue Authorization Server/IdP: a malicious issuer seeking to cause mix-up or steal codes/tokens.
- Compromised insider or administrator: modifying client registrations, keys, scopes, redirect URIs, or policies.
- Bot/DoS actor: generating floods of authorization, login, token, PAR, or introspection requests.

### 3.2. Trust Boundaries

| Boundary | Data crossing | What must be verified |
|---|---|---|
| Browser ↔ Authorization Server | Cookies, login form, authorization request/response | TLS, session, CSRF, state, redirect URI, nonce |
| Client ↔ Authorization Server | Client authentication, code, token, refresh, PAR | Client identity, grant permission, PKCE, replay |
| Authorization Server ↔ Resource Owner | Authentication, consent, MFA | Local authentication policy, consent integrity |
| Authorization Server ↔ Resource Server | Access token, introspection/JWKS | Issuer, signature, audience, scope, token status |
| Authorization Server ↔ KMS/HSM | Signing operations, key metadata | Service identity, key purpose, audit, rotation |
| Authorization Server ↔ database/cache | Clients, authorizations, consents, replay state | Tenant isolation, access control, integrity, availability |
| Application ↔ reverse proxy/ingress | Host, scheme, forwarded headers | Trusted proxy, canonical issuer, TLS termination |

Do not implicitly trust data just because it comes from an internal network. Requests from proxies, service meshes, admin consoles, or background jobs still require authentication and authorization.

### 3.3. Grouping Threats with STRIDE

| Category | Example in an Authorization Server | Representative controls |
|---|---|---|
| Spoofing | Impersonating a client, issuer, or Resource Owner | Client authentication, issuer validation, MFA |
| Tampering | Modifying redirect URI, scope, consent, or authorization request | Exact matching, signed request/PAR, integrity checks |
| Repudiation | Denying consent grants or client policy changes | Audit events with actor, timestamp, and correlation ID |
| Information disclosure | Leaking codes, tokens, secrets, or signing keys | TLS, redaction, KMS/HSM, no-store |
| Denial of service | Flooding login, token, PAR, introspection, or KMS | Rate limiting, quotas, bounded work, circuit breakers |
| Elevation of privilege | Requesting excessive scopes/audiences or using tokens on the wrong API | Least privilege, audience/scope validation, consent |

## 4. Authorization Code Flow and Attack Surface

The Authorization Code Flow separates user interaction from delivering tokens to the client:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth Client
    participant B as Browser
    participant AS as Authorization Server
    participant U as Resource Owner
    participant RS as Resource Server
    C->>C: Generate state, nonce and PKCE verifier
    C->>B: Redirect with client_id, redirect_uri, scope, state, code_challenge
    B->>AS: Authorization Request
    AS->>AS: Validate client, redirect URI, scope and PKCE challenge
    AS->>B: Login / consent if required
    B->>U: Authenticate and present consent
    U->>B: Complete authentication / consent
    B->>AS: Continue authorization request
    AS->>AS: Create short-lived single-use code bound to client and redirect URI
    AS->>B: Redirect to registered redirect URI with code and state
    B->>C: Authorization response
    C->>C: Validate state / issuer response and recover verifier
    C->>AS: Token Request with code and code_verifier
    AS->>AS: Validate client, code, redirect URI and PKCE
    AS-->>C: Access token (+ refresh token if policy allows)
    C->>RS: Protected request with access token
    RS->>RS: Validate issuer, signature, audience and authorization
    RS-->>C: Protected resource
~~~

Points vulnerable to attack:

1. The authorization request is modified before reaching the Authorization Server.
2. The redirect URI delivers the code to an attacker's domain.
3. The authorization code is intercepted or injected into another client's session.
4. The client sends the code to the wrong Token Endpoint due to a mix-up.
5. Tokens leak in URLs, browser history, logs, or outbound requests.
6. Refresh tokens are replayed after theft.
7. The Resource Server verifies the signature but ignores the audience or token purpose.

The Authorization Code Flow is not automatically secure merely by using HTTPS. Each step must bind the client, browser transaction, issuer, and target resource.

## 5. Foundational BCP: Choosing Secure Grant Types

RFC 9700 recommends using the Authorization Code Grant instead of flows that return access tokens directly in the authorization response.

| Grant/flow | Security guidance |
|---|---|
| Authorization Code + PKCE | Preferred flow for user authorization, for both public and confidential clients |
| Client Credentials | For workload/service-to-service; does not represent an end user |
| Device Authorization Grant | For browserless/input-constrained devices; requires user code, rate limits, and polling interval |
| Refresh Token | Issue only when needed; bind to client/resource/scope and detect replay |
| Implicit Grant | Do not use for new deployments; access tokens travel over the front channel |
| Resource Owner Password Credentials | Do not use; clients must not collect user passwords to exchange for tokens |

Do not enable a grant type just because the framework supports it. Each client should only have the grant types it actually needs. Allowing `client_credentials` does not mean a client should be allowed to use `authorization_code` or `refresh_token`.

## 6. Redirect URI Manipulation and Open Redirects

### 6.1. Redirect URIs Must Match Exactly

An attacker may try to register or send a redirect URI closely resembling the real redirect URI, for example:

- `https://client.example/callback.attacker.example`
- `https://client.example.evil.test/callback`
- `https://client.example/callback?next=https://evil.test`
- Using wildcards or prefix matching to accept unregistered hosts or paths.

The Authorization Server must compare the redirect URI against the registered URI using exact string matching per RFC 9700, with the port exception applying only to loopback redirect URIs for native apps. Do not use `startsWith`, wildcard domains, loose regexes, or hostname-only checks.

Example client registration in Spring Authorization Server:

~~~java
RegisteredClient portal = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("employee-portal")
        .clientSecret(passwordEncoder.encode(portalSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://portal.example.com/login/oauth2/code/internal")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .build();
~~~

The redirect URI list must be governed as security configuration. Production redirect URI changes require auditing, appropriate admin privileges, and a review process.

### 6.2. Do Not Build an Open Redirector

An open redirector is an endpoint that redirects the browser to an arbitrary URL taken from a query parameter or request body. If a client exposes an endpoint like `/continue?url=...`, an attacker can use it to capture authorization codes or access tokens through a redirect chain.

Only redirect to allowlisted destinations. If you need to remember the page a user intended to open before login, store a normalized internal path in session/server-side state; do not accept arbitrary absolute URLs.

### 6.3. Do Not Let Redirect URIs Become SSRF

A redirect URI is a browser destination, but features such as discovery, dynamic registration, JWKS retrieval, or webhooks can cause the server itself to fetch a client-supplied URL. Do not use a redirect URI as a URL for backend fetching. For client-managed URLs, apply an allowlist, block loopback/private/link-local IPs, guard against DNS rebinding, and restrict redirects when an HTTP client follows redirects.

### 6.4. Do Not Forward Credentials Across Redirects

After the browser POSTs a username/password or login credentials to the Authorization Server, the redirect response must not cause the browser to re-send the credential body to the client's redirect URI. RFC 9700 requires Authorization Servers to avoid accidentally forwarding credentials when redirecting a request that may contain login credentials. For login/consent POSTs, use response semantics that switch to GET (typically HTTP 303 See Other) and test both browsers and reverse proxies; do not use 307/308 for redirects that may carry a credential body.

## 7. Authorization Code Interception and Injection: PKCE

PKCE binds an authorization code to a verifier generated by the client at the start of the transaction. The client sends `code_challenge` at the Authorization Endpoint and sends `code_verifier` at the Token Endpoint.

### 7.1. Use S256

The client generates a random `code_verifier` with sufficient entropy, then computes:

~~~text
code_challenge = BASE64URL-ENCODE(SHA256(ASCII(code_verifier)))
code_challenge_method = S256
~~~

Do not use `plain` in new deployments. With `S256`, the verifier never appears in the authorization request.

### 7.2. Enforce PKCE on the Authorization Server

Spring Authorization Server supports configuring PKCE via `ClientSettings.requireProofKey(true)`:

~~~java
RegisteredClient publicClient = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("mobile-public-client")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("com.example.app:/oauth2/callback")
        .scope(OidcScopes.OPENID)
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .build())
        .build();
~~~

Public clients cannot keep a client secret confidential. PKCE is a mandatory layer of protection for the Authorization Code Grant of public clients. RFC 9700 also recommends PKCE for confidential clients.

The Authorization Server must:

- Support PKCE and the `S256` method.
- Store the challenge alongside the authorization code.
- Require the verifier at the Token Endpoint when the authorization request included a challenge.
- Reject missing or invalid verifiers.
- Reject requests containing a verifier if the original authorization request had no challenge; this prevents PKCE downgrade attacks.
- Bind the code to its corresponding client, redirect URI, and transaction.

Do not reuse a static verifier/challenge across multiple logins.

## 8. CSRF, State, Nonce, and Mix-Up

### 8.1. State Bound to the Browser Transaction

State is a random value generated by the client and bound to the user-agent/session when initiating the authorization request. The client must verify that the returned value matches the initial transaction. Do not use a static, predictable state, or merely encode a URL without integrity protection.

PKCE can provide CSRF protection for an OAuth client once the client has confirmed that the Authorization Server supports and enforces PKCE. In OIDC, `nonce` binds the ID Token to the authentication request. Depending on the flow, the client should still maintain `state` to correlate the transaction and restore application state.

### 8.2. Nonce in OIDC

The client generates a fresh `nonce` for each authentication request. After receiving the ID Token, the client verifies the signature, issuer, audience, expiration, and compares the `nonce` claim against the stored nonce. Never reuse a nonce across transactions.

### 8.3. Mix-Up Attacks with Multiple Authorization Servers

If a client supports multiple issuers, an attacker can trick the client into sending an authorization code or client credentials to a different issuer's Token Endpoint. This is a mix-up attack.

RFC 9700 requires clients to implement mix-up defenses. Prefer:

1. Using the authorization response `iss` parameter per RFC 9207 and comparing it strictly against the issuer selected for the transaction.
2. Or using a trusted issuer identifier inside the response, such as an ID Token/JARM per the applicable profile.
3. If neither option is available, using distinct redirect URIs per issuer and checking the actual callback URI received.

The client must store the chosen issuer for each authorization request, bound to the browser session. Never take the token endpoint from a query parameter or an unverified response.

### 8.4. CSRF in the Authorization Server UI

CSRF in the OAuth redirect flow and CSRF in the login/consent form are related but distinct concerns. The Authorization Server typically uses a session cookie for the login and consent UI; browsers send cookies automatically, so state-changing operations must be protected.

Spring Security enables CSRF protection for servlet applications by default. Do not disable CSRF globally just to make the Token Endpoint work. If you need to exclude back-channel endpoints, define a very narrow matcher, verify those endpoints do not rely on browser cookies as credentials, and keep CSRF enabled for login, consent, logout, and admin UIs.

GET, HEAD, OPTIONS, and TRACE must not mutate application state. Never perform consent approval, logout, or revocation via GET.

## 9. Client Authentication and Client Credential Management

### 9.1. Public and Confidential Clients

| Client type | Can hold a secret? | Controls |
|---|---|---|
| Native/mobile app | Cannot protect a static secret inside a binary | Public client, Authorization Code + PKCE, external browser |
| Browser-based SPA | Cannot protect a secret | Public client + PKCE; consider Backend-for-Frontend |
| Server-side web application | Can hold a secret on the server | Confidential client, client authentication, and PKCE |
| Service-to-service workload | Can hold credentials in a secret manager/KMS | Confidential client, `private_key_jwt` or mTLS |

Do not embed client secrets in JavaScript, mobile binaries, desktop binaries, container images, or source repositories.

### 9.2. Choosing a Client Authentication Method

| Method | Mechanism | Recommendation |
|---|---|---|
| `none` | Public client, no client secret | Only for public clients; pair with PKCE |
| `client_secret_basic` | Secret in HTTP Basic `Authorization` header | Suitable for confidential clients when the secret is protected |
| `client_secret_post` | Secret in form body | Avoid if alternatives exist because bodies are easily logged |
| `private_key_jwt` | Client signs a JWT assertion with a private key | Preferred when solid PKI/key lifecycle is in place |
| `tls_client_auth` | Client certificate verified by a trusted CA | Suitable for workloads with PKI/mTLS |
| `self_signed_tls_client_auth` | Client uses a registered self-signed certificate | Requires certificate registration and rotation processes |

RFC 9700 recommends asymmetric client authentication such as `private_key_jwt` or mTLS where feasible. For `private_key_jwt`, the assertion must have issuer/subject set to the client ID per the profile, the audience set to the exact Token Endpoint, a short lifetime, and a `jti` for replay prevention.

### 9.3. Secret Lifecycle

- Generate random secrets with sufficient entropy.
- Store hashed secrets using an appropriate password encoder; never store plaintext in the database.
- Do not reuse the same secret across clients or environments.
- Enforce expiration, rotation processes, and short overlap windows when needed.
- Revoke immediately on suspected secret exposure.
- Restrict read access to secrets in the secret manager.
- Never log the `Authorization` header or client assertions.

### 9.4. Client Registration as a Policy Boundary

`RegisteredClient` should restrict:

- Authorization grant types.
- Client authentication methods.
- Redirect URIs.
- Scopes.
- Client settings such as PKCE and consent.
- Token settings such as TTL, refresh-token reuse, and token format.

Do not grant every grant type to every client. Do not let clients supply arbitrary audience/resource values and have the Authorization Server issue tokens without policy checks.

## 10. Token Theft, Replay, and Refresh-Token Protection

### 10.1. Bearer Tokens Carry Replay Risk

A bearer access token can be used by any party that possesses it. If a token is copied from logs, browser storage, proxy traces, crash dumps, or outbound requests, an attacker can use it until it expires or is revoked.

Controls:

- Transmit tokens only over TLS.
- Send access tokens in the `Authorization: Bearer` header, not in URLs or query strings.
- Do not write tokens to logs, tracing spans, analytics, or error reports.
- Use short access token TTLs aligned with the risk profile.
- Restrict audience and scope.
- Use sender-constrained tokens for systems with high replay risk.
- Maintain a revocation process when a client, user, or device is compromised.

All Authorization Server endpoints, web redirect URIs, and back-channel calls must be protected with TLS; never let authorization codes or tokens travel over plain HTTP. Responses containing tokens must include `Cache-Control: no-store` and `Pragma: no-cache` so browsers and proxies do not cache credentials.

### 10.2. Refresh Tokens Are Long-Lived Credentials

Refresh tokens typically remain valid longer than access tokens. If leaked, an attacker can continually obtain new access tokens. The Authorization Server should issue refresh tokens only after a risk assessment and when the client genuinely needs persistent sessions.

Refresh tokens must be bound to the client, scope, and consented resource servers. For confidential clients, a refresh token may only be used by the exact client to which it was issued, and the client must authenticate when refreshing. Do not allow refresh requests to escalate privileges beyond the original grant.

### 10.3. Refresh Token Rotation

RFC 9700 requires refresh tokens for public clients to be either sender-constrained or rotated to detect replay.

With rotation:

1. The client sends the current refresh token.
2. The Authorization Server issues a new access token and a new refresh token.
3. The old refresh token is invalidated.
4. The Authorization Server maintains lineage/family relationships.
5. If an old refresh token is reused, the server detects the replay and revokes active tokens in the family according to policy.

Spring Authorization Server configures issuing new refresh tokens via `TokenSettings.reuseRefreshTokens(false)`:

~~~java
TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofHours(8))
        .reuseRefreshTokens(false)
        .build();
~~~

In SAS, `reuseRefreshTokens` defaults to `true`; production deployments must actively evaluate and configure it. Depending on client type and version, public clients may not automatically receive refresh tokens; verify SAS 1.5.8 behavior and do not relax policy solely to keep sessions alive longer.

Note: `reuseRefreshTokens(false)` instructs SAS to issue a new refresh token and invalidate the old one. This is the foundation for rotation, but do not assume this setting alone implements every replay-detection and full-family revocation policy described in RFC 9700. If family-wide revocation is required, store token lineage/relationships and add replay handling in the authorization persistence/provider; test concurrent refresh requests and lost-response scenarios.

### 10.4. Sender-Constrained Tokens

RFC 9700 recommends that Authorization Servers and Resource Servers consider sender-constraining via mTLS or DPoP to reduce the value of stolen tokens. A token can only be used when the client proves possession of the key or certificate bound to that token.

## 11. DPoP per RFC 9449

DPoP is an application-layer proof-of-possession mechanism. The client generates a key pair and sends a DPoP proof JWT in an HTTP header. The Authorization Server binds the access token to the proof's public key; the Resource Server requires a corresponding proof whenever the client presents the token.

A DPoP proof typically contains:

- `typ=dpop+jwt`.
- `alg` set to an allowed asymmetric signature algorithm.
- `jwk` containing the public key, never the private key.
- `htm`: HTTP method.
- `htu`: target HTTP URI.
- `iat`: time the proof was created.
- `jti`: unique ID to prevent replay.
- `ath`: access token hash when the proof accompanies an access token.
- `nonce`: server-provided nonce if required by the server.

Flow:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant AS as Authorization Server
    participant RS as Resource Server
    C->>C: Create DPoP proof with private key
    C->>AS: Token request + DPoP header
    AS->>AS: Validate typ, alg, signature, htm, htu, iat, jti and nonce
    AS-->>C: DPoP-bound access token + token_type=DPoP
    C->>C: Create a new proof with ath for this access token
    C->>RS: Authorization: DPoP token + DPoP proof
    RS->>RS: Validate proof and token key binding
    RS-->>C: Protected resource
~~~

DPoP does not replace TLS, client authentication, or authorization. It only binds the token to the client's key; an attacker can still exploit XSS to use the token indirectly inside a browser holding the private key.

When calling a Resource Server, the client sends the access token using the `DPoP` authentication scheme, e.g., `Authorization: DPoP <access_token>`, together with the proof in the `DPoP` header. Do not send a DPoP-bound token under the `Bearer` scheme.

Spring Authorization Server 1.5.x supports DPoP-bound access tokens. When deploying:

- Check that metadata advertises supported DPoP algorithms.
- Allow only approved asymmetric signing algorithms.
- Validate `typ`, public JWK, `htm`, `htu`, `iat`, `jti`, `ath`, and `nonce`.
- Bound the validity window of proofs.
- Store used `jti` values in a replay cache shared across nodes.
- Align key-binding verification logic between the Authorization Server and Resource Servers.
- Do not accept a `Bearer` token in place of a DPoP-bound token when policy requires DPoP.

If the replay cache lives only in the memory of a single node, the same proof could be sent to another node in a cluster. Production needs a distributed replay store or equivalent mechanism.

## 12. Mutual TLS and Certificate-Bound Access Tokens

RFC 8705 defines two related capabilities:

1. Using a client certificate to authenticate an OAuth client at the Authorization Server.
2. Binding the access token to the certificate so the Resource Server requires the same private key when the token is used.

Both capabilities can be deployed independently or together. With SAS 1.5.8, `TokenSettings.x509CertificateBoundAccessTokens(true)` enables binding access tokens to certificates when the client uses `tls_client_auth` or `self_signed_tls_client_auth`.

Example `TokenSettings` configuration:

~~~java
TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .x509CertificateBoundAccessTokens(true)
        .build();
~~~

The snippet above is only one part of an mTLS deployment. The TLS infrastructure must require client certificates on the appropriate endpoints; the Authorization Server must verify the certificate against the client registration; the Resource Server must obtain the certificate from a trusted TLS layer and compare its thumbprint with the binding in the token or introspection response.

Do not trust `X-Forwarded-Client-Cert` or similar headers unless the proxy is authenticated, client-supplied headers are stripped, and there is an explicit certificate-forwarding contract. Certificate rotation and revocation must be synchronized with the client registry and Resource Servers.

`TokenSettings.x509CertificateBoundAccessTokens(true)` only takes effect in client authentication flows using `tls_client_auth` or `self_signed_tls_client_auth` and when the infrastructure actually supplies the corresponding certificate. Enabling this flag without implementing certificate verification at the TLS layer and Resource Server will not establish complete sender constraining.

## 13. Pushed Authorization Requests (PAR)

PAR per RFC 9126 allows a client to send the authorization request directly to the PAR endpoint over a back-channel. The Authorization Server returns a random, short-lived `request_uri`; the browser carries only that reference to the Authorization Endpoint.

Benefits:

- Reduces exposure of `scope`, `resource`, `claims`, and sensitive authorization parameters in browser URLs.
- The Authorization Server authenticates the client and validates the request early.
- The `request_uri` is unpredictable, bound to the submitting client, and time-limited.
- Can be combined with PKCE, signed request objects, and client authentication.

PAR does not eliminate validation at the Authorization Endpoint. The Authorization Server must still validate the request just like a normal authorization request. `request_uri` requires high entropy, binding to the client, and should be single-use; expired or replayed requests must be rejected.

Spring Authorization Server 1.5.8 provides a Pushed Authorization Request Endpoint and extension points to customize converters, providers, and response handlers. Never generate `request_uri` values from sequence numbers, user IDs, or predictable values.

## 14. Token Purpose, Audience, Scope, and Resource Authorization

A token with a valid signature can still be used for the wrong purpose. A Resource Server must verify at least:

1. `iss` matches a trusted issuer.
2. The signature verifies against a key from that issuer using an allowlisted algorithm.
3. `exp`, `nbf`, `iat`, and clock skew are within valid bounds.
4. `aud` contains the specific Resource Server/API handling the request.
5. Token type/purpose is appropriate; never accept an ID Token as an access token.
6. Scope/authorities are sufficient for the endpoint and action.
7. Tenant, subject, client, and resource bindings comply with policy.

Example:

| Token | Audience | Scope | Where used |
|---|---|---|---|
| Orders access token | `https://orders.api.example` | `orders.read` | Orders API |
| Payroll access token | `https://payroll.api.example` | `payroll.read` | Payroll API |
| OIDC ID Token | `employee-portal` | Not used as an API scope | OIDC client verifying login |

Do not issue tokens with overly broad audiences simply to reduce token requests. When multiple resources are needed, evaluate resource indicators or token exchange according to policy.

Never read `tenant_id`, role, or scope from client-supplied request headers. Those claims must be derived from client registration, authorization context, and validated policy.

## 15. Baseline Spring Authorization Server Configuration

### 15.1. Separating the Protocol Filter Chain

Spring Authorization Server provides `OAuth2AuthorizationServerConfigurer` to configure protocol endpoints. Skeleton configuration example:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http
        .securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(Customizer.withDefaults()))
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .exceptionHandling(exceptions ->
            exceptions.defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"),
                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

This is an illustrative skeleton for the Authorization Server and login UI. An application also needs `RegisteredClientRepository`, `OAuth2AuthorizationService`, `OAuth2AuthorizationConsentService`, `JWKSource<SecurityContext>`, `AuthorizationServerSettings`, and `JwtDecoder` when OIDC UserInfo or client registration is enabled. Do not copy this configuration while omitting persistence, key management, or session policy.

By default, Spring Authorization Server provides the Authorization Endpoint, Token Endpoint, introspection, revocation, metadata, and JWK Set endpoints; the JWK Set endpoint is configured only when a `JWKSource` bean is present. OIDC endpoints are enabled by calling `oidc(...)`; the Client Registration endpoint is disabled by default.

### 15.2. PKCE and Client Policy

Registering a public client:

~~~java
RegisteredClient publicClient = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("browser-public-client")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://app.example.com/oauth/callback")
        .scope(OidcScopes.OPENID)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .build();
~~~

For confidential clients, use an appropriate client authentication method and consider requiring PKCE for the Authorization Code Grant. Never store client secrets in source code.

In the confidential client example above, `portalSecret` must be retrieved from a secret manager or protected configuration source before encoding; never hard-code real secrets in source code. If the client uses `private_key_jwt` or mTLS, configure the corresponding metadata, key, or certificate instead of a client secret.

### 15.3. Token Lifetime and Refresh Policy

~~~java
TokenSettings tokenSettings = TokenSettings.builder()
        .authorizationCodeTimeToLive(Duration.ofMinutes(2))
        .accessTokenTimeToLive(Duration.ofMinutes(5))
        .refreshTokenTimeToLive(Duration.ofHours(8))
        .reuseRefreshTokens(false)
        .build();
~~~

These numbers are examples only. Choose TTLs based on risk, revocation capabilities, user experience, and business requirements. Authorization codes should have a short lifetime; Spring Authorization Server recommends at most 10 minutes for authorization codes.

### 15.4. Do Not Customize Validators in Ways That Weaken Defaults

SAS provides extension points for the Authorization Endpoint, Token Endpoint, PAR, and providers. When adding custom validators:

- Keep the default validators for redirect URI, scope, PKCE, client, and grant.
- Never bypass client authentication.
- Never accept a redirect URI just because the domain looks valid.
- Never trust audience or scope merely because it came from the request.
- Never leak internal exceptions or secrets in OAuth error responses.
- Test both the happy path and all error branches.

## 16. Protecting Login, Consent, Sessions, and the Browser

### 16.1. Session Fixation and Cookies

Spring Security provides session fixation protection; with Servlet 3.1+, the default is typically `changeSessionId`. Do not disable this protection without a clear reason and review.

Production session cookies should have:

- `Secure` when served over HTTPS.
- `HttpOnly` so JavaScript cannot read the session cookie.
- `SameSite` compatible with redirect/callback flows.
- Minimal necessary `Path` and `Domain`.
- Appropriate lifetime and idle timeout.

`SameSite` is defense-in-depth, not a replacement for CSRF tokens. For OIDC redirects, test `SameSite=Lax`/`None` in practice according to response mode and supported browsers.

### 16.2. CSRF Does Not Disappear Just Because an API Is Stateless

If the browser automatically sends cookies or Basic credentials, an application can still be vulnerable to CSRF even if the backend stores no session. Keep CSRF protection for login forms, consent forms, logout, and admin UIs. If an endpoint accepts only bearer tokens in the `Authorization` header and does not use browser cookies, CSRF can be evaluated differently, but you must verify how credentials are transmitted.

### 16.3. CORS Is Not Authentication

CORS controls whether a browser is allowed to read cross-origin responses. It does not authenticate clients and does not block all attacker-initiated requests. Never use `allowedOrigins("*")` with credentialed requests. Allow only the origins, methods, and headers strictly needed; distinguish CORS policies across the Authorization Endpoint, Token Endpoint, and APIs.

### 16.4. Security Response Headers

Spring Security provides default security headers such as `Cache-Control`, `X-Content-Type-Options`, HSTS over HTTPS, and `X-Frame-Options`. CSP is not enabled by default because policies are application-specific.

Example adding CSP for login/consent UIs:

~~~java
http.headers(headers -> headers
        .contentSecurityPolicy(csp -> csp
                .policyDirectives(
                        "default-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'")));
~~~

The policy above is an example only. Test login/consent pages, static resources, inline scripts, and identity provider integrations before enforcing it. Never disable all default headers just to fix a rendering issue.

## 17. Signing Keys, Issuer, and Metadata

### 17.1. Signing Keys Are High-Value Assets

If a signing private key is exposed, an attacker can forge JWTs bearing a valid issuer. Controls:

- Use asymmetric signing keys.
- Keep private keys in a KMS/HSM or protected secret store.
- Restrict signing permissions by service identity.
- Never commit private keys to source control.
- Never generate a new random key on every restart.
- Use a unique `kid` in the JWK Set and allowlist algorithms.
- Audit key creation, activation, rotation, and revocation.

### 17.2. Rotation with Overlap

Safe rotation procedure:

1. Generate a new key and new public JWK.
2. Publish the new public key in the JWKS.
3. Wait for Resource Servers to refresh their caches or verify they can consume the new key.
4. Switch signing to the new key.
5. Keep the old public key published until the last token signed by the old key expires, plus clock skew and JWKS cache lifetime.
6. Remove the old public key and destroy the private key per retention policy.

If a key is compromised, follow the incident plan: stop signing with it, switch keys, remove the compromised key from JWKS, flush caches, revoke affected tokens/authorizations, and assess the exposure window. Removing a key from JWKS does not guarantee that every Resource Server with cached keys will immediately reject tokens.

### 17.3. Issuer and Metadata Must Be Stable

The Issuer URI is the Authorization Server's identifier and must match exactly across metadata, ID Tokens, and access tokens. Do not derive the issuer from an arbitrary `Host` header. Behind a reverse proxy, trust forwarded headers only from a configured, protected proxy.

Example configuring a fixed issuer for an Authorization Server:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

If deploying multiple issuers on the same host, use a dedicated multi-tenant design and an allowlisted issuer registry. Never mix a static issuer with an issuer inferred from an untrusted `Host` header.

Clients and Resource Servers must use metadata/JWKS URIs obtained from a trusted configured issuer. Never fetch arbitrary `jku` or `x5u` URLs from JWT headers. Do not allow user-supplied metadata URLs to cause SSRF.

## 18. Dynamic Client Registration and the Administrative Plane

Spring Authorization Server disables the OIDC Dynamic Client Registration endpoint by default. If enabled:

- Allow registration only under policy and an approval workflow.
- Restrict grants, redirect URIs, scopes, token endpoint auth methods, and JWKS URIs.
- Do not let public registration create confidential clients or self-grant sensitive privileges.
- Enforce rate limits, auditing, quotas, and ownership validation.
- Do not fetch arbitrary metadata/JWKS URLs without SSRF protections.
- Support suspending/revoking clients and rotating credentials.

Administrative APIs that modify `RegisteredClient`, signing keys, issuer settings, consents, or token policies must enforce strong authentication, role-based authorization, MFA/step-up for risky operations, and immutable auditing. Never let admin endpoints share authorization rules with public endpoints.

## 19. Availability, Abuse, and Rate Limiting

An Authorization Server has endpoints that can be abused to exhaust CPU, database, KMS, or external identity providers:

| Endpoint/activity | Abuse pattern | Controls |
|---|---|---|
| Login | Password spraying, credential stuffing | Rate limit per account/IP/device, MFA, breached-password detection |
| Authorization | Request floods, consent spam | Rate limit, client policy, early request validation |
| PAR | Repeated `request_uri` generation | Client authentication, short TTL, quotas, one-time references |
| Token | Code/secret brute force, invalid grant floods | Client auth, PKCE, rate limit, replay detection |
| Introspection | Token guessing, CPU/database exhaustion | Require authenticated resource server, quotas, and policy-based caching |
| Revocation | Request floods | Client auth, rate limit, and auditing |
| Device authorization | User-code guessing and polling floods | User code entropy, throttling, interval enforcement |
| JWKS/metadata | Cache-busting or request floods | Appropriate CDN/caching, rate limit, and availability controls |
| KMS/HSM | Signing request floods | Quotas, circuit breakers, bounded queues, and capacity planning |

Do not rate-limit by IP alone. A NAT proxy can represent many users, while a botnet has many IPs. Combine client ID, account, device/session, IP reputation, and endpoint-specific limits.

Design timeouts, bounded retries, circuit breakers, and bulkheads for database/KMS/external IdPs. Never retry token exchanges or login requests indefinitely. Ensure synchronized clocks so `iat`, `exp`, DPoP proofs, and certificate validations produce consistent results.

## 20. Logging, Monitoring, and Incident Response

### 20.1. Security Events to Observe

Record structured events for:

- Login success/failure and MFA outcomes.
- Client authentication failures.
- Redirect URI mismatches.
- PKCE missing/invalid/downgrade attempts.
- Authorization code replay.
- Refresh token reuse/replay.
- Invalid issuer/audience/signature.
- DPoP proof invalid/replay/nonce failures.
- mTLS certificate mismatch/expiry.
- PAR invalid, expired, or replayed request URIs.
- Client registration/update/suspension.
- Signing key activation/rotation/revocation.
- Consent grants/revocations.
- Administrative policy changes.

Logs should include timestamp, request/correlation ID, issuer, client ID, endpoint, grant type, error category, and outcome. Never log raw tokens, codes, secrets, passwords, DPoP proofs, or private keys.

### 20.2. Behavioral Alerts

Set up alerts when:

- `invalid_client`, `invalid_grant`, or PKCE failure rates spike.
- A client requests unusual scopes or audiences.
- Refresh-token replay is detected.
- Numerous redirect URI mismatches occur.
- DPoP `jti` replay or nonce downgrade occurs.
- KMS signing errors, JWKS fetch failures, or issuer metadata mismatches appear.
- Admins modify redirect URIs, grants, scopes, or signing keys outside change windows.

### 20.3. Incident Runbooks

**Client secret/private key exposure:** disable the client or credential, issue a new credential, rotate per procedure, review issued tokens/authorizations, and inspect logs.

**Signing key compromise:** stop signing with the compromised key, activate a new key, update JWKS, handle Resource Server caches, revoke affected tokens/authorizations, and assess issuer impact scope.

**Refresh-token replay:** revoke the affected token family/grant, require user re-authentication, inspect client/device state, and preserve audit evidence.

**Spoofed issuer/metadata:** block the discovery source, check DNS/TLS/proxies, verify issuer/JWKS trust configuration, and rotate keys if compromise is possible.

**Abused client:** suspend the client, throttle token issuance, revoke refresh tokens/authorizations, and notify the owner per incident policy.

## 21. Threat Matrix and Security Testing

| Threat | Exploitation condition | Security control | Test |
|---|---|---|---|
| Redirect URI manipulation | AS accepts wildcards/prefixes | Exact matching | A redirect URI differing by one character must be rejected |
| Open redirect | Client/AS redirects to arbitrary URLs | Destination allowlist | `next=https://evil.test` must not redirect |
| Authorization code interception | Code is intercepted | PKCE S256, TLS, single-use code | Code cannot be exchanged with a missing or wrong verifier |
| Code injection | Attacker injects a code from another transaction | PKCE, state/nonce, client binding | A code from a different transaction must fail |
| PKCE downgrade | Token request bypasses challenge | Enforce verifier only if challenge existed | Sending a verifier for a code without a challenge must be rejected |
| CSRF | Attacker crafts callback/form request | State/nonce/PKCE and CSRF token | Wrong state, wrong nonce, or missing CSRF token all fail |
| Mix-up | Client supports multiple issuers | RFC 9207 `iss` or distinct redirect URI | Response from the wrong issuer must abort |
| Client impersonation | Secret/key leaked or weak auth | `private_key_jwt`/mTLS, credential rotation | Wrong/expired credentials or cert mismatch rejected |
| Token replay | Bearer token stolen | Short TTL, DPoP/mTLS, audience | Token without proof or with wrong key is rejected |
| Refresh-token replay | Old token is reused | Rotation or sender constraint | Reusing an old token revokes the family per policy |
| Audience confusion | API checks signature only | Audience validator | Validly signed token with wrong `aud` is rejected |
| Scope escalation | Trusting scope from request | Client/resource policy | Scopes outside the allowlist are not granted |
| ID Token as access token | API accepts any JWT | Token purpose/type/audience validation | ID Token sent to an API must be rejected |
| DPoP proof replay | Proof is resent | `jti` replay cache, `iat` window, nonce | Reusing the same proof across nodes is rejected |
| mTLS binding bypass | Proxy/header spoofs certificate | TLS layer binding and trusted proxy | Certificate not matching token is rejected |
| PAR replay | `request_uri` guessed or reused | Entropy, client binding, TTL, one-time use | Expired, wrong-client, or replayed `request_uri` is rejected |
| SSRF via metadata/JWKS | Untrusted URL fetched | Allowlist, IP/network policy | URLs to loopback/private IPs are blocked |
| Key compromise | Private signing key leaked | KMS/HSM, rotation, least privilege | Rotation and cache invalidation are rehearsed |
| CSRF via cookie | Browser sends session cookie automatically | CSRF token, SameSite defense-in-depth | POST without CSRF token is rejected |
| CORS misconfiguration | Wildcard origin + credentials | Exact origin allowlist | Disallowed origins receive no CORS headers |
| DoS | Endpoint flooded | Rate limit, quotas, bounded work | Load tests do not exhaust pools/KMS/database |

### 21.1. Testing PKCE

For a client requiring PKCE:

1. Send an Authorization Request with an `S256` challenge.
2. Exchange the code with the right verifier and confirm success.
3. Exchange the code with the wrong verifier and confirm `invalid_grant`.
4. Omit the verifier and confirm failure.
5. Send a verifier for an authorization code created without a challenge and confirm rejection.
6. Attempt to use an already-exchanged code a second time and confirm replay rejection.

### 21.2. Testing Redirects and Issuer

- Exact redirect URI match succeeds.
- Changing scheme, host, path, port, or query in any unregistered way must fail.
- Responses from a different issuer must be aborted by the client.
- Codes must not be forwarded to a URL taken from a query parameter.
- Spoofed `Host` headers must not alter the internal issuer.

### 21.3. Testing Tokens and Resource Server

- Expired tokens, invalid signatures, wrong issuer, wrong audience, or wrong token purpose are all rejected.
- Tokens with insufficient scope cannot call sensitive APIs.
- ID Tokens are never accepted as access tokens.
- DPoP-bound tokens must be accompanied by a proof matching key, URI, method, time, `jti`, and `ath`.
- mTLS-bound tokens must be presented over the matching client certificate.

### 21.4. Operational Testing

- Refresh-token reuse detects replay and revokes the proper family.
- Key rotation includes overlap and Resource Servers pick up the new key.
- Revocation and introspection work across multiple nodes.
- Rate limits and circuit breakers do not trigger retry storms.
- Audit logs contain no credentials or tokens.
- Backup/restore of the authorization store and key metadata preserves integrity.

## 22. Hands-On Exercise

**Scenario:** Deploy an Authorization Server for `employee-portal`, `mobile-app`, `orders-api`, and `payroll-api`. Browser/mobile use Authorization Code; workloads use Client Credentials. The system has two external issuers for federation and one internal issuer.

### Requirements

1. List the system's assets and trust boundaries.
2. Identify threat actors that could access the browser, client secrets, reverse proxy, and KMS.
3. Register a public client with Authorization Code + PKCE S256.
4. Register a confidential client using appropriate client authentication.
5. Configure exact redirect URI matching and test open redirect scenarios.
6. Verify `state`, `nonce`, and issuer mix-up protection for clients supporting multiple IdPs.
7. Configure PAR for appropriate clients and test `request_uri` binding and replay.
8. Enable DPoP or mTLS for an API with high token replay risk.
9. Configure access token TTL, refresh-token rotation, and replay detection.
10. Configure Resource Servers to validate issuer, audience, token type, and scope.
11. Protect login, consent, and admin UIs with session, CSRF, and security headers.
12. Configure rate limiting for login, token, introspection, PAR, and device authorization.
13. Write audit events and alerts for client auth failures, replay, and key rotation.
14. Create a threat matrix and integration tests for the attack scenarios.
15. Write runbooks for client secret exposure, refresh-token replay, and signing-key compromise.

**Completion criteria:** every client has an explicit policy; Authorization Codes are protected by PKCE; redirect URIs match exactly; Resource Servers reject tokens with wrong issuer/audience/purpose; refresh-token replay is detected; secrets/keys never appear in logs; sensitive endpoints have rate limiting and auditing.

## 23. Pre-Production Checklist

- [ ] Threat model documents assets, actors, trust boundaries, and attack surface.
- [ ] Only necessary grant types are enabled; Implicit and Resource Owner Password Credentials are disabled.
- [ ] Authorization Codes are protected with PKCE S256; PKCE is also considered for confidential clients.
- [ ] Redirect URIs use exact matching; no wildcards or open redirectors exist.
- [ ] `state`/`nonce` are transaction-specific and bound to the browser session.
- [ ] Multi-issuer clients implement mix-up defense via RFC 9207 or distinct redirect URIs.
- [ ] Public clients contain no client secret.
- [ ] Confidential clients use appropriate authentication methods and credential lifecycles.
- [ ] Clients are granted only the necessary grants, scopes, resources, and audiences.
- [ ] Authorization codes are short-lived and single-use.
- [ ] Access token TTLs are appropriate; tokens are never passed in URLs.
- [ ] Refresh tokens are issued only when needed; rotation or sender constraining is in place for public clients.
- [ ] DPoP/mTLS is evaluated for APIs with high token replay risk.
- [ ] PAR is enabled for appropriate clients; `request_uri` has entropy, binding, TTL, and replay policy.
- [ ] Resource Servers validate issuer, signature, audience, expiration, token purpose, and scope.
- [ ] Signing keys reside in KMS/HSM or a protected secret store; a rotation runbook exists.
- [ ] Issuer/metadata/JWKS URIs are stable; forwarded headers are trusted only from managed proxies.
- [ ] CSRF still protects login, consent, logout, and admin UIs.
- [ ] CORS uses an origin allowlist; CORS is not treated as authentication.
- [ ] Session fixation protection, `Secure`/`HttpOnly`/`SameSite` cookies, and timeouts are configured.
- [ ] Security headers are retained; CSP is designed and tested separately.
- [ ] DCR/admin endpoints are restricted and audited.
- [ ] Login/token/PAR/introspection/device/JWKS have rate limits and capacity plans.
- [ ] Logs/traces contain no tokens, codes, passwords, secrets, or private keys.
- [ ] Alerts exist for replay, issuer/audience mismatch, client auth failure, and key events.
- [ ] A test matrix and rehearsed incident response runbooks exist.

## 24. Summary

OAuth 2.0 Security Best Current Practice requires designing security across the entire flow rather than relying solely on JWT signatures or a single framework setting.

Core principles:

1. Use the Authorization Code Grant with PKCE S256; eliminate insecure flows.
2. Perform exact redirect URI matching and eliminate open redirectors.
3. Bind authorization responses to the client, browser transaction, and issuer.
4. Authenticate confidential clients with protected credentials; public clients have no secret.
5. Mitigate token replay using TTLs, refresh rotation, DPoP, or mTLS.
6. Constrain scopes, audiences, resources, and token purpose.
7. Protect login/session/consent with CSRF, cookie policies, and security headers.
8. Protect signing keys, metadata, client registries, and the administrative plane.
9. Prevent abuse with rate limiting, quotas, bounded work, and monitoring.
10. Test attack scenarios and rehearse incident response.

Spring Authorization Server 1.5.8 provides the extension points and protocol support needed for many controls such as PKCE, PAR, DPoP, mTLS, token settings, and endpoint customization. However, applications must still define client policies, key lifecycles, Resource Server validation, CSRF/session handling, rate limiting, logging, and operations aligned with their threat model.

### References

1. [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): threat model and BCP requirements for redirects, PKCE, mix-up, token replay, refresh tokens, and client authentication.
2. [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636.html): code verifier, challenge, and S256.
3. [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207.html): `iss` in authorization responses to prevent mix-up.
4. [RFC 9126 — OAuth 2.0 Pushed Authorization Requests](https://www.rfc-editor.org/rfc/rfc9126.html): PAR endpoint, `request_uri`, client binding, and replay.
5. [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449.html): proof JWT, `ath`, nonce, and replay protection.
6. [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705.html): mTLS client auth and certificate-bound tokens.
7. [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html): issuer, endpoints, and capability metadata.
8. [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): default endpoints, `JWKSource`, and OIDC configuration.
9. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Authorization Endpoint, Token Endpoint, PAR, and DPoP.
10. [Spring Authorization Server 1.5.8 — How-to: Authenticate using a Single Page Application with PKCE](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-pkce.html): public client, PKCE, and BFF guidance.
11. [Spring Authorization Server 1.5.8 — ClientSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/ClientSettings.Builder.html): `requireProofKey` and consent settings.
12. [Spring Authorization Server 1.5.8 — TokenSettings.Builder API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/settings/TokenSettings.Builder.html): access/refresh/code TTL, refresh token reuse, and mTLS binding.
13. [Spring Security 6.5 — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html): CSRF tokens and SPA integration.
14. [Spring Security 6.5 — Security HTTP Response Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html): default headers, HSTS, and CSP.
15. [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session fixation, session persistence, and concurrent session controls.
