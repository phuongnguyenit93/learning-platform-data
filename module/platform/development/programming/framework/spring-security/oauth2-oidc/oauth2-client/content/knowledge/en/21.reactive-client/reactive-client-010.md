# 21.10. Selecting an Authorized Client or Registration per WebClient Request

## 1. Why Must Every WebClient Request Select the Right OAuth2 Client?

In a **Spring Security OAuth 2.0 OIDC Client** application built with **Spring WebFlux**, a single `WebClient` may call multiple Resource Servers. Each API may require an Access Token issued for a different **client registration**, **principal**, **audience**, and **scope**.

For example, a portal lets employees log in via OIDC while also running a backend job reading system metrics:

~~~text
                      +-- Reports API:
                      |    delegated user Access Token
Browser -> WebFlux ---+
                      +-- Billing API:
                      |    a different delegated user Access Token
                      |
Scheduled worker ------+-- Metrics API:
                           Client Credentials Access Token
~~~

All three HTTP requests need `Authorization: Bearer ...`, yet **you cannot reuse one token for every API**. Employee Alice's token must never be mixed up with Bob's; the Metrics API token is not accepted by the Reports API; and the backend's Client Credentials token does not represent an end-user.

Spring Security helps you select credentials for **each outbound request** via `ServerOAuth2AuthorizedClientExchangeFilterFunction`. The two core options are:

1. **Specify an existing `OAuth2AuthorizedClient`:** use the `oauth2AuthorizedClient(authorizedClient)` request attribute.
2. **Specify a registration name:** use the `clientRegistrationId("registration-name")` request attribute, letting `ReactiveOAuth2AuthorizedClientManager` locate, issue, or refresh the appropriate authorized client.

Although both end with WebClient sending a Bearer Token, they express **different intents**: picking a *specific authorization result* vs picking an *OAuth2 client configuration* and letting the manager handle the token lifecycle.

### Learning Outcomes

After this lesson, you will be able to:

- Explain the differences among `ClientRegistration`, `OAuth2AuthorizedClient`, and `Authentication`.
- Configure `ServerOAuth2AuthorizedClientExchangeFilterFunction` on a Reactive WebClient.
- Select an authorized client directly or select a registration per request without leaking tokens across users.
- Distinguish `DefaultReactiveOAuth2AuthorizedClientManager` and `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.
- Design requests for **OIDC user-delegated tokens** and **Client Credentials service tokens**.
- Recognize the risks of enabling `setDefaultOAuth2AuthorizedClient(true)`, `setDefaultClientRegistrationId(...)`, or letting users pick arbitrary URLs/registrations.
- Handle expired tokens, OAuth2 errors, and HTTP 401/403 responses according to client and Resource Server responsibilities.

> **Scope:** Spring WebFlux server/reactive OAuth2 Client with `ReactiveOAuth2AuthorizedClientManager` and `ServerOAuth2AuthorizedClientExchangeFilterFunction`. This is **not** `ServletOAuth2AuthorizedClientExchangeFilterFunction` used in Servlet/MVC applications.

## 2. Participating Components

### 2.1. Configuration vs Authorization Result

| Component | What does it hold? | Effect |
| --- | --- | --- |
| `ClientRegistration` | `registrationId`, client ID, client authentication method, grant type, token URI, scopes, redirect URI... | Defines **how the client is issued tokens** |
| `OAuth2AuthorizedClient` | `ClientRegistration`, `principalName`, Access Token, optional Refresh Token | Records **a client authorized for a principal** |
| `ReactiveClientRegistrationRepository` | `ClientRegistration` entries | Looks up configurations by registration ID |
| `ServerOAuth2AuthorizedClientRepository` | Authorized clients bound to `ServerWebExchange` and `Authentication` | Load/save/remove in reactive web flows |
| `ReactiveOAuth2AuthorizedClientService` | Authorized clients keyed by `registrationId + principalName` | Load/save/remove without an HTTP exchange |
| `ReactiveOAuth2AuthorizedClientManager` | Coordinates providers, loads/saves tokens, runs authorization/re-authorization | Returns the appropriate authorized client |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | WebClient filter using authorized client/manager | Attaches `Authorization: Bearer ...` to outbound requests |
| `Resource Server` | API with its own authorization policy | Validates tokens and decides whether to accept the HTTP request |

Example:

~~~text
ClientRegistration:
  registrationId = company-oidc
  clientId = portal-reactive
  authorizationGrantType = authorization_code

OAuth2AuthorizedClient A:
  registrationId = company-oidc
  principalName = alice
  accessToken = <TOKEN_ALICE>

OAuth2AuthorizedClient B:
  registrationId = company-oidc
  principalName = bob
  accessToken = <TOKEN_BOB>
~~~

**Registration ID is not a username.** One registration can hold tokens for many principals; the service store's logical key is typically the pair `(clientRegistrationId, principalName)`.

### 2.2. ID Token, Access Token, and Refresh Token

With OIDC Login:

- **ID Token** proves OIDC authentication claims to the client per issuer, audience, expiry, and related checks.
- **Access Token** accesses authorized resources; the filter uses it as the Bearer Token when calling APIs.
- **Refresh Token**, when issued, obtains a fresh Access Token at the Token Endpoint; never send it to a Resource Server.

Never pass `OidcUser.getIdToken().getTokenValue()` as `Authorization: Bearer` to call an API just because the ID Token also happens to be a JWT.

With Client Credentials, the token represents the **service/client identity**, not an OIDC-logged-in user; there is normally no end-user ID Token.

## 3. Flow for Selecting a Token per Request

~~~mermaid
flowchart TD
    A["Business code creates WebClient request"] --> B["Does request attributes have OAuth2AuthorizedClient?"]
    B -->|Yes| C["Select specific authorized client"]
    B -->|No| D["Is clientRegistrationId present?"]
    D -->|Yes| E["Select ClientRegistration config"]
    D -->|No| F["Check default client policy if configured"]
    C --> G["ReactiveOAuth2AuthorizedClientManager"]
    E --> G
    F --> G
    G --> H["Look up authorized client by registration/principal"]
    H --> I{"Usable token exists?"}
    I -->|Yes| J["Reuse token"]
    I -->|Missing / needs renewal| K["AuthorizedClientProvider acquires/refreshes"]
    K --> L["Save updated authorized client"]
    L --> J
    J --> M["WebClient filter attaches Bearer Access Token"]
    M --> N["Call targeted Resource Server"]
    N --> O["API enforces token validation + authorization"]
~~~

This is a logical model. **Not every call to the manager creates a new token.** Depending on provider and grant, the manager may reuse an existing record, acquire a new token, refresh, or be unable to authorize in the current context.

### 3.1. Request Attributes Are Not Sent Over the Wire

When you write:

~~~java
.attributes(clientRegistrationId("reports-api"))
~~~

the value is stored inside **WebClient `ClientRequest` internal attributes** for the filter to read. It is not automatically placed into the URL, JSON request body, or HTTP headers sent to the Resource Server.

This lets a request choose a client without manually building Bearer strings. Still, if the application reads the registration from a browser query parameter and passes it straight into attributes, the **token-selection authorization** vulnerability remains. Request attributes are a programming mechanism, not an access control check.

## 4. Attaching ServerOAuth2AuthorizedClientExchangeFilterFunction to WebClient

### 4.1. Using the Right Class on a Reactive Server

Imports:

~~~java
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;
~~~

Creating the filter:

~~~java
ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        authorizedClientManager);

WebClient webClient = WebClient.builder()
    .filter(oauth2)
    .build();
~~~

Here, `authorizedClientManager` is a **`ReactiveOAuth2AuthorizedClientManager`** supplied by Spring or configured by the application. The filter operates at the outbound HTTP client layer; the manager drives the authorized-client lifecycle.

### 4.2. WebClient Bean in Spring Configuration

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ResourceApiWebClientConfig {

    @Bean
    WebClient resourceApiWebClient(
            ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                authorizedClientManager);

        return WebClient.builder()
            .baseUrl("https://api.example.net")
            .filter(oauth2)
            .build();
    }
}
~~~

Defining the bean alone is not enough for requests to get the right token: each request still needs an `OAuth2AuthorizedClient`, `clientRegistrationId`, or a **deliberately configured** default, plus the proper principal context.

### 4.3. Constructing via Repositories

The filter also has a constructor accepting:

~~~java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    clientRegistrationRepository,
    authorizedClientRepository);
~~~

Where:

- `clientRegistrationRepository` is `ReactiveClientRegistrationRepository`.
- `authorizedClientRepository` is `ServerOAuth2AuthorizedClientRepository`.

This constructor is used when letting the filter coordinate with a repository-backed manager setup. Once your app needs custom providers, grants, failure handlers, or stores, the **manager constructor** centralizes configuration cleanly.

**Subtle difference often missed:** the repositories constructor sets up a default handler that removes an authorized client when the Resource Server returns matching OAuth2 Bearer errors; the `ReactiveOAuth2AuthorizedClientManager` constructor **does not automatically install** this handler. Section 16 explains the implications and how to configure it.

## 5. Approach 1 — Selecting a Specific OAuth2AuthorizedClient

### 5.1. Static Helper oauth2AuthorizedClient(...)

Spring Security provides:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;
~~~

Once you hold an `OAuth2AuthorizedClient` for the right principal and registration:

~~~java
Mono<String> response = webClient.get()
    .uri("/v1/profile")
    .attributes(oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class);
~~~

**Meaning:** this HTTP request must use the **exact authorized client** selected by code. There is no need to also pass the registration ID string on the same request just to repeat the same intent.

The `authorizedClient` object must come from a trusted backend source, such as an authorized-client repository/service or a Spring Security argument resolver. Never construct it from a browser-sent Access Token and bind it to an arbitrary principal.

### 5.2. When Is This Approach Suitable?

Examples:

- A controller already has the authorized client injected for a fixed registration and current user.
- The app needs to select one specific OAuth2 connection among several integrations authorized by the user.
- A service just loaded an authorized client using a verified principal.
- You need to send the exact authorized client carrying a workflow's granted scopes.

Advantage: clear intent, less reliance on defaults or registration names scattered across layers.

Important caveat: **never store `OAuth2AuthorizedClient` in a singleton field** to reuse across users. The object holds lifecycle-bound, principal-scoped, scope-bound credentials; it can go stale or belong to another account.

### 5.3. Example Loading an Authorized Client from the Reactive Service

`ReactiveOAuth2AuthorizedClientService` provides a reactive API:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import reactor.core.publisher.Mono;

Mono<OAuth2AuthorizedClient> selected =
    authorizedClientService.loadAuthorizedClient(
        "company", principalName);
~~~

Then use it in the chain:

~~~java
return authorizedClientService
    .<OAuth2AuthorizedClient>loadAuthorizedClient(
        "company", currentPrincipalName)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No OAuth2 authorized client found")))
    .flatMap(client -> webClient.get()
        .uri("/v1/profile")
        .attributes(oauth2AuthorizedClient(client))
        .retrieve()
        .bodyToMono(String.class));
~~~

This example **illustrates structure**; it assumes `authorizedClientService`, `webClient`, and `currentPrincipalName` are resolved server-side. Never take a principal name sent arbitrarily by the browser.

**Distinction:** `loadAuthorizedClient(...)` returning a record only proves the record exists, not that the Access Token is still accepted by the Resource Server. The filter/manager and API still govern token lifecycle and authorization; do not bypass them.

### 5.4. Never Attach Both an Authorized Client and a Registration Ambiguously

Anti-example of conflicting intent:

~~~java
webClient.get()
    .uri("/v1/profile")
    .attributes(oauth2AuthorizedClient(alicesClient))
    .attributes(clientRegistrationId("billing-service"))
    .retrieve();
~~~

Here the code passes Alice's authorized client while also specifying the billing registration. **Never rely on internal filter precedence to resolve this conflict.** A single request should have **one unambiguous client-selection strategy**; avoid letting service/tracing/filter layers attach contradictory attributes.

## 6. Approach 2 — Selecting clientRegistrationId per Request

### 6.1. Static Helper clientRegistrationId(...)

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
~~~

Example:

~~~java
Mono<String> response = webClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("reports-api"))
    .retrieve()
    .bodyToMono(String.class);
~~~

The filter sees `reports-api`, the manager looks up the matching `ClientRegistration`, and then loads or acquires an `OAuth2AuthorizedClient` for the active principal.

### 6.2. Benefits of Selecting by Registration

A WebClient call site does not need to know token values, token expiry, or Refresh Tokens. It simply declares:

> "This request needs authorization through the `reports-api` registration."

The manager can:

1. Load a saved authorized client by `registrationId + principalName`.
2. Reuse the Access Token if still valid.
3. Refresh the Access Token if the grant and Refresh Token allow.
4. Execute the Client Credentials grant to acquire a fresh token for a machine client.
5. Persist the updated `OAuth2AuthorizedClient` per policy.

There is no guarantee every registration can authorize in every context. For example, Authorization Code flow needs browser/authorization context; a scheduled job cannot walk through a user consent redirect.

### 6.3. Choosing Among Multiple Registrations

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-api:
            provider: company-auth
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [reports.read]
          billing-api:
            provider: company-auth
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [billing.read]
        provider:
          company-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

Calling each respective API:

~~~java
Mono<String> reports = webClient.get()
    .uri("https://reports.example.net/v1/reports")
    .attributes(clientRegistrationId("reports-api"))
    .retrieve()
    .bodyToMono(String.class);

Mono<String> invoices = webClient.get()
    .uri("https://billing.example.net/v1/invoices")
    .attributes(clientRegistrationId("billing-api"))
    .retrieve()
    .bodyToMono(String.class);
~~~

Both snippets assume the manager/provider supports Client Credentials tokens and has a **principal context**. This configuration defines two independent registrations, not one client ID automatically authorized for every API.

**Avoid sharing one WebClient across arbitrary hosts** merely because you can pick a registration per request. For sensitive APIs, use dedicated WebClients with fixed destinations and server-side registration mappings.

### 6.4. registrationId Is Not Provider ID

In YAML:

~~~yaml
registration:
  reports-api:
    provider: company-auth
provider:
  company-auth:
    token-uri: https://auth.example.net/oauth2/token
~~~

`reports-api` is the **registrationId** passed to `clientRegistrationId(...)`. `company-auth` is the **provider configuration ID**. Mixing up the two causes the manager to miss the registration or fail to acquire tokens.

## 7. Should You Pick Authorized Client or Registration?

| Scenario | Prefer | Explanation |
| --- | --- | --- |
| Controller already received the right `OAuth2AuthorizedClient` via annotation/resolver | `oauth2AuthorizedClient(client)` | Explicitly uses the current principal's authorization result |
| Service wants the manager to look up/acquire/refresh tokens by registration | `clientRegistrationId("id")` | Specifies client config without passing token objects |
| Background job using Client Credentials | `clientRegistrationId("service-id")` with service principal | Manager acquires/reuses machine tokens |
| App with multiple user-authorized integrations | Architecture-dependent, but pick the exact permitted authorized client/registration | Prevents cross-provider/tenant token mix-ups |
| Request to an API not needing OAuth2 | **Select no OAuth2 client** | Never attach Bearer Tokens needlessly |
| HTTP request to a user-chosen URL | Never use a credentialed WebClient without policy enforcement | Prevents SSRF and Access Token leakage |

### 7.1. Decision Tree

~~~mermaid
flowchart TD
    A["Does outbound API need an OAuth2 Access Token?"] -->|No| B["Use a WebClient without an OAuth2 filter"]
    A -->|Yes| C{"Trusted pre-selected authorized client available?"}
    C -->|Yes| D["attributes(oauth2AuthorizedClient(client))"]
    C -->|No| E{"Permitted registrationId available?"}
    E -->|Yes| F["attributes(clientRegistrationId(id))"]
    E -->|No| G["Reject / misconfigured; never guess a privileged token"]
    D --> H["Verify principal, Resource Server, scopes"]
    F --> H
    H --> I["Manager + filter -> Bearer Token"]
~~~

### 7.2. Explicit Selection Is Usually Safer Than Defaults

A request explicitly stating `clientRegistrationId(...)` or `oauth2AuthorizedClient(...)` makes it obvious to reviewers **why** a Bearer Token is attached. Enabling defaults on a multi-purpose WebClient lets another developer accidentally add an API call that sends tokens unexpectedly.

Explicitness in request attributes does not replace authorization logic, yet it reduces the risk of **unexpected credentials appearing** on requests that do not need OAuth2.

## 8. Configuring a WebFlux/OIDC Project

### 8.1. Dependencies

Gradle example for Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

In newer Spring Boot branches, starter names may be modularized; select dependencies per the BOM of your project's Boot version. The examples below use current Spring Security Reactive OAuth2 Client APIs following standard Spring Security 6.x patterns.

### 8.2. OIDC Registration for User Login

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

These are illustrative values. A real OIDC Provider requires a valid issuer, registered redirect URI, and appropriate scopes; secrets must come from environment variables/secret managers instead of source control.

**Do not assume `reports.read` is a standard OIDC scope.** It is an illustrative API/Authorization Server permission; issued tokens must also match the Reports API's expected audience/resource.

### 8.3. SecurityWebFilterChain

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

`oauth2Login()` handles browser OIDC login; `oauth2Client()` configures OAuth2 Client support for the Reactive server. Code calling Resource Servers must use the **OAuth2 client's Access Token**, never the OIDC principal's ID Token as a Bearer token.

## 9. Reactive Manager for User Tokens in WebFlux Requests

### 9.1. DefaultReactiveOAuth2AuthorizedClientManager

The standard manager for **WebFlux requests** accepts:

~~~java
DefaultReactiveOAuth2AuthorizedClientManager manager =
    new DefaultReactiveOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientRepository);
~~~

Where:

- `clientRegistrationRepository` is `ReactiveClientRegistrationRepository`.
- `authorizedClientRepository` is `ServerOAuth2AuthorizedClientRepository`.

The manager loads/saves authorized clients with `ServerWebExchange` and `Authentication`. It suits OAuth2 Login delegated user flows, including the Refresh Token grant when the provider issues a refresh token.

### 9.2. Explicit Manager Configuration

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
public class UserAuthorizedClientManagerConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientManager userAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

This is an **explicit configuration example**. If Spring Boot/Spring Security already supplies a suitable manager, avoid creating duplicate beans or accidentally replacing the authorized-client repository used by login.

### 9.3. Wiring the WebClient Filter to the User Manager

~~~java
package com.example.security;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsWebClientConfig {

    @Bean
    WebClient userReportsWebClient(
            @Qualifier("userAuthorizedClientManager")
            ReactiveOAuth2AuthorizedClientManager manager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://reports.example.net")
            .filter(oauth2)
            .build();
    }
}
~~~

If the application has only one manager bean, `@Qualifier` may be omitted. When both a **user manager** and a **machine manager** exist, use explicit bean names/qualifiers so you never inject the wrong manager with different grants/stores.

### 9.4. Calling an API Selecting the User's Registration

~~~java
package com.example.reports;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class UserReportsGateway {

    private final WebClient userReportsWebClient;

    public UserReportsGateway(WebClient userReportsWebClient) {
        this.userReportsWebClient = userReportsWebClient;
    }

    public Mono<String> loadMyReports() {
        return userReportsWebClient.get()
            .uri("/v1/me/reports")
            .attributes(clientRegistrationId("company"))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

This assumes the call executes within the WebFlux authentication context of a logged-in user. The filter/manager resolves the `Authentication` and the `company` authorized client. If the API requires a token for a different audience than what the OP issued, fix the integration/registration/resource request per contract—never substitute an ID Token.

## 10. Selecting OAuth2AuthorizedClient Directly in a Reactive Controller

In WebFlux applications, Spring Security supports `@RegisteredOAuth2AuthorizedClient` to resolve the authorized client for a specific registration.

Controller example:

~~~java
package com.example.web;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
public class UserProfileController {

    private final WebClient userReportsWebClient;

    public UserProfileController(WebClient userReportsWebClient) {
        this.userReportsWebClient = userReportsWebClient;
    }

    @GetMapping("/profile/remote")
    public Mono<String> remoteProfile(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient authorizedClient) {

        return userReportsWebClient.get()
            .uri("/v1/me")
            .attributes(oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

Here:

1. Spring Security resolves the `company` registration's authorized client in the logged-in user's context.
2. The controller passes that authorized client directly into the request attribute.
3. The WebClient filter uses the resolved authorized client to attach the Access Token.

**Never serialize `authorizedClient` or `authorizedClient.getAccessToken().getTokenValue()` into a response body sent to the browser.** The controller should only return API data after enforcing privacy/authorization rules.

Note: how the annotation resolves authorized clients and whether the manager refreshes depends on configuration/version. If a workflow must always proactively re-authorize, ensure the right manager/provider/store is wired; **never hold an old authorized client in a singleton across requests**.

### 10.1. Choosing the Right Client with Multiple User-Facing Registrations

Suppose a user logs in via `company` and later links a `calendar` account. A controller can receive the calendar authorized client once the app has completed the corresponding consent flow:

~~~java
@GetMapping("/calendar/events")
public Mono<String> events(
        @RegisteredOAuth2AuthorizedClient("calendar")
        OAuth2AuthorizedClient calendarClient) {
    return calendarWebClient.get()
        .uri("/events")
        .attributes(oauth2AuthorizedClient(calendarClient))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

This is an **illustrative method**; it assumes `calendarWebClient`, imports matching the example above, and a configured `calendar` registration. If the user has not granted consent, never grab a token from another provider and send it to the Calendar API.

## 11. Selecting Authentication/Principal Explicitly

### 11.1. Principal Defines Authorized-Client Ownership

With a service store:

~~~text
(company, alice) -> OAuth2AuthorizedClient for Alice
(company, bob)   -> OAuth2AuthorizedClient for Bob
~~~

Calling the manager with the wrong principal either misses the token or—worse—**accesses another person's token** if the application allows specifying arbitrary principal names.

In WebFlux, `Authentication` is normally propagated via Spring Security's **Reactor Context**, rather than relying on Servlet-style `ThreadLocal`.

### 11.2. Default Inside an Authenticated Request

In a protected reactive controller:

~~~java
@GetMapping("/my-reports")
public Mono<String> myReports() {
    return userReportsWebClient.get()
        .uri("/v1/me/reports")
        .attributes(clientRegistrationId("company"))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

The filter can resolve `Authentication` from the reactive security context inside the request chain. Never fabricate an `Authentication` from an email or query parameter.

### 11.3. Request Attribute authentication(...)

When passing a verified `Authentication` explicitly:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.authentication;
~~~

Example:

~~~java
Mono<String> result = webClient.get()
    .uri("/v1/me/reports")
    .attributes(clientRegistrationId("company"))
    .attributes(authentication(authenticationFromReactiveSecurity))
    .retrieve()
    .bodyToMono(String.class);
~~~

`authenticationFromReactiveSecurity` must be an `Authentication` obtained from a trusted server-side source. Passing a request attribute does not turn a self-constructed `Authentication` into valid proof of user authentication.

### 11.4. When Reading SecurityContext Inside a Reactive Service

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

Mono<String> result =
    ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No authentication context")))
        .flatMap(authentication -> webClient.get()
            .uri("/v1/me/reports")
            .attributes(clientRegistrationId("company"))
            .attributes(
                ServerOAuth2AuthorizedClientExchangeFilterFunction.authentication(
                    authentication))
            .retrieve()
            .bodyToMono(String.class));
~~~

This illustrates **explicit context passing**. In normal requests, the filter can resolve authentication automatically; avoid unnecessary boilerplate when not needed.

### 11.5. Never Use Servlet's SecurityContextHolder to Pick Users in WebFlux

Anti-example:

~~~java
// DO NOT USE as default in Reactive WebFlux:
Authentication auth = SecurityContextHolder.getContext()
    .getAuthentication();
~~~

Reactor can hop across multiple threads. WebFlux security uses **Reactor Context** and does not guarantee a request thread's `ThreadLocal` remains present on the thread executing the HTTP client. Use `ReactiveSecurityContextHolder` or valid request attributes.

## 12. ServerWebExchange and Session-Scoped Token Selection

### 12.1. When the Manager Needs ServerWebExchange

`DefaultReactiveOAuth2AuthorizedClientManager` uses `ServerOAuth2AuthorizedClientRepository`. The repository may need `ServerWebExchange` to access `WebSession` or request-scoped context.

In a WebFlux request, the filter/manager can resolve the exchange from Spring Security's reactive context. For special cases, pass the exchange explicitly:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.serverWebExchange;
~~~

Example:

~~~java
return webClient.get()
    .uri("/v1/me/reports")
    .attributes(clientRegistrationId("company"))
    .attributes(serverWebExchange(exchange))
    .retrieve()
    .bodyToMono(String.class);
~~~

`exchange` is the actual `ServerWebExchange` of the current request passed into the controller/service by WebFlux. Never store an exchange in a singleton or queue to reuse after the request completes.

### 12.2. Creating a Mono in a Request, Subscribing Outside the Request

A common bug:

~~~text
HTTP request /reports
  -> creates WebClient Mono
  -> pushes Mono onto a task queue
  -> HTTP request finishes
  -> Mono is subscribed later on another thread
  -> missing Authentication or ServerWebExchange
~~~

In Reactive programming, HTTP calls normally start on **subscribe**. Never assume creating a `Mono` inside a controller keeps controller contexts alive forever.

If a workflow genuinely must run outside a web request:

- Confirm the user/policy authorized using the token post-request.
- Persist the authorized client securely under a stable principal identity when needed.
- Consider **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`** instead of a web-exchange-dependent manager.
- Never carry around an expired `ServerWebExchange`.

### 12.3. WebSession Expiration and Authorized Clients

If the repository binds state to the session, tokens become unreachable after session timeout or invalidation. If authorized clients live in a persistent service store, data may survive user logout depending on policy.

**User logout does not automatically mean every Access Token/Refresh Token in the database was revoked.** Token revocation is a separate responsibility when products require revoking access.

## 13. Client Credentials: Per-Request Registration, Application-Level Principal

A backend worker with no end-user authentication typically uses **Client Credentials** to call APIs:

~~~text
report-sync service
   -> client_credentials grant
   -> service Access Token
   -> Reports API
~~~

There is no user authorization-code redirect, user ID Token, or browser session.

### 13.1. YAML for a Machine-to-Machine Registration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          report-sync:
            provider: internal-auth
            client-id: ${REPORT_SYNC_CLIENT_ID}
            client-secret: ${REPORT_SYNC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          internal-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

No `redirect-uri`, `state`, PKCE, or `nonce` is required for a basic Client Credentials grant.

### 13.2. AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager

Manager outside web exchanges:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class MachineClientManagerConfig {

    @Bean
    AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
            machineAuthorizedClientManager(
                    ReactiveClientRegistrationRepository registrations,
                    ReactiveOAuth2AuthorizedClientService authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

The service manager does not need `ServerWebExchange`. When a grant succeeds, the manager normally saves the authorized client via the reactive service for reuse on subsequent runs.

### 13.3. Dedicated WebClient for Machine Tokens

~~~java
package com.example.security;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class MachineReportsClientConfig {

    @Bean
    WebClient machineReportsWebClient(
            @Qualifier("machineAuthorizedClientManager")
            AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://reports.example.net")
            .filter(oauth2)
            .build();
    }
}
~~~

### 13.4. Passing an Explicit Application Authentication

Inside a scheduled job, a user Reactor security context may not exist. Use an application principal **strictly as a token storage key**, not to impersonate an end-user:

~~~java
package com.example.reports;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.authentication;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class MachineReportsGateway {

    private final WebClient machineReportsWebClient;

    public MachineReportsGateway(WebClient machineReportsWebClient) {
        this.machineReportsWebClient = machineReportsWebClient;
    }

    public Mono<String> loadReports() {
        Authentication servicePrincipal =
            new UsernamePasswordAuthenticationToken(
                "system-report-sync",
                "N/A",
                AuthorityUtils.NO_AUTHORITIES);

        return machineReportsWebClient.get()
            .uri("/v1/reports")
            .attributes(clientRegistrationId("report-sync"))
            .attributes(authentication(servicePrincipal))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

**Security boundary:** `servicePrincipal` in this example is a backend-constructed `Authentication` object so the manager can resolve a **principal name**; it is not proof of OIDC login and must never be used to grant controller access as an end-user.

The name `system-report-sync` should remain stable per service identity so the store reuses the same authorized client. Never read this principal from a browser-supplied query string or header.

### 13.5. Why Is No Refresh Token Needed?

With Client Credentials, Authorization Servers normally **do not issue a Refresh Token**. When the Access Token expires, the manager simply acquires a fresh token via the Client Credentials grant. Never add `refresh_token` or `offline_access` as if this were an OIDC end-user flow.

When the provider rejects with `invalid_client` or `invalid_scope`, that is a client authentication/policy error. Do not self-escalate permissions or retry infinitely.

## 14. Selecting Registrations by Feature or Tenant: Safety Principles

A multi-API, multi-tenant application may require a mapping:

~~~text
Feature: readReports
  -> Resource Server: reports.example.net
  -> Registration: reports-read

Feature: readInvoices
  -> Resource Server: billing.example.net
  -> Registration: billing-read
~~~

### 14.1. Mapping from a Server-Side Allowlist

A straightforward approach:

~~~java
enum Integration {
    REPORTS,
    BILLING
}

static String approvedRegistrationFor(Integration integration) {
    return switch (integration) {
        case REPORTS -> "reports-read";
        case BILLING -> "billing-read";
    };
}
~~~

This is an **illustrative snippet** to place inside a Java class; the mapping is backend-owned. In a real application, before selecting an integration, also verify the caller is **authorized to perform that action within the active tenant**.

### 14.2. Selecting by Verified Tenant

Suppose a multi-tenant product defines registrations `tenant-a-reports` and `tenant-b-reports`. If the user belongs only to Tenant A, the application must:

1. Verify tenant membership from `Authentication`/a trusted data source.
2. Select Tenant A's registration via a server-side mapping.
3. Keep principal namespaces isolated so another user/tenant's token is never loaded.
4. Send tokens only to Tenant A's Resource Server.

Never trust a `tenantId` from the URL as sufficient to use a registration holding that tenant's secrets.

### 14.3. Avoid Picking Tokens from Arbitrary Input

Anti-example:

~~~java
// DO NOT USE: caller can pick arbitrary credentials and destinations.
webClient.get()
    .uri(userSuppliedUrl)
    .attributes(clientRegistrationId(userSuppliedRegistration))
    .retrieve()
    .bodyToMono(String.class);
~~~

Risks:

- Attackers can make WebClient send Bearer Tokens to their own host.
- A user can choose a high-privilege registration and abuse service permissions.
- One tenant's token gets used for another tenant.
- The Resource Server and client become vulnerable to SSRF, redirect abuse, or confused-deputy attacks.

**Protect all three dimensions:** target URL, registration ID, and principal must all follow verified policies.

## 15. Default OAuth2 Authorized Client: Convenient Yet Prone to Credential Leaks

The filter provides defaults to avoid specifying attributes on every request. However, defaults affect **every request passing through that WebClient**.

### 15.1. setDefaultOAuth2AuthorizedClient(true)

~~~java
ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

oauth2.setDefaultOAuth2AuthorizedClient(true);
~~~

When enabled, the filter can automatically pick the authorized client tied to the **current OAuth2 authentication** even without an explicit registration ID on the request.

Risk: unintended outbound calls written by another developer sharing the same WebClient bean **may carry the current user's Access Token**.

### 15.2. setDefaultClientRegistrationId(...)

~~~java
oauth2.setDefaultClientRegistrationId("reports-read");
~~~

This tells the filter to use that registration whenever a request omits an explicit client. It is safer on a WebClient **dedicated to one fixed API**, yet you must still ensure absolute URLs and redirects cannot send tokens to external hosts.

### 15.3. Two Scenarios to Avoid

~~~text
Global WebClient:
  default client registration = admin-service
  calls Reports API -> admin token
  calls public weather URL -> unintended admin token

Global WebClient:
  default OAuth2 authorized client = current user login
  calls UserInfo API -> user Access Token
  calls arbitrary redirect URL -> risk of sending token to wrong destination
~~~

**Never enable defaults merely to "save typing `clientRegistrationId(...)`".** Enable them only where a clear trust boundary has been designed.

### 15.4. Recommended Pattern for Reviewable Code

In most multi-API systems:

- One WebClient bean per Resource Server or group of endpoints sharing a trust boundary.
- Clear registration and principal mapping in the service layer.
- Explicit `oauth2AuthorizedClient(...)` or `clientRegistrationId(...)` only where needed.
- Never use an OAuth2-filtered WebClient for arbitrary browser-supplied URLs.
- Enable defaults only on dedicated WebClients with strict path/redirect controls.

## 16. Resource Server 401/403 and Authorization Failure Handlers

Selecting the right authorized client **does not guarantee the API accepts the token**. A Resource Server may reject it due to revocation, wrong issuer/audience, or insufficient scope.

### 16.1. Distinguishing Error Codes

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.write"
~~~

| Where it occurs | Signal | Interpretation |
| --- | --- | --- |
| Token Endpoint | `invalid_client` | Client authentication rejected |
| Token Endpoint | `invalid_scope` | Requested scope invalid/not permitted |
| Token Endpoint | `invalid_grant` | Issue with Authorization Code/Refresh Token grant depending on flow |
| Resource Server | `401 invalid_token` | Access Token invalid/expired/revoked/mismatched claims |
| Resource Server | `403 insufficient_scope` | Token lacks required scope for the API operation |
| Resource Server | Other `403` | Likely tenant/ownership/business policy denial |

**Never treat HTTP 403 as a reason to self-request admin scopes**, nor treat 401 as guaranteed proof of a wrong Client Secret. Token Endpoint errors and Resource Server errors occur at different layers.

### 16.2. Failure Handler Behavior Depends on How the Filter Was Constructed

With the constructor:

~~~java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveAuthorizedClientManager)
~~~

Spring Security does not automatically install a `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` for Resource Server Bearer errors. A token rejected by the API can remain in the authorized-client store and be reused on the next request.

With the constructor:

~~~java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveClientRegistrationRepository,
    authorizedClientRepository)
~~~

the filter installs a default failure handler to remove authorized clients on matching errors. Behavior keys off **OAuth2/Bearer error codes**, not "delete every token on any HTTP error".

### 16.3. Configuring When Using the Manager Constructor

Applications wanting to evict stale tokens can configure:

~~~java
// Illustrative configuration hook; handler must match
// the application's actual repository/service.
oauth2.setAuthorizationFailureHandler(reactiveFailureHandler);
~~~

`reactiveFailureHandler` is a `ReactiveOAuth2AuthorizationFailureHandler` implementation wired to the matching removal mechanism/store. With Spring Security's `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler`, connect the removal strategy by registration/principal to the exact store used by the manager.

Never configure a handler removing tokens from JDBC service B while the manager stores tokens in repository A—stale records would remain.

### 16.4. Does It Automatically Retry Requests That Returned 401?

Do not assume so. The failure handler can **evict the invalid authorized client** so the next request has a chance to acquire a new token. The current request can still fail with `WebClientResponseException.Unauthorized` or another error response.

If you want retries:

1. Retry only recoverable errors with strict bounds.
2. For POST/PATCH/DELETE, enforce idempotency and prevent duplicate side effects.
3. Never loop infinitely if the provider keeps issuing tokens with the wrong audience.
4. Never retry `insufficient_scope` by escalating privileges.
5. Ensure retries keep **the same valid registration/principal**, never switching to a higher-privilege client.

## 17. How Do Token Expiration and Refreshes Work?

### 17.1. Authorization Code / OIDC User Tokens

~~~text
OIDC Login -> OAuth2AuthorizedClient(user, company)
      |
      +-- Access Token still usable -> reuse
      |
      +-- Access Token needs refresh
             -> refresh_token grant if Refresh Token exists
             -> Token Endpoint returns new Access Token
             -> manager saves updated authorized client
             -> WebClient filter attaches new Access Token
~~~

Providers may rotate Refresh Tokens. If the manager fails to save the new token after refresh, the next attempt may reuse an invalidated Refresh Token and hit `invalid_grant`.

### 17.2. Machine Tokens with Client Credentials

~~~text
Client Credentials token expired
  -> manager executes a new client_credentials grant
  -> saves new Access Token for service principal
  -> WebClient request proceeds to call API
~~~

Standard Client Credentials flows normally have no Refresh Token. Never enable OIDC `openid`/`offline_access` for a service merely because it periodically needs fresh tokens.

### 17.3. The Manager Does More Than Load Tokens

`ReactiveOAuth2AuthorizedClientService.loadAuthorizedClient(...)` is a **record read**. `ReactiveOAuth2AuthorizedClientManager.authorize(...)` can invoke providers to acquire/refresh tokens as configured. If a request only checks "connected or not" without triggering token exchange, use the service/repository load appropriately.

### 17.4. Concurrent Refreshes and Token Rotation

~~~mermaid
sequenceDiagram
    autonumber
    participant A as WebClient Request A
    participant B as WebClient Request B
    participant S as Authorized Client Store
    participant OP as Token Endpoint
    A->>S: Load old token
    B->>S: Load old token
    A->>OP: Refresh Token grant
    B->>OP: Refresh Token grant with old token
    OP-->>A: New token, rotated refresh token
    OP-->>B: Possible invalid_grant
    A->>S: Save updated authorized client
    Note over S: Prevent old request from deleting/overwriting new token
~~~

When multiple requests concurrently hit an expired authorized client, you may need **single-flight per registration/principal**, optimistic concurrency, or carefully designed database transactions. Never apply a global lock across all users.

## 18. Reactive Authorized Client Storage and Data Lifecycle

### 18.1. ServerOAuth2AuthorizedClientRepository

The reactive repository can store data tied to HTTP exchanges and principals—for instance in `WebSession` or via a backing service. It pairs with `DefaultReactiveOAuth2AuthorizedClientManager` in WebFlux request flows.

### 18.2. ReactiveOAuth2AuthorizedClientService

The reactive service requires no `ServerWebExchange`; it suits persistence/worker use cases where a clear principal name exists.

Common APIs:

~~~java
Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
);

Mono<Void> saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal
);

Mono<Void> removeAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
~~~

These signatures illustrate the Reactive API surface; use the exact imports/types and contracts of your library version. Because methods return `Mono`, the application must not call detached `subscribe()` outside the reactive chain.

### 18.3. In-Memory vs Persistent Stores

| Store type | Behavior | Notes |
| --- | --- | --- |
| In-memory reactive service | Simple; tokens lost on restart | Not shared across pods |
| WebSession repository | Tied to browser session | Session expiry can lose authorized clients |
| Persistent custom/service store | Accessible across instances/jobs | Needs encryption, schema, locking, and data lifecycle |
| Shared session backing store | Supports session continuity across instances | Must protect cookies/sessions and TTLs |

Never assume every `ServerOAuth2AuthorizedClientRepository` always stores in the session, since a repository can delegate to a service. When debugging, identify the **actual backing store used by the active bean/manager**.

### 18.4. Logout Differs from Token Removal and Revocation

| Action | Impact |
| --- | --- |
| WebFlux user logout | Ends context/session per logout policy |
| Delete authorized client from local store | App can no longer load that token record |
| Call token revocation endpoint if supported | Asks the Authorization Server to revoke the token per protocol |
| OIDC OP logout | May end the login session at the OP per support/config |

Never treat calling `removeAuthorizedClient(...)` as proof that all Access Tokens were revoked at the Resource Server. With persistent stores, user logout does not automatically delete every authorized client unless policy/implementation explicitly does so.

## 19. Protecting Access Tokens from SSRF, Redirects, and Logs

### 19.1. A WebClient with an OAuth2 Filter Is a Credentialed HTTP Client

If you write:

~~~java
webClient.get()
    .uri(untrustedUrl)
    .attributes(clientRegistrationId("admin-integration"))
    .retrieve();
~~~

an attacker can make the request send a Bearer Token to a host outside the trust boundary—an **SSRF and token exfiltration** vulnerability.

### 19.2. baseUrl Is Not a Host Allowlist

~~~java
WebClient.builder()
    .baseUrl("https://reports.example.net")
    .filter(oauth2)
    .build();
~~~

Setting `baseUrl` helps with routing, yet **does not block absolute URIs** passed to `.uri(...)`. If target URLs can originate from user input, validate host, scheme, port, IP resolution, and redirect behavior.

### 19.3. Separate WebClients by Trust Boundary

~~~text
reportsWebClient
  -> Reports API
  -> registration "reports-read"
  -> only allows destinations belonging to Reports API

billingWebClient
  -> Billing API
  -> registration "billing-read"
  -> only allows destinations belonging to Billing API

publicWebClient
  -> validated public data
  -> NO OAuth2 filter attached
~~~

Separation makes it clear during code review which calls carry credentials. Never share one high-privilege machine token across every API just because a client registration can be reused.

### 19.4. Cross-Host Redirects

HTTP clients/connectors vary in redirect behavior depending on transport and configuration. Never assume a redirect to another hostname safely strips the `Authorization` header in every scenario.

For credentialed clients:

- Disable or restrict cross-host redirects when unnecessary.
- Enforce destination allowlists and review redirect-following rules.
- Never allow an attacker-controlled API redirect target to receive external calls.
- Require HTTPS with TLS hostname/certificate verification.

### 19.5. Never Log Secrets

Never log:

- HTTP `Authorization: Bearer ...`.
- Access Tokens, Refresh Tokens, ID Tokens.
- Client Secrets, client assertions, private keys, token request bodies.
- Full `OAuth2AuthorizedClient` objects or personal JWT claims.
- Authorization codes, PKCE verifiers, or OIDC nonces.

Safe metadata log:

~~~text
event=outbound_oauth2_call
registration_id=reports-read
principal_type=user
resource=reports-api
result=success
http_status=200
correlation_id=internal-e43a
~~~

This is an **illustrative format**, not a default Spring Security log output. If principal IDs are logged, enforce privacy, retention, and least privilege.

## 20. Customizing HTTP Pipelines and Retries

### 20.1. WebClient Is Reactive

Example:

~~~java
Mono<String> response = webClient.get()
    .uri("/v1/me")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
~~~

The `Mono` describes a pipeline. Inside a WebFlux request, **return the `Mono`** or compose via `flatMap`, `zip`, `onErrorResume`. Never call `block()` on the Reactor event loop waiting for API responses.

### 20.2. HTTP 5xx Retries Differ from OAuth2 Errors

A service may encounter:

- Network timeout/503: can be retried **with bounds**, backoff, and jitter.
- Token Endpoint `invalid_client`: fix secret/auth method; infinite retries are futile.
- Token Endpoint `invalid_scope`: fix scope/policy; never self-escalate privileges.
- Resource Server `401 invalid_token`: check token/lifecycle and failure handler.
- Resource Server `403 insufficient_scope`: never self-add scopes; align with policy/API contract.

Never attach `retryWhen(Retry.max(Long.MAX_VALUE))` across all errors—it can trigger token request storms or duplicate side-effecting POST/DELETE calls.

### 20.3. For POST/PATCH/DELETE

Suppose an API creates reports via POST. If the HTTP client times out after the server already processed the POST, a blind retry creates a duplicate report. When retrying writes, require an idempotency key or downstream transactional deduplication.

### 20.4. The WebClient Filter Is Not User Authorization

`clientRegistrationId("admin-service")` only picks a client registration; it does not check whether the logged-in user is permitted to trigger admin actions. If an HTTP controller lets regular users reach a high-privilege registration, the backend must enforce authorization before calling WebClient.

## 21. Differences Between Reactive and Servlet WebClient Filters

| Item | Reactive WebFlux | Servlet MVC |
| --- | --- | --- |
| OAuth2 WebClient filter | **`ServerOAuth2AuthorizedClientExchangeFilterFunction`** | `ServletOAuth2AuthorizedClientExchangeFilterFunction` |
| Authorized Client Manager | `ReactiveOAuth2AuthorizedClientManager` | `OAuth2AuthorizedClientManager` |
| Request-context repository | `ServerOAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClientRepository` |
| Authorized client service | `ReactiveOAuth2AuthorizedClientService` | `OAuth2AuthorizedClientService` |
| Security context | Reactor Context / `ReactiveSecurityContextHolder` | `SecurityContextHolder` / Servlet context |
| HTTP exchange | `ServerWebExchange` | `HttpServletRequest`, `HttpServletResponse` |
| Controller return value | `Mono`/`Flux` natively | Synchronous values or async types per config |

Never use:

~~~java
// Servlet implementation — not a reactive server filter.
new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    servletAuthorizedClientManager)
~~~

in a WebFlux server that only defines reactive authorized-client beans, expecting it to read `ServerWebExchange`. Likewise, never use `ServerOAuth2AuthorizedClientExchangeFilterFunction` as a `ClientHttpRequestInterceptor` on `RestClient`; those are two distinct HTTP client hooks.

### 21.1. Never Mix Managers/Stores Across Stacks

`OAuth2AuthorizedClientService` (the Servlet/synchronous interface) and `ReactiveOAuth2AuthorizedClientService` do not share the same contract. If an application bridges both, design an explicit adapter or shared backing store rather than casting or calling ad-hoc `subscribe()`.

## 22. Symptom-Based Troubleshooting

| Symptom | Common cause | Check |
| --- | --- | --- |
| Request lacks Bearer header | WebClient bean missing filter | Verify `.filter(oauth2)` on the right bean |
| Filter cannot find registration | Wrong/missing `clientRegistrationId(...)` | Cross-check `spring.security.oauth2.client.registration.*` |
| Filter uses wrong registration | Default set or wrong mapping | Use explicit request attributes; separate WebClients |
| User A's token sent on User B's request | Wrong `Authentication`/principal context | Inspect Reactor Context and store ownership |
| WebClient request has no `Authentication` | Pipeline subscribed outside request or scheduled job | Supply proper context; use service manager |
| Default manager missing `ServerWebExchange` | Running outside web request | Use service manager or a valid exchange |
| Manager returns empty / fails to authorize | Grant/provider mismatch or missing consent | Check authorization flow and registration |
| Token Endpoint `invalid_client` | Wrong secret/method/tenant/token URI | Fix client authentication; do not retry forever |
| Token Endpoint `invalid_scope` | Scope not granted | Fix policy/requested scopes; never auto-escalate |
| API returns `401 invalid_token` | Expired/revoked token or wrong issuer/audience | Inspect token validation and failure handler |
| API returns `403 insufficient_scope` | Token lacks required scope | Check API authorization policy |
| Request after 401 still uses stale token | `Filter(manager)` lacks removal handler | Configure Reactive failure handler using the right store |
| Token removed yet current request still failed | Failure handler does not auto-retry | Review retry/idempotency policy |
| Multi-pod deploy makes every node request tokens | Unshared in-memory service | Use shared persistence/coordination if needed |
| Rotating refresh token hits `invalid_grant` | Concurrent refreshes or stale storage | Synchronize per client with appropriate versioning/locking |
| API call sends token to unexpected URL | WebClient received absolute URI from user input | Enforce SSRF checks, host allowlists, redirect limits |
| JWT/Access Token appears in logs | Wire logging or debug interceptors logging headers | Redact Authorization/credentials |
| OIDC login works yet Reports API returns 403 | Access Token scope/audience/policy mismatch | Never use ID Token in place of Access Token |
| JDBC token survives after logout | Persistent store lifecycle differs from session | Define explicit disconnect/revocation policy |

### 22.1. Request Debugging Sequence

~~~text
Outbound WebClient request fails
  |
  +-- Does the right WebClient bean have the OAuth2 filter?
  |
  +-- Is oauth2AuthorizedClient or clientRegistrationId selected?
  |
  +-- Does ClientRegistration exist with the right provider?
  |
  +-- Does Authentication/principal match the right user/service?
  |
  +-- Does the Reactive manager match web-context or service-context?
  |
  +-- Does the authorized client store have the right key and backing store?
  |
  +-- Did the Token Endpoint acquire/refresh successfully?
  |
  +-- Did the Access Token reach the right Resource Server?
  |
  +-- Did the API return 401, 403, 429, 5xx, or a transport exception?
  |
  +-- Are the failure handler and retry policy aligned?
~~~

You never need to print raw tokens to debug. Use registration ID, principal category, token presence, classified error codes, HTTP status, and an internal correlation ID.

## 23. Practical Scenarios

### Scenario A — Controller Already Has the Authorized Client

Spring Security injected `@RegisteredOAuth2AuthorizedClient("company")` for the logged-in user.

**Approach:** pass `.attributes(oauth2AuthorizedClient(client))`. Do not extract the token value to build Bearer headers manually, and never store the object in a singleton.

### Scenario B — Service Knows Only the Registration

A service needs to call the Reports API without managing token lifecycles.

**Approach:** use `.attributes(clientRegistrationId("reports-api"))` with the configured manager/provider/store. Never call the Token Endpoint manually on every HTTP request.

### Scenario C — Shared WebClient Calling Reports and Billing

A developer passes `clientRegistrationId("reports-api")` for both URLs.

**Approach:** separate clients/mappings per API and place registration selection in a trusted service layer; never send Reports' Access Token to Billing.

### Scenario D — Scheduled Job Without a User SecurityContext

A queue consumer running outside WebFlux requests needs a Client Credentials token.

**Approach:** use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` and `authentication(servicePrincipal)` with a stable application name, selecting `clientRegistrationId("report-sync")`.

### Scenario E — User Switches Login Providers

A user previously logged in with `company`, and now logs in with `partner`. Code still hard-codes `company`.

**Approach:** if the feature depends on the login's own registration, obtain the registration from the verified `OAuth2AuthenticationToken` or a trusted mapping. Never reuse an old token simply because usernames match.

### Scenario F — User Has Two Connections on the Same Provider

The app manages two separate delegated OAuth2 connections.

**Approach:** design appropriate namespacing/principal/account linking and pick the exact authorized client. Never key a registration solely by email and accidentally overwrite the other connection's token.

### Scenario G — Unexpired Token Yet API Returns 401

The Resource Server revoked the token or the audience mismatches.

**Approach:** inspect issuer/audience; for `invalid_token`, evict the cached authorized client via an appropriate handler. Never retry infinitely if newly issued tokens still have the wrong audience.

### Scenario H — API Returns 403 insufficient_scope

The client has `reports.read` yet calls an endpoint requiring `reports.write`.

**Approach:** never randomly swap in an admin registration to bypass checks; update permissions through the formal authorization process if the feature genuinely needs them.

### Scenario I — Default OAuth2 Authorized Client Enabled Before Adding Public Fetch

A WebClient was built for logged-in API calls and later used to fetch arbitrary URLs.

**Approach:** create a separate credential-less public WebClient, enforce host allowlists on OAuth2-filtered clients, and never rely on defaults to attach tokens everywhere.

### Scenario J — Authorized Client Persists After User Logout

A persistent store keeps delegated tokens after logout.

**Approach:** verify whether continued API access post-logout is consented to and permitted by policy; provide disconnect/revocation where required. Never treat `setDefaultOAuth2AuthorizedClient(false)` as revocation.

### Scenario K — Two Concurrent Refresh Token Requests

The provider issues single-use rotating Refresh Tokens, and one request gets `invalid_grant`.

**Approach:** coordinate concurrency and failure cleanup so an old failure never wipes a fresh token saved by another request.

### Scenario L — Request Attribute Read from a Query Parameter

A backend lets users call `/proxy?registration=admin-client&url=...` and forwards both straight into WebClient.

**Approach:** reject this design; enforce server-side mappings and user/tenant/feature authorization before choosing credentials or URLs.

## 24. Testing Authorized Client Selection on WebClient

To test thoroughly, separate concerns:

| Layer | What to test |
| --- | --- |
| Request mapping test | `clientRegistrationId(...)` or `oauth2AuthorizedClient(...)` is selected accurately |
| Filter test | Given a test authorized client, the HTTP request carries the Bearer Test Token |
| Manager test | Uses the right registration/principal and acquires/reuses tokens per grant |
| Reactive context test | `Authentication` is read accurately from Reactor Context with no user mix-ups |
| HTTP integration test | Resource Server returns 401/403 and the app handles it properly |
| Security/SSRF test | Tokens are never sent to unallowlisted hosts/URLs |
| Session/storage test | Logout, expiry, persistence, and multi-node behavior match policy |

### 24.1. Minimal Test Scenarios

1. Alice's `OAuth2AuthorizedClient` present: Alice's request sends Alice's test Bearer token; Bob's request never receives Alice's token.
2. `clientRegistrationId("reports-api")`: manager is asked to authorize the right registration.
3. `clientRegistrationId("billing-api")`: Reports token is never sent to Billing.
4. No matching registration/authorized client/default: never falls back to a high-privilege credential.
5. Client Credentials with a fixed application principal: token is saved/reloaded under the same key.
6. Manager cannot authorize: outbound request is never sent with a fake fabricated token.
7. Expired token: manager/provider executes re-authorization when supported.
8. Resource Server `401 invalid_token`: failure handler acts per policy.
9. Resource Server `403 insufficient_scope`: never self-switches to an admin registration.
10. Unallowlisted URL: request is blocked before the Bearer Token leaves the application.
11. No Reactor security context in a worker: service manager still authorizes the application principal.
12. Debug logging enabled: tokens, Client Secrets, and Authorization headers never appear in logs.

### 24.2. Testing the Filter with a Fake ExchangeFunction

A conceptual way to test is supplying a test double for `ReactiveOAuth2AuthorizedClientManager` returning an `OAuth2AuthorizedClient` with a **TEST_ONLY** token, and routing WebClient through a fake `ExchangeFunction`:

~~~text
WebClient.get("/v1/reports")
    attributes(clientRegistrationId("reports-api"))
       |
       v
ServerOAuth2AuthorizedClientExchangeFilterFunction
       |
       v
Fake ReactiveOAuth2AuthorizedClientManager
    -> returns TEST_ONLY_ACCESS_TOKEN
       |
       v
Fake ExchangeFunction
    assert Authorization == Bearer TEST_ONLY_ACCESS_TOKEN
    return HTTP 200 JSON
~~~

This test verifies **token selection and header injection**, not that a real OP issued the token or a Resource Server properly validated the JWT.

### 24.3. Authorization Code / OIDC Tests Need Their Own Layer

Mocking `OAuth2AuthorizedClient` does not replace testing:

- Authorization request + `state` correlation.
- PKCE challenge/verifier.
- OIDC ID Token signature/issuer/audience/nonce.
- Token Endpoint responses and Refresh Token rotation.
- User account linking and principal namespacing.

Those are protocol-layer tests requiring a mock OP or suitable integration environment.

### 24.4. Never Leak Real Credentials in Tests

Never use a production Client Secret trying to trigger `invalid_client` in tests. Never save real Access Tokens in fixtures, logs, or screenshots. Use fake credentials and mock Token Endpoints/Resource Servers.

## 25. Review Questions

**1. How do `clientRegistrationId(...)` and `oauth2AuthorizedClient(...)` differ?**

`clientRegistrationId(...)` selects an OAuth2 client configuration so the manager can look up or acquire an authorized client. `oauth2AuthorizedClient(...)` passes a specific authorized client already chosen by trusted server-side code.

**2. Should both attributes be passed on the same request?**

No. That introduces conflicting intent or dependence on internal precedence; pick one consistent token-selection strategy.

**3. Why must two users sharing a `registrationId` never share tokens?**

Because `OAuth2AuthorizedClient` is bound to a principal; the store must key tokens by registration/principal, not registration alone.

**4. Where does Reactive WebFlux get `Authentication`?**

Typically from the Spring Security-managed Reactor security context; it can also be passed explicitly via `authentication(...)` when needed. Never rely on Servlet ThreadLocals.

**5. Should a scheduled job use `DefaultReactiveOAuth2AuthorizedClientManager`?**

Not if the task lacks the required `ServerWebExchange`/web request. For Client Credentials, use the service manager with an explicit application principal.

**6. What is the risk of a default registration?**

Every request sent through that WebClient can accidentally attach a Bearer Token, even requests to untrusted URLs if code allows them.

**7. Does `Filter(manager)` automatically remove cached tokens when an API returns 401?**

No `RemoveAuthorizedClient` failure handler is installed by default on the manager constructor; evaluate and configure the appropriate handler.

**8. Does a user token with `ROLE_ADMIN` automatically include `reports.write`?**

No. Application roles and Access Token scopes/audiences managed by the Authorization Server/Resource Server are separate boundaries.

**9. Should `OAuth2AuthorizedClient` be stored in a static variable or returned to the browser?**

No. It holds sensitive credentials and binds principal, grant, and expiration.

**10. How should you handle `403 insufficient_scope` from an API?**

Check the API contract and granted permissions. Never swap in a higher-privilege registration or inflate scopes to bypass checks.

## 26. References

- Spring Security — Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — Reactive OAuth2 Authorized Clients: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html
- Spring Security — Reactive OAuth2 Client Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
- Spring Security — Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — `ServerOAuth2AuthorizedClientExchangeFilterFunction` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
- Spring Security — `ReactiveOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientManager.html
- Spring Security — `DefaultReactiveOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultReactiveOAuth2AuthorizedClientManager.html
- Spring Security — `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.html
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- OAuth 2.0 Authorization Framework (RFC 6749): https://www.rfc-editor.org/rfc/rfc6749
- OAuth 2.0 Bearer Token Usage (RFC 6750): https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700

## 27. Summary: Explicit Token Selection and Clear Principal Boundaries

~~~text
Reactive WebClient request
    |
    +-- OPTION A: already holding a specific authorized client
    |      attributes(oauth2AuthorizedClient(client))
    |
    +-- OPTION B: select registration for manager
           attributes(clientRegistrationId("company" | "reports-api"))
    |
    +-- Authentication/principal:
    |      - WebFlux user: Reactor SecurityContext
    |      - Machine flow: controlled application principal
    |
    v
ServerOAuth2AuthorizedClientExchangeFilterFunction
    |
    v
ReactiveOAuth2AuthorizedClientManager
    |
    +-- Load authorized client by registration + principal
    +-- Authorize/refresh per valid grant if needed
    +-- Save updated authorized client
    |
    v
Authorization: Bearer <access_token>
    |
    v
Resource Server validates issuer/audience/scope/policy
    |
    +-- 2xx -> handle response
    +-- 401 invalid_token -> consider invalidation/token lifecycle
    +-- 403 insufficient_scope -> handle missing scope, do not elevate
    +-- 429/5xx -> policy-driven retry/backoff
~~~

**Four core takeaways:**

1. **`oauth2AuthorizedClient(client)` picks a specific authorization result; `clientRegistrationId(id)` picks a configuration so the manager resolves/acquires a token.** Use one clear strategy per request.
2. **Principal is part of the security boundary.** In WebFlux user flows, `Authentication` comes from the reactive security context; in Client Credentials, the service principal must be stable, backend-selected, and never mistaken for a user identity.
3. **Default credentials risk unintended sprawl.** Avoid enabling default OAuth2 clients on WebClients shared across multiple hosts or user-controlled URLs; control destinations, registrations, redirects, and logging.
4. **The filter only attaches the Access Token to the HTTP request.** The authorized client manager governs token lifecycles, while the Resource Server decides access; handle HTTP 401/403 per error code and policy rather than bypassing checks.

Once you master both ways to select an **authorized client or registration per WebClient request**, your Reactive application can cleanly call multiple OAuth2 APIs, reuse tokens properly, and avoid confusing user identities, service permissions, and scopes permitted by Resource Servers.
