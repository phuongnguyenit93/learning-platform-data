# ClientRegistration and ClientRegistrationRepository in Spring Security Servlet

> **Scope:** Java 17+, Spring Boot 3.x, Spring Security 6.x on the Servlet stack (Spring MVC). This lesson focuses on OAuth2 Client/OIDC configuration: how a Spring application registers with an Authorization Server, stores configuration in `ClientRegistration`, looks it up through `ClientRegistrationRepository`, and distinguishes client configuration from an issued access token.

## 1. Context and objectives

In OAuth 2.0, a **client** is an application that requests an access token from an **Authorization Server** to call a **Resource Server**. For "Sign in with Google" in Spring MVC, the Spring application is an OAuth2 client using the authorization code flow; for a backend calling an API without a user, it can be an OAuth2 client using client credentials.

An application must register with the Authorization Server before requesting tokens. The provider issues a `client_id`; a confidential client typically has a `client_secret` or another client authentication mechanism. The provider also restricts redirect URIs, grant types, and scopes. Spring Security needs to know those parameters:

- `ClientRegistration` describes **one** registered client configuration: ID, credentials, grant, scope, redirect URI, and provider endpoints.
- `ClientRegistrationRepository` provides a **registration lookup method by ID** for OAuth2 filters/components.
- `OAuth2AuthorizedClient` represents a **client that has been granted a token** in the context of a specific principal; the two configuration types above are not token stores.

After this lesson, you will be able to configure one or more registrations, understand the login/authorization path, write Java beans or look up registrations, test without calling an IdP, and distinguish common errors.

## 2. ClientRegistration: configuration components

The class `org.springframework.security.oauth2.client.registration.ClientRegistration` is the configuration model of an OAuth2 client. It is not an HTTP request, does not hold current login state, and does not automatically issue access tokens.

| Field / getter | Meaning |
| --- | --- |
| `registrationId` / `getRegistrationId()` | **Spring internal** key, e.g., `google`, `github`, `company-login`. |
| `clientId` / `getClientId()` | ID issued by the Authorization Server; differing from registrationId is normal. |
| `clientSecret` / `getClientSecret()` | Server-side secret of a confidential client if used; do not send to frontend/logs. |
| `clientAuthenticationMethod` | How the client authenticates to the AS, such as `client_secret_basic` or `client_secret_post`. |
| `authorizationGrantType` | Grant such as `authorization_code` or `client_credentials`. |
| `redirectUri` | Callback URI for the authorization code flow, typically `{baseUrl}/login/oauth2/code/{registrationId}`. |
| `scopes` | Permissions the client requests the AS to grant; OIDC typically includes `openid`. |
| `clientName` | Human-readable name for UI display. |
| `providerDetails.authorizationUri` | Endpoint to start browser-based authorization (authorization code). |
| `providerDetails.tokenUri` | Endpoint to exchange a code or credentials for a token. |
| `providerDetails.jwkSetUri` / `issuerUri` | Metadata related to the AS/OIDC and token verification when applicable. |
| `providerDetails.userInfoEndpoint` | UserInfo URI and user-identifying attribute name, when supported by the provider. |

Required parameters vary by grant. `authorization_code` requires an authorization endpoint and redirect URI; `client_credentials` requires a token endpoint, client authentication, and scopes, and typically does not need an authorization URI or redirect URI because there is no browser callback.

### Why is registrationId not clientId?

Example:

~~~text
registrationId = company-login        (Spring internal key)
provider alias = company-oidc         (provider group name)
clientId       = portal-web-prod      (ID issued by Authorization Server)
clientName     = Company SSO          (display label)
~~~

Spring looks up configuration via `findByRegistrationId("company-login")`; the default login initiation URL is `/oauth2/authorization/company-login`. Meanwhile, the Authorization Server receives `client_id=portal-web-prod`. Changing `registrationId` can change the flow start URL, callback, and authorized client storage key; do not change it arbitrarily just to change a label.

## 3. ClientRegistrationRepository: the lookup contract

The interface `org.springframework.security.oauth2.client.registration.ClientRegistrationRepository` defines the core method:

~~~java
ClientRegistration findByRegistrationId(String registrationId);
~~~

This is a lookup contract. It does **not** define methods to fetch access tokens, refresh tokens, list all providers, or edit secrets. With the common implementation `InMemoryClientRegistrationRepository`, an unfound ID returns `null`. Calling code must handle that case.

`InMemoryClientRegistrationRepository` accepts one or more `ClientRegistration` instances and holds them in memory. It also implements `Iterable<ClientRegistration>`, so registrations can be enumerated when building a login page. A custom repository **only needs** to satisfy lookup; you cannot assume every repository can be cast to `Iterable`.

Comparing easily confused objects:

| Object | Data and lifecycle |
| --- | --- |
| `ClientRegistration` | Relatively static configuration of an OAuth2 client. |
| `ClientRegistrationRepository` | Lookup source for configuration by registrationId. |
| `OAuth2AuthorizationRequest` | In-flight authorization request: state, redirectUri, scopes, and related parameters. |
| `OAuth2AuthorizedClient` | Registration configuration bound to a principal and access token/refresh token issued by the AS. |
| `OAuth2AuthorizedClientRepository` | Authorized client store in the Servlet request/response context. |
| `OAuth2AuthorizedClientService` | Authorized client store by registration ID/principal, not tied directly to the request API. |
| `OAuth2AuthorizedClientManager` | Coordinates authorize, refresh, or re-authorize per the appropriate grant and context. |

**Key takeaway:** finding a registration only proves Spring knows about this client; it does **not** prove the token is valid, the user has logged in, or the AS has granted permission.

## 4. Using Spring Boot to build a repository from YAML

With a few static providers, the simplest approach is declaring `spring.security.oauth2.client.registration.*`, along with `spring.security.oauth2.client.provider.*` if needed. When the OAuth2 Client starter is on the classpath and configuration is valid, Boot usually auto-configures a `ClientRegistrationRepository` bean.

### 4.1 GitHub: provider with default settings

In `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          github:
            client-id: ${GITHUB_CLIENT_ID}
            client-secret: ${GITHUB_CLIENT_SECRET}
            scope:
              - read:user
              - user:email
~~~

Registration ID `github` receives default provider values supported by Boot. Before running, register a real GitHub OAuth App, supply the client ID/secret via environment variables, and register the exact callback. Do not commit real credentials into Git, logs, or documentation.

Typical URL to initiate authorization code:

~~~http
GET /oauth2/authorization/github HTTP/1.1
Host: app.example.org
~~~

Spring Security Servlet typically uses the redirect URI template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

With public app `https://app.example.org`, the callback example is `https://app.example.org/login/oauth2/code/github`. The URI accepted by the AS must match the actual URI; when running behind a reverse proxy, ensure the public host/scheme is reconstructed properly. GitHub OAuth in this example is not automatically synonymous with OIDC; do not assume GitHub issues an ID token.

### 4.2 Custom OpenID Connect provider

Declare a separate registration and provider alias:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-login:
            provider: company-oidc
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
            client-name: "Company SSO"
        provider:
          company-oidc:
            issuer-uri: https://idp.example.org/realms/training
~~~

The URL `idp.example.org` only illustrates structure and must be replaced with an active OIDC issuer in a real application. `issuer-uri` enables metadata discovery when supported by the provider; initialization may require accessing metadata. An incorrect or unreachable issuer can cause startup failure.

Here `company-login` is the registrationId, `company-oidc` is the provider alias, and `client-id` is issued by the AS. The `openid` scope marks an OIDC request. The client authentication method must match the AS; do not assume `client_secret_basic` for a provider that only supports `client_secret_post`.

For an OAuth2 provider without issuer discovery, you can explicitly declare `authorization-uri`, `token-uri`, `user-info-uri`, `user-name-attribute`, and `jwk-set-uri` if used. Obtain these values from the actual AS metadata/documentation.

### 4.3 Secrets and auto-configuration issues

Client secrets are information **only the server should know**. Use environment variables or a secret manager; do not expose them via a REST endpoint meant for the frontend and do not print the entire `ClientRegistration` object into logs.

When you manually define a `ClientRegistrationRepository` bean in Java, Boot's auto-configuration can **back off**. Registrations declared in YAML will not necessarily be merged automatically with the Java bean. Choose a single configuration source or explicitly build a composite repository.

## 5. Creating ClientRegistration and repository in Java

`ClientRegistration.withRegistrationId(...)` returns a builder; `CommonOAuth2Provider` provides presets for several common providers. The following is `GoogleClientRegistrationConfig.java` in a Spring Boot project with the OAuth2 Client starter. This is an alternative to configuring `registration.google` via YAML.

~~~java
package com.example.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.oauth2.client.CommonOAuth2Provider;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;

@Configuration
public class GoogleClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository(
            @Value("${app.google.client-id}") String clientId,
            @Value("${app.google.client-secret}") String clientSecret) {

        ClientRegistration google = CommonOAuth2Provider.GOOGLE
                .getBuilder("google")
                .clientId(clientId)
                .clientSecret(clientSecret)
                .scope("openid", "profile", "email")
                .build();

        return new InMemoryClientRegistrationRepository(google);
    }
}
~~~

The application can read configuration from `application.properties`:

~~~properties
app.google.client-id=${GOOGLE_CLIENT_ID}
app.google.client-secret=${GOOGLE_CLIENT_SECRET}
~~~

Explanation:

1. The `CommonOAuth2Provider.GOOGLE` preset supplies a builder with provider endpoints and suitable defaults.
2. `clientId/clientSecret` come from externalized configuration; the secret is not hardcoded in the Java class.
3. `build()` creates the `ClientRegistration` **configuration**; it does not call the token endpoint or log in a user.
4. The in-memory repository returns the registration when Spring calls `findByRegistrationId("google")`.
5. A valid Google OAuth2 client, exact callback, and a user completing the flow are required for a successful login.

**Example scope:** this is a Java class in a Spring application with the Spring Security OAuth2 Client dependency, not standalone Java SE. `javac` without the project's libraries will not compile; there is no automatic stdout.

### 5.1 client_credentials example using the builder directly

The following Java snippet illustrates a place where the two variables `clientId` and `clientSecret` are already obtained from a secret store:

~~~java
ClientRegistration inventory = ClientRegistration
        .withRegistrationId("inventory")
        .clientId(clientId)
        .clientSecret(clientSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
        .tokenUri("https://idp.example.org/oauth2/token")
        .scope("inventory.read")
        .clientName("Inventory Service")
        .build();
~~~

Required imports:

~~~java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
~~~

With `client_credentials`, the client has no browser authorization screen/callback. It needs a token endpoint, credentials/method, and a scope permitted by the AS. The `idp.example.org` endpoint is an illustrative address. **Defining a registration does not automatically call the token endpoint**; you must use an authorized-client manager/provider configured to support client credentials.

## 6. How Spring Security Servlet uses the repository during login

Example `OAuth2LoginSecurityConfig.java` that compiles in a Spring Boot application already having a repository bean via YAML or Java, with OAuth2 Client/Web/Security dependencies:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OAuth2LoginSecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());
        return http.build();
    }
}
~~~

`oauth2Login` provides the authorization code/OIDC branch used for user login; `oauth2Client` enables the OAuth2 Client integration mechanism for using authorized clients. This configuration does not automatically attach a Bearer token to every outbound HTTP request; you must integrate the HTTP client/authorized client manager properly.

Typical flow with registration `google`:

1. Browser GET `/oauth2/authorization/google`. `OAuth2AuthorizationRequestRedirectFilter` queries the repository by `google` to obtain the client ID, provider authorization endpoint, scopes, and redirect URI.
2. Spring creates an `OAuth2AuthorizationRequest` with an unpredictable `state`, saves the pending authorization request state, and redirects to the AS.
3. After the user authenticates/grants permission at the AS, the browser is redirected back to callback `/login/oauth2/code/google` carrying `code` and `state`.
4. `OAuth2LoginAuthenticationFilter` handles the callback, checks state/authorization response, looks up the registration again, and exchanges the code with the token endpoint using the proper client authentication.
5. Depending on OAuth2/OIDC, Spring loads/verifies the necessary user info and builds an `Authentication`. Tokens belong to `OAuth2AuthorizedClient` and its token store, not the registration.

~~~text
Browser -> GET /oauth2/authorization/google
        -> ClientRegistrationRepository.findByRegistrationId("google")
        -> authorization request + state
        -> redirect to AS
AS      -> /login/oauth2/code/google?code=...&state=...
        -> validate state + lookup client
        -> token endpoint (code exchange)
        -> Authentication + OAuth2AuthorizedClient
~~~

`state` in the authorization code flow is a mechanism for linking the callback to the authorization request; it is not synonymous with the CSRF token required by `CsrfFilter` on state-changing HTTP requests in a web app session.

## 7. Looking up a registration in a Java Service

File `ClientRegistrationLookup.java` in a Spring Boot component-scanned package:

~~~java
package com.example.security;

import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.stereotype.Service;

@Service
public class ClientRegistrationLookup {

    private final ClientRegistrationRepository repository;

    public ClientRegistrationLookup(ClientRegistrationRepository repository) {
        this.repository = repository;
    }

    public ClientRegistration require(String registrationId) {
        ClientRegistration registration =
                repository.findByRegistrationId(registrationId);
        if (registration == null) {
            throw new IllegalArgumentException(
                    "Unknown client registration: " + registrationId);
        }
        return registration;
    }
}
~~~

This service uses constructor injection and throws a clear error when the ID does not exist. It looks up the **registration ID**, not the client ID or provider name. Do not return `ClientRegistration` directly from a public JSON API because it may contain a secret.

With a repository implementation that implements `Iterable<ClientRegistration>` such as the in-memory one, you can list registrations to display login options. However, the base interface does not require `Iterable`; a custom repository is not guaranteed to support that capability. Only list necessary public info; never log `getClientSecret()` or tokens.

## 8. Multiple registrations coexisting with different grants

Example using GitHub for user login while using an inventory AS for a service to obtain tokens:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          github:
            client-id: ${GITHUB_CLIENT_ID}
            client-secret: ${GITHUB_CLIENT_SECRET}
            scope:
              - read:user
          inventory:
            provider: internal-auth
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          internal-auth:
            token-uri: https://idp.example.org/oauth2/token
~~~

- `github` uses authorization code; `/oauth2/authorization/github` can initiate login/authorization.
- `inventory` uses client credentials; it does not use browser login, so do not point at `/oauth2/authorization/inventory` expecting a redirect.
- The same `ClientRegistrationRepository` can serve both. However, to get a token for `inventory`, you must configure an `OAuth2AuthorizedClientManager` with the `client_credentials` grant and the right principal/service context.

### Distinguishing static config from runtime tokens

~~~text
ClientRegistrationRepository
  "github"    -> client ID, secret, scope, provider metadata
  "inventory" -> client ID, secret, token URI, grant

OAuth2AuthorizedClientService / Repository
  ("github", principal="alice")  -> Alice's access/refresh token
  ("github", principal="bob")    -> Bob's access/refresh token
  ("inventory", servicePrincipal)-> service token
~~~

`DefaultOAuth2AuthorizedClientManager` is generally suitable for a Servlet request context; `AuthorizedClientServiceOAuth2AuthorizedClientManager` works in service/background tasks without a Servlet request. Do not treat `ClientRegistrationRepository` as a token store; tokens have expirations and can be refreshed/revoked, whereas a registration is configuration used to request tokens.

## 9. Custom repository and multi-tenant: design risks

Writing a custom `ClientRegistrationRepository` is useful when registrations live in a DB, tenant store, or secret manager and must be looked up dynamically. Keep these caveats in mind:

- **Tenant isolation:** do not let a request freely choose another tenant's ID and read its client secret.
- **Caching & rotation:** caching avoids querying the secret store on every request, but must be invalidated safely when secrets/provider endpoints change.
- **Consistency between redirect and callback:** an authorization code request starts with configuration A; if client ID/redirect/issuer changes while the user is at the IdP, the callback may no longer match.
- **Endpoint trust/SSRF:** do not let untrusted users supply token/issuer URLs for the server to fetch arbitrarily. Validate provider metadata and domains.
- **Thread safety:** the repository bean is used concurrently by multiple HTTP requests; caches/updates must be thread-safe.
- **Iterable:** custom lookup does not automatically ensure the default login page lists all providers.
- **Secret protection:** encrypt/store in a secret store and do not dump registration objects when debugging.

With a small number of fixed providers, YAML + externalized secrets are usually easier to understand and less error-prone than a custom dynamic repository.

## 10. Testing lookup without calling the Authorization Server

JUnit 5 example in `src/test/java/com/example/security/ClientRegistrationRepositoryTest.java`. The test requires JUnit Jupiter and Spring Security OAuth2 Client on the test classpath, with no real IdP needed:

~~~java
package com.example.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertSame;

import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

class ClientRegistrationRepositoryTest {

    @Test
    void looksUpClientByRegistrationId() {
        ClientRegistration inventory = ClientRegistration
                .withRegistrationId("inventory")
                .clientId("inventory-service")
                .clientSecret("testing-only")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://idp.example.org/oauth2/token")
                .scope("inventory.read")
                .clientName("Inventory Service")
                .build();

        ClientRegistrationRepository repository =
                new InMemoryClientRegistrationRepository(inventory);

        assertSame(inventory, repository.findByRegistrationId("inventory"));
        assertNull(repository.findByRegistrationId("missing"));
        assertEquals("inventory-service",
                inventory.getClientId());
        assertEquals("client_credentials",
                inventory.getAuthorizationGrantType().getValue());
    }
}
~~~

This test proves the builder/repository returns the right data by ID; it does **not** prove the real secret is valid, the AS is working, or an access token can be obtained. `testing-only` is a string meant for unit tests, not a production credential. Integration tests for OAuth2 Login/manager must use an AS test sandbox and separately verify state, callback, token endpoint, OIDC validation, and the token store.

## 11. Common errors

| Symptom | Likely root cause | Check |
| --- | --- | --- |
| `findByRegistrationId("google")` returns null | Wrong ID, using clientId/provider alias, or registration not registered. | Compare registrationId in YAML/bean and URL. |
| `/oauth2/authorization/google` 404 | `oauth2Login` not enabled, filter chain not matching, or missing OAuth2 Client dependency. | Check starter, repository bean, security configuration. |
| Spring Boot does not create repository | Invalid/missing properties, custom bean replaced it, issuer discovery error. | Check `spring.security.oauth2.client.*` binding and startup errors. |
| Token endpoint returns `invalid_client` | Wrong client ID/secret, secret rotated, or wrong client auth method. | Check secret store and AS configuration. |
| AS returns `redirect_uri_mismatch` | Public callback does not match registered URI, reverse proxy built wrong scheme/host. | Compare redirect URI, trusted forwarded headers, and TLS. |
| Callback fails due to state/session | State mismatch, session cookie dropped, or session changed. | Inspect authorization request repository, session, callback. |
| OIDC login fails after token | Issuer/JWK/UserInfo/scopes or ID token data incompatible. | Check OIDC discovery/validation for the specific provider. |
| Registration exists but no token | Client manager not called, missing grant provider or principal context. | Check `OAuth2AuthorizedClientManager`, service/repository. |
| `client_credentials` does not open login | This is a machine-to-machine grant, no browser redirect. | Call manager for the grant, do not use login URL. |
| Adding Java bean causes YAML registrations to disappear | Auto-config can back off when a repository bean already exists. | Pick one source or build a composite repository. |

When debugging, only log registrationId, grant, scopes, public redirect, and provider endpoints in a controlled manner. Do not print `clientSecret`, authorization codes, or access/refresh tokens. Separate the three steps: **lookup client config → authorization/token exchange → save/use authorized client**. A failure in a later step is not automatically a repository error.

## 12. Choosing by use case

**Web app with OIDC/OAuth2 login:** configure registration in YAML, let Boot build the repository; enable `oauth2Login`, register the callback with the AS, verify scope, issuer, token exchange, and HTTPS.

**App calling APIs on behalf of logged-in user:** obtain the authorized client/access token through the appropriate manager/repository/service for the principal; do not look for tokens in `ClientRegistration`.

**Backend service-to-service:** create a `client_credentials` registration, use a manager supporting this grant, store the secret server-side, and do not open browser login.

**Multi-tenant / dynamic clients:** custom repository only when truly needed; protect tenant isolation, secret rotation, cache, provider endpoints, and callback consistency.

**Remember:** `ClientRegistration` is the **configuration descriptor of an OAuth2 client**, and `ClientRegistrationRepository` is the **lookup source by registrationId**. Tokens and authorized state reside in `OAuth2AuthorizedClient` and its dedicated repository/service/manager.