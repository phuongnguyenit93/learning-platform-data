# 19.2. Configuring the Filter with an Authorized Client Manager

## 1. The Problem to Solve with WebClient on Servlet

A **Spring Security OAuth 2.0 OIDC Client** application running on **Spring MVC/Servlet** often has two simultaneous needs:

1. Allow users to log in via **OAuth 2.0 Authorization Code / OpenID Connect (OIDC)**.
2. From the backend, send requests to another **Resource Server** using an Access Token issued to the user or to the application itself.

For example: an internal portal lets employees sign in through the enterprise identity provider, then calls the Reports API to read reports that the account is permitted to view.

~~~text
Browser -> Spring MVC portal -> Reports API
             |
             +-- OAuth2/OIDC Login
             |      ID Token: authenticates the user at the portal
             |
             +-- OAuth2 Client
                    Access Token: calls the Reports API
~~~

In Spring Framework, `WebClient` is a **Reactor**-based HTTP client with a fluent API returning `Mono`/`Flux`. Despite having “Web” in its name, `WebClient` can also be used from a **Servlet application** without converting all of Spring MVC to WebFlux.

To avoid having every controller manually load tokens, check expiration, and attach headers, Spring Security provides:

**`ServletOAuth2AuthorizedClientExchangeFilterFunction`**

This filter is attached to `WebClient` as an `ExchangeFilterFunction` and can use an **`OAuth2AuthorizedClientManager`** to obtain the appropriate Access Token for each outbound request.

A central configuration:

~~~java
ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(
        authorizedClientManager);

WebClient webClient = WebClient.builder()
    .apply(oauth2.oauth2Configuration())
    .build();
~~~

**Core idea:** WebClient performs HTTP; the filter selects the authorized client and inserts the Bearer Token; the manager handles loading/re-issuing tokens and persisting authorization state. The Resource Server remains responsible for validating the token, scope, audience, and access policies.

This lesson explains how to wire these components together, provides examples for **delegated user tokens** and **Client Credentials**, and covers passing request attributes, handling invalid tokens, security boundaries, and testing approaches.

## 2. Architecture: Filter, Manager, Provider, and Store

### 2.1. Components with Distinct Responsibilities

| Component | Role in the Flow | What Not to Assign to It |
| --- | --- | --- |
| `WebClient` | Executes asynchronous HTTP requests to the target API | Does not know on its own which OAuth2 token to request |
| `ServletOAuth2AuthorizedClientExchangeFilterFunction` | Attaches the authorized client's Access Token to outbound requests, coordinates with the manager | Not an OIDC authentication provider or a Resource Server |
| `OAuth2AuthorizedClientManager` | Loads authorized clients, re-authorizes/refreshes for matching grants, saves results | Does not enforce business permissions on behalf of the API |
| `OAuth2AuthorizedClientProvider` | Implements specific grants: authorization_code, refresh_token, client_credentials... | Does not independently persist all tokens across requests |
| `OAuth2AuthorizedClientRepository` | Saves/loads/removes authorized clients with Servlet context | Does not send token requests on its own |
| `OAuth2AuthorizedClientService` | Saves/loads/removes by registration + principal without needing a Servlet request | Does not automatically refresh Access Tokens |
| `ClientRegistrationRepository` | Holds registration and provider configuration | Does not hold per-principal Access Tokens |

### 2.2. Data Held by an OAuth2AuthorizedClient

`OAuth2AuthorizedClient` binds together:

~~~text
OAuth2AuthorizedClient
  clientRegistration:
    registrationId = "company"
    clientId = "portal-web"
    authorizationGrantType = authorization_code
  principalName = "employee-123"
  accessToken = <credential; do not log>
  refreshToken = <credential or null>
~~~

The logical key when using `OAuth2AuthorizedClientService` is usually **`(clientRegistrationId, principalName)`**. The same registration can hold separate tokens for Alice and Bob; and there can also be multiple registrations with different scopes/audiences for the same principal.

**An ID Token is not an Access Token.** The ID Token is verified by the OIDC client to log the user in; the filter uses the **Access Token** for HTTP `Authorization: Bearer ...`.

### 2.3. Overall Diagram

~~~mermaid
flowchart TD
    A["Spring MVC Controller / Service"] --> B["WebClient.get/post(...).attributes(...)"]
    B --> C["ServletOAuth2AuthorizedClientExchangeFilterFunction"]
    C --> D["Select authorized client or registration ID"]
    D --> E["OAuth2AuthorizedClientManager.authorize(...)"]
    E --> F["Repository / Service: find stored client"]
    F --> G{"Is Access Token usable?"}
    G -->|Yes| H["Return OAuth2AuthorizedClient"]
    G -->|Not issued / needs refresh| I["OAuth2AuthorizedClientProvider"]
    I --> J["Authorization Server / Token Endpoint"]
    J --> K["Save new authorized client"]
    K --> H
    H --> L["Add Authorization: Bearer access_token"]
    L --> M["Resource Server validates token and policy"]
    M --> N["WebClient receives response / error"]
~~~

The diagram shows a logical model, not a fixed internal order across every Spring Security version. For a token that is still valid, the manager can reuse the stored record; **not every HTTP request calls the Token Endpoint**.

## 3. What Is Special About WebClient in a Servlet Application?

### 3.1. A Servlet Runtime Can Still Use WebClient

Spring MVC uses `DispatcherServlet`, `HttpServletRequest`, and `HttpServletResponse` to handle inbound HTTP. `WebClient` is a reactive-style HTTP client that can be called from Servlet controllers/services to access external APIs.

A synchronous request typically looks like:

~~~java
String json = webClient.get()
    .uri("https://reports.example.net/api/reports")
    .retrieve()
    .bodyToMono(String.class)
    .block();
~~~

In this example, `block()` waits for the result on the Spring MVC thread. This can be suitable when the server already processes requests in a blocking model, though it requires timeouts and performance evaluation. Do not call `block()` on a Reactor event-loop thread, as doing so can cause errors or block the reactive model.

**Using WebClient in a Servlet application does not turn the application into a WebFlux server.** Servlet controllers, `SecurityFilterChain`, and HTTP sessions continue operating on the Servlet stack.

### 3.2. Why Does the Class Name Say Servlet While the Package Contains Reactive?

Full name:

~~~java
org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction
~~~

This class is named `Servlet...` because it works with the **Servlet HTTP context**, while implementing WebClient's `ExchangeFilterFunction` contract.

**Do not confuse** it with:

~~~text
ServerOAuth2AuthorizedClientExchangeFilterFunction
~~~

which is designed for **Reactive WebFlux** environments and the corresponding reactive security components.

### 3.3. Illustrative Dependencies

For Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Brings WebClient and the reactive HTTP client into an MVC application.
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

When both MVC and WebFlux starters are present, Spring Boot normally prefers the **Servlet/MVC server** unless explicitly configured otherwise. This is not a reason to copy a Reactive `SecurityWebFilterChain` into the application; server security still uses `HttpSecurity` and `SecurityFilterChain`.

Spring Boot 4.x has differently modularized starters; choose dependencies compatible with your project's BOM and do not manually mix Spring Security 6.x/7.x.

## 4. Configuring the Filter with OAuth2AuthorizedClientManager: Minimal Version

### 4.1. WebClient Bean

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfig {

    @Bean
    WebClient oauth2WebClient(
            OAuth2AuthorizedClientManager authorizedClientManager) {

        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                authorizedClientManager);

        return WebClient.builder()
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

`oauth2.oauth2Configuration()` configures the **filter** on the builder while adding helpful defaults for the Servlet request context. It is the Spring Security-supported integration approach.

An equivalent configuration can be written explicitly as:

~~~java
WebClient webClient = WebClient.builder()
    .defaultRequest(oauth2.defaultRequest())
    .filter(oauth2)
    .build();
~~~

**Choose one of the two approaches.** Do not use both `.apply(oauth2.oauth2Configuration())` and `.filter(oauth2)` on the same builder, as that can cause the filter to run twice.

### 4.2. Why Just Creating the WebClient Bean Is Not Enough

The filter must know which authorized client to use. It needs at least one valid identification source, such as:

- An authorized client passed directly via `oauth2AuthorizedClient(...)`.
- A `clientRegistrationId(...)` so the manager can look up/issue a token by registration and principal.
- An explicitly enabled default client configuration (requires special caution).

Without a client registration/authorized client and without a valid default, do not expect the filter to magically know which API needs which token.

### 4.3. No Need to Set the Authorization Header Manually

Once the filter resolves an `OAuth2AuthorizedClient`, it uses the Access Token to create:

~~~http
Authorization: Bearer ACCESS_TOKEN_VALUE
~~~

Business code should not both use the filter and set a Bearer header manually:

~~~java
// ANTI-PATTERN: risks duplicate headers or using a token from the wrong source.
webClient.get()
    .uri("https://reports.example.net/api/reports")
    .header("Authorization", "Bearer " + manuallyLoadedToken)
    .attributes(clientRegistrationId("company"))
    .retrieve();
~~~

Pick **one clear mechanism** for credential injection. With the configuration in this lesson, that is the filter and manager.

## 5. Attaching the Right clientRegistrationId to a Request

Spring Security provides the static helper:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
~~~

Usage in a request:

~~~java
String json = webClient.get()
    .uri("https://reports.example.net/api/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class)
    .block();
~~~

`clientRegistrationId("company")` records an **internal attribute on the ClientRequest**, not a URL query parameter and not a scope. The manager uses the registration ID to locate the corresponding client configuration, principal, and authorized client.

### 5.1. Multiple Registrations in One System

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${COMPANY_CLIENT_ID}
            client-secret: ${COMPANY_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, reports.read]
          billing-service:
            provider: billing-auth
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [billing.read]
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
          billing-auth:
            token-uri: https://auth.billing.example.net/oauth2/token
~~~

For a user-delegated token, a request can choose `company`; for a service-to-service token, `billing-service`. However, **never read a registration ID from a browser HTTP request if the user is not allowed to choose it**.

A user may log in with company OIDC without being allowed to use a broad-privilege Client Credentials token to call the Billing API at will.

### 5.2. The Registration ID Must Match the Configuration

~~~text
Spring Boot ClientRegistration:
  registrationId = "company"

WebClient request:
  .attributes(clientRegistrationId("company"))

=> Both names must match.
~~~

If you write `clientRegistrationId("company-oidc")` while the actual registration is `company`, the filter/manager cannot locate the right client. `company-oidc` in the YAML above is only the **provider ID**, not the registration ID.

### 5.3. Prefer Dedicated WebClients for Sensitive APIs

A shared WebClient bean can call multiple hosts. Because an OAuth2 filter can attach tokens, it is usually safer to create dedicated WebClients with fixed `baseUrl` values:

~~~java
WebClient reportsWebClient = WebClient.builder()
    .baseUrl("https://reports.example.net")
    .apply(oauth2.oauth2Configuration())
    .build();
~~~

However, `baseUrl` does not automatically block passing an absolute URL into `uri(...)`; application code must still use only approved paths/hosts and control redirects.

## 6. Passing OAuth2AuthorizedClient Directly via Request Attributes

The filter does not always need to resolve a token via registration ID. If a controller already has a valid `OAuth2AuthorizedClient`, it can pass it directly:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

String json = webClient.get()
    .uri("https://reports.example.net/api/reports")
    .attributes(oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class)
    .block();
~~~

Here `authorizedClient` is provided by Spring Security from a trusted server-side source, such as an annotation:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@RestController
public class ReportController {

    private final WebClient reportsWebClient;

    public ReportController(WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    @GetMapping("/reports/current-user")
    public String myReports(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient authorizedClient) {

        return reportsWebClient.get()
            .uri("/api/reports")
            .attributes(oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(String.class)
            .block();
    }
}
~~~

**Explanation:** the annotation resolver fetches the authorized client within the Spring Security context; the request attribute hands that object to the WebClient filter. WebClient no longer needs to resolve a registration ID because it has been given the exact client.

Note: if the application needs **new tokens upon expiration** and flexible reauthorization, `clientRegistrationId(...)` lets the manager proactively handle the lifecycle. Passing an old authorized client object directly does not mean the token will always be refreshed in every configuration; understand the manager/filter execution path and avoid storing stale token objects in singleton fields.

Never include `OAuth2AuthorizedClient`, Access Tokens, or Refresh Tokens in DTOs returned to the browser.

## 7. Authentication and the Servlet Context

### 7.1. Where Does the Default Authentication Come From?

In a normal Servlet MVC request:

~~~text
Browser
  -> SecurityFilterChain authenticates
  -> SecurityContextHolder holds Authentication
  -> Controller calls WebClient
  -> WebClient defaultRequest() reads current Authentication
  -> manager looks up authorized client by principal
~~~

`oauth2.oauth2Configuration()` can supply the **default Authentication** from `SecurityContextHolder` and the Servlet request/response from `RequestContextHolder`. This convenience keeps WebClient calls inside MVC requests from having to pass every object manually.

**Do not assume `SecurityContextHolder` is available on every thread.** In `@Async`, scheduled tasks, or pipelines using `publishOn(...)`/`subscribeOn(...)`, the executing thread may differ from the Servlet request thread, making ThreadLocal contexts invisible.

### 7.2. Setting Authentication Explicitly

Spring Security provides:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.authentication;
~~~

Example:

~~~java
String json = webClient.get()
    .uri("https://reports.example.net/api/reports")
    .attributes(clientRegistrationId("company"))
    .attributes(authentication(currentAuthentication))
    .retrieve()
    .bodyToMono(String.class)
    .block();
~~~

The `currentAuthentication` variable must come from a trusted server-side context, such as a controller parameter `Authentication authentication` or `SecurityContextHolder` on the right thread.

**Never take a user ID supplied by the browser and build a privileged Authentication to look up someone else's authorized client.**

### 7.3. Passing HttpServletRequest / HttpServletResponse When Truly Needed

For managers using `OAuth2AuthorizedClientRepository`, some operations require the Servlet request/response to load/save tokens in the right session:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.httpServletRequest;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.httpServletResponse;
~~~

Example:

~~~java
webClient.get()
    .uri("https://reports.example.net/api/reports")
    .attributes(clientRegistrationId("company"))
    .attributes(authentication(currentAuthentication))
    .attributes(httpServletRequest(servletRequest))
    .attributes(httpServletResponse(servletResponse))
    .retrieve()
    .bodyToMono(String.class)
    .block();
~~~

`servletRequest`/`servletResponse` are valid `jakarta.servlet.http.HttpServletRequest` and `HttpServletResponse` parameters passed to the controller/service.

In a normal MVC flow, `defaultRequest()` already populates the corresponding context so manual passing is unnecessary; pass them manually only when explicit control, special handling, or testing is needed. **Never store `HttpServletRequest`/`Response` in a singleton to reuse in later requests.**

### 7.4. WebClient Subscription Is Where Context Is Easily Lost

WebClient uses a Reactor pipeline; calling:

~~~java
Mono<String> mono = webClient.get()
    .uri("/api/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
~~~

does not necessarily execute the outbound HTTP call immediately. Subscribing/`block()` triggers the pipeline.

If code creates a `Mono` inside an MVC request and subscribes later on another thread, Servlet ThreadLocals and SecurityContext may no longer match request creation time. To process outside an HTTP request, design explicit authentication/authorized client context and choose a **service manager** when there is no Servlet context, rather than relying on `RequestContextHolder` existing indefinitely.

## 8. Authorized Client Manager: Two Common Configurations

### 8.1. DefaultOAuth2AuthorizedClientManager for Servlet Requests

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();

DefaultOAuth2AuthorizedClientManager manager =
    new DefaultOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientRepository);

manager.setAuthorizedClientProvider(provider);
~~~

This snippet assumes `clientRegistrationRepository` and `authorizedClientRepository` already exist. The manager uses an HTTP-aware repository, suited for browser-based OAuth2/OIDC Login in Servlet.

### 8.2. AuthorizedClientServiceOAuth2AuthorizedClientManager for Backend Tasks

~~~java
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
    new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        authorizedClientService);

manager.setAuthorizedClientProvider(
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build());
~~~

The service manager does not require a Servlet request/response. It fits batch jobs, scheduled jobs, and Client Credentials.

### 8.3. Selection Table

| Criterion | DefaultOAuth2AuthorizedClientManager | AuthorizedClientServiceOAuth2AuthorizedClientManager |
| --- | --- | --- |
| Authorized client source | Repository | Service |
| Bound to Servlet request | Yes | Not needed |
| Can be called from background job | Not recommended without Servlet context | Yes |
| Principal | Authentication/request context | Application-supplied Authentication/principal name |
| Common grants | Authorization Code, Refresh Token | Client Credentials; other compatible grants |
| Persistence component | Repository may delegate to service | Service storing in memory/JDBC/custom |
| WebClient filter wiring | Constructor taking `OAuth2AuthorizedClientManager` | Same constructor taking manager |

**The filter does not care which concrete manager implementation is used as long as the contract matches**. However, choosing the wrong manager can lose Servlet context or mix up end-user and service tokens.

## 9. Example A: WebClient Calling an API on Behalf of an OIDC User

This is a multi-component configuration for **Spring Boot MVC/Servlet**. The snippets are organized by functional file/class; they are not competing `SecurityFilterChain`s.

### 9.1. application.yml

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
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - reports.read
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

The URLs/scopes are examples; the real provider must permit `reports.read`, and the Access Token must be issued for the Reports API. Identical scope names across two providers do not guarantee equivalent semantics or audience.

### 9.2. SecurityFilterChain

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

`oauth2Login()` authenticates the browser using OIDC, while `oauth2Client()` supports OAuth2 Client features in the Servlet application. The controller only calls downstream APIs once the browser has been authenticated according to the security policy.

### 9.3. Explicit OAuth2AuthorizedClientManager Bean

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class UserAuthorizedClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager userAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository repository) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

This is an explicit configuration to illustrate the manager. If Spring Boot/Spring Security already creates a manager bean that fits your needs, do not declare a duplicate. If the application has both a user manager and a machine manager, use clear bean names/`@Qualifier` when injecting.

### 9.4. WebClient Filter Using the Manager

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsWebClientConfig {

    @Bean
    WebClient reportsWebClient(
            OAuth2AuthorizedClientManager userAuthorizedClientManager) {

        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                userAuthorizedClientManager);

        return WebClient.builder()
            .baseUrl("https://reports.example.net")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

**Important note on HTTP 401/403:** the constructor accepting a manager **does not automatically configure** `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` for Bearer errors from a Resource Server. If you want invalid tokens removed from the cache, you must configure the appropriate failure handler. Section 12 shows how to do this; do not assume it happens automatically just because you used a manager.

### 9.5. Controller Calling the Reports API

~~~java
package com.example.web;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

@RestController
public class MyReportsController {

    private final WebClient reportsWebClient;

    public MyReportsController(WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    @GetMapping("/my-reports")
    public ResponseEntity<String> myReports() {
        String body = reportsWebClient.get()
            .uri("/api/reports/me")
            .attributes(clientRegistrationId("company"))
            .retrieve()
            .bodyToMono(String.class)
            .block();

        return ResponseEntity.ok(body);
    }
}
~~~

The controller is protected by Spring Security. The filter retrieves the current Authentication and the authorized client for registration `company`, then adds the Bearer Access Token if authorization succeeds.

**This example returns raw JSON to stay focused on OAuth2.** In a real application, map the response to a DTO, filter sensitive claims, set timeouts, and handle downstream errors so you do not inadvertently proxy raw unintended data.

### 9.6. End-to-End Flow

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant MVC as Portal Spring MVC
    participant WC as WebClient OAuth2 Filter
    participant M as Servlet AuthorizedClientManager
    participant Store as Authorized Client Repository
    participant OP as OIDC Provider / Token Endpoint
    participant API as Reports API
    Browser->>MVC: GET /my-reports (logged-in session)
    MVC->>WC: GET /api/reports/me, registration=company
    WC->>M: authorize(company, current Authentication)
    M->>Store: loadAuthorizedClient(...)
    alt Existing token is usable
        Store-->>M: Existing OAuth2AuthorizedClient
    else Token needs refresh, refresh token present
        M->>OP: Refresh Token grant
        OP-->>M: New token response
        M->>Store: saveAuthorizedClient(...)
    end
    M-->>WC: OAuth2AuthorizedClient
    WC->>API: Authorization: Bearer Access Token
    API-->>WC: JSON/HTTP error
    WC-->>MVC: Mono response
    MVC-->>Browser: Controlled HTTP response
~~~

If the user is not logged in, the Servlet OAuth2 Login flow can redirect to the Authorization Server. If the API requires an ungranted scope/audience, the filter cannot fabricate additional permissions: the Resource Server may return 401/403.

## 10. Example B: WebClient + Client Credentials with a Service Manager

A backend worker needs to call the Reports API under the **application's identity**, with no logged-in user.

### 10.1. Client Credentials Registration Configuration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: reports-auth
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          reports-auth:
            token-uri: https://auth.example.net/oauth2/token
~~~

**Do not use the `openid` scope and OIDC ID Tokens just to fetch a machine-to-machine Access Token.** Client Credentials is an OAuth 2.0 grant, typically without an end-user, and does not need browser redirects, `state`, PKCE, or an OIDC `nonce`.

### 10.2. Service Manager for Client Credentials

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class MachineAuthorizedClientConfig {

    @Bean
    AuthorizedClientServiceOAuth2AuthorizedClientManager
            machineAuthorizedClientManager(
                    ClientRegistrationRepository registrations,
                    OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

This manager does not require a Servlet HTTP request, making it suitable when the service is invoked from a scheduler or job. The authorized client is stored by `registrationId` and an **application principal name** supplied by the caller.

### 10.3. WebClient Bean Using the Machine Manager

~~~java
package com.example.security;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class MachineReportsWebClientConfig {

    @Bean
    WebClient machineReportsWebClient(
            @Qualifier("machineAuthorizedClientManager")
            AuthorizedClientServiceOAuth2AuthorizedClientManager manager) {

        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://reports.example.net")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

The class name contains `Servlet`, yet the service manager allows it to run **outside a Servlet request** as long as the caller supplies a trusted principal context and does not rely on Servlet ThreadLocals.

### 10.4. Providing an Application Principal for the Request

The filter uses Authentication to determine `principalName`. For a scheduled job without `SecurityContextHolder`, supply an **internal Authentication used solely as the authorized client key**:

~~~java
package com.example.reports;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.authentication;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
public class ReportingSyncClient {

    private final WebClient machineReportsWebClient;

    public ReportingSyncClient(WebClient machineReportsWebClient) {
        this.machineReportsWebClient = machineReportsWebClient;
    }

    public String loadReportsJson() {
        // Strictly an application-level key for the authorized-client store.
        // Does NOT represent a logged-in end-user.
        Authentication servicePrincipal =
            new UsernamePasswordAuthenticationToken(
                "system-report-sync", "N/A");

        return machineReportsWebClient.get()
            .uri("/api/reports")
            .attributes(clientRegistrationId("reports-service"))
            .attributes(authentication(servicePrincipal))
            .retrieve()
            .bodyToMono(String.class)
            .block();
    }
}
~~~

`UsernamePasswordAuthenticationToken` is created here by server-side code solely to provide a **stable principal name** for the manager/service. Never use this token as proof that “a user is logged in”, and never let an HTTP caller choose the `system-report-sync` value.

If the application has multiple machine identities and must isolate permissions across tenants, namespace principals and registrations according to policy rather than using one all-powerful token for every tenant unnecessarily.

### 10.5. Does Every Call Request a New Access Token?

Not necessarily:

~~~text
Call 1:
  ("reports-service", "system-report-sync")
  -> no authorized client yet
  -> Token Endpoint issues Access Token
  -> manager saves authorized client

Call 2:
  -> manager looks up the same key, token still valid
  -> Access Token can be reused

When the token expires or is no longer valid:
  -> Client Credentials grant requests a new Access Token
  -> manager updates authorized client
~~~

Client Credentials normally **does not issue a Refresh Token under standard usage**. When the Access Token expires, the manager requests a new token via the Client Credentials grant. Do not attach `refreshToken()` merely out of concern that the token will expire.

### 10.6. Do Not Use a Machine Token to Substitute for User Identity

If browser user Alice calls a portal endpoint, and the portal uses a broad Client Credentials token to fetch all company reports, the Resource Server may only see the **service identity**, not Alice. The backend must enforce business authorization/tenant/ownership rules before using a machine-level token, or use a delegated user token if the API requires user context.

Do not use `principal("alice")` under Client Credentials and conclude that the issued Access Token represents Alice: **the principal name is only a storage key in the client manager**; it does not turn a machine-to-machine OAuth2 grant into user delegation.

## 11. Two Filter Constructors and an Important Consequence

`ServletOAuth2AuthorizedClientExchangeFilterFunction` has two main constructors to distinguish:

~~~java
// Approach A: supply an already created/configured manager.
new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    authorizedClientManager);

// Approach B: supply a repository and client registrations.
new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    clientRegistrationRepository,
    authorizedClientRepository);
~~~

### 11.1. Constructor Accepting an Authorized Client Manager

Advantages:

- Uses a manager with customized grant providers.
- Unifies success/failure policies in the manager.
- Easy to choose a service manager for background jobs.
- Can configure storage independently through the manager.

**Note:** the constructor **accepting a manager does not automatically configure** `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` for HTTP 401/403 errors from a Resource Server. If the API reports that an Access Token was revoked, the filter may keep using the cached token on subsequent requests unless you configure invalidation.

### 11.2. Constructor Accepting Repositories

When using the constructor:

~~~java
new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    clientRegistrationRepository,
    authorizedClientRepository);
~~~

the filter can use a suitable internally initialized manager configuration, and **a `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` is automatically configured** to handle Bearer errors from the Resource Server according to the error code policy.

This does not mean it deletes the token on every HTTP 403. The handler classifies by OAuth2 error code; each provider/Resource Server may return different errors.

### 11.3. Comparison Table

| Aspect | Filter(manager) | Filter(registrations, repository) |
| --- | --- | --- |
| Supplied manager | Decided by the application | Filter uses the mechanism set up by the constructor |
| Custom provider/grant flexibility | High | Per constructor/integration configuration |
| Suitable for service manager without Servlet context | Yes | Not the primary use case |
| Failure handler for HTTP 401/403 errors | **Must be explicitly configured when invalidation is desired** | **Provided by default** per constructor configuration |
| Token storage strategy | Per injected manager/store | Per injected repository |

Because this lesson focuses on **wiring the filter with an authorized client manager**, the examples favor the **manager constructor** while also showing how to configure the appropriate failure handler.

## 12. Configuring OAuth2AuthorizationFailureHandler for Filter(manager)

### 12.1. Why Is a Handler Needed for Resource Server Errors?

The Authorization Server may have issued a valid Access Token at time T0. By time T1, the token is revoked or the Resource Server detects an invalid issuer/audience:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

If the manager only checks `expiresAt`, the token may still appear valid by timestamp, so subsequent requests keep sending the broken token.

A `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` can delete the corresponding authorized client on matching errors so **the next authorize call** can obtain a fresh token.

### 12.2. Handler with AuthorizedClientService

For a **service manager**:

~~~java
import org.springframework.security.oauth2.client.RemoveAuthorizedClientOAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.OAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;

OAuth2AuthorizationFailureHandler failureHandler =
    new RemoveAuthorizedClientOAuth2AuthorizationFailureHandler(
        (registrationId, principal, attributes) ->
            authorizedClientService.removeAuthorizedClient(
                registrationId, principal.getName()));

ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(
        machineAuthorizedClientManager);

oauth2.setAuthorizationFailureHandler(failureHandler);
~~~

This code assumes `authorizedClientService` and `machineAuthorizedClientManager` are already available dependencies. The handler must operate on **the same backing store/principal namespace** that the manager uses; if the manager saves to service A while the handler deletes from service B, the broken cached token stays in A.

Do not use this snippet to wipe tokens for all users: the remover receives the `registrationId` and `principal` for the specific interaction.

### 12.3. Handler with OAuth2AuthorizedClientRepository in Servlet

With a Servlet manager persisting through a repository, the handler must have the right `HttpServletRequest` and `HttpServletResponse` context to remove the entry:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.oauth2.client.RemoveAuthorizedClientOAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.OAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;

OAuth2AuthorizationFailureHandler failureHandler =
    new RemoveAuthorizedClientOAuth2AuthorizationFailureHandler(
        (registrationId, principal, attributes) -> {
            // Retrieve the right servlet request/response using an adapter
            // controlled by the project and matching your framework version.
            HttpServletRequest request = currentServletRequest();
            HttpServletResponse response = currentServletResponse();
            authorizedClientRepository.removeAuthorizedClient(
                registrationId, principal, request, response);
        });

oauth2.setAuthorizationFailureHandler(failureHandler);
~~~

This snippet is **integration-oriented Java pseudocode**: `currentServletRequest()`/`currentServletResponse()` are helpers the project must define; they are **not built-in Spring Security APIs**. In a real implementation, prefer leveraging the Servlet request/response attributes provided by the filter/manager or a trusted adapter, avoiding pulling the wrong session from a different thread.

If you only need the default repository handler and do not need a custom manager, the `(ClientRegistrationRepository, OAuth2AuthorizedClientRepository)` constructor is a simpler option.

### 12.4. Do Not Automatically Delete All Tokens When the API Returns 403

Relevant HTTP statuses:

| Status / Bearer Challenge | Interpretation | Appropriate Behavior |
| --- | --- | --- |
| `401 invalid_token` | Token may be expired, revoked, or invalid | Can delete the cached authorized client per handler/policy |
| `403 insufficient_scope` | Token was recognized but lacks scope for the operation | Do not self-escalate scope or permissions; handle authorization |
| `403` without Bearer error | May be caused by tenant/ownership/resource state | Do not delete the token by default |
| `429` | Rate limit | Perform controlled backoff/retry |
| `500/503` | Upstream error | Monitor/retry per business rules; do not assume token is bad |

The filter's `OAuth2AuthorizationFailureHandler` handles **OAuth2 errors from the Resource Server**. Meanwhile, `OAuth2AuthorizedClientManager` has its own failure handling when the **Token Endpoint** returns errors like `invalid_client` or `invalid_grant`. Do not conflate the two error sources just because both involve OAuth2.

### 12.5. Does the Filter Automatically Retry the 401 Request?

Do not rely on that assumption. Removing the broken authorized client helps **the next request** obtain a new token; the current request may still fail with an exception or error response.

If the product requires retries:

- Only retry for recoverable errors.
- Enforce a **retry count limit** and reasonable backoff.
- Distinguish GET/idempotent requests from POST/PATCH/DELETE with side effects.
- Do not retry `insufficient_scope` by attempting to request admin scopes.
- Do not retry when the target API URL is user-controlled and not allowlisted.

## 13. setDefaultOAuth2AuthorizedClient and setDefaultClientRegistrationId

The filter supports defaults to avoid repeating request attributes, but these options require security review.

### 13.1. Using the Current OAuth2AuthorizedClient as Default

~~~java
ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(
        authorizedClientManager);

oauth2.setDefaultOAuth2AuthorizedClient(true);
~~~

When enabled, the filter can resolve a default authorized client from the current OAuth2 Authentication. Per Spring Security documentation, **every outbound HTTP request sent through this WebClient may receive an Access Token** if the filter finds a client.

Be careful: a WebClient used to call both trusted APIs and external URLs could inadvertently send the Bearer Token to the wrong host.

### 13.2. Using a Default Client Registration

~~~java
oauth2.setDefaultClientRegistrationId("company");
~~~

This causes the filter to choose registration `company` whenever a request does not specify a registration. Again, **every request through that bean may carry an Access Token**; do not configure this on a WebClient used to call hosts outside the same trust boundary.

### 13.3. Safer Alternatives

In many systems, it is better to:

- Keep the filter default **from forcing a token onto every request**.
- Specify `clientRegistrationId(...)` when calling the corresponding API.
- Use dedicated WebClients with clear `baseUrl`/host allowlists.
- Never let users pick high-privilege client registrations or principals.

If a team selects a default registration for a dedicated WebClient, ensure code cannot override the URL to an untrusted destination or leak tokens via redirects/tracing.

## 14. SecurityContext and Thread Boundaries in Servlet + WebClient

### 14.1. Why Calling WebClient from MVC Differs from WebClient in WebFlux

On the Servlet stack, Authentication usually resides in `SecurityContextHolder` on the request-handling thread. WebClient executes HTTP on a Reactor pipeline; asynchronous calls can shift execution to another thread.

~~~text
Servlet request thread
  SecurityContextHolder = Alice
  RequestContextHolder = current HttpServletRequest
  -> create WebClient Mono
       |
       v
Reactive subscriber / other scheduler
  may NOT have the same ThreadLocals
~~~

If the filter needs to load an authorized client through a repository when the Servlet request is no longer available, the application may encounter missing-context or missing-token errors.

### 14.2. Passing Attributes Explicitly When Needed

In a controller:

~~~java
@GetMapping("/my-data")
public String myData(
        Authentication authentication,
        HttpServletRequest request,
        HttpServletResponse response) {

    return webClient.get()
        .uri("https://reports.example.net/api/me")
        .attributes(clientRegistrationId("company"))
        .attributes(
            ServletOAuth2AuthorizedClientExchangeFilterFunction.authentication(
                authentication))
        .attributes(
            ServletOAuth2AuthorizedClientExchangeFilterFunction.httpServletRequest(
                request))
        .attributes(
            ServletOAuth2AuthorizedClientExchangeFilterFunction.httpServletResponse(
                response))
        .retrieve()
        .bodyToMono(String.class)
        .block();
}
~~~

This snippet is **abbreviated** to highlight request attributes; it assumes the class already has a `webClient` field, Spring MVC/Servlet imports, and a secured endpoint. In a typical application, `defaultRequest()` already handles context propagation so manual passing is unnecessary; this example is useful for understanding the mechanism or handling special architectures.

**Never store `servletRequest`/`response` in a singleton field** or pass them to a background job that runs after the response has completed.

### 14.3. When Should a Service Manager Be Used?

If an API call runs in a scheduled job, queue consumer, or task without a browser request, choose:

~~~text
AuthorizedClientServiceOAuth2AuthorizedClientManager
    + OAuth2AuthorizedClientService
    + Stable application principal
    + Client Credentials grant (if the goal is M2M)
~~~

Do not try to fake `RequestContextHolder` or reuse a user's global SecurityContext just to make a batch job work. Distinguish machine tokens from delegated user tokens and verify who authorized the job.

### 14.4. Avoid Blocking in the Event Loop

In Spring MVC, `.block()` can be convenient, but you must configure timeouts, manage the connection pool, and avoid stalling requests indefinitely.

In a reactive WebFlux pipeline, calling `.block()` on a non-blocking event loop violates the execution model. This lesson discusses **WebClient in Servlet** and does not recommend copying `.block()` into every environment.

## 15. Configuring Timeouts, HTTP Errors, and Operability

### 15.1. Setting Time Limits

A request to the Reports API may be slow, drop connections, or return 5xx. The OAuth2 filter does not replace HTTP client timeout policies.

Example with a properly configured Reactor Netty client:

~~~java
import java.time.Duration;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;

HttpClient httpClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(5));

WebClient client = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .apply(oauth2.oauth2Configuration())
    .build();
~~~

This configures the **HTTP response timeout for outbound Resource Server calls**; Spring Security's Token Endpoint client has its own HTTP client and timeouts. To configure timeouts for the Token Endpoint, customize the corresponding token response client—do not assume modifying the Reactor Netty connector always affects token grants.

### 15.2. Handling HTTP Errors at the Service Layer

~~~java
import org.springframework.web.reactive.function.client.WebClientResponseException;

public String fetchReports(WebClient webClient) {
    try {
        return webClient.get()
            .uri("https://reports.example.net/api/reports")
            .attributes(clientRegistrationId("company"))
            .retrieve()
            .bodyToMono(String.class)
            .block();
    } catch (WebClientResponseException.Unauthorized ex) {
        throw new IllegalStateException(
            "Reports API rejected Access Token", ex);
    } catch (WebClientResponseException.Forbidden ex) {
        throw new IllegalStateException(
            "Access to Reports API forbidden", ex);
    }
}
~~~

This example classifies HTTP 401/403 without auto-retrying and without forwarding the raw response body to the browser. Exact exception types may depend on how `retrieve()/onStatus` or `exchangeToMono()` is used.

### 15.3. Token Endpoint Errors and Resource Server Errors Differ

~~~text
WebClient filter -> AuthorizedClientManager -> Token Endpoint
   invalid_client, invalid_scope, invalid_grant
   -> Access Token issuance/refresh errors

WebClient filter -> Resource Server
   401 invalid_token, 403 insufficient_scope
   -> HTTP Bearer or API policy errors
~~~

Do not assume every 401 in the system is `invalid_client`, and do not assume every 403 is a scope issue. Check whether the error occurred at the **Token Endpoint** or the target API, inspect the OAuth2/Bearer error code, and consult provider documentation.

### 15.4. Circuit Breakers and Retries

When calling APIs:

- Perform bounded retries on 429/503/timeouts if the operation is idempotent and the contract permits it.
- Honor `Retry-After` when provided by the API.
- Avoid token request storms when multiple instances encounter errors simultaneously.
- Do not continuously retry Client Credentials `invalid_client`, since a wrong secret will not fix itself.
- Do not replay authorization code callbacks or uncontrollably retry rotated Refresh Tokens.

**An interceptor is not a universal fix for every integration error.** The manager owns the token lifecycle; HTTP retries and degradation belong to HTTP client/application policies.

## 16. Authorized Client Storage: Filter and Manager Use the Same Store

### 16.1. InMemory, JDBC, and Session

| Store | Example Implementation | Pros/Cons |
| --- | --- | --- |
| Memory | `InMemoryOAuth2AuthorizedClientService` | Easy for demos, lost on restart, not shared across instances |
| JDBC | `JdbcOAuth2AuthorizedClientService` | Persistent/shared; requires schema, encryption, and database operations |
| Servlet session | `HttpSessionOAuth2AuthorizedClientRepository` | Lifecycle tied to browser session; needs session replication when scaling out |
| Repository adapter | `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Delegates to a service for authenticated principals; falls back for anonymous |

If the manager saves to JDBC Service A while inspection code reads from Session Repository B, you may falsely conclude that tokens are disappearing.

### 16.2. JDBC Service Example

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class AuthorizedClientStorageConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcTemplate jdbcTemplate,
            ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbcTemplate, registrations);
    }
}
~~~

This is an illustrative configuration and does not include the Spring JDBC datasource or schema migrations. Do not blindly apply DDL from another Spring Security version to production without checking the contract.

**Access Tokens and Refresh Tokens in the database are credentials.** Protect access, apply encryption/retention per policy, and avoid unsafe SQL logs or unencrypted backups. Deleting a local authorized client does not mean the Authorization Server has revoked the token.

### 16.3. Principal Namespace

A service manager key:

~~~text
("reports-service", "system-report-sync")
~~~

must not be confused with:

~~~text
("reports-service", "employee-123")
~~~

If the principal key changes on every request, the manager will fail to locate stored tokens. If the principal key is overly broad, multiple tenants may accidentally share a token. Design keys to match security boundaries and grants.

## 17. Multi-Provider, Multi-Tenant, and Permission Boundaries

### 17.1. Assigning the Right Token to the Right Resource Server

Example:

~~~text
company-oidc (delegated user token)
  issuer = https://id.example.com/realms/company
  audience = reports-api
  scope = reports.read

billing-service (machine token)
  issuer = https://auth.billing.example.net
  audience = billing-api
  scope = billing.read
~~~

The WebClient filter **does not turn a Reports Token into a Billing Token**. Selecting a registration/principal determines how the manager obtains a token, while the Resource Server must verify the issuer, audience, expiration, scope, and policy.

### 17.2. Never Take a Tenant from the Browser to Pick a Privileged Token

Anti-pattern:

~~~java
webClient.get()
    .uri(userProvidedDestination)
    .attributes(clientRegistrationId(userProvidedRegistration))
    .attributes(authentication(userProvidedAuthentication))
    .retrieve();
~~~

This is a dangerous design: a request to an arbitrary URL could carry a high-privilege client's Access Token; principals must never come from untrusted input. Map destinations, registrations, and principals from server-side policy and verified Authentication.

### 17.3. API Scope Is Not the Same as User Role

A service token carrying `reports.read.all` does not prove the user visiting the portal is authorized to view all data. If the backend uses a machine token, user/tenant authorization must be enforced beforehand or at the downstream API by design.

Conversely, `ROLE_ADMIN` in the portal does not automatically add `reports.write` scope to an Access Token. Authorization must be granted at the Authorization Server and enforced by policy at the Resource Server.

### 17.4. Token Confidentiality

Do not:

- Put `access_token`, `refresh_token`, or `id_token` in controller JSON responses.
- Append an Access Token to URL query strings for debugging.
- Log the `Authorization` header, Client Secret, or full HTTP wire traces in production.
- Use a WebClient with an OAuth2 filter to fetch user-supplied URLs without an allowlist.
- Send delegated user tokens to hosts outside the issuer/resource trust boundary.

## 18. Securing Redirects, Interceptors, and Observability

### 18.1. Redirects Can Introduce Risk

An API may return 301/302/307/308 redirects. HTTP clients have their own rules for forwarding headers across redirects, depending on transport/library/version.

Do not **assume** Bearer Tokens are always protected when an API redirects to another host. For HTTP clients with token interceptors:

1. Restrict destination hosts.
2. Define explicit redirect policies, especially for cross-host redirects.
3. If the API does not need redirects, consider disabling or limiting redirect following in the HTTP connector.
4. Never let an attacker control the `Location` header or destination URL to steal credentials.

### 18.2. Logging Filters and the OAuth2 Filter

An `ExchangeFilterFunction` that logs HTTP requests may observe headers after the OAuth2 filter attaches the token, depending on filter ordering. **Do not rely on filter ordering** to protect credentials.

Enforce redaction policies across all logging/tracing layers:

~~~text
Authorization: [REDACTED]
Cookie: [REDACTED]
access_token: [REDACTED]
refresh_token: [REDACTED]
client_secret: [REDACTED]
~~~

### 18.3. Safe Metrics

A reasonable metric/log metadata format:

~~~text
event=outbound_oauth2_api_call
registration_id=company
resource=reports-api
result=success
http_status=200
correlation_id=internal-7fa2
~~~

This format is illustrative, not Spring Security's default logging. Do not use raw tokens, sensitive usernames, or high-cardinality request IDs as uncontrolled metric labels.

### 18.4. Client Credentials Secret Rotation

If a machine manager requests a token and the Token Endpoint returns `invalid_client`, check the Client Secret, auth method, and provider tenant. Do not try to fix it by adding scopes, cycling through old secrets, or retrying infinitely. The WebClient filter does not replace credential management processes.

## 19. WebClient Filter vs. RestClient Interceptor

The two HTTP client styles have different models:

| Criterion | WebClient | RestClient |
| --- | --- | --- |
| Model | Reactive client, `Mono`/`Flux` | Synchronous, fluent |
| HTTP hook | `ExchangeFilterFunction` | `ClientHttpRequestInterceptor` |
| Spring Security Servlet OAuth2 integration | `ServletOAuth2AuthorizedClientExchangeFilterFunction` | `OAuth2ClientHttpRequestInterceptor` (Spring Security 6.4+) |
| Manager | `OAuth2AuthorizedClientManager` | `OAuth2AuthorizedClientManager` |
| Selecting registration | `Servlet...FilterFunction.clientRegistrationId(...)` | `RequestAttributeClientRegistrationIdResolver.clientRegistrationId(...)` |
| Selecting principal | `Servlet...FilterFunction.authentication(...)` | `RequestAttributePrincipalResolver.principal(...)` or another resolver |

Do not copy:

~~~java
new OAuth2ClientHttpRequestInterceptor(manager)
~~~

to use as a WebClient filter. It is meant for RestClient and does not implement `ExchangeFilterFunction`.

Conversely, do not attach `ServletOAuth2AuthorizedClientExchangeFilterFunction` to `RestClient.Builder.requestInterceptor(...)`; the two HTTP hook interfaces are different.

### 19.1. Why Not Use the Reactive Security Filter in Servlet?

`ServerOAuth2AuthorizedClientExchangeFilterFunction` belongs to Reactive WebFlux integration and works with reactive authorization context components. In a Servlet app, `ServletOAuth2AuthorizedClientExchangeFilterFunction` is the right choice because it knows how to retrieve the default Authentication/Servlet request context.

### 19.2. When to Use WebClient?

WebClient is useful when you want:

- A fluent API for HTTP and Reactor-based response processing.
- Integration with reactive client SDKs or handling multiple downstream calls.
- Shared reactive HTTP utilities even though the inbound server remains MVC.

However, if the entire application is synchronous Servlet and only calls a few simple APIs, `RestClient` can also be a good fit. HTTP client choice should be based on architecture and dependencies/versions, not just library names.

## 20. Testing the Integration Between Filter and Manager

A useful test suite should distinguish:

1. **WebClient filter test:** does the filter attach the proper Bearer header when the manager returns a valid client?
2. **AuthorizedClientManager test:** does the manager obtain/refresh tokens by registration/principal?
3. **Resource Server integration test:** does the API accept tokens with the right audience/scope and reject wrong ones?
4. **Servlet context test:** are `SecurityContext` and `RequestContextHolder` propagated properly through MVC requests?

Mocking an Access Token in a WebClient unit test **does not prove** the token was issued by the Authorization Server or that an OIDC ID Token was verified.

### 20.1. Test Matrix

| Scenario | Expected Result |
| --- | --- |
| WebClient with OAuth2 filter, manager returns authorized client | Outbound request has `Authorization: Bearer TEST_TOKEN` |
| No registration and no default | Does not automatically send a high-privilege token |
| Correct `clientRegistrationId("company")` | Manager uses registration `company` |
| Wrong registration ID | Does not silently use another registration's token |
| User Alice and user Bob on the same registration | Each receives their own authorized client |
| Client Credentials with fixed application principal | Saves/loads token under the same key |
| Scheduled job with no Servlet request | Service manager still works with explicit Authentication |
| Valid token | Authorized client can be reused |
| Expired token with valid Refresh Token | Manager refreshes and saves new token |
| Client Credentials token expired | Manager requests new token via Client Credentials grant |
| Token Endpoint returns `invalid_client` | API is not called with fake/expired token |
| Resource Server returns `401 invalid_token` | Failure handler handles cached token per policy |
| Resource Server returns `403 insufficient_scope` | Does not self-elevate scope/role |
| Resource Server returns 404 | Does not delete token without an OAuth2-specific reason |
| API URL not in allowlist | Bearer Token is not sent |
| Filter manager constructor without failure handler | Test reflects that cached client may remain |
| Failure handler uses wrong service/store | Test catches deletion against wrong backing store |
| WebClient Mono subscribed on another thread | No false reliance on ThreadLocal Servlet context |
| HTTP logging enabled | No Authorization header/token in logs |

### 20.2. MockWebServer or WebClient ExchangeFunction Test

Test outline:

~~~text
WebClient
  -> ServletOAuth2AuthorizedClientExchangeFilterFunction(testManager)
  -> Fake ExchangeFunction / MockWebServer
       assert URI = /api/reports
       assert Authorization = Bearer TEST_ONLY_ACCESS_TOKEN
       return 200 mock JSON
~~~

The manager test double should return an `OAuth2AuthorizedClient` containing a test Access Token. When testing the filter, you may not need to run the Authorization Code flow. In grant integration tests, use a mock Authorization Server to verify token exchange and persistence.

Never use production Client Secrets, Access Tokens, or Refresh Tokens in test fixtures.

### 20.3. Verifying That the Filter Does Not Send Tokens to the Wrong Host

In production, you should have tests/contracts for destination policies:

~~~text
https://reports.example.net/api/reports -> allowed
https://example-evil.invalid/collect   -> blocked before token transmission
~~~

The filter is not a host allowlisting system by default. If the application passes arbitrary URLs to WebClient, enforce restrictions at the gateway/URI policy or via a dedicated HTTP client.

### 20.4. Testing Default OAuth2AuthorizedClient Flags

If enabling `setDefaultOAuth2AuthorizedClient(true)` or `setDefaultClientRegistrationId(...)`, test that **only outbound calls inside the trust boundary** use the token-bearing WebClient. Do not only test “valid requests get a token”; also test “inappropriate requests do not receive credentials”.

## 21. Diagnosing When the Filter Does Not Send an Access Token

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| Request has no Bearer header | WebClient bean does not apply filter | `.apply(oauth2.oauth2Configuration())` or `.filter(oauth2)` |
| Filter cannot find registration | Missing `clientRegistrationId(...)`, wrong name | Registration ID in Spring Boot config |
| Manager returns null | Cannot authorize grant in context | Provider chain, principal, registration, request attributes |
| Missing Servlet request error | Using Default manager in background job | Service manager or supply proper context |
| User A's token used for user B | Principal namespace or Authentication mix-up | SecurityContext, service store, request attributes |
| Token Endpoint `invalid_client` | Wrong Client Secret/method/tenant | Client registration and provider policy |
| Token Endpoint `invalid_scope` | Scope not granted | Grant policy, requested scopes |
| Resource Server `401 invalid_token` | Token expired/revoked/wrong issuer/audience | API validation, client registration, failure handler |
| Resource Server `403 insufficient_scope` | Token lacks scope | Granted permissions and API policy |
| Other Resource Server `403` | Tenant/ownership/resource state | API authorization logic |
| Error only happens with `@Async` | Lost SecurityContext/Servlet ThreadLocal | Subscription/thread boundaries |
| Token refresh succeeds but next request uses old token | Different manager/store, custom success handler does not save | Authorized client persistence |
| No new token after 401 error | Manager constructor lacks failure handler | Configure `setAuthorizationFailureHandler(...)` |
| Handler removes client yet current call still 401s | No auto-retry | Design separate bounded retry |
| Every request asks for a new token | Principal key changes, non-shared memory store | Service/Repository and persistence |
| Token leaked via tracing | Wire log prints Authorization header | Redaction and logging policy |
| Different host API receives token | WebClient uses caller-supplied URI | SSRF, redirects, host allowlist |

### 21.1. A Short Investigation Sequence

~~~text
WebClient outbound request fails
   |
   +-- Is the right WebClient bean wired with the filter?
   |
   +-- Was clientRegistrationId/authorizedClient provided?
   |
   +-- Does Authentication/principal match the right user/service?
   |
   +-- Was the right Servlet or Service manager chosen?
   |
   +-- Does the authorized client store have registration + principal?
   |
   +-- Did the Token Endpoint issue/refresh successfully?
   |
   +-- Was the Access Token sent to the right Resource Server?
   |
   +-- Did the API return 401/403/429/5xx?
   |
   +-- Is a failure handler/invalidation or retry policy needed?
~~~

Never log the entire `OAuth2AuthorizedClient` for debugging — this object can contain tokens. Only use necessary metadata, redaction, and credential-free correlation IDs.

## 22. Common Implementation Mistakes

### 22.1. Omitting the Registration ID

~~~java
webClient.get()
    .uri("/api/reports")
    .retrieve()
    .bodyToMono(String.class);
~~~

Without an authorized client or appropriate default, the filter cannot pick a token on its own. Add `.attributes(clientRegistrationId("company"))` or pass the authorized client explicitly.

### 22.2. Enabling Default OAuth2 Client on a Public WebClient

A WebClient used to call arbitrary URLs with `setDefaultOAuth2AuthorizedClient(true)` enabled can leak tokens unexpectedly. Separate clients by trust boundary, and avoid auto-attaching tokens to every outbound call.

### 22.3. Storing a User's Token in a Static Field

~~~java
// ANTI-PATTERN:
static String lastAccessToken;
~~~

Concurrent requests can cause one user to use another user's token. Use the manager/store keyed by registration + principal and never create a global token singleton.

### 22.4. Using an ID Token as Bearer for APIs

ID Tokens are for authenticating the OIDC client. Resource Servers normally require Access Tokens. Never use `oidcUser.getIdToken().getTokenValue()` in place of `authorizedClient.getAccessToken()`.

### 22.5. Letting a Scheduled Job Use a Servlet Manager Without a Request

`DefaultOAuth2AuthorizedClientManager` depends on Servlet context for its repository. Use a service manager for work outside HTTP requests, especially Client Credentials.

### 22.6. Passing Only clientRegistrationId and Forgetting the Service Principal

With Client Credentials on a worker thread, there is no valid SecurityContext for the manager to resolve a principal name. Pass an application-level Authentication via `authentication(...)`, and never take the principal from the browser.

### 22.7. Assuming the Filter Checks Audience and API Permissions

The filter primarily inserts the Access Token into the HTTP request; the Resource Server must verify the token and authorization. A properly attached token can still be rejected by the API.

### 22.8. Assuming 401 Cached Tokens Vanish Automatically with Constructor(manager)

The manager constructor **does not automatically install a RemoveAuthorizedClient failure handler for Resource Servers**. Configure it when invalidation is required, or use the repository constructor which has different default behavior.

### 22.9. Deleting All Authorized Clients After One HTTP Error

Do not wipe every user's tokens over a 404/503 or a 403 insufficient permissions error. Act on OAuth2/Bearer codes and policies; never wipe the entire store automatically.

### 22.10. Attaching Both the OAuth2 Filter and a Manual Bearer Header

Two credential sources easily conflict, causing flaky errors or data leaks. Prefer a single filter + manager for OAuth2 requests.

### 22.11. Using the Same WebClient for Internal APIs and Arbitrary URLs

This opens the door to SSRF/token exfiltration. Design dedicated WebClients with fixed hosts/paths or strict allowlists.

### 22.12. Using a Logging Filter as a “Token Inspection Point”

Logging/tracing must not record raw Bearer Tokens. Use test tokens in test environments or non-sensitive metadata when investigating production.

### 22.13. Creating a Mono in a Request and Subscribing After Session Context Is Lost

Do not rely on ThreadLocal Servlet/SecurityContext when a pipeline executes later or on another scheduler; pass context explicitly, pick a service manager, or design accordingly.

### 22.14. Setting a Manager Success Handler Only to Log

If you replace the default `OAuth2AuthorizationSuccessHandler` without saving the new client, tokens may not be persisted. When customizing, preserve saving tokens to the exact store.

## 23. Practical Scenario Exercises

### Scenario A — OIDC Portal Calling the User's Own API

A user signs in as `company`, and the portal needs to call the Reports API for that user.

**Design:** `DefaultOAuth2AuthorizedClientManager` with a Servlet repository, a WebClient filter receiving the manager, request attributes using `clientRegistrationId("company")`, and principal from SecurityContext. Only send tokens issued by the provider for the Reports API with the proper audience/scope.

### Scenario B — Report Sync Worker Without a Browser

A scheduled job calls the Reports API using Client Credentials.

**Design:** `AuthorizedClientServiceOAuth2AuthorizedClientManager`, `clientCredentials()` provider, a stable application principal passed via `authentication(...)`, and a dedicated WebClient. Do not borrow an authenticated user's token.

### Scenario C — Filter Has a Token but API Returns 403

The token contains `reports.read`, but the job calls an endpoint requiring `reports.write`.

**Design:** stop the operation, check the API contract, and request permissions through governance if needed. Do not self-escalate scopes or modify the filter to bypass the Resource Server.

### Scenario D — API Returns 401 for an Unexpired Token

The Resource Server has revoked the token or rejects the audience. The manager still sees `expiresAt` in the future.

**Design:** classify `invalid_token`, configure a failure handler to remove the cached authorized client when appropriate, and investigate issuer/audience if the new token still fails. Do not retry infinitely.

### Scenario E — Shared WebClient Used for Both APIs and User-Supplied URLs

A data import feature accepts a URL from the browser and calls it with the same WebClient that has the OAuth2 filter.

**Design:** separate out a token-free WebClient for public fetches, restrict hosts/IPs/redirects, and block SSRF. Never let the portal's Bearer Token be sent out to arbitrary Internet hosts.

### Scenario F — MVC Controller Uses Block/Mono, Background Subscription Misses Authentication

The application creates a Mono in a controller, hands it to a queue, and subscribes later.

**Design:** do not depend on `SecurityContextHolder`/`RequestContextHolder` from a finished HTTP request. Design delegated authorization with explicit storage and permissions, or switch to a service manager for machine flows.

### Scenario G — Two Client Registrations Sharing the Same Provider

The application has `reports-read` and `reports-write` using the same token endpoint but with different permissions.

**Design:** set the request attributes to the exact registration per feature; never let users pick `reports-write` via a query string. Consider splitting into two WebClients and adding service-level policies.

### Scenario H — New Token Is Not Saved

The manager successfully requests an Access Token, yet the next call requests a new one because a custom success handler only logs.

**Design:** restore default persistence or delegate saving to the authorized client service/repository; verify the principal key and avoid ad-hoc saves scattered in multiple places.

### Scenario I — 401 Invalidated but Current Request Still Errors

The failure handler removed the cached client; `WebClient.retrieve()` still throws an unauthorized exception.

**Design:** understand that invalidation helps the next request; if a retry is needed, implement it at the application layer with limits and idempotency checks. Do not assume the handler replays the request automatically.

### Scenario J — Multi-Node Inconsistent Token Reads

Node A stores authorized clients in memory; node B has its own memory and misses the token; multiple calls re-request simultaneously.

**Design:** use a shared authorized client service when needed, such as JDBC, and synchronize per registration/principal for refresh rotation. Do not mistake this for a scope error.

## 24. References

- Spring Security — OAuth2 Client on Servlet: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — Authorized Client Features, WebClient Integration: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — `ServletOAuth2AuthorizedClientExchangeFilterFunction` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServletOAuth2AuthorizedClientExchangeFilterFunction.html
- Spring Security — `OAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Spring Security — `DefaultOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html
- Spring Security — `AuthorizedClientServiceOAuth2AuthorizedClientManager` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html
- Spring Security — `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/RemoveAuthorizedClientOAuth2AuthorizationFailureHandler.html
- Spring Framework — WebClient: https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html
- RFC 6749 — OAuth 2.0 Authorization Framework: https://www.rfc-editor.org/rfc/rfc6749
- RFC 6750 — OAuth 2.0 Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700

## 25. Summary: One Filter, One Manager, Right Registration and Principal

~~~text
Spring MVC Controller / backend service
    |
    v
WebClient
    .attributes(clientRegistrationId("company" | "reports-service"))
    .attributes(authentication(...))  // when specifying a principal is needed
    |
    v
ServletOAuth2AuthorizedClientExchangeFilterFunction
    |
    +-- uses OAuth2AuthorizedClient directly if passed
    |
    +-- or calls OAuth2AuthorizedClientManager.authorize(...)
           |
           +-- Servlet user flow: repository + Authorization Code/Refresh Token
           |
           +-- Service flow: service + Client Credentials
           |
           +-- Load / issue / refresh / save authorized client
    |
    v
Authorization: Bearer <access_token>
    |
    v
Resource Server
    |
    +-- 2xx: process data
    +-- 401 invalid_token: appropriate failure handler/invalidation
    +-- 403 insufficient_scope: API/permission policy
    +-- 429/5xx: controlled retry/backoff
~~~

**Four key takeaways:**

1. **`ServletOAuth2AuthorizedClientExchangeFilterFunction` is the bridge between WebClient and `OAuth2AuthorizedClientManager` on the Servlet stack.** Use `new ...FilterFunction(manager)` followed by `WebClient.builder().apply(oauth2.oauth2Configuration())` to attach the filter and default Servlet context.
2. **Choose the right client and principal.** `clientRegistrationId(...)` selects the registration; `authentication(...)` or `SecurityContext` determines the principal, which identifies the authorized client and token to use.
3. **Filter(manager) does not automatically configure a removal handler for Resource Server 401/403 responses.** When invalidation is needed, configure `setAuthorizationFailureHandler(...)` with the right store and policy; do not wipe all tokens or retry every HTTP request.
4. **Protect permission and credential boundaries.** Only send Access Tokens to permitted APIs; avoid WebClients that attach default tokens to arbitrary URLs; keep secrets out of logs/redirects; and distinguish delegated user tokens, machine tokens, ID Tokens, and Resource Server permissions.

When these layers are configured consistently, WebClient in Spring MVC can call OAuth2-protected APIs without business code manually managing Bearer Tokens, while keeping clear responsibilities for **OIDC login**, **OAuth2 authorization**, **authorized client lifecycle**, and **HTTP client security**.
