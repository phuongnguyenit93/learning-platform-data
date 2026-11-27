# Distinguishing Upstream IdP Tokens from Internal Server-Issued Tokens

## Lesson objectives

In the **Identity Federation** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, this lesson explains how a system uses **Spring Security**, **Spring Authorization Server**, and **Spring Boot** to federate identities from an external OpenID Provider (IdP) and then issue its own tokens for internal applications and APIs.

In the federation model, the upstream IdP authenticates the user. The internal server trusts that authentication result according to a predefined issuer configuration, maps the external identity to an internal account, and applies the organization's permission policy. When an internal application needs to access an API, it uses an access token issued by the internal Authorization Server.

These two groups of tokens have different issuers, audiences, subjects, purposes, and lifecycles. The fact that a token is a valid JWT or signed by a trusted IdP does not mean it can be used at every API.

After this lesson, you will be able to:

1. Distinguish upstream ID Tokens, upstream access tokens, internal ID Tokens, and internal access tokens.
2. Explain the roles of IdP, OAuth2 Client, Authorization Server, Relying Party, and Resource Server.
3. Configure Spring Authorization Server to use OIDC social login via Spring Security OAuth2 Client.
4. Map external identities by issuer and subject pair to a stable internal user identifier.
5. Distinguish `OAuth2AuthorizedClientService` from `OAuth2AuthorizationService`.
6. Issue internal ID Tokens and access tokens with issuer, subject, audience, scope, and claims per internal policy.
7. Use upstream access tokens to call the right IdP APIs when needed.
8. Understand the limitations of default Token Exchange in Spring Authorization Server 1.5.8 when given a token from another IdP.
9. Design a custom token exchange for trusted external issuers when genuinely required.
10. Test issuer/audience validation, account linking, token exchange, logout, and deprovisioning.

> **Running scenario:** employees sign into the company system through a corporate IdP. The internal Authorization Server verifies the OIDC result, maps the employee to an internal account, and issues tokens to applications such as `employee-portal` and `mobile-app`. The `orders`, `payroll`, and `profile` APIs trust only tokens issued by the internal issuer.

## 1. Identity federation architecture

### 1.1. Roles in the model

| Component | Role | Related tokens |
|---|---|---|
| Upstream IdP / upstream OpenID Provider | Authenticates the End-User and provides external identity. | Upstream ID Token; upstream access token. |
| Internal Authorization Server | Trusts the IdP per configuration, maps the user, enforces policy, and issues internal tokens. | Internal ID Token; internal access token; refresh token if permitted. |
| Internal OAuth2/OIDC Client (RP) | Logs users in via the internal Authorization Server and verifies internal ID Tokens. | Receives internal ID Token and access token. |
| Internal Resource Server | Protects internal APIs with access tokens. | Accepts only tokens matching the API's trust policy. |
| Upstream Resource Server | Exposes APIs of the IdP or external system. | Accepts upstream access tokens per its audience/scopes. |

Spring Security provides OAuth2 Client and OAuth2 Login so the application acts as an RP toward the upstream IdP. Spring Authorization Server acts as the OpenID Provider/Authorization Server for internal applications. Both roles can run inside the same application, yet remain two distinct protocol relationships.

### 1.2. Two trust boundaries

In this model, there are at least two trust boundaries:

- **External trust boundary:** the internal Authorization Server trusts the external issuer for identity authentication. Trust must be tied to a specific issuer, predefined metadata/JWKS, client registration, and OIDC validation rules.
- **Internal trust boundary:** internal Resource Servers trust the internal issuer to determine who may call which API. Internal tokens are issued based on the mapped identity and internal permissions.

Do not expand trust simply because two tokens share the JWT format. Each Resource Server must specify the accepted issuer, audience, token type, and policy.

### 1.3. Federated login flow

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Browser / End-User
    participant RP as Internal OIDC Client
    participant IAS as Internal Authorization Server
    participant IDP as Upstream IdP
    participant DB as Local Identity Store
    participant API as Internal Resource Server

    U->>RP: Open internal application
    RP->>IAS: Authorization Request
    IAS->>IDP: Redirect to upstream OIDC login
    IDP->>U: Authenticate user
    U->>IDP: Credentials / MFA
    IDP-->>IAS: Authorization Code
    IAS->>IDP: Token Request
    IDP-->>IAS: Upstream ID Token + Access Token
    IAS->>IAS: Validate upstream OIDC response
    IAS->>DB: Resolve (issuer, subject)
    DB-->>IAS: Local user + local authorities
    IAS-->>RP: Internal Authorization Code
    RP->>IAS: Exchange code at internal Token Endpoint
    IAS-->>RP: Internal ID Token + Internal Access Token
    RP->>API: Authorization: Bearer internal_access_token
    API->>API: Validate internal issuer, audience and scopes
    API-->>RP: Protected resource
~~~

The key point is that internal applications receive tokens from the internal Authorization Server. The upstream IdP handles upstream authentication; the internal Authorization Server handles token issuance per internal policy.

### 1.4. Two token flows can coexist

An application may simultaneously need:

- Internal access tokens to call internal APIs.
- Upstream access tokens to call IdP APIs or an external service.

These are two different purposes. Spring Security stores authorized OAuth2 client state in `OAuth2AuthorizedClient`. Spring Authorization Server stores authorizations and tokens it issues itself in `OAuth2Authorization`. Never mix these two stores or use one flow's token in place of the other.

## 2. Distinguishing the four token types

### 2.1. Comparison table

| Token | Issuer (iss) | Audience (aud) | Purpose | Where used |
|---|---|---|---|---|
| Upstream ID Token | External IdP | Client ID of the internal Authorization Server registered at the IdP | Proof of user authentication for the OAuth2/OIDC Client. | Internal Authorization Server during OIDC login. |
| Upstream access token | External IdP | API/resource granted by the IdP | Access resources belonging to the upstream provider. | Upstream Resource Server. |
| Internal ID Token | Internal Authorization Server | Client ID of the internal RP | Lets the internal RP verify user identity. | Internal OIDC Client. |
| Internal access token | Internal Authorization Server | Internal API/resource | Authorizes API access per internal scopes and policy. | Internal Resource Server. |

A JWT may carry similar claims, yet cannot substitute for another token when the issuer, audience, or purpose does not match.

### 2.2. Upstream ID Token

An OIDC ID Token is a security token describing an End-User authentication result at an issuer. Key claims include:

- **iss:** the issuer that authenticated the user.
- **sub:** subject identifier meaningful within that issuer's scope.
- **aud:** client or audiences permitted to receive the ID Token.
- **exp**, **iat:** expiration and issuance timestamps.
- **nonce:** binds the Authentication Request to the ID Token when the request contained a nonce.
- **auth_time**, **acr**, **amr:** authentication timestamp and context if requested or provided per policy.

The internal Authorization Server is an OIDC Client of the upstream IdP. Thus, the upstream ID Token's audience is the internal Authorization Server's client registration. It is not issued for internal `orders` or `payroll` APIs to consume.

This lesson uses an upstream **OIDC Provider** as its example. Some social providers support only OAuth2 and return `OAuth2User`/UserInfo without issuing an ID Token. When integrating such a provider, the application must follow that provider's identity verification contract; do not call that response an OIDC ID Token and do not apply OIDC claim assumptions when the provider does not implement OIDC.

### 2.3. Upstream access token

An upstream access token grants access to an IdP's resource server or an external service.

Example:

~~~http
GET /userinfo HTTP/1.1
Host: idp.example.com
Authorization: Bearer UPSTREAM_ACCESS_TOKEN
~~~

This token should only be sent to resource servers authorized by its issuer. If the token's audience is the IdP's API, an internal Resource Server must not accept it simply because its signature is valid.

In Spring Security, `OAuth2AuthorizedClient` binds the access token and optional refresh token to a `ClientRegistration` and user principal. `OAuth2AuthorizedClientManager`, `OAuth2AuthorizedClientRepository`, and `OAuth2AuthorizedClientService` manage the authorized client lifecycle.

### 2.4. Internal ID Token

The internal ID Token is issued during the OIDC flow between the internal Authorization Server and internal RP.

- **iss** is the internal issuer.
- **aud** contains the internal RP's client ID.
- **sub** is a stable internal subject managed by the organization.
- Claims reflect data permitted for disclosure to the internal RP.

The internal ID Token lets the RP know the user was authenticated by the internal OP. It is not a credential for calling APIs. Never send an ID Token in an API `Authorization` header in place of an access token.

### 2.5. Internal access token

The internal access token is issued for calling internal APIs. It needs:

- An internal issuer trusted by the Resource Server.
- An audience/resource matching the target API.
- Scopes/authorities granted per internal policy.
- Reasonable lifetime and appropriate signature/opaque-token validation.
- A token lifecycle with introspection/revocation or equivalent verification mechanisms.

Example:

~~~http
GET /api/orders HTTP/1.1
Host: orders.internal.example
Authorization: Bearer INTERNAL_ACCESS_TOKEN
~~~

The internal Resource Server validates the token against the API's configured issuer and audience. Upstream tokens do not automatically become internal access tokens.

## 3. Configuring Spring Authorization Server to log in via an upstream IdP

### 3.1. Adding the OAuth2 Client dependency

Spring Authorization Server uses Spring Security OAuth2 Client to perform upstream login. With Spring Boot, add the starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

The internal Authorization Server must be registered as an OAuth2/OIDC client at the upstream IdP. At the IdP, register Spring Security OAuth2 Login's redirect URI, for example:

~~~text
https://auth.internal.example/login/oauth2/code/corporate-idp
~~~

This is the callback between the **internal Authorization Server and the upstream IdP**. It differs from the redirect URI that internal RPs register at the internal Authorization Server.

### 3.2. Configuring ClientRegistration

`application.yml` example:

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
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate:
            issuer-uri: https://login.corporate.example
~~~

Spring Security uses the issuer URI to discover the OIDC Provider Configuration. For providers that do not support discovery, configure endpoints and the JWK Set URI manually according to the provider's documentation.

Client secrets must come from a secret manager or environment injection. Never commit real secrets to source control.

The **openid** scope requests OIDC login. Without this scope, Spring Security may process the response as OAuth2 Login with `OAuth2User` instead of `OidcUser`.

### 3.3. Separating the Authorization Server filter chain and login filter chain

Spring Authorization Server handles protocol endpoints in a dedicated `SecurityFilterChain`. OAuth2 Login handles user authentication in the application's filter chain.

Skeleton configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;

@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
        .with(authorizationServerConfigurer, authorizationServer ->
            authorizationServer.oidc(Customizer.withDefaults()))
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
@Order(2)
SecurityFilterChain defaultSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http.authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated())
        .oauth2Login(Customizer.withDefaults());

    return http.build();
}
~~~

The first chain protects Authorization Server endpoints and redirects unauthenticated browsers to the upstream login entry point. The second chain configures OAuth2 Login and handles callbacks from the IdP.

In a real-world application, the default chain may also need a custom `OidcUserService`, authentication success handler, session policy, CSRF rules, and an appropriate login page.

### 3.4. Internal Authorization Server remains a separate issuer

After upstream login succeeds, Spring Security creates an `Authentication` in the `SecurityContext`. Spring Authorization Server uses that principal to process Authorization Requests and issue internal codes/tokens.

Do not replace the internal issuer with the upstream IdP's issuer. Never let request Host headers or upstream claims dictate the internal Authorization Server's issuer.

Internal issuer configuration should be stable, for example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;

@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.internal.example")
            .build();
}
~~~

Internal RPs must also be registered separately at the internal Authorization Server. Minimal example for a confidential web client:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;

RegisteredClient employeePortal = RegisteredClient
        .withId("employee-portal-registration")
        .clientId("employee-portal")
        .clientSecret(passwordEncoder.encode(employeePortalSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://portal.internal.example/login/oauth2/code/internal")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .build())
        .build();
~~~

The client ID and secret here belong to the relationship between `employee-portal` and the **internal** Authorization Server. They are independent of the client ID/secret the internal Authorization Server uses to log into the upstream IdP.

## 4. Mapping upstream identity to local user

### 4.1. Identity key via issuer and subject

OIDC scopes subjects within an issuer. Therefore, the identity linking key needs at least two components:

~~~text
(federated_issuer, federated_subject)
~~~

Example:

| Issuer | Subject | Local subject |
|---|---|---|
| https://login.corporate.example | 00u123abc | usr_8f31... |
| https://login.partner.example | 00u123abc | usr_9a42... |

Two IdPs may issue the same `sub` string, yet they are two distinct identities. The local subject is the stable identifier in the internal domain.

Do not use email as the sole federation key. Emails can change, be recycled, be unverified, or have different uniqueness rules across IdPs.

### 4.2. Account linking and JIT provisioning

When a user logs in for the first time, the system may use Just-In-Time (JIT) provisioning to create a local user. When an existing local user links another IdP, a verification and audit workflow is required.

Policies to decide:

- Allow only issuers in the allowlist.
- Locked or deprovisioned local accounts must be rejected even if upstream login succeeds.
- Linking to an existing account requires proving control over both identities.
- Never auto-merge accounts solely because emails match.
- Audit create/link/unlink/update identity events.
- Define procedures for issuer changes, subject changes, and upstream permission revocations.
- Persist mappings with a unique constraint on the issuer/subject pair.

Illustrative data structure:

~~~sql
CREATE TABLE federated_identity (
    id varchar(100) PRIMARY KEY,
    local_user_id varchar(100) NOT NULL,
    issuer varchar(500) NOT NULL,
    subject varchar(500) NOT NULL,
    linked_at timestamp NOT NULL,
    UNIQUE (issuer, subject)
);
~~~

This is only an illustrative mapping table. Production schemas need foreign keys, indexes, audit columns, appropriate collations, and database-specific timestamp types.

JIT provisioning must be idempotent and transactional. The first two login callbacks for the same `(issuer, subject)` pair can run concurrently; the unique constraint is the final safeguard. If an insert hits a duplicate-key error, the service can re-read the mapping created by the other request and proceed after verifying the local account is still active. Never create a second local user or attach a different identity just to work around a conflict.

### 4.3. Do not trust authorities or groups directly from the IdP

An IdP may return `groups`, `roles`, or custom claims. These values are only inputs for mapping; they do not automatically become internal permissions.

For instance, an upstream group **finance-admin** should not automatically grant administrative access to all internal APIs. Local policy must determine which groups map to which roles, in which tenant, and within which resource scope.

Ideally, the local user directory returns vetted local authorities. Never blindly copy all authorities from the upstream `Authentication`.

## 5. Creating a local OidcUser with an internal subject

### 5.1. Why is a local principal needed?

Spring Authorization Server uses the logged-in user's `Authentication` as the principal when processing Authorization Requests. The principal identifier therefore affects the subject of internal authorizations and ID Tokens.

If you leave the default principal name of the upstream `OidcUser` untouched, the internal subject can inadvertently depend on the upstream `sub`. That couples internals to how the IdP manages subjects and creates friction when a person links multiple IdPs.

Create an `OidcUser` wrapper whose `getName()` returns the local subject. Upstream claims and ID Token can still be retained for mapping/auditing, but must not be copied verbatim into internal tokens.

### 5.2. LocalFederatedOidcUser

Wrapper class example:

~~~java
import java.util.Collection;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUserInfo;

public final class LocalFederatedOidcUser implements OidcUser {

    private final OidcUser upstreamUser;
    private final String localSubject;
    private final Collection<? extends GrantedAuthority> localAuthorities;

    public LocalFederatedOidcUser(
            OidcUser upstreamUser,
            String localSubject,
            Collection<? extends GrantedAuthority> localAuthorities) {
        this.upstreamUser = upstreamUser;
        this.localSubject = localSubject;
        this.localAuthorities = localAuthorities;
    }

    @Override
    public String getName() {
        return this.localSubject;
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return this.localAuthorities;
    }

    @Override
    public Map<String, Object> getAttributes() {
        return this.upstreamUser.getAttributes();
    }

    @Override
    public Map<String, Object> getClaims() {
        return this.upstreamUser.getClaims();
    }

    @Override
    public OidcIdToken getIdToken() {
        return this.upstreamUser.getIdToken();
    }

    @Override
    public OidcUserInfo getUserInfo() {
        return this.upstreamUser.getUserInfo();
    }
}
~~~

Local authorities are passed from the local user directory. Do not use `upstreamUser`'s authorities directly without a mapping policy.

Keeping the upstream ID Token inside the principal does not make it an internal ID Token. It remains a token issued by the upstream issuer, with the audience and semantics of the upstream client registration.

In this wrapper, `getName()` is the local subject used by Spring Security and the internal Authorization Server as the principal name. `getIdToken()`, `getClaims()`, and `getSubject()` still reflect the upstream OIDC identity because the wrapper delegates those methods. Do not call `getSubject()` to obtain the local subject; use `getName()` or an explicit local identity property. Internal ID Tokens must have `sub` populated by a customizer from the local directory, as shown later.

### 5.3. Custom OidcUserService

Spring Security allows replacing `OidcUserService` to process the user after the OIDC response is verified.

Local identity directory contract example:

~~~java
import java.util.Collection;
import java.util.Map;

import org.springframework.security.core.GrantedAuthority;

public interface FederatedIdentityDirectory {

    LocalFederatedAccount resolveOrProvision(
            String issuer,
            String subject,
            Map<String, Object> upstreamClaims);
}

public record LocalFederatedAccount(
        String subject,
        String tenantId,
        Collection<? extends GrantedAuthority> authorities) {
}
~~~

Service example:

~~~java
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.util.StringUtils;

@Bean
OAuth2UserService<OidcUserRequest, OidcUser> federatedOidcUserService(
        FederatedIdentityDirectory identityDirectory) {

    OidcUserService delegate = new OidcUserService();

    return userRequest -> {
        OidcUser upstreamUser = delegate.loadUser(userRequest);

        String issuer = userRequest.getClientRegistration()
                .getProviderDetails().getIssuerUri();

        if (!StringUtils.hasText(issuer)
                || !StringUtils.hasText(upstreamUser.getSubject())) {
            throw new IllegalStateException(
                    "The upstream OIDC identity is incomplete");
        }

        LocalFederatedAccount localAccount =
                identityDirectory.resolveOrProvision(
                        issuer,
                        upstreamUser.getSubject(),
                        upstreamUser.getClaims());

        if (localAccount == null
                || !StringUtils.hasText(localAccount.subject())
                || !StringUtils.hasText(localAccount.tenantId())
                || localAccount.authorities() == null) {
            throw new IllegalStateException(
                    "The local federated account is incomplete");
        }

        return new LocalFederatedOidcUser(
                upstreamUser,
                localAccount.subject(),
                localAccount.authorities());
    };
}
~~~

This is an integration skeleton. In production, the directory must distinguish IdP errors, non-existent users, locked users, invalid tenants, and infrastructure failures. Do not auto-provision an account merely because upstream returns HTTP 200; verify the issuer allowlist, claim policy, and login eligibility.

### 5.4. Wiring custom OidcUserService into the login chain

~~~java
.oauth2Login(login -> login
    .userInfoEndpoint(userInfo -> userInfo
        .oidcUserService(federatedOidcUserService)
    )
)
~~~

Place this configuration in the `SecurityFilterChain` handling OAuth2 Login. Test that the `Authentication` after login has `LocalFederatedOidcUser` as its principal and `getName()` returns the local subject.

## 6. Issuing internal ID Tokens and access tokens

### 6.1. Internal ID Token created by the internal OP

When an internal RP requests OIDC with the `openid` scope and completes the Authorization Code Flow, Spring Authorization Server issues an internal ID Token.

The internal ID Token must contain:
- Internal issuer.
- Audience equal to the internal client ID.
- Subject equal to the local subject.
- Expiration and signature controlled by the internal Authorization Server.
- Nonce from the internal Authentication Request if that request included a nonce.
- Additional claims permitted by local policy.

Never copy protocol claims from the upstream ID Token into the internal ID Token. Claims `iss`, `sub`, `aud`, `exp`, `iat`, `nonce`, and `azp` of the internal token must describe the transaction between the internal OP and internal RP. The corresponding values in the upstream ID Token belong to a different transaction.

### 6.2. Adding local claims with OAuth2TokenCustomizer

SAS provides `OAuth2TokenCustomizer<JwtEncodingContext>` to customize JWTs. The example below loads data from the local user directory using the mapped principal name:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.oidc.endpoint.OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> internalTokenCustomizer(
        LocalUserDirectory localUserDirectory,
        ResourceAudiencePolicy resourceAudiencePolicy) {

    return context -> {
        boolean idToken = OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue());
        boolean accessToken = OAuth2TokenType.ACCESS_TOKEN.equals(
                context.getTokenType());

        if (!idToken && !accessToken) {
            return;
        }

        LocalUser user = localUserDirectory
                .findActive(context.getPrincipal().getName())
                .orElse(null);

        // client_credentials and other workload principals may not be local users.
        if (user == null) {
            if (idToken) {
                throw new IllegalStateException(
                        "An internal OIDC ID Token requires an active local user");
            }
            return;
        }

        if (idToken) {
            context.getClaims().subject(user.subject());
            context.getClaims().claim("tenant_id", user.tenantId());
            context.getClaims().claim("display_name", user.displayName());
        }

        if (accessToken) {
            context.getClaims().claim("tenant_id", user.tenantId());
            context.getClaims().audience(
                    resourceAudiencePolicy.audiencesFor(
                            context.getRegisteredClient(),
                            context.getAuthorizedScopes()));
        }
    };
}
~~~

The example adds only selected claims from the local directory. Do not place upstream email, groups, roles, or profile into every token by default. Each client and resource server has different needs; emit the minimum claims necessary.

In the example, `ResourceAudiencePolicy` is an application policy returning allowed audiences for the current client and scopes. Never directly use an arbitrary audience sent in the request. The customizer applies to JWTs; if using opaque access tokens, configure equivalent information in the token/introspection path. With `client_credentials`, the principal is typically a client rather than a local user, so the example skips local user claims for that grant.

If roles must be added to the access token, add only local authorities after policy validates tenant, resource, client, and consent. Never use upstream groups directly as API permissions.

### 6.3. Audience and scope of internal access tokens

Audience must reflect the target resource server. Example:

| API | Audience | Illustrative scopes |
|---|---|---|
| Orders API | https://orders.internal.example | orders.read, orders.write |
| Payroll API | https://payroll.internal.example | payroll.read |
| Profile API | https://profile.internal.example | profile.read, profile.update |

Do not issue a single overly broad-audience token just so a client can call many APIs. If a client needs multiple resources, evaluate resource indicators, token exchange, or separate audience-scoped tokens.

Internal Resource Servers must check the internal issuer and the API's own audience. If using JWTs, configure `JwtDecoder`/issuer validation and an appropriate audience validator. If using opaque tokens, introspection must point to the internal Authorization Server and the resource server client must be authenticated.

Example for the Orders API using JWT:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
NimbusJwtDecoder ordersJwtDecoder() {
    String issuer = "https://auth.internal.example";
    String audience = "https://orders.internal.example";

    NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withIssuerLocation(issuer).build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
        if (jwt.getAudience().contains(audience)) {
            return OAuth2TokenValidatorResult.success();
        }
        return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                        "invalid_token",
                        "The token is not intended for Orders API",
                        null));
    };

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(issuer),
                    audienceValidator));
    return decoder;
}
~~~

This example pins the issuer and audience per API. If an API serves multiple issuers, use a resolver with an allowlist and separate validator per issuer; never instantiate a decoder from an arbitrary `iss` inside a token. After verifying the token, the API proceeds to check scopes/authorities such as `SCOPE_orders.read`.

### 6.4. Do not confuse ID Tokens and access tokens

| Action | Appropriate token |
|---|---|
| Internal RP verifies user logged in | Internal ID Token or session created after OIDC login. |
| Internal RP calls Orders API | Internal access token with matching audience and `orders` scopes. |
| Internal Authorization Server calls upstream UserInfo/API | Upstream access token, if scopes/audience permit. |
| Internal Resource Server authenticates API request | Internal access token per issuer/audience policy. |
| Internal RP calls API with ID Token | Misuse; never use an ID Token as a Bearer access token. |

## 7. Two token stores with different responsibilities

### 7.1. OAuth2AuthorizedClientService

Spring Security OAuth2 Client uses `OAuth2AuthorizedClient` to bind tokens to a `ClientRegistration` and principal.

This data represents the internal Authorization Server's (or broker application's) authorization to access an upstream provider:
- Client registration ID.
- Principal name.
- Upstream access token.
- Upstream refresh token if issued by the provider.
- Expiration and related metadata.

`OAuth2AuthorizedClientRepository` stores authorized clients across web requests; `OAuth2AuthorizedClientService` manages them at the application level. `JdbcOAuth2AuthorizedClientService` can be used for durable storage.

### 7.2. OAuth2AuthorizationService

Spring Authorization Server uses `OAuth2AuthorizationService` to store authorizations issued by the internal Authorization Server:

- Internal registered client.
- Internal principal.
- Grant type.
- Authorized scopes.
- Internal authorization code.
- Internal access token.
- Internal refresh token.
- Internal OIDC ID Token and metadata.

### 7.3. Comparison table

| Service | Who issued the stored token? | Purpose |
|---|---|---|
| OAuth2AuthorizedClientService | Upstream IdP | Stores tokens the application uses when calling upstream provider APIs. |
| OAuth2AuthorizationService | Internal Authorization Server | Stores tokens/authorizations issued to internal OAuth2/OIDC clients. |

Both services may share a database, but must have separate tables, access permissions, and retention policies according to their roles.

Do not store upstream access tokens in `OAuth2AuthorizationService` as though they were issued by the internal AS. Likewise, do not use `OAuth2AuthorizedClientService` to store internal tokens for RPs.

## 8. When is the upstream access token needed?

### 8.1. Calling upstream APIs directly

If the internal application needs to read profile, group, or other data from an upstream API, use `OAuth2AuthorizedClientManager` to obtain the authorized client and send the right access token to the upstream resource server.

`RestClient` configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Bean
RestClient upstreamRestClient(
        OAuth2AuthorizedClientManager authorizedClientManager) {

    OAuth2ClientHttpRequestInterceptor interceptor =
            new OAuth2ClientHttpRequestInterceptor(
                    authorizedClientManager);

    return RestClient.builder()
            .requestInterceptor(interceptor)
            .build();
}
~~~

When calling, select the exact registration ID and principal so the manager uses the right authorized client. Do not enable automatic attachment of upstream tokens on every outbound request; doing so can send tokens to the wrong host.

You can retrieve the authorized client explicitly before calling the API:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

OAuth2AuthorizeRequest authorizeRequest =
        OAuth2AuthorizeRequest.withClientRegistrationId("corporate-idp")
                .principal(authentication)
                .build();

OAuth2AuthorizedClient authorizedClient =
        authorizedClientManager.authorize(authorizeRequest);

if (authorizedClient == null) {
    throw new IllegalStateException(
            "The upstream client could not be authorized");
}

String upstreamAccessToken =
        authorizedClient.getAccessToken().getTokenValue();

String profile = upstreamRestClient.get()
        .uri("https://api.corporate.example/v1/profile")
        .headers(headers ->
                headers.setBearerAuth(upstreamAccessToken))
        .retrieve()
        .body(String.class);
~~~

This snippet assumes `authentication` is the current principal and `upstreamRestClient` is used only for configured upstream hosts. `OAuth2AuthorizedClientManager` can use a refresh token to obtain a new access token when supported by the provider. Never accept an arbitrary target URL from a user and attach a bearer token to the request; restrict target hosts/paths via application configuration.

The explicit token retrieval example above does not need an interceptor to auto-attach the token. If choosing `OAuth2ClientHttpRequestInterceptor` instead, pass the registration ID and principal via request attributes or an explicitly configured resolver; do not both let the interceptor attach a token and manually set another Bearer header on the same request.

### 8.2. When is the upstream access token not needed?

If the goal is solely to authenticate users and let them use internal APIs, the internal Authorization Server can complete OIDC login and issue internal access tokens. There is no need to send the upstream access token to internal APIs.

This reduces coupling between internal APIs and the upstream IdP. Internal APIs need to trust only the internal issuer and the organization's token policies.

### 8.3. Do not forward upstream access tokens as internal credentials

Incorrect example:

~~~http
GET /api/orders HTTP/1.1
Host: orders.internal.example
Authorization: Bearer UPSTREAM_ACCESS_TOKEN
~~~

Unless the Orders API was explicitly designed to trust the upstream IdP's issuer and audience, this request must be rejected. Never relax a Resource Server to accept any issuer or any token with a valid signature.

## 9. Token Exchange between upstream IdP and internal Authorization Server

### 9.1. What problem does Token Exchange solve?

RFC 8693 defines OAuth 2.0 Token Exchange. An authenticated client sends a `subject_token` to the Authorization Server to request a new token for a different resource or audience.

Important parameters:
- `grant_type`: `urn:ietf:params:oauth:grant-type:token-exchange`.
- `subject_token`: token representing the subject.
- `subject_token_type`: type of the input token.
- `actor_token` and `actor_token_type`: actor identity if delegation is involved.
- `audience` or `resource`: target resource server.
- `scope`: desired permissions on the new token.
- `requested_token_type`: desired output token type.

Token Exchange is not an unconditional token swap. The Authorization Server must verify subject/actor tokens and enforce policies across client, subject, actor, resource, audience, and scope.

### 9.2. Spring Authorization Server 1.5.8 includes built-in Token Exchange

SAS 1.5.8 integrates RFC 8693 Token Exchange at the Token Endpoint. Default components include:

- `OAuth2TokenExchangeAuthenticationConverter`.
- `OAuth2TokenExchangeAuthenticationToken`.
- `OAuth2TokenExchangeAuthenticationProvider`.
- `OAuth2TokenGenerator`.
- `OAuth2AuthorizationService`.

A client using this grant must be registered with `AuthorizationGrantType.TOKEN_EXCHANGE`. The default Token Endpoint already includes the converter/provider for that grant type; there is no need to write a new converter just to parse RFC 8693 syntax.

`RegisteredClient` example:

~~~java
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;

RegisteredClient tokenBroker = RegisteredClient.withId("token-broker-registration")
        .clientId("internal-token-broker")
        .clientSecret(passwordEncoder.encode(tokenBrokerSecret))
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.TOKEN_EXCHANGE)
        .scope("orders.read")
        .scope("profile.read")
        .build();
~~~

This configuration merely permits the client to use the grant type. It does not automatically grant permission to exchange every token or target every audience. The provider still enforces validation and authorization policies.

### 9.3. Key limitation of the default Token Exchange

In SAS 1.5.8, `OAuth2TokenExchangeAuthenticationProvider` verifies subject/actor JWTs by looking up the token in the configured `OAuth2AuthorizationService`.

This means input tokens by default must belong to authorization state managed by the internal Authorization Server. An upstream ID Token or access token issued by an external IdP does not reside in the internal authorization store merely because it has a valid signature.

Spring Authorization Server has an open tracking request to support trusted external issuers in the default Token Exchange provider; current behavior remains limited to tokens found in `OAuth2AuthorizationService`. Therefore, do not assume enabling `TOKEN_EXCHANGE` is enough to exchange tokens from an external IdP.

There are two separate limitations to distinguish:

- The default Token Exchange converter in SAS 1.5.8 does not accept `subject_token_type=urn:ietf:params:oauth:token-type:id_token`; supported subject token types are JWT and access token per their respective standard URIs.
- Even for JWT/access token subject token types, the default provider still looks up the token in the internal `OAuth2AuthorizationService`. An upstream access token absent from that store will still not be accepted.

`OAuth2TokenExchangeAuthenticationProvider` is a `final` class, so it cannot be subclassed just to override one verification step. When supporting external issuers or ID Tokens is needed, the application must provide an appropriate converter/provider and register them through the Token Endpoint's extension points. Keep client authentication intact; never open a separate endpoint that bypasses protocol validation.

### 9.4. Illustrative Token Exchange request

Here is the RFC 8693 request shape when a client wants to exchange an upstream access token for an internal token:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.internal.example
Authorization: Basic BASE64_INTERNAL_BROKER_CREDENTIALS
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=UPSTREAM_ACCESS_TOKEN
&subject_token_type=urn:ietf:params:oauth:token-type:access_token
&audience=https%3A%2F%2Forders.internal.example
&scope=orders.read
~~~

**Note:** the request above shows only the protocol shape. With SAS 1.5.8's default provider, a subject token issued by an upstream IdP will not be accepted if it is not found in the internal `OAuth2AuthorizationService`. Supporting external issuers requires a custom trust/validation implementation.

### 9.5. When is a custom Token Exchange provider needed?

A custom provider is needed only when there is a genuine requirement to exchange tokens across security domains—for example, a gateway receiving an upstream access token that needs an internal token scoped to an internal API's audience.

A custom provider must:
1. Authenticate the OAuth2 client using standard client authentication mechanisms.
2. Verify the `RegisteredClient` is authorized to use token exchange.
3. Accept only token types allowed by policy.
4. Select the issuer from a preconfigured allowlist; never auto-discover an issuer from the token or request.
5. Verify signatures using trusted keys/JWKS, or call introspection with upstream client credentials if the token is opaque.
6. Validate issuer, audience, expiration, not-before, token purpose, and required claims.
7. Map the upstream identity by issuer and subject to a local subject.
8. Verify the actor token if the request involves delegation.
9. Restrict the requested resource, audience, and scopes per client and local authorization policy.
10. Mint the new token using the internal `OAuth2TokenGenerator`.
11. Persist the internal authorization via `OAuth2AuthorizationService`.
12. Return errors per RFC 8693 without leaking token or account details.

Never write a provider that accepts any JWT. Never fetch JWKS from an arbitrary URL inside a token. Never treat the `sub` claim as a global identifier without verifying `iss`.

### 9.5.1. Registering a custom converter/provider

SAS exposes the default converter and provider lists via `OAuth2TokenEndpointConfigurer`. Skeleton example:

~~~java
authorizationServerConfigurer.tokenEndpoint(tokenEndpoint -> {
    tokenEndpoint.accessTokenRequestConverters(converters ->
            converters.add(0, externalTokenExchangeConverter));

    tokenEndpoint.authenticationProviders(providers ->
            providers.add(0, externalTokenExchangeProvider));
});
~~~

`externalTokenExchangeConverter` and `externalTokenExchangeProvider` are application-implemented components. Place the custom converter/provider ahead of the defaults if they handle the same grant type. The custom provider must clearly identify which tokens fall under the external trust policy; for internal tokens, let the default provider handle them. Test both branches so the custom provider does not accidentally hijack all Token Exchange requests.

### 9.6. Impersonation and delegation

RFC 8693 distinguishes:

- **Impersonation:** the new token represents the subject; the target system processes the request as the subject acting within granted permissions.
- **Delegation:** the actor acts on behalf of the subject; the new token must represent both the subject and the actor per policy.

Delegation examples can use the `act` claim in a JWT. Do not blindly add `act` just because a client sends an `actor_token`; the Authorization Server must verify the actor and delegated permissions.

### 9.7. Token Exchange does not automatically link two token lifecycles

Exchanging a token is a separate event. RFC 8693 does not by default invalidate the subject token or automatically propagate every revocation event to the newly issued token.

If internal tokens must be invalidated when an upstream token is revoked, design dedicated mechanisms:
- Short token TTLs.
- Revocation events/notifications.
- Introspection or authorization state lookups.
- Local session/deprovisioning events.
- Mapping between external authorizations and internal authorizations to revoke per policy.

Never assume revoking an upstream token automatically revokes already-issued internal tokens.

## 10. Internal claims and permissions

### 10.1. Do not copy all upstream claims

Upstream claims may include:
- `email`, `name`, `preferred_username`.
- `groups`, `roles`, or `department`.
- `acr`, `amr`, `auth_time`.
- IdP-specific custom claims.

Each claim must be evaluated:
- Is it trustworthy for internal purposes?
- Does it need normalization or mapping?
- Should it be allowed in ID Tokens or access tokens?
- Can it change or be recycled?
- Is it sensitive or unnecessary for the target API?

Never copy upstream ID Token protocol claims such as `iss`, `sub`, `aud`, `exp`, `iat`, `nonce`, or `azp` into internal ID Tokens. Those values describe a different OIDC transaction.

### 10.2. Internal permissions come from local policy

For example, the upstream IdP returns group `CORP_FINANCE`. The internal directory can map it to local authority `FINANCE_USER` after checking:
- Exact issuer.
- Group belongs to a trusted namespace.
- User is active.
- Tenant mapping is valid.
- Client/resource is authorized to receive that role.

Never map a group to `ADMIN` solely based on the group's name. Never let an upstream IdP directly dictate scopes for all internal APIs.

### 10.3. Claims must fit each token

| Claim | Internal ID Token | Internal access token |
|---|---|---|
| sub | Local subject for the RP. | Local subject or workload principal per token policy. |
| aud | Internal client ID. | Internal API/resource. |
| tenant_id | Only when the RP needs and is permitted it. | When the API needs data partitioning. |
| roles | Can provide minimally to UI/RP if policy allows. | Only roles/scopes needed for API authorization. |
| email | Only when needed and permitted by consent/policy. | Usually unnecessary for API authorization. |
| upstream_issuer | Only with a clear audit/interoperability use case. | Avoid including if the API does not need it. |

## 11. Logout, revocation, and deprovisioning

### 11.1. Internal logout does not mean upstream logout

When a user logs out of the internal Authorization Server:
- The internal session must be terminated.
- Internal RPs must handle logout per configured flow.
- Internal refresh/access tokens must be handled per revocation policy.
- The upstream IdP session may still remain active.

If single logout across multiple systems is required, implement RP-Initiated Logout, Back-Channel/Front-Channel Logout, or the corresponding federation mechanism. Never assume logging out an internal session logs the user out of Google, Okta, or a corporate IdP.

### 11.2. Upstream token lifecycle

Upstream access/refresh tokens are managed according to the upstream provider's policy and Spring OAuth2 Client. When a user unlinks an identity or a token is revoked:
- Delete or revoke the local authorized client per policy.
- Stop using expired/revoked access tokens.
- Account for refresh token rotation and reuse detection per provider.
- Never write tokens to logs or telemetry.
- Never allow tokens to be shared between two users or two `ClientRegistration`s.

### 11.3. Deprovisioning must take effect internally

If an employee is locked in the IdP or local HR directory, the internal Authorization Server must define the source of truth and synchronization window:
- Reject new logins.
- Invalidate local sessions.
- Revoke refresh tokens and internal authorizations per policy.
- Update local permissions.
- Disable the federated identity if the link is revoked.
- Record an audit entry for the deprovisioning decision.

Do not wait until the upstream access token expires to revoke internal permissions if the organization requires immediate blocking.

## 12. Testing federation and token boundaries

### 12.1. Testing upstream OIDC login

- [ ] Issuer URI is in the allowlist.
- [ ] Discovery metadata is fetched from the right issuer.
- [ ] ID Token signature is verified with the issuer's key.
- [ ] `iss` exactly matches the configured issuer.
- [ ] `aud` contains the internal Authorization Server's client ID.
- [ ] `exp`, `iat`, `nonce`, and `azp` are validated per OIDC.
- [ ] UserInfo response `sub` matches ID Token `sub` when UserInfo is called.
- [ ] Callback URI is exact and PKCE/state are handled properly.
- [ ] Another IdP with the same `sub` is not conflated into the same user.

### 12.2. Testing local identity mapping

- [ ] The `(issuer, subject)` pair is unique.
- [ ] Local subject remains stable across multiple logins.
- [ ] Concurrent JIT provisioning does not create two local accounts for the same `issuer + subject`.
- [ ] One user can link multiple issuers per policy.
- [ ] Accounts are not auto-linked solely based on matching emails.
- [ ] Disabled/deprovisioned users cannot log in.
- [ ] Upstream groups/roles are mapped through an allowlist.
- [ ] Authorities of the local principal are vetted internal permissions.

### 12.3. Testing internal tokens

- [ ] Internal ID Token has the internal issuer.
- [ ] Internal ID Token has the internal client ID as audience.
- [ ] Internal ID Token `sub` is the local subject.
- [ ] Internal access token has the target API as audience.
- [ ] Internal Resource Server rejects tokens with the internal issuer whose audience is not meant for that API.
- [ ] Scopes and claims do not exceed local authorization policy.
- [ ] Internal Resource Server rejects upstream tokens when the issuer/audience is not configured as trusted.
- [ ] ID Tokens are not accepted as access tokens.
- [ ] No upstream `nonce`, `iss`, `aud`, or `exp` is mistakenly copied into internal tokens.

### 12.4. Testing Token Exchange

- [ ] Client is authenticated.
- [ ] `RegisteredClient` is permitted to use `TOKEN_EXCHANGE`.
- [ ] Input token matches allowed token type and issuer policy.
- [ ] Default converter rejects the ID Token token type; custom converter supports it only if designed by policy.
- [ ] Expired, wrong-audience, wrong-issuer, or revoked tokens are rejected.
- [ ] Default SAS provider accepts only tokens it can look up in `OAuth2AuthorizationService`.
- [ ] Custom external-issuer provider validates issuer allowlist and JWKS/introspection.
- [ ] Output audience/resource and scopes are constrained.
- [ ] Actor/delegation is validated when present.
- [ ] Internal authorization is persisted.
- [ ] Revocation propagation is tested if required by deployment.

### 12.5. Testing logout and deprovisioning

- [ ] Internal logout properly ends the local session.
- [ ] Upstream session is handled per federation requirements.
- [ ] Internal refresh tokens are revoked when a local user is deprovisioned.
- [ ] Upstream `OAuth2AuthorizedClient` is deleted/revoked upon unlinking.
- [ ] Logout/revocation behaves consistently across multiple application instances.
- [ ] Audit logs contain no raw tokens, client secrets, or unnecessary PII.

## 13. Common errors and troubleshooting

| Symptom | Cause | Resolution |
|---|---|---|
| Upstream login succeeds yet internal RP gets no code | Authorization Server failed to create local Authentication or session. | Check `SecurityFilterChain` ordering, `oauth2Login` callback, and session. |
| `invalid_issuer` | Issuer in ID Token differs from discovered/configured issuer. | Check issuer URI and provider configuration. |
| `invalid_audience` | Upstream ID Token was not intended for the internal Authorization Server's client. | Check client registration at the IdP and `aud`. |
| Two IdPs unintentionally create/share the same local user | Mapping relies only on email or `sub`. | Use `issuer + subject` and an explicit account linking workflow. |
| Internal ID Token contains upstream `sub` | Principal name was not mapped to the local subject. | Use a local `OidcUser` wrapper/identity mapping and test the `sub` claim. |
| Internal API receives upstream token and returns 401 | Token's issuer/audience does not belong to the internal API. | Use an internal access token or design token exchange. |
| Upstream API returns 401 | Using an internal token or an upstream token with the wrong audience/scope. | Select `OAuth2AuthorizedClient` for the right registration and resource. |
| Upstream token leaks via outbound request | `RestClient`/`WebClient` auto-attaches tokens to unintended hosts. | Select authorized client only on intended requests, restrict hosts, and redact logs. |
| Default Token Exchange rejects upstream token | Token does not exist in internal `OAuth2AuthorizationService`. | Use upstream login flow or a custom external-token exchange provider. |
| Token Exchange scopes too broad | Trusting requested scopes or upstream groups without local policy. | Intersect scopes across client, subject, resource, and authorization policy. |
| Locked user still calls API | Internal token/session still valid or deprovisioning out of sync. | Revoke local authorizations/sessions, shorten TTLs, and handle deprovisioning events. |
| Internal logout does not log out IdP | Two sessions belong to two different issuers. | Implement federated logout per requirements; do not assume it happens automatically. |
| Upstream token refresh fails | Token revoked, expired, or provider changed policy. | Remove faulty authorized client, require re-login, and audit. |

## 14. Hands-on exercise

**Scenario:** a company has a corporate IdP and an internal Authorization Server at `auth.internal.example`. Applications `employee-portal` and `mobile-app` must log in using the corporate IdP. The `orders` and `payroll` APIs trust only the internal issuer.

### Requirements

1. Register the internal Authorization Server as an OIDC client at the corporate IdP.
2. Configure `ClientRegistration` with `issuer-uri`, client ID, secret, and scope `openid`.
3. Configure two `SecurityFilterChain` beans: Authorization Server endpoints and OAuth2 Login.
4. Perform login and verify the upstream ID Token.
5. Create `FederatedIdentityDirectory` with unique key `issuer + subject`.
6. Map the upstream identity to a stable local subject.
7. Return `LocalFederatedOidcUser` with local authorities.
8. Configure `employee-portal` as an internal OIDC client.
9. Execute the Authorization Code Flow and verify the internal ID Token has the right issuer/audience/`sub`.
10. Issue an internal access token with audience `orders` API and scope `orders.read`.
11. Use `OAuth2AuthorizedClientManager` to call an upstream API with the upstream access token.
12. Verify the `orders` API rejects the upstream access token.
13. Register a client with `TOKEN_EXCHANGE` and test exchanging a token issued by the internal AS.
14. Attempt exchanging an upstream token and confirm the limitation of SAS 1.5.8's default provider.
15. Design a custom provider that accepts only allowlisted external issuers, validates JWT/introspection, and maps the subject to a local user.
16. Test account unlinking, logout, and deprovisioning.
17. Write a runbook for upstream issuer/key rotation, account linking, and revocation.

**Completion criteria:** internal RP receives internal ID Tokens; internal APIs receive internal access tokens; upstream APIs receive only upstream access tokens; identity mapping uses `issuer + subject`; tokens are stored in their respective services; external token exchange works only with custom trust validation.

## 15. Pre-production checklist

- [ ] Upstream issuers are in a configured allowlist.
- [ ] Client registration has the exact redirect URI.
- [ ] OIDC login uses the `openid` scope.
- [ ] Upstream ID Tokens are fully validated.
- [ ] Identity mapping uses `issuer + subject`.
- [ ] Local subject does not depend on email or display name.
- [ ] Account linking has proof and auditing.
- [ ] Local authorities are derived from internal policy.
- [ ] Internal issuer is stable and distinct from upstream issuers.
- [ ] Internal ID Token audience is the internal RP.
- [ ] Internal access token audience is the internal Resource Server.
- [ ] Upstream access tokens are sent only to matching upstream resources.
- [ ] `OAuth2AuthorizedClientService` and `OAuth2AuthorizationService` are used according to their respective roles.
- [ ] Upstream protocol claims are not copied into internal tokens.
- [ ] Internal APIs do not trust upstream issuers outside published policy.
- [ ] Token Exchange clients are granted least privilege.
- [ ] Subject/actor token lookup limits of SAS 1.5.8's default provider are understood.
- [ ] Custom external-token exchange enforces issuer allowlist, key/introspection validation, and audience/scope policy.
- [ ] Runbooks exist for refresh tokens, logout, revocation, and deprovisioning.
- [ ] Tokens and client secrets never appear in logs.
- [ ] Integration tests exist for login, token validation, token exchange, and multi-IdP mapping.
- [ ] Audit trail exists for account link/unlink and role mapping.
- [ ] Plans exist for handling upstream IdP outages and signing key rotations.

## Summary

In an identity federation model, the upstream IdP authenticates the user, while the internal Authorization Server is responsible for mapping the identity and issuing tokens per internal policy. Upstream ID Tokens are for the internal OAuth2/OIDC Client; upstream access tokens are for the upstream provider's APIs/resources. Internal ID Tokens are for internal RPs; internal access tokens are for internal Resource Servers.

Spring Authorization Server 1.5.8 provides official guidance to replace form login with OAuth2 Login and use OIDC social login. You can capture users, map claims, and build internal ID Tokens from local principals. Internal identities should be managed independently using the `issuer + subject` pair and a stable local subject.

SAS 1.5.8 also integrates RFC 8693 Token Exchange, but the default provider looks up subject/actor JWTs in the server's own `OAuth2AuthorizationService`. Consequently, tokens from external IdPs are not accepted automatically. If cross-issuer token exchange is required, build dedicated trust validation and authorization policies for external issuers, then issue new internal tokens with constrained audiences and scopes.

## References

1. [Spring Authorization Server 1.5.8 — How-to: Authenticate using Social Login](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-social-login.html): configuring `oauth2Login`, two `SecurityFilterChain` beans, capturing federated users, and mapping claims into internal ID Tokens.
2. [Spring Authorization Server 1.5.8 — Overview](https://docs.spring.io/spring-authorization-server/reference/overview.html): list of grant types and Token Exchange support.
3. [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): default Token Endpoint converters/providers and `OAuth2TokenExchangeAuthenticationProvider`.
4. [Spring Authorization Server 1.5.8 — OAuth2TokenExchangeAuthenticationToken API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/authentication/OAuth2TokenExchangeAuthenticationToken.html): subject token, actor token, audience, resource, and scope.
5. [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2Authorization` and `OAuth2AuthorizationService`.
6. [Spring Security — OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): OAuth2/OIDC login, `ClientRegistration`, and login processing.
7. [Spring Security — Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): `ClientRegistration`, `OAuth2AuthorizedClient`, `OAuth2AuthorizedClientService`, and `OAuth2AuthorizedClientManager`.
8. [Spring Security — Authorized Client Features](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): using `OAuth2AuthorizedClientManager` with `RestClient`/`WebClient`.
9. [OpenID Connect Core 1.0 incorporating errata set 2](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, issuer, subject, audience, and validation rules.
10. [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html): `subject_token`, `actor_token`, resource, audience, scope, impersonation, and delegation.
11. [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750.html): using bearer access tokens and protecting tokens in transit to resource servers.
12. [Spring Authorization Server GitHub issue #1867](https://github.com/spring-projects/spring-authorization-server/issues/1867): default provider limitation when subject/actor tokens are issued by trusted external issuers.
13. [Spring Authorization Server 1.5.8 — OAuth2TokenEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2TokenEndpointConfigurer.html): extension points for access token request converters and authentication providers.
14. [Spring Security 6.5 — OidcUser API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/oidc/user/OidcUser.html) and [IdTokenClaimAccessor API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/core/oidc/IdTokenClaimAccessor.html): distinguishing principal name from the upstream ID Token's subject claim.
15. [Spring Security 6.5 — Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html) and [NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): validating issuer, signature, expiration, and custom audience validators.
16. [Spring Authorization Server GitHub issue #1880](https://github.com/spring-projects/spring-authorization-server/issues/1880): ID Token token type limitation in the default Token Exchange converter.
