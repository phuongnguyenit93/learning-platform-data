# Mapping External Principals to Local Accounts and Subjects

## 1. Identity Federation in the Authorization Server architecture

Identity Federation is when a system accepts authentication results from another trust domain. The IdP is responsible for authenticating the user; the internal system decides which local account corresponds to them and which permissions are granted.

In this lesson, the upstream IdP uses OpenID Connect. The internal application acts simultaneously as:

- **OIDC client/RP:** redirects the user to the external IdP, receives the authorization response, and verifies the ID Token.
- **Identity broker:** maps the external principal to a local account.
- **Authorization Server:** uses the local account as the principal when processing authorization requests and issuing tokens to the system's RPs.

Identity Federation does not mean forwarding the IdP's raw access token to internal applications. Upstream tokens have their own audience, issuer, scope, and policies. The internal Authorization Server must issue its own tokens based on client registration, scope, consent, and local policy.

### 1.1. Overall flow

~~~mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant AS as Local Authorization Server
    participant IDP as External OIDC Provider
    participant MAP as Identity Mapping Service
    participant DB as Local Identity Store
    participant RP as Internal Relying Party

    B->>AS: GET /oauth2/authorize
    AS->>B: Redirect to External IdP
    B->>IDP: OIDC Authorization Request
    IDP->>B: Authorization Response
    B->>AS: Callback with authorization code and state
    AS->>IDP: Token Request
    IDP-->>AS: ID Token and Access Token
    AS->>AS: Verify ID Token and UserInfo
    AS->>MAP: Resolve (iss, sub)
    MAP->>DB: Find external_identity
    DB-->>MAP: Local account or unlinked
    MAP->>DB: Provision/link per policy if allowed
    MAP-->>AS: Local account principal
    AS->>AS: Create local authentication/session
    AS->>RP: Authorization Code / local ID Token
    RP->>AS: Token Request
    AS-->>RP: Local Access Token and ID Token
~~~

This flow involves two distinct token issuances:

1. The external IdP issues tokens to the internal OIDC client.
2. The internal Authorization Server issues tokens to the internal RP.

The RP only needs to know the issuer and subject of the internal Authorization Server. Which corporate IdP the user logged in with is handled at the federation layer.

### 1.2. Distinguishing the identifiers

| Value | Scope | Used for |
| --- | --- | --- |
| External `iss` | An OIDC Provider/realm | Identifies the issuer that authenticated the principal. |
| External `sub` | An issuer | Identifies the End-User within that issuer. |
| `registrationId` | Local OAuth2 Client configuration | Selects the connection configuration for an upstream IdP. |
| Local account ID | Internal database | Relationships, foreign keys, and internal business logic. |
| Local `sub` | Internal OIDC issuer | End-User identifier received by RPs in local ID Tokens. |

`registrationId` is a configuration name such as `corporate` or `partner-login`. It is not a protocol identifier and can change when refactoring configuration. The local account ID can be a UUID or database key. The local `sub` should be an opaque, stable, non-reusable identifier.

## 2. External identities must be identified by issuer and subject

OpenID Connect Core defines the `iss` and `sub` pair as the stable identifier that an RP can rely on. `sub` must be unique within the issuer, never reassigned to another End-User, and is a case-sensitive string. Claims like `email`, `phone_number`, `preferred_username`, and `name` do not carry the same guarantees of uniqueness or stability.

For example, two IdPs might both return:

~~~json
{
  "sub": "248289761001",
  "email": "alex@example.com"
}
~~~

If only `sub` is used as the key, two users from two different issuers could be merged by mistake. If only email is used, email changes or recycling can lead to account takeover.

The identifier key to store is:

~~~text
external_identity_key = (issuer, subject)
~~~

Example:

| Issuer | Subject | Result |
| --- | --- | --- |
| `https://idp-a.example.com` | `user-100` | External identity A |
| `https://idp-b.example.com` | `user-100` | External identity B |
| `https://idp-a.example.com` | `user-200` | External identity C |

These three pairs are three distinct external identities even though some subject values collide.

### 2.1. Use the verified issuer from the ID Token

Obtain the issuer from the ID Token after Spring Security has completed OIDC authentication and validation. Never accept `iss` from a query parameter, request body, arbitrary header, or browser-submitted profile.

The issuer must exactly match the configured/discovered issuer for the upstream provider. The path component of an issuer is also part of the identifier. For example, `https://login.example.com` and `https://login.example.com/tenant-a` are two different issuers.

Do not arbitrarily lowercase issuer/subject, strip paths or ports, remove slashes to merge issuers, or replace subject with email. If an organization changes issuers during a migration, handle it through a controlled linking/migration process.

### 2.2. Pairwise subjects from an upstream IdP

An OIDC Provider may issue different pairwise subjects for different sectors/clients to prevent RPs from correlating the same user's activity. Therefore, the same person may appear with two different external `sub` values if the system registers two OIDC clients belonging to two different sectors.

In that case, treat the two `iss`/`sub` pairs as two separate external identities. If they need to be attached to the same local account, require the user to authenticate and link explicitly. Never auto-merge them solely because their emails match.

## 3. Designing the local account and external identity store

The local account is the canonical source of truth for internal business logic. An external identity is merely a login method linked to an account.

One local account can link multiple external identities, such as a corporate account and a partner account, primary and backup IdPs, or multiple realms/tenants permitted by the organization.

### 3.1. Data model

Two main tables can be used:

~~~sql
CREATE TABLE local_account (
    id UUID PRIMARY KEY,
    subject_id VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(24) NOT NULL,
    display_name VARCHAR(200),
    email VARCHAR(320),
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE TABLE external_identity (
    id UUID PRIMARY KEY,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(255) NOT NULL,
    account_id UUID NOT NULL REFERENCES local_account(id),
    registration_id VARCHAR(100) NOT NULL,
    email_at_link VARCHAR(320),
    email_verified_at_link BOOLEAN NOT NULL DEFAULT FALSE,
    linked_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_authenticated_at TIMESTAMP WITH TIME ZONE,
    CONSTRAINT uq_external_identity_issuer_subject
        UNIQUE (issuer, subject)
);

CREATE INDEX ix_external_identity_account_id
    ON external_identity(account_id);
~~~

Meaning:

- `local_account.id` is the internal key for database relationships.
- `local_account.subject_id` is the local subject issued to RPs.
- `external_identity.issuer` and `external_identity.subject` form the unique key of the external identity.
- `external_identity.account_id` points to the local account.
- `registration_id` records which client configuration was used to log in; it is useful for operations but does not replace issuer/subject.
- `email_at_link` is a snapshot for auditing, not an identity key.

`sub` in OIDC does not exceed 255 ASCII characters. The issuer column length in the example is an implementation choice and should be adjusted to real issuer URIs. The database must compare issuer and subject case-sensitively; do not use case-insensitive collations or indexes that collapse these values.

### 3.2. Local subject must be stable and never reused

When creating a local account, generate an opaque subject, such as a UUID:

~~~java
String subjectId = UUID.randomUUID().toString();
~~~

Do not use email, phone number, username, or external `sub` as the local subject. Those values can change, be reused, or expose personal information.

When an external identity is unlinked, the local account retains the same `subject_id`. When a user moves from IdP A to IdP B, the system can link identity B to the existing account without changing the subject stored by RPs.

Never reuse a deleted account's local subject for another user. If account data must be deleted, retain a tombstone or minimal registry to ensure the old subject is never reissued.
## 4. Configuring OIDC Client to connect to an upstream IdP

Spring Security OAuth2 Client provides `ClientRegistration` and `ClientRegistrationRepository` to configure external providers.

Example configuring a corporate IdP via issuer discovery:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: local-authorization-server
            client-secret: <SECRET_FROM_SECRET_MANAGER>
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-idp:
            issuer-uri: https://idp.example.com
~~~

Key points:

- `openid` is the scope that enables OIDC authentication.
- `profile` and `email` request only the necessary claim sets.
- `client-secret` must come from a secret manager or secure configuration.
- Redirect URI must be registered with an exact match at the upstream IdP.
- `issuer-uri` must be an issuer trusted by the organization and verified via discovery.
- Never allow users to enter an arbitrary issuer URL for the system to auto-discover, as that can create SSRF and trust arbitrary providers.

Multiple `ClientRegistration` entries can be configured for multiple IdPs. Each registration can have different client IDs, secrets, redirect URIs, and scopes. Identity mapping still uses the verified issuer and subject.

### 4.1. Selecting providers by policy

Do not automatically accept any IdP submitted by a user. The list of allowed providers must be configured by administrators, including:

- verified issuer URI;
- registration ID;
- allowed tenant or user group;
- auto-provisioning policy;
- trusted email/group claim policy;
- MFA or authentication assurance requirements;
- whether the provider is active or revoked.

If a provider is disabled, block new logins and apply policy to previously issued sessions/tokens.

## 5. Integrating OidcUserService to map external principals

After OIDC authentication succeeds, Spring Security uses `OidcUserService` to load user information from the UserInfo Endpoint and build an `OidcUser`. You can delegate to the default implementation to keep protocol handling, then resolve the local account.

Never Base64-decode a JWT yourself and trust its claims. Signature, issuer, audience, expiration, nonce, and OIDC checks must complete before using the principal.

### 5.1. Creating a service to resolve external identities

Custom service example:

~~~java
@Component
public final class FederatedOidcUserService
        implements OAuth2UserService<OidcUserRequest, OidcUser> {

    private final OidcUserService delegate;
    private final ExternalIdentityService externalIdentityService;

    public FederatedOidcUserService(
            ExternalIdentityService externalIdentityService) {
        this.delegate = new OidcUserService();
        this.externalIdentityService = externalIdentityService;
    }

    @Override
    public OidcUser loadUser(OidcUserRequest request) {
        OidcUser externalUser = this.delegate.loadUser(request);
        OidcIdToken idToken = externalUser.getIdToken();

        String issuer = Objects.requireNonNull(idToken.getIssuer())
            .toString();
        String subject = Objects.requireNonNull(idToken.getSubject());

        String registrationId = request.getClientRegistration()
            .getRegistrationId();

        ExternalProfile profile =
            ExternalProfile.from(externalUser.getClaims());

        LocalAccount account = this.externalIdentityService.resolve(
            issuer,
            subject,
            registrationId,
            profile
        );

        if (!account.enabled()) {
            throw new OAuth2AuthenticationException(
                new OAuth2Error(OAuth2ErrorCodes.ACCESS_DENIED)
            );
        }

        return new FederatedLocalOidcUser(externalUser, account);
    }
}
~~~

This is the integration point between protocol identity and domain account:

1. Delegate handles OIDC user loading.
2. Extract `iss` and `sub` from the verified ID Token.
3. Extract `registrationId` to apply provider policy.
4. Convert allowed profile claims into `ExternalProfile`.
5. Resolve the external identity in the database.
6. Reject if the local account is locked, disabled, or not permitted to log in.
7. Return an OIDC principal attached with the local account; the success handler in section 6 converts it to a local authentication.

Do not use `registrationId` as the external identity key because registration names can change when configuration is reorganized.

### 5.2. Configuring the OIDC user service

Wire the service into `oauth2Login`:

~~~java
@Bean
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http,
        FederatedOidcUserService federatedOidcUserService)
        throws Exception {

    http
        .oauth2Login(oauth2 -> oauth2
            .userInfoEndpoint(userInfo -> userInfo
                .oidcUserService(federatedOidcUserService)
            )
        );

    return http.build();
}
~~~

This configures the filter chain handling web login. In an application with Spring Authorization Server, place this configuration in the application/login filter chain aligned with the matcher and ordering of the Authorization Server filter chain. Do not create overlapping matchers that cause the `/login/oauth2/code/*` callback to be intercepted earlier by another filter chain.

In a model using local subjects, also attach `LocalAccountAuthenticationSuccessHandler` as in section 6.2 to convert the external `OAuth2AuthenticationToken` to a local authentication after OIDC validation completes. Skipping this step may leave the Authorization Server receiving the external principal name.

## 6. Normalizing authentication into a local principal

After OIDC login, keep the external `OidcUser` as upstream identity evidence and resolve the local account. Do not mutate `getName()` or `sub` on the external `OidcUser` because they must continue accurately describing the upstream ID Token. After the callback, switch `Authentication` to a local principal so the Authorization Server uses the local subject.

The external OIDC user is wrapped alongside the local account so the success handler can switch to the local principal once the OIDC flow finishes:

~~~java
public final class FederatedLocalOidcUser implements OidcUser {

    private final OidcUser delegate;
    private final LocalAccount account;

    public FederatedLocalOidcUser(
            OidcUser delegate,
            LocalAccount account) {
        this.delegate = delegate;
        this.account = account;
    }

    @Override
    public String getName() {
        return this.delegate.getName();
    }

    @Override
    public Map<String, Object> getClaims() {
        return this.delegate.getClaims();
    }

    @Override
    public Map<String, Object> getAttributes() {
        return this.delegate.getAttributes();
    }

    @Override
    public OidcIdToken getIdToken() {
        return this.delegate.getIdToken();
    }

    @Override
    public OidcUserInfo getUserInfo() {
        return this.delegate.getUserInfo();
    }

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        return this.account.authorities();
    }

    public LocalAccount account() {
        return this.account;
    }
}
~~~

`FederatedLocalOidcUser` preserves the IdP's `getName()` and claims. This object merely attaches the local account so the success handler can complete the transition step.

### 6.1. Creating the local principal

Every local login method should produce a principal exposing the same subject:

~~~java
public interface LocalSubjectPrincipal {
    String subject();
}

public record LocalAccountPrincipal(
        UUID accountId,
        String subject)
        implements AuthenticatedPrincipal, LocalSubjectPrincipal {

    @Override
    public String getName() {
        return this.subject;
    }
}
~~~

`AuthenticatedPrincipal.getName()` returns the local subject. You can use `UsernamePasswordAuthenticationToken.authenticated(...)` to build the local authentication with authorities taken from the local account.

### 6.2. Converting OIDC authentication to local authentication

The success handler receives the verified OIDC authentication, extracts the attached local account, and saves a local authentication into the same SecurityContextRepository:

~~~java
@Component
public final class LocalAccountAuthenticationSuccessHandler
        implements AuthenticationSuccessHandler {

    private final SecurityContextRepository securityContextRepository;
    private final SavedRequestAwareAuthenticationSuccessHandler delegate =
        new SavedRequestAwareAuthenticationSuccessHandler();

    public LocalAccountAuthenticationSuccessHandler(
            SecurityContextRepository securityContextRepository) {
        this.securityContextRepository = securityContextRepository;
    }

    @Override
    public void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException {

        if (!(authentication instanceof OAuth2AuthenticationToken oauth2)
                || !(oauth2.getPrincipal() instanceof FederatedLocalOidcUser federated)) {
            throw new ServletException("Expected a federated OIDC principal");
        }

        LocalAccount account = federated.account();
        if (!account.enabled()) {
            SecurityContextHolder.clearContext();
            this.securityContextRepository.saveContext(
                SecurityContextHolder.createEmptyContext(), request, response
            );
            throw new ServletException("Local account is disabled");
        }

        Authentication localAuthentication =
            UsernamePasswordAuthenticationToken.authenticated(
                new LocalAccountPrincipal(account.id(), account.subject()),
                null,
                account.authorities()
            );

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(localAuthentication);
        SecurityContextHolder.setContext(context);

        this.securityContextRepository.saveContext(
            context, request, response
        );

        this.delegate.onAuthenticationSuccess(
            request, response, localAuthentication
        );
    }
}
~~~

Configure the application filter chain to use the same `SecurityContextRepository` for both the security context and OAuth2 login:

~~~java
@Bean
SecurityContextRepository securityContextRepository() {
    return new HttpSessionSecurityContextRepository();
}

@Bean
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http,
        SecurityContextRepository securityContextRepository,
        FederatedOidcUserService federatedOidcUserService,
        LocalAccountAuthenticationSuccessHandler successHandler)
        throws Exception {

    http
        .securityContext(context -> context
            .securityContextRepository(securityContextRepository)
        )
        .oauth2Login(oauth2 -> oauth2
            .securityContextRepository(securityContextRepository)
            .userInfoEndpoint(userInfo -> userInfo
                .oidcUserService(federatedOidcUserService)
            )
            .successHandler(successHandler)
        );

    return http.build();
}
~~~

The success handler must persist the context through the repository used by the filter chain. Otherwise, the local authentication may exist only during the callback request and vanish on the next request.

Spring Security stores `OAuth2AuthorizedClient` keyed by registration and upstream principal name during OAuth2 login; the default repository may hold tokens in the session. If the application needs to keep calling IdP APIs after switching to a local principal, design dedicated storage and loading for the authorized client keyed by external identity, and encrypt tokens when persisting. If not needed, delete the authorized client after federation completes or use a repository whose policy avoids long-term storage; do not assume tokens disappear on their own just because the application stops reading them.

### 6.3. Preserving local permissions

Local authorities must come from the internal account/policy. Never copy external authorities verbatim into the local authentication. If group mapping is needed, apply an allowlist in the mapping service before creating `LocalAccountPrincipal`.

Principals for password login, passkey, or SAML should also use `LocalAccountPrincipal` or implement the same contract so the Authorization Server always receives a local identity.

## 7. Resolving or provisioning the local account

An external identity may already be linked or not yet linked. The decision to create a new account must be based on issuer/tenant policy, not merely on whether the user has an email address.

### 7.1. Resolution flow

~~~mermaid
flowchart TD
    START["Verified OIDC authentication"] --> KEY["Build key (iss, sub)"]
    KEY --> LOOKUP{"External identity exists?"}
    LOOKUP -->|Yes| ACCOUNT["Load local account"]
    LOOKUP -->|No| POLICY{"Issuer trusted and auto-provision enabled?"}
    POLICY -->|No| LINK["Require invitation or account linking"]
    POLICY -->|Yes| CREATE["Create local account per tenant policy"]
    CREATE --> SAVE["Save external identity mapping"]
    SAVE --> ACCOUNT
    ACCOUNT --> ENABLED{"Account active?"}
    ENABLED -->|No| DENY["Deny login"]
    ENABLED -->|Yes| PRINCIPAL["Create local principal"]
    PRINCIPAL --> END["Complete local authentication"]
~~~

A domain-layer implementation can be expressed as follows:

~~~java
@Transactional
public LocalAccount resolve(
        String issuer,
        String subject,
        String registrationId,
        ExternalProfile profile) {

    ProviderPolicy policy =
        providerPolicyService.requireTrustedIssuer(issuer, registrationId);

    Optional<ExternalIdentity> existing =
        externalIdentityRepository.findByIssuerAndSubject(
            issuer, subject
        );

    if (existing.isPresent()) {
        return accountService.requireEnabled(
            existing.get().accountId()
        );
    }

    if (!policy.autoProvisioningEnabled()) {
        throw new AccountLinkingRequiredException();
    }

    LocalAccount account =
        accountProvisioningService.provision(policy, profile);

    externalIdentityRepository.insert(
        ExternalIdentity.create(
            issuer,
            subject,
            account.id(),
            registrationId,
            profile.email(),
            profile.emailVerified()
        )
    );

    return account;
}
~~~

This is a domain skeleton; add transaction boundaries, exception translation, auditing, and race condition handling according to your database.

### 7.2. Conditional auto-provisioning

Auto-provisioning can be appropriate when an organization manages a corporate IdP and wants eligible users to get a local account on first login.

Policy may require:

- issuer is in the allowlist;
- registration belongs to a permitted tenant;
- account belongs to an approved group or organizational unit;
- email is verified by an IdP trusted by the organization;
- an invitation or entitlement already exists;
- account has not been deprovisioned;
- provider is in an active state.

An email domain like `example.com` can be a secondary condition, but does not by itself prove a user is allowed to access a tenant. Outsiders can have emails on the same domain, or a domain may be shared across multiple organizations.

### 7.3. Handling concurrent first-time logins

Two initial callbacks for the same external identity can hit two nodes almost simultaneously. Both requests fail to find a mapping and both try to create an account.

A unique constraint on `(issuer, subject)` is the final safeguard. When a conflict occurs:

1. Roll back the conflicting account/link creation transaction.
2. Re-read the external identity in a new transaction.
3. Use the account created by the winning request.
4. Do not leave an orphan account behind as an independent login account.

You can use insert-on-conflict or a distributed lock if supported by the database. Do not rely solely on an application-level existence check because it does not eliminate race conditions.


## 8. Never auto-link accounts by email

This is one of the most dangerous mistakes in identity federation.

Suppose a local account already exists with email `alex@example.com`. A user logging in from another IdP also receives this email claim. If the system automatically attaches the new external identity to the existing account, that user can gain access to the account's data.

`email_verified=true` only indicates that the IdP verified the email according to the IdP's own policy. It does not automatically prove the logging-in user controls the existing local account or that the local account belongs to the same person.

### 8.1. Safe account linking rules

When an external identity is not yet linked:

- If no account exists and policy permits auto-provisioning, create a new account.
- If the email matches an existing local account, do not auto-link.
- If a user is currently logged into a local account and wants to add an IdP, require local account re-authentication.
- Authenticate the user with the new IdP in a separate linking flow.
- Confirm the external identity does not already belong to another local account.
- Record an audit event before completing the link.

### 8.2. Linking flow

~~~mermaid
sequenceDiagram
    participant U as User
    participant APP as Local Application
    participant IDP as External IdP
    participant DB as Identity Store

    U->>APP: Logged into local account A
    U->>APP: Select Link corporate identity
    APP->>APP: Re-authenticate and create linking state
    APP->>IDP: OIDC Authorization Request
    IDP-->>APP: Authenticated callback
    APP->>APP: Verify state, issuer, and subject
    APP->>DB: Check external identity is unlinked
    DB-->>APP: Not yet linked
    APP->>DB: Attach external identity to account A
    APP-->>U: Notify linking succeeded
~~~

Linking intent must be bound to the authenticated local account and browser session. Never take a target account ID from a query parameter and trust it directly.

If an external identity is already linked to account B, do not move it to account A automatically. Require an unlink/move workflow that verifies ownership of account B or a dedicated administrative process.

### 8.3. Account merging is a separate business process

If a user has two local accounts and wants to merge them, merging must evaluate:

- ownership of data and resources;
- tenant membership;
- consent and authorization history;
- subscriptions, billing, or business ownership;
- refresh tokens, sessions, and devices;
- auditing and retention rules.

Do not use account linking as an implicit merge operation.

## 9. Issuing local subjects in ID Tokens

Once the local principal is created, Spring Authorization Server must issue an ID Token whose `sub` is the local subject.

OIDC requires `sub` to identify the End-User within the scope of the issuer that issues the ID Token. Thus, if the local Authorization Server is the issuer trusted by RPs, the token's subject must belong to the local identifier domain.

### 9.1. Ensuring principal name is the local subject

`LocalAccountPrincipal.getName()` returns the local subject. Every authentication entering the Authorization Endpoint must have `Authentication.getName()` as the local subject, not the external `sub` or email.

To make the subject issuance policy explicit, you can add an `OAuth2TokenCustomizer<JwtEncodingContext>` for the ID Token:

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> localSubjectCustomizer() {
    return context -> {
        if (!OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            return;
        }

        Object principal = context.getPrincipal().getPrincipal();

        if (!(principal instanceof LocalSubjectPrincipal localPrincipal)) {
            throw new IllegalStateException(
                "ID Token requires a local subject principal"
            );
        }

        context.getClaims().subject(localPrincipal.subject());
    };
}
~~~

The customizer changes only the ID Token's `sub`. It does not alter the issuer, audience, nonce, issuance timestamps, or signature handled by the token generator. If the application supports multiple principal types, ensure all user authentications are converted to a local principal before reaching the Authorization Endpoint.

These examples use the token customizer API of Spring Authorization Server 1.5.x. When using Spring Security 7 with integrated Authorization Server, check the packages and dependencies against the BOM in use.

### 9.2. Do not issue external subjects as local subjects

Do not do this:

~~~java
context.getClaims().subject(externalIdToken.getSubject());
~~~

Doing so exposes upstream IdP identifiers to internal RPs. If the IdP changes, the upstream pairwise subject changes, or another provider is linked, the user's identity seen by RPs will change as well.

Issue the local subject stored in the local account. External issuer/subject are only needed in the identity store and internal audits.

### 9.3. Public subjects and pairwise subjects at the local OP

OIDC defines public and pairwise subject types:

- Public subjects provide the same subject to all clients.
- Pairwise subjects generate different subjects per sector to restrict clients from correlating the same End-User's activity.

If implementing public subjects, use the stable local `subject_id`. If pairwise subjects are needed, generate a separate mapping per account and sector/sector identifier, persisted durably so subjects do not change when secrets or algorithms are rotated. Never directly use an upstream pairwise subject as the local pairwise subject.

## 10. Building UserInfo responses from the local account

The local Authorization Server should return UserInfo from the local account. Do not forward the upstream IdP's raw UserInfo response to internal RPs.

Reasons:

- The upstream IdP may return claims the local RP is not permitted to receive.
- Email or name from the IdP may differ from verified local data.
- The local client's scopes/consent may differ from scopes requested from upstream.
- The local account may have been locked or had its tenant membership changed.
- UserInfo `sub` must match `sub` in the local ID Token.

### 10.1. UserInfo mapper

Spring Authorization Server provides `OidcUserInfoEndpointConfigurer.userInfoMapper(...)`. The mapper receives `OidcUserInfoAuthenticationContext` and can read the authenticated authorization and tokens.

Example:

~~~java
@Bean
Function<OidcUserInfoAuthenticationContext, OidcUserInfo>
        localUserInfoMapper(LocalAccountService accountService) {

    return context -> {
        OAuth2Authorization authorization =
            context.getAuthorization();

        OAuth2Authorization.Token<OidcIdToken> idTokenHolder =
            authorization.getToken(OidcIdToken.class);

        if (idTokenHolder == null) {
            throw new IllegalStateException(
                "Authorization does not contain an ID Token"
            );
        }

        String subject =
            idTokenHolder.getToken().getSubject();

        LocalAccount account =
            accountService.requireEnabledBySubject(subject);

        Set<String> scopes = authorization.getAuthorizedScopes();
        Map<String, Object> claims = new LinkedHashMap<>();

        claims.put("sub", subject);

        if (scopes.contains(OidcScopes.PROFILE)) {
            putIfPresent(claims, "name", account.displayName());
            putIfPresent(claims, "given_name", account.givenName());
            putIfPresent(claims, "family_name", account.familyName());
        }

        if (scopes.contains(OidcScopes.EMAIL)
                && account.email() != null) {
            claims.put("email", account.email());
            claims.put("email_verified", account.emailVerified());
        }

        return new OidcUserInfo(claims);
    };
}
~~~

Helper:

~~~java
private static void putIfPresent(
        Map<String, Object> claims,
        String name,
        String value) {

    if (value != null && !value.isBlank()) {
        claims.put(name, value);
    }
}
~~~

Wire the mapper into the Authorization Server OIDC configurer:

~~~java
authorizationServer.oidc(oidc ->
    oidc.userInfoEndpoint(userInfo ->
        userInfo.userInfoMapper(localUserInfoMapper)
    )
);
~~~

This is a fragment to integrate into the existing Authorization Server filter chain.

The OIDC UserInfo Endpoint also needs a `JwtDecoder` bean to verify Bearer access tokens per Spring Authorization Server's Resource Server configuration. If the endpoint returns authentication errors despite a valid mapper, check the decoder, issuer/JWK, and token audience.

### 10.2. Scopes and claims must be consistent

Example:

| Granted scope | Claims eligible to return |
| --- | --- |
| `openid` | `sub` |
| `profile` | `name`, `given_name`, `family_name`, `picture` if populated in local profile. |
| `email` | `email` and `email_verified` per local verification state. |

Do not return all claims merely because the upstream IdP provided them. Return only permitted local claims corresponding to the client's scopes/consent and disclosure policy.

In the UserInfo response, `sub` must exactly match the subject of the ID Token issued in that authorization. If an account is locked after tokens are issued, the mapper can reject or restrict data according to incident/session policy; never change the subject.

## 11. Mapping authorities and roles from the IdP

External IdPs may return OAuth scopes, group claims, application roles, tenant/organization claims, or authentication context like `acr` and `amr`. These values are not inherently internal permissions.

### 11.1. Use local roles as the source of truth

A safe option is for the local principal to contain only authorities fetched from the local account:

~~~java
@Override
public Collection<? extends GrantedAuthority> getAuthorities() {
    return this.account.authorities();
}
~~~

Spring Security uses authorities in `OAuth2AuthenticationToken` when performing application-level authorization. Therefore, if the wrapper returns authorities from the local account, internal policies do not depend directly on group strings sent by the IdP.

### 11.2. If group claims must be mapped

Use an allowlisted mapping table:

| Issuer | External group | Local authority | Tenant |
| --- | --- | --- | --- |
| Corporate IdP | `finance-readers` | `ROLE_FINANCE_VIEWER` | `tenant-a` |
| Corporate IdP | `finance-approvers` | `ROLE_FINANCE_APPROVER` | `tenant-a` |
| Partner IdP | `support-agents` | `ROLE_SUPPORT_AGENT` | `tenant-b` |

Do not map every group value to `ROLE_ + group`. A misconfigured or compromised IdP could send a group named `admin` and gain administrative privileges if trusted directly.

Mapping workflow:

1. Identify the trusted issuer.
2. Extract group claims from the verified ID Token/UserInfo.
3. Normalize per provider-specific policy.
4. Look up the administrator-approved mapping.
5. Check tenant membership.
6. Build local authorities from the mapping.
7. Audit if sensitive permissions are granted or modified.

### 11.3. Do not confuse upstream scopes with local roles

Scopes `openid profile email` only serve OIDC authentication and claim retrieval. They are not internal roles. Likewise, an upstream access token with scope `admin-api` does not mean the local account is allowed `ROLE_ADMIN`.

If the system needs to verify authentication assurance, `acr`/`amr` can be mapped according to configured policy and `auth_time` checked. Never elevate authentication assurance solely based on a claim string that the issuer is not authorized to assert.

## 12. Tenant mapping and data boundaries

A multi-tenant system must determine which tenant an account belongs to. Never infer tenant solely from an email domain or query parameter.

You can use:

- a dedicated issuer per tenant;
- provider policy binding a registration to a tenant;
- verified and allowlisted tenant claims;
- local invitation/organization membership;
- an admin approval workflow.

If one issuer serves multiple tenants, a local account may have multiple tenant memberships. External identity mapping still identifies the account by issuer and subject; tenant membership is a separate business relationship.

Example:

~~~text
External identity (issuer, subject)
              |
              v
        Local account
              |
              +---- Tenant A membership
              |
              +---- Tenant B membership
~~~

When a user logs in, the system must determine the tenant context before granting permissions. If the tenant context is requested by the client, verify the user actually holds membership in that tenant.

Do not add a browser-submitted tenant ID into the identity key to make one external identity masquerade as multiple users. If the upstream issuer has a dedicated realm path, the full issuer already distinguishes the realm.


## 13. Identity link lifecycle

Identity mappings must be managed as part of the account lifecycle.

### 13.1. Linking an additional IdP

- User is logged into the local account.
- Require re-authentication at the appropriate assurance level.
- Initiate OIDC flow with state/nonce bound to the linking intent.
- Verify the external ID Token.
- Verify the external identity does not already belong to another account.
- Save the mapping and audit.

### 13.2. Unlinking an IdP

Before unlinking:

- verify the account still has another login method;
- require re-authentication;
- check whether the external identity is the sole login method;
- invalidate upstream authorized client/sessions if needed;
- record an audit entry and notify the user.

Do not let a user unlink their sole login method and lose access to their account without a recovery process.

### 13.3. IdP deprovisioning

When an employee leaves or has access revoked at the IdP, the local system needs synchronization mechanisms:

- SCIM or provisioning events if supported by the organization;
- scheduled reconciliation;
- authenticated webhooks;
- checking account/entitlement status per policy.

Do not assume that a user not logging in for some period means the account was deleted. Upon receiving a deprovision event, disable the local account, revoke sessions/tokens per policy, and store an audit record.

### 13.4. Issuer or subject changes

If the IdP changes its issuer, realm, or subject format:

1. Identify the old and new identities through a trusted migration process.
2. Require re-authentication with the new IdP.
3. Verify ownership/access of the existing local account.
4. Create the new mapping to the existing account.
5. Retain old mapping history per retention/audit policy.
6. Never auto-merge by email.

OIDC requires issuers to keep subjects stable and never reassign them, yet cross-issuer migrations remain an event requiring explicit handling.

## 14. Critical security controls

### 14.1. IdP trust boundary

Trust only configured issuers. Discovery metadata and JWKS must be fetched from trusted endpoints. Never accept user-supplied issuers or tokens signed by keys not belonging to the registered issuer.

### 14.2. State, nonce, and authorization response

Preserve the checks performed by Spring Security OAuth2 Login:

- state bound to the authorization request;
- nonce in OIDC;
- registered redirect URI;
- authorization code flow and token response validation;
- ID Token issuer, audience, signature, and timestamps;
- UserInfo subject consistency.

Never write a simplified callback that just takes `code` and calls the token endpoint while skipping these validations.

### 14.3. Email and profile claims

- Never use email as the identity key.
- Update local email only according to issuer policy and verified status.
- Never automatically replace a locally verified email with an unverified claim.
- Never trust `preferred_username` as a unique username.
- Never render raw HTML from profile claims.
- Enforce length, character, and data format limits.

### 14.4. Session and token lifecycle

When a local account is disabled or an external identity is unlinked:

- block new logins;
- revoke local sessions per policy;
- revoke refresh tokens/authorizations when needed;
- account for how opaque/introspected tokens differ from offline-validated JWTs;
- invalidate/update account status caches;
- emit an audit event.

With JWTs verified offline by Resource Servers, changing account status in the database does not automatically invalidate already-issued JWTs. Use short TTLs, introspection, denylists, or a security epoch as required.

### 14.5. Do not store upstream tokens unnecessarily

If you only need authentication and profile retrieval at login time, do not persist upstream access/refresh tokens long-term. If calling IdP APIs after login is required:

- store authorized clients via Spring Security;
- encrypt tokens in the persistence layer;
- restrict read access to tokens;
- establish a refresh/revocation lifecycle;
- never embed upstream tokens into local access tokens;
- never log bearer tokens.

## 15. Testing identity mapping

Test both the mapping service and the full OIDC login flow.

| Scenario | Expected outcome |
| --- | --- |
| Linked issuer/subject pair | Resolves to the right existing local account. |
| Same subject but different issuer | Creates a different external identity; does not merge accounts. |
| Same email across two issuers | Does not auto-link. |
| Email changes while issuer/subject remain unchanged | Still resolves to the right local account. |
| Different subject with matching email | Not treated as the same external identity. |
| Issuer not in allowlist | Rejects login. |
| ID Token with invalid issuer/audience/signature/nonce | OIDC authentication fails. |
| Local account disabled | Rejects login even if upstream authentication succeeds. |
| Unlinked external identity, auto-provision off | Requires linking/invitation. |
| Unlinked external identity, auto-provision allowed | Creates local account per policy. |
| Two concurrent first-time callbacks | Only one mapping exists for issuer/subject. |
| External identity already belongs to another account | Rejects linking. |
| User attempts to link IdP using matching email | Does not auto-attach to existing account. |
| Group claim contains non-allowlisted admin | Does not grant local admin role. |
| Invalid tenant claim | Does not grant tenant membership. |
| Local ID Token issued | `sub` is the local subject. |
| UserInfo response | `sub` matches local ID Token and claims match scopes. |
| Account disabled after tokens issued | Session/tokens handled per revocation policy. |
| IdP deprovisioned | Blocks new logins; existing sessions/tokens handled per policy. |
| Issuer migration | New mapping linked only via verified process. |

### 15.1. Unit tests for identity keys

At minimum, assert:

~~~java
assertNotEquals(
    new ExternalIdentityKey("https://idp-a.example.com", "user-1"),
    new ExternalIdentityKey("https://idp-b.example.com", "user-1")
);

assertNotEquals(
    new ExternalIdentityKey("https://idp-a.example.com", "User-1"),
    new ExternalIdentityKey("https://idp-a.example.com", "user-1")
);
~~~

This test catches code that accidentally lowercases subjects or omits the issuer when constructing keys.

### 15.2. Integration tests for local subjects

1. Set up a test external IdP with a fixed issuer and subject.
2. Log in through Spring Security OIDC client.
3. Verify the external identity is saved and the local account is resolved.
4. Send an authorization request to the local Authorization Server.
5. Exchange the authorization code for an ID Token.
6. Decode and verify the signature of the local ID Token.
7. Verify `iss` is the local issuer and `sub` is the local subject.
8. Call the local UserInfo Endpoint with the access token.
9. Verify UserInfo `sub` exactly matches ID Token `sub`.
10. Change the upstream email and log in again; the local subject must remain unchanged.

## 16. Observability and operations

Useful events:

| Event/metric | Purpose |
| --- | --- |
| Federation login success/failure | Track login quality per issuer. |
| Unknown external identity | Detect new users needing provisioning/linking. |
| Account provisioning success/failure | Monitor onboarding. |
| Account linking/unlinking | Audit changes to login methods. |
| Disabled account login attempt | Detect out-of-sync IdP/local lifecycles. |
| External group mapping change | Control permission changes. |
| Issuer validation failure | Detect misconfigurations or untrusted tokens. |
| Duplicate identity conflict | Detect concurrent callbacks or inconsistent data. |
| Upstream token refresh failure | Monitor authorized clients if calling IdP APIs is needed. |

Log issuer and registration ID at an appropriate level, along with internal local account ID or correlation ID. Avoid logging raw ID Tokens, access tokens, refresh tokens, client secrets, unnecessary emails, or full claim sets.

With multiple Authorization Server instances:

- use a shared external identity store and local account database;
- ensure unique constraints are enforced at the database level;
- share the session store if sessions must span multiple nodes;
- synchronize provider policies and group mappings;
- invalidate caches when an account is disabled or an identity is unlinked;
- monitor upstream discovery/JWKS and key rotation schedules.

## 17. Common mistakes

### 17.1. Using email as the identity key

When emails change or are recycled, the system can mistakenly merge two users. Use issuer and subject.

### 17.2. Using registration ID as the identity key

Registration ID is local configuration, can change, and multiple registrations may point to the same issuer. Obtain the issuer from the verified ID Token.

### 17.3. Using the external subject as the local subject

Internal RPs become coupled to the IdP and upstream pairwise subjects. Issue subjects from the local account.

### 17.4. Changing subject only in ID Token while forgetting UserInfo

UserInfo `sub` must match ID Token `sub`. Configure the local UserInfo mapper with the same local subject policy.

### 17.5. Returning raw upstream claims to RPs

This can leak claims beyond consent or diverge from the local profile. Use the UserInfo mapper and authorized scopes.

### 17.6. Trusting group claims as local roles

A group claim sent by an IdP does not automatically equate to a local role. Use tenant-scoped allowlist mappings.

### 17.7. Auto-linking via email_verified

A verified email does not replace proof that the user owns the local account. Require local re-authentication and an explicit linking flow.

### 17.8. First two logins creating two local accounts

Missing unique constraint or conflict handling. Enforce unique issuer/subject and retry/reload after transaction conflicts.

### 17.9. Disabled accounts still able to log in

Checking only upstream authentication without checking local account status. Check local status on every federated login and enforce deprovisioning policy.

### 17.10. Changing issuer without migrating mappings

The same subject under a new issuer is a different external identity. Use a verified re-linking/migration workflow.

## 18. Implementation checklist

- [ ] Configure only issuers trusted by the organization.
- [ ] Use OIDC Authorization Code flow and preserve state/nonce validation.
- [ ] External identity key is the issuer and subject pair from the verified ID Token.
- [ ] Issuer and subject are compared exactly and case-sensitively.
- [ ] Registration ID is used only to select provider/configuration.
- [ ] Local account has its own internal key.
- [ ] Local subject is opaque, stable, and never reused.
- [ ] Unique constraint exists on external issuer/subject.
- [ ] Foreign key exists from external identity to local account.
- [ ] OidcUserService delegates to the default implementation before resolving the local account.
- [ ] Local principal returns the local subject from getName().
- [ ] All other authentication methods are also normalized into the local principal.
- [ ] Local ID Token issues the local `sub`.
- [ ] Local UserInfo returns `sub` matching the ID Token.
- [ ] Local UserInfo returns only claims permitted by scope/consent.
- [ ] Never use email or preferred_username as the identity key.
- [ ] Never auto-link existing accounts solely because emails match.
- [ ] Linking requires re-authentication and session-bound linking intent.
- [ ] Auto-provisioning enforces issuer/tenant/invitation policy.
- [ ] Group/role mappings have an allowlist and tenant boundary.
- [ ] Account disablement/deprovisioning is applied to sessions/tokens.
- [ ] Concurrent callbacks and unique constraint conflicts are handled.
- [ ] Auditing exists for link, unlink, provision, and deprovision events.
- [ ] Upstream tokens are stored securely and only when strictly necessary.
- [ ] Tests cover multiple issuers, subject casing, email collisions, and subject migration.
- [ ] Integration tests prove local ID Token and UserInfo use the same subject.

**Key takeaway:** The IdP authenticates the external identity; the local system decides the account and internal permissions. Store external identities by the issuer/subject pair, link them to a local account, and issue a stable local subject to RPs. Email and group claims are policy inputs, not default internal identifiers or permissions.

## 19. References

- [OpenID Connect Core 1.0 — ID Token and Subject Stability](https://openid.net/specs/openid-connect-core-1_0.html): `iss`, `sub`, claim stability/uniqueness, and subject identifier types.
- [Spring Security — Advanced OAuth2 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService`, `OAuth2UserService`, authority mapping, and OIDC login extension points.
- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `OAuth2TokenCustomizer`, `JwtEncodingContext`, and token generation.
- [Spring Authorization Server — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): `OidcUserInfoAuthenticationContext` and `userInfoMapper`.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): configuring the UserInfo Endpoint and extension points.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): client registration, authorized clients, and OAuth2/OIDC client integration.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): JWT structure and claim semantics.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): current best practices for OAuth 2.0 security.


