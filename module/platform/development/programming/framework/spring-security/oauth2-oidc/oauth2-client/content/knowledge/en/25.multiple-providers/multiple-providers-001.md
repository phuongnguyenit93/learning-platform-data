# 25.1. Configuring Multiple Registrations for OAuth 2.0 and OIDC

## Lesson Objectives

In **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, an application may need to support multiple identity providers, multiple OAuth clients, or different grants simultaneously. For example, **Partner Portal** needs employee login via a Corporate OP, partner login via a Partner OP, support for a legacy OAuth2-only provider that only has a UserInfo API, and at the same time obtain a service token to call the Reporting API.

Spring Security represents each client configuration with a **`ClientRegistration`**. A registration is tied to a `registrationId`, can point to a provider, and contains the client ID/secret, grant type, redirect URI, scopes, and other required details.

The key principle is: **multiple registrations do not mean users are automatically linked across OPs, nor does an access token from one registration permit calling another registration's API**.

After this lesson, you will be able to:

1. Distinguish between `registrationId`, provider ID, issuer URI, Authorization Server, and Resource Server.
2. Configure multiple OIDC registrations in `application.yml` using `provider` and `issuer-uri`.
3. Combine OIDC Login, OAuth2-only Login, and `client_credentials` in a single Spring Boot application.
4. Understand the default login initiation URL and callback URL by registration ID.
5. Look up `ClientRegistrationRepository` and identify the provider of an `OAuth2AuthenticationToken`.
6. Build a provider selection login page without exposing arbitrary URLs/issuers to users.
7. Distinguish `OidcUser` and `OAuth2User` based on how the user logged in.
8. Design account linking based on the `iss` + `sub` pair, without automatically merging users due to matching emails.
9. Manage separate `OAuth2AuthorizedClient` instances per registration/principal.
10. Use tokens with the proper audience/scope, without sending one provider's token to another API.
11. Protect state, PKCE, nonce, issuer validation, and callbacks against provider mix-up.
12. Handle logout, account switching, reverse proxies, multi-environment setups, and per-provider testing.

## 1. The Problem: One Portal, Multiple Providers

A company builds **Partner Portal** with four integrations:

- **Corporate OP:** employees log in via OIDC.
- **Partner OP:** partners log in via a different OIDC issuer.
- **Legacy OAuth2 Provider:** uses Authorization Code + UserInfo to identify users; does not support OIDC yet.
- **Reporting Authorization Server:** issues access tokens via `client_credentials` for a scheduled job.

Diagram:

~~~mermaid
flowchart LR
    U["Browser user"] --> P["Partner Portal / Spring Security"]
    P --> C["Corporate OIDC OP"]
    P --> R["Partner OIDC OP"]
    P --> L["Legacy OAuth2 AS"]
    P --> S["Reporting AS"]
    P --> API1["Orders API"]
    P --> API2["Reporting API"]
~~~

The portal has the following registration IDs:

~~~text
corporate-login
partner-login
legacy-oauth-login
reporting-service
~~~

The first three registrations serve **interactive login**. `reporting-service` serves **service identity**, with no browser login.

An application can configure all registrations under the same `spring.security.oauth2.client` tree.

## 2. Registration, Provider, and Issuer Are Different

### 2.1. `ClientRegistration`

A `ClientRegistration` describes **an OAuth client registered with an AS**. It can contain:

~~~text
registrationId
clientId
clientSecret
clientAuthenticationMethod
authorizationGrantType
redirectUri
scopes
providerDetails
clientName
~~~

Example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
~~~

`corporate-login` is **a key chosen by the application**, not the ID token issuer.

### 2.2. Provider configuration

`provider` describes the endpoints and metadata of the Authorization Server/OpenID Provider:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          corporate-op:
            issuer-uri: https://login.company.example/realms/employees
~~~

`corporate-op` is the local key of the provider config. `issuer-uri` is the actual issuer published by the OP/AS and is part of the trust boundary.

### 2.3. Linking a registration to a provider

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            provider: corporate-op
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          corporate-op:
            issuer-uri: https://login.company.example/realms/employees
~~~

The `provider: corporate-op` field connects the registration to the configured provider.

### 2.4. Comparison table

| Concept | Example | Role |
|---|---|---|
| Registration ID | `corporate-login` | Key for looking up the OAuth client in Spring |
| Provider ID | `corporate-op` | Key for provider configuration in Spring Boot |
| Client ID | `partner-portal-web` | Identity of the OAuth client at the AS |
| Issuer URI | `https://login.company.example/realms/employees` | Identity of the AS/OP used when validating tokens |
| Authorization endpoint | `.../authorize` | Starts the Authorization Code flow |
| Token endpoint | `.../token` | Exchanges code, refresh token, or client credentials for tokens |
| UserInfo endpoint | `.../userinfo` | Retrieves user information per contract |
| JWKS URI | `.../certs` | Fetches public keys for JWT validation |
| Resource Server | `Orders API` | API that accepts the access token |

Do not use registration ID, provider ID, and issuer as interchangeable names.

## 3. Complete Example: Two OIDC Registrations

A basic `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            provider: corporate-op
            client-id: ${CORPORATE_OIDC_CLIENT_ID}
            client-secret: ${CORPORATE_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

          partner-login:
            provider: partner-op
            client-id: ${PARTNER_OIDC_CLIENT_ID}
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

        provider:
          corporate-op:
            issuer-uri: https://login.company.example/realms/employees

          partner-op:
            issuer-uri: https://identity.partner.example/realms/partners
~~~

The domains and client names in the example are fictional. Real deployments must use the issuer, client ID, secret, and redirect URI registered and verified at each OP.

### 3.1. Registration IDs must be unique

The two registrations have distinct keys:

~~~text
corporate-login
partner-login
~~~

If duplicate YAML keys are used or a property overrides another, one of the registrations may be lost or receive the wrong configuration.

### 3.2. Same URI template, different actual callbacks

Both use:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

but the actual URLs are:

~~~text
https://portal.example.com/login/oauth2/code/corporate-login
https://portal.example.com/login/oauth2/code/partner-login
~~~

Corporate OP should only be configured with the `corporate-login` callback; similarly, Partner OP with `partner-login`. Each OP must accept the exact URI sent by the application.

### 3.3. The `openid` scope

OIDC Login requires requesting `openid` and a provider that genuinely supports OIDC. The `profile` and `email` scopes can request additional claims, though the OP decides what data is released.

If the provider does not support OIDC, adding `openid` to the scope list does not magically produce a valid ID token.

### 3.4. Secrets and client authentication

In the example, both registrations are confidential clients using `client_secret_basic`. Each OP can issue its own client secret.

If using a public client or another client authentication method such as `private_key_jwt`, configure it according to the provider's policy. Do not attempt to reuse the Corporate OP secret or client ID at the Partner OP.

## 4. OIDC Discovery with `issuer-uri`

When a valid issuer URI is configured, Spring Security can fetch the OP/AS metadata to determine:

- `authorization_endpoint`.
- `token_endpoint`.
- `jwks_uri`.
- `userinfo_endpoint` if published.
- Issuer and other supported capabilities.

Example:

~~~text
Corporate issuer:
  https://login.company.example/realms/employees

Partner issuer:
  https://identity.partner.example/realms/partners
~~~

Each provider has its own issuer and its own metadata.

### 4.1. Discovery does not replace OAuth client registration

Metadata helps locate endpoints and capabilities. It **does not automatically create a client ID/secret or register a callback** at the OP.

The portal still needs to be configured as an OAuth client at both Corporate OP and Partner OP.

### 4.2. ID token must have the expected issuer

An OIDC ID token contains the `iss` claim. A token received from Corporate OP must be verified against the issuer of the Corporate registration. Do not accept a Partner OP ID token as a Corporate identity merely because its JWT signature belongs to some valid key.

### 4.3. Do not perform discovery on user-supplied URLs

An endpoint like:

~~~text
/login?issuer=https://arbitrary.example.net
~~~

must not cause the backend to create a registration, call a metadata endpoint, and trust an arbitrary issuer. That can lead to SSRF or logging in through an AS not approved by the system.

Only accept registration IDs from the server-managed list.

### 4.4. When a provider does not support discovery

Endpoints can be configured manually:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          manual-provider:
            authorization-uri: https://auth.example.net/oauth2/authorize
            token-uri: https://auth.example.net/oauth2/token
            user-info-uri: https://api.example.net/me
            user-name-attribute: id
~~~

URLs must follow the actual provider's documentation; do not guess endpoints by appending strings to an issuer when the provider does not publish metadata.

## 5. OAuth2-only Login: No `OidcUser`

A legacy provider only supports OAuth2 Authorization Code, has a UserInfo API, and does not issue ID tokens.

Configuration:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-oauth-login:
            provider: legacy-oauth
            client-id: ${LEGACY_OAUTH_CLIENT_ID}
            client-secret: ${LEGACY_OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read

        provider:
          legacy-oauth:
            authorization-uri: https://auth.legacy.example/oauth/authorize
            token-uri: https://auth.legacy.example/oauth/token
            user-info-uri: https://api.legacy.example/me
            user-name-attribute: id
~~~

Here:

- `openid` is not used.
- There is no OIDC ID token.
- OAuth2 Login can use the UserInfo API to fetch attributes.
- The principal is typically `OAuth2User`, not `OidcUser`.
- `user-name-attribute: id` must match the actual field returned by the API.
- Trust in profile data must be based on the provider's contract and authentication policy.

### 5.1. OAuth2 is not synonymous with OIDC

OAuth 2.0 is an authorization framework. OIDC adds an End-User authentication layer, ID tokens, and issuer/nonce/subject rules.

If you need user identification with OIDC guarantees, prefer an OP that genuinely supports OIDC rather than assembling an unstandardized UserInfo mechanism.

### 5.2. Do not assume email is an immutable ID

The legacy API might return:

~~~json
{
  "id": "legacy-123",
  "email": "alice@example.com",
  "name": "Alice"
}
~~~

`id` can serve as a stable provider user ID if the contract confirms it; email may change or be unverified.

Do not automatically link a local account solely based on email from an OAuth2-only provider.

## 6. `client_credentials` Is a Registration for a Different Purpose

A backend job may need an access token to call the Reporting API without an interactive user.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: reporting-as
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read

        provider:
          reporting-as:
            token-uri: https://auth.reporting.example/oauth2/token
~~~

With `client_credentials`:

- The token represents the client/service, not an End-User.
- There is no browser login.
- Usually no redirect URI, nonce, ID token, or `openid` scope is needed.
- The AS must permit the client to use this grant.
- The token needs an audience/scope suitable for the Reporting API.

**Do not display `reporting-service` as a login button.**

### 6.1. Use the right manager for background services

In a Servlet application, `AuthorizedClientServiceOAuth2AuthorizedClientManager` is suitable for tasks without an `HttpServletRequest`/`HttpServletResponse`.

Do not rely on a web authorization manager that requires a request context when a scheduled job runs outside an HTTP request.

## 7. Combined YAML File with Four Registrations

All of them can reside in the same configuration tree:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            provider: corporate-op
            client-id: ${CORPORATE_OIDC_CLIENT_ID}
            client-secret: ${CORPORATE_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

          partner-login:
            provider: partner-op
            client-id: ${PARTNER_OIDC_CLIENT_ID}
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email

          legacy-oauth-login:
            provider: legacy-oauth
            client-id: ${LEGACY_OAUTH_CLIENT_ID}
            client-secret: ${LEGACY_OAUTH_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile.read

          reporting-service:
            provider: reporting-as
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read

        provider:
          corporate-op:
            issuer-uri: https://login.company.example/realms/employees

          partner-op:
            issuer-uri: https://identity.partner.example/realms/partners

          legacy-oauth:
            authorization-uri: https://auth.legacy.example/oauth/authorize
            token-uri: https://auth.legacy.example/oauth/token
            user-info-uri: https://api.legacy.example/me
            user-name-attribute: id

          reporting-as:
            token-uri: https://auth.reporting.example/oauth2/token
~~~

This is an illustrative example, not a configuration that can be used directly with a public provider. Real values must be provided by the AS and the deployment environment.

### 7.1. Multiple registrations can share the same provider

For example, one Corporate OP has two clients:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-login:
            provider: corporate-op
            client-id: ${CORPORATE_LOGIN_CLIENT_ID}
            client-secret: ${CORPORATE_LOGIN_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile

          corporate-orders:
            provider: corporate-op
            client-id: ${CORPORATE_ORDERS_CLIENT_ID}
            client-secret: ${CORPORATE_ORDERS_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - orders.read

        provider:
          corporate-op:
            issuer-uri: https://login.company.example/realms/employees
~~~

These two registrations:

- Share the same issuer.
- Have different registration IDs.
- Can have separate client IDs/secrets.
- Have separate scopes and authorized client records.
- Require separate callback URIs if both use Authorization Code.
- Do not automatically share tokens just because the issuer is the same.

Without a real need, avoid creating multiple registrations just to change scopes without evaluating consent and incremental authorization policy.

## 8. Login Initiation URL by `registrationId`

With Spring Security Servlet's default configuration:

~~~text
/oauth2/authorization/{registrationId}
~~~

Examples:

~~~text
/oauth2/authorization/corporate-login
/oauth2/authorization/partner-login
/oauth2/authorization/legacy-oauth-login
~~~

Spring Security selects the `ClientRegistration` and builds the Authorization Request with the matching client ID, authorization endpoint, scopes, redirect URI, state, and corresponding protection parameters.

### 8.1. Partner Login flow diagram

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant P as Portal Spring Security
    participant R as ClientRegistrationRepository
    participant OP as Partner OP
    U->>B: Select Partner Login
    B->>P: GET /oauth2/authorization/partner-login
    P->>R: findByRegistrationId(partner-login)
    R-->>P: Partner ClientRegistration
    P-->>B: 302 to Partner OP authorization endpoint
    B->>OP: Authorization Request
    OP-->>B: 302 callback with code + state
    B->>P: /login/oauth2/code/partner-login
    P->>OP: Token request with authorization code
    OP-->>P: Token response
    Note over P: Verify OIDC ID token and create Authentication
    P-->>B: Authenticated session
~~~

### 8.2. Login initiation differs from callback

~~~text
/oauth2/authorization/partner-login
/login/oauth2/code/partner-login
~~~

- The first URL initiates the request and stores correlation state.
- The second URL receives the Authorization Response, exchanges the code for tokens, and completes login.

Do not invoke the callback directly with an arbitrary code to bypass state verification.

### 8.3. Each OP's callback must be registered

Corporate OP:

~~~text
https://portal.example.com/login/oauth2/code/corporate-login
~~~

Partner OP:

~~~text
https://portal.example.com/login/oauth2/code/partner-login
~~~

If an OP has not registered the callback or the URI does not match, the Authorization Server may reject the request before token exchange.

## 9. Spring Security Servlet Configuration

A single `SecurityFilterChain` can serve multiple login registrations:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class PortalSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/", "/login", "/css/**", "/error")
                        .permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

`oauth2Login()` handles browser Authorization Code/OIDC Login, while `oauth2Client()` supports using authorized clients for outbound API calls.

### 9.1. No need for one chain per provider

You do not need three `SecurityFilterChain` beans just because you have Corporate, Partner, and Legacy providers. Spring Security looks up the registration by ID.

Separate chains are only needed when the application has distinct security boundaries, such as web session login and API Resource Server bearer tokens on different endpoint groups.

### 9.2. Default login page

Under appropriate configuration conditions, Spring Security can generate a default login page with links for OAuth2 client registrations.

However, do not assume every dynamic repository or every grant type will be rendered as intended by business requirements. With multiple providers, a self-managed provider selection page is usually clearer.

## 10. Custom Provider Selection Page

A login page might display:

~~~text
Sign in to Partner Portal

[Corporate Account]
[Partner Account]
[Legacy Account]
~~~

The links:

~~~html
<a href="/oauth2/authorization/corporate-login">
  Corporate Account
</a>
<a href="/oauth2/authorization/partner-login">
  Partner Account
</a>
<a href="/oauth2/authorization/legacy-oauth-login">
  Legacy Account
</a>
~~~

Do not display `reporting-service` because it is not a browser login.

### 10.1. Configuring a custom login page

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http)
        throws Exception {

    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/login", "/css/**", "/error")
                    .permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2.loginPage("/login"))
            .oauth2Client(Customizer.withDefaults())
            .build();
}
~~~

When setting `loginPage("/login")`, the application must implement the `GET /login` view/endpoint itself.

### 10.2. Controller rendering the login page

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class LoginPageController {

    @GetMapping("/login")
    String login() {
        return "login";
    }
}
~~~

This assumes the application has a view template named `login`. This lesson only illustrates the logic and does not create template files.

### 10.3. Only display registrations allowed for login

Do not display every key in `ClientRegistrationRepository` without filtering by purpose. A registration using `client_credentials` or an extension grant meant only for the backend will not have a browser flow.

A fixed allowlist can be used:

~~~java
private static final Set<String> LOGIN_REGISTRATIONS =
        Set.of("corporate-login", "partner-login",
               "legacy-oauth-login");
~~~

This is only an illustrative list; the application must still verify valid permissions/configuration.

### 10.4. Do not accept browser-selected issuer URLs

An interface like:

~~~text
/login?providerUrl=https://random.example.net
~~~

where the backend runs discovery against an arbitrary URL risks SSRF and issuer injection. Only allow the browser to choose registration IDs defined from trusted configuration.

## 11. `ClientRegistrationRepository`

Spring Security uses:

~~~java
org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository
~~~

Core method:

~~~java
ClientRegistration findByRegistrationId(String registrationId);
~~~

Spring Boot can create an `InMemoryClientRegistrationRepository` from properties if the application does not define another repository bean.

### 11.1. Looking up a registration

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.stereotype.Service;

@Service
public class RegistrationLookupService {

    private final ClientRegistrationRepository repository;

    public RegistrationLookupService(
            ClientRegistrationRepository repository) {
        this.repository = repository;
    }

    public ClientRegistration required(String registrationId) {
        ClientRegistration registration =
                repository.findByRegistrationId(registrationId);

        if (registration == null) {
            throw new IllegalArgumentException(
                    "Unknown OAuth2 registration");
        }

        return registration;
    }
}
~~~

Being able to look up a registration **does not mean the caller is allowed to use that registration**. For dynamic APIs, you must check the permitted use case and corresponding principal.

### 11.2. Distinguishing repositories

| Repository/service | Data |
|---|---|
| `ClientRegistrationRepository` | Client ID, secret, grant, provider metadata |
| `OAuth2AuthorizedClientRepository` | Access/refresh tokens for registration/principal in a web context |
| `OAuth2AuthorizedClientService` | Authorized clients by registration/principal outside a request |
| `OAuth2AuthorizationRequestRepository` | Authorization Request/correlation awaiting callback |

Do not fetch a `ClientRegistration` and treat it as already holding Alice's tokens. It is the client configuration, not the authorized client.

## 12. Determining Which Registration Was Used to Log In

In a Servlet app, `OAuth2AuthenticationToken` provides:

~~~java
authentication.getAuthorizedClientRegistrationId();
~~~

Example:

~~~java
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LoginProviderController {

    @GetMapping("/me/provider")
    ProviderInfo provider(
            OAuth2AuthenticationToken authentication) {

        return new ProviderInfo(
                authentication.getAuthorizedClientRegistrationId(),
                authentication.getName());
    }

    record ProviderInfo(
            String registrationId,
            String principalName) {}
}
~~~

If the user logged in with Partner OP, the response might be:

~~~json
{
  "registrationId": "partner-login",
  "principalName": "partner-user-123"
}
~~~

The actual principal name value depends on the OIDC subject or the provider-specific user-name attribute.

### 12.1. Do not use registration ID as a role

`registrationId=corporate-login` does not automatically imply `ROLE_ADMIN`. The provider authenticates the user; the application must have authority mapping policies and business authorization checks.

### 12.2. Initial login URL does not prove the user is authenticated

A user may visit `/oauth2/authorization/partner-login` without completing the flow. Only trust the `Authentication` constructed by Spring Security after a successful callback/token validation.

## 13. Distinguishing `OidcUser` and `OAuth2User`

With OIDC Login, the principal is usually `OidcUser`. With OAuth2-only Login, the principal is usually `OAuth2User`.

### 13.1. Handling both principal types uniformly

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityTypeController {

    @GetMapping("/me/identity-type")
    String identityType(
            @AuthenticationPrincipal OAuth2User principal) {

        if (principal instanceof OidcUser) {
            return "OIDC";
        }

        return "OAUTH2";
    }
}
~~~

This snippet only illustrates principal types; a real endpoint needs authentication and valid principal handling.

### 13.2. Do not cast every principal to OIDC

A pattern like:

~~~java
OidcUser user = (OidcUser) authentication.getPrincipal();
~~~

can fail when logging in via a legacy OAuth2 provider without an ID token.

Branch based on the principal type or map into an internal identity model.

## 14. Multi-provider Account Linking

Configuring multiple OIDC OPs is one thing. **Linking the identities of the same person** is another.

Suppose:

~~~text
Corporate OP:
  iss = https://login.company.example/realms/employees
  sub = 12345
  email = alex@example.com

Partner OP:
  iss = https://identity.partner.example/realms/partners
  sub = 12345
  email = alex@example.com
~~~

Two different `iss`/`sub` pairs can represent **two different people**.

### 14.1. `sub` is only unique within an issuer

Do not use `sub=12345` alone as a global identifier key. Treat the pair as:

~~~text
(issuer, subject)
~~~

### 14.2. Extracting issuer and subject from an OIDC ID token

~~~java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public record ExternalIdentityKey(
        String issuer,
        String subject) {

    public static ExternalIdentityKey from(OidcUser user) {
        return new ExternalIdentityKey(
                user.getIdToken().getIssuer().toString(),
                user.getIdToken().getSubject());
    }
}
~~~

Data in the ID token must be verified by Spring Security before being used as an identity.

### 14.3. Email is not a default account linking key

Emails can change, be unverified, or be reassigned to someone else. Do not merge two external identities automatically just because their emails match.

If account linking is needed, there must be a flow verifying that the user controls both identities, with consent/audit per policy.

### 14.4. Custom mapping schema

~~~sql
CREATE TABLE external_identity (
    id              BIGSERIAL PRIMARY KEY,
    local_user_id   BIGINT NOT NULL,
    issuer          VARCHAR(500) NOT NULL,
    subject         VARCHAR(500) NOT NULL,
    registration_id VARCHAR(100) NOT NULL,
    linked_at       TIMESTAMPTZ NOT NULL,
    UNIQUE (issuer, subject)
);
~~~

This is an illustrative application schema, not a schema pre-built by Spring Security.

### 14.5. Pairwise subject identifiers

Some OPs use pairwise `sub` values to limit correlation across clients/sectors. Do not assume two registrations on the same OP always see the same subject if pairwise policies differ.

## 15. Managing Authorized Clients per Registration

A principal can have these authorized clients:

~~~text
alice
  corporate-login  -> A1/R1
  corporate-orders -> A2/R2
  partner-api      -> B1/S1
~~~

The access token of `corporate-login` does not automatically substitute for `corporate-orders` or `partner-api`.

### 15.1. Looking up an authorized client by registration

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

public class AuthorizedClientLookup {

    private final OAuth2AuthorizedClientRepository repository;

    public AuthorizedClientLookup(
            OAuth2AuthorizedClientRepository repository) {
        this.repository = repository;
    }

    public OAuth2AuthorizedClient lookup(
            String registrationId,
            Authentication authentication,
            HttpServletRequest request) {

        return repository.loadAuthorizedClient(
                registrationId,
                authentication,
                request);
    }
}
~~~

`registrationId` must be tied to a server-permitted use case; do not let callers choose it arbitrarily to read tokens from another integration.

### 15.2. `@RegisteredOAuth2AuthorizedClient`

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersClientStatusController {

    @GetMapping("/orders/token-status")
    TokenStatus status(
            @RegisteredOAuth2AuthorizedClient("corporate-orders")
            OAuth2AuthorizedClient client) {

        if (client == null) {
            return new TokenStatus(false, null);
        }

        return new TokenStatus(
                client.getAccessToken() != null,
                client.getClientRegistration().getRegistrationId());
    }

    record TokenStatus(boolean hasAccessToken, String registrationId) {}
}
~~~

Do not return the raw access token in the response.

### 15.3. Partner login does not automatically grant a Corporate token

~~~text
User logs in via partner-login
  -> Portal has Partner Authentication
  -> does not automatically create corporate-orders authorized client
~~~

If the Orders API requires a token from Corporate AS, an appropriate token issuance/authorization flow is required. Do not use a Partner ID token to call the Corporate API.

## 16. `OAuth2AuthorizedClientManager` in a Multi-registration Environment

The manager uses the registration ID and principal to load/save the authorized client; providers in the chain handle the corresponding grants.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class MultiClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .clientCredentials()
                        .build();

        DefaultOAuth2AuthorizedClientManager manager =
                new DefaultOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

This is an example of configuring the manager for Servlet HTTP requests; depending on the project, Spring Boot may already provide a suitable default manager, so creating a new bean is not always necessary.

### 16.1. Separate refresh tokens per provider

If the Corporate authorized client has A1/R1 and the Partner authorized client has B1/S1, refreshing Corporate must use R1 at the Corporate token endpoint, not Partner's S1.

Do not store the "current refresh token" in a shared global variable.

### 16.2. Separate background manager

A job using `reporting-service` with `client_credentials` should use `AuthorizedClientServiceOAuth2AuthorizedClientManager` and an appropriate service store, without depending on a browser request/session.

### 16.3. Registration selection can impact security

An endpoint that accepts both `registrationId` and a target URL from the user and then attaches the corresponding token risks becoming a credential-bearing proxy. Whitelist registrations per feature and restrict the HTTP client's host/audience.

## 17. Right Access Token for the Right Resource Server

Multiple providers do not mean all access tokens are interchangeable.

| Resource Server | Valid token source | Notes |
|---|---|---|
| Corporate Profile API | Token issued by Corporate AS matching audience/scope | Do not use Partner token |
| Partner Orders API | Token issued by Partner AS per contract | Do not use ID token |
| Reporting API | `reporting-service` client credentials token | Service identity |
| Payments API | Token intended for Payments audience | May require another grant/client |

The Resource Server must verify issuer, audience, expiry, scope/authority, and business permissions.

### 17.1. Successful login does not automatically grant other API permissions

Corporate OIDC Login proves a user was authenticated by the OP. It does not prove the user has `orders.approve` or can view every order.

### 17.2. Token Exchange must be permitted by the AS

If business logic needs to exchange a token for a downstream API, consider Token Exchange when supported by the AS. Do not send a Partner AS token to Corporate AS just because both use OAuth 2.0.

### 17.3. Restrict hosts when attaching Bearer tokens

If `RestClient`/`WebClient` attaches access tokens automatically, separate dedicated clients per API. Do not pass browser-supplied URLs into a bearer-token-bearing client or automatically follow cross-host redirects without a policy.

## 18. State, PKCE, Nonce, and Mix-up Prevention

Each Authorization Code/OIDC transaction needs separate correlation:

~~~text
Corporate flow:
  registrationId = corporate-login
  state = state-C
  nonce = nonce-C
  PKCE verifier = verifier-C (if used)

Partner flow:
  registrationId = partner-login
  state = state-P
  nonce = nonce-P
  PKCE verifier = verifier-P (if used)
~~~

Do not share a static `state`/nonce/code_verifier variable across browser sessions or registration flows.

### 18.1. State correlation

`state` protects correlation between the authorization request and response. Do not skip state validation when writing a custom callback handler.

### 18.2. PKCE

PKCE protects the authorization code with a code challenge/verifier. How it applies depends on the client type, Spring Security version, and OP policy. Do not reuse a code verifier across requests.

### 18.3. OIDC nonce

The OIDC nonce (when applicable) binds the authentication transaction to the ID token. The ID token must still have its issuer, audience, signature, timestamps, and other claims verified per profile.

### 18.4. Provider mix-up

A dangerous scenario:

~~~text
Portal initiates Corporate flow
  -> Browser receives authorization response from Partner
  -> Custom callback mistakenly handles it as Corporate
~~~

This can cause sending a code to the wrong token endpoint or accepting an identity result with the wrong issuer.

Protect against it by:

- Binding `registrationId` to the saved authorization request.
- State correlation.
- Separate callback URIs per registration.
- Issuer validation.
- Not taking the token endpoint/issuer from an untrusted callback request.
- Preferring the standard filter flow instead of a custom callback handler lacking checks.
- Using issuer identification in the authorization response if the protocol/profile supports it and it is configured appropriately.

**Separate callback paths do not replace cryptographic validation.**

## 19. Switching Providers in the Same Browser

Alice logs in with Corporate, then selects Partner Login in the same browser. The application might replace the current `Authentication`, yet old authorized clients may not necessarily be cleared from every storage location.

### 19.1. Account switching rules are required

- Determine whether the user logged out or is actively linking accounts.
- Verify issuer/subject from the new login.
- Do not automatically merge local accounts without verification.
- Clean up authorized clients that are no longer applicable.
- Ensure principal A's tokens are never used in principal B's requests.
- Audit provider-switching events if required.

### 19.2. OP session differs from Portal session

Portal logout does not automatically terminate the Corporate OP SSO session or Partner OP SSO session. The two OPs have separate cookies, policies, and logout endpoints.

### 19.3. Avoiding previous user's tokens

If Bob logs into a session that previously belonged to Alice, a custom store must not return Alice's token just because the registration ID matches. Storage keys must consider principal, issuer/tenant, and policy.

## 20. Reverse Proxies and Redirect URIs

The portal may run behind a load balancer:

~~~text
External URL:
  https://portal.example.com

Internal URL:
  http://portal-service:8080
~~~

If the application computes `{baseUrl}` from the internal host, the redirect URI sent to the OP may be wrong:

~~~text
http://portal-service:8080/login/oauth2/code/partner-login
~~~

instead of:

~~~text
https://portal.example.com/login/oauth2/code/partner-login
~~~

### 20.1. Symptoms

- OP reports a redirect URI mismatch.
- Callback returns to HTTP or an internal hostname.
- One provider succeeds while another fails because each OP registers different URIs.
- Session/cookies are not sent by the browser as expected.

### 20.2. Resolution

- Register the exact external HTTPS redirect URI at each OP.
- Configure forwarded headers and trusted reverse proxies.
- Do not trust `X-Forwarded-Host` controlled by external clients.
- Check allowed hosts/TLS.
- Fixed redirect URIs via secure deployment configuration can be used when needed.
- Do not open broad wildcard redirect URIs at the AS as a "quick fix".

## 21. Multiple Environments: dev/staging/prod

A project has:

~~~text
application.yml
application-dev.yml
application-staging.yml
application-prod.yml
~~~

Client IDs/secrets, issuers, or callback domains may differ across environments.

### 21.1. Do not use production secrets in dev

Register separate clients for the development environment. Do not commit secrets to source control.

### 21.2. Configure issuers via trusted deployment config

Environment variables managed by the deployment system can be used, but never allow users to alter the issuer themselves.

### 21.3. Each OP needs environment-appropriate callbacks

Corporate/Partner OPs must have callbacks registered for dev, staging, and production if those environments are active. Do not assume callbacks across environments are equivalent.

## 22. Custom Claim Mapping and Roles

Corporate OP may return `groups`, Partner OP may return `roles`, and Legacy OAuth2 may return another JSON profile.

Example:

~~~json
{
  "sub": "corporate-123",
  "groups": ["staff", "finance"]
}
~~~

And:

~~~json
{
  "sub": "partner-456",
  "roles": ["viewer"]
}
~~~

Do not automatically map every `admin` claim from every issuer to `ROLE_ADMIN`. Explicit trust and authority mapping rules are needed per issuer.

### 22.1. User identity differs from business permissions

Valid authentication does not mean the user can access every API resource. The Backend/Resource Server must also check owner, tenant, scopes, and internal roles.

### 22.2. Do not log full claims

ID tokens/UserInfo may contain personal data. Log metadata such as registration ID, issuer reference, and correlation ID when needed; do not dump raw tokens or all claims.

## 23. Logout with Multiple OPs

Local logout in the Portal and RP-Initiated Logout at each OP are distinct flows.

### 23.1. Local session logout

The application can clear the `SecurityContext`/invalidate the session. This does not automatically revoke refresh tokens at the Authorization Server.

### 23.2. OP End Session

If Corporate OP and Partner OP support OIDC logout, each has its own end-session endpoint. Do not use Partner's endpoint to log out a Corporate identity.

### 23.3. `id_token_hint`

If a provider requires/permits `id_token_hint`, use the matching ID token for that issuer/client/session; do not send provider A's ID token to provider B.

### 23.4. Authorized client storage outside the session

A database-backed `OAuth2AuthorizedClientService` may still hold token records after browser logout. Separate cleanup rules are needed if business requirements demand disconnecting a provider or terminating API access.

## 24. Reactive/WebFlux

The multi-registration concepts remain the same in WebFlux, but the security/repository classes are reactive.

### 24.1. SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactivePortalSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(auth -> auth
                        .pathMatchers("/", "/login", "/error").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

### 24.2. Corresponding reactive APIs

~~~text
ReactiveClientRegistrationRepository
ServerOAuth2AuthorizedClientRepository
ReactiveOAuth2AuthorizedClientService
ReactiveOAuth2AuthorizedClientManager
WebClient
~~~

Do not use Servlet's `HttpSessionOAuth2AuthorizedClientRepository` when handling a `ServerWebExchange`.

### 24.3. Same isolation rules

WebFlux does not automatically solve issuer A being confused with issuer B, email collisions, or wrong-audience tokens. Registration selection, ID token validation, account linking, and storage isolation are still required.

## 25. Testing Multiple Registrations

A YAML file with no syntax errors does not prove two OIDC OPs and an OAuth2-only provider all work. Each registration must be tested individually.

### 25.1. Configuration matrix

| Test | Expectation |
|---|---|
| Lookup `corporate-login` | Returns the correct Corporate ClientRegistration |
| Lookup `partner-login` | Returns the correct Partner ClientRegistration |
| Lookup `legacy-oauth-login` | Has correct UserInfo mapping |
| Lookup `reporting-service` | Grant type is client_credentials |
| Unknown registration | Not found |
| Corporate issuer | Matches Corporate OP metadata |
| Partner issuer | Matches Partner OP metadata |
| Two registrations on same provider | Do not mix client ID/redirect/scope |
| Callback per provider | Points to the registered external HTTPS URL |

### 25.2. Repository unit test

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@SpringBootTest
class ClientRegistrationsTest {

    @Autowired
    ClientRegistrationRepository repository;

    @Test
    void registersTwoIndependentOidcProviders() {
        var corporate =
                repository.findByRegistrationId("corporate-login");

        var partner =
                repository.findByRegistrationId("partner-login");

        assertThat(corporate).isNotNull();
        assertThat(partner).isNotNull();

        assertThat(corporate.getRegistrationId())
                .isNotEqualTo(partner.getRegistrationId());

        assertThat(corporate.getProviderDetails().getIssuerUri())
                .isNotEqualTo(
                        partner.getProviderDetails().getIssuerUri());
    }
}
~~~

**Note:** `issuer-uri` may trigger discovery during configuration. Use mock metadata/test issuers to avoid uncontrolled unit/integration tests calling a production OP.

### 25.3. Authorization Request tests

For each registration:

1. Access `/oauth2/authorization/{registrationId}`.
2. Verify redirect to the correct authorization endpoint.
3. Confirm client ID.
4. Confirm redirect URI.
5. Confirm scopes.
6. Confirm state correlation.
7. Confirm PKCE/nonce per flow and provider policy.

### 25.4. Negative tests

- Callback with mismatched state.
- Callback path belonging to another provider.
- Incorrect ID token issuer.
- Incorrect ID token audience.
- UserInfo missing `user-name-attribute`.
- Mismatched client secret.
- Redirect URI not registered at the OP.
- Resource Server rejects token with wrong audience.

Do not use real production tokens to test error cases.

### 25.5. Authorized client isolation tests

- Alice logs in with Corporate.
- Bob logs in with Partner.
- Bob cannot read Alice's token.
- Switching providers in the same browser does not use stale tokens.
- Two OPs with the same email or `sub` do not auto-merge.
- `reporting-service` does not appear as an interactive login.
- Service manager obtains tokens for the right Reporting AS.

## 26. Troubleshooting

| Symptom | Common cause | Check |
|---|---|---|
| `ClientRegistration` not found | Wrong registration ID, profile, or YAML | Properties/repository |
| Corporate button opens Partner OP | Login link uses wrong registration | `/oauth2/authorization/{id}` |
| OP reports redirect mismatch | URI not registered or wrong proxy baseUrl | External redirect/callback |
| Token endpoint `invalid_client` | Wrong client ID/secret/auth method | Registration/AS settings |
| ID token issuer mismatch | Wrong provider/issuer | Discovery and `iss` validation |
| Casting `OidcUser` fails | Login came from OAuth2-only provider | Distinguish OidcUser/OAuth2User |
| UserInfo does not create principal | Wrong user-name-attribute | API response contract |
| Two accounts get mixed up | Using email or standalone sub only | Issuer+subject/linking |
| Partner token calling Corporate API returns 401 | Wrong audience/issuer | Resource Server contract |
| API returns 403 | Missing scope/ownership | API authorization |
| User A and user B tokens mix | Insufficient custom repository key | Principal/session isolation |
| Client credentials job gets redirected to login | Wrong web registration/manager used | Service manager |
| Custom login page does not render | Missing GET /login/view implementation | Login page config |
| Portal logged out but OP still has SSO | Local logout differs from OP logout | End-session policy |
| Callback fails only in production | Reverse proxy/forwarded header | External URI and trusted headers |
| Token sent to arbitrary host | HTTP client has no allowlist | Dedicated RestClient/WebClient |

## 27. Common Misconceptions to Avoid

**"Each provider must have its own SecurityFilterChain."**

No. A single `oauth2Login()` can use multiple registrations.

**"Registration ID must equal issuer."**

No. Registration ID is an internal key; issuer is the verified AS/OP identity.

**"One provider can only have one registration."**

No. Multiple registrations can use the same provider.

**"Having `openid` guarantees the provider returns an ID token."**

No. The provider must actually support OIDC.

**"OAuth2 UserInfo is the same as an OIDC ID token."**

No. OIDC defines authentication semantics and separate ID token validation.

**"Logging in to Corporate automatically grants a Partner token."**

No. Authorized clients belong to separate registrations and principals.

**"Same email or same subject means the same user."**

No. `sub` is only unique within an issuer; linking must be verified.

**"Client credentials is a login button."**

No. It is a grant for service identity.

**"Portal logout logs out every OP and revokes every token."**

No. Those lifecycles are separate.

**"Discovery automatically registers the OAuth client at the OP."**

No. Client registration and redirect allowlists must exist at the AS.

## 28. Practical Scenarios

### A. Two OIDC issuers

Portal allows Corporate and Partner logins.

**Handling:** two registrations pointing to two providers/issuers; links and callbacks keyed by registration ID, independent token issuer validation.

### B. Same issuer, multiple client IDs

Corporate OP issues one client for login and another client for the Orders API.

**Handling:** multiple registrations sharing the same provider; authorized clients and callbacks/scopes remain separate.

### C. Legacy OAuth2 UserInfo

Provider does not support OIDC.

**Handling:** configure authorization/token/user-info endpoints and `user-name-attribute`. Handle the `OAuth2User` principal; do not force OIDC.

### D. Scheduled reporting job

Job needs a `client_credentials` token.

**Handling:** use `reporting-service` with a service authorized client manager, without browser login.

### E. Email collision

Two OPs issue the same email.

**Handling:** do not auto-link; use issuer+subject and a verified account linking workflow.

### F. Reverse proxy causes wrong redirect

Portal sends callback URL from an internal hostname.

**Handling:** trusted forwarded headers/external baseUrl, register exact callbacks at each OP, avoid wildcards.

### G. API has a different issuer

Partner login succeeds, but Orders API only trusts Corporate AS.

**Handling:** do not use a Partner token as a Corporate token; design authorization/token issuance appropriate for the Resource Server.

### H. Switching from Alice to Bob

Same browser, old registration/token remains in storage.

**Handling:** enforce session/principal isolation and cleanup; never use Alice's token in Bob's requests.

## 29. Self-Check Questions

**Question 1.** How does a Registration ID differ from a Provider ID?

**Answer:** Registration ID identifies the OAuth client inside the application; Provider ID references the AS/OP configuration.

**Question 2.** Can multiple registrations point to the same provider?

**Answer:** Yes. They can have different client IDs, scopes, or grants.

**Question 3.** Which scope usually indicates an OIDC request?

**Answer:** `openid`, combined with a provider that genuinely supports OIDC.

**Question 4.** What is the default login initiation URL for `partner-login`?

**Answer:** `/oauth2/authorization/partner-login`.

**Question 5.** What form does the default callback usually take?

**Answer:** `/login/oauth2/code/{registrationId}`, matching the redirect URI at the OP.

**Question 6.** Is a separate SecurityFilterChain needed for each OP?

**Answer:** Usually no.

**Question 7.** Which registration should not be displayed as a login button?

**Answer:** `client_credentials` or registrations not intended for browser interaction.

**Question 8.** Does a user logging in via Partner automatically receive a Corporate access token?

**Answer:** No.

**Question 9.** Which API identifies the registration used for login in Servlet?

**Answer:** `OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()`.

**Question 10.** Can every principal be cast to `OidcUser`?

**Answer:** No. OAuth2-only login can produce an `OAuth2User`.

**Question 11.** Why is `iss` + `sub` needed?

**Answer:** Subject is only unique within the scope of an issuer.

**Question 12.** Does a matching email prove it is the same user?

**Answer:** No. Linking must be verified.

**Question 13.** Does discovery issue a client secret for the Portal?

**Answer:** No. The AS needs client registration and credential/callback configuration.

**Question 14.** How should an ID token issuer mismatch be handled?

**Answer:** Check provider/registration/metadata; do not disable issuer validation.

**Question 15.** Does local logout automatically revoke all tokens and end SSO at both OPs?

**Answer:** No.

**Question 16.** Can a Corporate OP token be used to call any Resource Server?

**Answer:** No. It must match the audience/scope and API contract.

**Question 17.** Which registration repository is used with WebFlux?

**Answer:** `ReactiveClientRegistrationRepository`.

**Question 18.** How do you verify multi-provider support actually works?

**Answer:** Test lookup, redirects, state/issuer validation, token exchange, and account/token isolation per registration.

## Key Takeaways

- **A Spring Security application can configure multiple ClientRegistrations** with separate providers/issuers or a shared provider when justified.
- **`registrationId` is not the issuer or provider ID**. Use them in their proper places to avoid selecting the wrong endpoint.
- **OIDC Login requires `openid` and issuer/ID token validation**; OAuth2-only Login requires separate UserInfo/identity mapping.
- **`/oauth2/authorization/{registrationId}` starts login**, while `/login/oauth2/code/{registrationId}` usually receives the callback. Register callbacks accurately at each OP.
- **One SecurityFilterChain is usually sufficient for multiple login providers**; the login page should only display registrations meant for interactive flows.
- **`client_credentials` is for service identity**, not an End-User login button.
- **Tokens across registrations must not be shared indiscriminately**. Access tokens must match the Resource Server audience, scopes, and business permissions.
- **Do not auto-merge identities by email or standalone `sub`**. Use issuer + subject and a secure account linking workflow.
- **Keep state, PKCE, nonce, issuer validation, and correlation separate for each authorization transaction** to avoid provider mix-up.
- **Logout, sessions, and token revocation are separate lifecycles**. Test account switching, token isolation, and reverse-proxy callbacks per provider.
