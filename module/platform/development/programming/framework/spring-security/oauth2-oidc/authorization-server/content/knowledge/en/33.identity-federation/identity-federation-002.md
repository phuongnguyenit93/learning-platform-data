# Integrating OIDC or OAuth2 Login from an Identity Provider

> **Chapter:** Identity Federation  
> **Module:** `SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER`  
> **Module objective:** Learn how to design, configure, secure, test, and operate an OAuth 2.0/OpenID Connect Authorization Server using Spring Security and Spring Authorization Server in a Spring Boot application.  
> **Scope:** Spring Boot 3.x, Spring Security 6.x, and Spring Authorization Server 1.5.x on the Servlet stack. The Authorization Server acts as an OAuth2/OIDC Client (Relying Party) when logging in through an upstream IdP, and can then issue tokens from the internal issuer to downstream clients.

## 1. Context and objectives

An organization may already use an external Identity Provider (IdP) to manage employees, customers, or partners. When building an internal Authorization Server, organizations typically want users to sign in with their existing identities rather than creating another standalone password system.

For example, an enterprise has an IdP at `https://login.corp.example` and an Authorization Server at `https://auth.platform.example`. A user opens the Portal application. Portal redirects the user to the Authorization Server. The Authorization Server directs the browser to the enterprise IdP for authentication. After the IdP authenticates successfully, the Authorization Server receives the result, maps the external identity to an internal account, and creates a local login session. When the Portal client executes the OAuth2 Authorization Code Flow with the internal Authorization Server, the server issues an authorization code, access token, and ID Token under the internal issuer.

In this architecture, the Authorization Server fulfills two roles:

- **Upstream Relying Party (RP):** uses an OAuth2/OIDC Client to log in via an external IdP.
- **Downstream OpenID Provider (OP):** provides OAuth2/OIDC for internal applications and APIs.

Do not confuse tokens issued by the upstream IdP with tokens issued by the internal Authorization Server. The upstream identity is an input to establish the internal principal; downstream tokens are new credentials issued according to the platform's policy, audience, scope, and issuer.

After this lesson, you will be able to:

1. Distinguish OAuth2 Login from OpenID Connect Login and understand the authentication limitations of plain OAuth2.
2. Describe the architecture where the Authorization Server acts as an RP to upstream IdPs and an OP to downstream clients.
3. Configure multiple upstream providers using `ClientRegistration` and provider metadata.
4. Use issuer discovery to obtain authorization endpoints, token endpoints, JWKS, and UserInfo endpoints.
5. Understand Authorization Code Flow, redirect URIs, state, nonce, and PKCE in federated login.
6. Verify ID Tokens and load UserInfo according to OIDC.
7. Build a durable identity mapping using the issuer and subject pair.
8. Provision local accounts, handle account linking, and synchronize attributes.
9. Map groups/roles from the IdP to internal authorities via an allowlist.
10. Maintain boundaries between upstream tokens, the local SecurityContext, and downstream tokens.
11. Test login success/failure, issuer mismatch, account linking, mapping, and logout.

**Core principle:** Use OIDC when federated user authentication is needed. Obtain identity from a trusted issuer, identify the user by the `(iss, sub)` pair, map to an internal principal, and let the Authorization Server issue tokens from its own internal issuer.

## 2. Identity federation architecture

### 2.1. Roles in the system

| Component | Role |
| --- | --- |
| Upstream IdP | Authenticates the End-User and issues ID Token/access token |
| Internal Authorization Server | OAuth2/OIDC Client to the IdP; maps identity and creates local session |
| Downstream RP/client | Logs in using the internal Authorization Server |
| Resource Server | Verifies access tokens issued by the configured issuer |
| Identity link store | Maps external identity to local user |
| User directory | Stores internal accounts, status, tenant, profile, and policy |

### 2.2. Login flow

~~~mermaid
sequenceDiagram
    autonumber
    participant U as End-User Browser
    participant AS as Internal Authorization Server
    participant IDP as Upstream OIDC IdP
    participant DB as Local Identity Store
    participant RP as Downstream Client

    U->>RP: Open application
    RP->>AS: Authorization Request
    AS-->>U: Redirect to upstream IdP
    U->>IDP: Authorization Request + state + nonce
    IDP->>U: Login / MFA / consent
    IDP-->>AS: Redirect callback with authorization code
    AS->>IDP: Token Request
    IDP-->>AS: ID Token + Access Token
    AS->>AS: Validate ID Token
    AS->>DB: Resolve (issuer, subject)
    DB-->>AS: Local user / account link
    AS->>AS: Create Authentication and local SecurityContext
    AS-->>U: Continue original Authorization Request
    AS-->>RP: Internal Authorization Code
    RP->>AS: Token Request
    AS-->>RP: Token issued by internal issuer
~~~

### 2.3. Two distinct authorization flows

There are two separate OAuth2/OIDC transactions:

1. **Upstream login:** The internal Authorization Server is a client of the IdP. This transaction authenticates the End-User and creates a local session.
2. **Downstream authorization:** The Portal application is a client of the internal Authorization Server. This transaction grants tokens according to internal permissions and scopes.

Do not pass the raw upstream authorization code to Portal. Do not use the upstream ID Token as the internal issuer's ID Token. Do not put the upstream access token in the downstream Token Endpoint response as though it were an internal access token.

### 2.4. Identity federation does not mean token federation

Identity federation is trusting an external issuer to identify a user and mapping them to an internal identity. Token federation or token exchange is a separate problem of accepting/transforming credentials and audiences.

In the common model:

- The IdP authenticates the user.
- The internal Authorization Server creates the local principal.
- The Authorization Server applies internal policy and issues new tokens.
- Resource Servers trust only configured issuers/audiences.

If RFC 8693 token exchange is needed or a downstream API must be called with an upstream token, explicitly design the audience, actor, delegation, scope, and token validation. Do not relay tokens arbitrarily.

## 3. OAuth2 Login and OpenID Connect Login

### 3.1. OAuth 2.0 is an authorization framework

OAuth 2.0 defines how a client obtains an access token to access protected resources. OAuth2 itself does not define a standard identity assertion equivalent to an ID Token.

A UserInfo API published by an OAuth2 provider can return a user profile, but the meaning of attributes, identification conventions, and authentication guarantees depend on the provider. Receiving an access token does not by itself prove identity according to a uniform standard.

### 3.2. OpenID Connect adds the authentication layer

OIDC builds on OAuth2 and adds the ID Token. An ID Token is a JWT assertion about an authentication event, containing standard claims such as:

- `iss`: the issuer that issued the token.
- `sub`: a subject unique within the scope of the issuer/sector.
- `aud`: the client or audience the token is intended for.
- `exp`: expiration time.
- `iat`: issuance time.
- `nonce`: binds the ID Token to the authentication request when a nonce was sent.
- `auth_time`: time the user was authenticated, if issued.
- `acr` and `amr`: authentication context/method information if supported by the provider.

With OIDC Login, Spring Security verifies the ID Token and can call the UserInfo Endpoint to retrieve additional claims.

### 3.3. When to use OIDC vs. an OAuth2 provider?

| Need | Choice |
| --- | --- |
| Enterprise login with standard issuer and subject | OIDC |
| Need to verify ID Token, nonce, and authentication claims | OIDC |
| Provider only offers OAuth2 + UserInfo API | OAuth2 Login with custom mapping |
| Only need to call provider APIs on behalf of the user | OAuth2 Client/Authorized Client; does not necessarily require login |
| Provider lacks UserInfo or reliable identity contract | Do not infer user identity from access token; requires controlled custom integration |

If the provider supports OIDC, prefer OIDC instead of decoding an access token yourself to extract a username.

### 3.4. Spring Security supports both

Spring Security OAuth2 Client provides `oauth2Login()` for login integration. For a registration with the `openid` scope, the framework uses the OIDC authentication flow and returns an `OidcUser`. For a non-OIDC OAuth2 provider, the framework uses `OAuth2UserService` and returns an `OAuth2User`.

The two principal types have different APIs. Application code should have an adapter/mapping layer to normalize them into a local principal rather than forcing every upstream provider into the same schema.

## 4. Registering upstream providers

### 4.1. ClientRegistration

`ClientRegistration` describes an OAuth2/OIDC client registration:

| Component | Meaning |
| --- | --- |
| `registrationId` | Local key to distinguish providers |
| `clientId` | Client ID issued by the IdP |
| `clientSecret` | Credential of a confidential client, if any |
| `clientAuthenticationMethod` | How the client authenticates at the Token Endpoint |
| `authorizationGrantType` | Typically Authorization Code |
| `redirectUri` | Application's callback URL |
| `scopes` | Requested scopes; OIDC typically includes openid/profile/email |
| `providerDetails` | Issuer, authorization/token/UserInfo/JWK endpoints |

`registrationId` is a local name, such as `corp` or `partner`. It does not have to equal the issuer URL or client ID.

### 4.2. OIDC Discovery via issuer-uri

If the IdP supports OIDC Discovery, configure `issuer-uri` so Spring Boot/Spring Security discovers metadata:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${CORP_OIDC_CLIENT_ID}
            client-secret: ${CORP_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corp:
            issuer-uri: https://login.corp.example
~~~

The framework uses the provider configuration to retrieve the authorization endpoint, token endpoint, JWKS URI, UserInfo endpoint, and issuer metadata. Discovery must be performed over HTTPS and the issuer must match the configured trusted value.

Never accept an arbitrary issuer from a query parameter or user input. Uncontrolled dynamic issuer discovery can turn the application into an SSRF client or cause the server to trust an attacker-controlled IdP.

### 4.3. Configuring an OAuth2 provider without OIDC Discovery

If a provider only supports OAuth2 and a dedicated UserInfo endpoint, configure the endpoints manually:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-partner:
            provider: legacy-partner
            client-id: ${PARTNER_CLIENT_ID}
            client-secret: ${PARTNER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - profile
              - email
        provider:
          legacy-partner:
            authorization-uri: https://accounts.partner.example/oauth/authorize
            token-uri: https://accounts.partner.example/oauth/token
            user-info-uri: https://accounts.partner.example/api/userinfo
            user-name-attribute: id
            user-info-authentication-method: header
~~~

`user-name-attribute` must point to a stable identifier attribute guaranteed by the provider. Do not use email as a linking key if emails can change or be recycled.

With an OAuth2-only provider, explicitly evaluate how the UserInfo API is protected, which provider owns the token, whether the profile is stable, and how the provider guarantees identifier uniqueness. OAuth2 does not provide a standard issuer/subject identity contract like OIDC.

### 4.4. Redirect URI and environments

A registration's redirect URI typically looks like:

~~~text
https://auth.platform.example/login/oauth2/code/corp
~~~

This URI must be registered at the IdP and match the actual URL. In production:

- Use HTTPS.
- Configure a trusted public base URL behind a reverse proxy.
- Control forwarded headers.
- Do not let an untrusted Host header dictate the callback host.
- Separate client registrations and secrets by environment.
- Do not use localhost or wildcard callbacks in production.

### 4.5. Multiple upstream providers

Multiple providers can be registered simultaneously:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          workforce:
            provider: workforce
            client-id: ${WORKFORCE_CLIENT_ID}
            client-secret: ${WORKFORCE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          customer:
            provider: customer
            client-id: ${CUSTOMER_CLIENT_ID}
            client-secret: ${CUSTOMER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          workforce:
            issuer-uri: https://sso.workforce.example
          customer:
            issuer-uri: https://identity.customer.example
~~~

Corresponding login initiation can use `/oauth2/authorization/workforce` and `/oauth2/authorization/customer`. Each registration requires its own issuer mapping, local tenant, and account-link policy.
## 5. Enabling OAuth2 Login in the Authorization Server application

### 5.1. Authorization Server and application login are two filter chains

Spring Authorization Server handles OAuth2/OIDC endpoints such as authorization, token, JWK Set, and OIDC Provider Configuration. User login to the Authorization Server itself is typically handled by a separate Spring Security application filter chain.

The application needs the OAuth2 Client dependency, for example in Gradle:

~~~kotlin
implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
~~~

This dependency provides `ClientRegistration`, OAuth2 Login filters, token clients, and UserServices. It complements the application's Spring Authorization Server dependency.

Example two-chain configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, as ->
                as.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated());

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is a skeleton configuration. The Authorization Server also needs a RegisteredClientRepository, OAuth2AuthorizationService, AuthorizationServerSettings, a JWK source, and a user directory. The application chain is responsible for redirecting to the upstream IdP and establishing the local Authentication after the callback.

### 5.2. Spring Security OAuth2 Client endpoints

For registration ID `corp`, Spring Security provides default endpoints:

| Endpoint | Role |
| --- | --- |
| `/oauth2/authorization/corp` | Initiates login with registration corp |
| `/login/oauth2/code/corp` | Receives authorization response from the IdP |
| IdP's Authorization Endpoint | User login, MFA, and consent |
| IdP's Token Endpoint | Exchanges authorization code for tokens |
| UserInfo Endpoint | Fetches additional claims if used by the flow |

Do not write a custom controller to receive the authorization code and exchange tokens unless there is a special requirement. `oauth2Login()` already integrates the filters, authorization request repository, state validation, token client, and user service.

### 5.3. Initiating login from a login page

You can provide links to registrations:

~~~html
<a href="/oauth2/authorization/corp">Sign in with enterprise account</a>
<a href="/oauth2/authorization/legacy-partner">Sign in with partner account</a>
~~~

If there are multiple providers, display only providers appropriate for the tenant/application. Do not let users pick an arbitrary issuer via query parameter for the server to discover dynamically.

### 5.4. Client credentials and PKCE

Authorization Code Flow is the right choice for browser-based login. A server-side web application is typically a confidential client, holding its client secret on the server and authenticating at the Token Endpoint. The secret must come from a secret manager/environment injection, never committed to a repository or sent to the browser.

PKCE protects authorization codes against theft and unauthorized redemption. Use PKCE whenever the IdP supports it, and it is especially mandatory for public clients per OAuth security best current practices. PKCE complements client authentication; it does not replace a confidential client's secret.

### 5.5. State, nonce, and callback protection

Spring Security generates and validates state for authorization requests. With OIDC, a nonce is sent in the authentication request and verified in the ID Token. The two values solve different problems:

- `state` binds the authorization response to the pending request, mitigating CSRF/login response injection.
- `nonce` binds the ID Token to the authentication request, mitigating ID Token replay/substitution.

Do not set a static state, reuse state across logins, or disable state/nonce validation to fix callback errors. If using a custom `AuthorizationRequestRepository`, preserve one-time correlation, session binding, and TTL.

## 6. Verifying identity from the upstream IdP

### 6.1. Validating the ID Token

With OIDC, Spring Security handles ID Token verification based on provider metadata and client registration. Important checks include:

- Signature is verified using the appropriate key from the issuer's JWKS.
- `iss` matches the configured issuer.
- `aud` contains the registration's client ID.
- `exp` is still valid, accounting for clock skew per policy.
- `iat` and related timestamps are valid.
- `nonce` matches the request if a nonce was sent.
- Other OIDC rules depending on the flow and requested claims.

Do not simply Base64-decode the JWT and trust the payload. Do not accept a token from a different issuer just because its signature could be verified by a key with a matching name.

### 6.2. UserInfo Endpoint

OIDC UserInfo can supplement profile claims such as name, email, preferred_username, or locale. The ID Token remains the primary identity assertion; UserInfo is supplementary data.

When using UserInfo:

- Call the endpoint over HTTPS.
- Use the Access Token belonging to the right provider/registration.
- Verify that the subject in UserInfo matches the subject in the ID Token.
- Request only necessary scopes.
- Handle missing or changed attributes.
- Do not treat email or display name as an immutable identity key.

### 6.3. OAuth2-only providers

For an OAuth2-only provider, Spring Security calls the UserInfo endpoint via `DefaultOAuth2UserService`. The provider must supply a username attribute configured via `user-name-attribute`.

For example, `id` or `user_id` can be used if the provider guarantees stability and uniqueness. If the provider only returns a mutable email, you need a different identity contract or must not use it as the external subject key.

### 6.4. Do not call UserInfo with an arbitrary upstream token

The upstream Access Token is a credential intended for that issuer's resources/APIs. Do not send it to arbitrary APIs or log it. Send it only to the UserInfo endpoint identified by the discovery/configuration of the matching registration.

## 7. Normalizing principals and mapping identities

### 7.1. The OIDC identity key is issuer + subject

`sub` is unique only within the scope of an issuer/sector. Therefore, a durable linking key should consist of:

~~~text
external_identity_key = (issuer, subject)
~~~

Example:

~~~text
("https://login.corp.example", "00u8a1f2")
("https://identity.partner.example", "00u8a1f2")
~~~

Two identical subject values from two different issuers are two different external identities. With pairwise subjects, the same person can receive different subjects across different clients/sectors; identity mapping must adhere to the exact OIDC deployment contract.

For an OAuth2-only provider, use the configured provider namespace plus the stable user identifier per the provider's contract. Do not pretend there is a standard `iss` if the provider does not offer issuer semantics.

### 7.2. Identity link table model

Relational schema example:

~~~sql
CREATE TABLE local_user (
    id              uuid PRIMARY KEY,
    tenant_id       varchar(100) NOT NULL,
    status          varchar(30) NOT NULL,
    display_name    varchar(255),
    email           varchar(320),
    created_at      timestamptz NOT NULL
);

CREATE TABLE federated_identity (
    id              uuid PRIMARY KEY,
    local_user_id   uuid NOT NULL REFERENCES local_user(id),
    tenant_id       varchar(100) NOT NULL,
    provider_key    varchar(255) NOT NULL,
    issuer          varchar(512),
    subject         varchar(512) NOT NULL,
    created_at      timestamptz NOT NULL,
    last_login_at   timestamptz,
    UNIQUE (tenant_id, provider_key, issuer, subject)
);

CREATE UNIQUE INDEX uq_federated_identity_oauth2
    ON federated_identity(tenant_id, provider_key, subject)
    WHERE issuer IS NULL;
~~~

With OIDC, the provider key represents the registration and `issuer` stores the canonical value. With an OAuth2-only provider, `issuer` may be null, but `provider_key` must be a configured stable namespace; the partial unique index ensures no duplicate identities are created within the same tenant. Adjust indexes according to your actual database and tenant rules.

### 7.3. Resolving or provisioning users

A service can execute the workflow:

~~~java
public LocalUser resolveIdentity(
        String providerKey,
        String tenantId,
        String issuer,
        String subject,
        Map<String, Object> claims) {

    return identityRepository
        .findByTenantIdAndProviderKeyAndIssuerAndSubject(
            tenantId, providerKey, issuer, subject)
        .map(this::requireActiveUser)
        .orElseGet(() -> provisionAccordingToPolicy(
            providerKey, tenantId, issuer, subject, claims));
}
~~~

`provisionAccordingToPolicy` is application logic. You might auto-create accounts for an administratively approved workforce IdP, while requiring an invitation or admin approval for partners. Do not enable Just-In-Time provisioning for all issuers without a tenant allowlist and policy.

`TrustedTenantResolver` must derive the tenant from configured registration/provider policy and trusted claims. Never take the tenant directly from a query parameter or an unverified claim.

### 7.4. Account linking must not rely solely on email

Do not automatically link an external identity to a local account just because their emails match. Email addresses can change, be unverified, be recycled, or have different aliasing rules across providers.

A safe linking flow typically requires:

1. The user is currently logged into the existing local account.
2. The user re-authenticates or performs step-up authentication per policy.
3. The user explicitly initiates linking the new IdP.
4. The application verifies the new IdP's callback and issuer/subject.
5. The identity link is created inside a transaction with a unique constraint.
6. An audit event is recorded and notifications are sent if required by policy.

If the account is already linked to another user, halt the flow and require a support/administrative resolution process. Never automatically transfer account ownership.

### 7.5. Profile updates and deprovisioning

Profile claims may change across logins. Decide which fields are synchronized:

- Display name and avatar are typically updatable fields.
- Email should be updated only when the provider guarantees verified status and policy permits it.
- Tenant, employment status, and group membership require an authoritative source.
- Local username/user ID should not be changed simply because upstream `preferred_username` changed.

When an employee leaves the organization or the IdP revokes an account, a deprovisioning policy is needed: disable the local user, revoke local sessions/refresh tokens, handle downstream authorizations, and retain audit records per retention policy. A single failed login does not by itself prove the account was deleted at the IdP.
## 8. Customizing OIDC UserService and OAuth2 UserService

### 8.1. Purpose of UserService

After the token response is processed, Spring Security uses UserService to create the principal for login. This is the right place to read subject/claims from the verified upstream identity, look up the external identity link, provision or load the local user, verify local account status, map local authorities, and return a principal with a stable internal identifier.

Do not place complex authorization logic inside a callback controller. Place identity resolution logic in an independently testable service.

### 8.2. OIDC UserService

By default, `OidcUserService` loads UserInfo when required by the provider and scopes. You can wrap this service to add local identity mapping:

~~~java
@Bean
OAuth2UserService<OidcUserRequest, OidcUser> federatedOidcUserService(
        IdentityFederationService identityFederationService,
        TrustedTenantResolver tenantResolver) {

    OidcUserService delegate = new OidcUserService();

    return userRequest -> {
        OidcUser upstreamUser = delegate.loadUser(userRequest);

        String issuer = userRequest.getClientRegistration()
            .getProviderDetails()
            .getIssuerUri();
        String providerKey = userRequest.getClientRegistration()
            .getRegistrationId();
        String tenantId = tenantResolver.resolve(
            providerKey, upstreamUser.getClaims());

        String subject = upstreamUser.getSubject();

        LocalUser localUser = identityFederationService
            .resolveOrProvisionOidcUser(
                providerKey, tenantId, issuer, subject,
                upstreamUser.getClaims());

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>(upstreamUser.getAuthorities());
        authorities.addAll(identityFederationService.mapAuthorities(
            localUser, upstreamUser.getClaims()));

        return new LocalFederatedOidcUser(
            upstreamUser, localUser.getId().toString(), authorities);
    };
}
~~~

`LocalFederatedOidcUser` is an application-defined adapter implementing `OidcUser` that delegates ID Token, UserInfo, claims, and attributes to `upstreamUser`; `getName()` returns the local user ID; `getAuthorities()` returns authorities mapped per internal policy. This lets the application use a stable internal principal while preserving the necessary OIDC identity details.

Do not mint a new ID Token inside UserService. The upstream ID Token has already been verified by Spring Security; the internal Authorization Server will issue downstream tokens in its own protocol flow.

### 8.3. OAuth2 UserService for non-OIDC providers

For OAuth2-only providers, use `DefaultOAuth2UserService` and map the configured identifier attribute:

~~~java
@Bean
OAuth2UserService<OAuth2UserRequest, OAuth2User> federatedOAuth2UserService(
        IdentityFederationService identityFederationService,
        TrustedTenantResolver tenantResolver) {

    DefaultOAuth2UserService delegate = new DefaultOAuth2UserService();

    return userRequest -> {
        OAuth2User upstreamUser = delegate.loadUser(userRequest);

        ClientRegistration registration =
            userRequest.getClientRegistration();
        String providerKey = registration.getRegistrationId();
        String tenantId = tenantResolver.resolve(
            providerKey, upstreamUser.getAttributes());

        String usernameAttribute = registration.getProviderDetails()
            .getUserInfoEndpoint()
            .getUserNameAttributeName();

        Object externalId =
            upstreamUser.getAttributes().get(usernameAttribute);

        if (externalId == null) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error("invalid_user_info_response"),
                "The configured user identifier is missing");
        }

        LocalUser localUser = identityFederationService
            .resolveOrProvisionOAuth2User(
                providerKey, tenantId,
                externalId.toString(),
                upstreamUser.getAttributes());

        Set<GrantedAuthority> authorities =
            new LinkedHashSet<>(upstreamUser.getAuthorities());
        authorities.addAll(identityFederationService.mapAuthorities(
            localUser, upstreamUser.getAttributes()));

        return new LocalFederatedOAuth2User(
            upstreamUser, localUser.getId().toString(), authorities);
    };
}
~~~

`LocalFederatedOAuth2User` is an adapter implementing `OAuth2User`, delegating attributes to the upstream principal, returning the local user ID from `getName()`, and returning mapped internal authorities. For OAuth2-only providers, `providerKey`/registration ID establishes the identity namespace; the external identifier must be guaranteed stable by the provider.

### 8.4. Wiring UserService into oauth2Login

~~~java
http.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(federatedOidcUserService)
        .userService(federatedOAuth2UserService)
    )
);
~~~

If using only OIDC, you can configure just `oidcUserService`. If using only OAuth2-only providers, configure `userService`. Do not use a generic OAuth2 service to handle ID Tokens manually without preserving proper OIDC validation.

### 8.5. Principal adapters must preserve the contract

The adapter should preserve the required methods:

- OIDC: `getIdToken()`, `getUserInfo()`, `getClaims()`, `getAttributes()`.
- OAuth2: `getAttributes()`.
- Both: `getAuthorities()` and `getName()`.

Do not return the local user ID by mutating the `sub` claim inside the upstream ID Token. `sub` is a claim belonging to the external issuer; the local user ID is an internal identifier. Keep them in separate fields for auditing and account linking.

OIDC adapter skeleton example:

~~~java
final class LocalFederatedOidcUser implements OidcUser {

    private final OidcUser delegate;
    private final String localUserId;
    private final Collection<? extends GrantedAuthority> authorities;

    LocalFederatedOidcUser(
            OidcUser delegate,
            String localUserId,
            Collection<? extends GrantedAuthority> authorities) {
        this.delegate = delegate;
        this.localUserId = localUserId;
        this.authorities = authorities;
    }

    @Override public String getName() { return localUserId; }
    @Override public Map<String, Object> getAttributes() { return delegate.getAttributes(); }
    @Override public Map<String, Object> getClaims() { return delegate.getClaims(); }
    @Override public OidcIdToken getIdToken() { return delegate.getIdToken(); }
    @Override public OidcUserInfo getUserInfo() { return delegate.getUserInfo(); }
    @Override public Collection<? extends GrantedAuthority> getAuthorities() {
        return authorities;
    }
}
~~~

The OAuth2-only adapter works similarly with `OAuth2User`: delegate `getAttributes()`, return the local ID from `getName()`, and use the mapped authorities. This is an illustrative class; add constructor validation and any additional methods required by your application.

## 9. Mapping groups and roles to internal permissions

### 9.1. Do not trust role names directly from the IdP

An IdP may return claims such as `groups`, `roles`, `entitlements`, or `memberOf`. Their structure and semantics depend on the provider. Never automatically convert arbitrary values into `ROLE_ADMIN` or privileged authorities.

Maintain a mapping table:

| Upstream provider | External group/claim | Local authority |
| --- | --- | --- |
| workforce | `portal-users` | `ROLE_PORTAL_USER` |
| workforce | `finance-approvers` | `ROLE_PAYMENT_APPROVER` |
| customer | `premium-tier` | `ROLE_PREMIUM_CUSTOMER` |
| partner | `support-agents` | `ROLE_SUPPORT_AGENT` |

Mappings must be scoped to both provider and tenant. The same group string can have different meanings across two IdPs.

### 9.2. Grant authorities only from approved mappings

Logic example:

~~~java
Set<GrantedAuthority> mapGroups(
        String providerKey,
        String tenantId,
        Collection<String> externalGroups) {

    return externalGroups.stream()
        .map(group -> roleMappingRepository
            .findLocalRole(providerKey, tenantId, group))
        .flatMap(Optional::stream)
        .map(SimpleGrantedAuthority::new)
        .collect(Collectors.toUnmodifiableSet());
}
~~~

This is a fragment. If a group is not in the mapping, ignore it or log an audit record per policy. Never use strings returned by the IdP directly as authorities.

### 9.3. Authentication assurance

Claims such as `acr`, `amr`, and `auth_time` can support step-up authentication policies if the IdP issues them under a reliable contract. For example, changing payment details may require recent MFA.

Do not turn an `amr` value into long-lived access permissions. Assurance is point-in-time and contextual; you must check freshness, issuer, and the actual assurance level provided by the IdP.

### 9.4. Local authorization remains the source of truth

The IdP authenticates the user; the internal Authorization Server decides which systems, tenants, scopes, and roles the user is permitted to use. Upstream group claims are policy inputs, not replacements for internal policy.

## 10. From upstream Authentication to internal tokens

### 10.1. Local SecurityContext

After the callback succeeds and UserService returns the principal, Spring Security creates an Authentication and stores it in the SecurityContext per the application chain configuration. This session represents the user logged into the internal Authorization Server.

SAS uses that Authentication when processing downstream Authorization Requests. Once the user consents and the client is authorized, the AS issues an authorization code and then tokens according to the RegisteredClient, scope, consent, and token policy.

### 10.2. Issuing internal claims

If you want to include the tenant or local user ID in the internal Access Token JWT, use `OAuth2TokenCustomizer<JwtEncodingContext>`. Example adding claims only to the Access Token:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> internalAccessTokenCustomizer(
        LocalAuthorizationPolicy localAuthorizationPolicy) {

    return context -> {
        if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            return;
        }

        String localUserId = context.getPrincipal().getName();

        LocalTokenClaims claims =
            localAuthorizationPolicy.claimsFor(
                localUserId,
                context.getRegisteredClient(),
                context.getAuthorizedScopes());

        context.getClaims()
            .claim("local_user_id", localUserId)
            .claim("tenant_id", claims.tenantId())
            .claim("roles", claims.allowedRoles());
    };
}
~~~

`LocalAuthorizationPolicy` must compute permissions based on the user, client, scope, and internal policy. Include only claims that the Resource Server genuinely needs; do not copy all upstream claims into downstream tokens.

The customizer must be wired into the `JwtGenerator` used by the Authorization Server. If the application configures its own `OAuth2TokenGenerator`, call `jwtGenerator.setJwtCustomizer(customizer)`; merely declaring a customizer bean without wiring it into a manually created generator will not alter issued tokens.

### 10.3. Audience and scope

Upstream tokens have an audience targeting the IdP's APIs. Downstream tokens need an audience and scope suited to internal Resource Servers. Do not reuse an upstream access token as an access token for an API with a different audience.

If a backend needs to call an upstream API on behalf of the user, use `OAuth2AuthorizedClient` and the access token from the upstream registration. If delegation or token exchange is needed, design it separately per RFC 8693 and both issuers' policies.

### 10.4. Two distinct token stores

| Service | Data |
| --- | --- |
| `OAuth2AuthorizedClientService` | Access/refresh tokens issued by the upstream IdP for the AS to call upstream APIs |
| `OAuth2AuthorizationService` | Authorizations and tokens issued by the internal AS for downstream clients |
| `RegisteredClientRepository` | Registrations of downstream OAuth2/OIDC clients |
| `ClientRegistrationRepository` | Registrations of upstream OAuth2/OIDC providers |

Do not use `OAuth2AuthorizationService` to store upstream authorized clients just because both contain tokens. The two token types have different issuers, audiences, owners, and lifecycles.

## 11. Storing upstream Authorized Clients

If the Authorization Server needs to call UserInfo, a directory API, or another upstream IdP API after login, it must store the authorized client keyed by the appropriate principal/registration.

Spring Boot can auto-configure a default `OAuth2AuthorizedClientService`. In production, consider:

- Storing tokens server-side; never sending refresh tokens to the browser.
- Encrypting tokens when persisting to a store.
- Restricting who can retrieve authorized clients.
- Binding authorized clients to the local principal and registration ID.
- Deleting/revoking upstream tokens upon account unlink or deprovisioning per policy.
- Handling refresh token rotation and refresh failures.
- Never logging token values or placing tokens in metric labels.

If you only need verified identity information at login time, do not retain the upstream access token longer than necessary. Minimize scopes and retention duration according to the principle of least privilege.

## 12. Session, logout, and link lifecycle

### 12.1. Local logout

Local logout terminates the login session at the internal Authorization Server via Spring Security's LogoutFilter/LogoutHandler. This clears the local SecurityContext and session as configured. It does not necessarily terminate the session at the upstream IdP.

### 12.2. Upstream OP logout

If the upstream IdP supports RP-Initiated Logout and publishes `end_session_endpoint`, the application can redirect the browser to that endpoint after local logout via the appropriate flow. You must use an ID Token hint matching the right issuer/client, a registered post-logout redirect URI, and state correlation. Do not assume every OAuth2-only provider has an OIDC logout endpoint.

### 12.3. Downstream logout

Downstream clients can call the internal Authorization Server's OIDC RP-Initiated Logout Endpoint. The AS then terminates the local OP session. If logout needs to propagate to other RPs, implement Front-Channel or Back-Channel Logout per the corresponding profile and registration.

### 12.4. Account unlinking differs from logout

Unlinking an external identity modifies the account-link relationship. It requires proper authorization, auditing, and confirmation. Logout only ends the current session; it does not automatically remove identity links. Deprovisioning may require disabling the user and revoking internal tokens/sessions per policy.

## 13. Security and common pitfalls

### 13.1. Trust boundaries

- Trust only configured issuers verified via metadata/JWKS.
- Use HTTPS for discovery, callback, token, and UserInfo endpoints.
- Never accept an arbitrary issuer from a request.
- Never skip issuer, audience, expiry, or nonce validation.
- Restrict redirect URIs and protect the public base URL.
- Keep client secrets in a server-side secret store.
- Use state and PKCE according to the flow.
- Never log ID Tokens, access tokens, refresh tokens, or authorization codes.

### 13.2. Account confusion

Common mistakes:

- Using email as the primary key for linking identities.
- Using subject alone while omitting issuer.
- Merging matching usernames across two tenants.
- Auto-linking a new account to an existing local user without proof.
- Accepting a user-chosen IdP.
- Using external groups directly as local roles.
- Keeping a local account active after the upstream identity has been deprovisioned without a policy.

Use a unique external identity key, an issuer/provider allowlist, tenant mapping, explicit account linking, and auditing.

### 13.3. Login CSRF and account swapping

State prevents responses not bound to a pending authorization request. In account linking, beyond state, you must ensure the callback belongs to the local account session that initiated linking. If the browser switches accounts or sessions between initiation and callback, do not attach the identity to a different user.

For sensitive flows, bind the link transaction to the local user ID, session ID, registration ID, and expiry; consume it once upon a successful callback.

### 13.4. SSRF and discovery

Do not allow users to submit arbitrary issuer URLs for the server to fetch discovery/JWKS/UserInfo. Use managed provider configurations, hostname allowlists, egress policies, and timeouts. Discovery metadata is trusted input only after the issuer has been verified against configuration.

## 14. Testing identity federation

### 14.1. Testing OIDC login

Verify:

- Discovery fetches the right issuer and authorization/token/JWKS/UserInfo endpoints.
- Redirect URI matches the registration ID and public base URL.
- State mismatch or replay is rejected.
- ID Tokens with invalid signature, issuer, audience, expiry, or nonce are rejected.
- UserInfo subject mismatch is rejected.
- Missing subject claim does not create a local account.
- Provider timeouts or JWKS rotations are handled properly.

### 14.2. Testing account mapping

| Scenario | Expected outcome |
| --- | --- |
| Same issuer + subject logs in again | Resolves to the right local user |
| Same subject, different issuer | Does not merge into the same user |
| Subject changes | Does not automatically transfer identity link |
| Email matches local user | Does not auto-link |
| Unverified email | Not used for account linking |
| Identity link already belongs to another user | Rejects and audits |
| Local user disabled | Does not grant local session |
| Provider not in allowlist | Does not initiate login |
| Invalid tenant mapping | Does not provision user |
| Unmapped group | Does not grant local authority |
| Concurrent JIT provisioning | Unique constraint prevents duplicates |

### 14.3. Testing OAuth2-only providers

- UserInfo endpoint requires the proper bearer token.
- The `user-name-attribute` property exists.
- The identifier is stable per the provider contract.
- Missing or invalid attributes are rejected.
- Do not assume an OAuth2 access token contains ID Token claims.
- Do not call another registration's UserInfo endpoint.

### 14.4. Testing downstream token issuance

After upstream login succeeds:

1. Verify the local SecurityContext contains the local principal.
2. Send a downstream Authorization Request with a registered client.
3. Verify consent and scopes are enforced.
4. Exchange the authorization code for internal tokens.
5. Verify the issuer/audience/signature of internal tokens.
6. Verify internal claims contain only data allowed by policy.
7. Verify the upstream token is not relayed as a downstream access token.

### 14.5. Testing logout and deprovisioning

- Local logout terminates the AS session.
- Upstream OP session persists or terminates accurately according to the configured logout flow.
- Downstream RP logout is not confused with upstream logout.
- User deprovisioning disables permissions and sessions/tokens per policy.
- Unlinking an account does not automatically delete the local user or other identity links.

## 15. Operations and troubleshooting

| Symptom | Common cause | Where to check |
| --- | --- | --- |
| /oauth2/authorization/corp returns 404 | Missing ClientRegistration or OAuth2 Client dependency | Boot configuration and dependencies |
| Callback state mismatch | Session cookie not sent, request replay, or buggy custom repository | Cookie SameSite, session, and state store |
| Invalid issuer | issuer-uri does not match iss claim | Provider metadata and IdP config |
| Invalid audience | Client ID differs from aud | Client registration at the IdP |
| Invalid nonce | Nonce lost or ID Token belongs to a different request | Authorization request repository |
| JWKS signature failure | Key rotation/cache or wrong issuer | JWKS URI, kid, and cache |
| UserInfo 401 | Wrong access token, scope, or auth method | UserInfo endpoint config |
| UserInfo subject mismatch | Provider returns profile for a different identity token | IdP contract and response |
| User logs in but local user does not exist | Provisioning/mapping did not run | IdentityFederationService |
| Logged into wrong tenant | Mapping relies only on username/email | Provider/issuer/tenant key |
| Local privileges too high | Copying external groups directly as roles | Authority allowlist |
| Callback URL has wrong host | Untrusted forwarded headers/Host header | Proxy and public base URL |
| Re-login still sees IdP session | Local logout did not end upstream OP session | Upstream logout metadata/flow |
| Downstream token contains stale upstream claims | Copying all upstream claims or buggy customizer | Local claim policy and token customizer |

### 15.1. Logging and metrics

Monitor:

- Login attempts/successes/failures per registration ID.
- Discovery/JWKS/UserInfo latency and failures.
- State/nonce/issuer/audience validation failures.
- Identity mapping misses and JIT provisioning results.
- Account linking conflicts.
- Disabled user login attempts.
- Authority mapping results.
- Upstream token refresh failures.
- Downstream token issuance successes/failures.

Never log raw authorization codes, ID Tokens, access tokens, refresh tokens, client secrets, or session cookies. Use correlation IDs, registration IDs, normalized issuers, local user IDs, and appropriate error categories.

## 16. Self-check questions

**Q1.** Does OAuth2 define a user authentication standard on its own?

**Answer:** No. OAuth2 is an authorization framework. OIDC adds the ID Token and authentication rules.

**Q2.** Why should an OIDC identity key include both issuer and subject?

**Answer:** Subject is unique only within the scope of an issuer/sector; two issuers can issue the same `sub` string to two different people.

**Q3.** How do state and nonce differ?

**Answer:** `state` binds the authorization response to the pending request; `nonce` binds the ID Token to the OIDC authentication request.

**Q4.** Should accounts be linked solely because emails match?

**Answer:** No. Emails can change, be unverified, or be recycled. Proof and an explicit linking workflow are required.

**Q5.** Which endpoint does Spring Security use to initiate upstream login?

**Answer:** `/oauth2/authorization/{registrationId}`.

**Q6.** What is the default callback of OAuth2 Login?

**Answer:** `/login/oauth2/code/{registrationId}`.

**Q7.** Does OIDC UserInfo replace the ID Token?

**Answer:** No. The ID Token is the identity assertion; UserInfo provides supplementary claims and its subject must match.

**Q8.** Can an upstream ID Token be forwarded as a downstream ID Token?

**Answer:** No. The internal Authorization Server must issue an ID Token from its own internal issuer tailored to the downstream client/audience.

**Q9.** What is an upstream Access Token used for?

**Answer:** Calling resources/APIs belonging to the upstream provider per the token's audience/scope; it is not meant by default for internal Resource Servers.

**Q10.** How do `OAuth2AuthorizedClientService` and `OAuth2AuthorizationService` differ?

**Answer:** The first stores upstream authorized clients/tokens; the second stores authorizations/tokens issued by the internal Authorization Server.

**Q11.** Should an upstream group claim be copied into ROLE_ADMIN?

**Answer:** No. Allowlist mapping scoped by provider, tenant, and internal policy is required.

**Q12.** Does local logout automatically end the upstream IdP session?

**Answer:** No. Doing so requires upstream RP-Initiated Logout if supported by the IdP and configured in the application's flow.

## 17. Production checklist

- [ ] Prefer OIDC for federated login when supported by the IdP.
- [ ] Providers/issuers are configured and allowlisted.
- [ ] Discovery/JWKS/UserInfo use HTTPS.
- [ ] Client ID, secret, and redirect URI match the registration at the IdP.
- [ ] Secrets are stored in a secret manager, never committed or sent to the browser.
- [ ] Authorization Code Flow is used.
- [ ] PKCE is enabled when appropriate and required for public clients per policy.
- [ ] State is validated, one-time, and session-bound.
- [ ] Nonce is validated in OIDC.
- [ ] ID Token signature, iss, aud, exp, and nonce are verified.
- [ ] UserInfo subject matches the ID Token subject.
- [ ] External identity key uses issuer + subject.
- [ ] OAuth2-only providers have a stable identifier contract and provider namespace.
- [ ] Never auto-link accounts based solely on email.
- [ ] JIT provisioning enforces an allowlist and tenant policy.
- [ ] Disabled local users cannot log in.
- [ ] External groups are mapped via an allowlist.
- [ ] Upstream Authentication is normalized into a local principal.
- [ ] Downstream tokens are issued by the internal issuer.
- [ ] Upstream and downstream audiences/scopes are kept separate.
- [ ] Upstream authorized client tokens are stored and protected properly.
- [ ] Logout/deprovisioning/unlinking have lifecycle policies.
- [ ] Tests cover state/nonce/issuer/audience/account linking/tenant/authority mapping.
- [ ] Never log raw tokens, authorization codes, client secrets, or session cookies.
- [ ] Metrics exist for upstream providers and identity mapping.

## 18. References and conclusion

Standards and documentation:

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html)
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)
- [OAuth 2.0 Authorization Framework — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749)
- [OAuth 2.0 Token Exchange — RFC 8693](https://www.rfc-editor.org/rfc/rfc8693)
- [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html)
- [Spring Security — OAuth2 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
- [Spring Security — OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html)
- [Spring Security — OAuth2 Client Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Authorization Server — Core Model](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html)
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html)

**Conclusion:** Integrating login from an upstream IdP turns the internal Authorization Server into an OIDC/OAuth2 Client toward the external identity system. With OIDC, Spring Security runs the Authorization Code Flow, checks state/nonce, verifies the ID Token, and loads UserInfo per registration. The application must map external identities by issuer and subject, provision/link local users according to policy, and then build the local principal and SecurityContext. For OAuth2-only providers, a dedicated identity contract and stable user identifier are required; never infer authentication solely from an access token. After upstream login, the internal Authorization Server still applies its own scopes, consent, audiences, and policies to issue downstream tokens. By maintaining these boundaries, the platform can federate multiple IdPs without mixing identities, permissions, or credentials across issuers.




