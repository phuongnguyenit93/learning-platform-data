# 15.5. OAuth2AuthorizedClientProviderBuilder and Configuring Needed Grants

## 1. The Problem: How Does an Application Obtain and Refresh Tokens?

When a Spring Security application acts as an **OAuth 2.0/OIDC Client**, it does not only need to know the Client ID, token endpoint, or authorization endpoint. The application must also decide **when it may request a token, when it may refresh a token, which grants are permitted, and where tokens are stored**.

For example, the same system might have three needs:

1. A user opens the web application and logs in via an OpenID Provider using the **Authorization Code Flow**.
2. After login, the application calls an API on the user's behalf. When the access token expires, the Client can use the issued **refresh token** to obtain a new access token.
3. A nightly background job needs to call a service API **without an interactive user**. The job uses the **Client Credentials Grant**.

These three needs differ in identity source, granted permissions, token lifecycle, storage mechanism, and grant preconditions. Writing a helper that arbitrarily picks token endpoint requests is error-prone: sending the wrong user's token, attempting to refresh without a refresh token, or running the Authorization Code Flow inside a job with no browser.

Spring Security separates responsibilities into abstractions:

- **<code>ClientRegistration</code>:** describes the registered configuration of an OAuth2 Client.
- **<code>OAuth2AuthorizedClient</code>:** links a `ClientRegistration` to a principal and the issued tokens.
- **<code>OAuth2AuthorizedClientProvider</code>:** component that knows how to execute one or more **authorization grants** when appropriate conditions are met.
- **<code>OAuth2AuthorizedClientProviderBuilder</code>:** builder used to compose commonly used grant providers into a composite provider.
- **<code>OAuth2AuthorizedClientManager</code>:** coordinates Client registrations, current authorized clients, providers, and storage during <code>authorize(...)</code> calls.
- **<code>OAuth2AuthorizedClientService</code> / <code>OAuth2AuthorizedClientRepository</code>:** saves, looks up, and removes authorized clients.

**Core takeaway of this lesson:** <code>OAuth2AuthorizedClientProviderBuilder</code> **declares which grants the Client Manager is permitted to handle**; it does not register a Client with the Authorization Server, does not create an End-User out of thin air, and does not make every grant valid for every `ClientRegistration`.

## 2. Role of ProviderBuilder in the Architecture

~~~mermaid
flowchart TD
    C["Application code / HTTP client"] --> M["OAuth2AuthorizedClientManager"]
    M --> R["ClientRegistrationRepository"]
    M --> S["Authorized Client Service / Repository"]
    M --> P["Composite OAuth2AuthorizedClientProvider"]
    B["OAuth2AuthorizedClientProviderBuilder"] --> P
    P --> A["Authorization Code Provider"]
    P --> F["Refresh Token Provider"]
    P --> CC["Client Credentials Provider"]
    A --> AS["Authorization Server / OpenID Provider"]
    F --> AS
    CC --> AS
    AS --> T["Token response"]
    T --> P
    P --> M
    M --> S
    M --> O["Current OAuth2AuthorizedClient"]
    O --> API["HTTP request to Resource Server"]
~~~

When <code>manager.authorize(request)</code> is called, the manager builds the request context, looks up the `ClientRegistration` and saved authorized client, and passes them to the configured provider. The provider applies the appropriate grant if conditions are satisfied.

With a composite provider, child providers are **tried in configured order**. A provider that does not support the current context normally returns <code>null</code> to yield to the next provider. If a provider encounters an actual token endpoint or authentication error, the exception must be handled properly; never assume the framework silently ignores errors to fall back to a less secure grant.

### 2.1. Four Distinct Questions

| Question | Primary Responsible Component |
|---|---|
| Which Client ID, grant type, and endpoints has the app registered? | <code>ClientRegistration</code> |
| Which token currently exists, and for which principal? | <code>OAuth2AuthorizedClient</code> |
| Which grant can issue or refresh a token in this situation? | <code>OAuth2AuthorizedClientProvider</code> |
| How should authorized clients be found, issued, refreshed, saved, or deleted? | <code>OAuth2AuthorizedClientManager</code> coordinating service/repository |

You do not change <code>ClientRegistration.authorizationGrantType</code> by adding <code>.clientCredentials()</code> to the builder. Both configuration layers must align: **the registration defines the Client and grant type**, while **the provider enables the manager to handle that grant**.

## 3. Commonly Used Grant Providers

<code>OAuth2AuthorizedClientProviderBuilder</code> in Spring Security provides a way to compose common providers:

| Builder Method | Grant / Function | When Is It Appropriate? |
|---|---|---|
| <code>authorizationCode()</code> | Authorization Code Grant | Client logs users in via browser or already has an appropriate authorization code context |
| <code>refreshToken()</code> | Refresh Token Grant | An authorized client exists with a usable refresh token and the access token needs renewal |
| <code>clientCredentials()</code> | Client Credentials Grant | Server-to-server / background job with no End-User |
| <code>provider(customProvider)</code> | Custom provider | Need a grant/condition supported by the framework/Authorization Server via an explicit extension |

Some Spring Security versions include additional APIs or providers for extension grants, such as JWT bearer or token exchange. Those capabilities **depend on the version**, Spring Security documentation, and Authorization Server support. This lesson focuses on the three foundational providers with the broadest applicability.

Do not use the **Resource Owner Password Credentials Grant** as a default choice for new applications. This grant has been dropped from OAuth 2.1 direction and does not fit modern browser/OP login models; supporting APIs across Spring Security releases may change. The **Implicit Grant** is also not recommended for new Clients.

### 3.1. Authorization Code

Interactive user flow:

~~~text
Browser
  → /oauth2/authorization/company
  → OP Authorization Endpoint
  → User authenticates / consents
  → /login/oauth2/code/company?code=...&state=...
  → Token Endpoint
  → Access token and ID Token if OIDC
~~~

In Spring Security Servlet, **<code>oauth2Login()</code> and the login filters** perform the redirect/callback portion. Adding <code>.authorizationCode()</code> to `ProviderBuilder` **does not create a login page or redirect a background job to a browser**.

The Authorization Code Flow typically pairs with **PKCE** according to the Client model and policy. With OIDC, the <code>openid</code> scope triggers the OIDC authentication request; <code>openid</code> is a **scope**, not a separate <code>authorizationGrantType</code>.

### 3.2. Refresh Token

A refresh token is not a second kind of login; it is **a mechanism to continue an existing authorization**.

~~~text
Existing Authorized Client
  ├─ Access token still valid → can keep using it
  ├─ Access token near expiry + refresh token → attempt refresh
  └─ No refresh token / no longer usable
       → cannot refresh with this grant
~~~

When refresh succeeds, the Client receives a new token response and the authorized client must be updated in the appropriate storage. If the Authorization Server uses **refresh token rotation**, the new refresh token must replace the old one per the response.

Do not assume every Authorization Code Flow receives a refresh token; many OPs have specific policies, sometimes requiring <code>offline_access</code> or explicit consent.

### 3.3. Client Credentials

Client Credentials is appropriate when **the application/service itself** is granted permission to access a Resource Server:

~~~text
Batch worker / backend
  → POST /token
       grant_type=client_credentials
       service client authentication
  ← access_token
  → Call API with service's access token
~~~

This grant **does not authenticate an End-User** and does not create an OIDC Login session for a user. In storage, the manager still needs a principal name to partition authorized clients; that name can be a stable service string, yet it does not turn a service token into a user token.

## 4. Basic Syntax of OAuth2AuthorizedClientProviderBuilder

### 4.1. Composing the Three Common Providers

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
~~~

The result is an <code>OAuth2AuthorizedClientProvider</code> capable of evaluating those grants given the supplied context.

It **does not** mean:

- Every registration is automatically allowed to use all three grants.
- An authorization code registration automatically turns into client credentials.
- Client secrets, redirect URIs, PKCE, or consent can be skipped.
- <code>OAuth2AuthorizedClientManager</code> is no longer needed.
- Every call will request a new access token.

Providers receive a context containing the registration, current authorized client, and relevant attributes. Only a provider whose conditions are met executes its grant; the manager decides how to save/read the result.

### 4.2. Enable Only the Providers You Need

If a worker only uses client credentials:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
~~~

If a web app uses Authorization Code and refreshes tokens:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();
~~~

If a service can only refresh previously issued tokens:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .refreshToken()
        .build();
~~~

The last example is only useful when storage **already contains a valid authorized client and refresh token**; without an initial token-issuance provider, the manager cannot create a new authorization out of nothing.

**Principle:** the provider list reflects real use cases, not “turn everything on for convenience”. Even though enabling an extra provider does not immediately make a registration use the wrong grant, minimal configuration keeps the system understandable and reduces the risk of mistakes when adding registrations or changing token managers later.

### 4.3. ProviderBuilder and Priority Order

The builder normally chains child providers in call order. When a provider returns <code>null</code> because it **does not support the context** or needs no action, the composite provider can try the next provider.

Example configuration:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
~~~

Never view this list as a chain of “if authorization code fails → automatically switch to client credentials”. A token endpoint error such as <code>invalid_grant</code> is not a signal to **downgrade** to another grant. Which grant runs depends on `ClientRegistration` and context conditions, not arbitrary fallback after failure.

## 5. Configuring Providers with Clock Skew

Access tokens have an expiration timestamp, yet clocks across the Client, Authorization Server, and Resource Server may drift slightly. Spring Security supports configuring **clock skew** for token-refresh/issuance providers.

Example of proactive early refresh:

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .refreshToken(refresh -> refresh
            .clockSkew(Duration.ofSeconds(60)))
        .clientCredentials(credentials -> credentials
            .clockSkew(Duration.ofSeconds(60)))
        .build();
~~~

Here <code>Duration.ofSeconds(60)</code> is an illustrative choice, not a value every system must use. When a token is within the skew window of expiring, the provider can treat it as needing refresh/reissuance to avoid expiring mid-HTTP request.

Important points:

- Clock skew does not extend the actual lifetime of an access token.
- It does not guarantee the refresh token is still valid.
- It does not replace system clock synchronization.
- If skew is too large relative to token lifetime, the Client may request new tokens overly frequently.
- It does not provide complete safety against refresh races across multiple instances.

For systems with very short token lifetimes, tune skew and retry policies based on Authorization Server characteristics, network latency, and concurrency handling.

## 6. Complete Example A: OIDC Web App Using Authorization Code and Refresh Token

This is the use case where **a user logs in via browser**, and the application needs an access token to call an API on their behalf.

### 6.1. Spring Boot Dependencies

Example Servlet application using Spring Boot 3 and Spring Security 6:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

### 6.2. ClientRegistration for OIDC

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: portal-web
            client-secret: ${COMPANY_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - api.read
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

The issuer, Client ID, secret, scope, and URL here are illustrative data only. <code>api.read</code> must be supported by the provider, and the target API must accept tokens with the matching audience/scope. Never store real secrets in source code.

### 6.3. SecurityFilterChain for OAuth2 Login

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
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

<code>oauth2Login()</code> configures browser login: authorization request, redirect, callback, token exchange, and OIDC authentication. <code>oauth2Client()</code> provides the OAuth2 Client support needed when the app uses authorized clients to call downstream APIs in Servlet requests.

**Note:** For an application that only needs login, enabling <code>oauth2Client()</code> is not always necessary. Add it when your use case actually needs OAuth2 Client features during request processing.

### 6.4. Creating a Provider for the Web Authorized Client Manager

If you need to explicitly configure grant providers for web requests, you can define the manager explicitly:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class WebAuthorizedClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager webAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        var manager = new DefaultOAuth2AuthorizedClientManager(
            registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

This is a **custom configuration** example to illustrate `ProviderBuilder`. Spring Security/Spring Boot already provides suitable managers, services, or repositories in many cases, so **do not create a custom manager just to re-enable defaults**.

If the application has multiple <code>OAuth2AuthorizedClientManager</code> beans, select the exact bean via name/qualifier and verify the HTTP client actually uses the intended manager. Avoid creating multiple beans of the same type without clear disambiguation.

Important: configuring <code>.authorizationCode()</code> in the manager **does not replace** the OAuth2 Login filters. Users still initiate the flow via paths such as:

~~~text
/oauth2/authorization/company
~~~

After the callback:

~~~text
/login/oauth2/code/company
~~~

Spring Security saves the authorized client once the authorization code is successfully exchanged for tokens. When an API call is needed, the manager uses the existing authorized client and the <code>refreshToken()</code> provider if refresh conditions are met.

### 6.5. Retrieving the Authorized Client from a Controller

~~~java
package example.web;

import java.util.Map;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ClientInfoController {

    @GetMapping("/my/authorized-client")
    public Map<String, Object> info(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient client) {

        return Map.of(
            "registrationId",
            client.getClientRegistration().getRegistrationId(),
            "hasRefreshToken",
            client.getRefreshToken() != null,
            "hasAccessToken",
            client.getAccessToken() != null
        );
    }
}
~~~

This endpoint only returns metadata, **never the access token/refresh token**. This example assumes the authorized client resolves successfully; in a real application, handle authorization failures or missing authorized clients according to your UI/API design.

The <code>@RegisteredOAuth2AuthorizedClient</code> annotation resolves the authorized client by registration ID and principal in a Servlet context. It does not allow the application to bypass authorization, scopes/audience, or Resource Server policies.

### 6.6. Token Operational Steps After Login

~~~text
User logs in via Authorization Code
    → Client has OAuth2AuthorizedClient
        → Access token still valid
            → Call API with matching audience/scope
        → Access token near expiry and refresh token present
            → refreshToken() provider requests new token
            → Persist updated authorized client
        → Refresh fails / no refresh token
            → Policy requires re-authorization or returns appropriate error
~~~

Do not infer that having the <code>openid</code> scope means the access token works for business APIs. OIDC proves authentication to the Client; permission to call a Resource Server is a separate concern.

## 7. Complete Example B: Background Job Needing Only `client_credentials`

A background job uses service credentials to fetch aggregated data. It has no browser, HTTP session, OIDC Login callback, or interactive End-User.

### 7.1. Registration for the Service

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          nightly-reports:
            provider: service-auth
            client-id: reports-worker
            client-secret: ${REPORTS_WORKER_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          service-auth:
            token-uri: https://auth.example.org/oauth2/token
~~~

The Client must be permitted <code>client_credentials</code> by the Authorization Server; the <code>reports.read</code> scope must also be valid. This grant uses neither a redirect URI nor an authorization endpoint in the standard flow.

### 7.2. Manager Without an HTTP Request

For jobs, use <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> combined with <code>OAuth2AuthorizedClientService</code>:

~~~java
package example.security;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class BackgroundClientManagerConfig {

    @Bean("reportsAuthorizedClientManager")
    OAuth2AuthorizedClientManager reportsAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials(configurer -> configurer
                    .clockSkew(Duration.ofSeconds(30)))
                .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

Differences from the web manager:

- Does not require <code>HttpServletRequest</code>/<code>HttpServletResponse</code>.
- Can run inside a scheduled job or service layer without a browser.
- Uses a storage service to hold authorized clients by registration/principal.
- Enables only **<code>clientCredentials()</code>**, without adding authorization code/refresh token when the use case does not need them.

### 7.3. Calling the Manager from a Service

~~~java
package example.jobs;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class ReportsTokenService {

    private final OAuth2AuthorizedClientManager manager;

    public ReportsTokenService(
            @Qualifier("reportsAuthorizedClientManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public String accessToken() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("nightly-reports")
                .principal("reports-worker-runtime")
                .build();

        OAuth2AuthorizedClient authorizedClient = manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "Reports client could not be authorized");
        }
        return authorizedClient.getAccessToken().getTokenValue();
    }
}
~~~

<code>reports-worker-runtime</code> is a **synthetic principal**, acting as the storage key for the job's authorized client. It is not an OIDC user account.

Returning the <code>String</code> token here only illustrates how to obtain credentials in a server-side service; **never expose this method through a controller** and never write tokens to logs. In a real application, integrate the manager into an appropriate HTTP client/interceptor so tokens do not pass unnecessarily through many code layers.

### 7.4. Why Is `refreshToken()` Omitted?

The Client Credentials Grant can normally obtain a new token using <code>grant_type=client_credentials</code> itself when the old access token expires. Many Authorization Servers do not issue refresh tokens for this grant.

Thus a manager enabling only <code>clientCredentials()</code> is sufficient for the common case. If a particular provider has a custom mechanism, follow its supported documentation/standard rather than assuming refresh tokens are always needed.

## 8. Example C: An Application with Both Web Login and Service-to-Service

In a large system, both kinds of `ClientRegistration` may exist:

~~~text
company-login:
  grant = authorization_code
  goal = log users in and call APIs on behalf of the user

reports-job:
  grant = client_credentials
  goal = backend calls APIs with service permissions
~~~

There are two strategies:

**Strategy 1 — Use separate managers per context.** The web manager enables authorization code + refresh token, while the service manager enables client credentials. This clarifies boundaries and simplifies storage/lifecycle management.

**Strategy 2 — Use one composite provider containing multiple grants.** This can work if the manager/context genuinely supports all registrations used. However, a Servlet-request-based manager is still unsuitable for background jobs without a request, even if the provider list contains <code>clientCredentials()</code>.

Example of two managers with explicit bean names:

~~~java
@Bean("webAuthorizedClientManager")
OAuth2AuthorizedClientManager webManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository repository) {

    var provider = OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();

    var manager = new DefaultOAuth2AuthorizedClientManager(
        registrations, repository);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}

@Bean("serviceAuthorizedClientManager")
OAuth2AuthorizedClientManager serviceManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService service) {

    var provider = OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();

    var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        registrations, service);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

This is an **alternative configuration snippet** to the manager beans in earlier sections. When placing it into a real class, add imports from the corresponding examples. Do not declare every example from this lesson in the same project to avoid bean duplication/ambiguity.

When injecting a manager, use <code>@Qualifier</code> or an explicit selection mechanism:

~~~java
public SomeService(
    @Qualifier("serviceAuthorizedClientManager")
    OAuth2AuthorizedClientManager manager) {
    this.manager = manager;
}
~~~

Never attach a user token to a job needing a service token out of convenience, nor use a client credentials token in place of End-User permissions.

## 9. What OAuth2AuthorizedClientProviderBuilder Does Not Do Automatically

### 9.1. Does Not Create ClientRegistration

To use a grant, the application still needs a `ClientRegistrationRepository` containing the matching registration. Example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-job:
            client-id: example-client-id
            client-secret: ${REPORTS_SECRET}
            authorization-grant-type: client_credentials
            provider: service-auth
        provider:
          service-auth:
            token-uri: https://auth.example.org/token
~~~

Adding <code>.clientCredentials()</code> to `ProviderBuilder` neither creates the <code>reports-job</code> registration nor registers the Client with the Authorization Server.

### 9.2. Does Not Start OAuth2 Login in the Browser

Authorization Code requires frontend redirects, state/correlation, PKCE when applicable, and callbacks. In Servlet applications, these responsibilities are handled by the OAuth2 Login/Client filter configuration. Calling <code>manager.authorize()</code> from a method without a browser will not open an IdP page.

### 9.3. Does Not Automatically Turn an Expired Token into a Valid Token

Refreshing a token depends on:

- Matching grant and enabled provider.
- Existing authorized client and current token present in storage.
- Valid refresh token if using the refresh grant.
- Authorization Server accepting the request.
- Manager saving the updated token state per configuration.

Merely adding <code>.refreshToken()</code> does not guarantee every token can be refreshed.

### 9.4. Does Not Grant Permission to Call Arbitrary APIs

The provider receives tokens from the Authorization Server, yet the Resource Server still must verify audience, scopes, issuer, expiration, and business authorization. Never treat a token returned by the manager as proof that the user has access to every endpoint.

### 9.5. Does Not Replace Storage and Principal Isolation

Providers know how to obtain tokens, not where to store them. If the manager uses inappropriate storage, or principal names collide across tenants, tokens can still get mixed up.

## 10. Relationship with OAuth2AuthorizeRequest and Context Attributes

When calling the manager, code usually constructs:

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("nightly-reports")
        .principal("reports-worker-runtime")
        .build();

OAuth2AuthorizedClient client = manager.authorize(request);
~~~

Key details:

| Component | Function |
|---|---|
| <code>clientRegistrationId</code> | Selects `ClientRegistration`, thereby determining grant type and token endpoint |
| <code>principal</code> | Distinguishes the authorized client context |
| Existing authorized client | Supplies current tokens to check expiry/refresh |
| Attributes/context | Extra data when a specific grant/extension requires it |

<code>OAuth2AuthorizeRequest</code> can also carry extra attributes depending on API/version. The manager has a mechanism to create <code>OAuth2AuthorizationContext</code> and map relevant attributes. This is especially important when using custom providers or specialized grants.

**For the three grants in this lesson, do not invent attributes not specified by Spring Security or a provider.** For client credentials, registration ID and synthetic principal are normally enough; for refresh, an authorized client containing a refresh token is required; for Servlet authorization code, the browser flow is handled by filters.

### 10.1. Synthetic Principals Must Not Depend on Untrusted Input

Sensible pattern:

~~~java
.principal("reports-worker-runtime")
~~~

Dangerous pattern:

~~~java
.principal(request.getParameter("user"))
~~~

If token storage uses principal name as its key, letting the browser pick the principal can allow access to an authorized client that does not belong to the caller. For End-Users, always use the authenticated `Authentication`; for services, use a backend-controlled principal key.

### 10.2. Multi-Tenant Systems May Need Separate Registrations

Suppose one backend serves two tenants:

~~~text
tenant-a → client ID A, scopes A, token A
tenant-b → client ID B, scopes B, token B
~~~

If credentials, issuer, or audience differ, you need separate `ClientRegistration` entries or a carefully designed dynamic registration strategy. Do not just change the principal name and expect the wrong `ClientRegistration` to emit a tenant-appropriate token.

Principal names must also be namespaced so authorized clients of two tenants never overwrite each other when sharing storage.

## 11. Customizing Providers or Using a Custom Provider

For typical needs, the builder with built-in methods is sufficient. If the Authorization Server supports a grant extension already supported by that Spring Security version, or the project has a custom <code>OAuth2AuthorizedClientProvider</code>, you can compose it into the composite provider.

Pattern:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .refreshToken()
        .clientCredentials()
        .provider(customProvider)
        .build();
~~~

Here <code>customProvider</code> is an instance implementing <code>OAuth2AuthorizedClientProvider</code> that has been separately defined and controlled; the snippet only illustrates the **extension point**, without creating a custom provider. Only add an extension when the corresponding grant is supported by the Authorization Server with clear security rules.

### 11.1. The OAuth2AuthorizedClientProvider Contract

Core interface:

~~~java
public interface OAuth2AuthorizedClientProvider {
    OAuth2AuthorizedClient authorize(
        OAuth2AuthorizationContext context);
}
~~~

Meaning:

- Return <code>OAuth2AuthorizedClient</code> when the provider performed authorization/reauthorization or produced an appropriate result.
- Return <code>null</code> when the provider does not support the grant/context or reauthorization is unnecessary/impossible per contract.
- Throw an appropriate exception when grant execution actually fails.

A custom provider must honor these conditions. Never fabricate dummy tokens when the Authorization Server rejects a request; never catch all errors and return <code>null</code> so another provider issues a token using a weaker grant.

### 11.2. When Is a Custom Provider Needed?

Examples can include:

- An extension grant not built into the current Spring Security version.
- Specialized behavior mutually supported by both the Authorization Server and Client per a standard/extension.
- Extracting credentials or context attributes via a safely defined mechanism.

Never use a custom provider to skip OIDC validation, replace the Authorization Code callback with custom hacks, or let Clients obtain tokens using a browser-supplied principal. For requirements such as custom HTTP headers or custom token response bodies, **customizing the token response client** is often better than writing an entire new provider.

## 12. Token Storage and Authorization Success/Failure

### 12.1. How Does the Manager Save Results?

When a provider issues a new token or refreshes successfully, the manager typically uses a success handler to save the new <code>OAuth2AuthorizedClient</code>:

~~~text
OAuth2AuthorizedClientManager
  → OAuth2AuthorizedClientProvider.authorize(context)
  → New OAuth2AuthorizedClient
  → AuthorizationSuccessHandler
  → OAuth2AuthorizedClientService or Repository
~~~

In default managers, Spring Security configures a handler to persist authorized clients matching the manager type. If the application overrides the success handler, ensure persistence behavior still runs when needed rather than accidentally keeping the new token only in a single request's return variable.

### 12.2. Failure Handler and `invalid_grant`

When a refresh token is rejected, the Token Endpoint can return <code>invalid_grant</code> because the token expired, was revoked, or was already consumed under rotation.

Default managers have failure handling that can remove invalid authorized clients on certain error codes (such as <code>invalid_grant</code>), depending on the manager and configuration. Removing it prevents repeated refresh attempts with a dead token.

Do not catch every <code>OAuth2AuthorizationException</code> and wipe out all authorized clients. Timeouts, HTTP 502s, or connection failures do not prove the refresh token was revoked; misclassifying them can unnecessarily disrupt user sessions.

### 12.3. Differences Between Service and Repository

| Component | Primary Lookup Key | Where Typically Used |
|---|---|---|
| <code>OAuth2AuthorizedClientService</code> | registration ID + principal name | Backend services, background managers |
| <code>OAuth2AuthorizedClientRepository</code> | registration ID + Authentication + HTTP request | Servlet web requests |
| <code>InMemoryOAuth2AuthorizedClientService</code> | Tokens in single-process memory | Demos, local dev, single-instance |
| <code>JdbcOAuth2AuthorizedClientService</code> | Tokens in a database using matching schema | Applications needing persistence |

Do not confuse <code>OAuth2AuthorizedClientService</code> with <code>ClientRegistrationRepository</code>, nor with <code>HttpSessionOAuth2AuthorizationRequestRepository</code> which stores state/PKCE **before the callback**.

### 12.4. Logout and Revocation Are Different Things

Logging out an HTTP session, deleting an authorized client from the service, and revoking tokens at the Authorization Server are not automatically equivalent. A refresh token can remain in persistent storage after a user logs out if the application lacks a cleanup policy.

When revocation is needed:

- Delete the local authorized client for the exact registration and principal.
- Call the token revocation endpoint if supported by the provider and required by policy.
- Invalidate the session/`SecurityContext` appropriately.
- Evaluate permissions at the Resource Server or domain service when permissions can be revoked outside token lifetimes.

## 13. Common Pitfalls When Configuring Grants

### 13.1. Enabling `clientCredentials` When Registration Is `authorization_code`

~~~yaml
registration:
  company:
    authorization-grant-type: authorization_code
~~~

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
~~~

The manager cannot use the client credentials provider to execute a proper authorization code flow for this registration. You must enable the grant provider matching the registration and use case. For web login, the Authorization Code Flow also needs the corresponding filters/redirects/callbacks.

### 13.2. Enabling Only `refreshToken` When No Authorized Client Exists Yet

The refresh token provider requires an authorized client that **already has a refresh token**. If authorization has never occurred and no token is stored, it cannot create a refresh token from Client ID/secret.

### 13.3. Using `DefaultOAuth2AuthorizedClientManager` in a Background Job

The web manager relies on the Servlet context. In a scheduled job without an `HttpServletRequest`, choose <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>. Merely adding <code>clientCredentials()</code> to the web manager does not remove its dependency on Servlet requests.

### 13.4. Thinking `OAuth2AuthorizedClientProviderBuilder` Is a `ClientRegistration` Builder

Two distinct APIs:

~~~java
ClientRegistration.withRegistrationId("company")
// describes registered Client configuration

OAuth2AuthorizedClientProviderBuilder.builder()
// builds providers that handle authorization grants
~~~

Do not use the grant builder to configure issuer URIs, redirect URIs, or client secrets. That metadata belongs to `ClientRegistration`.

### 13.5. Adding Refresh Grant Unnecessarily for Client Credentials

Client credentials normally requests a new token when needed without relying on refresh tokens. If the provider does not issue refresh tokens, adding <code>refreshToken()</code> gives no benefit and can cause confusion about the flow.

### 13.6. Using a User Token as a Service Token

An access token from OIDC Login may be issued for UserInfo or APIs matching the user's scopes/audience. Do not blindly send that token to an internal service if that API expects **service credentials**. When acting on behalf of a user is required, design delegation with audience/delegation mechanisms supported by the OP and API.

### 13.7. Ignoring Token Refresh Concurrency

If two requests on two nodes refresh the same token simultaneously and the OP enables refresh token rotation, one request can cause the other to fail with <code>invalid_grant</code>. You need an appropriate persistence/concurrency/handling strategy; a single-JVM lock is insufficient for a cluster.

### 13.8. Blindly Retrying Token Requests

Authorization codes may be single-use. If the token endpoint times out after the server received the request, the Client does not know whether the code was consumed. Do not auto-retry infinitely like an idempotent GET; classify errors and restart the authorization flow when necessary.

## 14. Security When Selecting Grants and Using Tokens

### 14.1. Principle of Least Privilege

Each `ClientRegistration` should request only the scopes required by its workload:

~~~text
web-login:
    openid, profile, api.read

reports-job:
    reports.read

billing-job:
    billing.write (only when genuinely needed)
~~~

Do not use one confidential client with overly broad scopes for both user logins and privileged jobs just to reduce the number of registrations.

### 14.2. Separating End-Users and Services

| Scenario | Usually Appropriate Grant | Who Is Represented? |
|---|---|---|
| User logs in via OIDC | Authorization Code + PKCE as configured | End-User |
| Calling API on behalf of authorized user | Authorized client from login, refresh if available | End-User |
| Worker calling API with service permissions | Client Credentials | Client/service |
| User must re-login because refresh is no longer valid | New Authorization Code Flow | End-User |

Client Credentials **does not allow a service to impersonate a specific user** just because a <code>principalName</code> was supplied in <code>OAuth2AuthorizeRequest</code>.

### 14.3. Protecting Credentials and Tokens

- Never commit <code>client-secret</code> to source control; use a secret store or environment variables.
- Only send token requests over HTTPS with TLS verification.
- Never log access tokens, refresh tokens, client secrets, authorization codes, PKCE verifiers, or HTTP `Authorization` headers.
- Never return access/refresh tokens to the browser when the backend acts as a confidential Client.
- Protect token storage with least-privilege permissions, encryption-at-rest, and appropriate auditing.
- Establish cleanup/revocation policies when users log out, accounts are locked, or services have permissions revoked.

### 14.4. Checking Audience and Scope

<code>OAuth2AuthorizedClient</code> holds a token issued to the Client; it does not prove every API accepts that token. Each Resource Server must verify the exact issuer, audience, expiration, scopes, and internal authorization conditions.

### 14.5. Multi-Tenant and Principal Isolation

When multiple tenants share storage, avoid:

~~~text
tenant-a principal=service
tenant-b principal=service
same registrationId
~~~

If two workloads must keep separate tokens, use separate registrations or namespaced principals depending on grant and architecture. Never use a browser-supplied tenant ID to select a privileged token. Tenant selection rules must rely on trusted authentication and policy.

## 15. Common Issues and How to Narrow Them Down

| Symptom | Common Cause | How to Handle |
|---|---|---|
| <code>manager.authorize()</code> returns null or cannot issue token | Grant provider does not support registration/context, missing authorized client, or invalid request | Check registration grant type, principal, provider list, and flow |
| <code>authorizationCode()</code> enabled yet job fails to log in | No browser/redirect/callback | Use client credentials for jobs without an End-User |
| Web login succeeds yet refresh never happens | No refresh token, provider not enabled, or token not close enough to expiry | Check refresh token, clock skew, and which manager is used |
| <code>invalid_client</code> at Token Endpoint | Wrong Client ID/secret or authentication method | Cross-check configuration with Authorization Server |
| <code>unauthorized_client</code> | Client not permitted to use grant | Enable the corresponding grant on the Authorization Server |
| <code>unsupported_grant_type</code> | Provider does not support grant or malformed request | Check registration and OP metadata/docs |
| <code>invalid_scope</code> | Scope not granted or incompatible with grant | Adjust scopes and policy |
| <code>invalid_grant</code> on refresh | Refresh token expired, revoked, or reused | Check rotation, cleanup, and reauthorization |
| Access token still gets 401 from API | Wrong audience/issuer, expired, or revoked | Check Resource Server and actual token |
| Job works in dev yet fails on multi-node | Unshared in-memory storage or refresh race | Design persistent store and concurrency |
| Two manager beans cause ambiguity | Missing <code>@Qualifier</code>/primary | Name clearly and inject the right manager |
| After custom success handler, refreshed tokens are not saved | Custom handler fails to save authorized client | Preserve persistence logic |
| Logout leaves refresh token in DB | Missing cleanup/revocation policy | Delete local authorized client, revoke token if needed |
| Service A uses Service B's token | Principal/registration key does not separate workloads | Partition tokens by registration/principal/tenant |

### 15.1. Troubleshooting Workflow

~~~text
Does ClientRegistration exist?
    |
    v
Does authorizationGrantType match the use case?
    |
    v
Does OAuth2AuthorizeRequest have the right principal/context?
    |
    v
Which Manager is being used (web/service)?
    |
    v
Did ProviderBuilder enable the matching grant?
    |
    v
Does Storage contain the matching authorized client/refresh token?
    |
    v
Does the Token Endpoint accept the Client and grant?
    |
    v
Did the Manager save the updated authorized client?
    |
    v
Does the Resource Server accept the audience/scope?
~~~

When debugging, you can enable controlled logging in development environments:

~~~yaml
logging:
  level:
    org.springframework.security.oauth2.client: DEBUG
~~~

Log verbosity can vary by version. Do not enable raw token request/response dumping in production; redact tokens, secrets, and `Authorization` headers from logs/telemetry.

## 16. Exercises and Scenarios

### Exercise 1 — Choosing Providers for a Background Job

A batch job runs nightly with no HTTP request or user. `ClientRegistration` has <code>authorization-grant-type=client_credentials</code>.

**Question:** Which providers should be enabled and which manager should be used?

**Hint:** <code>clientCredentials()</code> and <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>; a stable synthetic principal, namespaced if tenants/workloads must be separated.

### Exercise 2 — Web Login and Refresh

A Servlet application uses the OIDC Authorization Code Flow and stores authorized clients. The OP may issue refresh tokens.

**Question:** Reasonable provider list configuration?

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();
~~~

**Explanation:** <code>oauth2Login()</code> handles redirect/callback; the manager can refresh tokens when a valid refresh token is present. Do not assume a refresh token exists in every case.

### Exercise 3 — Wrong Grant

Registration <code>company</code> has <code>authorization_code</code>, yet the manager only has <code>clientCredentials()</code>.

**Question:** Will the Client Credentials Provider automatically pick the authorization code grant?

**Answer:** No. You must use providers matching the grant, and login requires a browser flow. The builder does not alter `ClientRegistration`.

### Exercise 4 — Refresh Without a Token

A manager enabling only <code>refreshToken()</code> is called for the first time for a registration that was never authorized.

**Answer:** There is no refresh token to execute the grant; an appropriate initial token-issuance flow is needed first, after which refresh becomes possible if the server issues a refresh token.

### Exercise 5 — User and Service Access Tokens

Users log in via OIDC while a worker runs client credentials. A developer uses the same principal name <code>default</code> for both, storing them in a custom token store keyed by principal.

**Question:** Is this design safe?

**Answer:** No. Tokens can be overwritten or have mismatched contexts, especially if registration ID is ignored. Use proper storage abstractions, partition by registration/principal, and separate user tokens from service tokens.

### Exercise 6 — Refresh Token Rotation

Two nodes read the old refresh token and try to refresh concurrently; the second node receives <code>invalid_grant</code>.

**Question:** What could cause this and what needs to be done?

**Answer:** The OP may be using refresh token rotation. A multi-node-safe storage/concurrency strategy is needed, handling failures safely without infinitely retrying the stale token.

### Exercise 7 — Reading and Explaining a Provider Configuration

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .refreshToken()
        .clientCredentials()
        .build();
~~~

**Question:** What can this configuration do, and what can it not do?

**Answer:** It can refresh an authorized client that already has a refresh token, or issue a client credentials token for a matching registration. It cannot initiate an OIDC Authorization Code Login in the browser because neither the authorization code provider is enabled nor are OAuth2 Login filters configured.

### Exercise 8 — Controlled Practice

1. Create registration <code>nightly-reports</code> using client credentials and a read-only scope.
2. Create an <code>OAuth2AuthorizedClientService</code> for the test environment.
3. Create an <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code> with <code>clientCredentials()</code>.
4. Call the manager via <code>OAuth2AuthorizeRequest.withClientRegistrationId(...).principal(...)</code>.
5. Inspect whether an authorized client, registration ID, principal, and expiry exist; **do not print the token value**.
6. Call the manager again to observe reuse of a valid token and reissuance near expiry per the provider.
7. Add a separate OIDC Login registration; distinguish the web manager from the service manager.
8. Describe the reasons why the manager fails to authorize when secret, grant type, scope, or token endpoint is wrong.

## 17. Key Takeaways

- **<code>OAuth2AuthorizedClientProviderBuilder</code>** builds a composite provider from the grants that <code>OAuth2AuthorizedClientManager</code> is permitted to handle.
- **<code>authorizationCode()</code>** serves grants with an End-User and browser flow; in Servlet apps, <code>oauth2Login()</code> still handles redirects/callbacks, state, and OIDC authentication.
- **<code>refreshToken()</code>** only refreshes when an authorized client already exists with a valid refresh token and refresh conditions are met; it does not grant refresh tokens itself.
- **<code>clientCredentials()</code>** is for server-to-server calls without an End-User; typically paired with <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>.
- The provider list must match **ClientRegistration.authorizationGrantType**, the chosen manager, and Authorization Server policies. Enabling an extra provider does not convert a registration to another grant.
- **<code>DefaultOAuth2AuthorizedClientManager</code>** suits Servlet contexts; **<code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>** suits jobs/services without an HTTP request.
- Storage, refresh policies, principal keys, audience/scopes, and token revocation are **separate** architectural responsibilities; `ProviderBuilder` does not solve them on its own.
- Use minimal configuration per use case, keep credentials safe, and never equate a service token with a token representing a human user.

### References

- **Spring Security Reference — OAuth2 Client:** <code>OAuth2AuthorizedClientManager</code>, <code>OAuth2AuthorizedClientProvider</code>, <code>OAuth2AuthorizedClientProviderBuilder</code>, built-in providers.
- **Spring Security Reference — OAuth2 Login (Servlet):** Authorization Code Flow, callbacks, and authorized client persistence.
- **Spring Security Java API:** <code>OAuth2AuthorizedClientProviderBuilder</code>, <code>DefaultOAuth2AuthorizedClientManager</code>, <code>AuthorizedClientServiceOAuth2AuthorizedClientManager</code>, <code>OAuth2AuthorizeRequest</code>.
- **Spring Security Java API:** <code>OAuth2AuthorizedClient</code>, <code>OAuth2AuthorizedClientService</code>, <code>OAuth2AuthorizedClientRepository</code>, <code>OAuth2AuthorizedClientProvider</code>.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code, Client Credentials, and Refresh Token grants.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** Authorization Code Flow and PKCE.
- **RFC 7009 — OAuth 2.0 Token Revocation:** token revocation mechanism.
- **OpenID Connect Core 1.0:** OIDC Authorization Code Flow, ID Token, and UserInfo.
