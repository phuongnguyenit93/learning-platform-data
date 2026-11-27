# Customizing Claims by Client, Grant Type, Principal, and Tenant

> **Chapter: Tokens and claims.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, guiding you through designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in Spring Boot. It focuses on adding claims under control based on the **registered client**, **active grant type**, **authenticated principal**, and **verified tenant**, while distinguishing access token, ID Token, and UserInfo claims.

## 1. Why Customize Claims?

An access token typically needs to carry enough information for the Resource Server to understand who the token was issued for, by which client, in what context, and what it is allowed to do. Spring Authorization Server already produces standard claims per protocol and token format. However, real applications often need additional data such as:

- Subject type: human user or service account.
- Client that requested and received the token.
- Grant type used to issue the token.
- Tenant in which the user/service is operating for this transaction.
- Policy or permission version to assist Resource Server checks.
- Actor/delegation context when a service acts on behalf of a user.

Example:

- **Authorization Server:** `https://login.example.vn`.
- **Web client:** `portal-web`, authenticating users via Authorization Code + PKCE.
- **Machine client:** `billing-job`, obtaining tokens via Client Credentials.
- **Tenant:** `tenant-a` or `tenant-b`, each with isolated order data.
- **Resource Server:** `https://api.example.vn`, verifying tokens and restricting access by audience, scope, subject, and tenant.

Two tokens may be issued by the same issuer while carrying different contexts:

| Scenario | Primary identity | Potentially useful custom claims |
|---|---|---|
| User signs in via `portal-web` | End user | Verified `tenant_id`, subject type, assurance info if applicable |
| Service using Client Credentials | Client/service account | `client_id`, service identity, tenant bound to the service |
| User refreshes token | Subject of the original authorization | Keep the original authorization's subject/tenant; do not treat refresh as a new login |
| Token Exchange | Verified subject and actor | `act`, delegation context, audience, and scope per policy |

**Customizing claims is the step of building token contents, not granting permissions.** Before the customizer runs, the Authorization Server must authenticate the client and validate the grant, subject, scopes, consent, and policy. Never use a token customizer to turn an invalid request into an allowed one.

## 2. What Is a Claim and Where Does It Live?

A claim is a name/value pair inside a JWT payload or in corresponding token/introspection data. Illustrative JWT access token payload:

~~~json
{
  "iss": "https://login.example.vn",
  "sub": "user-123",
  "aud": ["orders-api"],
  "client_id": "portal-web",
  "scope": "orders.read",
  "iat": 1794825600,
  "exp": 1794825900,
  "https://claims.example.vn/tenant_id": "tenant-a",
  "https://claims.example.vn/subject_type": "user"
}
~~~

This is illustrative JSON, **not a signed JWT**. Some claims like `iss`, `sub`, `aud`, `iat`, and `exp` are standard claims; `client_id` is used in the JWT Access Token Profile. The two URI-named claims are organization-defined private claims to reduce naming collisions.

### 2.1. Claim Categories to Distinguish

| Category | Examples | Who decides? |
|---|---|---|
| **JWT registered claims** | `iss`, `sub`, `aud`, `exp`, `iat`, `jti` | Protocol and Authorization Server |
| **OAuth access token claims** | `client_id`, `scope`, `cnf` | Authorization Server, per profile and sender-constraining mechanism |
| **OIDC ID Token claims** | `nonce`, `auth_time`, `acr`, `amr` | OpenID Provider based on transaction and authentication evidence |
| **Private/application claims** | `tenant_id`, `subject_type`, policy version | Verified internal policy |
| **Delegation claims** | `act`, `may_act` per profile | Authorization Server based on verified delegation relationship |

Do not put all data into the same token. Access tokens are for Resource Servers; ID Tokens are for OIDC Relying Parties; UserInfo is an endpoint returning user attributes per scope/authorization. A claim useful to an API does not necessarily belong in an ID Token.

### 2.2. Claim Names and Naming Rules

RFC 7519 distinguishes registered claim names, public claim names, and private claim names. When defining custom claims:

- Prefer namespaced names controlled by your organization, e.g., `https://claims.example.vn/tenant_id`.
- Keep names, data types, and semantics stable across versions.
- Never use names that collide with standard claims such as `iss`, `sub`, `aud`, `exp`, `iat`, `nonce`, or `scope`.
- Never put passwords, client secrets, private keys, refresh tokens, payment details, or unnecessary personal data into claims.
- Document whether a claim is a string, number, boolean, or array; the Resource Server must validate the data type instead of casting blindly.
- Avoid changing claim semantics without versioning; older tokens may remain valid after new code deploys.

A URI name in the payload is a **claim name**; it does not mean the Resource Server should call that URL. It is a collision-avoidance namespace, not a lookup endpoint.

## 3. Contexts Provided by Spring Authorization Server

Spring Authorization Server provides `OAuth2TokenCustomizer<T>` to customize the token context before encoding/issuance. When using the JWT generator, the typical extension point is:

~~~java
OAuth2TokenCustomizer<JwtEncodingContext>
~~~

`JwtEncodingContext` provides trusted context constructed by the Authorization Server, including key data:

| API | Meaning | Safe usage |
|---|---|---|
| `getRegisteredClient()` | Client located and authenticated for the current flow | Choose policy by `clientId`/registration; never take client from query params |
| `getAuthorizationGrantType()` | Grant type being processed | Branch token logic by grant |
| `getPrincipal()` | Authentication tied to grant/token generation | Use after checking whether principal is a user or client |
| `getAuthorization()` | Associated authorization record if present | Read subject, authorization attributes, and persisted context |
| `getAuthorizedScopes()` | Scopes authorized for the token context | Never replace with scopes pulled from the raw request |
| `getTokenType()` | Type of token being generated, e.g., access token or ID Token | Do not unconditionally copy access token claims into ID Tokens |
| `getClaims()` | Builder for JWT claims | Add claims only after policy verification |
| `getAuthorizationGrant()` | Authentication object of the current grant | Use when grant-specific data is needed, while checking type and trust boundaries |

A customizer should read from the authenticated context and trusted policy services. **Never** read the HTTP request directly inside a customizer to take `tenant_id`, `role`, `audience`, or `scope` and place them into the token.

### 3.1. Token Creation Flow and Customizer Placement

~~~mermaid
flowchart TD
    Request["Token request"] --> Auth["Authenticate client"]
    Auth --> Grant["Validate grant, code/refresh token, and principal"]
    Grant --> Policy["Validate scope, consent, audience, tenant, and authorization"]
    Policy -->|Deny| Deny["OAuth2 error, no token issued"]
    Policy -->|Valid| Context["Create OAuth2TokenContext"]
    Context --> Generator["OAuth2TokenGenerator"]
    Generator --> Customizer["OAuth2TokenCustomizer<JwtEncodingContext>"]
    Customizer --> Sign["Sign JWT with Authorization Server key"]
    Sign --> Store["Save authorization/token state"]
    Store --> Response["Return token response"]
~~~

The customizer sits inside the token creation process. It can add claims, but must not be the sole place deciding whether a client can access a tenant or scope. Authorization must be decided earlier; the Resource Server continues verifying the token and API policies.

## 4. Distinguishing Access Token, ID Token, UserInfo, and Opaque Token

### 4.1. JWT Access Token

A JWT access token is used by the Resource Server to verify access privileges. Useful claims can include:

- `iss`: issuer of the Authorization Server.
- `sub`: token subject per issuance profile.
- `aud`: Resource Server or resource the token is intended for.
- `client_id`: client that requested the token.
- `scope`: granted scopes.
- `tenant_id`: verified tenant bound to the authorization.
- `act`: actor/delegation context if required by profile and use case.

Do not pack verbose user profile data into access tokens just to save the API a lookup. Tokens pass through multiple services, traces, and devices; the less data inside, the lower the impact if a token leaks.

### 4.2. OIDC ID Token

An ID Token proves the user authentication outcome to the RP. Claims such as `iss`, `sub`, `aud`, `exp`, `iat`, and `nonce` carry protocol semantics. `auth_time` must reflect the actual active authentication timestamp when required; never set it to the moment the token was signed. `acr`/`amr` must be grounded in the authentication level/method actually performed, never fabricated to satisfy a client.

Add custom claims to ID Tokens only when the RP genuinely needs them and OIDC policy permits. Profile attributes often belong better on the UserInfo endpoint, where the server checks the access token and scopes before returning claims.

### 4.3. UserInfo

UserInfo is the OIDC endpoint returning claims about the end user. It is a separate surface from the ID Token customizer. When customizing UserInfo claims, use the OIDC UserInfo endpoint's extension point (such as the mapper/handler for your version) to:

- Verify the access token and granted scopes.
- Return only user attributes permitted by scopes/consent and client policy.
- Never leak another user's tenant/profile.
- Keep `sub` consistent with the subject in the ID Token.
- Never use UserInfo to expand API privileges or replace Resource Server authorization.

### 4.4. Opaque Access Token

`OAuth2TokenCustomizer<JwtEncodingContext>` applies only when tokens follow the JWT encoding path. If the access token is an **opaque/reference token**, the Resource Server cannot read a JWT payload from the token string. Claim customization must use the token claims context/generator and corresponding introspection mechanism, such as `OAuth2TokenClaimsContext` for `OAuth2AccessTokenGenerator` in Spring Authorization Server.

Do not configure a JWT customizer and expect claims to appear in every token format. Explicitly confirm which token generator is active and how the Resource Server obtains information (local JWT validation vs. introspection).

### 4.5. Refresh Token

A refresh token is normally a standalone credential, not a JWT access token holding business claims. Upon refresh, a new access token can be regenerated; claims must be derived from the active authorization/principal/policy and saved original context. Never assume every refresh is a new login or update `auth_time`.

## 5. Customizing Claims by Client

Each client has a different purpose and trust level. `portal-web` may need a tenant claim for an orders API, while `billing-job` needs only a service identity. Do not attach the exact same claim set to every client.

### 5.1. Using the Authenticated RegisteredClient

Example configuration for two clients:

| Client | Grant type | Claims needed per policy |
|---|---|---|
| `portal-web` | Authorization Code, Refresh Token | Verified `tenant_id`; subject type is user |
| `billing-job` | Client Credentials | Service identity; client-bound tenant if granted; never impersonate a user |

Client identity should come from `context.getRegisteredClient().getClientId()`. Never use `client_name` or a display logo as a security identifier; display metadata can change and is not a credential.

### 5.2. Server-Managed Claim Policy

You can define a dedicated policy:

~~~java
interface ClientClaimPolicy {
    boolean includeTenantClaim(String clientId);

    boolean includeGrantTypeClaim(String clientId);

    boolean includeSubjectTypeClaim(String clientId);
}
~~~

Implementations can load policies from admin configuration or an internal registry. Only administrators/automation should alter policies; clients must never send a parameter like `include_tenant=true` to toggle claims. In large systems, policies should support versioning, auditing, and cache invalidation.

### 5.3. Per-Client Claims Do Not Mean Granting Client Permissions

If policy allows `portal-web` to receive `tenant_id`, that only decides which claim is added after the tenant is verified. It does not let `portal-web` choose arbitrary tenants. The Authorization Server must still verify the user belongs to the tenant, the client is permitted for that tenant, and the request is bound to a valid authorization.

Likewise, adding `role=admin` does not confer legitimate admin access. If roles are used for authorization, they must come from a trusted authorization source and the Resource Server must enforce current policy.

## 6. Customizing Claims by Grant Type

The grant type describes how the token was issued and helps identify the principal/context type. Branch explicitly instead of assuming all tokens represent human users.

| Grant type | Typical subject | What to avoid |
|---|---|---|
| `authorization_code` | Authenticated user | Never read user from query params; never set tenant from unverified browser input |
| `refresh_token` | Original subject/authorization | Never treat refresh as a new login; never auto-update `auth_time` |
| `client_credentials` | Confidential client/service account | Never invent user claims or a fake user `sub` |
| `urn:ietf:params:oauth:grant-type:token-exchange` | Subject and possibly actor | Use subject/actor only after verifying input tokens and delegation policy |
| Device Authorization Grant | User who completed authentication on another device | Never derive identity from user code; use authorization record |
| Custom grant | Per application profile | Must clearly define identity, authorization, claims, and negative cases |

### 6.1. Client Credentials Is a Service Identity

With Client Credentials, the principal typically represents the authenticated OAuth client, not an end user. The token can carry `client_id` and a private claim like `subject_type=service` if the Resource Server needs to distinguish them. Never assign `tenant_id` from an arbitrary request parameter; the tenant must be tied to the service configuration or approved authorization.

### 6.2. Authorization Code and Refresh Token

With Authorization Code, the principal is the user after successful login. The tenant (if any) must be resolved via membership/directory and bound to the authorization transaction. Upon refresh, use the tenant stored in the original authorization and/or re-verify against the authoritative source; never take the tenant from an arbitrary API request.

### 6.3. Token Exchange

With Token Exchange, the subject token and actor token may describe two distinct entities. Claims like `sub` and `act` must be constructed from verified subject/actor identities and delegation policy. Never use a generic customizer to read a raw `subject_token` from the HTTP request and decode it yourself. Input token validation and exchange decisions belong to the token exchange provider/policy layer.

## 7. Customizing Claims by Principal and Tenant

### 7.1. The Principal Is Not Always a User

`Authentication.getPrincipal()` may represent `UserDetails`, a custom principal, OAuth2 client authentication, or another grant's principal. Before reading attributes, check the grant type and principal type. Never blindly cast every principal to `UserDetails` or assume `getName()` is an email.

Prefer a stable, low-PII identifier such as an internal subject ID. Email/username can change or be recycled; they should not serve as long-term authorization keys when a stable subject ID exists.

### 7.2. Tenant Is a Verified Context

In a multi-tenant system, a user may belong to multiple tenants. The tenant chosen for a transaction must satisfy checks:

1. The principal is authenticated and has a stable subject.
2. The tenant exists, is active, and belongs to the appropriate organization/issuer.
3. The principal has valid membership/roles in that tenant.
4. The client is permitted to operate for that tenant per registration/policy.
5. Requested scopes and resources are valid within the tenant.
6. The tenant is persisted with the authorization record or a trusted server-side context for reuse on refresh.

Never take `tenant_id` from a query string, browser-set header, hidden form field, or unverified token claim. If a request conveys a tenant identifier, it is merely a **selection to be verified**, not proof of access.

### 7.3. Binding Tenant to the Authorization Transaction

One implementation pattern is saving the verified tenant in authorization attributes when the authorization is created. The customizer then reads the attribute from the authorization rather than from the current request. Attribute names and persistence mechanisms are application details; the value must be produced after verifying membership/client policy and preserved safely across refreshes.

Conceptual model:

~~~text
Authorization transaction:
  registered_client_id = registration-portal-web
  principal_name       = user-123
  grant_type           = authorization_code
  tenant_id            = tenant-a        # verified
  tenant_policy_version= 12
  authorized_scopes    = [orders.read]
~~~

During token refresh, the Authorization Server uses the original authorization record to preserve the correct tenant. If membership has been revoked or the tenant suspended, policy may require denying the refresh or downscoping privileges; never keep issuing tokens from an old snapshot indefinitely.

## 8. Example OAuth2TokenCustomizer for JWT Access Tokens

The following example illustrates a single customizer handling JWT access tokens. `ClientClaimPolicy` and `TenantClaimResolver` are application-defined services; they must read policies and tenants from trusted sources.

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Configuration(proxyBeanMethods = false)
class AccessTokenClaimsConfiguration {

    static final String TENANT_CLAIM =
            "https://claims.example.vn/tenant_id";
    static final String GRANT_TYPE_CLAIM =
            "https://claims.example.vn/grant_type";
    static final String SUBJECT_TYPE_CLAIM =
            "https://claims.example.vn/subject_type";

    @Bean
    OAuth2TokenCustomizer<JwtEncodingContext> jwtTokenCustomizer(
            ClientClaimPolicy claimPolicy,
            TenantClaimResolver tenantClaimResolver) {

        return context -> {
            if (!OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
                return;
            }

            String clientId =
                    context.getRegisteredClient().getClientId();
            AuthorizationGrantType grantType =
                    context.getAuthorizationGrantType();

            if (claimPolicy.includeGrantTypeClaim(clientId)) {
                context.getClaims().claim(
                        GRANT_TYPE_CLAIM, grantType.getValue());
            }

            if (AuthorizationGrantType.CLIENT_CREDENTIALS.equals(grantType)) {
                if (claimPolicy.includeSubjectTypeClaim(clientId)) {
                    context.getClaims().claim(SUBJECT_TYPE_CLAIM, "service");
                }
                return;
            }

            // Only defined user grants may receive subject_type=user.
            if (AuthorizationGrantType.AUTHORIZATION_CODE.equals(grantType)
                    || AuthorizationGrantType.REFRESH_TOKEN.equals(grantType)) {
                if (claimPolicy.includeSubjectTypeClaim(clientId)) {
                    context.getClaims().claim(SUBJECT_TYPE_CLAIM, "user");
                }

                if (claimPolicy.includeTenantClaim(clientId)) {
                    Optional<String> tenantId =
                            tenantClaimResolver.resolveValidatedTenant(context);
                    tenantId.ifPresent(value ->
                            context.getClaims().claim(TENANT_CLAIM, value));
                }
            }
            // Token Exchange/custom grants require dedicated policies and resolvers.
        };
    }
}
~~~

**Limitations and conditions of this example:**

- Runs only for `OAuth2TokenType.ACCESS_TOKEN`; does not add these claims to ID Tokens.
- `ClientClaimPolicy` and `TenantClaimResolver` are application-written abstractions, not built-in Spring beans.
- `resolveValidatedTenant(context)` must rely on verified authorization attributes or an authoritative directory service. It must never take the tenant from an unverified HTTP request.
- For refresh grants, the resolver must read the tenant from the original authorization and/or re-verify membership; never infer a tenant from a new request.
- Token Exchange and custom grants require dedicated policy branches. Do not assume every non-Client-Credentials grant is a user grant.
- The grant type claim is included for illustration; emit it only if the Resource Server genuinely needs it. Grant type can leak architectural details and is not always needed in tokens.
- Do not overwrite standard claims such as `iss`, `sub`, `aud`, `exp`, `iat`, `scope`, or `client_id` just to make them look the way you want.

### 8.1. Reading Tenant from Persisted Authorization

A `TenantClaimResolver` can follow this pattern (API/attribute keys are application-defined):

~~~java
import java.util.Optional;

import org.springframework.security.oauth2.server.authorization.OAuth2Authorization;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;

interface TenantClaimResolver {
    Optional<String> resolveValidatedTenant(JwtEncodingContext context);
}

final class AuthorizationAttributeTenantResolver
        implements TenantClaimResolver {

    static final String TENANT_ATTRIBUTE = "validated_tenant_id";

    private final TenantDirectory tenantDirectory;

    AuthorizationAttributeTenantResolver(TenantDirectory tenantDirectory) {
        this.tenantDirectory = tenantDirectory;
    }

    @Override
    public Optional<String> resolveValidatedTenant(
            JwtEncodingContext context) {

        OAuth2Authorization authorization = context.getAuthorization();
        if (authorization == null) {
            return Optional.empty();
        }

        Object rawTenant = authorization.getAttribute(TENANT_ATTRIBUTE);
        if (!(rawTenant instanceof String tenantId) || tenantId.isBlank()) {
            return Optional.empty();
        }

        String principalName = authorization.getPrincipalName();
        String clientId = context.getRegisteredClient().getClientId();

        // Re-check status/membership against current policy.
        return tenantDirectory.isAuthorized(principalName, clientId, tenantId)
                ? Optional.of(tenantId)
                : Optional.empty();
    }
}
~~~

`TenantDirectory` is an application-implemented service; `isAuthorized` must verify subject, client, and tenant. In production, if a missing tenant is an error for a tenant-mandatory client/grant, do not silently issue a token missing the claim and let the API misinterpret it. Enforce the tenant requirement **before token generation**; the customizer should not be the only place deciding authorization.

For Client Credentials, the tenant can be bound to the client/service registration instead of a user authorization. Use a dedicated resolver for service identity, constrained to tenants the client is authorized to represent.

## 9. Customizing ID Tokens and Distinguishing UserInfo

### 9.1. Customize ID Tokens Only for Proper Purposes

If you need to add claims to an ID Token, place that branch **inside the same JWT customizer** from section 8, or compose them explicitly in generator configuration. Example snippet (merge into the existing bean rather than declaring a second bean of the same generic type):

~~~java
import org.springframework.security.oauth2.core.oidc.OidcParameterNames;

// Merge into the existing OAuth2TokenCustomizer<JwtEncodingContext>:
if (OidcParameterNames.ID_TOKEN.equals(context.getTokenType().getValue())) {
    if (oidcClaimPolicy.includeDepartment(
            context.getRegisteredClient().getClientId())) {
        oidcUserClaimResolver.resolveDepartment(context)
                .ifPresent(department ->
                        context.getClaims().claim(
                                "https://claims.example.vn/department",
                                department));
    }
    return;
}
~~~

This snippet illustrates the Spring Authorization Server 1.x API. If your project already has an `OAuth2TokenCustomizer<JwtEncodingContext>` bean, **merge the logic** or compose intentionally per your generator configuration; never declare multiple customizers of the same generic type expecting the framework to automatically invoke all of them in your desired order.

Never use a customizer to set `auth_time` to the current time. Never assign `acr`/`amr` without corresponding authentication evidence. Standard OIDC claims must follow OIDC Core and OP security policies.

### 9.2. UserInfo Is a Separate Contract

If an RP needs display name, email, or department, it can retrieve them from UserInfo after verifying the access token and scopes. There is no need to stuff all those attributes into ID Tokens or access tokens. Even when data originates from the same user directory, the UserInfo endpoint must:

- Verify the access token and subject.
- Return only claims permitted by scopes/consent and client policy.
- Keep returned `sub` consistent with the ID Token's subject.
- Maintain tenant isolation.
- Never return sensitive attributes merely because the user directory contains them.

## 10. Non-Negotiable Rules When Customizing Claims

### 10.1. Do Not Trust Request Input

| Data source | Safe to use directly? | How to handle |
|---|---|---|
| `RegisteredClient` from token context | Yes, after client authentication | Use client ID and server-side policy |
| `getAuthorizedScopes()` | Yes, as the authorized scope context | Never expand on your own |
| Authenticated principal | Yes, after distinguishing user/client | Extract stable subject; do not assume principal is `UserDetails` |
| Verified authorization attributes | Yes, if persistence/integrity is controlled | Re-verify membership/policy when needed |
| Query/header/body `tenant_id` | No | Treat only as a selection; verify membership/client policy and persist in context |
| Unverified JWT subject token | No | Validate signature/issuer/type/expiry/status before using claims |
| Self-asserted client metadata | Not as an authorization source | Use only after provisioning/approval and escaping |
| Email/username | Should not be a long-term permission key | Use stable subject ID; emit PII only when needed |

### 10.2. Do Not Overwrite Standard Claims

Consequential mistakes:

- Overwriting `sub` with email or tenant ID alters token identity.
- Overwriting `aud` from a query parameter routes tokens to the wrong Resource Server.
- Synthesizing `scope` from unapproved roles instead of granted scopes.
- Setting `exp` longer than policy to avoid refreshes.
- Setting `auth_time=iat` during refresh, tricking the RP into thinking the user just authenticated.
- Setting `acr`/`amr` arbitrarily, misrepresenting authentication assurance.
- Removing `cnf` or sender-constraining claims, breaking token binding.
- Changing `iss` or signing with a key that does not match the issuer's metadata/JWKS.

### 10.3. Claims Do Not Replace Authorization

Even if an access token carries `tenant_id=tenant-a` and `scope=orders.read`, the Resource Server must still verify:

1. Signature, issuer, expiration, and audience.
2. Whether granted scopes permit the endpoint/operation.
3. Whether the token's tenant matches the resource/request tenant and identity context.
4. Whether the subject/actor has permission on the specific data object.
5. Whether the token has not been revoked under the system's mechanism if immediate revocation is required.

Never let a client send `X-Tenant-Id: tenant-b` and have the API trust the header over the token claim/policy. If a tenant header is used to select context, compare it against the token and the principal's authorization.

## 11. Configuring JWT Access Tokens and Opaque Tokens

### 11.1. JWT Access Token

If you want tokens carrying claims readable at the Resource Server, configure the self-contained/JWT access token format. Example in RegisteredClient:

~~~java
import org.springframework.security.oauth2.server.authorization.settings.OAuth2TokenFormat;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

TokenSettings tokenSettings = TokenSettings.builder()
        .accessTokenFormat(OAuth2TokenFormat.SELF_CONTAINED)
        .build();
~~~

Depending on version and defaults, `SELF_CONTAINED` denotes JWT access tokens; verify actual issued tokens and metadata/keys. The Authorization Server needs an appropriate JWKSource/encoder and published public JWKS so the Resource Server can verify signatures. Never place the private signing key in the Resource Server.

### 11.2. Opaque/Reference Access Token

When using `OAuth2TokenFormat.REFERENCE`, the token does not contain a JWT payload decodable at the client/API. The Resource Server typically introspects the token or checks state via a configured mechanism. Claims must be added to the introspection/authorization context through the appropriate generator/service; the `JwtEncodingContext` customizer is not invoked on the opaque token path.

Choosing JWT vs. opaque by requirements:

| Criterion | JWT/self-contained | Opaque/reference |
|---|---|---|
| Resource Server verification | Signature and claims locally | Introspection/lookup |
| Reading claims | Readable after verifying signature | Payload cannot be decoded from token |
| Immediate revocation | Requires extra mechanisms or short TTL | Can check centralized status |
| AS dependency during API calls | Lower | Higher if introspected on every request |
| Customizing claims | JWT encoding customizer | Token claims context/generator and introspection |
| Data leakage | Payload readable if token leaks | Opaque token hides payload, yet remains a bearer credential |

## 12. Testing Claims Across the Client, Grant, Principal, and Tenant Matrix

Do not merely decode a JWT, see a claim appear, and declare it done. Test **both permitted cases and cases that must be rejected**, and verify the Resource Server enforces claims.

| Case | Client | Grant | Principal/context | Expectation |
|---|---|---|---|---|
| 1 | `portal-web` | Authorization Code | User in `tenant-a` | Token carries verified tenant, subject is user |
| 2 | `portal-web` | Authorization Code | User in `tenant-b` | Token carries `tenant-b`; does not reuse cached tenant A |
| 3 | `billing-job` | Client Credentials | Service account | Subject type claim is service; no fake user profile |
| 4 | Client disallowed for tenant | Client Credentials | Service bound to `tenant-a` | Does not issue claim/authorization for `tenant-b` |
| 5 | `portal-web` | Refresh Token | Original authorization tenant A | Tenant comes from original authorization and current policy |
| 6 | `portal-web` | Refresh Token | Membership for tenant A revoked | Rejects or downscopes per policy; never blindly issues old token |
| 7 | Client A | Authorization Code | Client B sends spoofed request | Never takes client identity from request body |
| 8 | Client whose policy excludes claim | Authorization Code | Valid user | Claim is not added |
| 9 | User without valid tenant | Authorization Code | Missing/invalid tenant | Never issues token with fake tenant |
| 10 | Multi-tenant user | Authorization Code | Selects tenant outside membership | Rejected before token generation |
| 11 | `billing-job` | Client Credentials | Principal is client authentication | Does not cast principal to `UserDetails` |
| 12 | Token Exchange | Token Exchange | Verified subject/actor | Claims reflect subject/actor and target policy |
| 13 | Token Exchange | Token Exchange | Unauthorized actor | Rejected; no fake `act` claim added |
| 14 | OIDC client | Authorization Code | Requests ID Token | Standard claims, nonce, aud, and auth_time accurate; custom claims per policy |
| 15 | Opaque token | Authorization Code | Valid user | Do not expect JwtEncodingContext customizer to run |
| 16 | JWT token | Refresh Token | Old claims changed | New token follows current policy; old token stays a snapshot until expiry |
| 17 | Disabled user | Refresh Token | Old authorization still stored | Re-check user status per policy instead of blindly trusting old token |
| 18 | Tenant A | Authorization Code | API request selects tenant B | Resource Server rejects mismatch |
| 19 | Broad scopes in registration | Authorization Code | Request only authorized narrow scopes | Token contains only granted scopes, never auto-expanded |
| 20 | Unexpected principal type | Custom grant | Principal lacks tenant attribute | No ClassCastException; fail closed/omit claim per policy |

### 12.1. Unit Testing Policies and Claim Resolvers

A unit test should verify policy against validated data without needing a real JWT for every case:

~~~java
@Test
void doesNotResolveTenantFromUntrustedRequestValue() {
    JwtEncodingContext context = contextFor(
            "portal-web",
            AuthorizationGrantType.AUTHORIZATION_CODE,
            "user-123");

    // Authorization lacks validated_tenant_id and directory
    // does not confirm membership.
    Optional<String> tenant =
            tenantClaimResolver.resolveValidatedTenant(context);

    assertTrue(tenant.isEmpty());
}
~~~

`contextFor(...)` is a project-written test fixture that creates a version-appropriate `JwtEncodingContext`. Add tests covering valid authorization attributes, revoked membership, unauthorized clients for a tenant, and refresh against original authorizations. Do not use this unit test to claim the token endpoint or JWT signing works.

### 12.2. Token Endpoint Integration Testing

In a test environment, run the complete flow:

1. Register test clients and users; configure tenant memberships in fixtures.
2. Send a valid authorization request, complete login/consent, and exchange the code.
3. Decode the access token **after verifying its signature**; check claim names, types, issuer, audience, scopes, tenant, and expiry.
4. Call the test Resource Server with that token; verify the right tenant is accessible and other tenants are rejected.
5. Refresh the token; verify claims remain tied to the original authorization and `auth_time` is not updated.
6. Revoke membership/tenant and retry refresh/exchange; verify policy is enforced.
7. Run Client Credentials; verify the token represents a service and carries no user data.
8. Test ID Token/UserInfo separately; never assume an access token customizer applies to every token type.

### 12.3. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| Claim missing | Opaque token or customizer not wired to right generator/token type | Check format, generator, and bean wiring |
| Claim appears in ID Token but not access token | Wrong token type check or customizer only handles ID Tokens | Branch explicitly per token type |
| Tenant claim intermittently wrong | Reading tenant from ThreadLocal/request or unpartitioned cache | Use authorization context and resolver keyed by client+subject |
| Client Credentials carries user claims | Treating every principal as an end user | Branch by grant type; separate service identity |
| Refresh token updates `auth_time` | Using current timestamp when minting token | Use saved original active authentication timestamp; never auto-refresh it |
| Scope in token is too broad | Copying scopes from request/registration instead of authorized scopes | Use authorized scopes; verify policy prior to issuance |
| Resource Server ignores tenant | Decodes claim without comparing to resource context | Enforce tenant isolation during authorization |
| Multiple customizers misbehave | Multiple beans with same generic type or custom generator | Explicit composition; test ordering and wiring |
| Claims change after user role change while old token still valid | JWT is a snapshot at issuance time | Short TTL, revocation/introspection, or policy version |
| Opaque token lacks custom claims in introspection | Only configured JwtEncodingContext | Configure token claims context and introspection response |

## 13. Operations, Privacy, and Claim Lifecycle

### 13.1. JWT Is a Snapshot

Claims in a JWT are signed at issuance time. If a user is removed from a tenant or a role changes afterward, old tokens may still hold previous claims until they expire, are revoked by supplementary mechanisms, or the Resource Server checks live state. Therefore:

- Keep access token TTL aligned with risk.
- For rapidly changing privileges, use policy versions or live membership checks at the API when needed.
- Explicitly define revocation propagation latency.
- Never treat custom claims as real-time data sources.
- Have a procedure to handle issued tokens when a tenant/user is disabled.

### 13.2. Minimizing Personal Data

Claims can be read by anyone holding the bearer token or authorized to decode/verify it. Issue only data essential to API goals. Avoid:

- Email, phone number, address, date of birth if the API does not need them.
- Massive lists of all groups/roles.
- Internal data like fraud scores, support notes, or payment details.
- Operational secrets or metadata that reveals internal architecture.
- Another tenant's data or attributes lacking appropriate consent/purpose.

Use stable subject IDs, minimize PII, and enforce retention/audit policies for claims. If using pairwise subjects for OIDC, maintain consistency per client/sector and never change them arbitrarily.

### 13.3. Versioning Claim Schemas

When changing data types or semantics, consider a claim schema version:

~~~json
{
  "https://claims.example.vn/claims_version": 2,
  "https://claims.example.vn/tenant_id": "tenant-a",
  "https://claims.example.vn/subject_type": "user"
}
~~~

Resource Servers must maintain compatibility while older tokens remain alive. Never change `tenant_id` from a string to an object without versioning/rollout; APIs may fail or bypass authorization.

### 13.4. Auditing Without Logging Tokens

Log audits using event ID, client ID, grant type, a protected subject reference, tenant, and policy version. Never log full JWTs/access tokens/refresh tokens, secrets, private keys, or Authorization headers. Metrics should not use raw user IDs/emails/tenant IDs as high-cardinality labels; choose safe categorical labels.

## 14. Checklist and Self-Check Questions

- [ ] Distinguish access tokens, ID Tokens, UserInfo, refresh tokens, and opaque tokens.
- [ ] Use `OAuth2TokenCustomizer<JwtEncodingContext>` for the JWT encoding path; do not expect it to cover every token format.
- [ ] Claims are chosen from verified `RegisteredClient`, grant type, principal, and authorization context.
- [ ] Client policies are server-managed; clients cannot toggle claims via request parameters.
- [ ] Client Credentials is handled as a service identity without impersonating a user.
- [ ] Tenant is verified against principal, client, membership, and policy; saved on the authorization transaction so refreshes use the right context.
- [ ] Never take tenant/role/audience/scope from query parameters, headers, or unverified tokens.
- [ ] Never overwrite standard claims like `iss`, `sub`, `aud`, `exp`, `iat`, `scope`, `nonce`, `auth_time`, and `cnf`.
- [ ] Never assign a new `auth_time` on refresh; `acr`/`amr` reflect actual evidence.
- [ ] Claims are minimal, strongly typed, namespaced, and schema-versioned when needed.
- [ ] Resource Server verifies issuer, audience, scope, tenant, and per-resource permissions.
- [ ] Tests cover every client/grant/principal/tenant and negative cases.
- [ ] JWT snapshot behavior, TTL, revocation, policy versions, and membership changes have been evaluated.
- [ ] Raw tokens/PII are never logged; audit records have defined retention and access control.

**Self-Check Questions**

1. At which stage of token generation does `OAuth2TokenCustomizer<JwtEncodingContext>` run?
2. Why must an authenticated client not be allowed to choose `tenant_id` in a token on its own?
3. How does the principal in Client Credentials differ from the principal in Authorization Code?
4. When refreshing a token, why must you never set `auth_time=Instant.now()`?
5. Why do access token claims, ID Token claims, and UserInfo require separate policies?
6. Does a JWT customizer apply to opaque access tokens? If not, which extension point should you inspect?
7. If a JWT carries `tenant_id=tenant-a` while the API request targets tenant-b, how must the Resource Server respond?
8. Why does adding `role=admin` to a token not by itself prove the user holds admin privileges?
9. Do already-issued JWTs immediately reflect membership/role changes in the database?
10. How do you verify that a customizer does not emit sensitive claims for unauthorized clients?

## References

- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `OAuth2Authorization`, token generation, and authorization state.
- [Spring Authorization Server — How-to: Customize the JWT](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html): using `OAuth2TokenCustomizer<JwtEncodingContext>` to add claims/authorities.
- [Spring Authorization Server — Token Generation](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html#oauth2-token-generator): `OAuth2TokenGenerator`, `JwtGenerator`, and token customizers.
- [Spring Authorization Server — OIDC UserInfo Endpoint](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html#oauth2-oidc-user-info-endpoint): customizing UserInfo claims.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): registered, public, and private claim names.
- [RFC 9068 — JSON Web Token (JWT) Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile and related claims.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, UserInfo, and OIDC claims.
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693): subject, actor, and delegation context.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): verifying JWTs and protecting APIs.
