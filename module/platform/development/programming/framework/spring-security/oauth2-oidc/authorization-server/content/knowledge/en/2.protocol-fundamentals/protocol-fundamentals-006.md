# Redirect URI, Issuer Identifier, and Discovery Document

> **Scope:** Protocol and Terminology — learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in Spring Boot. This lesson focuses on three easily confused concepts: where the browser returns after authorization, the identity of the authorization server, and the document describing that server's endpoints.

## 1. Three Concepts, Three Different Questions

In a system with a web application (`OAuth Client`), an authentication/authorization server (`Authorization Server` or `OpenID Provider`), and an API (`Resource Server`), these three values serve three distinct roles:

| Concept | Question answered | Example | Who configures/uses it |
|---|---|---|---|
| **Redirect URI** | After the user completes the authorization step, **where** does the Authorization Server send the browser back? | `https://app.example.vn/login/oauth2/code/portal` | Client declares callback; Authorization Server stores the registered URI list and validates requests |
| **Issuer Identifier** (`issuer`) | **Which Authorization Server** issued this token and metadata set? | `https://login.example.vn` | Authorization Server publishes it; Client/Resource Server validates it |
| **Discovery Document** | To integrate with this issuer, **which endpoints to call, what features are supported, and where to fetch public keys**? | `https://login.example.vn/.well-known/openid-configuration` | Authorization Server publishes JSON document; Client/Resource Server reads it |

**Remember:** Redirect URI belongs to the **Client** side; issuer identifies the **Authorization Server** side; the discovery document describes how to interact with the **issuer**. The discovery URL is constructed from the issuer according to standard rules, whereas redirect URIs are registered individually per client.

Running example:

- Authorization Server: `https://login.example.vn`.
- Spring Boot application acting as OAuth2/OIDC Client: `https://app.example.vn`, `client_id=web-client`, `registrationId=portal`.
- Redirect URI: `https://app.example.vn/login/oauth2/code/portal`.
- API validating JWTs: `https://api.example.vn`.

## 2. How Do They Work Together?

~~~mermaid
sequenceDiagram
    autonumber
    participant Client as OAuth2/OIDC Client
    participant Browser as Browser
    participant AS as Authorization Server
    participant API as Resource Server

    Client->>AS: GET /.well-known/openid-configuration
    AS-->>Client: JSON: issuer, endpoints, jwks_uri
    Browser->>Client: Request login
    Client-->>Browser: Redirect to authorization_endpoint (state, PKCE, redirect_uri)
    Browser->>AS: GET /oauth2/authorize?...
    AS->>Browser: Authenticate user and obtain consent when needed
    AS-->>Browser: 302 Location: redirect_uri?code=...&state=...
    Browser->>Client: GET /login/oauth2/code/portal?code=...&state=...
    Client->>Client: Match state and transaction session
    Client->>AS: POST /oauth2/token (code, redirect_uri, code_verifier, client authentication if applicable)
    AS-->>Client: Token response (OIDC may include id_token)
    Client->>Client: Validate ID Token: signature, iss, aud, exp, nonce when applicable
    Client->>API: Call API with access token
    API->>AS: Fetch metadata/JWKS when needed
    API->>API: Validate signature, issuer, lifetime, audience/scope per policy
    API-->>Client: Permitted resource
~~~

The diagram illustrates an **Authorization Code + PKCE** flow. Fetching metadata/JWKS may occur at startup, on first use, or upon key refresh, depending on the library. Discovery is not mandatory for every OAuth 2.0 integration: systems can still configure static endpoints if the protocol/library allows.

## 3. Redirect URI: Return Path of the Authorization Response

### 3.1. What Is a Redirect URI?

In the Authorization Code Flow, the client includes the `redirect_uri` parameter in the authorization request. After authentication and processing the authorization decision, the Authorization Server sends the **authorization code** along with `state` (if sent) back to the callback via the browser. The client then uses the authorization code to call `token_endpoint` over the back channel.

~~~http
GET /oauth2/authorize?response_type=code
    &client_id=web-client
    &redirect_uri=https%3A%2F%2Fapp.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal
    &scope=openid%20profile
    &state=RANDOM_CSRF_VALUE
    &nonce=RANDOM_OIDC_VALUE
    &code_challenge=BASE64URL_SHA256_OF_VERIFIER
    &code_challenge_method=S256
Host: login.example.vn
~~~

The lines above are split for readability; an actual HTTP request must put the entire query on a single line and URL-encode it properly. `state`, `nonce`, `code_verifier`, and `code_challenge` must be generated per transaction with appropriate randomness; uppercase values are placeholders.

Upon successful processing, the Authorization Server responds like this:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.vn/login/oauth2/code/portal?code=AUTH_CODE&state=RANDOM_CSRF_VALUE
~~~

**The callback is not the token endpoint.** The URL `/login/oauth2/code/portal` is an endpoint on the **client application**, handled by Spring Security's OAuth2 Login mechanism per configuration. It receives `code` so the client can exchange it for tokens; it is not `/oauth2/token` on the Authorization Server. Tokens should not appear in the callback URL in the Authorization Code Flow.

### 3.2. Exact Registration and Validation

The Authorization Server must store valid Redirect URIs per `client_id`. For web apps, the URI should be full HTTPS specifying the host and callback path. Under OAuth 2.0 Security Best Current Practice (RFC 9700), URI matching must use **exact string comparison**; the standard defines an exception regarding variable port numbers on loopback `localhost` redirect URIs for native apps. Do not rely on prefixes, wildcards, or fuzzy matching.

| Registered URI | URI appearing in request | Expected result |
|---|---|---|
| `https://app.example.vn/callback` | `https://app.example.vn/callback` | Match |
| `https://app.example.vn/callback` | `https://app.example.vn/callback/` | No match: extra `/` |
| `https://app.example.vn/callback` | `http://app.example.vn/callback` | No match: different scheme |
| `https://app.example.vn/callback` | `https://app.example.vn.evil.test/callback` | No match: different host |
| `https://app.example.vn/callback` | `https://app.example.vn/callback?next=https://evil.test` | No match unless this exact query was registered |

A valid Redirect URI may contain registered query parameters, but must not open an arbitrary forwarding mechanism such as `?next=<user-supplied URL>`. The Authorization Server must **reject requests with an invalid redirect URI** and avoid sending error codes or authorization codes to untrusted URIs. The client must defend against open redirects at the callback.

In addition to validation at the authorization endpoint, when exchanging an authorization code for tokens, `redirect_uri` (if used in the authorization request) must match the value bound to the authorization code; the Authorization Server also binds the code to the exact client. PKCE adds `code_verifier` to prevent stolen codes from being redeemed, but does not replace redirect URI and `state` validation.

### 3.3. Distinguishing from Other URIs

- `redirect_uri` is used for the authorization response; each RegisteredClient may register multiple values, but whichever value a request uses must be validated exactly.
- `post_logout_redirect_uri` in OIDC RP-Initiated Logout is the return target after logout, with its own registration/validation mechanism; do not use it in place of the authorization callback.
- `authorization_endpoint` is where authorization requests begin on the Authorization Server; `token_endpoint` receives code-for-token exchange requests; neither is a client redirect URI.
- `state` helps the client correlate the authorization response with the initial request and prevent CSRF; `nonce` binds the ID Token to the corresponding OIDC authentication session when applicable.

## 4. Issuer Identifier: Stable Identity of the Authorization Server

The issuer is the URL identifying the **issuing authority**. Example:

~~~text
https://login.example.vn
~~~

In OIDC, the exact same identifier must appear consistently in:

1. The `issuer` value in the OpenID Provider Configuration (discovery document).
2. The `iss` claim of **ID Tokens** issued by that issuer.
3. The issuer value trusted and used by the client application to validate tokens.

For **JWT access tokens** carrying an `iss` claim, the Resource Server must also validate `iss` against the trusted issuer value, alongside signature, expiration, and related constraints such as audience. Do not assume every access token is a JWT: opaque access tokens have no JSON claims for the resource server to parse directly.

Illustrative payload excerpt of an ID Token:

~~~json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": "web-client",
  "exp": 1890000000,
  "iat": 1889996400,
  "nonce": "RANDOM_OIDC_VALUE"
}
~~~

This is merely an **example payload**, not a validly signed JWT. `iss` states who issued it; `aud` states whom the token is intended for; `sub` identifies the user subject within the issuer's context. The client must verify the ID Token signature with the appropriate key, `iss`, `aud`, validity timestamps, and related OIDC conditions. Checking only the signature while ignoring issuer/audience is insecure.

**Issuer constraints:**

- In production deployments, the issuer uses `https://`, contains no query or fragment, and is a public, stable URL reachable by other components. Local demos may use HTTP loopback per test environment; that is not a production deployment pattern.
- Match against the **exact configured and published value**. `https://login.example.vn`, `https://login.example.vn/`, and `https://login.example.vn/auth` are three different strings; never strip trailing `/`, rewrite hosts, or alter paths when validating `iss`.
- The issuer is not the client's callback domain. Changing the issuer can break discovery, JWT validation, or trust configurations on clients/resource servers; plan migrations carefully.
- A single hostname can serve multiple issuers by path, but must comply with the corresponding discovery rules and thoroughly verify actual product/library support.

### 4.1. Why Do Proxies/Load Balancers Often Cause Issuer Errors?

An Authorization Server may run on `http://localhost:9000` inside a container while exposed via a gateway at `https://login.example.vn`. If the issuer is inferred from internal request URLs or improperly handled forwarded headers, metadata and `iss` may accidentally carry `http://...`, an internal hostname, or the wrong path. Resource Servers configured with the public issuer will reject tokens.

With Spring Authorization Server, prefer configuring the public issuer **explicitly** via `AuthorizationServerSettings`. If the protocol requires deriving URLs behind a proxy, configure forwarded headers strictly for trusted infrastructure and verify the actual host, scheme, port, and context path. Never unconditionally trust `X-Forwarded-*` headers arriving directly from the internet.

## 5. Discovery Document: Machine-Readable Description

The discovery document is a JSON document publishing metadata about the Authorization Server/OpenID Provider so clients, SDKs, and Resource Servers can locate endpoints and supported capabilities without hardcoding individual URLs.

### 5.1. Two Common Discovery Standards

| Standard | Metadata URL when issuer is `https://login.example.vn` | Purpose |
|---|---|---|
| **OpenID Connect Discovery 1.0** | `https://login.example.vn/.well-known/openid-configuration` | OpenID Provider metadata; used for OIDC login, `issuer` info, endpoints, keys, and OIDC capabilities |
| **OAuth 2.0 Authorization Server Metadata — RFC 8414** | `https://login.example.vn/.well-known/oauth-authorization-server` | Authorization Server metadata per OAuth 2.0, even when OIDC is not enabled |

The two documents share many fields yet are **not identical across all requirements and semantics**. Spring Authorization Server includes the OAuth Authorization Server Metadata endpoint in its default protocol configuration; the OIDC Provider Configuration endpoint appears only when **OIDC is enabled**. The JWK Set endpoint requires a configured `JWKSource<SecurityContext>`. Do not guess the JWK URL or assume OIDC is enabled merely because `/oauth2/authorize` responds.

**Case of an issuer with a path:** Well-known construction rules are not identical between the two specifications. Given issuer `https://login.example.vn/tenant-a`:

- OIDC Discovery 1.0 appends at the end of the issuer: `https://login.example.vn/tenant-a/.well-known/openid-configuration`.
- RFC 8414 inserts the well-known segment before the issuer's path: `https://login.example.vn/.well-known/oauth-authorization-server/tenant-a`.

Some libraries probe additional compatible metadata locations. When deploying path/tenant-based issuers, verify the URL **actually published** by the Authorization Server and how the client library resolves it; do not assume every variant is supported.

### 5.2. Example `.well-known/openid-configuration` Document

~~~json
{
  "issuer": "https://login.example.vn",
  "authorization_endpoint": "https://login.example.vn/oauth2/authorize",
  "token_endpoint": "https://login.example.vn/oauth2/token",
  "jwks_uri": "https://login.example.vn/oauth2/jwks",
  "userinfo_endpoint": "https://login.example.vn/userinfo",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic"]
}
~~~

The URLs and capability lists above are **illustrative data**, not a guarantee that they represent the full metadata or algorithms/capabilities returned by Spring Authorization Server in every configuration. Always inspect the actual response from the server.

Fields to understand:

| Field | Proper usage |
|---|---|
| `issuer` | Verify it equals the trusted issuer; must match `iss` in ID Tokens |
| `authorization_endpoint` | Direct the browser here to initiate the Authorization Code Flow |
| `token_endpoint` | Client calls over the back channel to exchange codes, using registered PKCE/client authentication |
| `jwks_uri` | Fetch **public keys** to verify JWT signatures; this is a key-fetching URL, not the issuer or discovery URL |
| `userinfo_endpoint` | When provided, the client can fetch user claims using an appropriate OIDC access token |
| `response_types_supported`, `grant_types_supported` | Response/grant types the server advertises support for |
| `scopes_supported`, `token_endpoint_auth_methods_supported` | Scopes and client authentication methods published by the server |

Metadata can be fetched publicly via HTTP GET without logging in; it is **public configuration**. It contains no client secrets or private signing keys. In particular, JWKS publishes public keys and `kid` values for selecting verification keys. Never confuse `jwks_uri` with an API returning private keys; private keys must remain protected on the server.

### 5.3. Discovery Does Not Replace Validation

Fetching a JSON document containing `issuer` and `jwks_uri` does not automatically make a server trustworthy. An application must start from a configured/allowed issuer, retrieve metadata over a secure connection, match the `issuer` field, and validate tokens per protocol. Never accept an arbitrary issuer URL from a user to auto-fetch metadata without strict allowlisting and controls, as that introduces SSRF risks or trusting an attacker-controlled token issuer.

For a Resource Server, discovery helps locate JWKS automatically, but is **not sufficient** to decide whether a token is authorized to call a specific API: you must still check audience, scopes/authorities, and API access rules.

## 6. Configuration with Spring Authorization Server

The examples below illustrate the relevant components in Spring Boot using the Spring Authorization Server 1.5.x Java API. They are **focused configuration snippets** that belong inside a `@Configuration` class alongside other infrastructure beans such as `JWKSource`, user login mechanisms, and appropriate authorization storage. Depending on the Spring Security/Spring Authorization Server version, integration API names may differ.

### 6.1. Pinning the Public Issuer

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://login.example.vn")
        // Keep defaults: /oauth2/authorize, /oauth2/token, /oauth2/jwks, ...
        .build();
}
~~~

If `.issuer(...)` is omitted, Spring Authorization Server may derive the issuer from the incoming request. Explicit configuration is preferable when running behind a reverse proxy, multiple pods, or multiple domains.

### 6.2. Registering a Redirect URI for a Client

~~~java
@Bean
RegisteredClientRepository registeredClientRepository() {
    RegisteredClient portal = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("web-client")
        // Illustrative only for reading the flow; NEVER use {noop} secrets in production.
        .clientSecret("{noop}demo-secret")
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://app.example.vn/login/oauth2/code/portal")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .clientSettings(ClientSettings.builder()
            .requireProofKey(true)
            .requireAuthorizationConsent(true)
            .build())
        .build();

    return new InMemoryRegisteredClientRepository(portal);
}
~~~

Here `.redirectUri(...)` is an **allowed URI** for `web-client`; it does not create a callback endpoint on the Authorization Server. Spring Security on the client application side must actually handle `/login/oauth2/code/portal`. In production, use encoded secrets, secret management, and a durable RegisteredClient store; do not generate a fresh random ID for a registered client on every server startup if stable identifiers/persistence are needed.

For public clients (such as SPAs or native apps), client secrets cannot be trusted: use `ClientAuthenticationMethod.NONE`, Authorization Code + PKCE, app-appropriate callbacks, and platform-specific protections. `requireProofKey(true)` forces the client to send PKCE, preventing downgrade to non-PKCE flows.

### 6.3. Enabling OpenID Connect Provider Configuration

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
        throws Exception {
    OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServer.getEndpointsMatcher())
        .with(authorizationServer, server ->
            server.oidc(Customizer.withDefaults()))
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .exceptionHandling(exceptions -> exceptions
            .defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"),
                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

    return http.build();
}
~~~

The corresponding imports come from Spring Security and Spring Authorization Server packages (e.g., `org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer`). The application also needs a filter chain handling user login, a `JWKSource<SecurityContext>` to sign/publish public keys, and a `JwtDecoder` when using OIDC endpoints that require it. Example decoder bean:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

`.oidc(Customizer.withDefaults())` enables OIDC endpoints, including Provider Configuration and UserInfo; **OIDC Dynamic Client Registration** is not enabled by default. If you only use OAuth 2.0 without enabling OIDC, do not expect `/.well-known/openid-configuration` to be available.

### 6.4. Spring Security Client Using Issuer for Discovery

The following configuration belongs to the **client application** `https://app.example.vn`, not the Authorization Server:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: company-idp
            client-id: web-client
            client-secret: ${PORTAL_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          company-idp:
            issuer-uri: https://login.example.vn
~~~

Spring Security replaces `{baseUrl}` and `{registrationId}` with the client's public base URL and `portal`, yielding `https://app.example.vn/login/oauth2/code/portal`. This value must **match exactly** the URI registered on the Authorization Server. Setting `issuer-uri` lets the client fetch metadata instead of manually entering `authorization-uri`, `token-uri`, and `jwk-set-uri` for each endpoint.

If the client app runs behind a gateway, configure public base URL / forwarded header resolution consistently so it does not generate `http://localhost:8080/login/oauth2/code/portal` inconsistent with the registered value.

### 6.5. Resource Server Verifying the JWT Issuer

Example configuration for the **API application**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.vn
~~~

Once the required Resource Server and JOSE starters/dependencies are added, Spring Security uses the issuer to locate metadata/JWKS and validate the JWT's `iss` claim. Depending on configuration, you can specify `jwk-set-uri` directly to reduce startup dependency on fetching discovery; when doing so, still retain `issuer-uri` to validate `iss`. Checking `aud` and API-level authorization requires separate configuration/evaluation.

## 7. Verification and Troubleshooting

### 7.1. Checking Discovery and JWKS via HTTP Commands

After launching the system on the proper domain (or substituting your test environment host), run:

~~~bash
curl -fsS https://login.example.vn/.well-known/openid-configuration \
  | jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri}'

curl -fsS https://login.example.vn/.well-known/oauth-authorization-server \
  | jq '{issuer, authorization_endpoint, token_endpoint}'

curl -fsS https://login.example.vn/oauth2/jwks \
  | jq '{key_count: (.keys | length)}'
~~~

Expected behavior: the OIDC endpoint returns JSON if OIDC is enabled; both metadata documents have `issuer` **exactly equal to** `https://login.example.vn`; the public JWKS endpoint returns a list of keys when a JWKSource is present. The `jwks_uri` field in metadata is the source of truth for the JWKS URL: if customized, read the URL from JSON before testing.

Note: thorough verification requires registering a client and executing an actual Authorization Code + PKCE flow. The GET commands above only confirm metadata discoverability; they do not prove a token or callback is secure.

### 7.2. Minimal Valuable Test Suite

1. **Valid redirect URI:** send an authorization request with a registered callback, log in and approve consent (if required); confirm `Location` points strictly to that callback with `code` and the matching `state`. Verify the client accepts only responses matching the issued `state`.
2. **Invalid redirect URI:** change `https` to `http`, append `/`, or alter the domain. Confirm the Authorization Server rejects it and **does not redirect** to the unregistered target.
3. **Authorization code binding:** attempt to exchange an authorization code with a mismatched `redirect_uri` or `code_verifier`; the token exchange must fail. An authorization code must not be reusable after a successful exchange.
4. **Issuer/metadata consistency:** verify that `issuer` in metadata, `iss` in the ID Token, and `issuer-uri` on client and resource server are identical; a token with a spoofed `iss` must be rejected even if the signature appears valid in a test setup.
5. **Keys and token validation:** verify `jwks_uri` is reachable, JWTs signed with the corresponding key validate, and expired tokens or wrong `aud` are rejected per policy.
6. **Reverse proxy:** test through the real public HTTPS hostname, not just `localhost`; confirm issuer, endpoint URLs, and client redirect URIs do not leak internal hosts/schemes.

### 7.3. Common Symptoms

| Symptom | Causes to check | Remediation |
|---|---|---|
| Invalid `redirect_uri` | Mismatched scheme, port, host, trailing `/`, `registrationId`, or unregistered callback | Compare exact literal URIs in the authorization request, `RegisteredClient`, and client `redirect-uri` |
| Client returns to callback but login fails | Lost `state`/session, callback not handled by filter, expired code, invalid PKCE, or token exchange failure | Preserve cookie/session properly, inspect OAuth2 Login callback, and debug code/token exchange |
| `/.well-known/openid-configuration` returns 404 | OIDC not enabled, wrong proxy/path routing, or incomplete protocol config | Enable OIDC configurer; check actual public paths and security filter chain |
| Metadata shows `http://localhost:9000` | Issuer derived from internal request or misconfigured proxy | Set `AuthorizationServerSettings.issuer(...)` to the public HTTPS URL; verify proxy config |
| Resource Server reports `Invalid issuer` | `iss` claim differs from `issuer-uri`, including trailing `/` or path | Compare exact issuer strings across token, metadata, and configuration |
| JWT signature verification fails | Wrong `jwks_uri`, missing JWKSource, key/`kid` mismatch, or unsynchronized key rotation | Inspect public JWKS, key rotation, and metadata for the right issuer |
| Discovery works but OIDC login fails | Client not registered, missing `openid` scope, invalid redirect URI/PKCE, or missing user authentication | Inspect full RegisteredClient, OIDC enablement, and Authorization Code Flow chain |

## 8. Operational Rules to Keep Consistent

- Use a **stable public HTTPS issuer** per environment, publishing the exact same value in metadata and tokens; change it only with a migration plan.
- Register **specific, exact redirect URIs** per client and environment; never use wildcards or open callbacks; enforce PKCE for Authorization Code Flow.
- Publish standard metadata so integrators can discover endpoints; protect private signing keys while keeping public metadata/JWKS readable by design.
- Monitor health/availability of discovery, token endpoint, and JWKS; ensure key rotation does not break verification for clients holding valid tokens.
- Test through the gateway/proxy and real hostname, including negative cases rejecting invalid redirects and JWTs with wrong issuer/audience.
- In monitoring/logs, log client ID, error codes, and endpoints; avoid logging raw authorization codes, client secrets, access tokens, refresh tokens, ID Tokens, or `code_verifier`.

**Self-Check Questions:**

1. Why cannot `https://app.example.vn/callback/` arbitrarily substitute for a registered `https://app.example.vn/callback`?
2. If a JWT has a valid signature yet `iss` differs from the issuer trusted by the Resource Server, what must the API do?
3. How do a discovery document and a JWKS differ?
4. Why is explicit issuer configuration important when an Authorization Server sits behind a reverse proxy?
5. In a Spring Security client, what configuration on the Authorization Server must the URI generated by `{baseUrl}/login/oauth2/code/{registrationId}` correspond to?

## References

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), especially sections on the redirection endpoint and authorization code.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700), especially exact redirect URI matching, PKCE, and preventing open redirects.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414).
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html) and [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html).
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html) and [Core Model/Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html).
- [Spring Security — OAuth 2.0 Client Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html) and [OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
