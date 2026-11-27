# 6.3. Linking a Registration to a Provider with Provider ID

> **Module:** Spring Security OAuth 2.0 OIDC Client  
> **Chapter:** 6. Provider Configuration  
> **Focus:** Using the `spring.security.oauth2.client.registration.<registrationId>.provider` property to connect each OAuth 2.0 Client registration with the appropriate OpenID Provider/Authorization Server configuration.

When a Spring Boot application implements OpenID Connect (OIDC) login or calls APIs as an OAuth 2.0 Client, configuration is usually split into two groups: **registration** describes the Client represented by the application, while **provider** describes the authorization/authentication provider with which the Client communicates.

These two groups can have the same name, though it is not required. The `provider` property under each registration is the **linking key** between them. Understanding this key properly helps configure multiple Clients, reuse a provider, choose meaningful business names, and avoid mixing up issuers, token endpoints, or parameters across different systems.

This lesson uses the common configuration syntax of Spring Boot 3.x and Spring Security 6.x in Servlet/MVC applications. For other versions, consult the corresponding documentation for exact property names and auto-configuration behavior.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain how **registration ID** and **provider ID** differ in function.
2. Declare a registration with an arbitrary name and link it to a provider via `registration.<id>.provider`.
3. Use `provider.<providerId>.issuer-uri` to configure OIDC discovery or declare endpoints manually when needed.
4. Set up multiple registrations sharing a single provider while keeping client ID, client secret, scopes, and redirect URI separate.
5. Distinguish provider configurations defined in YAML from well-known providers for which Spring Security provides default settings.
6. Recognize the impact of `registrationId` on the login initiation URL, callback, and looking up authorized clients.
7. Diagnose errors caused by wrong aliases, missing provider properties, mismatched issuer URIs, or mixed-up configurations across tenants.

## 2. The Big Picture: How Do Registration and Provider Connect?

In Spring Boot configuration, two property branches are directly related:

~~~text
spring.security.oauth2.client
├── registration
│   └── <registrationId>
│       ├── provider: <providerId>    <-- linking key
│       ├── client-id: ...
│       ├── client-secret: ...
│       ├── authorization-grant-type: authorization_code
│       ├── redirect-uri: ...
│       └── scope: ...
└── provider
    └── <providerId>
        ├── issuer-uri: ...            # commonly used for OIDC
        ├── authorization-uri: ...     # can be declared explicitly
        ├── token-uri: ...
        ├── jwk-set-uri: ...
        ├── user-info-uri: ...
        └── user-name-attribute: ...
~~~

For example, if a registration has ID `web` and the provider has ID `company-idp`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          web:
            provider: company-idp
            client-id: web-client
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          company-idp:
            issuer-uri: https://identity.example.test/realms/training
~~~

The line `provider: company-idp` means: **registration `web` uses the provider configuration keyed `company-idp`**. It does not mean the Client is named `company-idp`, nor does it require the login path to contain the string `company-idp`.

With this configuration:

- **Registration ID:** `web`.
- **Provider ID:** `company-idp`.
- **Client ID registered at the OP:** `web-client`.
- **Issuer URI:** `https://identity.example.test/realms/training`.
- **Default login initiation URL:** `/oauth2/authorization/web`.
- **Default callback URL:** `/login/oauth2/code/web`.

The three names `web`, `company-idp`, and `web-client` are three distinct identifiers serving three distinct purposes.

### 2.1. Mapping Diagram

~~~mermaid
flowchart LR
    subgraph REG["Client registrations in the application"]
        W["registration.web<br/>client-id: web-client<br/>provider: company-idp"]
        A["registration.admin<br/>client-id: admin-client<br/>provider: company-idp"]
    end
    subgraph PROV["Provider configuration in the application"]
        P["provider.company-idp<br/>issuer-uri: https://identity.example.test/realms/training"]
    end
    OP["Actual OpenID Provider"]
    W -->|"provider ID"| P
    A -->|"same provider ID"| P
    P -->|"discovery/authorization/token"| OP
~~~

Each **registration** represents one Client configuration. One **provider configuration** can be referenced by multiple registrations if they genuinely share the same provider and the same corresponding protocol parameters.

### 2.2. Commonly Confused Names

| Name | Where it lives | Purpose | Example |
|---|---|---|---|
| `registrationId` | Key under `registration` | Identifies a Client registration in Spring Security; used to select login and authorized clients | `web` |
| `providerId` | Value of `registration.web.provider` and key under `provider` | Selects the provider configuration block to link with the registration | `company-idp` |
| `client-id` | `registration.web.client-id` | Client identifier registered by the Authorization Server/OP | `web-client` |
| `issuer-uri` | `provider.company-idp.issuer-uri` | Issuer identifier of the OP; supports discovery and issuer verification | `https://identity.example.test/realms/training` |
| `redirect-uri` | `registration.web.redirect-uri` | Callback where the Client receives the authorization response | `{baseUrl}/login/oauth2/code/{registrationId}` |
| `scope` | `registration.web.scope` | Scope of permissions/claims requested by the registration | `openid`, `profile` |

**Provider ID is a configuration alias chosen by the application**, not proof of identity, not an issuer URI, not an OAuth scope, and not a hostname required to match the provider.

## 3. Why Separate Registration and Provider?

If there is only one Client and one OP, you could give both groups the same ID and barely notice the distinction. As a project grows, the two groups describe things that change at different cadences.

**Registration properties** usually depend on each application or access purpose:

- Client ID and Client secret issued by the OP for a specific registration.
- Grant type, e.g., `authorization_code` or `client_credentials` by design.
- Callback URI for the login application.
- Scopes to request, which may differ between a web UI and an operations tool.
- Client authentication method and per-Client options.

**Provider properties** describe where the Client executes the protocol:

- Authorization endpoint receiving browser-based authorization requests.
- Token endpoint exchanging authorization codes or executing the appropriate grant.
- JWK Set URI for verifying JWT/ID token signatures when applicable.
- UserInfo endpoint and user identity attribute name for OAuth2/OIDC users.
- Issuer URI identifying the OP and enabling metadata download when discovery is supported.

If two registrations use the same OP, they can share the same issuer and endpoints while still needing different **client IDs/secrets/scopes/redirects**. If two OPs have different issuers, they should not reference the same provider config merely because they run on the same domain or the same software.

### 3.1. Rule of Thumb for Choosing the Property Group

Ask yourself:

- "Does this value change when I create another Client on the **same OP**?" If yes, it usually belongs to **registration**.
- "Does this value describe the OP/Authorization Server that multiple Clients contact?" If yes, it usually belongs to **provider**.
- "Is this value how Spring Security names configuration inside the application?" That is **registrationId** or **providerId**; it does not have to appear literally on the IdP side.

Keeping this separation clear reduces duplicated endpoints and makes configuration changes safer.

## 4. Exact Linking Syntax in `application.yml`

Consider configuring a Client named `sales-portal` using an internal OP aliased as `corporate-oidc`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          sales-portal:
            provider: corporate-oidc
            client-id: sales-web
            client-secret: ${SALES_OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corporate-oidc:
            issuer-uri: https://login.example.test/realms/employees
~~~

Read the configuration in order:

1. `registration.sales-portal` states that the application has a Client registration named `sales-portal`.
2. Inside the registration, `provider: corporate-oidc` selects the provider configuration with ID `corporate-oidc`.
3. `provider.corporate-oidc.issuer-uri` states that the corresponding OP has issuer `https://login.example.test/realms/employees`.
4. `client-id` and `client-secret` identify the specific Client registered with that OP.
5. `scope` contains `openid`, so this registration requests OIDC when using Authorization Code login.
6. `redirect-uri` contains the `{registrationId}` placeholder, so the callback for this registration ends with `/sales-portal` by default.

The link is **the exact string match between `provider: corporate-oidc` and the key `provider.corporate-oidc`**. You can rename this alias to `central-identity` if you change **both places**, as long as the issuer and other settings remain accurate.

### 4.1. Does the Provider ID Have to Match the Issuer or Product Name?

No. For example, all three values below can be different:

~~~yaml
registration:
  user-login:
    provider: main-sso
    client-id: training-frontend
provider:
  main-sso:
    issuer-uri: https://idp.example.test/realms/company
~~~

- `user-login` is the registration key in the application.
- `main-sso` is the provider config key in the application.
- `https://idp.example.test/realms/company` is the issuer published by the OP.

Use meaningful and consistent names; do not ascribe protocol semantics to the string `main-sso`. It is the **issuer URI**, endpoints, and OIDC verification rules that establish the actual trust relationship.

### 4.2. Using `application.properties` Instead of YAML

The same configuration can be expressed in properties:

~~~properties
spring.security.oauth2.client.registration.sales-portal.provider=corporate-oidc
spring.security.oauth2.client.registration.sales-portal.client-id=sales-web
spring.security.oauth2.client.registration.sales-portal.client-secret=${SALES_OIDC_CLIENT_SECRET}
spring.security.oauth2.client.registration.sales-portal.authorization-grant-type=authorization_code
spring.security.oauth2.client.registration.sales-portal.redirect-uri={baseUrl}/login/oauth2/code/{registrationId}
spring.security.oauth2.client.registration.sales-portal.scope=openid,profile,email
spring.security.oauth2.client.provider.corporate-oidc.issuer-uri=https://login.example.test/realms/employees
~~~

In both formats, the logical structure is identical. Pay special attention to the difference between `client.registration.*.provider` and `client.provider.*`: missing a level can cause binding errors or prevent the registration from finding the intended configuration.

## 5. When Registration ID Matches Provider ID

In a small application, you might see declarations like:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          internal:
            client-id: internal-web
            client-secret: ${INTERNAL_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile]
        provider:
          internal:
            issuer-uri: https://id.example.test/realms/internal
~~~

When a registration named `internal` has a provider configuration that also has ID `internal`, Spring Boot can link the provider settings by matching-name convention. This keeps configuration concise for a single Client.

Nevertheless, **setting `provider: internal` explicitly is clearer for teaching and system maintenance**:

~~~yaml
registration:
  internal:
    provider: internal
    client-id: internal-web
    client-secret: ${INTERNAL_CLIENT_SECRET}
    authorization-grant-type: authorization_code
    scope: [openid, profile]
provider:
  internal:
    issuer-uri: https://id.example.test/realms/internal
~~~

Both groups have the same ID in this example, yet they remain **two independent configuration roles**. Do not infer that any declared provider ID automatically creates a Client registration; the application only has a registration when declared or provided through the corresponding repository.

## 6. Setting Registration ID Different from Provider ID: Explicit Alias

This case highlights the role of the `provider` property:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          backoffice-login:
            provider: keycloak-main
            client-id: backoffice-web
            client-secret: ${BACKOFFICE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          keycloak-main:
            issuer-uri: https://sso.example.test/realms/staff
~~~

Login for this Client starts at:

~~~http
GET /oauth2/authorization/backoffice-login HTTP/1.1
Host: localhost:8080
~~~

The callback typically returns to:

~~~text
http://localhost:8080/login/oauth2/code/backoffice-login
~~~

The value `keycloak-main` is **not** a registrationId, so:

- Do not assume the login initiation path is `/oauth2/authorization/keycloak-main`.
- Do not assume the callback is `/login/oauth2/code/keycloak-main`.
- Do not write code looking up the registration with `findByRegistrationId("keycloak-main")` when the actual registration has ID `backoffice-login`.

If the application has a custom login page, the link must use `registrationId`:

~~~html
<a href="/oauth2/authorization/backoffice-login">
  Sign in to internal area
</a>
~~~

You can rename the provider alias without changing the login link in the UI, as long as `registrationId` stays the same and the configuration mapping is updated. Changing **`registrationId`**, however, can affect login URLs, callbacks registered at the OP, source code referencing the registration, and stored authorized client records.

## 7. One Provider Used by Multiple Registrations

A company may create two Clients at the same OP: `customer-portal` for the customer web app and `support-console` for the support application. Both talk to the same issuer but have different client IDs, secrets, scopes, and callbacks.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          customer-portal:
            provider: shared-sso
            client-id: customer-portal-web
            client-secret: ${CUSTOMER_PORTAL_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]

          support-console:
            provider: shared-sso
            client-id: support-console-web
            client-secret: ${SUPPORT_CONSOLE_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, support.read]

        provider:
          shared-sso:
            issuer-uri: https://identity.example.test/realms/company
~~~

Now the two registrations use the same provider configuration, but different Client data:

| Property | `customer-portal` | `support-console` |
|---|---|---|
| `provider` | `shared-sso` | `shared-sso` |
| `client-id` | `customer-portal-web` | `support-console-web` |
| Secret variable | `CUSTOMER_PORTAL_SECRET` | `SUPPORT_CONSOLE_SECRET` |
| Scope | `openid profile email` | `openid profile support.read` |
| Login URL | `/oauth2/authorization/customer-portal` | `/oauth2/authorization/support-console` |
| Callback URL | `/login/oauth2/code/customer-portal` | `/login/oauth2/code/support-console` |
| Issuer | Same | Same |

**To work properly**, each Client must be registered properly at the OP with its respective redirect URIs, scopes, and policies. Having two configurations point to the same provider ID does not cause the OP to automatically create another Client.

### 7.1. Why Is This Design Useful?

- Changing the issuer or shared endpoint settings only requires editing one provider configuration.
- The application can pick the registration based on login/authorization needs.
- Client credentials are not mixed together, even though the OAuth 2.0/OP endpoints are the same.
- When one registration needs additional API permissions, you change the scope on that registration without granting extra permissions to the other.
- Authorized client records in Spring Security are tied to the registration ID and principal, keeping permissions/tokens separate per Client.

**Note:** the scope `support.read` in the example is a hypothetical value. This scope only has effect when the OP is configured to support it and the actual API understands/enforces that permission. A scope does not implicitly make a user a support agent.

### 7.2. When Must You Not Reuse the Same Provider?

Do not use `shared-sso` for two systems just because both run Keycloak or share a hostname. If they belong to **two realms/tenants with different issuers**, define separate provider configs:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          employees:
            provider: employees-oidc
            client-id: employees-web
            client-secret: ${EMPLOYEES_SECRET}
            scope: [openid, profile]

          partners:
            provider: partners-oidc
            client-id: partners-web
            client-secret: ${PARTNERS_SECRET}
            scope: [openid, profile]

        provider:
          employees-oidc:
            issuer-uri: https://identity.example.test/realms/employees

          partners-oidc:
            issuer-uri: https://identity.example.test/realms/partners
~~~

Two issuers differing only in path are still two distinct OP identifiers. That affects discovery, `iss` validation in the ID token, JWK keys, claim policies, and identity boundaries. **Provider ID is a configuration alias; keeping OP parameters unmixed is a security requirement.**

## 8. How Does Provider ID Relate to OIDC Discovery?

For OIDC, provider configuration is usually most concise when using `issuer-uri`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          enterprise-idp:
            issuer-uri: https://login.example.test/realms/training
~~~

When Spring Boot/Spring Security builds `ClientRegistration` for a registration linked to this provider, the library can use **OpenID Provider metadata discovery** to locate the required endpoints. The OP must publish appropriate metadata, typically at the `.well-known/openid-configuration` path derived from the issuer and applicable discovery rules.

Depending on the provider, metadata may publish:

- `issuer`;
- `authorization_endpoint`;
- `token_endpoint`;
- `jwks_uri`;
- `userinfo_endpoint`;
- signing algorithms, Client authentication methods, and other features supported by the OP.

Spring Security uses the required details to construct the appropriate Client configuration. You do not need to manually copy all endpoints if discovery is complete and accurate.

### 8.1. Provider ID Does Not Verify Issuer in Place of Issuer URI

Suppose:

~~~yaml
registration:
  admin:
    provider: main-idp
    client-id: admin-web
    scope: [openid]
provider:
  main-idp:
    issuer-uri: https://id.example.test/realms/staff
~~~

The ID `main-idp` is only an internal key. A valid ID token must pass OIDC checks, including that the actual issuer matches `https://id.example.test/realms/staff`. Naming the provider ID `staff` or `main-idp` does not change the issuer inside the token.

### 8.2. Discovery Path and Hostname

Use the **official issuer published by the OP**, not a guess from an admin UI path or a token endpoint URL. For example, in a system behind a reverse proxy:

- The application knows the OP via its public URL `https://login.example.test/realms/staff`.
- Metadata and ID tokens also use this public issuer.
- An internal URL like `http://identity-service:8080/realms/staff` might allow network connectivity, but if it does not match the issuer published by the OP, it can cause validation errors.

Ensure consistency of scheme, host, port (if any), and path according to the OP's configuration. In real environments, use HTTPS and proper TLS verification.

### 8.3. When Does Discovery Occur?

Building `ClientRegistration` from an issuer URI may require fetching provider metadata during application startup, depending on configuration and version. If the OP is not yet ready, DNS/TLS fails, or metadata is invalid, the application may fail right at startup or when preparing the registration.

Therefore, when encountering a provider initialization error, do not look only in `SecurityFilterChain`; check connectivity to the issuer and the published metadata first.

## 9. Providers Without OIDC Discovery: Explicit Endpoint Declaration

Not every Authorization Server is an OpenID Provider. Some OAuth 2.0 providers only support API access authorization and use custom endpoints and profile APIs.

When suitable OIDC discovery is unavailable, Spring Boot can accept endpoints from the `provider` branch:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-account:
            provider: legacy-auth
            client-id: legacy-web
            client-secret: ${LEGACY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [account.read]
        provider:
          legacy-auth:
            authorization-uri: https://auth.partner.example/authorize
            token-uri: https://auth.partner.example/token
            user-info-uri: https://api.partner.example/user
            user-name-attribute: id
~~~

This is an **OAuth 2.0 Login example that is not OIDC by default**; it only runs if the provider actually exposes endpoints, user profile format, and behavior compatible with Spring Security OAuth2 Login. Names and URLs here are hypothetical for the lesson.

The distinctions:

- `registration.legacy-account.provider: legacy-auth` still only performs the linking role.
- `provider.legacy-auth.authorization-uri` is the endpoint to which the user is redirected.
- `token-uri` is where the Client exchanges the code for tokens.
- `user-info-uri` and `user-name-attribute` let the Client fetch and identify `OAuth2User` according to the provider's custom contract.
- Without the `openid` scope and an OIDC ID token, do not describe this as OIDC authentication merely because Spring Security can create an `Authentication` from provider data.

If you are implementing **OIDC**, prefer `issuer-uri` to leverage metadata and proper OIDC rules. Only configure endpoints manually when there is a specific requirement and you thoroughly understand the provider's protocol.

### 9.1. When JWK Set URI Is Needed

With OIDC or JWT types verified via JWK, provider config may involve `jwk-set-uri`. However, when discovery already supplies the appropriate `jwks_uri`, there is no need to re-enter the URI manually just to "fill out the config."

Also distinguish the JWK Set used to verify ID tokens for the **Client** from JWK/JWT verification on a **Resource Server** receiving access tokens. Both components may fetch keys from the same OP, yet validate tokens for different purposes and audiences.

## 10. Well-Known Default Providers and Choosing Aliases

Spring Security includes default settings for several well-known OAuth2 providers recognized by provider ID, such as `google`, `github`, `facebook`, or `okta` depending on library capabilities and version. In a Spring Boot project, you can take advantage of built-in defaults when the corresponding case is supported.

For example, if you want a registration named `staff-google` while using the default `google` provider:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          staff-google:
            provider: google
            client-id: ${GOOGLE_CLIENT_ID}
            client-secret: ${GOOGLE_CLIENT_SECRET}
            scope: [openid, profile, email]
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

Here:

- `staff-google` is the **registration ID** and appears in the login URL `/oauth2/authorization/staff-google`.
- `google` is the **provider ID** used to select the well-known provider defaults recognized by the library.
- `client-id` and `client-secret` are still the Client credentials registered with Google.
- The callback must be registered accurately with the provider matching the registration's URL.

When using a provider with built-in defaults, you may not need a separate `provider.google` branch if the defaults meet your needs. When you want to override endpoints/settings or use a provider not in the default set, declare the corresponding provider branch.

**Note:** do not assume every built-in provider supports OIDC or the `openid` scope. Providers vary in protocol and features; for instance, traditional GitHub OAuth 2.0 Login uses its user API under the OAuth 2.0 model and does not automatically become OIDC Login just by setting `provider: github`.

### 10.1. Default Aliases and Custom Aliases

| Need | Registration ID | Provider ID | Source of provider settings |
|---|---|---|---|
| Use Google with a custom login name | `staff-google` | `google` | Built-in provider if supported by library |
| Use internal OIDC | `web` | `company-idp` | `provider.company-idp.issuer-uri` |
| Use two Clients on the same OP | `portal`, `reporting` | `company-idp` | Same provider config |
| Use two tenants with different issuers | `staff`, `partner` | `staff-idp`, `partner-idp` | Two separate provider configs |

Inventing an arbitrary provider ID does **not** make Spring Security know OAuth 2.0 URLs from the name alone. A new alias like `corp-sso` requires valid endpoint configuration or an issuer URI, unless it is linked to a supported built-in provider set.

## 11. Registration ID Directly Affects OAuth2 Client URLs and State

In a standard Servlet web configuration, Spring Security provides two default paths:

| Step | URL Pattern |
|---|---|
| Initiate login/authorization | `/oauth2/authorization/{registrationId}` |
| Receive authorization response | `/login/oauth2/code/{registrationId}` |

Example:

~~~yaml
registration:
  console:
    provider: central-oidc
    client-id: console-client
    client-secret: ${CONSOLE_SECRET}
    redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
    scope: [openid, profile]
provider:
  central-oidc:
    issuer-uri: https://sso.example.test/realms/core
~~~

Then:

~~~text
Start:    GET http://localhost:8080/oauth2/authorization/console
Callback:     http://localhost:8080/login/oauth2/code/console
~~~

The browser goes through the Authorization Server identified by `provider.central-oidc`, while internal paths in the Client use **`console`**.

When creating a custom login page, use:

~~~html
<a href="/oauth2/authorization/console">Sign in to Console</a>
~~~

If a learner mistakenly uses the provider ID:

~~~html
<!-- Incorrect if there is no registration named central-oidc -->
<a href="/oauth2/authorization/central-oidc">Sign in to Console</a>
~~~

An error occurs because Spring Security looks up `ClientRegistration` by `registrationId`, rather than taking a provider key and inferring a Client.

### 11.1. Authorized Clients Are Identified by Registration ID

Once an OAuth 2.0 Client is authorized, Spring Security uses `OAuth2AuthorizedClient` to hold the Client registration details and issued tokens. This record is typically looked up by **registration ID** together with the principal identity (or corresponding storage context).

Therefore, two registrations referencing a shared provider can still have separate authorized clients and token sets:

~~~text
registrationId = customer-portal  --> credentials/scopes/tokens of customer-portal
registrationId = support-console  --> credentials/scopes/tokens of support-console
providerId     = shared-sso       --> shared issuer/endpoints
~~~

Sharing a provider **does not merge permissions or access tokens** across two Clients. Always retrieve the token for the right registration and verify permissions suitable for the target API.

### 11.2. Changing `registrationId` Is More Than Editing One Name in YAML

If you rename `console` to `operations`:

- The URL `/oauth2/authorization/console` must change to `/oauth2/authorization/operations`.
- The default callback becomes `/login/oauth2/code/operations`; the OP may need its redirect URI updated.
- Source code referencing `@RegisteredOAuth2AuthorizedClient("console")` or looking up the registration via repository must change accordingly.
- Authorized client records stored under the old registration ID may need to be handled according to application policy.

Conversely, renaming only the provider alias `central-oidc` to `company-sso` (and updating the matching provider key) does not require changing login URLs if `registrationId` remains unchanged.

## 12. Configuring HTTP Security to Use the Linked Registration

Provider and registration properties only define **OAuth 2.0 Client settings**. The application must still enable the login mechanism in HTTP Security if it defines its own `SecurityFilterChain`.

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

When a browser accesses a protected page, Spring Security can initiate the OIDC login flow. When a user visits `/oauth2/authorization/console`, Spring Security looks up the `ClientRegistration` with ID `console`. That registration has already been constructed from the Client data and the linked provider.

In an application relying purely on Spring Boot auto-configuration, Boot can provide a default chain when eligible. If you declare your own `SecurityFilterChain` bean, do not assume `oauth2Login()` stays enabled; configure it explicitly on the chain handling login.

### 12.1. One Registration, One Provider: Processing Flow

~~~mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant B as Browser
    participant C as Spring Security Client
    participant R as ClientRegistrationRepository
    participant OP as OpenID Provider
    U->>B: Choose Sign in to Console
    B->>C: GET /oauth2/authorization/console
    C->>R: findByRegistrationId("console")
    R-->>C: ClientRegistration(console), provider details
    C-->>B: 302 to OP authorization endpoint
    B->>OP: Authorization request with client_id and scope
    OP-->>B: Redirect to /login/oauth2/code/console?code=...&state=...
    B->>C: Send callback
    C->>OP: Exchange code at token endpoint
    OP-->>C: Token response per OP/Client configuration
    C->>C: Process OIDC, create Authentication/session
    C-->>B: Redirect to original page
~~~

At runtime, Spring Security operates on the resolved **`ClientRegistration` and provider details**. The provider ID is a configuration-time link; it is not identity information returned by the OP to the Client.

## 13. Inspecting the Mapping in Java Code

When configuring multiple registrations, you can inspect a `ClientRegistration` via `ClientRegistrationRepository`. This is a diagnostic step to confirm the application has bound data from YAML properly.

Spring Boot example:

~~~java
import java.util.List;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class ClientRegistrationDiagnostics {

    @Bean
    ApplicationRunner showSafeClientConfiguration(
            ClientRegistrationRepository registrations) {

        return args -> {
            for (String id : List.of("customer-portal", "support-console")) {
                ClientRegistration registration =
                    registrations.findByRegistrationId(id);

                if (registration == null) {
                    throw new IllegalStateException(
                        "Missing OAuth2 registration: " + id);
                }

                System.out.println("registrationId=" +
                    registration.getRegistrationId());
                System.out.println("issuer=" +
                    registration.getProviderDetails().getIssuerUri());
                System.out.println("authorizationUri=" +
                    registration.getProviderDetails().getAuthorizationUri());
            }
        };
    }
}
~~~

This snippet only prints non-secret diagnostic values for use in development environments. Do not print client secrets, access tokens, refresh tokens, authorization codes, or cookies. For an OAuth2 provider without an issuer declared, `getIssuerUri()` may be null; the authorization/token endpoints are what to inspect.

**Technical note:** `providerId` in YAML is a key for Spring Boot to combine properties, rather than necessarily having a `ClientRegistration.getProviderId()` method. After binding, `ClientRegistration` carries `registrationId`, client ID, scopes, redirect URI, and the corresponding `ProviderDetails`. When you need to know the original provider alias, check the declared application configuration instead of assuming such a getter exists.

### 13.1. What Happens If the Application Defines Its Own `ClientRegistrationRepository`?

If the application declares its own `ClientRegistrationRepository` bean, Spring Boot may back off from providing the default repository built from properties. In that case:

- `application.yml` may still contain `registration`/`provider` branches, yet you cannot assume the custom repository loaded those configurations.
- Registrations available at runtime depend on the implementation of the bean supplied by the application.
- Verify that each `ClientRegistration` is built with the right issuer/endpoints/scopes, especially when configured dynamically per tenant.

Therefore, when Java code cannot find a `registrationId` despite valid YAML, first check whether a custom repository is overriding auto-configuration.

## 14. Common Errors Caused by Incorrect Provider ID Linking

### 14.1. Provider Value Does Not Match the Declared Key

Example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: employee-sso
            client-id: portal-client
            client-secret: ${PORTAL_SECRET}
            scope: [openid]
        provider:
          employees-sso:
            issuer-uri: https://id.example.test/realms/employees
~~~

The registration selects `employee-sso`, while the provider branch has ID `employees-sso`. The two strings differ because of the extra `s`. This is a **configuration mapping error**, not a user account error.

The application may fail to build the registration or fail to obtain the required provider details, depending on conditions and version; do not rely on one fixed exception message. Fix both to use the exact same ID:

~~~yaml
registration:
  portal:
    provider: employees-sso
    client-id: portal-client
    client-secret: ${PORTAL_SECRET}
    scope: [openid]
provider:
  employees-sso:
    issuer-uri: https://id.example.test/realms/employees
~~~

### 14.2. Confusing Provider ID with Registration ID When Building Login Links

Given registration:

~~~yaml
registration:
  intranet:
    provider: company-sso
    client-id: intranet-web
    scope: [openid]
~~~

The right link for this registration is `/oauth2/authorization/intranet`, not `/oauth2/authorization/company-sso` unless there truly is another registration named `company-sso`.

### 14.3. Placing Issuer Under the Wrong Branch

Structurally incorrect example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          intranet:
            provider: company-sso
            client-id: intranet-web
            issuer-uri: https://id.example.test/realms/company
~~~

`issuer-uri` is for provider metadata, so it must be placed under `spring.security.oauth2.client.provider.company-sso.issuer-uri`. Placing it arbitrarily under registration will not make Spring Boot treat it as a valid provider configuration.

### 14.4. Giving Two Tenants with Different Issuers the Same Provider ID

For example, `sales` and `hr` belong to two realms with different issuers, yet both use:

~~~yaml
registration:
  sales:
    provider: company
  hr:
    provider: company
provider:
  company:
    issuer-uri: https://id.example.test/realms/sales
~~~

Then the `hr` configuration relies on `sales`'s issuer. If tokens/metadata belong to a different realm, the flow may fail or reveal a flawed trust boundary design. Create a separate provider for each real issuer and point each registration to its matching provider.

### 14.5. Provider Present, Registration Missing

Declaring only:

~~~yaml
spring:
  security:
    oauth2:
      client:
        provider:
          company-sso:
            issuer-uri: https://id.example.test/realms/company
~~~

is not enough for Spring Security to have a Client registration named `company-sso` for login. You need at least one registration with a client ID and the required properties linked to that provider.

### 14.6. Missing `openid` While Expecting an OIDC Principal

A registration with an OIDC provider whose scope is only `profile` or an API permission does not implicitly request the OIDC login protocol. To sign in with OIDC, the registration needs the `openid` scope and the OP must handle OIDC according to standard.

`provider: company-sso` only selects the provider configuration block. It **does not automatically add the `openid` scope**, does not determine which claims the user receives, and does not automatically enable `oauth2Login()` in a custom filter chain.

### 14.7. Redirect URI Does Not Match the OP

When a registration ID changes from `portal` to `portal-v2`, the default callback also changes. If the IdP only allows `/login/oauth2/code/portal`, the new request with `/login/oauth2/code/portal-v2` may be rejected.

In that case, the issuer/provider mapping may be fine; the mismatch lies in the **registration and the redirect URI configuration at the OP**. Compare full scheme, host, port, and path, and also check whether a reverse proxy alters the public base URL.

### 14.8. OP Does Not Support or Publish Valid Metadata

If `issuer-uri` points to the wrong path, metadata is unreachable, TLS fails, or the OP does not support discovery, Spring Boot/Spring Security may fail to build the registration. Verify the issuer URL published by the OP and the actual metadata; do not change `providerId` randomly to try fixing a connection error.

## 15. Lab A — Linking a Registration to a Custom Provider

**Objective:** master the `registration.<id>.provider` syntax.

**Prerequisites:** an OP supporting OIDC in a test environment, a Client registered at the OP, and a Spring Boot MVC application with the OAuth2 Client starter.

**Configuration:**

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          course-ui:
            provider: training-sso
            client-id: course-ui-web
            client-secret: ${COURSE_UI_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          training-sso:
            issuer-uri: https://identity.example.test/realms/training
~~~

Addresses are illustrative; to actually run, replace with the OP in use and the issued client ID/secret.

**Steps:**

1. Match `provider: training-sso` with the `provider.training-sso` key.
2. Verify the issuer URI in configuration matches the OP metadata.
3. Ensure the OP accepts the callback `http://localhost:8080/login/oauth2/code/course-ui` if the app runs at `http://localhost:8080`.
4. Enable `oauth2Login()` in the security chain if the application defines its own chain.
5. Open `http://localhost:8080/oauth2/authorization/course-ui` to initiate login.
6. Observe the redirect to the OP and callback to the Client; after login, inspect the principal through a safe endpoint.
7. Do not copy real tokens, codes, or cookies into lab notes.

**Expected result:** `course-ui` is resolved by Spring Security as the registration ID, while endpoints/issuer come from provider `training-sso`. The provider ID does not appear as the registration ID in the default login URL.

**Question:** if you rename `training-sso` to `training-oidc` in both places, does the login URL need to change? If you rename `course-ui` to `course-portal`, which parts must be updated?

## 16. Lab B — Reusing One Provider Across Two Registrations

**Objective:** see clearly that Client identities differ while endpoints/issuer can be shared.

**Preparation:** register two Clients `learning-web` and `admin-web` at the same OP, each with appropriate secret and callback.

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          learner:
            provider: training-idp
            client-id: learning-web
            client-secret: ${LEARNING_WEB_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]

          administrator:
            provider: training-idp
            client-id: admin-web
            client-secret: ${ADMIN_WEB_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, admin.read]

        provider:
          training-idp:
            issuer-uri: https://id.example.test/realms/training
~~~

**Steps:**

1. Add two login links pointing to `/oauth2/authorization/learner` and `/oauth2/authorization/administrator`.
2. Open each flow in a separate browser session for clear observation.
3. Compare `client_id` in the authorization request (without sharing other sensitive values) and the redirect URI in each flow.
4. After login, check the authorized client's registration ID according to the application feature in use.
5. Observe that both issuer and authorization endpoint lead to the same OP.
6. Compare requested scopes with actually granted scopes; do not assume admin privileges from a scope named `admin.read`.

**Expected result:** two Client registrations share provider metadata while having separate client IDs, redirect URIs, and managed tokens. Reusing a provider config does not mean the Clients share the same application identity or access rights.

## 17. Lab C — Intentionally Triggering and Isolating Linking Errors

**Objective:** distinguish alias errors, registration errors, and provider/issuer errors.

Run each variant separately in a lab environment, then **revert the configuration** to avoid overlapping errors.

| Variant | Intentional change | Sign to observe | Conclusion |
|---|---|---|---|
| Mismatched alias | `registration.web.provider: oidc-main` while only `provider.main-oidc` exists | Registration initialization or discovery/config fails | Wrong linking key name |
| Wrong login URL | Use `/oauth2/authorization/main-oidc` while the registration is named `web` | Registration not found for requested URL | Login URL requires `registrationId` |
| Wrong Issuer URI | Point `issuer-uri` to a different issuer/realm | Discovery/issuer validation may fail | Provider identity mismatch |
| Stale callback | Change registration ID without updating URI at OP | OP rejects redirect URI or callback fails | Client registration and OP must stay in sync |
| Missing `openid` scope | Request only `profile` on login | Expected `OidcUser` behavior not received | OIDC provider alone is not enough; OIDC must be requested properly |
| Same provider for two tenants | Two registrations with different issuers share a provider | Wrong endpoint/issuer/claims or verification failure | Separate provider needed per issuer |

The exact outcome may be a startup error, rejection at the OP, or a failure during login, depending on Spring Security/Boot implementation and the provider used. The lab's purpose is to **identify the configuration layer responsible**, not to memorize a single error message.

## 18. How to Observe and Troubleshoot in Spring Boot

To diagnose issues, check in order: **registration ID → provider alias → issuer/endpoints → redirect URI → HTTP Security**.

### 18.1. Inspect the Bound Configuration

Look for the branches:

~~~text
spring.security.oauth2.client.registration.<registrationId>.provider
spring.security.oauth2.client.registration.<registrationId>.client-id
spring.security.oauth2.client.registration.<registrationId>.scope
spring.security.oauth2.client.provider.<providerId>.issuer-uri
~~~

Confirm the provider ID matches the intended key exactly. If configuration is overridden by profiles or environment variables, verify the resolved source safely; never print secrets to logs.

### 18.2. Inspect Provider Metadata

For OIDC, identify the issuer published by the OP and the corresponding discovery endpoint. Verify that metadata returns the right issuer, endpoints, and required JWK Set URI. If behind a reverse proxy, verify the OP is publishing valid public URLs.

Do not guess metadata from the provider ID alone: `corp-sso` is an application-chosen name and cannot substitute for real URLs.

### 18.3. Inspect Requests Entering Spring Security

With default login configuration, `/oauth2/authorization/{registrationId}` is handled by `OAuth2AuthorizationRequestRedirectFilter`. When using `oauth2Login()`, the default callback goes through OAuth2 login processing at `/login/oauth2/code/{registrationId}`.

If the application customizes `SecurityFilterChain`, confirm that the chain covers both the login initiation path and the callback path. Do not mistake a filter matcher error for a provider ID error; both can stop login from working, but their fixes differ.

### 18.4. Enable Controlled Logging

In development environments you can set:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
~~~

Observe filter execution and requests without storing raw authorization codes, tokens, client secrets, cookies, or credentials. Avoid sending sensitive logs to shared systems or enabling high log verbosity in production just to explain lab exercises.

### 18.5. Quick Troubleshooting Table

| Symptom | Questions to answer |
|---|---|
| Provider config exists, but no login appears | Is a registration declared? Is `oauth2Login()` enabled on the matching chain? |
| Visiting `/oauth2/authorization/<providerId>` does nothing | Is that ID actually a registration ID? |
| Registration fails to build | Does the provider alias match a key? Does the provider have the required discovery/endpoint settings? |
| Browser goes to the wrong OP | Does this registration point to the right provider ID? Are issuer/endpoints mixed across tenants? |
| Callback rejected after OP login | Does the registration's redirect URI match a URI registered at the OP? |
| Token issuer is not as expected | Is the provider config pointing to the wrong realm/issuer? Which issuer do metadata and the ID token use? |
| After renaming registration, API-calling code cannot find authorized client | Is anything still referencing the old registration ID? |
| Two registrations share an OP, but scopes seem mixed | Are scopes set separately under each registration? Is the wrong registration being used when requesting a token? |

## 19. Security and Operations When Configuring Multiple Providers

Linking via provider ID is a configuration convenience, while the system must rely on **verified protocol parameters** to establish trust.

- **Correct issuer:** every OIDC provider config must use the exact issuer URI; ID tokens are validated for issuer, audience, signature, expiration, and required OIDC conditions.
- **Separate client credentials:** multiple registrations on the same OP can still have different secrets. Use environment variables or a secret manager; never commit client secrets to a repository.
- **Restricted redirect URIs:** register only necessary callbacks at the OP. When changing a registration ID, update under change control.
- **Least-privilege scopes:** grant permissions according to each registration's needs; sharing a provider does not mean sharing all scopes.
- **Purpose-bound tokens:** ID tokens are for the Client to authenticate the user, access tokens are for the Resource Server; do not mix them up merely because they share an issuer.
- **Check HTTP Security:** provider configuration does not automatically protect internal paths. Ensure chains and access rules are right.
- **Tenant isolation:** if issuers or trust boundaries differ, use separate provider configurations and an intentional account-linking policy.
- **Safe observability:** record only registration ID, issuer, public endpoints, and appropriate check outcomes in logs/docs; redact tokens, cookies, and secrets.

When managing multiple environments such as `dev`, `staging`, and `production`, use profiles or external configuration to substitute the matching issuer/client ID. Never let a profile combine a production issuer with a staging client secret. Values must stay consistent within the same environment configuration.

## 20. Self-Check Questions

**Question 1.** Configuration has `registration.dashboard.provider: central-login` and `provider.central-login.issuer-uri: https://id.example.test/realms/main`. What name will the default login initiation URL use?

*Hint:* `/oauth2/authorization/dashboard` uses the registration ID, not the provider ID.

**Question 2.** Can two registrations share `provider: central-login` while having different client IDs?

*Hint:* yes, if they are genuinely two Clients at the same provider, registered and authorized separately.

**Question 3.** There are two realms with different issuers. Should they point to the same provider ID because both run Keycloak?

*Hint:* no. Provider config must reflect the exact issuer/endpoints of each OP.

**Question 4.** Must `providerId` equal `client-id` or the OP's domain?

*Hint:* no. It is an internal configuration alias in the application.

**Question 5.** There is a `provider.company-sso.issuer-uri` branch, but `registration` is missing. Will Spring Security automatically create a login registration?

*Hint:* do not assume so. Provider config describes the server; a Client registration must exist separately.

**Question 6.** If a registration is renamed from `web` to `dashboard`, what needs to be checked?

*Hint:* login URLs, registered callbacks, source code using the registration ID, and authorized client storage.

**Question 7.** Why does `provider: github` not automatically turn an OAuth 2.0 login into OIDC?

*Hint:* the actual protocol, scopes, ID token, and provider metadata determine whether OIDC is used.

**Question 8.** Once Spring Security has built `ClientRegistration` from YAML, should you look for `getProviderId()` to find the issuer?

*Hint:* use `getProviderDetails().getIssuerUri()` and the resolved provider properties. The provider alias is a key at the configuration properties layer.

## 21. References

- [Spring Boot Reference — Spring Security OAuth2](https://docs.spring.io/spring-boot/reference/web/spring-security.html#web.security.oauth2): declaring `spring.security.oauth2.client.registration.*` and `provider.*` in Boot, depending on version.
- [Spring Security Reference — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `ClientRegistration`, repository, authorized client, and usage in Servlet applications.
- [Spring Security Reference — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): authorization URL, login callback, and login configuration.
- [Spring Security API — ClientRegistration](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/registration/ClientRegistration.html): properties of registration and provider details.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata, discovery, and OIDC endpoints.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, issuer, audience, and authentication checks.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): roles of Client, Authorization Server, tokens, and authorization parameters.

**Remember:** `registrationId` identifies a **Client registration** in the application; `providerId` identifies the **provider configuration block** referenced by that registration. The line `registration.<registrationId>.provider: <providerId>` is the bridge between the two parts. You can use different names, reuse one provider across multiple registrations, or separate providers per issuer; always ensure client credentials, callbacks, scopes, and issuer/endpoints actually match the system in use.
