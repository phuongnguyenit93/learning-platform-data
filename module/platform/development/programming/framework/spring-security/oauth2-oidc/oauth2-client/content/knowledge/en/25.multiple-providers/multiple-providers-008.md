# 25.8. Differences in Scopes, Claims, UserInfo, and Logout Across Providers

## 1. One Application Logging In via Multiple OpenID Providers

In **Spring Security OAuth 2.0 OIDC Client**, an application can let users log in through multiple **OpenID Providers (OPs)**: enterprise SSO, a partner provider, Google Identity, or Microsoft Entra ID. Each "Sign in" button looks similar at first glance, yet each OP can differ in **scopes**, **claims**, **UserInfo**, **user identifiers**, and **logout**.

~~~text
                          Spring Boot OIDC Client
                                  |
            +---------------------+---------------------+
            |                     |                     |
       Corporate OP           Partner OP           Workforce OP
       issuer A                issuer B             issuer C
       scope set A             scope set B          scope set C
       ID Token A              ID Token B           ID Token C
       UserInfo A              UserInfo B           UserInfo C
       logout A                logout B             logout C
            |                     |                     |
            +---------------------+---------------------+
                                  |
                     Claims normalization + policy
                                  |
                       Internal account / session
~~~

A common design mistake is treating provider A's claims as a universal standard:

~~~java
// ANTI-PATTERN: email and role claims are not uniform across providers.
String localUserId = oidcUser.getEmail();
boolean isAdmin = oidcUser.getClaimAsStringList("roles")
    .contains("admin");
~~~

This code can cause **account collisions**, **`NullPointerException`**, **wrong role assignments**, or accidentally merging two different people's identities.

### Lesson Objectives

After this lesson, you will be able to:

1. Distinguish **OIDC Core standards** from **provider-specific behavior**.
2. Understand that requested scopes differ from granted scopes; claims differ from application permissions.
3. Identify whether a claim resides in the ID Token or UserInfo, especially the `sub` matching rule.
4. Normalize identities by **issuer + subject**, accounting for pairwise subjects.
5. Configure multiple `ClientRegistration` entries and provider-specific adapters in Spring Security.
6. Choose logout policies suited to each OP's capabilities.
7. Design an integration test matrix for provider claims, scopes, and login sessions.

> **Scope:** examples use Spring Security Servlet/MVC, contrasted with WebFlux. Examples mentioning Google, Microsoft Entra ID, or Keycloak do not claim every tenant/provider version returns those exact claims. Always verify each deployment's metadata and contract.

## 2. Data Layers to Keep Clearly Separated

| Component | Role |
| --- | --- |
| `ClientRegistration` | Client ID, issuer/provider, endpoints, grant, scopes, redirect URI configuration |
| `OAuth2AuthorizedClient` | Authorization result holding Access Token/Refresh Token for a registration and principal |
| `OidcIdToken` | ID Token issued by the OP, used in OIDC authentication |
| `OidcUserInfo` | Additional claims from the UserInfo Endpoint |
| `OidcUser` | OIDC principal built by Spring Security |
| `OAuth2AuthenticationToken` | `Authentication` and registration ID of the OAuth2/OIDC Login |
| `GrantedAuthority` | Application permissions accepted per policy |
| `HttpSession` / `WebSession` | Relying Party (RP) session |
| OP SSO session | Identity provider session |

ID Token, Access Token, and Refresh Token do not share the same purpose:

~~~text
Authorization Code -> Token Endpoint
    ID Token      : authenticates the OIDC user to the client
    Access Token  : calls UserInfo or a Resource Server
    Refresh Token : requests new Access Tokens when issued
~~~

**Never use an ID Token as a Bearer Token for a business API** just because it is a JWT, and never treat a JWT Access Token meant for a Resource Server as a valid ID Token for login.

## 3. `ClientRegistration` Is the Provider Boundary

Example:

~~~text
registrationId = corporate
clientId       = portal-corporate
issuer         = https://sso.corp.example.net/realms/main

registrationId = partner
clientId       = portal-partner
issuer         = https://login.partner.example.org
~~~

`registrationId` is a key inside Spring Security—**not** an OAuth2 scope, JWT `aud`, OP user ID, or provider ID. One provider can have multiple client registrations with different client IDs, scopes, or redirect URIs.

### 3.1. Configuration that can vary by provider

| Property | Effect |
| --- | --- |
| `issuer-uri` | Defines trust boundary, supports Discovery |
| `authorization-uri` | Authorization Endpoint |
| `token-uri` | Token Endpoint |
| `jwk-set-uri` | Source of public keys for signature verification |
| `user-info-uri` | UserInfo Endpoint if provided |
| `client-id` / `client-secret` | Client identity/credentials |
| `scope` | Scopes requested in the authorization flow |
| `redirect-uri` | Callback that must be registered at the OP |
| Provider metadata | Logout capabilities, supported scopes, claims, algorithms |

Do not copy provider A's configuration to B simply by swapping the issuer. Provider B might use a different client authentication method, lack a UserInfo Endpoint, or require a different redirect URI.

## 4. Scopes Are Requests, Not Guarantees of Permission

Example request:

~~~http
GET /authorize?response_type=code&
  client_id=portal-corporate&
  scope=openid%20profile%20email&
  redirect_uri=https%3A%2F%2Fportal.example.net%2Flogin%2Foauth2%2Fcode%2Fcorporate&
  state=RANDOM_STATE&
  code_challenge=RANDOM_CHALLENGE&
  code_challenge_method=S256
~~~

The scopes here are **requested scopes**. The OP may approve them, prompt for consent, deny them, or grant a subset according to policy.

### 4.1. OIDC standard scopes

| Scope | Meaning | Do not infer |
| --- | --- | --- |
| `openid` | Initiates OIDC authentication | Not permission to call business APIs |
| `profile` | Requests profile claims | Does not guarantee all fields are returned |
| `email` | Requests `email`, `email_verified` | Does not turn email into a unique user ID |
| `address` | Requests address claim | Does not guarantee data is present |
| `phone` | Requests phone claims | Does not guarantee phone number is verified |
| `offline_access` | Requests offline access | Does not guarantee the OP issues a Refresh Token |

Scopes such as:

~~~text
reports.read
calendar.events.read
api://resource-id/report.read
https://api.example.net/auth/reports.read
~~~

are **provider/resource-specific API scopes**. Never treat two `read` strings at two Authorization Servers as the same permission.

### 4.2. Requested vs. granted scopes

~~~text
Authorization request:
  openid profile email calendar.read

Granted scopes:
  openid profile email

=> Client MUST NOT conclude it has calendar.read.
~~~

When needed, Spring Security allows reading `OAuth2AuthorizedClient.getAccessToken().getScopes()`. Nevertheless, **the Resource Server remains the final authority checking scopes/audience/policy**.

### 4.3. Scopes are not local roles

Portal's `ROLE_ADMIN` does not create a `reports.write` scope in an Access Token. Conversely, an Access Token having `reports.read` does not prove the user is a Portal admin. The two models require separate authorization policies.

## 5. Which Claims Do OIDC Scopes Request?

| Scope | Standard claims that may be requested |
| --- | --- |
| `profile` | `name`, `given_name`, `family_name`, `middle_name`, `nickname`, `preferred_username`, `profile`, `picture`, `website`, `gender`, `birthdate`, `zoneinfo`, `locale`, `updated_at` |
| `email` | `email`, `email_verified` |
| `address` | `address` |
| `phone` | `phone_number`, `phone_number_verified` |

Per OpenID Connect Core, **an OP is permitted to omit certain requested claims** for privacy or because data is unavailable. Never automatically treat a missing `email` as a protocol error in all cases.

For example:

~~~json
{
  "sub": "user-123",
  "name": "Demo User",
  "email": "user@example.net",
  "email_verified": true
}
~~~

and:

~~~json
{
  "sub": "person-890",
  "preferred_username": "person890"
}
~~~

can both occur under different contracts. If email is mandatory for the product, the application must **prompt to collect/verify it** or reject onboarding per policy; never assume `email_verified=true` when the claim is absent.

### 5.1. The `claims` request parameter

OIDC also supports requesting specific claims:

~~~json
{
  "userinfo": {
    "given_name": null,
    "email": {"essential": true}
  },
  "id_token": {
    "auth_time": {"essential": true}
  }
}
~~~

Not every provider supports the `claims` parameter. Discovery's `claims_parameter_supported` helps check support. Even when the OP supports it, the app still needs business policy for cases where an essential claim is omitted.

## 6. Comparing Common Providers

| Provider type | Claims you may encounter | Notes |
| --- | --- | --- |
| Generic OIDC | `iss`, `sub`, `aud`, profile/email if issued | Identity by issuer + subject |
| Google Identity | `sub`, `email`, `email_verified`, `hd` when applicable | Use `sub` as ID; `hd` supports Workspace policy |
| Microsoft Entra ID | `sub`, `tid`, `oid`, `preferred_username`, optional `roles`/`groups` | Tenant isolation, pairwise `sub`, group overage |
| Keycloak | OIDC claims and custom mapper roles/groups | Claim placement depends on protocol mapper |
| Partner OIDC | Custom `employee_id`, `org_id`, `entitlements` | Requires clear schema/trust policy |
| OAuth2-only provider | User endpoint `id`/`login`, no ID Token | Do not force into OIDC flow |

### 6.1. Google: email is not a stable identifier

Google recommends using `sub` as the account identifier instead of email, because email can change. To restrict to a Google Workspace domain, do not merely match an `@company.example` suffix—check the `hd` hosted-domain claim and appropriate membership policies per provider documentation.

### 6.2. Microsoft Entra: `tid`, `oid`, and `sub` differ

- `tid`: tenant ID, not the user's ID.
- `oid`: user's object ID within the tenant, when the claim is present.
- `sub`: subject, which can be a **pairwise identifier** per client/application.
- `preferred_username`: convenient for display, can change.
- `groups`: may be absent due to **group overage**; when needed, querying Microsoft Graph with granted permissions may be required.

Do not expect `tid`/`oid` on other OPs: these are not mandatory OIDC Core claims.

### 6.3. Keycloak: role shapes are not uniform

For example, one realm might return:

~~~json
{
  "realm_access": {
    "roles": ["report-reader"]
  },
  "resource_access": {
    "portal-client": {
      "roles": ["team-editor"]
    }
  }
}
~~~

However, claims may be placed into the **Access Token** rather than the **ID Token** or UserInfo. Realm/client scopes/protocol mappers control this. Never use an Access Token meant for another API as an OIDC principal without an appropriate contract and validation.

### 6.4. Partner custom claims

~~~json
{
  "sub": "partner-481",
  "employee_id": "E-102",
  "org_id": "partner-a",
  "entitlements": ["purchase-orders.read"]
}
~~~

For non-standard claims, explicitly define: where they are issued, data types, stability, who controls them, privacy impact, and business authorization mapping. Never use `employee_id` as a global ID without namespacing by issuer.

## 7. ID Tokens Must Be Verified Against the Exact `ClientRegistration`

OIDC authentication normally requires checking:

- Signature and allowed signing algorithms; never accept `alg=none`.
- `iss` matches the configured issuer.
- `aud` contains the exact client ID; handle `azp` if protocol conditions require it.
- `exp`, `iat`, clock skew, and time conditions.
- `nonce` per flow/authorization request when required.
- `auth_time`, `at_hash`/`c_hash` when applicable per flow/policy.

Anti-pattern:

~~~java
// DO NOT USE: decoding payload does not mean verifying the token.
Map<String, Object> claims = decodeJwtWithoutVerification(rawJwt);
String userId = claims.get("sub").toString();
createAuthenticatedSession(userId);
~~~

**Provider adapters must run after ID Token validation**; never rewrite issuer or subject to match a value that "looks right."

### 7.1. ID Token differs from Access Token

An Access Token can be an opaque string or a JWT containing `sub` and `scope`, yet it is meant for a Resource Server. Never use a JWT Access Token as an ID Token just because it also contains a user ID.

## 8. Stable User Identity = Issuer + Subject

Example:

~~~text
Provider A:
  iss = https://sso.corp.example.net
  sub = 42

Provider B:
  iss = https://login.partner.example.org
  sub = 42
~~~

Two `sub=42` values **do not mean the same person**. An OIDC subject is an ID within the scope of an issuer. External identity keys should rely on:

~~~text
(issuer, subject)
~~~

A logical schema:

~~~text
user_account
  id = internal-user-100
  status = ACTIVE

external_identity
  internal_user_id = internal-user-100
  issuer = https://sso.corp.example.net
  subject = corp-55
  registration_id = corporate

external_identity
  internal_user_id = internal-user-100
  issuer = https://login.partner.example.org
  subject = partner-992
  registration_id = partner
~~~

Two external identities may only be linked to the same internal account via a **verified account linking workflow**.

### 8.1. Do not auto-link by email

Emails can change, be recycled, be unverified, or span multiple providers. Even when both providers return `email_verified=true`, that does not prove the user consented to linking the two accounts into one.

### 8.2. Pairwise subjects

An OP can issue:

~~~text
Same OP, same human:
  Portal client -> sub = pairwise-123
  Mobile client -> sub = pairwise-789
~~~

Do not auto-merge by email. If account correlation across client IDs is needed, use an approved identity linking mechanism or provider-specific stable identifiers per contract.

### 8.3. Registration context

The `issuer + sub` pair is usually the foundation of OIDC identity. With pairwise subjects, multi-tenancy, multiple client IDs, or complex account linking, storing registration/client context may also be necessary. Choose uniqueness constraints according to the OP's privacy/identity semantics.

## 9. What Is the UserInfo Endpoint?

UserInfo is a protected OIDC endpoint where the RP uses an **Access Token** to retrieve additional claims if supported by the provider.

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant RP as Spring Security Client
    participant OP as OpenID Provider
    participant UI as UserInfo Endpoint
    Browser->>RP: Start OIDC Login
    RP-->>Browser: Authorization redirect
    Browser->>OP: Authenticate and consent
    OP-->>Browser: code + state
    Browser->>RP: OAuth2 callback
    RP->>OP: Token request
    OP-->>RP: ID Token + Access Token
    RP->>RP: Validate ID Token
    opt UserInfo called per config
        RP->>UI: Bearer Access Token
        UI-->>RP: UserInfo claims
        RP->>RP: Verify UserInfo sub == ID Token sub
    end
    RP->>RP: Build OidcUser and apply local policy
    RP-->>Browser: Local session + redirect
~~~

### 9.1. ID Token and UserInfo differ

| | ID Token | UserInfo |
| --- | --- | --- |
| Source | Token Endpoint | UserInfo Endpoint |
| Purpose | OIDC authentication | Additional claims |
| Format | Signed JWT, optionally encrypted | Usually JSON, optionally signed/encrypted JWT |
| Credentials | Token exchange | Access Token sent to UserInfo |
| `sub` | Verified subject | Required, must match ID Token |
| Freshness | When token was issued | When UserInfo response is returned |

### 9.2. The `sub` rule is mandatory

OIDC Core requires `sub` in UserInfo **MUST match exactly** `sub` in the ID Token. If they differ, **never use the UserInfo values**:

~~~text
ID Token:  sub = alice-123
UserInfo:  sub = bob-456, email = bob@example.org

=> Reject/discard UserInfo data.
~~~

HTTP 200 and valid-looking JSON do not prove UserInfo belongs to the same end-user. This defends against **token substitution**.

### 9.3. UserInfo omitting a requested claim is not automatically an error

A provider may return only:

~~~json
{
  "sub": "person-890",
  "name": "Demo User"
}
~~~

even when the app requested `email`. If email is mandatory, the app must prompt for and verify it separately or reject the workflow per policy; never fabricate placeholder addresses.

### 9.4. UserInfo is not a Directory API

Providers may omit groups/roles from UserInfo. That data may come from a Directory/Graph API requiring an Access Token with the right audience/scope, consent, and rate limits. Never call admin APIs with broad Client Credentials just to fill in a missing claim without an authorization policy.

## 10. Discovery Metadata: Checking Actual Capabilities

Example metadata:

~~~json
{
  "issuer": "https://id.example.net",
  "authorization_endpoint": "https://id.example.net/authorize",
  "token_endpoint": "https://id.example.net/token",
  "jwks_uri": "https://id.example.net/jwks",
  "userinfo_endpoint": "https://id.example.net/userinfo",
  "scopes_supported": ["openid", "profile", "email"],
  "claims_supported": ["sub", "name", "email"],
  "end_session_endpoint": "https://id.example.net/connect/endsession"
}
~~~

These are **illustrative values**, not live endpoints to call.

| Metadata | Meaning |
| --- | --- |
| `issuer` | Issuer that must match the ID Token |
| `authorization_endpoint` | Where the browser begins authorization |
| `token_endpoint` | Where codes/refresh tokens are exchanged |
| `jwks_uri` | Issuer's signing keys |
| `userinfo_endpoint` | UserInfo if available |
| `scopes_supported` | Advertised scopes |
| `claims_supported` | Claims the OP can issue, not guaranteed for every user |
| `claims_parameter_supported` | Whether the `claims` parameter is supported |
| `end_session_endpoint` | RP-Initiated Logout capability |
| `backchannel_logout_supported` | Back-Channel Logout capability |
| `backchannel_logout_session_supported` | Whether the OP can support `sid` |

**Never construct UserInfo/logout URLs by appending `/userinfo` or `/logout` to the issuer** if the OP does not publish them or lack a reliable provider-specific contract.

## 11. Configuring Multiple Providers in Spring Boot

Spring Boot 3.x and Spring Security 6.x example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-oidc
            client-id: ${CORPORATE_OIDC_CLIENT_ID}
            client-secret: ${CORPORATE_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          partner:
            provider: partner-oidc
            client-id: ${PARTNER_OIDC_CLIENT_ID}
            client-secret: ${PARTNER_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
          workforce:
            provider: workforce-oidc
            client-id: ${WORKFORCE_OIDC_CLIENT_ID}
            client-secret: ${WORKFORCE_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          corporate-oidc:
            issuer-uri: https://sso.corp.example.net/realms/main
          partner-oidc:
            issuer-uri: https://login.partner.example.org
          workforce-oidc:
            issuer-uri: https://login.microsoftonline.com/00000000-0000-0000-0000-000000000000/v2.0
~~~

All URLs, GUIDs, and secret names are **placeholders**. Each redirect URI must be registered accurately at its OP; client credentials come from a protected secret manager/environment and are never committed to source.

### 11.1. Provider ID is not registration ID

~~~text
registrationId = corporate
providerId = corporate-oidc
clientId = value of CORPORATE_OIDC_CLIENT_ID
~~~

Default Spring Security login initiation endpoints:

~~~text
/oauth2/authorization/corporate
/oauth2/authorization/partner
/oauth2/authorization/workforce
~~~

Callbacks:

~~~text
/login/oauth2/code/corporate
/login/oauth2/code/partner
/login/oauth2/code/workforce
~~~

### 11.2. Servlet dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Spring Boot 4.x changed some module/starter names; use the matching BOM version and never mix Spring Security 6.x and 7.x.

## 12. `SecurityFilterChain` and Provider Selection Page

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiProviderSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/signed-out", "/error")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login"))
            .build();
    }
}
~~~

`/login` must be implemented by the app when customizing the login page. Example links:

~~~text
Corporate Login -> /oauth2/authorization/corporate
Partner Login   -> /oauth2/authorization/partner
Workforce Login -> /oauth2/authorization/workforce
~~~

Never let users supply arbitrary issuer URLs/JWKS URIs and treat them as trusted providers. Registrations must belong to a **server-side allowlist**.

### 12.1. Login CSRF and authorization response mix-up

With multiple providers, Spring Security's correlation via `state`, authorization request repository, and OAuth2/OIDC checks are especially critical. Never pick the registration from a callback query parameter while ignoring the registration tied to the initial request.

## 13. Reading Verified Registration, Issuer, and Subject

~~~java
package com.example.web;

import org.springframework.security.oauth2.client.authentication.OAuth2AuthenticationToken;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/identity")
    public IdentityView identity(
            OAuth2AuthenticationToken authentication) {

        String registrationId =
            authentication.getAuthorizedClientRegistrationId();
        OidcUser user = (OidcUser) authentication.getPrincipal();

        String issuer = user.getIdToken().getIssuer().toString();
        String subject = user.getSubject();

        return new IdentityView(registrationId, issuer, subject);
    }

    public record IdentityView(
            String registrationId, String issuer, String subject) {
    }
}
~~~

This example assumes the endpoint only accepts **OIDC Login**. If the application also has form login or non-OIDC OAuth2 Login, check the `Authentication`/principal type before casting. Never return raw tokens/claim graphs to the browser.

`authentication.getName()` is insufficient as a **global account ID** if it lacks the issuer or uses a custom name attribute. Keep explicit `issuer + sub` from the verified ID Token.

## 14. Normalizing Claims into `ExternalIdentity`

~~~text
Verified OidcUser
   |
   v
Provider-specific normalizer
   +-- issuer + subject (required)
   +-- email + verified (optional)
   +-- displayName (optional)
   +-- tenant/organization (provider-specific)
   |
   v
ExternalIdentity
   |
   v
Account linking + authorization policy
~~~

~~~java
package com.example.identity;

public record ExternalIdentity(
    String registrationId,
    String issuer,
    String subject,
    String displayName,
    String email,
    boolean emailVerified,
    String providerTenant) {
}
~~~

### 14.1. Illustrative normalizer

~~~java
package com.example.identity;

import java.util.Map;
import java.util.Objects;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public final class ProviderIdentityNormalizer {

    public ExternalIdentity normalize(
            String registrationId, OidcUser verifiedUser) {

        Objects.requireNonNull(registrationId);
        Objects.requireNonNull(verifiedUser);

        String issuer =
            verifiedUser.getIdToken().getIssuer().toString();
        String subject = verifiedUser.getSubject();

        if (issuer.isBlank()
                || subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                "Missing verified OIDC identity");
        }

        Map<String, Object> claims = verifiedUser.getClaims();

        String email = textClaim(claims, "email");
        boolean emailVerified =
            Boolean.TRUE.equals(claims.get("email_verified"));

        String displayName = textClaim(claims, "name");
        if (displayName == null) {
            displayName =
                textClaim(claims, "preferred_username");
        }

        String tenant = switch (registrationId) {
            case "workforce" -> textClaim(claims, "tid");
            case "corporate" -> textClaim(claims, "organization_id");
            default -> null;
        };

        return new ExternalIdentity(
            registrationId, issuer, subject,
            displayName, email, emailVerified, tenant);
    }

    private static String textClaim(
            Map<String, Object> claims, String name) {

        Object value = claims.get(name);
        return value instanceof String text && !text.isBlank()
            ? text : null;
    }
}
~~~

`organization_id` is a **fictional custom claim**, meaningful only when a real provider issues it under an approved contract. `email_verified` is only treated as true when it is an actual boolean; do not coerce a string `"true"` into verification without an explicit policy.

### 14.2. Identity normalization does not automatically grant roles

A normalized profile **does not determine** whether a user may administer a tenant or access confidential documents. Those permissions must rely on account status, tenant membership, trusted role mapping, and an authorization service.

## 15. Customizing `OidcUserService` in Spring Security

With Servlet/OIDC, you can wrap the default `OidcUserService` and enforce per-registration application policy:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserRequest;
import org.springframework.security.oauth2.client.oidc.userinfo.OidcUserService;
import org.springframework.security.oauth2.client.userinfo.OAuth2UserService;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ProviderAwareOidcConfig {

    @Bean
    OAuth2UserService<OidcUserRequest, OidcUser> providerUserService() {
        OidcUserService delegate = new OidcUserService();

        return request -> {
            OidcUser user = delegate.loadUser(request);
            String registrationId =
                request.getClientRegistration().getRegistrationId();

            if ("workforce".equals(registrationId)) {
                String tenantId = user.getClaimAsString("tid");

                // Production: expected tenant from trusted configuration.
                if (!"APPROVED_TENANT_ID".equals(tenantId)) {
                    throw new OAuth2AuthenticationException(
                        new OAuth2Error("tenant_not_allowed"));
                }
            }

            return user;
        };
    }

    @Bean
    SecurityFilterChain chain(
            HttpSecurity http,
            OAuth2UserService<OidcUserRequest, OidcUser>
                    providerUserService) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .userInfoEndpoint(info -> info
                    .oidcUserService(providerUserService)))
            .build();
    }
}
~~~

**This is an alternative to the `SecurityFilterChain` in section 12**—do not register two catch-all chains simultaneously without matchers/ordering. `"APPROVED_TENANT_ID"` is a placeholder, not a real tenant; load it from trusted deployment config.

Never use this adapter to rewrite issuer or subject, skip ID Token validation, or call arbitrary UserInfo URIs.

### 15.1. OIDC `UserService` vs. OAuth2 `UserService`

| Use case | Service |
| --- | --- |
| OIDC Login with ID Token | `OidcUserService` |
| OAuth2-only Login without ID Token | `DefaultOAuth2UserService` |
| Reactive OIDC Login | Corresponding Reactive OIDC UserService |
| Provider Directory/Graph API | Dedicated API adapter with matching Access Token/permissions |

If a provider does not genuinely support OIDC, do not force it into `OidcUserService` by arbitrarily adding `openid`.

## 16. Roles and `GrantedAuthorities` Must Be Mapped per Provider

Example three claim shapes:

~~~json
{"groups": ["finance-reporters"]}
~~~

~~~json
{"roles": ["Report.View"]}
~~~

~~~json
{"realm_access": {"roles": ["read-reports"]}}
~~~

These three strings do not automatically carry the same meaning. An approved mapping is needed:

~~~text
(issuer A, group finance-reporters) -> ROLE_REPORT_VIEWER
(issuer B, app role Report.View)     -> ROLE_REPORT_VIEWER
(issuer C, realm role read-reports)  -> ROLE_REPORT_VIEWER
~~~

### 16.1. Never blindly turn raw claims into `ROLE_ADMIN`

~~~java
// ANTI-PATTERN if trusted issuer/schema are not checked.
new SimpleGrantedAuthority("ROLE_" + rawRole);
~~~

An `admin` role at a provider may only administer another service, not the Portal.

### 16.2. Illustrative `GrantedAuthoritiesMapper`

~~~java
package com.example.security;

import java.util.HashSet;
import java.util.Set;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;
import org.springframework.security.oauth2.core.oidc.user.OidcUserAuthority;

@Configuration
public class RoleMappingConfig {

    @Bean
    GrantedAuthoritiesMapper providerRoles() {
        return authorities -> {
            Set<GrantedAuthority> mapped = new HashSet<>(authorities);

            for (GrantedAuthority authority : authorities) {
                if (!(authority instanceof OidcUserAuthority oidc)) {
                    continue;
                }

                String issuer =
                    oidc.getIdToken().getIssuer().toString();
                Object raw = oidc.getAttributes().get("app_roles");

                if ("https://sso.corp.example.net/realms/main"
                        .equals(issuer)
                        && raw instanceof java.util.Collection<?> roles
                        && roles.contains("report-reader")) {
                    mapped.add(new SimpleGrantedAuthority(
                        "ROLE_REPORT_VIEWER"));
                }
            }
            return mapped;
        };
    }
}
~~~

`app_roles` is an **illustrative custom claim** of a corporate OP. Wire the mapper in the OAuth2 Login DSL:

~~~java
.oauth2Login(oauth2 -> oauth2
    .userInfoEndpoint(info -> info
        .userAuthoritiesMapper(providerRoles)))
~~~

This is a DSL fragment; inject the `providerRoles` bean appropriately and avoid duplicate `SecurityFilterChain` beans. Never assume roles are always present on the OIDC principal if the OP only places them in Access Tokens or another API.

### 16.3. Group overage and role freshness

Some OPs like Microsoft Entra may omit full group IDs from tokens. **Absence of a `groups` claim does not necessarily mean the user belongs to no groups.** When permissions depend on group memberships, establish an approved API query/caching/retry/fail-closed policy.

## 17. Classifying Claims by Purpose

| Claim | Display | Identity key | Authorization |
| --- | --- | --- | --- |
| `iss` | Rarely | **Yes, with `sub`** | Trusted issuer boundary |
| `sub` | Rarely | **Yes, with `issuer`** | Per internal account mapping |
| `email` | Yes | **No** | Not by default |
| `email_verified` | Maybe | No | Does not replace role/MFA |
| `name` | Yes | No | No |
| `preferred_username` | Yes | No | No |
| `tid` (Entra) | Maybe | Tenant context | Tenant allowlist |
| `oid` (Entra) | Rarely | Provider-specific stable identifier | Enterprise policy |
| `hd` (Google) | Maybe | No | Can support Workspace domain policy |
| `groups`/`roles` | Maybe | No | Only per trusted issuer/schema/map |
| `sid` | No | No | Session correlation/logout |

Do not persist every claim "just in case"; they can contain PII or security-sensitive group memberships. Apply data minimization and retention policies.

## 18. Logout: One Word, Multiple Distinct Sessions

~~~text
Browser
  +-- Portal local session
  +-- Corporate OP SSO session
  +-- Partner OP SSO session
  +-- Workforce OP SSO session
  +-- OAuth2 Authorized Client tokens
~~~

Logging out of the Portal **does not automatically** end the other states.

| Mechanism | Initiated by | Effect |
| --- | --- | --- |
| Local Logout | Browser/RP | Invalidates RP local session |
| RP-Initiated Logout | RP redirects browser to OP | Requests OP to end SSO session |
| Front-Channel Logout | OP via browser/iframe/redirect | OP notifies RPs through the user agent |
| Back-Channel Logout | OP server-to-server | Signed Logout Token telling RP to end sessions |

### 18.1. Local logout does not guarantee password prompts on re-login

~~~text
Portal local logout -> RP session is destroyed
OP SSO cookie remains
User clicks Login -> OP may auto-SSO login again
~~~

This can be valid behavior. If the product requires re-authentication, enforce policies like `max_age`, `prompt=login`, and `auth_time` per OP capability, rather than merely deleting the Portal cookie.

## 19. RP-Initiated Logout and `end_session_endpoint`

An OP may publish:

~~~json
{
  "issuer": "https://id.example.net",
  "end_session_endpoint": "https://id.example.net/connect/endsession"
}
~~~

Never guess the endpoint by appending `/logout` to the issuer. The actual URL must come from Discovery or a trusted provider-specific contract.

### 19.1. Common parameters

| Parameter | Role |
| --- | --- |
| `id_token_hint` | Previous ID Token, hinting client/user session to the OP |
| `post_logout_redirect_uri` | Where to ask the browser to return; typically must be registered |
| `state` | Correlation when returning to the RP after logout |
| `logout_hint` | Provider-specific hint |
| `client_id` | May be required depending on OP/spec conditions |

Never substitute an Access Token for an `id_token_hint`, and never send a Client Secret in a logout URL.

### 19.2. Open redirects

Never forward browser input directly:

~~~text
/logout?returnUrl=https://attacker.example/collect
~~~

into `post_logout_redirect_uri`. Accept only registered redirect URIs controlled by the RP/OP.

## 20. Spring Security Servlet: RP-Initiated Logout

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.logout.OidcClientInitiatedLogoutSuccessHandler;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.logout.LogoutSuccessHandler;

@Configuration
public class MultiProviderLogoutConfig {

    @Bean
    LogoutSuccessHandler oidcLogoutSuccessHandler(
            ClientRegistrationRepository registrations) {

        OidcClientInitiatedLogoutSuccessHandler handler =
            new OidcClientInitiatedLogoutSuccessHandler(registrations);
        handler.setPostLogoutRedirectUri("{baseUrl}/signed-out");
        return handler;
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            LogoutSuccessHandler oidcLogoutSuccessHandler)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    "/", "/login", "/signed-out", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login"))
            .logout(logout -> logout
                .logoutSuccessHandler(oidcLogoutSuccessHandler))
            .build();
    }
}
~~~

**This is an alternative configuration**—do not copy it alongside catch-all `SecurityFilterChain` beans from earlier sections. The OP must register the matching `post_logout_redirect_uri`.

### 20.1. Selecting the OP of the current `Authentication`

`OidcClientInitiatedLogoutSuccessHandler` uses the OIDC `Authentication` and `ClientRegistrationRepository` to pick the OP logout metadata of the matching registration. Never let a caller choose provider B to send provider A's ID Token to a different endpoint.

### 20.2. OP does not support end-session

If the OP lacks `end_session_endpoint`, provide a **local logout fallback** and UX that accurately states the logout scope, without claiming the OP SSO session ended.

### 20.3. CSRF

Local logout in a Servlet browser app should normally use POST with CSRF protection per configuration. Never disable CSRF app-wide just to make GET logout convenient.

## 21. Reactive/WebFlux Logout Uses a Different Handler

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.oidc.web.server.logout.OidcClientInitiatedServerLogoutSuccessHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.logout.ServerLogoutSuccessHandler;

@Configuration
public class ReactiveLogoutConfig {

    @Bean
    ServerLogoutSuccessHandler oidcServerLogoutSuccessHandler(
            ReactiveClientRegistrationRepository registrations) {

        OidcClientInitiatedServerLogoutSuccessHandler handler =
            new OidcClientInitiatedServerLogoutSuccessHandler(
                registrations);
        handler.setPostLogoutRedirectUri("{baseUrl}/signed-out");
        return handler;
    }

    @Bean
    SecurityWebFilterChain webFilterChain(
            ServerHttpSecurity http,
            ServerLogoutSuccessHandler oidcServerLogoutSuccessHandler) {

        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/signed-out", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessHandler(oidcServerLogoutSuccessHandler))
            .build();
    }
}
~~~

The Reactive example is an **alternative application** to Servlet—do not mix cross-stack classes into a `SecurityFilterChain`. WebFlux uses `SecurityWebFilterChain`, `ServerLogoutSuccessHandler`, and `ServerWebExchange`/`Mono<Void>`.

## 22. Front-Channel and Back-Channel Logout Are Not the Same

### 22.1. Front-Channel

The OP uses the browser/iframe/redirect to notify RPs of logout. It can be hindered by third-party cookie restrictions, iframe security, `SameSite` policies, and browsers not having the right site open. Do not assume it is reliable in every environment.

### 22.2. Back-Channel

The OP sends a direct POST:

~~~http
POST /logout/connect/back-channel/corporate HTTP/1.1
Host: portal.example.net
Content-Type: application/x-www-form-urlencoded

logout_token=SIGNED_LOGOUT_JWT
~~~

A Logout Token is a logout-event JWT, **not an ID Token or Access Token**. The RP must verify its signature, issuer, audience, timestamps, event marker, `sid`/`sub`, and other conditions before invalidating sessions.

Supporting Spring Security versions offer the `oidcLogout().backChannel(...)` DSL, with default endpoint:

~~~text
/logout/connect/back-channel/{registrationId}
~~~

**Having `end_session_endpoint` does not prove a provider supports Back-Channel Logout.** Check `backchannel_logout_supported` and client registration at the OP.

### 22.3. OP `sid` is not RP local session ID

~~~text
OP sid        = op-session-123
RP JSESSIONID = rp-session-987
~~~

The RP needs an OIDC session registry linking issuer/client/`sid`/`sub` to local sessions. Never take `sid` from a Logout Token and treat it as a `JSESSIONID` cookie.

### 22.4. Logout selection matrix

| Provider capability | Handling approach |
| --- | --- |
| Has `end_session_endpoint` + registered post-logout URI | RP-Initiated Logout |
| Lacks end-session metadata | Local logout or trusted provider adapter |
| Has Back-Channel Logout | Register endpoint and session registry |
| Has Front-Channel Logout | Test browser/cookie constraints |
| Only proprietary logout API | Integrate per contract; do not assume OIDC |
| OAuth2-only provider | Never assume OIDC SSO/logout |

## 23. Local Logout Does Not Mean Revoking OAuth2 Tokens

~~~text
RP local session:
  INVALIDATED

Access Token:
  may remain valid until exp

Refresh Token:
  may remain in OAuth2AuthorizedClientService
~~~

| Action | Effect |
| --- | --- |
| `HttpSession.invalidate()` | Ends RP session |
| RP-Initiated Logout | Requests OP logout |
| Back-Channel Logout | OP asks RP to invalidate session |
| `removeAuthorizedClient(...)` | Deletes local token record |
| RFC 7009 Revocation | Asks Authorization Server to revoke token |
| Resource Server validation | API decides whether token is still accepted |

**Never promise "log out of every application"** without designing SSO logout propagation, token expiration/revocation, and offline access handling.

### 23.1. Offline access is separate from the browser session

A Refresh Token issued under offline access may be permitted to sync APIs even after the user leaves the browser. Disconnecting an OAuth2 connection and browser logout need separate policies.

### 23.2. Unlinking differs from Logout

Logout ends a session; disconnecting usually removes/revokes tokens; unlinking removes the link between an external identity and an internal account after permission checks. Never permanently delete identity mappings just because of an OP logout event.

## 24. Account Linking Across Providers

A user may log in with Corporate, then link Partner:

~~~text
internal-user-100
  +-- Corporate: (issuer A, sub A)
  +-- Partner:   (issuer B, sub B)
~~~

Safe workflow:

1. Current user is authenticated and permitted to link.
2. User actively chooses to link the new OP.
3. Run authorization code + `state`/PKCE + OIDC verification.
4. Obtain verified `iss + sub` from the new OP.
5. Check the identity is not already linked to another account.
6. Perform reauthentication/step-up if required by policy.
7. Write the mapping atomically and audit the acting subject.
8. Never elevate privileges or merge solely because of matching emails.

## 25. Multi-Tenant Provider Routing

~~~text
tenant alpha -> corporate-alpha registration
tenant beta  -> corporate-beta registration
partner      -> partner registration
~~~

Tenant/email domain/query parameters can help suggest a provider for the UI, yet **never decide trusted issuer/JWKS/role mapping on their own**.

~~~java
enum LoginProvider {
    CORPORATE,
    PARTNER,
    WORKFORCE
}

static String registrationId(LoginProvider provider) {
    return switch (provider) {
        case CORPORATE -> "corporate";
        case PARTNER -> "partner";
        case WORKFORCE -> "workforce";
    };
}
~~~

This is a fragment inside a Java class for server-side mapping. Never let the browser send `issuer=https://attacker.example` and have the backend download signing keys and accept attacker-signed JWTs.

## 26. Symptom-Based Troubleshooting

| Symptom | Possible cause | Check |
| --- | --- | --- |
| Provider A login works, provider B fails | Wrong issuer/client ID/redirect URI/client auth | `ClientRegistration`, metadata |
| `invalid_scope` only on B | Unsupported scope or missing consent | OP's scope policy |
| Missing email despite requesting `email` | Provider privacy/data policy | Missing-claim handling |
| `email_verified` absent | OP does not issue it | Do not default to true |
| Two users merged | Using email/username as unique ID | Issuer + `sub`, account linking |
| Same OP yet `sub` differs across clients | Pairwise subject | Sector/client ID policy |
| UserInfo `sub` differs from ID Token | Token substitution/mismatch | Discard UserInfo data |
| UserInfo returns 401 | Wrong/expired token or wrong audience | UserInfo endpoint and Access Token |
| Keycloak roles missing in ID Token | Protocol mapper places roles in another token | Claim placement |
| Entra groups absent | Group overage/optional claims | Provider-specific API policy |
| Login succeeds yet API returns 403 | Access Token lacks scope/audience | Resource Server authorization |
| Local logout, re-login happens immediately | OP SSO cookie still active | RP-Initiated Logout/reauth policy |
| OP logout redirect 400 | Post-logout URI not registered | Exact match URI |
| OP lacks `end_session_endpoint` | No standard RP-Initiated Logout | Local fallback |
| Back-channel fails to invalidate RP session | Registry, cookie, network, security chain | Protocol integration test |
| API token still works after logout | Not expired/not revoked | Token lifecycle policy |
| Logging out A deletes B's tokens | Removal not scoped by issuer/registration | Provider isolation |

### 26.1. Short debugging checklist

~~~text
1. Which registrationId was actually used?
2. Does the issuer match the ID Token iss?
3. Which scopes were requested vs. granted?
4. Is the claim in ID Token, UserInfo, or a separate API?
5. Does UserInfo sub match ID Token sub?
6. Are custom claim types/schemas accurate?
7. Does account linking rely on email?
8. Is role mapping scoped by trusted issuer/tenant?
9. Is the failure at login or at a downstream API?
10. Are RP logout, OP logout, and token revocation distinguished?
~~~

No need to print raw ID Tokens, Access Tokens, or UserInfo bodies to debug; use redacted metadata and correlation IDs.

## 27. Testing Scopes/Claims/UserInfo per Provider

| Case | Expectation |
| --- | --- |
| Corporate has `sub` but lacks email | Fall back or reject per product policy |
| Partner `email_verified=false` | Do not treat email as verified |
| Workforce `tid` outside allowlist | Reject tenant |
| Google `hd` outside allowlist | Do not grant corporate membership |
| Custom roles have wrong type | Do not grant role |
| Scope requested but not granted | Do not assume API permission |
| Wrong ID Token issuer/audience | Authentication fails |
| UserInfo `sub` differs from ID Token | Reject/discard UserInfo |
| UserInfo lacks profile claim | No `NullPointerException` |
| Provider has no UserInfo | Do not invent an endpoint |
| Custom claim schema changes | Contract test catches it |

### 27.1. Identity linking tests

| Case | Expectation |
| --- | --- |
| Two OPs share email | Do not auto-link |
| Two OPs share raw `sub` | Do not collide |
| Pairwise `sub` differs by client ID | Do not auto-merge via email |
| Identity already linked to another account | Reject or secure re-link flow |
| Provider A admin, Provider B user | Do not keep A's `ROLE_ADMIN` automatically |
| Unlink one provider | Do not delete unrelated accounts |

### 27.2. Logout tests

| Case | Expectation |
| --- | --- |
| OP has `end_session_endpoint` | Redirects to the right OP |
| OP lacks `end_session_endpoint` | Local logout fallback |
| Unregistered post-logout URI | Error caught, no open redirect |
| Browser picks provider B when logged in via A | Never send A's ID Token to B |
| Back-channel token badly signed | Session not deleted |
| Back-channel includes `sid` | Only matching session deleted |
| Back-channel has `sub` only | Scoped to right issuer/client |
| Local logout while OP SSO remains | New login may auto-SSO |
| Access Token still unexpired | Do not assume revoked |
| Event hits node different from login node | Registry/session store consistent |

### 27.3. Test layers

~~~text
Unit:
  ProviderClaimsAdapter + role mapping + tenant policy

Spring Security integration:
  registration routing, session, OidcUserService

OIDC protocol integration:
  mock OP, state, PKCE, ID Token, UserInfo sub, nonce

Provider sandbox contract:
  scopes, discovery, claim schema, logout endpoint

Operational monitoring:
  login/logout failure rates per provider
~~~

Mocking a single `OidcUser` does not prove an app works across multiple providers. Negative tests for issuer mismatches, missing claims, and logout are also required.

## 28. Practical Scenarios

### A — Corporate and Partner both return Alice's email

Both OPs return `alice@example.net`, `email_verified=true`.

**Solution:** keep two separate external identities `(iss, sub)`; link to one internal account only after a permission-checked flow.

### B — OP omits email despite requesting `email` scope

The application requires an email for notifications.

**Solution:** ask the user to provide and verify it or stop onboarding per policy; never fabricate fake emails.

### C — UserInfo returns a different `sub` than ID Token

ID Token `sub=alice`, UserInfo `sub=bob` despite HTTP 200.

**Solution:** discard UserInfo data; investigate token substitution/Access Token mismatch.

### D — Provider A issues roles, provider B issues groups via Directory API

**Solution:** separate allowlisted adapters and API permissions; never auto-grant `ROLE_ADMIN` when Directory API is unavailable.

### E — Google email suffix matches Workspace without proving membership

**Solution:** use hosted-domain evidence and organization policy per provider; never rely on email suffix matching alone.

### F — Using `tid` as user ID in Entra

All employees in the same tenant share the same `tid`.

**Solution:** `tid` is the tenant; user identity uses `iss + sub` or `tid + oid` in Entra-specific integrations when designed accordingly.

### G — Portal logout followed by passwordless re-login

**Solution:** distinguish local sessions from OP SSO sessions; use RP-Initiated Logout or reauth policies if genuinely required.

### H — Partner has no `end_session_endpoint`

**Solution:** never guess `/logout`; perform local logout only or use a trusted proprietary contract.

### I — Keycloak roles appear only in the Access Token

**Solution:** inspect protocol mappers/client scopes; never treat an Access Token meant for another API as an OIDC principal.

### J — Entra group overage

**Solution:** apply policy and Graph API with proper permissions; never treat absent `groups` as empty membership.

### K — Logging out OP A deletes OP B's tokens

**Solution:** scope by issuer/client/session; handle token revocation/disconnect under separate policies.

### L — User changes `preferred_username`

**Solution:** update display profile; keep internal account link by `issuer + sub`.

### M — OAuth2-only provider without ID Token

**Solution:** use OAuth2 Login; do not force OIDC `UserService`/logout semantics.

### N — One person has two pairwise subjects

**Solution:** provider-approved account correlation, never auto-merge by email.

## 29. Pre-Production Checklist

| Question | What to check |
| --- | --- |
| Does the OP genuinely support OIDC? | Discovery and ID Token contract |
| Is `issuer-uri` right? | Exact issuer validation |
| Are Client IDs/redirect URIs right? | OP console, callback tests |
| Are scopes granted? | Consent and actual granted scopes |
| Can claims be missing? | Null/type handling |
| Does UserInfo `sub` match ID Token? | Mandatory |
| Is the identity key stable? | Issuer + `sub`, pairwise handling |
| Is email verification clear? | Boolean, missing claims, provider semantics |
| Is roles/groups mapping safe? | Trusted issuer/schema/allowlist |
| Multi-tenant isolation? | No arbitrary issuer/JWKS |
| Are app roles and API scopes separated? | RP/Resource Server tests |
| Does the OP have `end_session_endpoint`? | Discovery/contract |
| Is post-logout URI registered? | Exact-match URI |
| Is back-channel supported? | Metadata and OP registration |
| Are sessions consistent across nodes? | Registry/session store tests |
| Is logout distinct from revocation? | Refresh Token/offline access policy |
| Do logs contain credentials? | Redaction, retention |
| Provider contract changes? | Tests/monitoring/migration |

## 30. References

- OpenID Connect Core 1.0, scopes/claims/UserInfo: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- OpenID Connect RP-Initiated Logout: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- OpenID Connect Front-Channel Logout: https://openid.net/specs/openid-connect-frontchannel-1_0.html
- OpenID Connect Back-Channel Logout: https://openid.net/specs/openid-connect-backchannel-1_0.html
- Spring Security — Servlet OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — OAuth2 Login Advanced Configuration: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — Servlet OIDC Logout: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security — Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — Reactive OIDC Logout: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Google — OpenID Connect implementation: https://developers.google.com/identity/openid-connect/openid-connect
- Microsoft — ID Token Claims Reference: https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference
- Keycloak — Server Administration Guide: https://www.keycloak.org/docs/latest/server_admin/
- RFC 6749 — OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700
- RFC 8725 — JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009

## 31. Summary: OIDC Standards Do Not Erase Differences Between Providers

~~~text
Spring Security OIDC Client
  |
  +-- registration corporate: issuer A, scopes A, claims A
  +-- registration partner:   issuer B, scopes B, claims B
  +-- registration workforce: issuer C, scopes C, claims C
  |
  v
Validate ID Token per exact issuer/client first
  |
  v
Provider-specific normalization
  +-- Identity = issuer + subject
  +-- Email/display name = optional
  +-- UserInfo sub MUST match ID Token sub
  +-- Roles = allowlisted trusted issuer/provider mapping
  |
  v
Internal user account + authorization + session
  |
  +-- Local logout: RP session only
  +-- RP-Initiated Logout: OP endpoint if present
  +-- Front/Back-Channel: OP notifies RP if supported
  +-- Token revocation: separate policy
~~~

**Six core principles:**

1. **Requested scopes do not guarantee granted claims or API permissions.** `openid` defines OIDC Login, while `profile`/`email` do not force an OP to return every field for every user.
2. **OIDC identity is tied to issuer + subject.** Never use email, username, or raw `sub` as a global key across providers; use secure account linking and pairwise subject awareness.
3. **UserInfo does not replace the ID Token.** When calling UserInfo, `sub` must match the ID Token `sub` exactly; if they differ, never use the UserInfo claims.
4. **Provider adapters only normalize trusted principals.** Never skip signature/issuer/audience checks or auto-assign `ROLE_ADMIN` from arbitrary claims.
5. **Logout has multiple scopes.** Check `end_session_endpoint`, Front-/Back-Channel support, and session registries; local logout does not automatically revoke tokens.
6. **Multi-provider setups require contract tests and clear trust boundaries.** Each registration has its own scopes, claim schemas, UserInfo rules, resource audiences, and logout capabilities.

Applying these principles helps a Spring Security application support multiple OIDC Providers without confusing user identities, conflating claims with permissions, or promising logout guarantees beyond what a provider actually supports.
