# Enabling OIDC and Handling the openid Scope

> **Chapter: OIDC Core and ID Token.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, covering the design, configuration, security, testing, and operations of an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in Spring Boot. It focuses on enabling OpenID Connect 1.0 (OIDC), the meaning of the required `openid` scope, registering scopes for a client, issuing ID Tokens, and testing the OIDC Authorization Code flow.

## 1. OAuth 2.0 and OpenID Connect Solve Two Different Problems

OAuth 2.0 is an authorization framework. It allows a client to obtain an access token to access resources within granted scopes. OAuth 2.0 by itself does not define a standard, complete protocol for a client to verify the identity of a signed-in user.

OpenID Connect 1.0 (OIDC) builds on top of OAuth 2.0 and adds a user authentication layer. When a client sends a valid OIDC Authentication Request, the OpenID Provider (OP, often also the OAuth Authorization Server) can issue an **ID Token** — a JWT signed by the OP containing the subject and information about the authentication result.

| Aspect | OAuth 2.0 | OpenID Connect |
|---|---|---|
| Goal | Which resources is the client allowed to access? | Who is the authenticated user and what is the sign-in result? |
| Characteristic token | Access token | ID Token, usually alongside an access token |
| Typical audience | Resource Server/API | Client / Relying Party (RP) |
| Scope | Scopes and authorization for APIs | Authentication and claims per OIDC |
| Additional protocols | Authorization, token, introspection, revocation… | Provider Configuration/Discovery, UserInfo, Logout… |
| Request indicator | OAuth authorization parameters | Required `openid` scope in the Authentication Request |

Running example:

- **OpenID Provider / Authorization Server:** `https://login.example.vn`.
- **Relying Party / OAuth client:** `portal-web`.
- **End user:** `user-123`.
- **Resource Server:** `https://api.example.vn`.
- **API permission:** `orders.read`.
- **OIDC scopes:** `openid profile email`.

When a user signs in to `portal-web`, the client needs to verify the authentication result and obtain a stable user identifier. When calling the Orders API, the client needs an access token with the `orders.read` permission. Both goals can take place in the same Authorization Code Flow, yet **the ID Token and access token have different contracts, audiences, and consumers**.

### 1.1. Distinguishing the Roles

- **OpenID Provider (OP):** the server that performs OIDC authentication, issues ID Tokens, and exposes discovery/UserInfo as configured.
- **Relying Party (RP):** an OIDC application that relies on an OP to authenticate users.
- **OAuth Client:** an application requesting authorization and tokens. An RP is also an OAuth client.
- **Resource Server:** an API that receives access tokens and enforces authorization. A Resource Server does not use an ID Token in place of an access token.

Spring Authorization Server can act as both an OAuth Authorization Server and an OpenID Provider when the application enables OIDC and configures the required components.

## 2. Enabling OIDC in Spring Authorization Server

Spring Authorization Server supports OAuth 2.0 endpoints according to the Authorization Server configuration. **OpenID Connect 1.0 is disabled by default**. To enable OIDC, you must configure the OIDC configurer in the Authorization Server filter chain:

~~~java
.oidc(Customizer.withDefaults())
~~~

In Spring Authorization Server 1.5.x, enabling OIDC adds the following protocol endpoints:

| Endpoint | Default Path | Purpose |
|---|---|---|
| Provider Configuration | `/.well-known/openid-configuration` | Publishes metadata for RP discovery |
| UserInfo | `/userinfo` | Returns claims about the end user based on the access token and policy |
| Logout | `/connect/logout` | Handles OIDC logout requests |
| Client Registration | `/connect/register` | Dynamic Client Registration; disabled by default |

OAuth endpoints such as authorization, token, introspection, revocation, and JWK Set continue operating per the Authorization Server configuration. OIDC adds protocol endpoints; it does not replace the token endpoint or turn an access token into an ID Token.

### 2.1. SecurityFilterChain with OIDC Enabled

Configuration example with Spring Authorization Server 1.5.x and Spring Security 6.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Configuration(proxyBeanMethods = false)
class AuthorizationServerSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(
            HttpSecurity http) throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                    server.oidc(Customizer.withDefaults()))
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
    SecurityFilterChain applicationSecurityFilterChain(
            HttpSecurity http) throws Exception {

        http.authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

        return http.build();
    }
}
~~~

What this configuration does:

- `OAuth2AuthorizationServerConfigurer.authorizationServer()` creates the configurer for the AS endpoint set.
- `securityMatcher(authorizationServer.getEndpointsMatcher())` scopes the first chain to AS endpoints, including OIDC endpoints once enabled.
- `oidc(Customizer.withDefaults())` initializes OIDC support.
- `@Order(1)` ensures the Authorization Server chain is evaluated before the application chain.
- The entry point redirects browser requests requiring user authentication to `/login`. Non-HTML protocol requests are handled by the appropriate error flow.
- The second chain provides form login for illustration; production may use a different user authentication mechanism.

This is a filter-chain skeleton, not a complete production system. The application still needs a `RegisteredClientRepository`, `OAuth2AuthorizationService`, `AuthorizationServerSettings`, token generator, signing keys, and a user authentication mechanism.

### 2.2. Enabling OIDC Does Not Authenticate Users Automatically

The OIDC configurer adds protocol support and endpoints. It does not automatically create a user database, password login, MFA, sessions, or a consent workflow. The Authorization Code Flow still requires authenticating the resource owner via form login, an identity provider, or an integrated mechanism.

Consent is also a separate policy. If a client requests `profile`, `email`, or API scopes, the consent UI and policy must clearly show which permissions the user is granting. Enabling OIDC does not imply automatically consenting to all scopes.

## 3. The openid Scope Is the Required Marker of an OIDC Authentication Request

Per OpenID Connect Core 1.0, an OIDC Authentication Request **MUST** contain the scope value `openid`. The presence of this scope marks the request as an OIDC Authentication Request. Without `openid`, the request is processed as an OAuth 2.0 Authorization Request, even when the AS has OIDC enabled.

Example Authorization Code Request:

~~~http
GET /oauth2/authorize?response_type=code&client_id=portal-web&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&scope=openid%20profile%20email%20orders.read&state=STATE_RANDOM&nonce=NONCE_RANDOM&code_challenge=PKCE_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: login.example.vn
~~~

Key parameters:

- `openid`: requests the OIDC protocol and an authentication result via an ID Token.
- `profile` and `email`: request the corresponding OIDC claim groups, subject to available data, consent, and policy.
- `orders.read`: custom OAuth scope for the Orders API.
- `state`: binds the response to the authorization transaction initiated by the client.
- `nonce`: if sent by the client, the corresponding value must be returned in the ID Token and verified by the RP.
- `code_challenge` and `code_challenge_method=S256`: PKCE protecting the Authorization Code.

### 3.1. openid Is Neither a Role Nor an API Permission

Do not interpret `openid` as permission to read all user details or call all APIs. It marks the request as using OIDC. The scopes `profile`, `email`, `address`, and `phone` request their respective claim groups. API permissions are still governed by dedicated scopes like `orders.read`, audience, and authorization policies.

For example, a client may be granted `orders.read` without being granted `email`. Conversely, a client granted `profile` is not automatically permitted to read orders.

### 3.2. Registered Scopes and Requested Scopes Are Two Separate Steps

1. **Client registration:** the AS declares which scopes a client is allowed to request via `RegisteredClient.getScopes()`.
2. **Authorization Request:** the client sends a specific set of scopes in the `scope` parameter; the AS checks whether each scope is permitted by the registration and policy.

Registering `openid` in `RegisteredClient` **does not mean every request from that client is OIDC**. The actual request must contain `openid`. Conversely, if a client sends `openid` when its registration does not allow it, the AS must reject it during validation rather than expanding permissions automatically.

## 4. Common OIDC Scopes

OIDC Core defines standard scopes that request groups of claims. Commonly used scopes:

| Scope | Requested Information Group | Example Claims |
|---|---|---|
| `openid` | Marks an OIDC Authentication Request | `sub` in the ID Token |
| `profile` | Basic profile | `name`, `given_name`, `family_name`, `preferred_username`, `picture`, `locale` |
| `email` | Email information | `email`, `email_verified` |
| `address` | Postal address | `address` |
| `phone` | Phone number | `phone_number`, `phone_number_verified` |
| `offline_access` | Requests eligibility for a refresh token when OIDC conditions are met | Not a user profile claim |

Requesting a scope does not guarantee a claim will have a value. The OP only returns attributes that have data and are allowed by policy/consent. For example, if a user has not provided a `phone_number`, the `phone` scope cannot fabricate one.

### 4.1. Custom API Scopes

An application can define OAuth scopes such as:

- `orders.read` — read orders.
- `orders.write` — create/update orders.
- `billing.read` — read invoices.

These are not standard OIDC scopes. They are meant for Resource Server authorization. Do not use `openid` in place of API permissions or put business domain data into `profile`.

### 4.2. Requested Scopes Are Not Guaranteed to Be Granted Scopes

The AS evaluates client registration, user consent, authorization, and policy. The client must rely on the scopes actually granted in the authorization/token context, rather than assuming all requested scopes were accepted.

If a user denies certain permissions or policy restricts scopes, the client must handle the outcome and avoid calling APIs with ungranted permissions.

## 5. Registering an OIDC Client in Spring Authorization Server

Spring Authorization Server uses `RegisteredClient` to store the client ID, authentication methods, grant types, redirect URIs, scopes, and client settings.

Example confidential web client:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

RegisteredClient portalWeb = RegisteredClient
        .withId("registration-portal-web")
        .clientId("portal-web")
        .clientSecret(encodedClientSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(
                AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri(
                "https://portal.example.vn/login/oauth2/code/portal")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope(OidcScopes.EMAIL)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .requireAuthorizationConsent(true)
                .requireProofKey(true)
                .build())
        .build();
~~~

Notes:

- `OidcScopes.OPENID` is the constant for the `openid` scope; `PROFILE` and `EMAIL` are standard OIDC scopes.
- `encodedClientSecret` must be hashed with an appropriate `PasswordEncoder`; never store plaintext secrets in source code.
- `requireProofKey(true)` requires PKCE for the Authorization Code Flow.
- `requireAuthorizationConsent(true)` requires consent per client settings; the consent page must display scopes clearly.
- Redirect URIs must match the registration exactly and use HTTPS in production.
- Public clients must use an appropriate authentication method, typically `none`, along with PKCE; never embed a client secret in an SPA.

### 5.1. Do Not Use Client Credentials to Sign In End Users

Client Credentials represents the application/service itself, not a signed-in user. If the goal is service-to-service communication, use API scopes like `orders.read` and an OAuth access token. Do not use Client Credentials to simulate a user login or expect an ID Token carrying an end-user identity.

### 5.2. Persisting Client Registrations

Store `RegisteredClient` instances via `RegisteredClientRepository`. An in-memory repository suits demos/local development; production usually requires persistence such as JDBC. Registration scopes act as an allowlist. When updating scopes, consider prior consents, already-issued tokens, and migration policies; updating a registration does not automatically alter claims in still-valid JWTs.

## 6. Issuer, JWK, and JwtDecoder

An OIDC ID Token is a JWS-signed JWT. The RP needs to verify the signature using the public key of the right OP, typically fetched from the JWK Set published in discovery metadata.

### 6.1. Configuring a Stable Issuer

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://login.example.vn")
            .build();
}
~~~

The issuer must be consistent across Provider Configuration, the `iss` claim in ID Tokens, OAuth AS metadata, and RP configuration. Production requires a stable HTTPS issuer reflecting the public URL behind a reverse proxy. Do not let the issuer vary by internal hostname or untrusted caller headers.

### 6.2. JWKSource and Signing Key

The AS needs a signing key to sign ID Tokens. When the application registers a `JWKSource<SecurityContext>` bean, Spring Authorization Server can publish the JWK Set endpoint so RPs can retrieve public keys.

Example `JWKSource` structure (loading the key is the application's responsibility):

~~~java
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;

@Bean
JWKSource<SecurityContext> jwkSource() {
    RSAKey signingKey = loadSigningKeyFromSecureStorage();
    JWKSet jwkSet = new JWKSet(signingKey);
    return (selector, context) -> selector.select(jwkSet);
}
~~~

`loadSigningKeyFromSecureStorage()` is an illustrative helper implemented by the application, not a built-in API. The JWK Set publishes public keys; the private signing key must be protected in a keystore/HSM/secret manager. Do not generate a random new key on every production startup; plan key rollover and keep old public keys long enough to validate already-issued tokens.

### 6.3. JwtDecoder for UserInfo

Spring Authorization Server needs a `JwtDecoder` bean to process the UserInfo endpoint and certain OIDC endpoints such as Client Registration when enabled. You can use the helper:

~~~java
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.jwk.source.JWKSource;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

In the example above, `JWKSource` is imported from the Nimbus package `com.nimbusds.jose.jwk.source.JWKSource`. Registering a `JwtDecoder` does not enable OIDC by itself; you still must configure `oidc(Customizer.withDefaults())`. Conversely, enabling OIDC without the required signing key or decoder can prevent ID Token/UserInfo flows from working properly.

## 7. OIDC Authorization Code Flow

For the OIDC Authorization Code Flow, the typical sequence is:

~~~mermaid
sequenceDiagram
    autonumber
    participant RP as portal-web (Relying Party)
    participant OP as OpenID Provider / AS
    participant U as End User
    participant API as Resource Server

    RP->>OP: Authorization Request (scope=openid profile orders.read)
    OP->>U: Login and consent if needed
    U-->>OP: Authentication succeeds
    OP-->>RP: Redirect callback with code + state
    RP->>OP: POST /oauth2/token (code + client auth + PKCE verifier)
    OP-->>RP: access_token + id_token
    RP->>RP: Validate signature, iss, aud, exp, nonce if present
    RP->>API: API request with access_token and orders.read
    API-->>RP: Resource response per scope/policy
~~~

### 7.1. Authorization Request

The RP generates a random `state`, a PKCE verifier/challenge, and an OIDC `nonce` if used. Example:

~~~http
GET /oauth2/authorize?response_type=code&client_id=portal-web&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&scope=openid%20profile%20email%20orders.read&state=STATE_RANDOM&nonce=NONCE_RANDOM&code_challenge=PKCE_CHALLENGE&code_challenge_method=S256 HTTP/1.1
Host: login.example.vn
~~~

The OP verifies the client, redirect URI, response type, scopes, and policy. The user is authenticated; if required, a consent page displays the scopes. In the Code Flow, the OIDC `nonce` is optional; if the request includes a nonce, the ID Token must contain the matching value and the RP must verify it.

### 7.2. Authorization Response

After successful user authentication and consent, the OP returns the authorization code to the registered redirect URI:

~~~http
HTTP/1.1 302 Found
Location: https://portal.example.vn/login/oauth2/code/portal?code=AUTH_CODE_REDACTED&state=STATE_RANDOM
~~~

In the Authorization Code Flow, the front-channel authorization response contains the code (and state if sent by the client); the ID Token is returned in the token response, not via this redirect.

### 7.3. Token Request and Response

The client sends the code to the token endpoint along with the PKCE verifier and client authentication per its registration:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Content-Type: application/x-www-form-urlencoded
Authorization: Basic CLIENT_CREDENTIALS_REDACTED

grant_type=authorization_code&code=AUTH_CODE_REDACTED&redirect_uri=https%3A%2F%2Fportal.example.vn%2Flogin%2Foauth2%2Fcode%2Fportal&code_verifier=PKCE_VERIFIER_REDACTED
~~~

An OIDC response can contain both an access token and an ID Token:

~~~json
{
  "access_token": "ACCESS_TOKEN_REDACTED",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile email orders.read",
  "id_token": "SIGNED_ID_TOKEN_REDACTED"
}
~~~

This JSON is illustrative. Actual responses depend on the grant, granted scopes, token format, and client policy. Do not send the ID Token in the Authorization header to call APIs; Resource Servers accept access tokens per the API contract.

## 8. ID Token and Mandatory RP Validations

An ID Token is OIDC evidence of an end-user authentication event. It is signed by the OP and contains claims defined by OIDC Core.

Illustrative payload (signature omitted):

~~~json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": "portal-web",
  "iat": 1794825600,
  "exp": 1794825900,
  "nonce": "NONCE_RANDOM",
  "name": "Nguyen An",
  "email": "an@example.vn",
  "email_verified": true
}
~~~

Not every ID Token contains `name` or `email`. Profile claims depend on scopes, available data, consent, and policy. Core claims include issuer, subject, audience, issued-at time, and expiration time.

At a minimum, the RP must validate:

1. **Signature:** verify the JWS using a trusted public key from the JWK Set of the right issuer and an accepted algorithm.
2. **Issuer (`iss`):** matches the discovered/registered issuer exactly; do not use substring matching or similar hostnames.
3. **Audience (`aud`):** contains the RP's exact client ID. If multiple audiences are present, apply the `azp` (authorized party) rule; if `azp` is present, verify it matches the appropriate client.
4. **Expiration (`exp`):** the token has not expired; clock skew must be bounded.
5. **Issued At (`iat`):** the issuance time is reasonable per policy.
6. **Nonce:** if the request sent a nonce, match it against the nonce bound to the current authorization transaction.
7. **Authentication context:** if `max_age`, `auth_time`, `acr`, or `amr` were requested, verify the corresponding claims and policy.
8. **Hash claims:** if the flow/response type requires `c_hash` or `at_hash`, validate them per OIDC Core.

Never merely Base64-decode a JWT and trust its payload. Decoding does not verify the signature, issuer, audience, or expiration.

### 8.1. Using (iss, sub) as the Subject Identity

`sub` is the subject identifier assigned by the OP. The RP should use the pair `(iss, sub)` as the user identifier within OIDC scope. Do not assume email or username is a stable identifier; emails can change, collide, or be reassigned.

If the OP uses pairwise subject identifiers, the same user may have different `sub` values across sectors/clients per policy. The RP must not correlate identities across clients by comparing email addresses unless the OP provides that contract.

## 9. Distinguishing ID Token, Access Token, and UserInfo

| Attribute | ID Token | Access Token | UserInfo response |
|---|---|---|---|
| Consumer | OIDC Client / RP | Resource Server or UserInfo endpoint | OIDC Client / RP |
| Purpose | Verify authentication and subject | Access resources per permissions | Retrieve additional user claims |
| Audience | Client ID | Resource Server/resource | Protected by access token |
| Format | OIDC-signed JWT | JWT or opaque depending on AS | JSON claims |
| Sent in Authorization header to call APIs | **No** | Yes, per token type/scheme | No |
| Claims | Authentication claims and permitted claims | Authorization/resource claims | Claims per scope and policy |

A valid ID Token does not prove the client is authorized to read an API. An access token with scope `orders.read` does not guarantee all profile information will appear in the ID Token. Separating purposes prevents token confusion and data leakage.

### 9.1. UserInfo Endpoint

When additional claims are needed, the RP calls the UserInfo endpoint with an access token:

~~~http
GET /userinfo HTTP/1.1
Host: login.example.vn
Authorization: Bearer ACCESS_TOKEN_REDACTED
Accept: application/json
~~~

UserInfo is a protected resource of the OP. Spring Authorization Server handles Bearer access tokens by default; the application can customize the UserInfo mapper/handler to decide which claims are returned based on scope, principal, authorization, and policy.

The RP must verify that `sub` in the UserInfo response matches `sub` in the ID Token. If they differ, the RP must not treat the response as the profile of the same user.

Do not send an ID Token to the UserInfo endpoint, and do not send a refresh token to APIs. Only return claims that have data and are permitted by scope/consent/policy.

## 10. Configuring Spring Security OAuth2 Client on the RP Side

On the RP side, the `openid` scope in `ClientRegistration` tells Spring Security that login uses OIDC. Spring Security then uses OIDC components such as `OidcUserService`; without `openid`, login is processed as OAuth2 Login with `DefaultOAuth2UserService`.

Example Spring Boot application YAML:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: login-server
            client-id: portal-web
            client-secret: ${PORTAL_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - orders.read
        provider:
          login-server:
            issuer-uri: https://login.example.vn
~~~

Spring Boot uses `issuer-uri` to discover Provider Configuration and retrieve authorization, token, JWK, and UserInfo endpoints from metadata. The client must use the exact HTTPS issuer. In production, secrets should be injected from a secret manager/environment variables rather than committed as real values in YAML.

### 10.1. OIDC Principal

After a successful login, Spring Security can expose a principal of type `OidcUser` and the ID Token as `OidcIdToken`.

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProfileController {

    @GetMapping("/me")
    ProfileView me(@AuthenticationPrincipal OidcUser oidcUser) {
        return new ProfileView(
                oidcUser.getSubject(),
                oidcUser.getFullName(),
                oidcUser.getEmail());
    }
}
~~~

`ProfileView` is an application-defined DTO. The controller reads claims from the principal already processed by Spring Security; do not manually decode the raw ID Token to extract email or user ID.

### 10.2. Missing openid Scope

If `ClientRegistration` only contains `profile,email` without `openid`, Spring Security does not treat this as an OIDC login. The client must not expect `OidcUser`, an ID Token, or the OIDC-specific validation flow. Conversely, having `openid` in client registration when the AS has not enabled OIDC will not produce a complete OpenID Provider either.

## 11. Discovery and Provider Configuration

OIDC Discovery allows an RP to locate an OP's endpoints and capabilities from its issuer. With issuer `https://login.example.vn`, the URL typically used is:

~~~http
GET /.well-known/openid-configuration HTTP/1.1
Host: login.example.vn
Accept: application/json
~~~

Abbreviated illustrative metadata:

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
  "id_token_signing_alg_values_supported": ["RS256"]
}
~~~

This is an example, not fixed metadata for every deployment. Runtime metadata must reflect the actual configured public endpoints, issuer, subject types, and algorithms.

### 11.1. Discovery Is Not Dynamic Client Registration

Provider Configuration publishes information **about the OP** for client discovery. It does not automatically register new clients. Dynamic Client Registration is a separate endpoint, disabled by default in Spring Authorization Server; only enable it when there is an appropriate use case, onboarding workflow, and protection policy.

### 11.2. OIDC Discovery vs. OAuth AS Metadata

OAuth 2.0 Authorization Server Metadata (RFC 8414) and OIDC Provider Configuration share many similar fields but serve different protocol profiles. An OIDC RP should use OIDC Discovery and verify the issuer per OIDC Core. Do not take an issuer from one metadata document and fetch JWKs/endpoints from another host without an explicit trust contract.

## 12. Common Errors When Enabling OIDC and Handling openid

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Discovery endpoint returns 404 | `oidc(Customizer.withDefaults())` not enabled or wrong issuer/path | Check the AS filter chain and public routes |
| Authorization request yields no ID Token | Missing `openid` scope; request is OAuth2 only | Add `openid` to allowed registration scopes and the request |
| Request has `openid` but fails with `invalid_scope` | `RegisteredClient` does not allow the scope | Register `OidcScopes.OPENID` and verify the right client ID |
| OIDC endpoint enabled but UserInfo fails | Missing `JwtDecoder` or invalid access token | Register a decoder from `JWKSource` and inspect the token |
| No JWK Set endpoint | `JWKSource<SecurityContext>` not registered | Configure public JWK Set and signing key |
| Client does not receive `OidcUser` | Client registration missing `openid` or wrong provider config | Check scopes and `issuer-uri` |
| ID Token signature validation fails | JWKS/issuer/key rotation or algorithm mismatch | Discover the right issuer, check `kid`, signing algorithm, and rollover |
| `aud` does not contain client ID | Wrong ID Token audience or RP pointing to wrong OP | Inspect ID Token, client registration, and issuer |
| Nonce mismatch | Response matched to wrong transaction or nonce reused | Generate a random nonce per transaction and match exactly |
| UserInfo `sub` differs from ID Token `sub` | UserInfo mapper maps subject incorrectly | Reject response, inspect mapper |
| `profile` granted but `name` missing | User store lacks data or policy omits claim | Check user data, consent, and mapper |
| API rejects ID Token | RP sent the wrong token | Call the API with an access token |
| Browser not redirected to login | Missing user authentication chain/entry point | Configure login mechanism and HTML entry point |
| Refresh token still works after OP logout | OIDC logout does not revoke all OAuth tokens automatically | Design separate revocation/authorization cleanup |

## 13. Test Matrix for OIDC Core and the openid Scope

| # | Test Case | Expected Result |
|---|---|---|
| 1 | Call Provider Configuration after enabling OIDC | Metadata returns the expected issuer |
| 2 | Call Provider Configuration when OIDC is disabled | Endpoint is not published / does not operate as OIDC |
| 3 | Registration allows `openid`, request includes `openid` | Processed as an OIDC Authentication Request |
| 4 | Registration allows `openid`, request omits `openid` | OAuth 2.0 request; no ID Token expected |
| 5 | Request includes `openid` but registration disallows it | Scope rejected |
| 6 | Request `openid profile email` | Corresponding claims returned only when data exists and policy/consent allows |
| 7 | Request `openid orders.read` | OIDC authentication and API scope handled for their respective purposes |
| 8 | Client Credentials requests `openid` to sign in a user | Do not use this grant in place of end-user OIDC login |
| 9 | Authorization Code Flow, user not logged in | Redirected to user authentication mechanism |
| 10 | Login succeeds, consent valid | Authorization code returned to registered redirect URI |
| 11 | Exchange valid code | Token response includes ID Token |
| 12 | Wrong PKCE verifier | Token endpoint rejects request |
| 13 | ID Token with invalid signature | RP rejects token |
| 14 | Wrong `iss` | RP rejects token |
| 15 | `aud` does not contain client ID | RP rejects token |
| 16 | Expired ID Token | RP rejects token |
| 17 | Request sent nonce, ID Token returns different nonce | RP rejects token |
| 18 | Valid ID Token and matching nonce | RP accepts if all other validations pass |
| 19 | UserInfo with valid access token | Returns claims per scope/policy |
| 20 | Call UserInfo with ID Token | Rejected due to wrong credential type |
| 21 | UserInfo `sub` differs from ID Token `sub` | RP rejects response |
| 22 | Missing `JwtDecoder` | UserInfo endpoint does not work properly |
| 23 | Missing `JWKSource`/signing key | ID Token/JWK publication does not work properly |
| 24 | `ClientRegistration` missing `openid` | Spring Security uses OAuth2-specific flow |
| 25 | `ClientRegistration` includes `openid` | Spring Security uses OIDC components like `OidcUserService` |
| 26 | Unstable issuer behind reverse proxy | Discovery/ID Token issuer mismatch |
| 27 | OP logout | Verify session logout; test revocation separately if policy requires |
| 28 | Dynamic Client Registration disabled | Do not assume `/connect/register` exists |
| 29 | Signing key rotation | RP validates new tokens and old tokens during rollover window |
| 30 | Consent denies `email` but accepts `openid` | Do not return email claims against consent/policy |

### 13.1. Key Assertions in Integration Tests

Integration tests should verify together:

- Metadata issuer matches the public URL.
- Only requests with `openid` enter the OIDC flow.
- Both registration and authorization request permit the requested scopes.
- Token endpoint returns an ID Token after exchanging a valid code.
- RP verifies signature, issuer, audience, expiry, and nonce if present.
- UserInfo uses an access token and returns a consistent `sub`.
- Resource Server only accepts access tokens, checking audience/scopes separately.
- Logout and token revocation are tested as two distinct behaviors.

## 14. Checklist and Self-Assessment Questions

- [ ] Enable OIDC with `oidc(Customizer.withDefaults())` in the AS `SecurityFilterChain`.
- [ ] Provide a user authentication mechanism for the Authorization Code Flow.
- [ ] Allow `OidcScopes.OPENID` and required scopes in `RegisteredClient`.
- [ ] Ensure the actual Authorization Request includes `openid`; do not only register the scope on the client.
- [ ] Do not use `openid` as a role or API permission.
- [ ] Return `profile`, `email`, `address`, and `phone` only per available data, consent, and policy.
- [ ] Provide a `JWKSource<SecurityContext>` and protected signing key with a rollover plan.
- [ ] Provide a `JwtDecoder` for the OIDC UserInfo endpoint.
- [ ] Keep the issuer stable and consistent with discovery/ID Token.
- [ ] Have the RP use OIDC Discovery and verify the issuer.
- [ ] Have the RP validate ID Token signature, `iss`, `aud`, `exp`, `iat`, nonce, and additional claims as needed.
- [ ] Have the RP use `(iss, sub)` as the subject identity rather than relying solely on email.
- [ ] Never send an ID Token to a Resource Server as an access token.
- [ ] Call UserInfo with an access token; `sub` must match the ID Token.
- [ ] Enable Dynamic Client Registration only when there is a dedicated use case and policy.
- [ ] Design and test session logout and token revocation separately.

**Self-Assessment Questions**

1. Why is an OAuth 2.0 Authorization Server not automatically a full OpenID Provider?
2. Which protocol endpoints does `oidc(Customizer.withDefaults())` add?
3. Why must an OIDC Authentication Request contain the `openid` scope?
4. Is registering `openid` in `RegisteredClient` enough to make every request an OIDC request?
5. If a request omits `openid`, can the client expect an ID Token?
6. What is the difference between `openid`, `profile`, `email`, and `orders.read`?
7. Why is Client Credentials not an end-user OIDC login flow?
8. Is the ID Token returned in the authorization response or the token response in the Authorization Code Flow?
9. Which claims must an RP validate before trusting an ID Token?
10. Why is `(iss, sub)` more suitable as a subject identity than email?
11. Which credential does UserInfo require, and why must `sub` match the ID Token?
12. Why does SAS require a `JwtDecoder` when the UserInfo endpoint is enabled?
13. How does Discovery metadata differ from Dynamic Client Registration?
14. Does OIDC logout automatically revoke all access tokens and refresh tokens?

## References

- [OpenID Connect Core 1.0 — Authentication using the Authorization Code Flow](https://openid.net/specs/openid-connect-core-1_0.html#CodeFlowAuth): Authentication Request, `openid` scope, ID Token, nonce, and validation.
- [OpenID Connect Core 1.0 — Standard Claims](https://openid.net/specs/openid-connect-core-1_0.html#StandardClaims): `profile`, `email`, `address`, `phone` claims and their meanings.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration, issuer, and discovery metadata.
- [Spring Authorization Server 1.5.8 — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): OIDC disabled by default, `oidc(Customizer.withDefaults())`, OIDC endpoints, `JwtDecoder`, and `AuthorizationServerSettings`.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): UserInfo endpoint, Bearer access token, and customizing the UserInfo response.
- [Spring Authorization Server — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): customizing UserInfo claims.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/): configuring the `openid` scope, OIDC login, and OIDC-specific components.
- [Spring Security — Advanced OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): handling ID Tokens and OIDC user authentication.
