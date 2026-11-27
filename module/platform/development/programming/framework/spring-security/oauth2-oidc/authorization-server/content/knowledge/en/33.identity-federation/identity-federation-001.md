# Authorization Server Acting Simultaneously as an OAuth2 Client with an External IdP

> **Chapter: Identity Federation.** This lesson belongs to the **SPRING_SECURITY_OIDC_AUTHORIZATION_SERVER** module, covering the design, configuration, security, testing, and operations of an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in Spring Boot. This lesson focuses on the **federated identity** model: an internal Authorization Server uses Spring Security OAuth2 Client to log users in via an external Identity Provider (IdP), and then continues acting as the Authorization Server/OpenID Provider for downstream applications.

## 1. The problem: one server holding two different OAuth roles

In an identity federation system, an internal Authorization Server can act simultaneously as:

- **OAuth2 Client / Relying Party (RP):** redirects the user to an external IdP, receives the authorization response, exchanges the authorization code, and verifies the identity provided by the IdP.
- **OAuth2 Authorization Server / OpenID Provider (OP):** manages internal clients, authenticates and authorizes users according to organizational policy, and issues its own access tokens and ID Tokens to downstream applications.

Running example:

| Component | Illustrative value | Role |
|---|---|---|
| External IdP | `https://identity.partner.example` | Authenticates the user and issues upstream ID Token/access token |
| Internal Authorization Server | `https://login.example.vn` | Acts as an OAuth2 Client to the IdP, and simultaneously as the internal AS/OP |
| Upstream client registration | `corporate-idp` | Client ID registered by the internal AS at the IdP |
| Downstream application | `portal-web` | OAuth2/OIDC client of the internal AS |
| Internal Resource Server | `https://api.example.vn` | Verifies access tokens issued by the internal AS |
| Local user | `local-user-8472` | Internal identity mapped from the upstream account |

Typical flow:

1. The user accesses `portal-web` and initiates login via the internal AS.
2. The internal AS does not have a login session yet, so it redirects the browser to the external IdP.
3. The IdP authenticates the user and returns an authorization code to the internal AS callback.
4. The internal AS exchanges the code for tokens, verifies the OIDC ID Token or fetches UserInfo depending on provider configuration.
5. The application resolves or provisions the local user and links it with the upstream identity.
6. The internal AS completes the local login session.
7. `portal-web` continues the Authorization Code Flow with the internal AS and receives **tokens issued by the internal AS**.

The external IdP authenticates the user for the internal AS. Downstream applications still trust the internal issuer and receive tokens according to internal policy. Identity federation **does not mean** forwarding the IdP's raw access token to every internal API.

## 2. Distinguishing authentication federation from authorization delegation

These two concepts are often conflated:

| Aspect | Authentication federation | Authorization/delegation |
|---|---|---|
| Question | Who is the user according to a trusted IdP? | What is the user/client allowed to do with a resource? |
| Evidence | Verified OIDC ID Token or OAuth2 UserInfo authentication result | Local roles, permissions, scopes, consent, and policy |
| Decision maker | IdP authenticates; internal AS validates and maps identity | Internal AS and Resource Server according to local policy |
| Outcome | Local authenticated principal/session | Local authorization and token claims/scopes |
| Lifecycle | Account linking, upstream session, IdP disablement | Local grant, access/refresh token, consent, revocation |

An external IdP may send claims such as `groups` or `roles`, but the internal AS should not automatically trust and grant all permissions from those claims. An allowlisted mapping policy is required: which group corresponds to which role, which tenant it belongs to, and whether approval is required.

For example, the IdP returning `groups=["finance-admin"]` does not mean the user automatically becomes an admin across all internal tenants. The AS must verify the issuer, subject, tenant context, and authorization policy before using the claim.

## 3. Identity federation flow with two Authorization Servers

~~~mermaid
sequenceDiagram
    autonumber
    participant U as User Browser
    participant RP as portal-web
    participant AS as Local Authorization Server / OP
    participant IDP as External IdP
    participant DB as Local Identity Store
    participant API as Internal Resource Server

    U->>RP: Open application
    RP->>AS: Authorization Request (internal client)
    AS->>AS: No local session
    AS-->>U: Redirect /oauth2/authorization/corporate-idp
    U->>IDP: Authorization Request (Internal AS as OAuth Client)
    IDP->>U: Login / MFA / consent
    U-->>IDP: Authentication succeeds
    IDP-->>U: Redirect callback with authorization code
    U->>AS: /login/oauth2/code/corporate-idp?code=...
    AS->>IDP: Token Request + client authentication
    IDP-->>AS: Upstream ID Token / access token
    AS->>AS: Verify issuer, signature, audience, expiry, nonce
    AS->>DB: Resolve or provision (issuer, sub)
    DB-->>AS: Local user + local authorities
    AS->>AS: Create local authenticated session
    AS-->>U: Continue original Authorization Request
    AS-->>RP: Local authorization code
    RP->>AS: Exchange code at local token endpoint
    AS-->>RP: Local access_token + local id_token
    RP->>API: Call API with local access_token
    API-->>RP: Response per local audience/scope
~~~

In the diagram, there are **two distinct OAuth client relationships**:

- The internal AS is a client of the IdP, with its own client ID issued by the IdP.
- `portal-web` is a client of the internal AS, with its own registration and credentials.

The two registrations do not share a client ID, secret, redirect URI, or authorization grant. Each side has its own issuer, audience, consent, and token lifecycle.

## 4. Registering the internal AS at the external IdP

Before configuring Spring, you need to create an OAuth/OIDC client application at the IdP.

| Attribute | Example | Usage |
|---|---|---|
| Issuer | `https://identity.partner.example` | Discovery and issuer validation |
| Client ID | `local-as-client-123` | Identifies the internal AS at the IdP |
| Client Secret | Secret issued by the IdP | Client authentication at the upstream token endpoint |
| Authorization endpoint | Retrieved from OIDC Discovery | Browser redirect for login |
| Token endpoint | Retrieved from OIDC Discovery | Authorization code exchange |
| JWK Set URI | Retrieved from metadata | Verifying upstream ID Token signatures |
| UserInfo endpoint | Retrieved from metadata | Fetching additional claims if needed |
| Redirect URI | `https://login.example.vn/login/oauth2/code/corporate-idp` | Exact Spring Security callback |

The redirect URI must be registered with an exact match at the IdP. Spring Security uses the default template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

With registration ID `corporate-idp`, the public callback is:

~~~text
https://login.example.vn/login/oauth2/code/corporate-idp
~~~

If the AS runs behind a reverse proxy, forwarded headers and the public base URL must be configured properly so Spring constructs a redirect URI matching the registered URI. Do not use broad wildcards or open redirects to work around URL mismatches.

## 5. Configuring Spring Security OAuth2 Client

Spring Security OAuth2 Client manages upstream IdPs through `ClientRegistration`. Each registration contains the client ID/secret, grant type, redirect URI, scopes, and provider information.

The application needs the `spring-boot-starter-oauth2-client` dependency alongside the Spring Authorization Server dependency currently in use:

~~~gradle
implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
~~~

For an IdP that supports OIDC Discovery, you can configure it using `issuer-uri`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-idp:
            provider: corporate
            client-id: ${CORPORATE_IDP_CLIENT_ID}
            client-secret: ${CORPORATE_IDP_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate:
            issuer-uri: https://identity.partner.example
~~~

Spring Boot/Spring Security can use the issuer to discover the Provider Configuration and retrieve the authorization endpoint, token endpoint, JWK Set URI, UserInfo endpoint, and related metadata. If the provider does not support OIDC Discovery, you must explicitly configure the endpoints and UserInfo mapping.

The client secret must be injected from a secret manager or environment; never commit real values into source code, YAML, or container images.

### 5.1. Providers supporting only OAuth 2.0, without OIDC

Some providers offer an OAuth 2.0 authorization code and a UserInfo API but do not issue an ID Token. In that case, you can explicitly configure the endpoints:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-idp:
            provider: legacy
            client-id: ${LEGACY_IDP_CLIENT_ID}
            client-secret: ${LEGACY_IDP_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - user.read
        provider:
          legacy:
            authorization-uri: https://legacy.example.net/oauth/authorize
            token-uri: https://legacy.example.net/oauth/token
            user-info-uri: https://legacy.example.net/api/me
            user-info-authentication-method: header
            user-name-attribute: id
~~~

In this case, the principal is typically an `OAuth2User` rather than an `OidcUser`. `user-name-attribute` must point to a stable, unique identifier attribute guaranteed by the provider. Do not use display name or email as the account key if the provider has an immutable subject/user ID.

OIDC Discovery and ID Token validation provide a better standardized identity contract. If only OAuth2 UserInfo is available, you must evaluate the provider's reliability, TLS, API contract, uniqueness, and identifier lifecycle.

## 6. Configuring SecurityFilterChain: internal AS and OAuth2 Login

Spring Authorization Server has a filter chain for AS protocol endpoints. Spring Security OAuth2 Login is configured in the application chain so the internal AS can authenticate users via the IdP.

Servlet stack example with Spring Authorization Server 1.5.x:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Configuration(proxyBeanMethods = false)
class FederatedAuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http.securityMatcher(authorizationServer.getEndpointsMatcher())
                .with(authorizationServer, server ->
                        server.oidc(Customizer.withDefaults()))
                .authorizeHttpRequests(authorize ->
                        authorize.anyRequest().authenticated())
                .exceptionHandling(exceptions ->
                        exceptions.defaultAuthenticationEntryPointFor(
                                new LoginUrlAuthenticationEntryPoint(
                                        "/oauth2/authorization/corporate-idp"),
                                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)));

        return http.build();
    }

    @Bean
    FederatedLoginSuccessHandler federatedLoginSuccessHandler(
            ClientRegistrationRepository registrations,
            FederatedIdentityService identities) {
        return new FederatedLoginSuccessHandler(registrations, identities);
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(
            HttpSecurity http,
            FederatedLoginSuccessHandler successHandler) throws Exception {

        http.authorizeHttpRequests(authorize ->
                        authorize.anyRequest().authenticated())
                .oauth2Login(oauth2 ->
                        oauth2.successHandler(successHandler));

        return http.build();
    }
}
~~~

Configuration meaning:

- The first chain handles the OAuth2/OIDC protocol endpoints of the internal AS.
- OIDC is enabled so the internal AS issues ID Tokens and provides Provider Configuration/UserInfo as configured.
- Browser requests to the authorization endpoint requiring user authentication are redirected to `/oauth2/authorization/corporate-idp`.
- The second chain enables `oauth2Login()` so Spring Security performs the authorization code flow with the IdP.
- The success handler is where the application resolves/provisions the local identity after upstream authentication succeeds.

This example selects a fixed IdP. If there are multiple IdPs, you should display a login page for the user to choose a provider or select according to a verified tenant policy. Do not automatically redirect to an IdP based on an arbitrary URL submitted by the user.

Do not globally disable CSRF protection just to handle the callback. Use Spring Security's filter, authorization request repository, and state mechanism; if customizing the callback or session storage, preserve transaction binding and test CSRF.

## 7. Upstream login success: resolve or provision the local user

When Spring Security successfully handles the callback, the application receives a principal from the upstream provider. With OIDC, the principal is typically an `OidcUser` and contains the ID Token verified by Spring Security. This is the appropriate point to look up or create the local identity.

### 7.1. The federation identifier key must be issuer and subject

With OIDC, the external key should be the pair:

~~~text
(external_issuer, external_sub)
~~~

Example:

| External issuer | External subject | Local user |
|---|---|---|
| `https://identity.partner.example` | `00u8x91abc` | `local-user-8472` |
| `https://accounts.vendor.example` | `00u8x91abc` | `local-user-9921` |

Even if both providers return `sub=00u8x91abc`, those are two subjects belonging to two different issuers. Never use `sub` alone as a global key.

OIDC Core defines `sub` as a subject identifier unique within the scope of an issuer and never reassigned to another user. Therefore, the `(iss, sub)` pair is the appropriate key for linking upstream identities. Email, username, display name, and phone number can change, collide, or be recycled.

### 7.2. Just-in-time provisioning

If the local user does not exist yet, the system can create an account on first login (JIT provisioning). The workflow should:

1. Verify that upstream identity authentication succeeded.
2. Obtain the configured/trusted issuer and verified subject.
3. Look up the external identity by the unique key `(issuer, sub)`.
4. If found, load the local user and check enabled/locked/deprovisioned status.
5. If not found, check domain, tenant, invitation, allowlist, or onboarding policy.
6. Create the local user with a local subject that remains immutable throughout its lifecycle.
7. Create the external identity link with a unique constraint to prevent race conditions during concurrent logins.
8. Sync only allowed profile fields; store provenance and update timestamps.

Do not automatically grant administrative privileges just because the IdP returns a group/role. Local authorities must be mapped through a dedicated policy.

### 7.3. Success handler example

The example below handles only OIDC providers configured with issuer discovery. The `FederatedIdentityService` is a business service implemented by the application.

~~~java
import java.io.IOException;

import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;

final class FederatedLoginSuccessHandler
        implements AuthenticationSuccessHandler {

    private final ClientRegistrationRepository registrations;
    private final FederatedIdentityService identities;
    private final AuthenticationSuccessHandler delegate =
            new SavedRequestAwareAuthenticationSuccessHandler();

    FederatedLoginSuccessHandler(
            ClientRegistrationRepository registrations,
            FederatedIdentityService identities) {
        this.registrations = registrations;
        this.identities = identities;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {

        if (!(authentication instanceof OAuth2AuthenticationToken oauth2)
                || !(oauth2.getPrincipal() instanceof OidcUser oidcUser)) {
            throw new ServletException(
                    "This federation handler requires an OIDC provider");
        }

        ClientRegistration registration =
                registrations.findByRegistrationId(
                        oauth2.getAuthorizedClientRegistrationId());

        if (registration == null
                || registration.getProviderDetails().getIssuerUri() == null) {
            throw new ServletException("Trusted OIDC issuer is not configured");
        }

        String issuer = registration.getProviderDetails().getIssuerUri();
        String subject = oidcUser.getSubject();

        // Resolve or provision local identity using the verified (issuer, sub).
        identities.resolveOrProvision(
                issuer, subject, FederatedProfile.from(oidcUser));

        delegate.onAuthenticationSuccess(request, response, authentication);
    }
}
~~~

`FederatedProfile` is an application-defined projection containing only allowlisted profile attributes; do not pass all upstream claims into the local store. The business service must enforce a unique constraint on issuer + subject, handle race conditions, and check local user status. Only accept the issuer from the configured ClientRegistration; never take an arbitrary issuer from request parameters. For non-OIDC OAuth2 providers, use a separate handler relying on a verified immutable provider-specific user ID.

### 7.4. Account linking must require proof of account control

If a user already has a local account and wants to link an additional IdP:

- Require the user to already be logged in locally and re-authenticate when risk is high.
- Start the federation transaction from an authenticated local session, protected by CSRF/state.
- After the callback, verify the issuer + subject pair.
- Display confirmation of the provider/account being linked.
- Enforce a unique constraint so one external identity cannot be linked to two local accounts.
- Audit the actor, provider, protected subject reference, and link/unlink timestamp.

Do not automatically link local accounts by matching email. An email may be unverified, have changed owners, or have been recycled; even a verified email does not replace proof that the user controls the existing local account.

## 8. Mapping upstream claims to local identity and ID Token

The external IdP may return claims such as `name`, `email`, `email_verified`, `groups`, `locale`, and custom attributes. The internal AS must decide which claims are stored in the local profile, which claims are included in the local ID Token, which claims are mapped to local authorities, and which claims must be discarded.

### 8.1. Do not copy all claims from the IdP

Do not perform an unfiltered copy of all upstream claims. Upstream may contain claims colliding with standard names, wrong value types, internal information, or roles incompatible with local policy.

Do not allow upstream to overwrite claims managed by the local OP such as:

- `iss` — issuer of the **internal AS**.
- `sub` — local subject identifier per the internal OP's contract.
- `aud` — downstream client ID.
- `iat`, `exp` — timestamps issued by the local AS.
- `nonce`, `auth_time`, `acr`, `amr` — authentication claims managed by the local OP according to policy.
- `azp`, `at_hash`, `c_hash` — claims determined by the local OIDC flow when applicable.

The upstream ID Token is evidence for the internal AS to verify login; it is not an internal ID Token to be re-issued verbatim.

### 8.2. Local subject differs from external subject

The local OP should maintain a stable local subject. For example:

~~~text
Upstream identity:
  issuer  = https://identity.partner.example
  subject = 00u8x91abc

Local identity:
  local_subject = local-user-8472
~~~

The internal ID Token has `iss=https://login.example.vn` and `sub=local-user-8472`. Downstream RPs only need to know the identity within the internal issuer domain. The internal AS maintains the upstream/local mapping in the identity store.

If business requirements call for pairwise subject identifiers, the local OP can issue distinct subjects per client/sector following a stable, non-reassigned rule managed as part of the OIDC subject policy.

### 8.3. OAuth2TokenCustomizer example

Spring Authorization Server provides `OAuth2TokenCustomizer<JwtEncodingContext>` to customize claims when issuing JWTs. The example below assumes `FederatedIdentityResolver` returns a verified and normalized local identity from the authorization flow principal:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.core.oidc.endpoint.OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> federatedIdTokenCustomizer(
        FederatedIdentityResolver identityResolver) {

    return context -> {
        if (!OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            return;
        }

        FederatedIdentity identity =
                identityResolver.resolve(context.getPrincipal());

        // Local OP owns the subject; never copy upstream "sub".
        context.getClaims().subject(identity.localSubject());

        if (context.getAuthorizedScopes().contains(OidcScopes.PROFILE)) {
            context.getClaims().claim("name", identity.displayName());
            context.getClaims().claim("preferred_username",
                    identity.localUsername());
        }

        if (context.getAuthorizedScopes().contains(OidcScopes.EMAIL)
                && identity.emailVerified()) {
            context.getClaims().claim("email", identity.email());
            context.getClaims().claim("email_verified", true);
        }
    };
}
~~~

This is a customizer skeleton; `FederatedIdentityResolver` and `FederatedIdentity` are application-defined business types. The resolver must map the authenticated principal to the local user; never directly trust email/roles claims from the browser. Only add claims requested/permitted by scope and consent. Do not overwrite other standard claims generated by Spring Authorization Server.

Spring Authorization Server provides dedicated guidance on social login, storing local users, and mapping claims into ID Tokens. Apply allowlisting and local identity mapping aligned with organizational policy.

## 9. Managing upstream tokens and local tokens

In a federation model, two groups of tokens can exist simultaneously:

| Token | Issuer | Audience/consumer | Purpose |
|---|---|---|---|
| Upstream ID Token | External IdP | Internal AS (OAuth2 Client/RP) | Proves authentication from the IdP |
| Upstream access token | External IdP | IdP API/resource | Accesses upstream resources if granted |
| Local ID Token | Internal AS | Downstream OIDC client | Proves the local OP authenticated the local subject |
| Local access token | Internal AS | Internal Resource Server | Accesses internal APIs per local scope/audience |
| Local refresh token | Internal AS | Local token endpoint | Renews local access tokens per policy |

### 9.1. Do not pass upstream access tokens as local access tokens

Do not take an upstream access token and return it directly to `portal-web` or an internal Resource Server expecting it to represent local authorization. Upstream tokens have their own issuer, audience, scope, signing keys, and lifecycle.

The local AS must issue its own tokens after:

1. Authenticating the external identity.
2. Resolving the local user and account status.
3. Identifying the downstream client and authorization request.
4. Applying consent, local roles, tenant, scope, and audience.
5. Issuing the local access token/ID Token under the internal issuer.

Internal Resource Servers trust only configured issuers and keys. Do not add external IdPs to every API's trust list unless an API has a direct use case to accept upstream tokens.

### 9.2. When calling IdP or upstream provider APIs is needed

If the internal AS needs to call upstream APIs on behalf of the user, it can retain the authorized client/token by design using `OAuth2AuthorizedClientService` or `OAuth2AuthorizedClientRepository`. Token storage must include encryption at rest, access control, expiry/revocation handling, and cleanup.

Use `OAuth2AuthorizedClientManager` to manage authorized clients and perform authorized API calls. Do not copy an upstream refresh token into the local refresh token response.

If delegation between two security domains is needed, design a dedicated token exchange or delegation contract specifying the actor, subject, audience, scope, and trust relationship. Token exchange does not happen automatically just because `oauth2Login()` is enabled; it requires support across the issuer, client, and resource server.

## 10. Multiple IdPs, tenants, and mix-up defense

An internal AS can configure multiple IdPs: corporate directory, partner IdP, or social provider. Each IdP must be an independent `ClientRegistration` with its corresponding registration ID, issuer, client credentials, endpoints, and redirect URI.

### 10.1. Do not trust caller-chosen IdPs

If users are allowed to choose a provider, the UI may only submit a registration ID from a configured allowlist. Do not accept arbitrary authorization endpoints, token endpoints, or issuer URLs from query strings. Fetching an arbitrary discovery URL can expose the server to SSRF or send client credentials to an attacker's endpoint.

For multi-tenancy, map the verified tenant to an issuer/provider allowlist. Do not use an unverified email domain to automatically determine the trust domain.

### 10.2. Mix-up attacks when a client interacts with multiple issuers

When an OAuth2 Client can interact with multiple Authorization Servers, mix-up attacks must be prevented. RFC 9700 recommends validating the issuer of the authorization response, such as the `iss` response parameter per RFC 9207 or an equivalent mechanism based on the issuer in the ID Token. Otherwise, distinct redirect URIs per issuer can be used as required by RFC 9700.

With multiple registrations in Spring Security:

- Use a unique registration ID for each provider.
- Register a specific redirect URI per provider, such as `/login/oauth2/code/corporate-idp` and `/login/oauth2/code/partner-idp`.
- Validate each provider's issuer/discovery metadata and only use the token/JWK endpoints of the provider that initiated the transaction.
- Verify that the authorization response belongs to the right registration/issuer; check RFC 9207 support by version and provider.
- Do not write custom callback handlers that bypass Spring Security's state/issuer validation.
- If a provider does not support issuer identification, use distinct redirect URIs and RFC-compliant transaction binding; do not treat the registration name alone as sufficient if the application customizes the flow.

### 10.3. Tenant isolation

Identity federation does not solve tenant isolation on its own. Explicit tenant/local account mappings must be stored:

| Attribute | Rule |
|---|---|
| External issuer | Must belong to the tenant's or trust domain's allowlist |
| External subject | Unique within the issuer; not globally unique |
| Local user ID | Stable internal identifier |
| Tenant membership | Granted according to local policy |
| External groups | Mapped via allowlist/namespace; do not auto-grant global roles |
| Downstream client | Allowed only registered and consented scopes/audiences |

If the same external identity is allowed to belong to multiple tenants, model membership separately and resolve the tenant context in each authorization transaction.

## 11. Logout, unlink, and deprovisioning

Logout in a federated system spans multiple session/token lifecycles:

- Downstream application session.
- Local session at the internal AS.
- SSO session at the external IdP.
- Local refresh/access tokens.
- Upstream authorized client tokens.

A local logout does not automatically log the user out of the IdP. Conversely, ending the IdP session does not guarantee that already-issued local access tokens are immediately invalidated.

### 11.1. Local logout

When a user logs out locally:

1. Terminate the local web session.
2. Remove the upstream authorized client/token if the application no longer needs it.
3. Revoke local refresh tokens/authorizations per policy.
4. Account for already-issued local access tokens and how Resource Servers observe revocation.
5. If using OIDC logout, handle session/client notifications according to dedicated configuration.

### 11.2. Unlinking accounts

Unlinking an external identity must require authentication proof from the local user and ensure a valid login method still remains. Do not allow unlinking the last identity if it would inadvertently lock out the account unless policy allows it.

After unlinking:

- Delete or mark the external identity link inactive.
- Revoke the upstream authorized client if tokens are retained and the provider supports revocation.
- Audit the operation.
- Determine whether the current local session requires re-authentication.
- Do not delete the local account if the user still has data/permissions to retain.

### 11.3. Deprovisioning from the IdP

When an employee is disabled at the IdP, the local AS may not know immediately if it relies solely on local sessions and offline JWTs. Organizations must choose mechanisms: short session TTLs, periodic re-authentication, back-channel events/SCIM or admin synchronization, local account disablement, token revocation, and Resource Server introspection/denylist.

Do not assume that upstream ID Token expiration automatically invalidates already-issued local access tokens.

## 12. Operational security and trust boundaries

### 12.1. Upstream IdP

- Pin the issuer according to approved configuration; verify ID Token signature, issuer, audience, expiry, and nonce per OIDC.
- Fetch Discovery/JWK Set only over HTTPS from trusted issuers.
- Monitor signing key rotation and JWKS caching.
- Use client secret or private key according to the registered method; manage in a secret manager.
- Request only the upstream scopes actually needed.
- Never log authorization codes, access tokens, refresh tokens, ID Tokens, or client secrets.

### 12.2. Local AS

- Maintain a stable internal issuer.
- Never reassign local subjects to another user.
- Check account enabled/locked state and tenant policy on every federated login.
- Enforce local consent, scope, audience, and authorization; never blindly copy upstream permissions.
- Use PKCE S256, transaction-specific state and nonce; exact-match redirect URIs.
- Protect session cookies, CSRF, SameSite, and reverse proxy forwarded headers.
- Do not allow callback or post-login redirects to arbitrary URLs.
- Separate local and upstream logs/audits; redact tokens/PII.

### 12.3. Token storage and authorized clients

If storing upstream authorized client tokens:

- Store only when there is a use case requiring calls to upstream resources.
- Encrypt tokens/refresh tokens at rest and restrict who can decrypt them.
- Associate records with the local principal, registration ID, and tenant.
- Handle token expiry, refresh, revocation, user unlink, and deprovisioning.
- Enforce retention/cleanup and never store raw tokens in metric labels.

### 12.4. Account linking and claim mapping

- Use the issuer + subject pair as the external identity key.
- Email is only a profile attribute, not a default linking key.
- Never auto-link by username/display name.
- Map only allowlisted claims; retain provenance for each attribute.
- Never trust upstream groups/roles without a mapping policy.
- Audit link/unlink/provisioning events and local authority changes.

## 13. Identity federation testing matrix

| # | Scenario | Expected outcome |
|---|---|---|
| 1 | Login with valid OIDC IdP | Spring OAuth2 Login completes and creates local identity/session |
| 2 | IdP issuer outside allowlist | Does not start or rejects federation |
| 3 | Invalid ID Token signature | Authentication fails |
| 4 | Mismatched ID Token issuer | Authentication fails |
| 5 | ID Token audience missing local AS client ID | Authentication fails |
| 6 | Expired ID Token | Authentication fails |
| 7 | Nonce does not match transaction | Authentication fails |
| 8 | Invalid/missing authorization response state | Callback rejected |
| 9 | Authorization code replay | Token exchange fails |
| 10 | Redirect URI differs from URI registered at IdP | IdP rejects or flow aborts |
| 11 | Wrong upstream client secret | Upstream token endpoint rejects |
| 12 | IdP unavailable | Login fails cleanly; does not fall back to another issuer |
| 13 | JWK signing key rotated | Cache/refresh works and verifies with the new key |
| 14 | External issuer + sub already exists | Resolves to the existing local user |
| 15 | Same sub but different issuer | Creates/links separate identity without mixing users |
| 16 | New external identity, valid tenant allowlist | JIT provisioning succeeds per policy |
| 17 | New external identity, disallowed tenant | Provisioning rejected |
| 18 | Two concurrent callbacks for same identity | Unique constraint prevents creating two local links |
| 19 | Email matches local user without account-link proof | Does not auto-link |
| 20 | Email changed at IdP | Local subject stays stable; profile synced per policy |
| 21 | UserInfo lacks stable ID | Rejects or requires reliable provider-specific mapping |
| 22 | Upstream group contains non-allowlisted role | Does not grant local role |
| 23 | Local user disabled while upstream login succeeds | Local AS still rejects authorization |
| 24 | Downstream client logs in after federation | Receives local authorization code and local tokens |
| 25 | Local access token has internal issuer/audience | Internal Resource Server verifies local issuer properly |
| 26 | Upstream access token sent to internal API | Rejected if API does not trust upstream issuer |
| 27 | Local ID Token sent to API | API rejects due to wrong token type/audience |
| 28 | Multi-IdP callback with swapped issuer/registration | Mix-up defense aborts transaction |
| 29 | Provider URL from query string points to unknown host | Does not perform discovery/request (SSRF defense) |
| 30 | Local logout | Local session terminates; upstream session/token handled per separate policy |
| 31 | Unlinking last identity | Blocked if user has no remaining valid login method |
| 32 | IdP deprovisions user | Local disable/re-auth/revocation per SLA |
| 33 | Upstream token refresh fails | Does not corrupt local token; authorized client handled per policy |
| 34 | Logging enabled at gateway/AS | Does not leak codes, ID Tokens, access tokens, refresh tokens, or secrets |
| 35 | Reverse proxy changes host/proto | Public redirect URI remains accurate and untrusted headers are not trusted |

### 13.1. Critical assertions

Integration tests should simultaneously verify:

- Upstream authentication is verified using the correct issuer/JWK/client registration.
- Local identity lookup uses `(issuer, sub)`, not email as a key.
- Local user is checked against enabled/tenant/authority policy.
- Downstream authorization request resumes after local login succeeds.
- Local access token has internal issuer/audience/scope.
- Upstream tokens are not mistakenly returned to downstream clients.
- Internal ID Token has the local subject and allowlisted claims.
- Multi-provider callbacks are not susceptible to mix-up.
- Logout, unlink, and deprovisioning have documented behavior.

## 14. Troubleshooting, production checklist, and self-assessment

| Symptom | Common cause | Resolution |
|---|---|---|
| `/oauth2/authorization/corporate-idp` returns 404 | Missing OAuth2 Client dependency or ClientRegistration | Check starter, registration ID, and auto-configuration |
| Callback returns 404 | Redirect URI does not match filter callback pattern | Check redirect-uri and proxy |
| IdP reports redirect_uri mismatch | Registered URI differs from URI sent by Spring | Align scheme/host/path and exact match |
| invalid_client at upstream token endpoint | Wrong client ID/secret/auth method | Verify credentials and auth method at IdP |
| Discovery fails to load | Wrong issuer, TLS, metadata, or network | Check HTTPS issuer and OIDC metadata |
| ID Token signature fails | Wrong JWK Set URI/key rotation/issuer | Check discovery, kid, and cache |
| Duplicate local users created | Missing unique constraint on (issuer, sub) | Add constraint and handle transaction races |
| Two IdPs with same email merged erroneously | Email used as identity key | Use issuer + subject and account-link flow |
| Local token carries external sub | Missing local subject mapping | Map via local identity resolver before issuing ID Token |
| Downstream API rejects token | Client sent upstream token or ID Token | Use local access token with the right audience |
| User lost access yet still calls API | Local token/JWT still valid | Disable local user, revoke/denylist/introspect per SLA |
| Only one IdP fails | Wrong registration/provider endpoint/secret for that IdP | Inspect individual ClientRegistration and trust config |

### 14.1. Production checklist

- [ ] Internal AS is registered as a separate OAuth2 Client at each upstream IdP.
- [ ] OIDC Discovery is used when supported; issuers are pinned/allowlisted.
- [ ] Redirect URI is exact-matched and reflects the public URL behind any reverse proxy.
- [ ] OAuth2 Login is configured in a dedicated application SecurityFilterChain.
- [ ] Authorization Server chain and OIDC endpoints remain independently configured.
- [ ] State, nonce, PKCE S256, and callback transaction binding are protected.
- [ ] Upstream client secrets/private keys reside in a secret manager.
- [ ] External identities are keyed by (issuer, sub); local subjects remain stable.
- [ ] Account linking requires proof of control over the local account.
- [ ] JIT provisioning validates tenant, invitation, enabled/locked status, and policy.
- [ ] External groups/roles are mapped only through an allowlist.
- [ ] Local ID Token does not blindly copy upstream claims or reserved claims.
- [ ] Local access token has local issuer/audience/scope.
- [ ] Upstream access tokens are not forwarded to downstream APIs outside a delegation contract.
- [ ] Upstream authorized client tokens are stored only when needed, with encryption/retention/cleanup.
- [ ] Multi-IdP mix-up defense and issuer validation are tested.
- [ ] Logout, unlink, and deprovisioning are designed separately.
- [ ] Metrics/audits do not contain tokens, secrets, or unnecessary PII.
- [ ] Tests cover key rotation, IdP outage, duplicate identity, and cross-tenant isolation.

**Self-assessment questions**

1. Why can an Authorization Server simultaneously act as an OAuth2 Client to an IdP and an OP to internal clients?
2. How do the two client registrations in a federation model differ?
3. Why is the upstream ID Token only authentication evidence for the local AS, rather than an internal ID Token to be re-issued?
4. Why should external identities be keyed by (issuer, sub) instead of just sub or email?
5. Which policies must JIT provisioning check before creating a local user?
6. Why can account linking based on matching email lead to account takeover?
7. On which filter chain is oauth2Login() configured when the internal AS uses Spring Authorization Server?
8. How do an OIDC provider and an OAuth2 provider without ID Tokens differ in terms of principal and validation?
9. Why should a local ID Token have a local iss and local sub?
10. When mapping upstream claims, which claims must upstream never be allowed to overwrite?
11. What is the difference between authentication federation and authorization delegation?
12. Why should an upstream access token not be passed to an internal Resource Server as a local access token?
13. When multiple IdPs exist, how does a mix-up attack occur and what defenses are needed?
14. Does local logout automatically terminate the session at the IdP?
15. If the IdP deprovisions a user, how can still-valid local access tokens be handled within SLA?
16. When calling an IdP's API on behalf of a user is required, how should authorized client tokens be managed?

## References

- [Spring Authorization Server 1.5.8 — How-to: Authenticate using Social Login](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-social-login.html): OAuth2 Login, IdP configuration, capturing local users, and mapping claims into ID Tokens.
- [Spring Security — OAuth2 Login Core Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): ClientRegistration, issuer discovery, redirect URI, UserInfo, and OAuth2 Login.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): ClientRegistrationRepository, OAuth2AuthorizedClientService, and authorized client management.
- [Spring Boot — OAuth2 Client Configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html): multiple registrations/providers, issuer-uri, and custom provider endpoints.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, issuer, subject, audience, nonce, and validation.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): Provider Configuration, issuer, and JWK Set metadata.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): PKCE, redirect URI, CSRF, and mix-up attack defense when clients interact with multiple issuers.
- [RFC 9207 — OAuth 2.0 Authorization Server Issuer Identification](https://www.rfc-editor.org/rfc/rfc9207.html): the iss parameter in authorization responses so clients identify the right issuer.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): delegation/token exchange between trust domains; not automatically enabled by OAuth2 Login.
