# 3.5. Discovery Document and Its Relationship with Issuer

## 1. Why Does OIDC Need a Discovery Document?

In OpenID Connect (OIDC), the logging-in application is called the **Relying Party (RP)** or **OIDC Client**; the system authenticating the user is called the **OpenID Provider (OP)**. To log in, the Client must know the authorization endpoint, token endpoint, where to obtain public keys to verify the ID Token, supported algorithms, and provider capabilities.

If every application had to manually declare all OP URLs and capabilities, integration would easily mix up environments, realms/tenants, endpoint versions, or signing keys. **OpenID Connect Discovery 1.0** provides a standard mechanism: the OP publishes a JSON document describing itself. That document is commonly called the **Discovery Document**, **OpenID Provider Configuration**, or **OIDC metadata**.

The Client typically starts from a **trusted issuer URI**, queries that issuer's discovery document, confirms the JSON actually describes the expected issuer, and then retrieves the endpoints and token validation details. This relationship is vital in Spring Security OAuth 2.0/OIDC Client: simply by configuring the appropriate issuer, Spring Security can automatically discover the information needed to execute OIDC Login.

Example issuer:

~~~text
https://login.example.org/realms/training
~~~

The corresponding OIDC Discovery Document is typically located at:

~~~text
https://login.example.org/realms/training/.well-known/openid-configuration
~~~

These are illustrative URLs; addresses under <code>example.org</code> are not real providers.

> **Principle:** The Issuer defines **which OP is trusted**; the Discovery Document describes **how to communicate with that OP**. The Discovery URL is not the issuer value, and the well-known suffix must never be included in the issuer configuration.

## 2. What Is an Issuer?

### 2.1. Identifier of the OpenID Provider

An issuer is a URL identifying an OP, using the <code>https</code> scheme, optionally containing a path, and having no query or fragment per OIDC Discovery. Some example forms:

~~~text
https://identity.example.com
https://identity.example.com/realms/team-a
https://login.example.org/tenant/contoso
~~~

An issuer can identify a realm or tenant, not necessarily a single physical server. Two realms running on the same host can have two distinct issuers. The Client must know precisely which issuer has been authorized by the application administrator.

The issuer is placed in the <code>iss</code> claim of the **ID Token** issued by the OP. An illustrative ID Token payload:

~~~json
{
  "iss": "https://login.example.org/realms/training",
  "sub": "248289761001",
  "aud": "training-web-client",
  "exp": 1999999999,
  "iat": 1999999000
}
~~~

The JSON above shows only selected claims, not a complete JWT. In practice, the ID Token must have its signature and relevant OIDC claims verified. The <code>iss</code> value must match the issuer trusted by the Client.

### 2.2. Distinguishing Issuer from Other URLs and Identifiers

| Value | Example | Purpose |
|---|---|---|
| **Issuer URI** | <code>https://login.example.org/realms/training</code> | Identifies the trusted OP |
| Discovery URL | <code>https://login.example.org/realms/training/.well-known/openid-configuration</code> | Fetches OP metadata |
| Authorization endpoint | <code>https://login.example.org/realms/training/protocol/openid-connect/auth</code> | Where the browser starts the authentication flow |
| Token endpoint | <code>https://login.example.org/realms/training/protocol/openid-connect/token</code> | Where the Client exchanges the authorization code for tokens |
| JWKS URI | <code>https://login.example.org/realms/training/protocol/openid-connect/certs</code> | Address for fetching public keys to verify signatures |
| Client ID | <code>training-web-client</code> | Identifier of the application registered with the OP |
| Registration ID | <code>training</code> | Internal name in Spring Security to select ClientRegistration |
| Redirect URI | <code>https://app.example.org/login/oauth2/code/training</code> | Callback address belonging to the Client application |

Do not take a login page URL, authorization endpoint, JWKS URL, or discovery URL and treat it as the issuer. Nor do endpoints have to share the same host/path as the issuer: the Client must read endpoints from verified metadata rather than constructing paths by guesswork.

### 2.3. Issuer Matching Requirement

Suppose the Client is configured with:

~~~text
https://login.example.org/realms/training
~~~

Yet the discovery document returns:

~~~json
{
  "issuer": "https://login.example.org/realms/other",
  "authorization_endpoint": "https://login.example.org/realms/other/protocol/openid-connect/auth"
}
~~~

This metadata **does not describe the configured issuer** and must be rejected. Likewise, an ID Token carrying <code>iss</code> for realm <code>other</code> must not be accepted in the flow for realm <code>training</code>.

OIDC requires metadata issuer to match exactly the issuer used to perform discovery. Differences in hostname, scheme, path, path casing, or trailing <code>/</code> can cause a mismatch. Never intentionally relax or bypass issuer validation just to make login succeed. When a mismatch occurs, inspect the configuration and the public issuer published by the OP.

OIDC user identity is reliably identified by the **pair (<code>iss</code>, <code>sub</code>)**. Two tokens from different issuers with the same <code>sub</code> do not automatically represent the same account; nor is email a reliable cross-provider identifier key.

## 3. Main Contents of a Discovery Document

The OIDC Provider Configuration is served via HTTP GET as JSON. Example request:

~~~http
GET /realms/training/.well-known/openid-configuration HTTP/1.1
Host: login.example.org
Accept: application/json
~~~

Abbreviated example response:

~~~json
{
  "issuer": "https://login.example.org/realms/training",
  "authorization_endpoint": "https://login.example.org/realms/training/protocol/openid-connect/auth",
  "token_endpoint": "https://login.example.org/realms/training/protocol/openid-connect/token",
  "userinfo_endpoint": "https://login.example.org/realms/training/protocol/openid-connect/userinfo",
  "jwks_uri": "https://login.example.org/realms/training/protocol/openid-connect/certs",
  "response_types_supported": ["code", "id_token"],
  "subject_types_supported": ["public"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "scopes_supported": ["openid", "profile", "email"],
  "claims_supported": ["sub", "iss", "aud", "exp", "iat", "name", "email"],
  "token_endpoint_auth_methods_supported": ["client_secret_basic", "client_secret_post"],
  "code_challenge_methods_supported": ["S256"]
}
~~~

This is illustrative data, not metadata verified against a real provider. An OP may return additional fields or omit optional ones. Do not assume fields like <code>userinfo_endpoint</code>, <code>code_challenge_methods_supported</code>, or <code>claims_supported</code> are always present.

### 3.1. Identity and Endpoint Metadata

| Field | Meaning | When Used |
|---|---|---|
| <code>issuer</code> | OP identifier | Matched against the requested issuer and the <code>iss</code> claim |
| <code>authorization_endpoint</code> | Endpoint receiving the Authorization Request | Redirecting the browser to log in |
| <code>token_endpoint</code> | Endpoint receiving the Token Request | Exchanging the code for tokens over the back channel |
| <code>jwks_uri</code> | Endpoint publishing the JSON Web Key Set | Locating public keys to verify the ID Token signature |
| <code>userinfo_endpoint</code> | UserInfo endpoint if supported by OP | Fetching profile info with an access token |
| <code>end_session_endpoint</code> | Federated logout endpoint, if published | Supporting RP-Initiated Logout depending on provider |

In the Authorization Code Flow, the Client needs to know the authorization endpoint and token endpoint. When verifying asymmetrically signed ID Tokens, JWKS publishes the public keys used for signature verification. **JWKS does not contain user passwords or client secrets**, and the public keys published here are not the OP's private keys.

### 3.2. Capability Metadata

| Field | What to Understand |
|---|---|
| <code>response_types_supported</code> | Response types advertised by the OP; must support <code>code</code> for Authorization Code Flow |
| <code>subject_types_supported</code> | Subject types such as <code>public</code> and <code>pairwise</code> |
| <code>id_token_signing_alg_values_supported</code> | ID Token signing algorithms, e.g. <code>RS256</code> |
| <code>scopes_supported</code> | Advertised scopes, including <code>openid</code> for an OIDC OP |
| <code>claims_supported</code> | Some claims the OP is capable of providing |
| <code>grant_types_supported</code> | Advertised grant types if the OP includes this field |
| <code>token_endpoint_auth_methods_supported</code> | Client authentication methods at the token endpoint |
| <code>code_challenge_methods_supported</code> | PKCE methods, e.g. <code>S256</code>, if advertised by the OP |

Discovery reflects **server capabilities**, not the list of permissions for a specific Client. An OP may support <code>client_secret_basic</code> and <code>client_secret_post</code>, yet the Client may only use its registered method. The OP advertising the <code>email</code> scope also does not guarantee the Client will necessarily be granted that scope.

The Discovery Document does not supply client secrets, authorization codes, or application tokens. Those values have independent lifecycles and exchange channels.

## 4. Trust Relationship: issuer → metadata → ID Token

There are three interconnected checkpoints:

1. **Configured issuer:** the application knows the trusted OP in advance, e.g. <code>https://login.example.org/realms/training</code>.
2. **Issuer in metadata:** the OP publishes an <code>issuer</code> field matching the configured issuer. Only after verifying source and consistency does the Client use endpoints from the metadata.
3. **Issuer in ID Token:** the <code>iss</code> claim must match the trusted issuer, while signature and required claims must also be valid.

~~~mermaid
flowchart TD
    A["Configure issuer-uri"] --> B["Fetch OIDC Discovery Document"]
    B --> C{"Does metadata.issuer match issuer-uri?"}
    C -->|No| X["Reject metadata / detect wrong OP"]
    C -->|Yes| D["Obtain authorization endpoint, token endpoint, JWKS URI"]
    D --> E["Complete Authorization Code Flow"]
    E --> F["Receive ID Token"]
    D --> G["Fetch / cache public keys from JWKS URI"]
    G --> H["Verify ID Token signature"]
    F --> H
    H --> I{"Are iss, aud, exp, and other OIDC checks valid?"}
    I -->|No| Y["Reject login"]
    I -->|Yes| J["Accept user identity"]
~~~

An ID Token whose signature verifies mathematically **is not guaranteed to come from the issuer the Client trusts**. The Client must check <code>iss</code>, <code>aud</code> (usually containing the Client ID), <code>exp</code>, related timestamps, and OIDC conditions such as <code>nonce</code> when the flow uses a nonce. Conversely, a matching <code>iss</code> is still insufficient if the signature is invalid, the token is expired, or the audience does not match.

In particular, never read the <code>iss</code> claim from an **unverified** token to automatically trust a new provider. Trusted issuers must be decided beforehand via application configuration or allow-list policy.

### 4.1. Role of JWKS and Key Rotation

A JWT header may contain:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026-01"
}
~~~

Within the trusted issuer's JWKS, the Client locates the public key with the matching <code>kid</code>, ensures the algorithm is permitted, and verifies the signature. An OP may publish multiple keys simultaneously to rotate signing keys. Spring Security / Nimbus libraries support key lookup, caching, and refresh per configuration; avoid hardcoding a single public key when the provider expects dynamic JWKS usage.

## 5. Discovery and the OIDC Login Flow

Fetching metadata typically happens when Spring Security initializes or resolves <code>ClientRegistration</code>, depending on version and configuration. The Client **does not necessarily fetch the Discovery Document on every login**.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Spring Security Client
    participant OP as OpenID Provider
    participant B as Browser
    C->>OP: GET OIDC Configuration Endpoint
    OP-->>C: JSON metadata: issuer, endpoints, jwks_uri
    C->>C: Match metadata.issuer against issuer-uri
    B->>C: GET /oauth2/authorization/training
    C-->>B: Redirect to authorization_endpoint
    B->>OP: Authorization Request: scope=openid, response_type=code...
    OP-->>B: Callback redirect with code and state
    B->>C: GET /login/oauth2/code/training?code=...&state=...
    C->>OP: POST token_endpoint to exchange code for tokens
    OP-->>C: ID Token and related tokens
    C->>OP: GET jwks_uri (when loading/refreshing keys)
    OP-->>C: Public JWKS
    C->>C: Verify signature, iss, aud, exp, relevant claims
    C-->>B: Complete login session
~~~

Each step has a distinct purpose: discovery retrieves OP configuration; the authorization endpoint handles the login request; the token endpoint exchanges the code; JWKS supplies signature verification keys. **The issuer runs throughout the flow**, ensuring the Client receives the right configuration and ID Token from the right provider.

When using PKCE, the Client also sends a code challenge in the authorization request and a verifier in the token request to protect the authorization code. PKCE solves a different risk; it does not replace issuer or ID Token signature verification.

## 6. Using issuer-uri in Spring Security OAuth2 Client

### 6.1. Spring Boot 3 / Spring Security 6 Example

An OIDC web Client application typically needs these dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Configure <code>application.yml</code>:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          training:
            provider: training-oidc
            client-id: training-web-client
            client-secret: replace-with-secret-from-vault
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          training-oidc:
            issuer-uri: https://login.example.org/realms/training
~~~

The client secret value is a placeholder for the lesson. In a real project, read the secret from a secure secret manager or environment variable, never commit it to the repository; at the OP, register the exact Client ID, authentication method, and redirect URI.

Component breakdown:

- <code>training</code>: the **registration ID** in the Spring application, also appearing in the default login initiation path <code>/oauth2/authorization/training</code>.
- <code>training-oidc</code>: internal **provider ID** linking the registration to the OP configuration; does not need to match the issuer.
- <code>issuer-uri</code>: the **root** issuer URL. Do not append the <code>/.well-known/openid-configuration</code> suffix.
- Discovery metadata supplies Spring Security with <code>authorizationUri</code>, <code>tokenUri</code>, <code>jwkSetUri</code>, and required details.
- The <code>openid</code> scope indicates an OIDC request; the Client expects to receive an ID Token and validate it per OIDC.

A minimal login configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

After successful OIDC authentication, you can obtain the <code>OidcUser</code> principal to read claims verified by the library. Example endpoint returning only minimal identity info:

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {
    @GetMapping("/me")
    public Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        return Map.of(
            "issuer", user.getIdToken().getClaimAsString("iss"),
            "subject", user.getSubject()
        );
    }
}
~~~

Do not return raw access tokens, refresh tokens, or ID Tokens in an API just to check login status. Those tokens can grant access to resources and must be protected.

### 6.2. Benefits and Limitations of issuer-uri Configuration

When metadata is valid, Spring Security uses the OP-advertised endpoints and JWKS to drive the OIDC flow. The application avoids hardcoding numerous URLs; key rotation or endpoint updates published by the OP can be handled by the library according to an appropriate metadata/cache lifecycle.

However, configuring an issuer does not replace <code>client-id</code>, Client authentication, redirect URI, scopes, authorization, or session management. Working discovery only confirms the Client obtained metadata; it does not mean a user is logged in or a token is valid.

Depending on how Boot/Spring Security builds `ClientRegistration`, fetching metadata may require connecting to the OP during startup. If the OP is down, DNS is misconfigured, TLS certificates are invalid, or returned metadata is malformed, the application may fail while constructing configuration. Ensure the OP is reliable and the infrastructure has the necessary network connectivity.

Beyond YAML, Spring Security also provides factory APIs in <code>ClientRegistrations</code> to construct client registrations from an issuer. In standard applications, let the framework perform discovery and token validation; manually making HTTP calls, parsing JSON, and assembling `ClientRegistration` yourself risks missing critical checks.

## 7. Distinguishing OIDC Discovery from OAuth 2.0 Authorization Server Metadata

These two standards are related but not identical:

- **OpenID Connect Discovery 1.0** describes OpenID Provider Configuration, typically with the suffix <code>/.well-known/openid-configuration</code>. Its metadata includes OIDC-specific fields such as <code>subject_types_supported</code> and <code>id_token_signing_alg_values_supported</code>.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata** describes OAuth Authorization Server metadata, using the default well-known suffix <code>/.well-known/oauth-authorization-server</code> and a different path-insertion rule when the issuer has a path.

Example:

| Concept | Example URL |
|---|---|
| Issuer | <code>https://login.example.org/realms/training</code> |
| OIDC Discovery URL | <code>https://login.example.org/realms/training/.well-known/openid-configuration</code> |
| RFC 8414 metadata URL (default suffix) | <code>https://login.example.org/.well-known/oauth-authorization-server/realms/training</code> |

Note the position of <code>/.well-known/</code>: the OIDC example places it **after the issuer path**, whereas RFC 8414 places well-known **before the issuer path**. Some OPs and libraries support multiple compatible URL forms, but never assume every provider implements all variants.

To implement **OIDC Login**, the Client needs OIDC-compliant metadata and validation mechanisms. An Authorization Server that only serves OAuth 2.0 metadata does not automatically issue ID Tokens or satisfy all OIDC requirements.

## 8. Issuer Across Multiple Environments and Tenants

### 8.1. Development, Staging, Production

~~~text
Development: https://login-dev.example.org/realms/training
Staging:     https://login-staging.example.org/realms/training
Production:  https://login.example.org/realms/training
~~~

Each environment needs its own matching issuer, Client ID, secret/method, and redirect URI. A production application must never accept an ID Token issued by a staging issuer merely because both systems share the same realm name or codebase.

When an OP runs behind a reverse proxy, metadata may return an internal issuer:

~~~text
http://identity-service:8080/realms/training
~~~

While the Client uses the public issuer:

~~~text
https://login.example.org/realms/training
~~~

A mismatch in that situation is a legitimate protection failure. Configure the public hostname/external issuer and proxy headers on the OP to match the external URL—never disable issuer validation to bypass the error.

### 8.2. Multiple ClientRegistrations

An application can declare two separate OPs:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-a:
            provider: company-a
            client-id: web-company-a
            client-secret: replace-with-secret-a
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
          company-b:
            provider: company-b
            client-id: web-company-b
            client-secret: replace-with-secret-b
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          company-a:
            issuer-uri: https://login.example.org/realms/company-a
          company-b:
            issuer-uri: https://login.example.org/realms/company-b
~~~

This is an illustrative example; real deployments require formal registrations and secrets/authentication methods appropriate for each OP. The application must not merge identities based solely on <code>sub</code> across two issuers.

If users are allowed to enter an issuer URL for the application to fetch metadata dynamically, use an allow-list of permitted providers or a dedicated verification workflow. **Never automatically fetch an arbitrary issuer received from a request**, as that creates SSRF risks and could accept a rogue provider. Prefer trusted ClientRegistrations pre-registered by an administrator.

## 9. When an OP Does Not Support Discovery

With some legacy OAuth/OIDC systems, endpoints may need to be declared manually:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy:
            provider: legacy
            client-id: legacy-web
            client-secret: replace-with-secret
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          legacy:
            authorization-uri: https://legacy.example.org/oauth/authorize
            token-uri: https://legacy.example.org/oauth/token
            jwk-set-uri: https://legacy.example.org/oauth/jwks
            user-info-uri: https://legacy.example.org/oauth/userinfo
            user-name-attribute: sub
~~~

The URLs and secret are placeholders. Manual configuration is only valid for OIDC if the OP genuinely issues spec-compliant ID Tokens and the Client has proper validation mechanisms. Specifically, **verify how the issuer is determined and checked when using manual configuration in your current Spring Security version**. Filling in authorization endpoint, token endpoint, and JWKS URI individually does not automatically enforce the same issuer constraints as discovery.

If a provider only supports OAuth 2.0 and does not issue OIDC ID Tokens, then even if the Authorization Code Flow works, it is **not** a complete OIDC integration. An access token must never be treated as an ID Token or identity proof for the Client.

## 10. Inspecting the Discovery Document During Integration

In a development environment, you can read public metadata using HTTP tools:

~~~bash
curl --fail --silent --show-error \
  "https://login.example.org/realms/training/.well-known/openid-configuration"
~~~

Or using PowerShell:

~~~powershell
$metadata = Invoke-RestMethod -Uri "https://login.example.org/realms/training/.well-known/openid-configuration"
$metadata.issuer
$metadata.authorization_endpoint
$metadata.token_endpoint
$metadata.jwks_uri
~~~

First compare <code>issuer</code> in the JSON against the configured issuer. Seeing HTTP 200 or valid JSON alone is not enough to conclude you reached the right OP; a proxy or tenant router might return metadata for a different realm.

A useful verification checklist:

1. Obtain the official issuer from OP admin configuration or documentation; never use a login page or discovery URL as the issuer.
2. Access discovery over HTTPS and verify certificate, status, and metadata structure.
3. Confirm the returned <code>issuer</code> matches the configured issuer, including path and trailing <code>/</code>.
4. Confirm endpoints advertised by metadata are reachable from the application; verify <code>response_types_supported</code> includes <code>code</code>.
5. Verify Client ID, authentication method, redirect URI, and scopes registered with the OP.
6. Test login; if token validation fails, inspect issuer, audience, token expiration, JWKS, and <code>kid</code> without printing raw tokens into logs.

### 10.1. Common Issues

| Symptom | Possible Cause | How to Handle |
|---|---|---|
| Discovery URL returns HTTP 404 | Wrong issuer/path, discovery disabled on OP, or OIDC/RFC 8414 URL convention mix-up | Verify the official issuer and metadata URL published by the OP |
| ClientRegistration initialization fails | DNS/TLS/proxy error, OP unavailable, or invalid JSON | Check network, certificate trust, response payload, and Spring configuration |
| <code>issuer mismatch</code> when reading metadata | <code>metadata.issuer</code> differs from configured issuer | Fix public issuer at the OP or <code>issuer-uri</code> on the Client to match the right provider |
| ID Token rejected due to <code>iss</code> | Token issued from another realm/tenant | Verify login routing and correct ClientRegistration |
| Invalid ID Token signature | Wrong JWKS, missing <code>kid</code>, disallowed algorithm, or key rotation | Verify the issuer's JWKS and token decoder configuration |
| Authorization succeeds but token endpoint fails | Wrong Client ID/secret, authentication method, redirect URI, or grant | Check actual registration and token endpoint metadata |
| Access token received but no ID Token | <code>openid</code> was not sent or OP only supports OAuth 2.0 | Distinguish OAuth 2.0 from OIDC and verify OP support |
| Users from two tenants get merged into one account | Storing users solely by email or <code>sub</code> | Use the <code>(iss, sub)</code> pair for cross-issuer identification |

## 11. Security Principles

**Issuer is a trust configuration:** only accept permitted OPs. Do not fetch metadata from an untrusted user-supplied URL, as this risks SSRF and logging in through a spoofed OP.

**Metadata must be verified:** fetch over HTTPS with TLS validation, and compare metadata issuer and endpoints against application trust policies. Never trust a new provider simply because JSON contains <code>authorization_endpoint</code> and <code>token_endpoint</code> keys.

**Never skip ID Token validation:** signature, issuer, audience, expiration, and relevant OIDC conditions must all be valid. A JWT claiming <code>iss</code> is not enough for the Client to accept it.

**Prepare for legitimate changes:** an OP can rotate public keys, change endpoints, or update metadata. Use a proper OIDC library, manage caching, and monitor discovery/JWKS errors; avoid hardcoding a single public key when the provider supports dynamic JWKS.

**Distinguish Client from Resource Server:** <code>spring.security.oauth2.client.provider.*.issuer-uri</code> configures an OAuth2/OIDC Client. <code>spring.security.oauth2.resourceserver.jwt.issuer-uri</code> is used when the application acts as a Resource Server validating JWTs on incoming requests. One application can play both roles, but they have separate configurations and processing flows.

## 12. Questions and Practice Exercises

### Scenario A — Computing the Discovery URL

An OP publishes the issuer:

~~~text
https://sso.example.net/tenant/alpha
~~~

**Question:** What are the OIDC Discovery URL, the <code>issuer-uri</code> value, and the expected <code>iss</code> claim?

**Answer:**

~~~text
Discovery URL:
https://sso.example.net/tenant/alpha/.well-known/openid-configuration

issuer-uri:
https://sso.example.net/tenant/alpha

ID Token iss:
https://sso.example.net/tenant/alpha
~~~

### Scenario B — Discovery from Another Realm

The Client configures <code>https://sso.example.net/realms/alpha</code>, yet metadata returns:

~~~json
{
  "issuer": "https://sso.example.net/realms/beta",
  "authorization_endpoint": "https://sso.example.net/realms/beta/auth",
  "token_endpoint": "https://sso.example.net/realms/beta/token",
  "jwks_uri": "https://sso.example.net/realms/beta/jwks"
}
~~~

**Answer:** Do not bypass issuer validation to use realm <code>beta</code>'s endpoints. Fix the path, tenant configuration, or create a valid registration for realm <code>beta</code> if that is the truly intended provider.

### Scenario C — Are Two Subjects Equal?

~~~text
Token A: iss=https://sso.example.net/realms/alpha, sub=12345
Token B: iss=https://sso.example.net/realms/beta,  sub=12345
~~~

**Answer:** Do not assume they belong to the same account. A subject identifier is scoped to its issuer. Cross-provider identity keys should include both <code>iss</code> and <code>sub</code>. If linking two accounts is desired, the application needs a dedicated, verified account-linking workflow.

### Practice Exercise with Spring Security

1. Pick an authorized OIDC OP in your development environment and obtain its official issuer.
2. Fetch the Discovery Document and inspect <code>issuer</code>, authorization endpoint, token endpoint, and JWKS URI.
3. Configure <code>issuer-uri</code> in Spring Boot OAuth2 Client, enable <code>oauth2Login()</code>, and log in via <code>/oauth2/authorization/&lt;registrationId&gt;</code>.
4. After login, read the <code>iss</code> claim from the OIDC principal verified by Spring Security and compare it with the original issuer.
5. In a test environment, intentionally configure a different realm's issuer and observe the error during discovery or ID Token validation—never disable validation to pass.

## 13. Key Takeaways

- **Issuer** is the OP identity trusted by the Client; that value appears in metadata as <code>issuer</code> and in the ID Token as the <code>iss</code> claim.
- **Discovery Document** describes OP endpoints, JWKS URI, and capabilities. For OIDC, its usual location is <code>&lt;issuer&gt;/.well-known/openid-configuration</code>.
- The Client must **match metadata issuer against the configured issuer**, while validating the ID Token's signature, issuer, audience, expiration, and relevant OIDC conditions.
- In Spring Security OAuth2 Client, use <code>spring.security.oauth2.client.provider.&lt;provider-id&gt;.issuer-uri</code> so the framework discovers and builds `ClientRegistration` details.
- Issuer is not the Discovery URL, authorization endpoint, token endpoint, JWKS URI, Client ID, or redirect URI. In multi-tenant systems, each issuer has its own trust boundary and identity scope.

### References

- **OpenID Connect Discovery 1.0**: Provider Configuration, issuer, metadata fields, and discovery rules.
- **OpenID Connect Core 1.0**: ID Token, <code>iss</code>/<code>aud</code> claims, and ID Token validation requirements.
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata**: OAuth 2.0 metadata and well-known URI rules.
- **RFC 7517 — JSON Web Key (JWK)** and **RFC 7518 — JSON Web Algorithms (JWA)**: key and algorithm representations in JWT.
- **Spring Security Reference — OAuth2 Client / OAuth2 Login** and **Spring Boot Reference — OAuth2 Client**: ClientRegistration, issuer-uri, and OIDC Login.
