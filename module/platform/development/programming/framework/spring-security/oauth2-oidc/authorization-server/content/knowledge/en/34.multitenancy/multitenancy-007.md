# Customizing UI, Consent, and Claims per Tenant

> **Chapter: Multitenancy.** This lesson belongs to the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module and covers designing, configuring, securing, testing, and operating an OAuth 2.0/OpenID Connect Authorization Server with Spring Security and Spring Authorization Server in Spring Boot. It focuses on delivering a tenant-specific login experience, displaying consent with accurate branding and purpose, and issuing claims that reflect the right tenant context.

## 1. Objective: One Authorization Server, Many Experiences and Policies

An Authorization Server serving multiple tenants may share a runtime and host, while each tenant requires:

- Its own organization name, logo, colors, language, support links, and legal terms.
- A login page reflecting the right tenant and enabled authentication methods.
- A consent screen indicating which application is requesting permissions, what permissions are requested, and what data will be accessed.
- Claims in access tokens, ID Tokens, and UserInfo reflecting the tenant's membership and policies.

Example:

| Attribute | Tenant Acme | Tenant Contoso |
|---|---|---|
| Issuer | **https://auth.example.vn/acme** | **https://auth.example.vn/contoso** |
| Display name | Acme Corporation | Contoso Group |
| Logo | Approved Acme logo | Approved Contoso logo |
| Default locale | vi-VN | en-US |
| Internal scopes | **orders.read**, **orders.write** | **invoices.read**, **reports.export** |
| Tenant claim | **tenant_id=acme** | **tenant_id=contoso** |
| Consent policy | Scoped by Acme client and principal | Scoped by Contoso client and principal |

The UI may differ, yet the protocol contract must still conform to OAuth 2.0/OIDC. One tenant must never receive another tenant's client registrations, consents, user profiles, authorities, or signing keys.

## 2. Separating Three Layers: Presentation, Consent, and Token Claims

| Layer | Primary data | Source of truth | Never use for |
|---|---|---|---|
| Presentation | Name, logo, theme, locale, support URL | Approved tenant configuration | Deciding API access permissions |
| Consent | Client, requested scopes, granted scopes, principal | The right tenant's `RegisteredClient` and `OAuth2AuthorizationConsent` | Granting arbitrary roles or altering the authorization request |
| Token claims | Issuer, subject, tenant ID, scopes, permitted authorities | `AuthorizationServerContext`, local user, and tenant policy | Blindly copying claims from browser or external IdP |

Never treat colors, logos, or tenant display names as security proof. Displaying a scope on the consent page also does not mean that scope has been granted. Only scopes approved by the Authorization Server enter the authorization/token context.

### 2.1. Overall Flow

~~~mermaid
flowchart TD
    A["Request to tenant issuer"] --> B["Resolve registered issuer and tenant"]
    B --> C{"Tenant active?"}
    C -->|No| X["Reject request"]
    C -->|Yes| D["Load tenant presentation and policy"]
    D --> E["Tenant-scoped Login UI"]
    E --> F["Authenticate principal"]
    F --> G["Authorization Endpoint validates client and scopes"]
    G --> H{"Consent required?"}
    H -->|Yes| I["Tenant/client/scope-scoped Consent UI"]
    H -->|No| J["Continue authorization"]
    I --> J
    J --> K["Resolve local identity and tenant authorities"]
    K --> L["Token customizer by token type"]
    L --> M["Issue local access token / ID Token"]
~~~

## 3. Tenant Context Must Be Verified and Preserved Across the Flow

When Spring Authorization Server supports path-based issuers, protocol requests can obtain the current issuer from **AuthorizationServerContextHolder.getContext()**. This is the appropriate source when processing the authorization endpoint, token endpoint, UserInfo, or JWK endpoint.

~~~java
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContext;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;

AuthorizationServerContext context =
        AuthorizationServerContextHolder.getContext();

if (context == null || context.getIssuer() == null) {
    throw new IllegalStateException("Issuer context is unavailable");
}

String issuer = context.getIssuer();
Tenant tenant = tenantRegistry.requireByIssuer(issuer);
~~~

`AuthorizationServerContextHolder` is a request context for protocol processing. Do not assume this context remains automatically present on application routes such as **/login** or **/oauth2/consent** after the browser has been redirected.

### 3.1. Preserving Tenant Context Across Login Redirects

When an authorization request requires login, the browser may be redirected from the issuer path to a shared login page. On the login page request, the application needs to know which tenant the initial authorization transaction belongs to.

Safe design:

1. Upon receiving the authorization request, resolve the issuer using the Authorization Server's multi-issuer mechanism and verify the issuer exists in the tenant registry.
2. Store an interaction context server-side, bound to the browser session and authorization transaction. The context holds tenant ID, issuer, expiration, correlation ID, and state.
3. When rendering the login page, read the saved context and verify session, expiry, and tenant active status.
4. After login, continue only the original transaction. Never accept a new tenant from a query string or hidden form field.
5. Delete the interaction context when the flow finishes, is canceled, or expires.

Do not use a single session variable like **CURRENT_TENANT** if users can open multiple login tabs concurrently; the second tab can overwrite the first tab's tenant. Use a transaction-scoped context with a TTL and handle concurrent flows.

### 3.2. Do Not Take the Tenant from Arbitrary Host or Query Parameters

`Host`, `X-Forwarded-Host`, paths, query parameters, and form fields can be spoofed if not controlled at the trust boundary. If the tenant is resolved from host/path, accept only canonical routes produced by a trusted reverse proxy and check them against the registry. Never use **?tenant=acme** or hidden field **tenant_id=acme** as the basis for choosing a database, policy, or issuer.

## 4. Per-Tenant Presentation Data Model

Create a dedicated presentation configuration managed in the tenant registry or configuration store. Do not stuff themes into access tokens.

~~~java
import java.net.URI;
import java.util.Locale;

record TenantPresentation(
        String tenantId,
        String displayName,
        String logoAssetPath,
        String themeKey,
        Locale defaultLocale,
        URI supportUri,
        URI privacyPolicyUri,
        URI termsUri) {
}
~~~

Example configuration:

~~~yaml
tenants:
  acme:
    display-name: "Acme Corporation"
    logo-asset-path: "/assets/tenants/acme/logo.svg"
    theme-key: "blue"
    default-locale: "vi-VN"
    support-uri: "https://support.example.vn/acme"
    privacy-policy-uri: "https://example.vn/acme/privacy"
    terms-uri: "https://example.vn/acme/terms"
  contoso:
    display-name: "Contoso Group"
    logo-asset-path: "/assets/tenants/contoso/logo.svg"
    theme-key: "slate"
    default-locale: "en-US"
    support-uri: "https://support.example.vn/contoso"
    privacy-policy-uri: "https://example.vn/contoso/privacy"
    terms-uri: "https://example.vn/contoso/terms"
~~~

The theme key should be an allowlisted value such as **blue**, **slate**, **green**; never accept arbitrary CSS from requests or unauthorized tenant admins. Logos should be stored in a controlled asset store/CDN with content-type, size, and origin validation. Support/legal URLs must be validated against scheme and host policies.

### 4.1. Separating Branding from Authorization Policies

The presentation service returns name, logo, colors, locale, and support links. A separate authorization policy service decides tenant active status, user membership, allowed clients, MFA requirements, and granted scopes.

Never allow an admin whose permissions cover only editing logos to modify the scope allowlist, redirect URIs, signing keys, or claim mappings. Use separate permissions for branding, client registration, and security policies.

## 5. Customizing the Login Page

Spring Security supports custom login pages via **formLogin().loginPage(...)**. With Authorization Server, HTML requests requiring login can be forwarded to a login entry point configured in the application's filter chain.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Bean
SecurityFilterChain applicationSecurityFilterChain(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .formLogin(form -> form
                    .loginPage("/login")
                    .permitAll());

    return http.build();
}
~~~

The **/login** controller loads `TenantPresentation` from the verified interaction context and places validated values into the model:

~~~java
record LoginPageModel(
        String tenantName,
        String logoPath,
        String themeKey,
        String supportUrl,
        String localeTag) {
}
~~~

The view uses `tenantName`, `logoPath`, and `themeKey` to render. `themeKey` maps only to predefined CSS classes; never inject raw CSS into `style` attributes. If a tenant supports multiple login methods, display the exact providers/password/MFA options configured for that tenant.

### 5.1. Principles for Login UI

- Do not disclose which users/emails exist in a tenant via differing error messages.
- Never echo usernames, passwords, OTPs, or tokens into HTML.
- Enforce CSRF protection on login forms; use `POST` and appropriate cookie/session policies.
- Apply CSP, output encoding, and escaping to all tenant-provided text.
- Never allow `returnUrl` or `continue` redirects to arbitrary hosts.
- Never load scripts/CSS from arbitrary tenant-declared URLs.
- When a tenant is deactivated, block new logins and authorizations per policy.

## 6. Customizing the Consent Page in Spring Authorization Server

Spring Authorization Server lets you specify a custom consent URI via **authorizationEndpoint(...).consentPage(...)**.

~~~java
OAuth2AuthorizationServerConfigurer authorizationServer =
        OAuth2AuthorizationServerConfigurer.authorizationServer();

http.with(authorizationServer, server ->
        server.authorizationEndpoint(endpoint ->
                endpoint.consentPage("/oauth2/consent")));
~~~

When consent is required, the Authorization Endpoint redirects the resource owner to the configured URI. According to the Spring Authorization Server 1.5.8 API documentation, the custom consent page query string contains:

| Parameter | Meaning |
|---|---|
| `client_id` | Client identifier of the request |
| `scope` | Requested scopes, space-delimited |
| `state` | Token protecting the consent transaction/CSRF |

`state` on the consent page is the consent-step state generated by the Authorization Server; do not confuse it with the original `state` sent by the OAuth client in the Authorization Request.

### 6.1. Considerations with Path-Based Multi-Issuer

The `consentPage` value in the configurer is a static URI configuration. The documented default redirect carries only `client_id`, `scope`, and `state`; it does not promise to append a tenant slug to the query. Therefore, with issuers like **https://auth.example.vn/acme** and **https://auth.example.vn/contoso**, never infer the tenant solely from `client_id` or a browser-supplied parameter.

If using a shared consent page:

1. Bind the verified tenant to the authorization interaction server-side before redirecting to the custom consent route.
2. When rendering consent, verify the interaction context is valid, belongs to the current browser session/principal, and matches the consent transaction's `state`.
3. Resolve the tenant from the saved context and tenant registry.
4. Build the form action targeting the right issuer's authorization endpoint, combining the canonical issuer with **AuthorizationServerSettings.getAuthorizationEndpoint()**.
5. On `POST`, let the Authorization Server re-validate `state`, client, principal, and requested scopes.

You can use a server-side interaction store or a controlled routing strategy. Never treat a tenant query parameter or hidden input as proof. If you lack a safe mechanism to preserve transaction tenant binding, use the default consent page on the protocol path or complete the tenant-aware consent handoff before enabling a custom page.

### 6.2. The Consent Form Must POST to the Right Authorization Endpoint

A consent form must send an HTTP `POST` to the current tenant's authorization endpoint. The form must preserve `client_id`, `state`, and the user-selected scopes. Illustrative Thymeleaf example:

~~~html
<form method="post" th:action="${authorizationEndpoint}">
    <input type="hidden" name="client_id" th:value="${clientId}">
    <input type="hidden" name="state" th:value="${state}">

    <label th:each="scope : ${requestedScopes}">
        <input type="checkbox"
               name="scope"
               th:value="${scope.name}"
               th:checked="${scope.previouslyGranted}">
        <span th:text="${scope.displayName}"></span>
        <small th:text="${scope.description}"></small>
    </label>

    <button type="submit">Approve selected permissions</button>
</form>
~~~

This is an illustrative template; `authorizationEndpoint` must be constructed from the verified issuer/tenant interaction. The controller must never read the `POST` URL directly from a query parameter. Verify the converters and form fields of the Spring Authorization Server version in use via integration tests; never drop `state` or replace `POST` with `GET`.

## 7. Presenting Clients and Scopes Clearly

The consent page must tell users **who is requesting permission** and **what that permission allows**.

Client details should be retrieved from `RegisteredClient` in the current tenant's repository:

- `clientName`: registered application name.
- `clientId`: used for reference, not necessarily displayed in full.
- Scopes registered by the client and scopes actually being requested.
- Redirect URI/domain may be shown as verified origin information if required by UX/policy.

Additional client presentation metadata can be stored in a separate repository keyed by `(tenant_id, client_id)`, including approved icon, publisher, description, privacy URL, and support URL. Never trust `client_name`, logo URLs, or privacy URLs passed in the query string.

### 7.1. Per-Tenant Scope Catalog

A scope code may have different descriptions per tenant or product. Use an approved catalog:

~~~java
record ScopePresentation(
        String scope,
        String displayName,
        String description,
        String dataCategory,
        String riskLevel,
        String purpose) {
}
~~~

Example:

| Scope | Display name | Description |
|---|---|---|
| `orders.read` | View orders | Allows the application to view orders belonging to the tenant |
| `orders.write` | Manage orders | Allows creating or updating orders |
| `invoices.read` | View invoices | Allows the application to read authorized invoices |
| `reports.export` | Export reports | Allows generating report exports per policy |

Never infer permissions from a scope's name. The scope catalog must align with actually registered scopes and Resource Server policies.

### 7.2. Requested, Previously Granted, and Newly Requested

The Consent UI should distinguish:

- **Requested scopes:** scopes in the current authorization request.
- **Previously granted scopes:** scopes the user already granted to this client in this tenant.
- **Newly requested scopes:** new scopes that the user needs to review.
- **Selected scopes:** the subset the user chooses to grant this time.

`OAuth2AuthorizationConsentService.findById(registeredClientId, principalName)` can be used to retrieve existing consent. In multitenancy, the service must delegate by issuer/tenant; never query a shared consent store without a tenant discriminator.

Never mark a scope as approved simply because the client previously requested it. Only persisted consent records determine previously granted scopes.

## 8. Persisting Consent by Tenant and Principal

`OAuth2AuthorizationConsent` represents the authorities a resource owner has granted to a `RegisteredClient`. Core fields include:

| Field | Meaning |
|---|---|
| `registeredClientId` | Internal ID of the `RegisteredClient` |
| `principalName` | Principal/resource owner name |
| `authorities` | Approved scopes or authorities |

In a multi-issuer architecture, the consent store must be isolated by tenant. If two tenants share the same `client_id` or principal name, Tenant A's consent must never cause Tenant B to skip consent.

Principles:

- Use a tenant-aware `OAuth2AuthorizationConsentService`.
- Unique keys in shared tables must include the tenant discriminator.
- When reading consent, verify the client belongs to the current tenant.
- When writing consent, save only the scope subset the user actually selected.
- When client scopes shrink or tenant policies change, have a procedure to handle stale consents.
- Require re-consent when sensitive scopes expand or policies change.

## 9. Per-Tenant Claims in Access Tokens and ID Tokens

Spring Authorization Server supports customizing JWT claims via `OAuth2TokenCustomizer<JwtEncodingContext>`. The context provides token type, principal, `RegisteredClient`, authorized scopes, and `AuthorizationServerContext`. Thus the customizer can read the current issuer/tenant from the context and invoke the tenant policy service.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.core.oidc.endpoint.OidcParameterNames;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;

@Bean
OAuth2TokenCustomizer<JwtEncodingContext> tenantClaimsCustomizer(
        TenantRegistry tenantRegistry,
        TenantClaimsService tenantClaimsService) {

    return context -> {
        String issuer = context.getAuthorizationServerContext().getIssuer();
        Tenant tenant = tenantRegistry.requireByIssuer(issuer);

        if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
            TenantAuthorities authorities =
                    tenantClaimsService.authoritiesFor(
                            tenant.id(), context.getPrincipal());

            context.getClaims().claim("tenant_id", tenant.id());
            context.getClaims().claim("tenant_roles", authorities.roles());
        }

        if (OidcParameterNames.ID_TOKEN.equals(
                context.getTokenType().getValue())) {
            LocalProfile profile =
                    tenantClaimsService.profileFor(
                            tenant.id(), context.getPrincipal());

            context.getClaims().claim("tenant_id", tenant.id());

            if (context.getAuthorizedScopes().contains(OidcScopes.PROFILE)) {
                context.getClaims().claim("name", profile.displayName());
            }

            if (context.getAuthorizedScopes().contains(OidcScopes.EMAIL)
                    && profile.emailVerified()) {
                context.getClaims().claim("email", profile.email());
                context.getClaims().claim("email_verified", true);
            }
        }
    };
}
~~~

`TenantRegistry`, `TenantClaimsService`, `TenantAuthorities`, and `LocalProfile` are application-defined domain types. The customizer uses only the issuer in `JwtEncodingContext` and verified local membership; never read tenant IDs from request parameters or unverified principal attributes.

### 9.1. Access Tokens and ID Tokens Have Different Purposes

| Claim/data | Access token | ID Token |
|---|---|---|
| `tenant_id` | When the Resource Server needs tenant context | When the RP needs to know which tenant the user is in |
| Tenant roles/permissions | Only when the API needs authorization claims | Usually unnecessary |
| `name`, `email` | Avoid if the API does not need them | Per OIDC scopes and consent |
| Logo, theme, support URL | Should not be included | Should not be included |
| Issuer, subject, audience, expiry | Issued by AS per token contract | Issued by OP per OIDC contract |

Do not put the entire tenant profile or PII into every token. A JWT is a bearer credential; tokens can end up in browsers, logs, or client telemetry. Issue only the claims required by the respective consumer.

### 9.2. Do Not Overwrite Standard Claims

A tenant customizer must not overwrite claims owned by the Authorization Server such as `iss`, `sub`, `aud`, `iat`, `exp`, `nonce`, `azp`, `auth_time`, `at_hash`, or `c_hash`. The local subject must be stable per issuer and local identity policy.

If multiple custom claim needs exist, consolidate the logic into a single `OAuth2TokenCustomizer<JwtEncodingContext>` that dispatches by token type and service; avoid declaring multiple beans of the same generic type, which can conflict or have unclear ordering.

## 10. Customizing UserInfo per Tenant

The OIDC UserInfo endpoint is a protected resource requiring a Bearer access token. Spring Authorization Server lets you configure `userInfoMapper` to build `OidcUserInfo` based on authorization, tenant, and scopes.

Skeleton example:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;

import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.core.oidc.OidcUserInfo;
import org.springframework.security.oauth2.server.authorization.context.AuthorizationServerContextHolder;
import org.springframework.security.oauth2.server.authorization.oidc.authentication.OidcUserInfoAuthenticationContext;

Function<OidcUserInfoAuthenticationContext, OidcUserInfo> userInfoMapper =
        context -> {
            String issuer = AuthorizationServerContextHolder.getContext().getIssuer();
            Tenant tenant = tenantRegistry.requireByIssuer(issuer);

            Set<String> scopes = context.getAuthorization().getAuthorizedScopes();
            LocalProfile profile = profileService.load(
                    tenant.id(), context.getAuthorization().getPrincipalName());

            Map<String, Object> claims = new HashMap<>();
            claims.put("sub", profile.subject());

            if (scopes.contains(OidcScopes.PROFILE)) {
                claims.put("name", profile.displayName());
            }

            if (scopes.contains(OidcScopes.EMAIL) && profile.emailVerified()) {
                claims.put("email", profile.email());
                claims.put("email_verified", true);
            }

            return new OidcUserInfo(claims);
        };
~~~

Register the mapper in the Authorization Server's OIDC configurer:

~~~java
authorizationServer.oidc(oidc ->
        oidc.userInfoEndpoint(userInfo ->
                userInfo.userInfoMapper(userInfoMapper)));
~~~

This is a skeleton; applications must handle nulls and tenant/profile errors per policy. The UserInfo mapper must determine the tenant from the verified request context, fetch the profile in the right tenant, and return only claims allowed by scopes and policy. `sub` in UserInfo must match the ID Token's `sub` for the same user/issuer.

Additional per-tenant claims may be added if clients have valid use cases, provided contracts and consent are clearly defined. Never return internal roles, support metadata, or PII simply because they exist in the database.

## 11. Organizing Configuration by Tenant

A service structure can be separated into:

| Component | Responsibility |
|---|---|
| `TenantRegistry` | Looks up tenants by canonical issuer and status |
| `TenantPresentationService` | Name, logo, theme, locale, legal/support links |
| `TenantInteractionContextStore` | Preserves verified tenant across login/consent redirects |
| `TenantClientPresentationService` | Display metadata for clients within a tenant |
| `TenantScopeCatalog` | Scope descriptions and sensitivity classification |
| `TenantConsentPolicy` | Required consent decisions, re-consent, and policy |
| `TenantClaimsService` | Local profile, membership, authorities, and claim allowlist |
| `TenantAwareAuthorizationConsentService` | Saves/reads consent per tenant |
| `TenantAwareTokenCustomizer` | Adds claims by token type and issuer |

Never let a mutable singleton swap `currentTenant` per request. Each service receives a verified tenant ID as a parameter or reads from a properly lifecycle-scoped request context.

### 11.1. Static and Dynamic Configuration

With few tenants, presentation/scope catalogs can be loaded at startup. For dynamically onboarded tenants, an authenticated workflow is needed:

1. An authenticated admin/control plane creates the tenant configuration.
2. Validate theme key, logo asset, locale, and external URLs.
3. Validate that the scope catalog contains only policy-approved scopes.
4. Provision presentation, consent policy, and claim mappings.
5. Publish a configuration version.
6. Activate only when the issuer and core multi-tenant components are ready.
7. Audit changes and maintain rollback/version history.

Changing branding should not require rotating signing keys. Changing authorization policies or claim mappings requires separate review and testing.

## 12. Securing UI and Claims

### 12.1. Presentation Security

- Escape all tenant/client content in templates.
- Use CSS theme keys strictly from an allowlist.
- Never render arbitrary HTML from tenant configuration.
- Validate logo URLs/assets and restrict host, content type, and size.
- Enable CSP, frame protection, secure cookies, HSTS, and TLS per deployment.
- Never expose sensitive information in query strings.
- Never pass client secrets, tokens, or raw authorization requests into models/views.

### 12.2. Consent Security

- Render only clients looked up in the current tenant's `RegisteredClientRepository`.
- Treat `client_id`, `scope`, and `state` from query params as untrusted input requiring validation, not authorized data.
- Preserve `state`, use HTTP `POST`, and submit to the right tenant's authorization endpoint.
- Accept only a scope subset within requested scopes and the `RegisteredClient` allowlist.
- Never let the form submit arbitrary scopes to escalate permissions.
- Denials/rejections must go through Spring Authorization Server's consent protocol; never issue authorization codes manually.
- Never use `redirect_uri` from the consent form as the form action.

### 12.3. Claims Security

- Claims come from the local user store and verified tenant membership.
- Scopes/consent govern which profile claims are emitted.
- Resource Servers must still validate issuer, audience, signature, expiration, and authorities.
- Never trust `tenant_id` inside a token before token validation succeeds.
- Never allow clients to send a tenant claim to overwrite token values.
- Never emit PII/roles beyond the consumer's intended purpose.

## 13. Test Matrix for UI, Consent, and Claims

| # | Scenario | Expected outcome |
|---|---|---|
| 1 | Open Acme login | Acme logo, name, theme, and locale |
| 2 | Open Contoso login | No Acme branding appears |
| 3 | Inactive tenant | New logins/authorizations rejected |
| 4 | Unknown tenant theme key | Falls back to safe theme or rejects config |
| 5 | Logo URL outside allowlist | Asset not loaded |
| 6 | Tenant name contains HTML/script | Rendered escaped; no XSS |
| 7 | Two login tabs for two tenants | Interaction contexts do not overwrite each other |
| 8 | Login page request with no transaction | Never infers tenant from arbitrary query/`Host` |
| 9 | Consent for Acme client | Displays Acme client metadata |
| 10 | Same client ID exists in two tenants | Each consent displays metadata for the right tenant |
| 11 | Non-existent client ID | Rejected; never renders query-declared client |
| 12 | Requested scope in allowlist | Displays accurate scope description |
| 13 | Scope disallowed by `RegisteredClient` | Authorization request rejected |
| 14 | New sensitive scope | Displays risk/purpose and prompts for consent |
| 15 | Previously granted scope | Clearly displayed as previously granted |
| 16 | User selects a subset of scopes | Only the approved subset is saved |
| 17 | User denies consent | No authorization code issued |
| 18 | Consent form sent via `GET` | Rejected; only `POST` accepted |
| 19 | Tampered consent `state` | Authorization endpoint rejects |
| 20 | Consent form posted to another tenant's issuer | Authorization not granted |
| 21 | Consent page missing tenant interaction | Fails closed, no fallback |
| 22 | Acme consent store queried from Contoso | No cross-tenant consent returned |
| 23 | Acme access token | `tenant_id` and authorities belong to Acme |
| 24 | Contoso access token | Contains no Acme authorities |
| 25 | ID Token with `profile` scope | Contains only permitted profile claims |
| 26 | ID Token without `email` scope | Does not return email claims |
| 27 | Unverified email | Does not set `email_verified=true` |
| 28 | Customizer receives refresh token | Does not add claims intended only for JWT access/ID tokens |
| 29 | ID Token customizer | Does not overwrite `iss`/`sub`/`aud`/`exp`/`nonce` |
| 30 | UserInfo with Acme access token | Acme profile and `sub` |
| 31 | UserInfo with Contoso token | Does not read Acme profile |
| 32 | UserInfo `sub` differs from ID Token `sub` | RP test detects and rejects |
| 33 | Tenant role revoked | New tokens omit role; old tokens follow revocation/expiry policy |
| 34 | Branding updated with multiple pods running | All pods serve the same presentation version |
| 35 | Missing or broken claims config | Never emits broad default permission claims |

### 13.1. End-to-End Integration Tests to Run

A complete test flow should:

1. Send an authorization request to Acme's issuer with a valid client and scopes.
2. Verify the login page uses Acme's presentation.
3. Authenticate an Acme user.
4. Verify the consent page displays Acme's client, requested scopes, and descriptions.
5. Approve a subset of scopes and `POST` to Acme's authorization endpoint.
6. Exchange the authorization code at Acme's token endpoint.
7. Decode and validate local access token/ID Token: issuer, audience, subject, scopes, and tenant claims.
8. Call UserInfo with the access token and verify the profile belongs to Acme.
9. Repeat with Contoso and verify no client, consent, theme, or claim leaks across tenants.

## 14. Troubleshooting, Production Checklist, and Self-Assessment Questions

| Symptom | Possible cause | Resolution |
|---|---|---|
| Login page always uses default theme | Tenant interaction not preserved across redirects | Add server-side interaction context |
| Login page shows wrong tenant with multiple tabs | Single `currentTenant` session attribute used | Use transaction-scoped context |
| Consent page does not know the issuer | Static custom consent URI, query lacks tenant | Bind tenant server-side and validate `state` |
| Consent form posts back to root issuer | Form action uses default endpoint without tenant path | Build action from verified canonical issuer |
| Wrong client name on consent page | Looked up from query or global client registry | Look up `RegisteredClient` by tenant |
| Wrong previously granted scopes | Consent service is not tenant-aware | Delegate store by issuer |
| User selects scope yet token lacks it | Scope restricted by policy/consent | Inspect granted scopes and token context |
| Token contains another tenant's role | Claims service lacks tenant ID or cache lacks tenant | Use tenant-aware lookup/cache keys |
| ID Token contains email even though unrequested | Customizer ignores authorized scopes | Gate claims by scopes and policy |
| UserInfo returns wrong tenant's profile | Mapper uses global `principalName` | Resolve tenant and local identity in the same context |
| Customizer overwrites standard claim | Copies claim map without filtering | Use allowlists and preserve reserved claims |
| Tenant theme updates out of sync | Cache lacks versioning/invalidation | Versioned config and cache invalidation |

### 14.1. Production Checklist

- [ ] Presentation, consent policy, and claims policy are separate components.
- [ ] Tenant is resolved from a verified issuer/transaction context.
- [ ] Login and consent UIs preserve tenant context per transaction, supporting multiple tabs.
- [ ] Never take tenant from query params, hidden inputs, or untrusted forwarded headers.
- [ ] Branding config uses an allowlist for themes/assets/URLs and output escaping.
- [ ] Consent page looks up `RegisteredClient` from the current tenant's repository.
- [ ] Consent clearly displays requested, previously granted, and newly requested scopes.
- [ ] Consent form uses `POST`, preserves `state`, and submits to the right issuer's authorization endpoint.
- [ ] Consent store is tenant-aware.
- [ ] Token customizer verifies token type, issuer, principal, authorized scopes, and tenant membership.
- [ ] Access tokens and ID Tokens carry only claims needed by consumers.
- [ ] Standard Authorization Server claims are never overwritten.
- [ ] UserInfo returns only claims permitted by scopes/consent/policy for the right tenant.
- [ ] Cache keys include tenant ID/issuer and support versioning/invalidation.
- [ ] Negative tests cover cross-tenant UI, consent, claims, and UserInfo access.
- [ ] Audits track changes to branding, scope catalogs, consent policies, and claim mappings.
- [ ] Logs/traces contain no tokens, raw `state`, or unnecessary PII.

**Self-assessment questions**

1. Why must presentation, consent, and token claims be three separate layers?
2. When processing a protocol request, where do you retrieve the current issuer?
3. Why is `AuthorizationServerContextHolder` not automatically available on a custom login page?
4. How do you preserve tenant context when a user opens multiple authorization tabs?
5. Why should you not use a `tenant_id` query parameter as the basis for selecting a tenant?
6. Which query parameters does Spring Authorization Server's `consentPage(...)` receive?
7. Is `state` on the consent page the same `state` originally sent by the OAuth client?
8. Which endpoint must the consent form `POST` to, and which fields must it preserve?
9. How do you safely retrieve the client name for the consent page?
10. What is the difference between requested scopes and previously granted scopes?
11. Why must the consent store be tenant-aware when client IDs can overlap across tenants?
12. Where can `OAuth2TokenCustomizer<JwtEncodingContext>` obtain the tenant context?
13. Why should access tokens and ID Tokens not contain the exact same set of claims?
14. When should `tenant_id` be included in an access token?
15. Why should you not copy all upstream/local claims into a JWT?
16. How must the UserInfo mapper validate tenant, scopes, and subject?
17. How do you detect theme, consent, or profile leakage between two tenants?

## References

- [Spring Authorization Server 1.5.8 — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization endpoint configurer, consent page, and extension points.
- [Spring Authorization Server 1.5.8 — OAuth2AuthorizationEndpointConfigurer API](https://docs.spring.io/spring-authorization-server/reference/api/java/org/springframework/security/oauth2/server/authorization/config/annotation/web/configurers/OAuth2AuthorizationEndpointConfigurer.html): `consentPage(String)` and form contract.
- [Spring Authorization Server 1.5.8 — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): `RegisteredClient`, `clientName`, `OAuth2AuthorizationConsent`, and `OAuth2TokenContext`.
- [Spring Authorization Server 1.5.8 — How-to: Implement Multitenancy](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-multitenancy.html): issuer context and tenant-aware component registry.
- [Spring Authorization Server 1.5.8 — How-to: Customize the OpenID Connect 1.0 UserInfo response](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-userinfo.html): ID Token customizer and UserInfo mapper.
- [Spring Authorization Server 1.5.8 — How-to: Add authorities as custom claims in JWT access tokens](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-custom-claims-authorities.html): access token claim customization and token type check.
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html): custom login page and form authentication.
- [Spring Security — Cross Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): CSRF protection for browser-based forms.
