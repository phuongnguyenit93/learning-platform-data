# Enabling OpenID Connect and Configuring OIDC Endpoints

> **Chapter: Server Configuration.** In the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, we learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in a Spring Boot application. This lesson focuses on **enabling OpenID Connect (OIDC)** on an Authorization Server supporting OAuth 2.0, understanding OIDC endpoints, configuring them, and verifying an end-to-end login flow.

## 1. What Does Enabling OIDC Change?

**OAuth 2.0** primarily defines how a client is granted authorization to access resources; it does not by itself provide a standard protocol for the client to verify who the logged-in user is. **OpenID Connect 1.0** builds an identity authentication layer on top of OAuth 2.0: requests include the `openid` scope, the Authorization Server becomes an **OpenID Provider (OP)**, the token response can include an **ID Token**, and the client, also called the **Relying Party (RP)**, must validate the ID Token according to OIDC rules.

Example: the application `https://app.example.vn` wants to authenticate users through the server `https://login.example.vn`. The OAuth 2.0 Authorization Code Flow lets the application receive an authorization code and exchange it for tokens; OIDC adds a standardized representation of authentication information via an ID Token and services such as discovery, UserInfo, and RP-Initiated Logout.

| Component | Role | Example in the system |
|---|---|---|
| Authorization Server / OpenID Provider | Authenticates users, handles consent, issues codes/tokens, publishes metadata and public keys | `https://login.example.vn` |
| OAuth2/OIDC Client / Relying Party | Redirects for login, receives authorization code, exchanges tokens, verifies ID Token | `https://app.example.vn` |
| Resource Server | Receives access token, validates token, and enforces API authorization | `https://api.example.vn` |
| Issuer Identifier | OP/AS identifier; the `iss` value in the ID Token must match exactly | `https://login.example.vn` |
| Redirect URI | Registered client callback where the browser returns with the code | `https://app.example.vn/login/oauth2/code/portal` |

**Distinguishing three token/value types:**

- **ID Token:** A JWT containing user authentication and identity information intended for the client, including `iss`, `sub`, `aud`, `exp`, and related claims. Never use an ID Token in place of an access token to call APIs.
- **Access Token:** A credential for calling protected resources, which may be a JWT or an opaque token; the Resource Server must validate it and enforce authorization properly.
- **Authorization Code:** A single-use, short-lived code exchanged by the client at the token endpoint; it is neither an ID Token nor an access token.

Enabling OIDC does **not** automatically create a user store, secure login mechanism, `RegisteredClient`, signing keys, persistent consent service, or multi-tenant deployment. Those components must still be configured separately.

## 2. Map of Endpoints When OIDC Is Enabled

In Spring Authorization Server's default configuration, the following paths have distinct roles:

| Endpoint (default path) | Primary method | Function | Configuration notes |
|---|---|---|---|
| `/.well-known/openid-configuration` | GET | **OIDC Provider Configuration**: metadata for issuer, endpoints, supported algorithms/capabilities | Available only when OIDC is enabled |
| `/userinfo` | GET/POST per protocol/implementation | **OIDC UserInfo**: returns claims about the user for requests with an appropriate access token | Requires Bearer access token authentication; actual claims depend on scopes/policy/mapper |
| `/connect/logout` | GET/POST per protocol/implementation | **RP-Initiated Logout**: RP requests session termination at the OP | Requires validating `id_token_hint` and return URI against policy |
| `/connect/register` | POST and supported management operations | **Dynamic Client Registration**: registers clients via API | **Disabled by default**; enable only when needed and with strict permission controls |
| `/oauth2/authorize` | GET | OAuth 2.0 Authorization Endpoint; accepts `scope=openid` for OIDC flows | Part of OAuth 2.0, still used when OIDC is enabled |
| `/oauth2/token` | POST | OAuth 2.0 Token Endpoint; exchanges code for tokens, can include `id_token` | Not a new OIDC-only endpoint |
| `/oauth2/jwks` | GET | Publishes JWK Set of **public keys** for verifying JWT/ID Token signatures | Default path, requires `JWKSource<SecurityContext>` |
| `/.well-known/oauth-authorization-server` | GET | OAuth 2.0 Authorization Server Metadata per RFC 8414 | **Different** from OIDC Discovery; does not replace full OIDC metadata |

**Remember:** `/oauth2/authorize` and `/oauth2/token` remain shared OAuth 2.0 endpoints. An OIDC request typically uses `scope=openid` and Authorization Code + PKCE; the ID Token is issued at the token endpoint after the client exchanges a valid code.

The path list above reflects **defaults** in Spring Authorization Server 1.x. `AuthorizationServerSettings` allows configuring several paths; always inspect the metadata returned by the **running instance** rather than assuming URIs are immutable.

### 2.1. Which Endpoints Are Enabled Out of the Box?

With the default OIDC configuration:

- Provider Configuration, UserInfo, and RP-Initiated Logout are activated within Spring Authorization Server's supported capabilities.
- **OIDC Dynamic Client Registration** is not enabled automatically. This is a sensitive administrative endpoint requiring explicit authorization decisions and registration policies.
- OAuth2 Authorization, Token, JWK Set, and OAuth AS Metadata remain provided by the core authorization server configuration; the JWKS endpoint depends on having a JWK source.
- For UserInfo to accept Bearer access tokens, the Authorization Server filter chain must support Bearer JWT/OAuth2 Resource Server processing as documented for your version.

Do not open all paths with `permitAll()` just because discovery is public. Provider Configuration and JWKS are designed to be readable; UserInfo requires a valid access token, and the remaining endpoints must follow their respective authentication/authorization mechanisms.

## 3. Standard OIDC Login Flow and Endpoint Placement

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as OIDC Client (RP)
    participant Browser as Browser
    participant OP as Spring Authorization Server (OP)
    participant API as Resource Server

    RP->>OP: GET /.well-known/openid-configuration
    OP-->>RP: issuer, authorization_endpoint, token_endpoint, jwks_uri, ...
    Browser->>RP: Initiate login
    RP-->>Browser: Redirect to /oauth2/authorize<br/>scope=openid profile, state, nonce, PKCE
    Browser->>OP: Authorization request
    OP->>Browser: Authenticate and consent if needed
    OP-->>Browser: 302 to redirect_uri?code=...&state=...
    Browser->>RP: Authorization response
    RP->>RP: Verify state
    RP->>OP: POST /oauth2/token<br/>code, redirect_uri, code_verifier, client authentication
    OP-->>RP: access_token, id_token (and other tokens if eligible)
    RP->>OP: GET jwks_uri when needed
    OP-->>RP: Public JWK Set
    RP->>RP: Verify ID Token: signature, iss, aud, exp, nonce...
    RP->>OP: GET /userinfo with access_token (optional)
    OP-->>RP: UserInfo claims, consistent sub
    RP->>API: Authorization: Bearer access_token
    API-->>RP: Resource if token/permissions are valid
~~~

Example authorization request (split across lines for readability; the actual URL must be a valid single URL-encoded line):

~~~http
GET /oauth2/authorize?response_type=code
    &client_id=portal-web
    &redirect_uri=https%3A%2F%2Fapp.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal
    &scope=openid%20profile%20email
    &state=STATE_RANDOM_VALUE
    &nonce=NONCE_RANDOM_VALUE
    &code_challenge=PKCE_S256_CHALLENGE
    &code_challenge_method=S256
Host: login.example.vn
~~~

`state`, `nonce`, and PKCE values must be generated randomly/algorithmically for **each transaction**; the uppercase strings are only placeholders. Upon receiving the callback, the client verifies `state`, then sends the corresponding secret `code_verifier` to the token endpoint.

Example OIDC token response in the Authorization Code flow (abbreviated):

~~~json
{
  "access_token": "ACCESS_TOKEN_REDACTED",
  "token_type": "Bearer",
  "expires_in": 300,
  "id_token": "SIGNED_ID_TOKEN_REDACTED",
  "scope": "openid profile email"
}
~~~

Actual responses depend on grant, client registration, scopes, and token policy. Never log raw access tokens, ID Tokens, authorization codes, or `code_verifier`.

## 4. Enabling OIDC in Spring Boot with SecurityFilterChain

### 4.1. Dependencies and Prerequisites

In a Spring Boot application using a compatible Spring Authorization Server, declare the relevant starters (depending on Boot version, dependencies managed via BOM):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-authorization-server'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

This is a Gradle Groovy example illustrating required capabilities; align Boot, Spring Security, and Spring Authorization Server versions using your project's dependency management. To run OIDC in practice, you need:

1. A `RegisteredClientRepository` managing clients, `redirect_uri`, scopes, and authentication methods.
2. A user login mechanism (for example form login and `UserDetailsService`, or a custom mechanism).
3. A `JWKSource<SecurityContext>` to sign JWTs/ID Tokens and publish public JWKS; a `JwtDecoder` for components that need to decode/verify JWTs.
4. An `AuthorizationServerSettings` containing the accurate issuer; services persisting authorizations/consents as required for production.
5. HTTPS on public endpoints, persistent secrets/signing keys, and proper access controls in production.

### 4.2. Filter Chain Dedicated to the Authorization Server

The example below uses the modern `OAuth2AuthorizationServerConfigurer` API in Spring Authorization Server 1.x and Spring Security 6.x:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.oidc(Customizer.withDefaults())) // ENABLE OIDC
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .exceptionHandling(exceptions ->
                exceptions.defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)))
            .oauth2ResourceServer(resourceServer ->
                resourceServer.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Types used in this example belong to packages `org.springframework.security.config.annotation.web.*`, `org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.*`, `org.springframework.security.web.authentication.*`, and `org.springframework.http.MediaType` (ensure IDE imports match your actual dependencies).

**Meaning of each configuration:**

- `@Order(1)` and `securityMatcher(authorizationServer.getEndpointsMatcher())`: applies the first filter chain only to the Authorization Server endpoint set, preventing the regular login filter chain from intercepting and blocking them improperly.
- `.with(authorizationServer, server -> server.oidc(Customizer.withDefaults()))`: enables OIDC components. Without this call, `/.well-known/openid-configuration` may return 404 and OIDC clients cannot discover metadata.
- `.oauth2ResourceServer(resourceServer -> resourceServer.jwt(...))`: sets up Bearer JWT handling for endpoints such as UserInfo. This does **not** mean every Bearer token is allowed to access every resource.
- `.exceptionHandling(...LoginUrlAuthenticationEntryPoint...)`: when a browser requires interactive login, redirects to `/login`; API/token requests should receive appropriate error responses.
- The second filter chain configures user authentication into the OP. You must also supply a real `UserDetailsService` or authentication provider; two chains alone do not create users.

The configuration above is a **security skeleton**; the program still needs the beans in sections 5 and 6. Spring Authorization Server provides some in-memory defaults; production typically requires durable persistence for authorizations and consents. Do not copy sample configuration directly to production without session, CSRF, audit, persistence, and key management strategies.

## 5. Configuring Issuer, Signing Keys, and JwtDecoder

### 5.1. Fixing the Issuer Identifier

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings(
        @Value("${app.authorization-server.issuer}") String issuer) {
    return AuthorizationServerSettings.builder()
            .issuer(issuer)
            .build();
}
~~~

Example runtime configuration:

~~~yaml
# application.yml
app:
  authorization-server:
    issuer: ${AUTH_SERVER_ISSUER}
~~~

~~~text
AUTH_SERVER_ISSUER=https://login.example.vn
~~~

The line `AUTH_SERVER_ISSUER=...` only illustrates the environment value, **not** content to place directly in YAML. `issuer` is the **public, stable** identifier of the OP, not a secret. In an ID Token, the `iss` claim must **match exactly** the metadata `issuer` and the issuer trusted by the RP. Do not allow the issuer to be inferred as `http://localhost:9000` when the server runs behind a reverse proxy.

If there is a path prefix or multi-tenant issuer, verify the exact metadata discovery URL per OIDC Discovery and the actual URL published by the library. Never manually edit or trim slashes when comparing issuers.

### 5.2. JWKSource and JwtDecoder

Spring Authorization Server uses `JWKSource<SecurityContext>` when issuing signed self-contained tokens and publishes the **public JWK Set** via `/oauth2/jwks`. JWT/ID Token signing keys must be shared consistently across server instances and persisted across restarts.

Example **for local development/testing only** (generating a new key in memory):

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() throws GeneralSecurityException {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
    generator.initialize(2048);
    KeyPair pair = generator.generateKeyPair();

    RSAKey rsaJwk = new RSAKey.Builder((RSAPublicKey) pair.getPublic())
            .privateKey((RSAPrivateKey) pair.getPrivate())
            .keyID(UUID.randomUUID().toString())
            .build();

    JWKSet jwkSet = new JWKSet(rsaJwk);
    return (selector, context) -> selector.select(jwkSet);
}

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

`RSAKey`, `JWKSet`, `JWKSource`, and `SecurityContext` belong to Nimbus JOSE/JWT; `JwtDecoder` belongs to Spring Security OAuth2 JWT. Import `KeyPairGenerator`, `RSAPublicKey`, `RSAPrivateKey`, `GeneralSecurityException`, and `UUID` from standard Java. `jwtDecoder` in the example creates a decoder backed by the active key source; it is also used by OIDC components when JWT verification is needed.

**Operational warning:** If every restart or every pod generates a random RSA key as in the example, tokens signed by one instance may fail verification when JWKS or instances change. In production, **do not use** this approach. Load private keys from a secret store, keystore/HSM/KMS according to policy and configure a stable key/JWKS source; protect private keys and publish only public keys; design `kid` and key rotation so active tokens do not abruptly fail verification.

## 6. Registering a Valid OIDC Client

When a client uses Authorization Code + OIDC, in addition to `redirect_uri` and grant types, it needs the `openid` scope. If redirecting after logout is desired, register `post_logout_redirect_uri` separately.

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder passwordEncoder,
        @Value("${PORTAL_CLIENT_SECRET}") String clientSecret) {

    RegisteredClient portal = RegisteredClient.withId("portal-registration")
            .clientId("portal-web")
            .clientSecret(passwordEncoder.encode(clientSecret))
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri(
                    "https://app.example.vn/login/oauth2/code/portal")
            .postLogoutRedirectUri("https://app.example.vn/logged-out")
            .scope(OidcScopes.OPENID)
            .scope(OidcScopes.PROFILE)
            .scope(OidcScopes.EMAIL)
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .build();

    return new InMemoryRegisteredClientRepository(portal);
}

@Bean
PasswordEncoder passwordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}
~~~

This snippet illustrates a **confidential web client**. Supply `PORTAL_CLIENT_SECRET` via a protected secret store/environment variable; the Authorization Server stores its **hash** using `PasswordEncoder`. Never hard-code plaintext secrets or use `{noop}` in production. `InMemoryRegisteredClientRepository` should only be used for examples/local runs; real systems need a persistent datastore and procedures for provisioning clients and rotating secrets.

Common pitfalls:

1. `scope(OidcScopes.OPENID)` allows the client to request OIDC. If an authorization request omits `openid`, it is not an OIDC authentication request and will not automatically yield an ID Token.
2. `redirectUri(...)` is the callback receiving the **authorization code**; `postLogoutRedirectUri(...)` is the destination **after logout**. They are validated separately and are not interchangeable.
3. `requireProofKey(true)` enforces PKCE on the client. Even confidential clients should use PKCE to reduce the risk of authorization code interception and misuse.
4. `requireAuthorizationConsent(true)` causes the OP to require consent per policy; it does not mean every claim under `profile` and `email` will automatically appear in UserInfo.
5. For a **public client** (SPA/native app), the client cannot hold a `client_secret`. Register an appropriate authentication method, enforce PKCE, and restrict redirect URIs to the application type. Do not apply the confidential client example above as-is to an SPA.

## 7. Provider Configuration: Publishing Metadata for Client Discovery

Once OIDC is enabled, the OP publishes its document via:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: login.example.vn
Accept: application/json
~~~

An **illustrative** response structure (actual metadata varies by version and configuration):

~~~json
{
  "issuer": "https://login.example.vn",
  "authorization_endpoint": "https://login.example.vn/oauth2/authorize",
  "token_endpoint": "https://login.example.vn/oauth2/token",
  "jwks_uri": "https://login.example.vn/oauth2/jwks",
  "userinfo_endpoint": "https://login.example.vn/userinfo",
  "end_session_endpoint": "https://login.example.vn/connect/logout",
  "response_types_supported": ["code"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"]
}
~~~

**Note:** Do not hand-author this JSON as a static file to replace the built-in endpoint without an explicit design. Spring Authorization Server generates metadata dynamically from configuration; whenever endpoints/issuer/algorithms change, inspect the actual document published by the server. Some fields shown in the illustrative JSON may be omitted if the server does not support the corresponding feature.

Meaning of key fields:

| Field | Purpose |
|---|---|
| `issuer` | Value by which the OP identifies itself; RP matches against trusted issuer and ID Token `iss` |
| `authorization_endpoint` | URL to direct the browser to perform the authorization request |
| `token_endpoint` | URL to exchange codes/tokens over the back-channel |
| `jwks_uri` | URL of the **public keys** set used to verify signatures |
| `userinfo_endpoint` | URL to retrieve user info using a Bearer access token |
| `end_session_endpoint` | URL the RP can use to request OP logout |
| `id_token_signing_alg_values_supported` | ID Token signing algorithms declared supported by the OP |

Metadata may be publicly readable; that does **not** allow clients to trust any user-supplied issuer URL. The RP needs a trusted issuer allowlist or a controlled issuer verification workflow; fetching metadata from arbitrary URLs introduces SSRF risks or trusting unintended providers. After fetching, verify `issuer` and validate the ID Token per OIDC Core.

**RFC 8414** also defines OAuth Authorization Server Metadata at `/.well-known/oauth-authorization-server`. The two discovery documents are similar yet serve different specification suites; OIDC Clients typically use `/.well-known/openid-configuration`.

## 8. UserInfo Endpoint: Retrieving Claims After Authentication

UserInfo is a resource protected by an **access token**, not a public endpoint like Provider Configuration. Example request:

~~~http
GET /userinfo HTTP/1.1
Host: login.example.vn
Authorization: Bearer ACCESS_TOKEN_REDACTED
Accept: application/json
~~~

Example response when allowed by user, scopes, and policy:

~~~json
{
  "sub": "user-123",
  "name": "Nguyen Van A",
  "preferred_username": "vana",
  "email": "vana@example.vn",
  "email_verified": true
}
~~~

This is **illustrative data**, not a guarantee that Spring Authorization Server always returns every claim above. By default, UserInfo may only include basic claims or claims mapped from authorization/ID Token data; fetching user attributes from a database/identity provider requires configuring a corresponding mapping mechanism.

### 8.1. Required Checks

- UserInfo requests must be authenticated with a valid access token, typically Bearer authentication. Tokens intended solely for another Resource Server should not automatically grant access to read UserInfo.
- The `sub` returned by UserInfo **must match** the `sub` in the ID Token that the client already verified. If they differ, the RP **must not** use that response to bind identity.
- The `openid` scope is the foundation of an OIDC request. `profile`, `email`, and other scopes/claims only request the corresponding permissions and do not guarantee that data exists or is permitted for release.
- Never allow clients to pass `sub` as a query parameter to read another user's UserInfo. Subject identity must come from the validated token and authorization context.
- Never log full Bearer tokens or UserInfo payloads containing unnecessary personal information.

### 8.2. Customizing Claims in Spring Authorization Server

Spring Authorization Server supports customizing UserInfo claim mapping via `oidc().userInfoEndpoint(...)` and the corresponding mapper for your version. When building a mapper:

1. Obtain the subject identity from the **validated authentication/token/authorization**, never from client-supplied parameters.
2. Query from the user store only fields allowed by the token, scopes, and consent policy.
3. Always keep `sub` consistent and identical to the ID Token.
4. Test expired tokens, missing scopes, locked users, revoked grants, and updated user attributes.

Do not return a raw JPA entity (which might contain password hashes, internal emails, or system roles) as UserInfo JSON. Create explicit DTOs/claims with dedicated tests.

## 9. RP-Initiated Logout: Terminating Sessions and Safe Redirects

OIDC RP-Initiated Logout allows a client to ask the OP to end the login session at the OP. With Spring Authorization Server's default paths, an RP can navigate the browser to `end_session_endpoint` when published in metadata:

~~~http
GET /connect/logout?id_token_hint=ID_TOKEN_REDACTED
    &post_logout_redirect_uri=https%3A%2F%2Fapp.example.vn%2Flogged-out
    &state=LOGOUT_STATE_RANDOM HTTP/1.1
Host: login.example.vn
~~~

Query lines are wrapped for readability; the actual URL must be on a single line. `id_token_hint` helps the OP identify the relevant client/session; `post_logout_redirect_uri` must match a registered value and the OP's logout policy. `state` lets the client correlate the return response with the logout request.

**Important limitations:**

- Logging out of the OP does not automatically expire every other client's session or revoke all access/refresh tokens. Perform front-channel/back-channel logout or token revocation only if your protocols, libraries, and actual deployment support them.
- The client must also properly clear/close its local session, even when no post-logout redirect occurs.
- Never accept arbitrary return URIs to prevent open redirects. `post_logout_redirect_uri` is not the authorization request's `redirect_uri`.
- Never place full ID Tokens, client secrets, or access tokens in logs, analytics URLs, referrers, or tickets; if `id_token_hint` appears in URLs, enforce strict logging redaction and sensitive data handling.

## 10. Customizing OIDC Endpoints and Dynamic Client Registration

### 10.1. Changing UserInfo/Logout Paths via AuthorizationServerSettings

When specific reverse proxy, API architecture, or versioning needs arise, you can change certain default endpoints:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings(
        @Value("${app.authorization-server.issuer}") String issuer) {
    return AuthorizationServerSettings.builder()
            .issuer(issuer)
            .oidcUserInfoEndpoint("/oidc/userinfo")
            .oidcLogoutEndpoint("/oidc/logout")
            .build();
}
~~~

This snippet **replaces** the `AuthorizationServerSettings` bean in section 5.1; **do not define two beans of this type simultaneously** when configuration requires only one settings instance. Update proxy/security routes and verify metadata returns the new `userinfo_endpoint` and `end_session_endpoint`. If clients hard-coded old endpoints, provide a compatibility/migration plan; new clients should read metadata.

Customizing **behavior** differs from customizing **paths**. Customizing UserInfo/Logout behavior uses `OidcConfigurer` hooks in the filter chain, for example:

~~~java
.with(authorizationServer, server ->
    server.oidc(oidc -> oidc
        .userInfoEndpoint(Customizer.withDefaults())
        .logoutEndpoint(Customizer.withDefaults())
        .providerConfigurationEndpoint(Customizer.withDefaults())))
~~~

This shows where OIDC endpoints are configured in the DSL; `Customizer.withDefaults()` **retains default behavior** without adding custom mappers/handlers. When you genuinely need custom claims or logout responses, supply customizers matching your library API and version, backed by security tests. Never create a custom `/userinfo` controller without Bearer token validation to replace the standard endpoint.

### 10.2. Dynamic Client Registration: Enable Only for Operational Needs

OIDC Dynamic Client Registration lets clients register their own metadata via an API. Spring Authorization Server **does not enable this endpoint by default**. In environments requiring dynamic client provisioning, you can explicitly enable it:

~~~java
.with(authorizationServer, server ->
    server.oidc(oidc ->
        oidc.clientRegistrationEndpoint(Customizer.withDefaults())))
~~~

This snippet **replaces** `server.oidc(Customizer.withDefaults())` in section 4.2 while keeping the rest of the filter chain. Before enabling, establish registration authorization policies (initial access tokens/associated authorities), validation of client metadata, redirect URIs, grant types, authentication methods, quotas/rate limits, and audit logging. Avoid letting arbitrary Internet users register confidential clients or obtain permissions beyond policy.

The Dynamic Client Registration endpoint is not end-user sign-up, nor does it replace a pre-designed client repository and approval process used in many internal systems.

## 11. Post-Configuration Verification

### 11.1. Verifying Discovery and Public JWKS

Once the service is running on its public hostname (locally, substitute the environment's host/port), check:

~~~bash
curl -fsS https://login.example.vn/.well-known/openid-configuration \
  | jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri, userinfo_endpoint, end_session_endpoint}'

curl -fsS https://login.example.vn/oauth2/jwks \
  | jq '{key_count: (.keys | length), kids: [.keys[].kid]}'
~~~

Expected: Provider Configuration returns JSON with `issuer` matching configuration, along with accurate `userinfo_endpoint` and `end_session_endpoint`; public JWKS contains valid verification keys and **does not** contain private key parameters. If you customized `jwkSetEndpoint`, obtain the URL from `jwks_uri` in metadata rather than assuming `/oauth2/jwks`.

You can also inspect OAuth AS Metadata:

~~~bash
curl -fsS https://login.example.vn/.well-known/oauth-authorization-server \
  | jq '{issuer, authorization_endpoint, token_endpoint, jwks_uri}'
~~~

This command only verifies metadata publication; it **does not prove** login, UserInfo, or logout flows work end-to-end.

### 11.2. End-to-End Flow Testing

| Scenario | Expected result |
|---|---|
| `GET /.well-known/openid-configuration` when OIDC is enabled | 200 JSON, accurate issuer, endpoints properly declared |
| `scope=openid` + valid Authorization Code + PKCE | Returns authorization code; exchange at token endpoint yields validly signed ID Token |
| Authorization request **without** `openid` | Not treated as OIDC authentication; no ID Token expected |
| Callback differs from registered URI | Authorization request rejected; never redirect code to unknown URI |
| Invalid `state` or PKCE `code_verifier` | Client or token endpoint rejects the transaction |
| ID Token with wrong `iss`/`aud` or invalid signature/nonce | RP rejects the ID Token |
| `GET /userinfo` without Bearer token | Rejected (typically 401); returns no claims |
| `GET /userinfo` with valid token and appropriate permissions | Policy-compliant JSON claims; `sub` matches ID Token |
| Unregistered `post_logout_redirect_uri` | Logout must not redirect to untrusted URI |
| Dynamic Client Registration when disabled | Endpoint cannot be used as a public client provisioning service |
| Issuer change or lost JWKS after proxy/rolling restart | Validation/discovery errors detected; tokens with wrong issuer or signature rejected |

Login/consent testing must be executed via a browser or equivalent OAuth2 Client test; plain `curl` requests to `/oauth2/authorize` do not fully simulate form login, session cookies, and CSRF. Tokens, secrets, and codes in test reports must use dummy or redacted values.

### 11.3. Common Errors

| Symptom | Likely cause | How to inspect/fix |
|---|---|---|
| `/.well-known/openid-configuration` returns 404 | `.oidc(...)` not called, request hits wrong filter chain, or proxy routing wrong | Check OIDC configurer, `securityMatcher`, and public routes |
| Provider Configuration contains `http://localhost` | Issuer inferred from internal/reverse-proxy request | Set explicit public HTTPS issuer via `AuthorizationServerSettings`; configure trusted proxies |
| OIDC Client receives no `id_token` | Missing `openid` scope, wrong grant/RegisteredClient, or invalid token flow | Verify `openid` scope was granted; inspect token exchange and signing setup |
| `/userinfo` returns 401 | Missing Bearer token, filter chain lacks JWT support, or invalid token | Check Authorization header, JWT decoder/keys, and authentication entrypoint |
| `/userinfo` omits `email` | Claims not mapped, missing scope/consent, or user record lacks data | Customize UserInfo mapper per policy; verify ID Token/UserInfo `sub` |
| Token reports `Invalid issuer` | JWT `iss` differs from client's trusted issuer (including `/` or path) | Compare exact issuer across metadata, token, and RP config |
| `/connect/logout` does not return to app | Unregistered `post_logout_redirect_uri`, missing hint/valid session, wrong proxy URL | Check RegisteredClient, metadata, logout request, and redacted logs |
| JWKS changes after restart breaking old tokens | Random RSA key generated at startup or inconsistent keys across pods | Use persistent key source; publish all required public keys during rotation |
| `/connect/register` unavailable | Dynamic Client Registration disabled or unauthorized | Enable only when needed; configure authenticated/authorized registration |

## 12. Security and Production Operations Principles

- **Do not confuse OIDC with OAuth authorization:** OIDC authenticates users at the RP using an ID Token; Resource Servers validate access tokens by issuer, signature, expiration, audience, scope, and dedicated policies. An ID Token is not an API credential.
- **Public HTTPS and stable issuer:** metadata/redirects/end-session must use exact public scheme, hostname, and paths; reverse proxies must trust forwarded headers only from controlled infrastructure.
- **PKCE + state + nonce:** use Authorization Code Flow with PKCE; RP binds responses with `state` and verifies `nonce` in the ID Token when sent; avoid legacy flows prone to front-channel token leakage.
- **Exact Redirect URIs:** both post-authorization callbacks and post-logout URIs must be registered and strictly validated; avoid wildcards or open redirects.
- **Signing keys/JWKS:** publish only public keys while keeping private keys in a secret store/HSM/keystore; use `kid` and rotation processes so valid active tokens remain verifiable.
- **Scope-bound UserInfo:** release only claims permitted by grants/scopes/consent; never expose password hashes, secrets, administrative fields, or another user's data.
- **Controlled dynamic registration:** keep disabled if there is no use case; never allow unrestricted client registration; maintain audit logs.
- **Monitoring and testing:** monitor availability/latency of discovery, authorization, token, UserInfo, logout, and JWKS; alert on spikes in issuer/JWT validation errors; keep tokens and secrets out of logs.
- **Session/logout:** manage secure cookies, session fixation protection, `SameSite`, CSRF, and appropriate timeouts; distinguish OP session logout, RP session logout, and access/refresh token validity.

### Self-Check Questions

1. What does enabling `server.oidc(Customizer.withDefaults())` change compared to an OAuth 2.0 Authorization Server without OIDC enabled?
2. Why should a Resource Server never accept an ID Token as an access token?
3. Why does UserInfo require a Bearer access token, while Discovery and public JWKS typically allow public GET requests?
4. How do `redirectUri(...)` and `postLogoutRedirectUri(...)` differ?
5. Why is a stable signing key needed across pods and restarts?
6. Is Dynamic Client Registration enabled by default, and what security controls are needed before enabling it?
7. When changing the `/userinfo` path via `AuthorizationServerSettings`, what must be verified across metadata, proxy, and clients?

## References

- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): authorization server configurer and endpoint settings.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OAuth 2.0 and OIDC endpoint configurers.
- [Spring Authorization Server — Core Model/Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, repositories, and token services.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, UserInfo, validation, and authentication flows.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration and metadata.
- [OpenID Connect RP-Initiated Logout 1.0](https://openid.net/specs/openid-connect-rpinitiated-1_0.html): logout requests and `post_logout_redirect_uri`.
- [OpenID Connect Dynamic Client Registration 1.0](https://openid.net/specs/openid-connect-registration-1_0.html): dynamic client registration rules.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): PKCE, redirect URI, authorization flow protection.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): OAuth 2.0 metadata.
