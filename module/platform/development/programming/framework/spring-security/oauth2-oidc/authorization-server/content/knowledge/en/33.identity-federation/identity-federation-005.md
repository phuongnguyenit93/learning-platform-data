# Issuing Internal Claims from External Identities by Policy

## 1. Why must federated identities be mapped?

An internal Authorization Server may rely on an external Identity Provider (IdP) to authenticate users: an enterprise identity provider, a partner, or another OpenID Provider. The external IdP authenticates the user and returns an ID Token along with claims such as **sub**, **email**, **groups**, **department**, or **acr**.

The internal Authorization Server must still decide for itself which internal identity is logging in, which tenant that person belongs to, what roles they hold, and which claims clients may receive. External claims are input data from another trust domain. They must be verified, linked to an internal account, and transformed according to policy before being used to issue tokens.

This lesson belongs to the **Identity Federation** chapter of the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module. It focuses on federated login via OpenID Connect, mapping external claims into internal identities/authorities, and issuing ID Tokens, access tokens, and UserInfo from Spring Authorization Server 1.5.8.

This lesson covers **federated authentication and claim transformation** at runtime. It is not an implementation guide for the OpenID Federation 1.0 trust framework with Entity Statements, Trust Marks, or Federation Operators.

After this lesson, you will be able to:
1. Distinguish upstream IdPs, the downstream Authorization Server, clients, and Resource Servers.
2. Understand the OIDC Login flow when an Authorization Server uses an external IdP to authenticate users.
3. Use the issuer/subject pair to link external identities to internal accounts.
4. Build policies to allow, normalize, map, and reject claims.
5. Use Spring Security `OidcUserService` to link users and create internal principals.
6. Map external groups to internal authorities via an allowlist.
7. Issue internal claims into ID Tokens, access tokens, and UserInfo using Spring Authorization Server extension points.
8. Protect tenant isolation, account linking, claim freshness, and personal data.
9. Test upstream authentication, mapping, and token issuance end-to-end.

## 2. Roles in the identity federation model

| Component | Role | Responsible data |
| --- | --- | --- |
| **Upstream Identity Provider** | Authenticates external users | ID Token, UserInfo, and source claims |
| **Internal Spring Authorization Server** | Acts as downstream OP/AS for the internal system | Internal subject, tenant, roles, entitlements, and internal tokens |
| **OAuth2/OIDC Client** | Requests login and receives tokens from the internal AS | Claims issued by the internal AS |
| **Resource Server** | Verifies internal access tokens and enforces authorization | Audience, scopes, and internal authorization claims |
| **Internal Identity Directory** | Source of truth for internal identity and permissions | Account status, tenant membership, roles, profile, and policy |

The upstream IdP answers the question: "In which external trust domain was the user authenticated?" The Internal Identity Directory answers the question: "Which internal account is that user, and what are they currently allowed to do?"

Do not let the upstream IdP dictate all internal permissions merely through a `groups` or `roles` claim. The internal AS needs its own policy to define which data is trusted, how it is transformed, and what scope of claims is released.

## 3. Authentication and token issuance flow

~~~mermaid
sequenceDiagram
    autonumber
    participant U as Browser / User
    participant C as Internal Client
    participant AS as Internal Authorization Server
    participant IDP as External OIDC Provider
    participant DIR as Internal Identity Directory

    C->>AS: Authorization Request
    AS->>AS: No local authenticated session
    AS-->>U: Redirect to upstream IdP
    U->>IDP: OIDC Authorization Request
    IDP-->>U: Redirect with authorization code
    U->>AS: Callback with code
    AS->>IDP: Token Request
    IDP-->>AS: ID Token + Access Token
    AS->>AS: Validate upstream ID Token
    AS->>IDP: UserInfo request (if configured)
    IDP-->>AS: External claims
    AS->>DIR: Resolve (issuer, registration, subject)
    DIR-->>AS: Internal account + policy + authorities
    AS->>AS: Establish internal authenticated session
    AS-->>C: Authorization code
    C->>AS: Token Request
    AS->>AS: Build claims from internal policy
    AS-->>C: Internal ID Token + Access Token
~~~

Main sequence:

1. The client sends an Authorization Request to the internal Authorization Server.
2. If there is no local authenticated session, Spring Security redirects the browser to the upstream IdP via OIDC Login.
3. The AS receives the authorization code from the upstream IdP and exchanges it for tokens.
4. Spring Security verifies the ID Token according to the Client Registration configuration and may call the UserInfo Endpoint.
5. `OidcUserService` receives the external identity and looks up or provisions the internal account per policy.
6. The AS creates a local authenticated principal attached to the internal account and authorities.
7. Spring Authorization Server resumes the Authorization Code flow for the internal client.
8. When exchanging the code for tokens, the AS issues new tokens with an issuer, subject, and claims belonging to the internal trust domain.

**The upstream ID Token must not be forwarded verbatim to the internal client.** That token carries an issuer and audience meant for the internal AS's client registration at the upstream IdP. The internal AS must issue a new ID Token under its own issuer and subject.

The upstream access token is a credential used by the internal AS to call the upstream IdP's APIs per granted permissions. Do not pass this token to internal clients as the system's access token. If downstream needs to access upstream resources on behalf of the user, design dedicated delegation/token exchange with explicit audience, scope, and consent.

## 4. Distinguishing external claims from internal claims

External claims describe what the upstream IdP knows or asserts. Internal claims describe the identity and authorization decisions the internal AS is responsible for.

| Group | Examples | Trusted source | Usage |
| --- | --- | --- | --- |
| External identity | iss, sub | Verified ID Token | Links the external identity |
| Contact/profile | email, email_verified, name, locale | IdP per trust policy | Hints or profile synchronization |
| External organization | groups, department, organization | External IdP/Directory | Transformed via mapping policy |
| Authentication context | acr, amr, auth_time | IdP if semantics are agreed | Evaluates assurance per authentication policy |
| Internal identity | sub, internal_user_id | Internal Identity Directory | Identifies user within internal AS |
| Internal authorization | roles, tenant_id, entitlements | Internal policy engine/directory | Grants permissions to clients and Resource Servers |
| Account lifecycle | account_status, disabled_at | Internal account system | Blocks login/token issuance |

Claims with the same name do not necessarily share the same semantics. For example, `groups` from an external IdP do not automatically equate to internal system roles. `department` is not necessarily a tenant. `email_verified=true` is only an issuer assertion; the internal AS must decide whether to accept that assertion for a specific purpose.

## 5. Identifying external identities by issuer and subject

With OIDC, a user's stable identifier at an issuer is the pair:

~~~text
external_identity = (issuer, subject)
                  = (iss, sub)
~~~

OIDC Core specifies that `sub` is a unique identifier within the issuer's scope and is never reassigned to another user. The `iss` and `sub` pair is the stable identifier a Relying Party can rely on. Claims such as email, phone number, preferred username, and name do not carry the same stability or uniqueness guarantees.

Never use email as the primary key to automatically link accounts. Emails can change, be recycled, or appear across multiple trust domains. Even when `email_verified=true`, email remains a contact attribute, not an external subject identifier.

### 5.1. Pairwise subjects and multiple Client Registrations

Some IdPs use pairwise subject identifiers: the same user can receive different `sub` values for different clients or sectors. Therefore, if the internal AS configures multiple upstream Client Registrations pointing to the same issuer, the linking key should also retain the registration/sector context.

Schema example:

~~~text
external_identity
-----------------
id
issuer
subject_scope_key
upstream_registration_id
subject
internal_user_id
linked_at
link_method
status
UNIQUE(issuer, subject_scope_key, subject)
~~~

If the issuer uses public subjects, `subject_scope_key` can be a fixed value like `public`; the `(iss, sub)` pair remains the OIDC identifier. With pairwise subjects, `subject_scope_key` is the corresponding sector identifier. Registration ID remains useful for auditing and configuration lookup, but registrations sharing the same sector can share the same subject identity; do not create distinct keys merely because their registration IDs differ.

Do not arbitrarily normalize `iss` by stripping paths, changing case, or removing trailing slashes. Compare issuers against the configured and verified value; issuers are case-sensitive.

### 5.2. Internal subjects must be managed by the internal AS

The internal AS needs a stable internal user ID, such as a UUID or opaque identifier. Internal ID Tokens should use this internal subject as `sub`, per the AS's subject identifier policy.

Do not copy the external `sub` into the local `sub` by default. Doing so exposes the upstream IdP's identifier, causes collisions across issuers, and complicates consolidating multiple identity sources.

## 6. Account linking and Just-in-Time Provisioning

When a user logs in for the first time from an IdP, the AS must decide how the external identity can be linked to an internal account.

| Strategy | How it works | Control conditions |
| --- | --- | --- |
| Pre-provisioned linking | Administrators link external identities to internal accounts beforehand | Suits workforce/partners with onboarding workflows |
| Just-in-Time (JIT) provisioning | Creates an internal account on the user's first login | Enable only for allowlisted issuers, domains, tenants, and profiles |
| Explicit account linking | User logs into an internal account and authenticates an additional external identity | Requires re-authentication/step-up and auditing |
| Directory synchronization | Syncs accounts and groups from the source system via SCIM or connectors | Requires workflows for disablement, renames, transfers, and deletion |

JIT provisioning does not mean automatically attaching an external identity to an existing account by email. When no linked external identity is found:
- If policy requires pre-provisioning, reject login and direct to onboarding.
- If JIT is permitted, create a new internal account in the tenant determined from a trusted source.
- If a candidate internal account shares the same email, require a verified account linking workflow.
- If the issuer is not in the allowlist, reject before creating an account.

When linking two accounts, authenticate control over both the internal account and the external identity. Never let someone who gained control of another person's email attach their own IdP to that account solely via an email claim.

## 7. Designing a Claim Mapping Policy

Claim mapping should be a versioned, auditable policy rather than a series of `if` statements scattered across controllers.

A policy must define:

1. **Issuer allowlist:** which issuers are permitted to supply identities.
2. **Client registration:** which upstream registration is used and which sector/tenant corresponds to it.
3. **Source claims:** which claims are read from the ID Token or UserInfo.
4. **Trust level:** whether the claim is verified, how fresh it is, and whether the issuer is authorized to assert it.
5. **Transformation:** normalizing data types, names, group codes, locales, and values.
6. **Target claim:** which internal attributes are updated or created.
7. **Conflict resolution:** when external claims differ from internal data, which source takes precedence.
8. **Authorization mapping:** which groups/attributes can produce internal roles or entitlements.
9. **Release policy:** which clients receive which claims, under which scopes and purposes.
10. **Lifecycle:** how claims are refreshed, revoked, or expired.

### 7.1. Mapping matrix example

| External claim | Acceptance condition | Internal representation | Rule |
| --- | --- | --- | --- |
| iss + sub | Valid ID Token, allowlisted issuer | external_identity link | Never substitute with email |
| email | Trusted issuer and valid value | contact_email | Never use as primary key |
| email_verified | Issuer with agreed semantics | contact_email_verified | Never self-elevate permissions |
| groups | Group ID in allowlist | internal_roles | Map by issuer + group ID |
| department | Department code recognized by directory | org_unit_id | Never infer tenant automatically |
| tenant / organization | Code mapped to internal tenant | tenant_membership | Verify internal membership |
| acr / amr | Issuer and semantics evaluated | authentication_assurance | Use only in authentication policy |
| name | Valid claim | display_name | Profile data, not for authorization |

### 7.2. Precedence order when claims conflict

You can apply the following precedence order:

~~~text
Internal security policy / account state
              |
Internal identity directory
              |
Approved federation mapping
              |
Verified upstream profile claims
              |
Unverified / unknown external claims
~~~

Internal account status, tenant membership, roles, and entitlements must be decided by an authoritative internal source. External IdPs are only allowed to update explicitly delegated attributes. Claims not covered by the mapping policy must be ignored or fail the request depending on criticality.

Do not overwrite internal values merely because the upstream IdP sends a claim with the same name. For instance, if internal `tenant_id` is managed by provisioning, never take `tenant_id` from the request or external claims to replace it.

## 8. Mapping external groups to internal authorities

External groups typically have IdP-specific structures: group names, object IDs, DNs, or URIs. Internal applications have their own roles/permissions. An explicit mapping table is required:

~~~text
federation_group_mapping
------------------------
issuer
upstream_registration_id
external_group_id
internal_role
policy_version
enabled
UNIQUE(issuer, upstream_registration_id, external_group_id, internal_role)
~~~

Example:

| Issuer | External group ID | Internal role |
| --- | --- | --- |
| https://idp.corp.example | grp-finance-readers | FINANCE_VIEWER |
| https://idp.corp.example | grp-order-approvers | ORDER_APPROVER |
| https://partner-id.example | p-ops-01 | PARTNER_OPERATIONS |

Do not directly turn a value like `admin`, `superuser`, or `ROLE_ADMIN` from an upstream claim into internal administrative privileges. Mappings must be keyed by issuer, registration, group ID, and approved status. Deleted or disabled groups must update internal authorities within the defined SLA.

If upstream group claims are too large or unsuitable for inclusion in tokens, use SCIM/directory synchronization to store memberships internally. During login, read only the synchronized internal memberships and check their current status.

## 9. Configuring Spring Security as an OIDC Client to an upstream IdP

Spring Authorization Server handles protocol endpoints, while Spring Security handles user login. OIDC Login can be configured on the security filter chain for the internal web application.

External IdP configuration example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
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
            issuer-uri: https://idp.corp.example
~~~

`issuer-uri` enables Spring Security to discover the upstream provider's metadata. Client ID, secret, redirect URI, and scopes must match the registration at the IdP. Request only the scopes needed for claim mapping; do not request permissions to read groups or sensitive data unless required by policy.

The client ID and client secret placeholders in the example come from a secret manager or environment-specific configuration. Never store raw secrets in Git. The redirect URI is rendered from the application's base URL and registration ID; reverse proxies must forward scheme/host accurately so the callback matches the URI registered at the upstream IdP.

Example security filter chain for web login:

~~~java
@Bean
@Order(2)
SecurityFilterChain defaultSecurityFilterChain(
        HttpSecurity http,
        OAuth2UserService<OidcUserRequest, OidcUser> federatedOidcUserService)
        throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/assets/**", "/error").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2Login(oauth2 -> oauth2
            .userInfoEndpoint(userInfo -> userInfo
                .oidcUserService(federatedOidcUserService)
            )
        );

    return http.build();
}
~~~

In an application with multiple security filter chains, the chain for Authorization Server endpoints must be ordered first with its own matcher. The web login chain handles `/login`, `/oauth2/authorization/{registrationId}`, and the callback `/login/oauth2/code/{registrationId}`. The example above illustrates only the login chain; combine it with the protocol endpoints chain, issuer, JWK, and foundational Authorization Server beans.

Spring Security validates the upstream ID Token per the OIDC client registration, including signature, issuer, audience, expiration, and nonce for the flow. If calling the UserInfo Endpoint, `OidcUserService` uses the upstream access token to fetch additional claims; the `sub` claim in UserInfo must match `sub` in the ID Token. Never Base64-decode a JWT yourself and trust its payload.

## 10. Using OidcUserService to link external identities

`OidcUserService` is the appropriate extension point to:
- Call the default implementation to verify and load the OIDC user.
- Extract issuer and subject from the verified ID Token.
- Look up the external identity link.
- Perform JIT provisioning if permitted by policy.
- Retrieve internal authorities from the account/policy engine.
- Construct a principal with a stable name using the internal user ID.

Skeleton example:

~~~java
@Bean
OAuth2UserService<OidcUserRequest, OidcUser> federatedOidcUserService(
        FederatedIdentityService identityService) {

    OidcUserService delegate = new OidcUserService();

    return userRequest -> {
        OidcUser upstreamUser = delegate.loadUser(userRequest);

        String issuer = upstreamUser.getIdToken().getIssuer().toString();
        String subject = upstreamUser.getSubject();
        String registrationId =
                userRequest.getClientRegistration().getRegistrationId();

        InternalAccount account = identityService.resolveOrProvision(
                issuer,
                registrationId,
                subject,
                upstreamUser.getClaims()
        );

        if (!account.enabled()) {
            throw new OAuth2AuthenticationException(
                    new OAuth2Error(OAuth2ErrorCodes.ACCESS_DENIED)
            );
        }

        Set<GrantedAuthority> authorities = account.authorities().stream()
                .map(SimpleGrantedAuthority::new)
                .collect(Collectors.toUnmodifiableSet());

        Map<String, Object> principalClaims = new HashMap<>();
        principalClaims.put("sub", subject);
        principalClaims.put("internal_user_id", account.id().toString());

        OidcUserInfo principalUserInfo = new OidcUserInfo(principalClaims);

        return new DefaultOidcUser(
                authorities,
                upstreamUser.getIdToken(),
                principalUserInfo,
                "internal_user_id"
        );
    };
}
~~~

`FederatedIdentityService` is an application-implemented business service. It must:
1. Accept only configured trusted issuers.
2. Look up the external identity by issuer, sector/registration context, and subject.
3. If not found, apply pre-provisioning/JIT policy.
4. Check that the internal account is active and not locked.
5. Pass external claims through a versioned mapping policy.
6. Compute authorities from the internal directory and policy.
7. Record an audit entry for the link/provision and login event.

In the example, `DefaultOidcUser` uses the `internal_user_id` claim as `getName()`. Thus the principal seen by Spring Authorization Server has the internal user ID as its name. `sub` in the upstream ID Token remains the external subject and is used only in the linking table. Never take all external claims and place them verbatim into internal tokens.

The `OidcUserInfo` constructed for the internal principal retains `sub` equal to the subject in the upstream ID Token for consistency with the ID Token verified by Spring Security. The `internal_user_id` claim serves solely as the name attribute for the local principal. When SAS generates a new ID Token, this principal name becomes the internal subject of the internal system.

This code snippet is an illustrative skeleton; types like `InternalAccount`, `FederatedIdentityService`, and exception handling must be defined per your domain. If the application needs to retain upstream UserInfo for display, store/read it via a controlled profile service; never use that raw claim set as the authorization context.

## 11. Choosing between OidcUserService and GrantedAuthoritiesMapper

Spring Security offers two common ways to translate external authorities:

| Extension point | When suitable | Capabilities |
| --- | --- | --- |
| GrantedAuthoritiesMapper | Only need to translate existing authorities into internal ones | Receives a collection of authorities and maps to a new collection |
| OidcUserService | Need directory lookup, reading access token, account linking, and building principal | Has OidcUserRequest, upstream access token, ID Token, and UserInfo |
| OAuth2UserService | Upstream is a non-OIDC OAuth 2.0 Provider | Loads user attributes and creates OAuth2User |
| Custom authentication service | Need multi-step linking/step-up workflows | Actively coordinates policy and persistence |

If you only need simple group claim mapping, `GrantedAuthoritiesMapper` may suffice. If you need `(iss, sub)` resolution, JIT provisioning, tenant membership, or querying a protected IdP API, a delegation-based `OidcUserService` is a better fit.

Do not use `GrantedAuthoritiesMapper` as the sole place managing account linking if that logic requires transactions, auditing, retries, or multiple data sources.

## 12. Issuing internal claims into ID Tokens and access tokens

Once `OidcUserService` returns the internal principal, Spring Authorization Server can read the internal user ID via `context.getPrincipal().getName()` in the token context.

Distinguish clearly:

| Token/Response | Purpose | Claims it should contain |
| --- | --- | --- |
| Upstream ID Token | Evidence of login at the external IdP | External issuer/subject and authentication claims |
| Internal ID Token | User authentication claims at the internal OP | Internal subject, allowed profile claims |
| Internal access token | Resource Server access rights | Internal roles, tenant, entitlements per audience/scope |
| UserInfo | User claims requested by the client | Profile claims permitted for release per scopes |

Never copy the upstream ID Token wholesale into the internal ID Token. Internal tokens must use the internal AS's issuer, internal subject, and the corresponding internal client as audience.

### 12.1. OAuth2TokenCustomizer for internal claims

Spring Authorization Server lets you use `OAuth2TokenCustomizer<JwtEncodingContext>` to customize JWTs. One bean can handle multiple token types; check the token type before adding claims.

SAS automatically wires the customizer bean into the JWT token generator. Consolidate claim policies into one customizer and branch by token type; do not declare multiple beans of the same type competing to write claims.

~~~java
@Bean
OAuth2TokenCustomizer<JwtEncodingContext> internalClaimsCustomizer(
        InternalClaimsService internalClaimsService) {

    return context -> {
        String internalUserId = context.getPrincipal().getName();

        if (OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {

            InternalProfile profile =
                    internalClaimsService.loadProfile(internalUserId);

            context.getClaims().claims(claims -> {
                claims.put("name", profile.displayName());

                if (profile.email() != null) {
                    claims.put("email", profile.email());
                    claims.put("email_verified", profile.emailVerified());
                }
            });
        }

        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())
                && AuthorizationGrantType.AUTHORIZATION_CODE.equals(
                        context.getAuthorizationGrantType())) {

            InternalAccessPolicy accessPolicy =
                    internalClaimsService.resolveAccess(
                            internalUserId,
                            context.getRegisteredClient().getClientId(),
                            context.getAuthorizedScopes()
                    );

            context.getClaims().claims(claims -> {
                claims.put("roles", accessPolicy.roles());
                claims.put("tenant_id", accessPolicy.tenantId());
                claims.put("entitlements", accessPolicy.entitlements());
            });
        }
    };
}
~~~

`InternalClaimsService` must read internal data approved by policy. `resolveAccess(...)` should scope permissions by the internal account, active tenant, client ID, and authorized scopes.

Key points to watch:
- ID Token uses internal profile claims permitted for the client; do not use external email unless approved by policy.
- Access token contains authorization claims for Resource Servers; do not stuff the entire profile into it.
- `roles`, `tenant_id`, and `entitlements` must be computed from internal policy, never read directly from request parameters.
- Never overwrite protocol claims such as `iss`, `aud`, `exp`, `iat`, `jti`, or `sub` with upstream data.
- If the Authorization Server also supports `client_credentials`, do not attach user claims to access tokens of client-only flows. The example above restricts user authorization claims to the Authorization Code grant.

This example applies to JWT token generation. If using opaque access tokens or a custom token generator, configure the customizer matching the token generator in use.

## 13. Customizing OIDC UserInfo per internal policy

The UserInfo Endpoint is an OAuth2 protected resource and requires an access token. SAS can return standard claims from the ID Token per requested scopes. When a dedicated release policy is needed, use `OidcUserInfoEndpointConfigurer.userInfoMapper(...)`.

Example mapper reading the internal profile from the access token's subject and returning only claims matching authorized scopes:

~~~java
Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper =
        context -> {
            JwtAuthenticationToken authentication =
                    (JwtAuthenticationToken) context.getAuthentication().getPrincipal();

            String internalUserId = authentication.getToken().getSubject();
            Set<String> scopes = context.getAuthorization().getAuthorizedScopes();

            InternalProfile profile =
                    internalClaimsService.loadProfile(internalUserId);

            Map<String, Object> claims = new HashMap<>();
            claims.put("sub", internalUserId);

            if (scopes.contains(OidcScopes.PROFILE)) {
                claims.put("name", profile.displayName());
                claims.put("preferred_username", profile.preferredUsername());
            }

            if (scopes.contains(OidcScopes.EMAIL) && profile.email() != null) {
                claims.put("email", profile.email());
                claims.put("email_verified", profile.emailVerified());
            }

            return new OidcUserInfo(claims);
        };
~~~

Register the mapper in the Authorization Server configurer:

~~~java
authorizationServer
    .oidc(oidc -> oidc
        .userInfoEndpoint(userInfo -> userInfo
            .userInfoMapper(userInfoMapper)
        )
    );
~~~

The mapper above assumes the access token is a JWT and the principal is a `JwtAuthenticationToken`, matching SAS's UserInfo configuration model. If using opaque tokens or changing how UserInfo requests are authenticated, obtain the subject/authorization from the appropriate context instead of casting like this.

When enabling the OIDC UserInfo Endpoint, configure resource server support and provide a `JwtDecoder` per SAS guidance. Example using the Authorization Server's JWK source:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

The UserInfo response must keep the `sub` claim equal to the subject in the internal ID Token. Do not return internal claims merely because they exist in the database: check scope, client, consent, purpose, and release policy on every response.

## 14. Resource Server consuming internal authorization claims

Resource Servers must verify the internal access token before reading `roles`, `tenant_id`, or `entitlements`. A valid signature only proves the token was issued by a trusted issuer; the Resource Server must still validate issuer, audience, expiry, and policy.

Example converting the `roles` claim into Spring authorities:

~~~java
@Bean
JwtAuthenticationConverter internalJwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter scopeConverter =
            new JwtGrantedAuthoritiesConverter();

    JwtAuthenticationConverter converter = new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(jwt -> {
        Set<GrantedAuthority> authorities =
                new HashSet<>(scopeConverter.convert(jwt));

        List<String> roles = jwt.getClaimAsStringList("roles");
        if (roles != null) {
            roles.stream()
                    .map(role -> new SimpleGrantedAuthority("ROLE_" + role))
                    .forEach(authorities::add);
        }

        return authorities;
    });

    return converter;
}
~~~

Configure the converter with Resource Server JWT support:

~~~java
http.oauth2ResourceServer(resourceServer -> resourceServer
        .jwt(jwt -> jwt
                .jwtAuthenticationConverter(internalJwtAuthenticationConverter())
        )
);
~~~

This is only an authority mapping example. Each Resource Server must validate the audience appropriate to that specific API and never treat the `tenant_id` claim as sole proof if the request still requires checking tenant ownership in the database.

Access tokens can remain valid after a group or account is revoked upstream. Choose token lifetimes, introspection, revocation, or direct policy checks according to API sensitivity. For critical administrative operations, do not rely on a long-lived access token holding a stale permission snapshot.

## 15. Multi-tenancy and multiple upstream IdPs

A user may log in through multiple IdPs or belong to multiple tenants. Do not select a tenant from an unverified query parameter and place it directly into tokens.

A secure tenant resolution workflow:
1. Obtain the verified external identity and linked internal account.
2. Read the list of tenant memberships from the internal directory.
3. If only one valid tenant exists, select it per policy.
4. If multiple tenants exist, require the user to choose via a protected UI.
5. Verify the selected tenant is in the internal account's memberships.
6. Bind the tenant context to the local session/authorization transaction.
7. When issuing access tokens, grant only roles/entitlements within the confirmed tenant context.

With multiple IdPs:
- Use an issuer allowlist and separate Client Registration configurations.
- Store registration/sector alongside the external identity if pairwise subjects may differ.
- Never auto-merge two accounts due to matching emails.
- Maintain clear link/unlink workflows and auditing.
- When an IdP is untrusted/retired, disable its registration, block new logins, and review existing external identity links.

## 16. Claim freshness, account lifecycle, and revocation

Claims in a JWT are a snapshot at issuance time. When an external group is removed or an internal account is locked, already-issued tokens may still be accepted until expiry if Resource Servers perform only local JWT validation.

Define policies for:
- Synchronization intervals for groups and account status.
- Cache TTLs for external claims.
- When internal policies are re-evaluated during refresh token flows.
- How refresh tokens and authorizations are revoked when a user is disabled.
- Access token lifetimes for APIs of varying risk levels.
- How Resource Servers detect revoked accounts or tenant memberships.
- How upstream IdP outages and key rotations are handled.

For sensitive permissions, use short-lived access tokens, introspection, revocation-aware policies, or service-level account/tenant status checks. Never treat an external group inside a token as permanent permission.

## 17. Security and privacy when mapping claims

- **Issuer trust:** accept only configured and verified issuers; never take an issuer from a request to fetch arbitrary metadata.
- **Signature and token validation:** use OIDC client support to validate ID Tokens; never trust payloads merely because they decode as JSON.
- **Stable identity:** use issuer/subject and appropriate registration context; never use email, username, or display name as the key.
- **Account linking:** require proof of control over both accounts; never auto-link by email alone.
- **Claim allowlist:** read only required claims; ignore or reject unknown claims.
- **Group mapping:** map group IDs per issuer and policy version; never turn arbitrary group names into admin roles.
- **Tenant isolation:** tenant memberships are verified by the internal directory; never trust browser/client-submitted tenant IDs.
- **Claim collision:** never overwrite `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, and protocol claims.
- **Data minimization:** issue only claims needed by the client/resource server; avoid placing unnecessary PII in access tokens.
- **Logging:** never log raw ID Tokens, access tokens, refresh tokens, or full personal claim sets; log pseudonymized external identity keys and policy outcomes.
- **Failure handling:** if permission mapping fails or the account is disabled, halt login/token issuance; never fall back to broad default permissions.
- **Policy audit:** record mapping version, issuer, source claim, target claim, actor, and timestamp of changes.

If fetching additional data from URLs in claims such as `picture`, `website`, or `logo_uri`, never automatically download those URLs from internal servers. Enforce SSRF, redirect, size, and content-type controls. Claim URLs are data, not instructions for the backend to make network calls.

## 18. Identity federation and claim mapping testing matrix

| Scenario | Action | Expected outcome |
| --- | --- | --- |
| Trusted issuer | Log in with allowlisted IdP | OIDC Login succeeds after token validation |
| Unknown issuer | Log in via unconfigured issuer | Rejected; no internal account created |
| Invalid signature | ID Token signed by untrusted key | Authentication rejected |
| Wrong audience | ID Token not intended for upstream client registration | Authentication rejected |
| Expired ID Token | Use an expired token | Authentication rejected |
| Nonce mismatch | Callback with non-matching nonce | Authentication rejected |
| Existing external link | Log in with linked (iss, registration, sub) | Resolves to the right internal account |
| New identity with JIT off | Unlinked subject | Rejected and routed to onboarding |
| New identity with JIT on | New subject from permitted issuer | Provisioned per policy and tenant allowlist |
| Duplicate email | Two external subjects share the same email | Accounts are not auto-linked |
| Unverified email | email_verified=false | Local email is not marked verified |
| Group not mapped | External group has no mapping | No internal role created |
| Group revoked | Mapping/group disabled | Authority not granted on next evaluation |
| Disabled account | Internal account locked | No local session established, no tokens issued |
| Tenant escalation | Request selects tenant outside membership | Rejected |
| ID Token claims | Client requests openid profile | Issues only internal profile claims allowed by policy |
| UserInfo scope | Client without email scope calls UserInfo | Does not return email claim |
| Access token audience | Token used against another API | Resource Server rejects |
| Upstream outage | IdP unavailable | Applies availability policy; never skips verification |
| Claim freshness | Internal role revoked | New tokens omit role; old tokens handled per revocation/lifetime policy |
| Pairwise subject | Same user across two registrations with different subs | Not merged without verified account linking |
| Unlink identity | Remove external identity link | Subsequent login rejected or requires re-linking |

Tests must verify the local session, internal account link, audit record, ID Token, access token, and UserInfo response. A successful upstream login alone does not prove internal mapping is correct.

## 19. Case study exercise

An enterprise uses a parent company's IdP to log into an internal Authorization Server. The IdP sends the following claims:

~~~json
{
  "iss": "https://login.parent.example",
  "sub": "00u-a8c92",
  "email": "linh@example.com",
  "email_verified": true,
  "groups": [
    "grp-order-readers",
    "grp-finance"
  ],
  "department": "FIN"
}
~~~

The internal system has account ID `usr-4821`, tenant `tenant-vn`, and roles `ORDER_VIEWER` and `FINANCE_VIEWER`. The `orders-web` client only needs basic profile information and permission to read orders.

Analyze:

1. Which key is used to link the external identity to `usr-4821`?
2. Why should email not be used as the linking key?
3. Through what policy are `groups` translated into internal roles?
4. Is `department=FIN` sufficient to assign a tenant or role?
5. Which `sub` does the internal Authorization Server issue in the internal ID Token?
6. Which claims should appear in the ID Token and access token?
7. How do you ensure `orders-web` does not receive unnecessary financial information?
8. If the user is removed from `grp-order-readers`, how are active tokens handled?
9. If the user logs in from a different upstream registration with a new pairwise `sub`, how do you avoid creating or linking the wrong account?
10. Propose tests for duplicate email, unverified email, disabled account, tenant escalation, and group revocation.

**Hint:** Store the external identity by issuer + registration/sector + subject. The internal subject remains `usr-4821` or an internal opaque ID. Map only the two approved groups to internal roles. Obtain tenant membership from the internal directory. The access token carries only the audience, scopes, and permissions needed for the Orders API; profile claims are released according to scope and consent.

## 20. Production implementation checklist

1. **Trust:** allowlist issuers and configure OIDC Client Registrations per upstream IdP.
2. **Validation:** verify signature, issuer, audience, expiry, nonce, and UserInfo subject consistency.
3. **Identity key:** use `(iss, sub)`; include registration/sector context when using pairwise subjects.
4. **Account linking:** enforce pre-provisioning, JIT, or explicit linking policies; never auto-link by email.
5. **Internal subject:** use a stable internal ID as the internal OP's subject.
6. **Claim policy:** define source, trust, transformation, target, conflict, and release policies.
7. **Group mapping:** allowlist external group IDs per issuer/registration; map to internal roles.
8. **Authority source:** derive roles, tenants, and entitlements from the internal directory/policy engine.
9. **Spring Security:** use `OidcUserService` or `GrantedAuthoritiesMapper` appropriately; build a principal with the internal identity.
10. **Token customizer:** branch between ID Token and access token; never mix profile claims with authorization claims.
11. **UserInfo:** enable the endpoint, provide a `JwtDecoder`, and use a custom mapper when a release policy is needed.
12. **Audience/scope:** constrain tokens by client, Resource Server, and granted permissions.
13. **Tenant:** confirm membership before attaching tenant context to tokens.
14. **Freshness:** define sync intervals, cache TTLs, token lifetimes, and revocation policies.
15. **Lifecycle:** handle disablement, unlinking, IdP offboarding, key rotation, and policy versioning.
16. **Privacy:** minimize PII, redact tokens/claims in logs, and audit on a need-to-know basis.
17. **Testing:** test identity resolution, mapping, token issuance, UserInfo, replay, stale claims, and multi-tenancy.
18. **Operations:** monitor login failures, unknown issuers, unmapped groups, JIT provisioning, account linking, and policy denials.

## 21. Standards and Spring references

- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token validation, issuer, subject, UserInfo, and claim stability/uniqueness.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html): OAuth 2.0 Authorization Code flow and Authorization Server/Client roles.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700.html): protecting OAuth clients, authorization flows, and token handling.
- [Spring Security 6.5 — OAuth 2.0 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/login/advanced.html): `OidcUserService`, `GrantedAuthoritiesMapper`, and mapping authorities from upstream providers.
- [Spring Authorization Server 1.5.8 — Customize the OIDC UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): customizing ID Token claims and `userInfoMapper`.
- [Spring Authorization Server 1.5.8 — Add authorities as custom claims in JWT access tokens](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html): `OAuth2TokenCustomizer<JwtEncodingContext>` and token-specific claims.
- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): OIDC UserInfo Endpoint configurer and extension points.
- [Spring Authorization Server 1.5.8 — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): token customization and Authorization Server model components.

**Key takeaway:** The upstream IdP authenticates the external identity; the internal Authorization Server is responsible for linking the identity, computing internal authorities, and issuing its own tokens. Use issuer/subject together with registration context to identify external accounts, never email as a key. Transform claims only through an allowlisted, versioned mapping policy; roles, tenants, and entitlements must come from the internal directory or policy engine. Use `OidcUserService` to construct the internal principal, `OAuth2TokenCustomizer` to issue claims per token type, and `userInfoMapper` to control claims released to clients. A successful external login does not mean the user is granted every permission published by the external IdP.
