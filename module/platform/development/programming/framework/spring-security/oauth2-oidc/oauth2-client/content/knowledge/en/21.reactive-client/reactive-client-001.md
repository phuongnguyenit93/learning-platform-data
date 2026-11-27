# 21.1. ReactiveOAuth2AuthorizedClientManager and OAuth2AuthorizeRequest

## Lesson Objectives

In **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, a **Spring WebFlux** application often needs an access token to call a Resource Server. Instead of manually handling every step of acquiring, storing, reusing, and refreshing tokens, the application can use **`ReactiveOAuth2AuthorizedClientManager`**.

One notable point: even though the manager is **reactive**, its input parameter is still **`OAuth2AuthorizeRequest`** — a synchronous object describing the request. The result of calling the manager is the reactive publisher:

~~~java
Mono<OAuth2AuthorizedClient> result =
        reactiveAuthorizedClientManager.authorize(authorizeRequest);
~~~

The manager is not simply an HTTP client calling the token endpoint. It coordinates the **client registration**, **principal**, **stored authorized client**, and **provider for the OAuth grant**. A call to `authorize(...)` can create a new authorized client, return an existing token, refresh a token, or emit nothing when authorization cannot be performed in that context.

After this lesson, you will be able to:

1. Understand the exact contract of `ReactiveOAuth2AuthorizedClientManager.authorize(OAuth2AuthorizeRequest)`.
2. Distinguish `OAuth2AuthorizeRequest` from `OAuth2AuthorizationRequest` in the redirect flow.
3. Build an `OAuth2AuthorizeRequest` with the registration ID, principal, and required context attributes.
4. Choose `DefaultReactiveOAuth2AuthorizedClientManager` for WebFlux HTTP requests and `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` for non-request tasks.
5. Understand the roles of `ReactiveOAuth2AuthorizedClientProvider`, `ReactiveClientRegistrationRepository`, `ServerOAuth2AuthorizedClientRepository`, and `ReactiveOAuth2AuthorizedClientService`.
6. Configure the manager to handle `authorization_code`, `refresh_token`, and `client_credentials` appropriately for the environment.
7. Compose `Mono<OAuth2AuthorizedClient>` into controllers, services, and `WebClient` without calling `block()` or `subscribe()` arbitrarily.
8. Handle `Mono.empty()`, token endpoint errors, refresh token rotation, concurrent requests, and isolation between principals.
9. Distinguish access tokens, ID tokens, and OIDC principals to avoid using the wrong token when calling an API.

## 1. Scenario: WebFlux Portal Calling the Orders API

Suppose there is an **Employee Portal** built with Spring Boot WebFlux. Employees sign in through an OpenID Provider (OP), and the Portal needs an access token to call the **Orders API**.

~~~mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Browser as Browser
    participant Portal as WebFlux Portal
    participant OP as OpenID Provider
    participant Store as Authorized Client Store
    participant Orders as Orders API
    User->>Browser: Visit /api/orders
    Browser->>Portal: HTTP request
    Portal-->>Browser: Redirect to OIDC if not signed in
    Browser->>OP: Authorization Request
    OP-->>Browser: Authorization Code
    Browser->>Portal: Callback
    Portal->>OP: Exchange code for tokens
    OP-->>Portal: ID token, access token
    Note over Portal: Create Authentication and OidcUser
    Portal->>Store: Save authorized client
    Browser->>Portal: Subsequent request
    Portal->>Store: Look up authorized client
    Store-->>Portal: Access token and refresh token if present
    Portal->>Orders: Bearer access token for Orders API
    Orders-->>Portal: List of orders
    Portal-->>Browser: HTTP response
~~~

The Portal has two distinct needs:

- **Authentication**: knowing which user is accessing the Portal.
- **OAuth 2.0 Client authorization**: having an appropriate access token to call the Orders API.

`ReactiveOAuth2AuthorizedClientManager` primarily addresses the second part: managing **OAuth2AuthorizedClient** state and coordinating authorization/reauthorization.

### 1.1. Not Every Call to the Manager Sends a Request to the OP

For example:

~~~text
09:00  Alice logs in, Portal receives access token A1
09:02  Manager finds A1 in repository -> reuses A1
09:05  Manager can still reuse A1
09:10  A1 is close to expiration -> provider attempts refresh using R1 if issued
09:11  Stores A2/R2 or A2/R1 depending on response and AS policy
09:12  Next call uses the updated authorized client
~~~

The timestamps are illustrative only. The key point is that calling `authorize(...)` **does not mean always starting a new OIDC Login**.

## 2. Five Core Objects

| Object | Responsibility | Is it reactive? |
|---|---|---|
| `OAuth2AuthorizeRequest` | Describes the registration, principal, and context attributes of an authorize request | No, it is an input object |
| `ReactiveOAuth2AuthorizedClientManager` | Coordinates authorization/reuse/reauthorization | Yes, returns `Mono<OAuth2AuthorizedClient>` |
| `ReactiveOAuth2AuthorizedClientProvider` | Executes the appropriate grant or reauthorization | Yes, participates in the reactive pipeline |
| `OAuth2AuthorizedClient` | Authorized client state: access token and possibly refresh token | Data object, not a publisher |
| Repository/service storing authorized clients | Stores and retrieves authorized clients | Reactive API when using the WebFlux stack |

### 2.1. `ClientRegistration` Is Not a User's Token

`ClientRegistration` describes a client registered with an Authorization Server:

~~~text
registrationId = corporate
clientId = employee-portal
authorizationGrantType = authorization_code
scopes = openid profile orders.read
provider = company-oidc
~~~

A client registration can exist before Alice logs in. It does **not** contain Alice's access token.

### 2.2. `OAuth2AuthorizedClient` Is the Authorized Result

An authorized client has the conceptual structure:

~~~text
OAuth2AuthorizedClient
├── clientRegistration = corporate
├── principalName = alice
├── accessToken = A1
│   ├── issuedAt = ...
│   └── expiresAt = ...
└── refreshToken = R1 (if issued by AS)
~~~

Tokens may be reused or updated, but they must remain bound to the right principal/registration and Resource Server.

### 2.3. `OAuth2AuthorizeRequest` Only Describes the Request

For example:

~~~java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest
                .withClientRegistrationId("corporate")
                .principal(authentication)
                .build();
~~~

This code **has not performed authorization yet** and has not produced a token. It only builds a request to pass into the manager.

### 2.4. `ReactiveOAuth2AuthorizedClientManager` Returns a Publisher

~~~java
Mono<OAuth2AuthorizedClient> authorizedClientMono =
        manager.authorize(request);
~~~

When the publisher is subscribed to in the appropriate context, the manager looks up the authorized client, coordinates with providers, and emits the result or an error. Do not try to extract the token by forcing the `Mono` into a synchronous `OAuth2AuthorizedClient`.

### 2.5. The Provider Decides Which Grant Can Be Handled

Typical providers support:

- `authorization_code`.
- `refresh_token`.
- `client_credentials`.

The mere presence of a provider does not mean that grant is allowed for every registration. `ClientRegistration.getAuthorizationGrantType()` and the authorization context must match the provider.

## 3. The Contract of `ReactiveOAuth2AuthorizedClientManager`

Main interface:

~~~java
package org.springframework.security.oauth2.client;

public interface ReactiveOAuth2AuthorizedClientManager {
    Mono<OAuth2AuthorizedClient> authorize(
            OAuth2AuthorizeRequest authorizeRequest);
}
~~~

This is an abbreviated signature to explain the API.

### 3.1. Input: an `OAuth2AuthorizeRequest`

The request provides at least:

- The client registration or registration ID to authorize.
- The principal representing the user/service.
- Context attributes needed for the manager/provider to operate.

For example, `ServerWebExchange` can be passed via attributes in a WebFlux request.

### 3.2. Output: `Mono<OAuth2AuthorizedClient>`

There are three result types to understand:

| Result | Meaning |
|---|---|
| `Mono` emits an authorized client | An authorized client state is available for the application to use |
| `Mono.empty()` | No authorized client was created/returned in this context |
| `Mono.error(...)` | Authorization/reauthorization encountered an error |

**Do not confuse empty with error.** `Mono.empty()` contains no object on which to call `getAccessToken()`; whereas `Mono.error(...)` must be handled according to the application's policy.

### 3.3. The Manager May Return a Stored Client

An existing authorized client may be returned as-is if the token is still usable and the provider does not need or cannot perform reauthorization.

Therefore:

~~~text
manager.authorize(request)
  -> existing authorized client
  -> provider does not perform a new authorization
  -> returns stored authorized client
~~~

A call to `authorize()` does not automatically prove that an HTTP token request was sent to the Authorization Server.

### 3.4. When There Is No Authorized Client

The manager checks whether the provider chain can execute an appropriate grant. For example:

- `client_credentials` can request a token in the backend.
- `refresh_token` has no effect if no refresh token has ever been obtained.
- `authorization_code` requires the proper interactive flow; a single manager call in a background job cannot automatically open a browser and complete a callback.

## 4. Distinguishing Two Similar-Sounding Names

| Name | Role |
|---|---|
| `OAuth2AuthorizeRequest` | Internal request passed to the authorized client manager |
| `OAuth2AuthorizationRequest` | Protocol Authorization Request, typically used when redirecting the browser to the authorization endpoint |
| `OAuth2AuthorizedClient` | Result representing a client that has been granted tokens |
| `OAuth2AccessTokenResponse` | Token endpoint response after a token request |
| `OAuth2AuthorizationContext` | Context passed to providers when evaluating authorize/reauthorize |

### 4.1. `OAuth2AuthorizationRequest` in the Authorization Code Flow

An authorization request to the OP may contain:

~~~text
response_type = code
client_id = employee-portal
redirect_uri = https://portal.example.com/login/oauth2/code/corporate
scope = openid profile orders.read
state = random-correlated-value
code_challenge = ... (if using PKCE)
nonce = ... (if using OIDC)
~~~

It relates to browser redirects, state correlation, PKCE/nonce, and callbacks.

### 4.2. `OAuth2AuthorizeRequest` in Application Code

A manager request may contain:

~~~text
clientRegistrationId = corporate
principal = Alice's Authentication
attributes = { ServerWebExchange: current request }
~~~

It helps Spring Security identify the client/principal and context needed to find or issue an authorized client.

**Do not store these two objects in the same repository.** An Authorization Request awaiting a callback and an authorized client holding tokens are two different kinds of state.

## 5. Processing Flow of the Reactive Manager

~~~mermaid
flowchart TD
    A["App creates OAuth2AuthorizeRequest"] --> B["ReactiveOAuth2AuthorizedClientManager.authorize"]
    B --> C["Look up ClientRegistration"]
    C --> D["Look up existing OAuth2AuthorizedClient"]
    D --> E["Create OAuth2AuthorizationContext"]
    E --> F["ReactiveOAuth2AuthorizedClientProvider chain"]
    F --> G{"Can create/exchange authorized client?"}
    G -->|Yes| H["Execute grant or refresh"]
    H --> I["Save authorized client via success handler"]
    I --> J["New/updated Mono<OAuth2AuthorizedClient>"]
    G -->|No| K{"Existing stored client present?"}
    K -->|Yes| L["Mono emits existing authorized client"]
    K -->|No| M["Mono.empty or ineligible result"]
    H -->|Error| N["Mono.error and failure handling"]
~~~

The diagram is a conceptual model, not a claim that every provider always performs a token request.

The existence of an authorized client does not guarantee the token will be accepted by every Resource Server: the API still needs to validate issuer, audience, scope, and business permissions.

## 6. Choosing the Right Manager Implementation

Spring Security Reactive provides two key choices:

1. **`DefaultReactiveOAuth2AuthorizedClientManager`**: for processing in a **WebFlux HTTP request** context.
2. **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`**: for processing **outside a `ServerWebExchange`**, such as a scheduled job or backend service.

### 6.1. Quick Comparison

| Aspect | `DefaultReactiveOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
|---|---|---|
| Primary context | WebFlux HTTP request | Background/non-web |
| Registration config | `ReactiveClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| Authorized client store | `ServerOAuth2AuthorizedClientRepository` | `ReactiveOAuth2AuthorizedClientService` |
| May require ServerWebExchange | Yes, because the repository is web-request scoped | No |
| Suitable for UI OIDC Login | Yes, when login/client are properly configured | Does not handle browser login itself |
| Suitable for client credentials job | Can be used if executed within an HTTP request | Better suited |
| Manager input | `OAuth2AuthorizeRequest` | `OAuth2AuthorizeRequest` |
| Result | `Mono<OAuth2AuthorizedClient>` | `Mono<OAuth2AuthorizedClient>` |

Both implementations share the same interface but have different contracts regarding **context and storage**.

### 6.2. Do Not Confuse with the Servlet Manager

In the Servlet stack there is:

~~~java
org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager
~~~

This is a **synchronous** manager using `OAuth2AuthorizedClientRepository` with `HttpServletRequest`/`HttpServletResponse`.

WebFlux uses the **Reactive** manager, `ServerWebExchange`, and the corresponding reactive repository/service. Do not take a Servlet manager and wrap it in `Mono.fromCallable(...)` expecting it to be a proper reactive solution.

## 7. Configuring a Spring Boot WebFlux Project

### 7.1. Maven Dependencies

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

This is a Reactive stack example. If a project places both Spring MVC and WebFlux starters on the classpath, you must clearly verify which web application type Spring Boot is running; do not assume every controller is WebFlux just because the WebFlux dependency is present.

### 7.2. Registering an OIDC Client

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

Here:

- `corporate` is the internal registration ID.
- `client-id`/`client-secret` must match the registration at the OP.
- `authorization_code` is the grant for interactive login.
- `openid` requests OpenID Connect.
- `orders.read` is an illustrative API scope; the AS must support and issue it appropriately.
- `issuer-uri` helps identify the trusted OP.

Secrets must be sourced from the environment or a secret manager; never commit real values to the repository.

### 7.3. WebFlux SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/", "/health", "/error").permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }
}
~~~

`oauth2Login()` supports OIDC/OAuth2 browser login, while `oauth2Client()` supports client authorization and using tokens for outbound requests.

In a real application, only permit appropriate public endpoints and retain CSRF protection for browser cookie/session-based requests when needed.

## 8. Configuring `DefaultReactiveOAuth2AuthorizedClientManager`

Class:

~~~java
org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager
~~~

It uses:

- `ReactiveClientRegistrationRepository` to look up registrations.
- `ServerOAuth2AuthorizedClientRepository` to store/retrieve authorized clients in the WebFlux context.
- `ReactiveOAuth2AuthorizedClientProvider` to handle grants.

### 8.1. A Web Manager with a Provider Chain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
public class WebAuthorizedClientManagerConfig {

    @Bean("webAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager webAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .clientCredentials()
                        .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
                new DefaultReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Explanation:

1. The manager knows about the client registrations.
2. The authorized client repository manages state in the request/WebSession or service depending on the implementation.
3. The provider chain allows handling the appropriate grants.
4. When an authorized client is updated, the manager can use a success handler to save it.
5. No provider "automatically converts" an `authorization_code` registration into `client_credentials` if the AS does not allow it.

### 8.2. Do Not Declare Redundant Beans if Auto-Configuration Already Suffices

Spring Boot/Spring Security may provide default beans depending on classpath, version, and configuration. You do not necessarily need to write a custom manager for every project.

Only create a dedicated manager when you need to customize the provider chain, token client, success/failure handlers, or where authorized clients are stored. If you declare two managers of the same interface, use `@Qualifier` to select the right bean.

## 9. Building `OAuth2AuthorizeRequest` in a WebFlux HTTP Request

A WebFlux controller can access `ServerWebExchange` to obtain the authenticated principal and pass the exchange as a context attribute.

### 9.1. Direct Example from a Controller

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class AuthorizedClientStatusController {

    private final ReactiveOAuth2AuthorizedClientManager manager;

    public AuthorizedClientStatusController(
            @Qualifier("webAuthorizedClientManager")
            ReactiveOAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @GetMapping("/api/client-status")
    Mono<ClientStatus> clientStatus(ServerWebExchange exchange) {
        return exchange.getPrincipal()
                .cast(Authentication.class)
                .flatMap(authentication -> {
                    OAuth2AuthorizeRequest request =
                            OAuth2AuthorizeRequest
                                    .withClientRegistrationId("corporate")
                                    .principal(authentication)
                                    .attribute(
                                            ServerWebExchange.class.getName(),
                                            exchange)
                                    .build();

                    return manager.authorize(request);
                })
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.UNAUTHORIZED,
                                "Authorization required")))
                .map(client -> new ClientStatus(
                        client.getClientRegistration()
                                .getRegistrationId(),
                        client.getAccessToken() != null));
    }

    record ClientStatus(
            String registrationId,
            boolean accessTokenPresent) {}
}
~~~

In this example, the endpoint is protected by `SecurityWebFilterChain` and assumes the principal provided by Spring Security is an `Authentication`. If the app supports other principal types, handle the appropriate types accordingly.

### 9.2. Why Is the `ServerWebExchange` Attribute Needed?

`DefaultReactiveOAuth2AuthorizedClientManager` uses a WebFlux request-scoped repository. `OAuth2AuthorizeRequest` can pass `ServerWebExchange` through attributes so the manager has the context to load/save the authorized client.

~~~java
.attribute(ServerWebExchange.class.getName(), exchange)
~~~

This is an **internal context attribute inside the authorize request**, not an OAuth claim, scope, or parameter sent to the token endpoint.

If the manager lacks the required WebFlux request context, it may fail to interact with the repository as expected. Always use the right manager for the right environment.

### 9.3. When Should `principal(Authentication)` Be Used?

`OAuth2AuthorizeRequest.Builder` allows attaching an `Authentication` principal. For web requests, obtain it from the authenticated Spring Security/`ServerWebExchange`.

Do not read a principal name from a query parameter and build a request on behalf of another user:

~~~text
GET /api/orders?principalName=admin
~~~

Such input must never be treated as proof that the user is authorized to use the admin's authorized client.

### 9.4. What If the Manager Returns `Mono.empty()`?

`switchIfEmpty(...)` allows converting an empty result into a controlled application response.

Depending on business requirements, you can:

- Return 401 if required authorization is missing.
- Initiate a deliberate login/consent flow.
- Return an integration error if the registration/provider is misconfigured.

Never turn an empty result into a fake access token.

## 10. Why Not Call `block()` or `subscribe()` Manually?

An incorrect pattern in a WebFlux request handler:

~~~java
OAuth2AuthorizedClient client =
        manager.authorize(request).block();
~~~

`block()` waits synchronously for the result, which can block the event loop and break the intended reactive design. Do not use it in the non-blocking request path just to "get the object easily".

Another error-prone pattern:

~~~java
manager.authorize(request)
        .subscribe(client -> callApi(client));
~~~

Creating a manual subscription causes:

- The HTTP response to no longer be coordinated by the main publisher.
- Exceptions to potentially escape the request-handling chain.
- Context propagation to behave unexpectedly.
- The API call to become a hard-to-control side effect.
- Tests to become difficult to synchronize for completion.

**Return `Mono`/`Flux` or use `flatMap` to compose instead.**

### 10.1. Composing the Manager with WebClient

~~~java
Mono<String> orders = manager.authorize(request)
        .switchIfEmpty(Mono.error(
                new IllegalStateException("No authorized client")))
        .flatMap(client ->
                ordersWebClient.get()
                        .uri("/api/orders")
                        .headers(headers -> headers.setBearerAuth(
                                client.getAccessToken().getTokenValue()))
                        .retrieve()
                        .bodyToMono(String.class));
~~~

Here `ordersWebClient` is a `WebClient` configured to call only the trusted Orders API. This example demonstrates publisher composition, not a complete production refresh and URL validation workflow.

### 10.2. Do Not Misuse `Mono.just(...)`

`Mono.just(client)` is only appropriate when you already have a synchronous client object, not as a replacement for `manager.authorize(...)`.

Do not write:

~~~java
return Mono.just(manager.authorize(request));
~~~

because the result becomes `Mono<Mono<OAuth2AuthorizedClient>>`, not a resolved authorized client.

## 11. What Can `OAuth2AuthorizeRequest` Contain?

A common request builder:

~~~java
OAuth2AuthorizeRequest authorizeRequest =
        OAuth2AuthorizeRequest
                .withClientRegistrationId("corporate")
                .principal(authentication)
                .attribute(
                        ServerWebExchange.class.getName(),
                        exchange)
                .build();
~~~

### 11.1. Registration ID

`withClientRegistrationId("corporate")` selects a configured client registration.

If an application has multiple registrations:

~~~text
corporate         -> Employee OIDC Login
reporting-service -> client_credentials for reporting job
billing           -> dedicated client for Billing API
~~~

never assume all registrations share the same scopes/audience.

### 11.2. Principal

`principal(authentication)` supplies the Authentication associated with the request. For background tasks, a request may use a technical principal name:

~~~java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest
                .withClientRegistrationId("reporting-service")
                .principal("reporting-job")
                .build();
~~~

`reporting-job` is a technical identifier used to store the authorized client; **it does not mean an End-User named reporting-job logged in via OIDC**.

### 11.3. Attributes

`attribute(...)` lets you pass contextual values needed by the manager/provider.

Do not treat attributes as a place to accept unverified OAuth data from users. They are inputs that can influence authorization, so they must come from trusted application components.

### 11.4. Using an Existing Authorized Client

The `OAuth2AuthorizeRequest` builder also supports initializing from an existing `OAuth2AuthorizedClient` when the use case fits. In that case, ensure the client belongs to the correct principal/registration, and never use an object supplied directly by the browser.

Conceptual example:

~~~java
OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest
                .withAuthorizedClient(existingClient)
                .principal(authentication)
                .build();
~~~

Do not pass Alice's authorized client with Bob's Authentication just because they share the same registration ID.

## 12. Provider Chain: Authorization Code, Refresh Token, Client Credentials

### 12.1. Building a Reactive Provider Chain

~~~java
ReactiveOAuth2AuthorizedClientProvider provider =
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();
~~~

Providers react to specific conditions. Having a provider in the chain **does not mean that grant will always be executed**.

### 12.2. Authorization Code

For WebFlux OIDC Login:

1. The browser is redirected to the OP.
2. The OP authenticates/consents according to policy.
3. The browser returns to the callback with an authorization code.
4. Spring Security completes the token exchange, validates the ID token, and saves the authorized client.

Having `authorizationCode()` in the provider chain does not automatically turn every manager call into a full browser redirect/callback. The interactive flow requires WebFlux OAuth2 Login filters and an authorization request repository.

### 12.3. Refresh Token

If the authorized client has a refresh token and the access token needs refreshing, `refreshToken()` can send a refresh-token grant and return an updated authorized client.

If a successful refresh response **does not issue a new refresh token**, the provider normally keeps the old refresh token; if the AS issues a new one, it updates according to rotation.

A new access token **does not itself prove the user just re-authenticated at the OP**.

### 12.4. Client Credentials

For background services, `clientCredentials()` can acquire an initial access token or obtain a new one when the previous token is no longer usable.

It represents the **client/service**, not an End-User OIDC Login.

### 12.5. No Suitable Provider

If a registration uses `authorization_code` but the chain only has `clientCredentials()`, the manager cannot acquire a token on its own for that registration.

If `refreshToken()` is present but the authorized client has never had a refresh token, the refresh provider cannot create a new token either.

**The grant, registration, and provider chain must be compatible.**

## 13. Manager for Background Jobs Without a WebFlux Request

Class:

~~~java
org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
~~~

This manager uses:

- `ReactiveClientRegistrationRepository`.
- `ReactiveOAuth2AuthorizedClientService`.

It is suitable for scheduled tasks, message consumers, or services without a `ServerWebExchange`.

### 13.1. Registration Using Client Credentials

Example added to `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: company-auth
            client-id: ${REPORTING_CLIENT_ID}
            client-secret: ${REPORTING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company-auth:
            token-uri: https://id.example.com/oauth2/token
~~~

`reporting-service` is not an OIDC Login; it does not need `openid` or a browser redirect URI.

### 13.2. Configuring the Manager for a Service

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class BackgroundAuthorizedClientConfig {

    @Bean("backgroundAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager backgroundManager(
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

No Servlet HttpSession or ServerWebExchange is needed. The authorized client is managed by registration/principal in the service.

### 13.3. Using the Manager in a Reactive Service

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReportingTokenService {

    private final ReactiveOAuth2AuthorizedClientManager manager;

    public ReportingTokenService(
            @Qualifier("backgroundAuthorizedClientManager")
            ReactiveOAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public Mono<String> accessToken() {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId("reporting-service")
                        .principal("reporting-job")
                        .build();

        return manager.authorize(request)
                .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                                "No token for reporting-service")))
                .map(client -> client.getAccessToken().getTokenValue());
    }
}
~~~

This pattern returns `Mono<String>` for other services to compose, without calling `block()` or `subscribe()`.

**In production, avoid exposing access tokens to the frontend or logs.** It is usually better to use the manager inside a dedicated HTTP client calling the Reporting API directly.

### 13.4. Technical Principals and Token Sharing

Multiple jobs can share the same principal name `reporting-job` and registration `reporting-service`, thereby sharing the authorized client in the backing store if designed that way.

You need to decide:

- Does each job require its own scope/audience?
- Is protection against concurrent token requests needed?
- How are tokens stored across multiple instances?
- How is cleanup handled when a client secret rotates or a token is revoked?

Do not use an arbitrary user's principal name as a service principal.

## 14. Differences Between the WebFlux Repository and Authorized Client Service

### 14.1. `ServerOAuth2AuthorizedClientRepository`

This repository operates in the WebFlux server context and can interact with the request, principal, and `ServerWebExchange`. The concrete implementation determines whether state is stored in `WebSession` or backed by a service/identity.

### 14.2. `ReactiveOAuth2AuthorizedClientService`

The service can save and load authorized clients by registration ID and principal name using a reactive API. It does not require `ServerWebExchange` to operate.

### 14.3. Storage Options

| Requirement | Recommended direction |
|---|---|
| UI OIDC Login using WebSession | Appropriate WebFlux authorized client repository |
| Authenticated user, stored by principal | Repository combined with a reactive service where appropriate |
| Scheduled job without HTTP request | Reactive authorized client service + service manager |
| Multiple instances needing to share tokens | Shared backing store with concurrency protection |
| Token only needed for one browser session | Session-backed repository if policy allows |
| Login/logout/account switch | Consistent cleanup and principal binding |

**Do not confuse WebFlux's `WebSession` with Servlet's `HttpSession`.** The reactive stack uses its own abstractions and does not need a Servlet request.

### 14.4. Having an Authentication in Session Does Not Always Mean an Authorized Client Exists

A user may already be logged into the Portal yet:

- Has not been granted a token for the target API.
- The access token has expired.
- No refresh token was issued.
- The authorized client lives in a different service store.
- The Resource Server rejects the audience/scope.

Authentication and authorized client are two separate states.

## 15. Using `WebClient` with the Reactive Manager

`WebClient` is Spring WebFlux's non-blocking HTTP client. It can use an access token in two ways:

1. Compose `manager.authorize(request)` and set the Bearer header manually.
2. Use `ServerOAuth2AuthorizedClientExchangeFilterFunction` for OAuth2 client integration.

### 15.1. Composing `Mono` Directly

~~~java
public Mono<String> orders(
        OAuth2AuthorizeRequest authorizeRequest) {

    return manager.authorize(authorizeRequest)
            .switchIfEmpty(Mono.error(
                    new IllegalStateException(
                            "Orders authorization required")))
            .flatMap(client -> ordersWebClient.get()
                    .uri("/api/orders")
                    .headers(headers -> headers.setBearerAuth(
                            client.getAccessToken().getTokenValue()))
                    .retrieve()
                    .bodyToMono(String.class));
}
~~~

This example assumes `ordersWebClient` has a trusted base URL and does not send tokens to arbitrary URLs.

Composing with `flatMap` keeps the flow asynchronous and lets upstream handle results/errors.

### 15.2. OAuth2 Integration with `ServerOAuth2AuthorizedClientExchangeFilterFunction`

Class:

~~~java
org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction
~~~

Example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OrdersWebClientConfig {

    @Bean
    WebClient ordersWebClient(
            ReactiveOAuth2AuthorizedClientManager manager) {

        var oauth2 =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                        manager);

        return WebClient.builder()
                .baseUrl("https://orders-api.example.com")
                .filter(oauth2)
                .build();
    }
}
~~~

If there are multiple manager beans, add `@Qualifier` so WebClient uses the right web or service manager.

A request can specify the registration:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> result = ordersWebClient.get()
        .uri("/api/orders")
        .attributes(clientRegistrationId("corporate"))
        .retrieve()
        .bodyToMono(String.class);
~~~

When using a manager that depends on a WebFlux request, ensure `ServerWebExchange`/principal context is provided through the corresponding integration. If calling outside a request, use the service manager.

### 15.3. Do Not Automatically Send Tokens to Arbitrary URLs

If the application uses an OAuth2 filter that attaches tokens by registration, avoid using that same WebClient as a generic HTTP client for arbitrarily supplied URLs.

Only send tokens to allowed hosts matching the expected resource/audience/scope. A request following redirects or using a full absolute URI can risk credential leakage if URLs and HTTP clients are not tightly controlled.

### 15.4. Using an Authorized Client Directly

When the caller already has a valid `OAuth2AuthorizedClient`, `ServerOAuth2AuthorizedClientExchangeFilterFunction` can also use that authorized client via the corresponding request attribute. Even so, verify that the authorized client belongs to the correct user/client registration.

Never use User A's authorized client for User B just because both call the same API.

## 16. Reactor Context and WebFlux Authentication

### 16.1. Reactive SecurityContext

In Spring WebFlux, Authentication can be accessed via:

~~~java
ReactiveSecurityContextHolder.getContext()
~~~

The result is:

~~~java
Mono<SecurityContext>
~~~

Never assume `SecurityContextHolder.getContext()` (typically backed by ThreadLocal in Servlet) will work properly across reactive operators.

### 16.2. Creating an Authorize Request from Reactive Context

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import reactor.core.publisher.Mono;

Mono<OAuth2AuthorizedClient> currentUserClient() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .flatMap(authentication ->
                    manager.authorize(
                            OAuth2AuthorizeRequest
                                    .withClientRegistrationId("corporate")
                                    .principal(authentication)
                                    .build()));
}
~~~

This example illustrates retrieving the principal without relying on ThreadLocal.

**Important:** if you are using `DefaultReactiveOAuth2AuthorizedClientManager` with a repository that requires `ServerWebExchange`, you still must ensure the exchange is provided in the appropriate request context. Retrieving Authentication alone does not guarantee sufficient context for every repository.

### 16.3. Why Context Matters to the Manager

A reactive pipeline can switch schedulers. Reactor Context travels with the subscriber/publisher via Reactor mechanisms, rather than as a global variable shared across requests.

When the manager and WebClient are composed in the same pipeline, context can be preserved according to reactive rules. If you manually start a new subscription or jump through non-Reactor callbacks without propagating context, components may not see the principal/exchange as expected.

### 16.4. Passing Identity Explicitly

For domain services, it may be cleaner to extract the verified identity at the request boundary and pass an immutable DTO (such as issuer + subject or internal user ID) into the service.

However, passing a DTO does not replace `Authentication` if the manager/repository needs the actual principal to fetch tokens. Keep responsibilities clear: **identity for business logic** and **principal for the authorized client manager**.

## 17. `oauth2Login()` vs `oauth2Client()`

In WebFlux:

- `oauth2Login()` handles browser authentication via OAuth 2.0 Login/OIDC.
- `oauth2Client()` provides OAuth2 client support so the application can use authorized clients/access tokens.

### 17.1. Login Does Not Automatically Issue Tokens for Every Resource Server

A user may be logged into the Portal yet still need a separate access token for the Orders API, with scopes/audience defined by the AS and API.

Never use an ID token as an API access token just because OIDC Login succeeded.

### 17.2. Successful Login Does Not Guarantee a Refresh Token Exists

The AS may or may not issue a refresh token depending on policy, scopes/consent, and client type. When the access token expires without a refresh token, the manager cannot manufacture a refresh token.

A new interactive authorization may be required if the application allows it.

### 17.3. Background Client Credentials Is Not OIDC Login

A scheduled job using `client_credentials` typically has no `OidcUser`, ID token, or WebSession. The token represents the client/service.

Do not attach a random user's principal to a service authorization request.

## 18. How the Manager and Providers Decide When to Refresh

### 18.1. When the Access Token Is Still Valid

The provider chain may skip reauthorization, and the manager returns the stored authorized client. No token endpoint request is necessarily made.

### 18.2. When the Token Is Expired or About to Expire

The refresh provider can check `expiresAt` and clock skew, then use the refresh token if present.

~~~text
A1 close to expiration
R1 still valid
  -> refresh_token grant
  -> A2 and possibly R2
  -> store updated authorized client
~~~

### 18.3. When the Response Does Not Issue a New Refresh Token

If the AS returns A2 without R2, the Spring Security refresh provider normally preserves the existing R1 when creating the updated authorized client.

If the AS issues R2, R1 must be replaced with R2 according to the token rotation policy.

### 18.4. When Refresh Is Not Possible

If R1 is expired/revoked or the AS returns `invalid_grant`, the application must handle the failure. Do not retry infinitely with the same R1, and do not substitute an ID token for a refresh token.

### 18.5. A New Token Does Not Imply OIDC Reauthentication

A refreshed access token does not prove the End-User just performed MFA or re-entered their password.

If business logic requires authentication freshness/step-up, use an appropriate OIDC Authentication Request (for example `max_age`, `prompt=login`, `acr_values`) and verify the result according to policy.

## 19. Empty Results, Errors, and HTTP API Failures

### 19.1. `Mono.empty()`

The manager has no authorized client and the provider chain cannot authorize in the current context.

The application can use:

~~~java
return manager.authorize(request)
        .switchIfEmpty(Mono.error(
                new IllegalStateException(
                        "Client authorization unavailable")));
~~~

In a WebFlux controller, this can be mapped to a `ResponseStatusException` with an appropriate HTTP status per the API contract.

### 19.2. `Mono.error(...)`

The token endpoint can reject authorization, for example:

- `invalid_client`: invalid client authentication.
- `invalid_grant`: refresh token expired, revoked, or invalid.
- Network timeout.
- Misconfigured provider/registration.
- Failure handler or repository error.

Do not conflate an AS configuration error with "user not logged in".

### 19.3. API Returns 401

Even after the manager returns an access token, the Resource Server may return 401 if the token has the wrong audience/issuer, is expired, revoked, or unacceptable.

The manager does not automatically know about every API error unless WebClient is integrated with appropriate failure handling. Inspect HTTP responses and your authorized client management policy.

### 19.4. API Returns 403

403 usually relates to authorization/scope/ownership. Refreshing a token does not by default grant additional permissions.

Do not handle every 401/403 by deleting the authorized client or unconditionally refreshing.

### 19.5. Avoid Retrying Requests with Side Effects

If a payment POST fails, refreshing the token and retrying must account for idempotency. Never loop a POST infinitely after a timeout or an uncertain failure.

## 20. Authorization Success/Failure Handlers

The manager can use an authorization success handler to save a new or updated authorized client into the repository/service.

### 20.1. After a Successful Refresh

If the AS returns A2/R2, the handler must ensure the updated state is saved under the right registration/principal. If the next request reads from a different store, it might still see A1/R1.

### 20.2. On `invalid_grant`

Some default Spring Security managers/handlers can remove the authorized client on specific token refresh errors that render the old token unusable. Exact behavior depends on implementation and configuration.

Do not assume every failure automatically deletes the token; nor should you keep an `invalid_grant` token and retry indefinitely.

### 20.3. When Customizing Handlers

If writing a custom success/failure handler:

- Choose the right backing store.
- Maintain principal isolation.
- Never log raw tokens.
- Never delete another user's token.
- Do not assume a network timeout means the refresh token was definitely revoked.
- Handle concurrent updates if multiple requests refresh simultaneously.

## 21. Account Switching and the Risk of Another Principal's Token

Suppose Alice logs into the Portal, and later Bob logs in within the same browser/session.

If the authorized client repository stores tokens per session but fails to clean up properly on principal change, Bob's request could accidentally use Alice's access token.

You must:

1. Identify users by verified OIDC issuer + subject.
2. Bind authorized clients to the correct principal/session.
3. Clean up stale tokens when switching accounts or tenants.
4. Never use a global token cache keyed only by registration ID.
5. Never accept a principal name sent directly by the browser.
6. Enforce authorization checks at the target API.

### 21.1. Different Issuers Can Have Colliding `sub` Values

OIDC `sub` only guarantees uniqueness within a single issuer. If two OPs both issue `sub=12345`, do not assume they are the same user.

When designing identifier keys for a token store, use a trusted internal identity linked to `iss` + `sub` or an equivalent tenant model.

### 21.2. Registration ID Is Not Audience

The same registration ID may appear in code, yet the access token must still be valid for the specific Resource Server. Never send a token intended for the Orders API to the Billing API.

## 22. Refresh Token Rotation and Concurrent Requests

Suppose the authorized client has A1/R1, and the AS uses rotation:

~~~text
Request A: loads A1/R1
Request B: loads A1/R1
Request A: refreshes R1 -> A2/R2
Request B: refreshes R1 -> invalid_grant or reuse detection
~~~

Do not assume the manager/repository guarantees atomic refresh across concurrent requests or multiple nodes.

Under high load, consider:

- Synchronizing/locking by registration + principal/service.
- Appropriate single-flight or locking mechanisms.
- Conditional token writes to avoid overwriting newer tokens with stale ones.
- A shared token store across instances.
- Handling lost refresh responses.
- The AS's rotation and reuse policies.

If a successful refresh response does not issue R2, the provider usually keeps R1. Still, R1 may later expire or be revoked by the AS; do not treat it as valid forever.

## 23. Security Considerations

### 23.1. Tokens Are Sensitive Credentials

Never write to logs or tracing:

~~~text
access_token
refresh_token
id_token
authorization_code
code_verifier
client_secret
WebSession cookie
serialized OAuth2AuthorizedClient
~~~

Prefer logging non-sensitive diagnostics:

~~~text
registrationId=corporate
principalReference=internal-user-id
authorizedClientFound=true
refreshAttempted=true
refreshSucceeded=true
tokenExpiresAt=timestamp
correlationId=...
~~~

### 23.2. Use Access Tokens Only for the Intended API

`OAuth2AuthorizedClient.getAccessToken()` provides the access token for APIs. Never send `OidcUser.getIdToken()` or a refresh token to a Resource Server.

Verify the proper audience/scope and restrict outbound WebClients to trusted hosts only.

### 23.3. Prevent WebClient from Attaching Tokens to Arbitrary URLs

An OAuth2-aware WebClient can automatically attach a bearer token. If the application accepts a full URL from user input and uses that same WebClient, the token could leak to an unintended host.

Separate clients per Resource Server, restrict hosts/redirects, enforce HTTPS, and scope tokens by policy.

### 23.4. Sessions and Logout

WebFlux typically uses `WebSession` and `ServerSecurityContextRepository`. Session logout and local removal of authorized clients do not automatically revoke tokens at the AS.

If authorized clients are stored via `ReactiveOAuth2AuthorizedClientService` outside the session, records may persist after logout unless explicitly cleaned up.

### 23.5. Do Not Treat `Authentication.isAuthenticated()` as Sufficient API Authorization

A legitimately authenticated user still may not view another user's orders. The API must verify ownership, tenant, and business permissions on every request.

## 24. Testing the Reactive Manager

### 24.1. Using `StepVerifier` to Test Publishers

With a manager configured against an appropriate mock token endpoint/service, you can use Reactor Test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class AuthorizedClientManagerTest {

    @Test
    void returnsClientWhenAvailable() {
        // manager and authorizeRequest are created using test fixtures
        StepVerifier.create(manager.authorize(authorizeRequest))
                .assertNext(client -> {
                    assertThat(client.getClientRegistration()
                            .getRegistrationId())
                            .isEqualTo("corporate");
                    assertThat(client.getAccessToken()).isNotNull();
                })
                .verifyComplete();
    }
}
~~~

This is an illustrative test structure; `manager` and `authorizeRequest` are test-provided fixtures, not variables automatically injected by Spring in this example class.

Using `StepVerifier` requires the `reactor-test` dependency in test scope.

### 24.2. Scenarios to Test

| Scenario | Expected behavior |
|---|---|
| Registration has no authorized client, grant supported | Provider acquires token when conditions permit |
| Token still valid | Manager may return existing client |
| Token near expiration, refresh token present | Provider refreshes and stores new token |
| Refresh response has no replacement refresh token | Keeps old refresh token |
| Refresh response includes R2 | Stores R2, does not reuse R1 |
| AS returns `invalid_grant` | Proper failure handling, no infinite retry |
| No suitable provider | Empty/error per contract, no fake token |
| Web manager missing required exchange | Clear context error/handling |
| Background manager runs outside HTTP | Does not require ServerWebExchange |
| Bob's request reading Alice's token | Prevented by principal isolation |
| Two concurrent refresh requests | Does not overwrite newly rotated token |
| WebClient called with wrong host | Does not leak bearer token |

### 24.3. Tests Should Not Call the Production AS

Use a stub/mock HTTP token endpoint or a test Authorization Server in a controlled environment. Never write real tokens into test logs or use real refresh tokens to trigger rotation/reuse errors.

## 25. Troubleshooting

| Symptom | Likely cause | Remediation |
|---|---|---|
| `authorize()` returns `Mono.empty()` | No matching authorized client/provider | Check registration, grant, context |
| Manager missing `ServerWebExchange` | Using web manager outside request or missing attribute | Pass exchange properly or choose service manager |
| Background job fails due to missing session | Using web repository instead of service | Use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| Token missing after login | Repository/service stored elsewhere or flow incomplete | Check wiring and callback |
| Same old token returned repeatedly | Access token is still eligible for use | May be expected behavior |
| Expired token does not refresh | No R1, missing refresh provider, or AS policy | Check provider, grant, token store |
| `invalid_grant` during refresh | Expiry/revocation/rotation/race | Handle failure, do not retry blindly |
| `invalid_client` | Wrong client authentication/config | Check registration, secret, provider |
| `block()` throws error on event loop | Blocking inside reactive request | Compose Mono with flatMap |
| Authentication missing inside operator | Using ThreadLocal or detached subscription | Use ReactiveSecurityContextHolder, preserve pipeline |
| 401 from Resource Server | Wrong audience/issuer/expiry/token profile | Check API validation |
| 403 from Resource Server | Missing permissions/scope/ownership | Do not just refresh token |
| Two instances see different tokens | Store not shared/inconsistent | Use shared reactive service store/session |
| User Bob uses Alice's token | Principal/session isolation bug | Fix storage key/cleanup |
| Token appears in logs | Debug interceptor/tracing capturing headers | Redact credentials |

## 26. Practice Scenarios

### Scenario A: User OIDC Login in WebFlux

Alice logs in successfully and has an `Authentication` and `corporate` authorized client. The controller needs an access token to call the Orders API.

**Approach:** Use the web manager or an OAuth2-aware WebClient with a trusted principal and exchange context. Return `Mono`; do not call `block()`.

### Scenario B: No Authorized Client

The controller calls the manager before completing the browser Authorization Code flow.

**Approach:** Start the interactive authorization flow when appropriate; do not expect the manager to open a browser and complete the callback on its own.

### Scenario C: Scheduled Reporting Job

A job runs hourly and needs a `client_credentials` token.

**Approach:** Use the service manager with technical principal `reporting-job`, the `clientCredentials()` provider, and the reactive authorized client service. No WebSession is needed.

### Scenario D: Expired Access Token

Authorized client has A1/R1; the provider includes `refreshToken()`.

**Approach:** The manager can refresh and store A2/R2 or A2/R1 per the token response. Do not treat refresh as a new login.

### Scenario E: API Returns 403 for Token

The access token has `orders.read`, while the endpoint requires `orders.approve`.

**Approach:** Review scopes and business permissions; refreshing will not elevate privileges.

### Scenario F: Lost Reactor Context

A service manually calls `subscribe()` inside a callback detached from the HTTP request and cannot see the principal.

**Approach:** Return `Mono` for upstream composition; when running independently, use a service identity or pass trusted data explicitly by design.

### Scenario G: Switching Accounts

Alice logs out and Bob logs in using the same browser, yet the old authorized client remains in the store.

**Approach:** Clean up and bind by principal/issuer+subject; never use Alice's token for Bob.

## 27. Self-Check Questions

**Question 1.** What parameter type does `ReactiveOAuth2AuthorizedClientManager.authorize(...)` take?

**Answer:** `OAuth2AuthorizeRequest` — an object describing the registration, principal, and context attributes.

**Question 2.** What type does the method return?

**Answer:** `Mono<OAuth2AuthorizedClient>`, not a synchronous `OAuth2AuthorizedClient`.

**Question 3.** Is `OAuth2AuthorizeRequest` the same as the `OAuth2AuthorizationRequest` sent to the OP?

**Answer:** No. One is an internal request to the manager; the other describes the protocol Authorization Request of the redirect flow.

**Question 4.** Which manager is suitable for WebFlux HTTP requests?

**Answer:** `DefaultReactiveOAuth2AuthorizedClientManager` with `ServerOAuth2AuthorizedClientRepository`.

**Question 5.** Which manager is suitable for a scheduled job without a `ServerWebExchange`?

**Answer:** `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` with `ReactiveOAuth2AuthorizedClientService`.

**Question 6.** Why might `ServerWebExchange` need to be passed via attributes?

**Answer:** So the web manager/repository has the request context needed when loading/saving the authorized client.

**Question 7.** Does calling `authorize()` always call the token endpoint?

**Answer:** No. The manager can return a stored authorized client when reauthorization is not needed.

**Question 8.** Can `refreshToken()` acquire an initial token if no refresh token exists yet?

**Answer:** No. The refresh token grant requires a refresh token already issued by the AS.

**Question 9.** Does `clientCredentials()` represent an OIDC-logged-in user?

**Answer:** No. This grant uses the client/service identity.

**Question 10.** Why should `block()` not be used in a WebFlux controller?

**Answer:** It can block the event loop and break reactive composition; use `flatMap`/`map` instead.

**Question 11.** What should you do when `authorize()` returns `Mono.empty()`?

**Answer:** Handle the missing authorization according to policy, such as with `switchIfEmpty`, rather than using a fake token.

**Question 12.** Does a new access token after refresh prove the user just completed MFA?

**Answer:** No. OIDC reauthentication/step-up requires its own flow and verification.

**Question 13.** If two different providers have the same `sub`, are they guaranteed to be the same user?

**Answer:** No. You must consider the issuer and internal account mapping.

**Question 14.** Can an ID token be used to call the Orders API instead of an access token?

**Answer:** No, not under the standard OAuth Resource Server model.

**Question 15.** Does the manager returning an authorized client replace authorization checks at the API?

**Answer:** No. The Resource Server must still verify the token, audience/scope, and resource permissions.

## Key Takeaways

- **`OAuth2AuthorizeRequest` is the input object, while `ReactiveOAuth2AuthorizedClientManager.authorize(...)` returns `Mono<OAuth2AuthorizedClient>`.** Do not confuse this internal request with the browser redirect `OAuth2AuthorizationRequest`.
- **The manager coordinates the registration, principal, authorized client store, and reactive provider chain.** It may issue an initial token, reuse a token, or reauthorize, rather than always calling the token endpoint.
- **`DefaultReactiveOAuth2AuthorizedClientManager` is for WebFlux web requests** and typically needs `ServerWebExchange` via the appropriate context; **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` is suited for background/non-web workloads**.
- **`ReactiveOAuth2AuthorizedClientProvider` only handles matching grants**, such as Authorization Code, Refresh Token, or Client Credentials. Authorization Code still requires browser redirect/callback.
- **Compose `Mono` in WebFlux; never call `block()` or manual `subscribe()`** to obtain a token on the request path.
- **A `WebClient` carrying an access token must target the right host/audience/scope**; never use an ID token in place of an access token and never send tokens to untrusted URLs.
- **Protect principal isolation, refresh token rotation, concurrency, and the token store**, never log credentials, and never treat local logout as token revocation at the AS.
