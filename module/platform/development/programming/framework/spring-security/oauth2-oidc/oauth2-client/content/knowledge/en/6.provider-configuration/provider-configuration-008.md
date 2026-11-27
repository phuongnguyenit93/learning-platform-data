# 6.8. Pure OAuth 2.0 Providers vs. OIDC-Supporting Providers

## 1. Two Types of Providers: Same Authorization Flow, Different Identity Guarantees

A **Spring Security OAuth 2.0 OIDC Client** application can connect to providers with very different capabilities:

- **Pure OAuth 2.0 providers** provide mechanisms to request and grant access to resources: authorization endpoint, token endpoint, Access Token, scopes, and possibly a custom profile API. OAuth 2.0 **does not define a standard user authentication protocol** or an ID Token format.
- **OIDC providers (OpenID Providers, OP)** support **OpenID Connect**, an identity authentication layer built on top of OAuth 2.0. When the client requests OIDC properly, the provider issues an **ID Token** and can provide a **UserInfo endpoint**, discovery metadata, and JWKS for signature verification.

For example, a Spring Boot system might let employees log in via a corporate identity server with OIDC, while also allowing login through an external service that only supports OAuth 2.0 Login and an account info API. Both may start with the Authorization Code flow, yet how Spring Security **establishes user identity** after exchanging the code for tokens differs.

**An OIDC provider is also an OAuth 2.0 authorization server, but an OAuth 2.0 provider is not automatically an OIDC provider.** Moreover, a provider that supports OIDC can still handle a pure OAuth 2.0 transaction if the client does not request the `openid` scope and the provider permits it.

### 1.1. Core Comparison Table

| Criterion | Pure OAuth 2.0 provider | OIDC-supporting provider |
| --- | --- | --- |
| Protocol goal | Authorize a client to access resources | OAuth 2.0 authorization **and** OIDC user authentication |
| Authorization Code flow | Can be supported | Supported as a common flow |
| Access Token | Yes, used to call resource servers | Yes, used to call resource servers or UserInfo |
| ID Token | **Not defined by OAuth 2.0** | Issued in a valid OIDC Authorization Code flow |
| `openid` scope | Not a standard pure OAuth 2.0 scope; provider may reject it | Signal activating an OIDC request |
| UserInfo | May have a **custom** profile API with non-uniform schema | May provide a **standard OIDC UserInfo endpoint** |
| Account identifier | Per custom API/contract, e.g., `id`, `login` | Verified **`iss` + `sub` pair** |
| Identity verification | Depends on provider's custom mechanism and app conventions | Based on ID Token and OIDC validation rules |
| Discovery/JWKS | May support OAuth authorization server metadata, not mandatory | Commonly uses OIDC discovery/JWKS when published by provider |
| Spring Security principal | Typically `OAuth2User` | Typically `OidcUser`, which is also a subtype of `OAuth2User` |
| User service | Typically `DefaultOAuth2UserService` | Typically `OidcUserService` |

In the table, "typically" reflects default configuration when using `oauth2Login()`. A system can customize principals, user services, or mappings; do not infer a provider's entire feature set merely from a product name.

## 2. Pure OAuth 2.0 Is Not a Standardized Login Protocol

OAuth 2.0 defines **delegation/authorization**: the resource owner lets a client access a protected resource, typically via an Access Token. The protocol does not define a standard "logged-in user" with claims such as issuer, subject, and authentication time.

For example, a provider may allow:

1. The browser visits the authorization endpoint for user consent.
2. The provider redirects back to the application with an authorization code.
3. Spring Security exchanges the code at the token endpoint for an Access Token.
4. The application calls a custom profile endpoint with the Access Token.
5. The application uses an account identifier field, such as `id`, to create a local login session.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant C as Spring Boot OAuth2 Client
    participant P as OAuth2 Provider
    U->>C: Visit page requiring login
    C-->>U: Redirect to authorization endpoint
    U->>P: Log in and grant consent
    P-->>U: Redirect with code + state
    U->>C: Authorization Code callback
    C->>P: POST token endpoint, exchange code
    P-->>C: Access Token
    C->>P: GET custom profile API + Bearer Access Token
    P-->>C: {"id": 456, "login": "an.nguyen", ...}
    Note over C: Map id per provider contract
    C-->>U: Create local Authentication/session
~~~

This flow is commonly called **OAuth2 Login** in many frameworks. It lets the application establish a session based on calling the provider's profile API, yet **identity guarantees depend on the provider and how the application validates returned data**. Pure OAuth 2.0 does not inherently provide the guarantees of an OIDC ID Token.

### 2.1. An Access Token Is Not OIDC Proof

Do not infer "having an Access Token means a person has definitely been authenticated":

- An Access Token can represent **the client itself**, such as in the Client Credentials grant, with no interactive user.
- A token can be **opaque**, with no JWT structure for the application to read.
- Even when a token is a JWT, pure OAuth 2.0 does not require it to contain `iss`/`sub`/`aud` with ID Token semantics.
- An Access Token is designed for **resource servers**, and does not necessarily have the web application's client ID as its audience.

In pure OAuth2 Login, the client typically uses the Access Token to call a trusted profile API and obtain an identifier per the provider's contract. Never use `email` or `name` as an account key merely because those fields are convenient to display.

### 2.2. Custom Profile APIs Differ from OIDC UserInfo

An OAuth provider might return:

~~~json
{
  "id": 456,
  "login": "an.nguyen",
  "display_name": "Nguyen An",
  "email": "an@example.com"
}
~~~

Field names like `id`, `login`, and `display_name` do not belong to any mandatory OAuth 2.0 profile schema. Another provider might return `user_id`, `account`, or nested JSON. Thus Spring Security needs to know **which attribute identifies the principal** via `user-name-attribute` or a custom user service.

Conversely, a compliant OIDC UserInfo response requires a `sub` field to bind against the ID Token; you cannot treat any profile API returning an email as standard OIDC UserInfo.

## 3. How Does OIDC Standardize User Authentication?

OIDC adds the **ID Token**, a JWT containing authentication claims that lets the client verify a login event from a trusted provider. In the Authorization Code flow, the `openid` scope is required; after the client exchanges the code at the token endpoint, a valid OIDC response contains an ID Token alongside the Access Token.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser
    participant C as Spring Boot OIDC Client
    participant OP as OpenID Provider
    U->>C: Access resource requiring login
    C-->>U: Redirect authorization endpoint with scope openid, state, PKCE
    U->>OP: Log in/consent if needed
    OP-->>U: Redirect code + state
    U->>C: Callback code + state
    C->>OP: POST token endpoint (code, PKCE, client auth if needed)
    OP-->>C: Access Token + ID Token (+ Refresh Token if issued)
    Note over C: Verify signature, iss, aud, exp, nonce if present
    opt Need additional profile claims
        C->>OP: GET UserInfo with valid Access Token
        OP-->>C: UserInfo {sub, name, email...}
        Note over C: Check UserInfo.sub = ID Token.sub
    end
    C-->>U: Authenticated OIDC session/principal
~~~

### 3.1. ID Token vs. Access Token

An illustrative decoded ID Token:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "external-subject-6b19",
  "aud": "spring-portal",
  "exp": 1925003600,
  "iat": 1925000000,
  "auth_time": 1924999950,
  "nonce": "RANDOM_NONCE"
}
~~~

| Claim | Meaning in the ID Token |
| --- | --- |
| `iss` | Trusted issuer that issued the ID Token |
| `sub` | Subject identifier of the user scoped to the issuer |
| `aud` | Audience containing the client ID for which the ID Token was issued |
| `exp` | Expiration time of the ID Token |
| `iat` | Issuance timestamp |
| `auth_time` | Time when the user authenticated; used in flows requiring re-authentication |
| `nonce` | Binds the ID Token to the authentication request that sent the nonce, mitigating certain replay attacks |

The client must **validate the ID Token**, not merely Base64URL-decode it. Checks include signature/algorithm, issuer, audience, timestamps, and nonce where applicable. If the ID Token is encrypted, decrypt it per trusted configuration and then run the appropriate verification steps.

**The ID Token is for the OIDC client**, whereas **the Access Token is for resource servers**. Never send an ID Token instead of an Access Token to a business API, even if the ID Token is a validly signed JWT. APIs must check audience, scopes, and policies on the token type they expect.

### 3.2. OIDC UserInfo and Checking `sub`

When a provider publishes a UserInfo endpoint, the client can send an appropriate Access Token to obtain claims:

~~~http
GET /realms/company/protocol/openid-connect/userinfo HTTP/1.1
Host: id.example.com
Authorization: Bearer ACCESS_TOKEN_FOR_USERINFO
~~~

Example response:

~~~json
{
  "sub": "external-subject-6b19",
  "name": "Nguyen An",
  "preferred_username": "an.nguyen",
  "picture": "https://cdn.example.com/avatar/456.png",
  "email": "an@example.com",
  "email_verified": true
}
~~~

The OIDC client **must verify that `sub` in UserInfo matches `sub` in the ID Token** before using any claims. If they do not match, discard the entire UserInfo response. Fields such as `name`, `picture`, or `email` are optional; even when requesting `profile` and `email`, the provider is not required to return all of them.

UserInfo is an **endpoint and profile data source**, not a "third token" issued alongside ID Token/Access Token. An OIDC provider may place profile claims directly inside the ID Token or serve permitted claims only via UserInfo, depending on policy.

### 3.3. Using `iss` + `sub` as the Identity Key

`sub` is the subject identifier within one issuer. Two providers can issue the exact same `sub` string for two different people, and the same person may receive different subjects across clients or sectors depending on how a provider generates *pairwise subjects*.

A suitable internal account table structure:

~~~text
idp_issuer                                  idp_subject              local_user_id
https://id.example.com/realms/company      external-subject-6b19    1207
https://login.partner.example.net          external-subject-6b19    9981
~~~

Never merge two rows just because `sub` matches. Email, phone number, or display name can change and should not be the primary unique key for OIDC account linking.

## 4. When Is a Provider Actually Being Used as OIDC?

**A product claiming "supports OIDC" is not enough to confirm the current login transaction uses OIDC.** Look at the client registration and protocol responses.

| Indicator | Meaning |
| --- | --- |
| Client requests the `openid` scope | Requesting OIDC authentication |
| Provider returns a compliant ID Token from the token endpoint in Authorization Code flow | An OIDC result is present for the client to verify |
| Client verifies the ID Token and creates `OidcUser` | Spring Security is executing OIDC login |
| `issuer-uri` and valid OIDC discovery metadata exist | Client can auto-configure endpoints/keys and issuer |
| Provider returns only an Access Token, no ID Token | Does not qualify as OIDC login |
| Provider's profile API returns `name`/`email` | **Does not prove** the API is compliant OIDC UserInfo |
| Provider returns a JWT Access Token | **Does not prove** an OIDC transaction; a JWT Access Token is not an ID Token |

**An OAuth2 provider that does not support `openid` typically returns an error like `invalid_scope`** when this scope is requested. If an OIDC-capable provider omits the ID Token in response to a valid OIDC request, treat it as a protocol/configuration error to fix; never silently ignore the missing ID Token and downgrade authentication.

OIDC Core describes Authorization Code, Implicit, and Hybrid flows; for modern applications, **Authorization Code + PKCE** is usually the right choice. Do not pick Implicit merely because an ID Token is returned on the front channel. Servlet applications with a backend holding a client secret should still use PKCE when supported by the provider.

## 5. How Spring Security Handles OAuth2 Login and OIDC Login

Spring Security Servlet uses the same `oauth2Login()` DSL to enable login across registered providers, yet the steps after receiving tokens differ:

~~~mermaid
flowchart TD
    A["Browser starts /oauth2/authorization/{registrationId}"] --> B["Authorization Code + state (+ PKCE)"]
    B --> C["Exchange code at token endpoint"]
    C --> D{"Does registration have scope openid?"}
    D -->|No| E["OAuth2 Login"]
    E --> F["Access Token -> Provider's User API"]
    F --> G["DefaultOAuth2UserService / custom user service"]
    G --> H["OAuth2User principal"]
    D -->|Yes| I["OIDC Login"]
    I --> J["ID Token validation: iss, aud, signature, exp, nonce..."]
    J --> K["OidcUserService: UserInfo if applicable"]
    K --> L["OidcUser principal"]
    H --> M["OAuth2AuthenticationToken + session"]
    L --> M
~~~

Key component names:

| API | Responsibility |
| --- | --- |
| `ClientRegistration` | Client configuration, grant, scopes, redirect, and provider endpoints |
| `ClientRegistrationRepository` | Looks up registrations by `registrationId` |
| `OAuth2LoginAuthenticationFilter` | Handles the Authorization Code callback and produces the login result |
| `OAuth2LoginAuthenticationProvider` | Handles non-OIDC OAuth2 login |
| `OidcAuthorizationCodeAuthenticationProvider` | Handles OIDC Authorization Code authentication and ID Token validation |
| `DefaultOAuth2UserService` | Calls an OAuth2 provider's UserInfo-like API to load `OAuth2User` |
| `OidcUserService` | Builds the OIDC principal, optionally fetching UserInfo when applicable |
| `OAuth2User` | Principal contract for OAuth2 Login |
| `OidcUser` | OIDC principal with ID Token and optional UserInfo; extends `OAuth2User` |
| `OAuth2AuthorizedClient` | Client granted an Access Token, optionally accompanied by a Refresh Token |

The provider/user service classes can be configured or replaced; the table describes the standard path in Spring Security Servlet. **There is no need to branch on protocol manually by inspecting JWT responses** when using `oauth2Login()` with properly configured client registrations.

### 5.1. Spring Boot Dependencies and `SecurityFilterChain`

In a Spring Boot **Servlet** application, you need Spring MVC and the OAuth2 Client starter matching your Boot version. Example common Boot 3 starter names:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

With Spring Boot 4, use the corresponding starter names `spring-boot-starter-webmvc` and `spring-boot-starter-security-oauth2-client` per Boot 4's BOM. Do not manually mix Spring Security branches/versions when using Boot dependency management.

One `SecurityFilterChain` for both registrations:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

`oauth2Login()` handles redirecting the browser to the provider and processing callbacks; `oauth2Client()` supports obtaining and using authorized clients to call downstream APIs. Depending on requirements, you can customize the login page, user service, success/failure handlers, or authorized client manager.

## 6. Configuring a Pure OAuth 2.0 Provider in `application.yml`

Suppose a provider only offers OAuth2 authorization/token endpoints and a profile API returning an `id` attribute. There is no ID Token, OIDC issuer, or standard UserInfo schema.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          external-oauth:
            provider: external-provider
            client-id: ${EXTERNAL_OAUTH_CLIENT_ID}
            client-secret: ${EXTERNAL_OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - read_profile
        provider:
          external-provider:
            authorization-uri: https://auth.example.net/oauth/authorize
            token-uri: https://auth.example.net/oauth/token
            user-info-uri: https://api.example.net/account
            user-info-authentication-method: header
            user-name-attribute: id
~~~

URLs, scopes, auth method, and the `id` attribute in the example **must be replaced according to the real provider's documentation**. Spring Security has no single shared `user-info-uri` across all OAuth2 providers. For providers requiring special profile API handling (different headers, nested JSON, follow-up requests, custom mapping), a custom `OAuth2UserService` may be needed.

In the configuration above:

- `registration.external-oauth` creates a registration ID triggered via `/oauth2/authorization/external-oauth`.
- `provider: external-provider` points to the provider's URIs; it is unrelated to `client-id`.
- `authorization-uri` is where the browser goes to obtain a code; `token-uri` is where the backend exchanges the code.
- `user-info-uri` is the API called to retrieve user details once an Access Token is obtained.
- `user-name-attribute: id` tells Spring Security to use the `id` field of the JSON response to identify the principal.
- **No `openid`** is present; Spring Security performs **OAuth2 Login** and does not require an ID Token.

Example profile API:

~~~http
GET /account HTTP/1.1
Host: api.example.net
Authorization: Bearer ACCESS_TOKEN_FROM_EXTERNAL_PROVIDER
~~~

~~~json
{
  "id": 456,
  "login": "an.nguyen",
  "display_name": "Nguyen An"
}
~~~

If the profile API requires a special `Accept` header, nested response structure, or non-standard OAuth 2.0 token delivery instead of a Bearer header, consult the provider docs and customize the user service. Never add `openid` to `scope` just to force ID Token issuance when the provider does not support it.

### 6.1. When to Use `CommonOAuth2Provider`?

Spring Security supports several popular providers via `CommonOAuth2Provider` or built-in preset configurations. Using a registration ID matching a supported provider lets Spring Boot populate many default endpoints.

Example traditional OAuth2 Login with a GitHub OAuth App:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          github:
            client-id: ${GITHUB_CLIENT_ID}
            client-secret: ${GITHUB_CLIENT_SECRET}
            scope:
              - read:user
              - user:email
~~~

This example illustrates an OAuth2 login provider: **do not assume an ID Token exists merely because a provider offers other OIDC-related products**. A provider may implement OIDC for another purpose (such as workload identity) while its user-facing OAuth login flow does not issue OIDC ID Tokens.

Built-in URIs, default scopes, and supported provider presets in Spring Security depend on version. When your organization's provider has no built-in defaults, declare endpoints explicitly per the official contract.

## 7. Configuring an OIDC-Supporting Provider with `issuer-uri`

For an OIDC provider with discovery metadata, you normally do not need to copy individual authorization, token, JWKS, and UserInfo URLs. Example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-oidc:
            provider: company-provider
            client-id: ${COMPANY_OIDC_CLIENT_ID}
            client-secret: ${COMPANY_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-provider:
            issuer-uri: https://id.example.com/realms/company
~~~

`issuer-uri` is the issuer identifier. When the provider publishes standard discovery metadata, Spring Security/Spring Boot can find:

~~~json
{
  "issuer": "https://id.example.com/realms/company",
  "authorization_endpoint": "https://id.example.com/realms/company/protocol/openid-connect/auth",
  "token_endpoint": "https://id.example.com/realms/company/protocol/openid-connect/token",
  "jwks_uri": "https://id.example.com/realms/company/protocol/openid-connect/certs",
  "userinfo_endpoint": "https://id.example.com/realms/company/protocol/openid-connect/userinfo"
}
~~~

This is **illustrative metadata**, not data from a live provider. Real metadata also includes many fields such as supported response types, signing algorithms, and client authentication methods.

The benefit of discovery is reducing repetitive configuration and giving Spring Security the exact issuer/JWKS to verify ID Tokens. Some providers do not publish discovery or expose non-standard metadata; in that case, configure endpoints explicitly or provide a custom `ClientRegistration` while still enforcing OIDC constraints. **Never treat an arbitrary URL as a trusted issuer.**

### 7.1. OIDC Scopes

| Scope | Meaning |
| --- | --- |
| `openid` | Mandatory to request OIDC |
| `profile` | Requests standard profile claims, such as name or picture, per provider policy |
| `email` | Requests `email` and `email_verified` if supplied by provider |
| `phone` | Requests phone number claims, if supported |
| `address` | Requests address claims, if supported |
| `offline_access` | May relate to requesting a Refresh Token per OIDC/provider policy |
| Custom API scopes like `tasks.read` | Requests permission to call business APIs, defined by provider/resource server |

`profile` or `email` does not guarantee those claims will definitely appear. `openid` does not grant permission to call arbitrary APIs. `offline_access` also does not automatically guarantee a Refresh Token; issuance still depends on grant, client, and provider policy.

### 7.2. OIDC Provider Endpoints

| Endpoint | Purpose | Discoverable? |
| --- | --- | --- |
| Authorization endpoint | Browser login and consent | Usually yes |
| Token endpoint | Code exchange, refresh, supported grants | Usually yes |
| JWKS endpoint | Fetch public keys to verify JWT/ID Token signatures | Usually yes |
| UserInfo endpoint | Fetch additional user claims using an Access Token | If provided by provider |
| End-session/logout endpoint | Supports federated logout per extension | If published and supported by provider |

Do not assume every discovered endpoint is automatically used by Spring Security. For example, **OIDC RP-Initiated Logout** requires configuring an appropriate logout handler; UserInfo is called according to user service policy, not necessarily on every HTTP request.

## 8. An Application Supporting Both OAuth2 and OIDC Providers

Spring Boot can hold multiple registrations simultaneously. For example, an application with two login options:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp-oidc
            client-id: ${CORP_CLIENT_ID}
            client-secret: ${CORP_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          community:
            provider: community-oauth
            client-id: ${COMMUNITY_CLIENT_ID}
            client-secret: ${COMMUNITY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [read_profile]

        provider:
          corp-oidc:
            issuer-uri: https://id.example.com/realms/company
          community-oauth:
            authorization-uri: https://auth.example.net/oauth/authorize
            token-uri: https://auth.example.net/oauth/token
            user-info-uri: https://api.example.net/account
            user-info-authentication-method: header
            user-name-attribute: id
~~~

Here:

- `/oauth2/authorization/corp` initiates OIDC login with `openid`.
- `/oauth2/authorization/community` initiates pure OAuth2 Login.
- Default callbacks are `/login/oauth2/code/corp` or `/login/oauth2/code/community`.
- Both share the same Servlet `SecurityFilterChain` unless configuration requires splitting them.
- Spring Security creates either `OidcUser` or `OAuth2User` respectively; never force every request to expect `OidcUser`.

A login UI can present two clear options, while deciding which accounts from which provider may access which features still requires dedicated application policy.

### 8.1. Reading the Principal Without Unsafe Casting

Example controller returning minimal public info and distinguishing OIDC from OAuth2:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public Map<String, Object> currentUser(Authentication authentication) {
        if (!(authentication instanceof OAuth2AuthenticationToken oauthLogin)) {
            throw new IllegalStateException("Endpoint only for OAuth2/OIDC login");
        }

        OAuth2User principal = oauthLogin.getPrincipal();
        Map<String, Object> response = new LinkedHashMap<>();
        response.put("registrationId", oauthLogin.getAuthorizedClientRegistrationId());
        response.put("principalName", principal.getName());

        if (principal instanceof OidcUser oidcUser) {
            response.put("loginProtocol", "OIDC");
            response.put("issuer", oidcUser.getIdToken().getIssuer().toString());
            response.put("subject", oidcUser.getSubject());
        } else {
            response.put("loginProtocol", "OAuth2");
            response.put("providerUserName", principal.getName());
        }
        return response;
    }
}
~~~

This example uses Java pattern matching for `instanceof`. In a real application, `/me` should require authentication via the security chain, handle errors with proper responses, and return only permitted fields. Never return raw `principal.getAttributes()`, Access Tokens, ID Tokens, or Refresh Tokens to the browser.

`getAuthorizedClientRegistrationId()` identifies **which registration** was used, which is helpful when mapping internal accounts. In pure OAuth2 Login, `principal.getName()` reads the field defined by `user-name-attribute` or a custom user service; it has no global equivalence to OIDC `sub`.

### 8.2. Designing Internal Account Keys for Multiple Providers

A system supporting login from multiple providers should store external identities with a namespace:

| Provider type | External key to use | Example |
| --- | --- | --- |
| OIDC | `(issuer, sub)` | `(https://id.example.com/realms/company, external-subject-6b19)` |
| Pure OAuth2 | `(provider/registration namespace, stable provider user ID)` | `(community-oauth, 456)` |

With pure OAuth2, use a stable ID field **per provider documentation**, not a display name. A registration's client ID might vary across environments; choosing the namespace should rely on the actual identity source and data policy rather than an unstable UI label.

**Never automatically merge accounts merely because two providers return the same email.** Account linking should be an explicit workflow that verifies ownership with consent and protections against account takeover.

## 9. When Do You Need to Customize `OAuth2UserService` or `OidcUserService`?

Different providers can return claims in custom schemas or require special HTTP requests. Spring Security lets you configure user services:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.userinfo.DefaultOAuth2UserService;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuthLoginServicesConfig {

    @Bean
    SecurityFilterChain loginFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .userInfoEndpoint(userInfo -> userInfo
                    .userService(new DefaultOAuth2UserService())
                    .oidcUserService(new OidcUserService())))
            .build();
    }
}
~~~

The example above only shows the DSL extension points; the two passed-in services are the defaults, so you do not need to declare them if you are not customizing them. When a provider requires custom logic, implement `OAuth2UserService<OAuth2UserRequest, OAuth2User>` for OAuth2 or `OAuth2UserService<OidcUserRequest, OidcUser>` for OIDC.

Cases worth considering a custom service:

1. An OAuth2 provider returns nested JSON or an identifier field that cannot be mapped with `user-name-attribute`.
2. A provider requires special headers, extra parameters, or supplementary profile APIs.
3. The application needs to map claims to an internal profile, application roles, or normalized display names.
4. An OIDC provider returns claims in UserInfo and the application needs custom processing or policy enforcement before creating the principal.

**Never use a custom service to skip ID Token validation, ignore `state`, skip UserInfo `sub` checks, or turn an Access Token into an ID Token.** If a provider claims to be OIDC yet violates required standards, fix the configuration/integration with the provider rather than disabling security checks.

## 10. Tokens and Permission Scopes with Multiple Providers

After OAuth2 or OIDC Login, Spring Security stores the OAuth2 authorized client for the corresponding registration/principal. An `OAuth2AuthorizedClient` holds an Access Token and optionally a Refresh Token. When calling APIs, use the token belonging to the right provider and the right resource server.

~~~text
OAuth2 / OIDC Login
    -> ClientRegistration (registrationId + provider endpoints)
    -> OAuth2AuthorizedClient (Access Token, optionally Refresh Token)
    -> Resource Server the token was issued for
~~~

An Access Token from `corp` is not automatically accepted by `community`, and vice versa. Even under the same issuer, an Access Token used to call UserInfo may lack the audience/scopes of a business API.

| Need | Component to use |
| --- | --- |
| Verify user identity from an OIDC provider | ID Token validated by the OIDC client |
| Fetch additional OIDC profile details | UserInfo endpoint with a provider-accepted Access Token |
| Fetch pure OAuth2 provider profile | Custom profile API with an Access Token per provider contract |
| Call business APIs | Access Token with matching audience/scopes for the API |
| Obtain a new token | Refresh Token if issued and valid, or a supported grant |
| Log out of application session | Spring Security logout/session policy |
| Simultaneously log out of the OIDC provider | OIDC logout mechanism supported by provider and configured separately |

When an API returns `401`, investigate expired tokens, audience, issuer, signature, or token verification setup. When it returns `403`, inspect scopes, roles, and resource policies. "OIDC login succeeded" only means the client verified identity under that flow; it does not guarantee the Access Token can call every API.

## 11. Common Mistakes When Classifying and Configuring Providers

| Symptom | Likely cause | How to resolve |
| --- | --- | --- |
| OAuth2 provider returns `invalid_scope` when adding `openid` | Provider does not support OIDC for this flow/client | Remove OIDC request or use a provider that genuinely supports OIDC |
| OIDC login fails due to missing `id_token` | Transaction requested OIDC, but token endpoint did not return a valid ID Token | Check `openid`, client registration, token endpoint, and provider OIDC support |
| Spring fails to build OIDC registration | Wrong `issuer-uri`, discovery metadata, TLS, or network issue | Cross-check official issuer and discovery metadata |
| `invalid_redirect_uri` or `redirect_uri_mismatch` | Callback URI not registered or altered through a proxy | Match scheme/host/port/path; check forwarded headers and trusted proxies |
| OAuth2 Login receives Access Token, yet fails to load profile | Wrong `user-info-uri`, missing scope, or user service cannot parse response | Check provider profile API and `user-name-attribute` |
| OAuth2 Login fails with `Missing attribute 'id'` or similar | JSON lacks the field chosen as principal name | Use an actual stable field or custom mapping |
| ID Token rejected due to issuer/audience | Wrong tenant, client ID, or token from another registration | Check `iss`, `aud`, issuer config, and registration |
| UserInfo lacks email | Optional claim not granted by scope/consent/policy | Handle nulls; display only provided data |
| UserInfo `sub` differs from ID Token `sub` | Mixed tokens/requests across users or providers | Reject response; inspect token source and session |
| OAuth login has email, yet app creates duplicate accounts | Using unstable email as account key | Use provider namespace + stable ID; manage account linking |
| Principal is not `OidcUser` as code expects | Pure OAuth2 flow or registration missing `openid` | Check protocol and handle `OAuth2User` appropriately |
| Another API returns `401/403` despite successful login | Access Token not intended for that API or missing scope | Request token for right resource/scope; check resource server config |
| Web logout leaves IdP SSO active | App logout is not provider logout | Design OIDC logout or SSO session handling per requirements |

### 11.1. Distinguishing Dependency Errors from Provider Errors

If Java cannot import `OAuth2User` or `OidcUser`, or no OAuth2 Client bean exists, that is likely a missing dependency/module or wrong Spring Security version. If the application starts, redirects the browser to the IdP, and then fails with `invalid_scope`, `invalid_client`, or token/claim errors, inspect **provider configuration and protocol** before swapping starters.

### 11.2. Do Not "Fix" ID Token Errors by Disabling Checks

If an OIDC ID Token is rejected for issuer, audience, signature, or expiration, skipping validation destroys OIDC's authentication foundation. Fix the issuer URI, client registration, clock skew/sync, metadata/JWKS, or provider contract. Likewise, UserInfo with a mismatched `sub` must be rejected—never ignore it just because emails look identical.

## 12. Criteria for Choosing a Provider for a Product

Before integrating a provider, the development team should identify its exact requirements:

| Requirement | Appropriate choice |
| --- | --- |
| Centralized enterprise login with standardized identity claims | Prefer an OIDC provider supporting Authorization Code + PKCE |
| Only requesting permission to call external APIs | Pure OAuth 2.0 may suffice; OIDC is unnecessary |
| Login with a provider offering only OAuth2 and a custom account API | Integrate `oauth2Login()`; design identity mapping and account for custom provider behavior |
| Need to unify multiple IdPs/SSOs and manage login sessions | OIDC is usually advantageous thanks to `iss`/`sub`, ID Tokens, and standard metadata |
| Service-to-service without users | OAuth2 Client Credentials; do not treat as OIDC user login |
| Need to display user profile | OIDC UserInfo or provider-specific profile API, depending on provider type |
| Need to call application APIs with specific permissions | Access Token with matching scopes/audience, regardless of OAuth2 or OIDC login |

**A "feature-rich" provider does not mean the application should enable every scope and endpoint.** Choose the minimal flow and scopes needed for functionality, especially for user profile data.

## 13. Security Principles Applying to Both Types of Providers

1. **HTTPS in production:** protect browser redirects, token endpoints, UserInfo, and profile APIs. Never disable TLS certificate validation.
2. **Register exact Redirect URIs:** the authorization server only redirects to permitted URIs; the client validates `state` bound to the transaction.
3. **Prefer Authorization Code + PKCE:** even for confidential server-side web clients when supported by the provider; do not use Implicit or password grants for new logins.
4. **Protect client credentials:** secrets stay only on the backend/secret manager; public clients never embed secrets in browser/mobile code.
5. **Trust only configured providers:** never take an arbitrary issuer/endpoint from user input for discovery or sending codes/tokens; prevent SSRF and authorization server mix-ups.
6. **Never log credentials:** authorization codes, Access Tokens, ID Tokens, Refresh Tokens, and client secrets must never appear in URLs/logs/analytics.
7. **Authorize at the application:** login provider scopes do not automatically become admin roles; verify roles/ownership/policies inside your own system.
8. **Validate the right token type:** ID Token for OIDC login; Access Token for APIs; UserInfo and profile APIs only supplement claims after proper authentication.
9. **Never merge accounts by email:** use stable per-provider identity keys and secure account-linking flows.
10. **Manage sessions and refresh:** lifecycles of HTTP sessions, Access Tokens, Refresh Tokens, and provider SSO sessions differ; handle expiration, revocation, and logout explicitly.

## 14. Practice Scenarios

### Scenario A — Logging In with a Pure OAuth2 Provider

The provider returns an Access Token and exposes `/account` returning `id=456` and `login=an.nguyen`, with no ID Token.

**Integration approach:** `oauth2Login()` with `authorization-uri`, `token-uri`, `user-info-uri`, and `user-name-attribute: id`. Principal is `OAuth2User`. When linking internal accounts, store the provider namespace together with stable ID `456`, not just email.

### Scenario B — Logging In with an OIDC Provider

The provider publishes issuer, discovery metadata, and JWKS; the token endpoint returns an Access Token and ID Token when `scope` includes `openid`.

**Integration approach:** registration has `openid` and provider has `issuer-uri`. Spring Security OIDC login validates the ID Token; the application uses the `iss` + `sub` pair to identify the account. If UserInfo is needed, use a valid Access Token and match `sub`.

### Scenario C — Provider Issues a JWT Access Token Without an ID Token

**Conclusion:** a JWT Access Token does not turn the provider into OIDC for this transaction. Never decode a JWT Access Token to fabricate OIDC Authentication. If the product requires standard OIDC authentication, use a provider/flow that issues valid ID Tokens.

### Scenario D — Same Provider, Two Registrations

An application has a `corp-web` registration with `openid` for users, and `corp-service` using Client Credentials to call APIs.

**Conclusion:** both share the same authorization server yet have **different grants and subjects**. `corp-web` can produce an OIDC principal; `corp-service` obtains an Access Token on behalf of the service and has no user-login ID Token.

### Scenario E — UserInfo Returns a Mismatched Subject

The ID Token has `sub=employee-123`; UserInfo returns `sub=employee-999` while the email matches.

**Conclusion:** reject the UserInfo response. Email cannot replace subject binding and does not prove the two subjects are the same person.

### Scenario F — OIDC Login Succeeds, Yet API Returns 403

The ID Token was verified; the Access Token only has `openid profile` while the API requires `tasks.read`.

**Conclusion:** successful login only attests identity. Request the right scope/consent, ensure the proper audience, and satisfy the API's policies; never use an ID Token in place of an Access Token.

## 15. References

- **Spring Security — OAuth2 Login (Servlet):** https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- **Spring Security — OAuth2 Client (Servlet):** https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- **Spring Security — OAuth2 Login Core Configuration:** https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- **Spring Security — ClientRegistration and ProviderDetails:** https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- **OpenID Connect Core 1.0:** https://openid.net/specs/openid-connect-core-1_0.html
- **OpenID Connect Discovery 1.0:** https://openid.net/specs/openid-connect-discovery-1_0.html
- **OAuth 2.0 Authorization Framework (RFC 6749):** https://www.rfc-editor.org/rfc/rfc6749
- **Proof Key for Code Exchange (RFC 7636):** https://www.rfc-editor.org/rfc/rfc7636

## 16. Remember

~~~text
Pure OAuth 2.0 provider
  Authorization Code -> Access Token -> provider-specific profile API
  -> OAuth2User (per provider's custom identity contract)

OIDC provider, with openid scope
  Authorization Code -> Access Token + ID Token
  -> Verify ID Token (iss, aud, signature, exp, nonce...)
  -> Optional UserInfo, verify sub
  -> OidcUser (identity key: issuer + subject)

Both types:
  Access Token with right resource/audience/scope -> call API
  Business permissions -> resource server / application policy
~~~

In Spring Security, the same `oauth2Login()` can work with both **pure OAuth2 providers** and **OIDC providers**, yet the purpose and trustworthiness of the login data differ. **OAuth 2.0 provides an authorization mechanism; OIDC adds user authentication evidence with an ID Token and standardized `iss` + `sub` identifiers.** Configuring the right provider type, scopes, endpoints, and user service forms the foundation for secure login and proper token usage.
