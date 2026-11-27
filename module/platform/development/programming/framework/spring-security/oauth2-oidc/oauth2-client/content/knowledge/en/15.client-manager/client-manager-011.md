# 15.11. Configuring `oauth2Client` and Wiring a Custom Manager

## 1. The Problem: `oauth2Client` Is Enabled, Yet the HTTP Client Does Not Use the New Token Policy

Suppose **Employee Portal** is a **Spring Boot 3, Spring Security 6, Servlet/Spring MVC** application. Users log in with OpenID Connect (OIDC), after which the Portal calls the **Orders API** on the user's behalf. The Portal also has a periodic job calling the **Reports API** using the application's own permissions.

The development team wants to:

- Log users in via `oauth2Login()`.
- Manage access tokens/refresh tokens when calling the Orders API.
- Use `client_credentials` for the Reports API background task.
- Control when tokens are refreshed and handle token-issuance failures under custom policies.
- Use a **custom `OAuth2AuthorizedClientManager`** instead of calling the token endpoint manually everywhere.

A configuration might already exist:

~~~java
http.oauth2Login(Customizer.withDefaults())
    .oauth2Client(Customizer.withDefaults());
~~~

However, merely adding an `OAuth2AuthorizedClientManager` bean does not automatically cause **every HTTP client, OAuth2 login filter, or background job** to use that manager. You need to understand which components make up the manager, **which objects invoke the manager**, and **where the manager instance must be passed explicitly**.

**Core takeaway:** `oauth2Client()` configures OAuth2 Client components in the **Spring Security Servlet filter chain**; `OAuth2AuthorizedClientManager` orchestrates **authorization/refresh** of an authorized client; and **`RestClient`, `WebClient`, controllers, or services** must be wired to the manager using the exact integration mechanism in use. These are related responsibilities, not a single API.

> Examples use Java 17+, Spring Boot 3, and Spring Security 6. The `OAuth2ClientHttpRequestInterceptor` pattern for `RestClient` belongs to Spring Security **6.4+**; for older versions, use `WebClient` in Servlet or the manager-calling mechanism suited to that version. This lesson focuses on **Servlet**; do not copy directly to WebFlux.

## 2. Architecture and Participating Objects

| Component | Role | Holds Tokens? |
|---|---|---|
| `ClientRegistrationRepository` | Holds client config: registration ID, grant type, client ID, provider endpoints, scopes | No; metadata / client registration |
| `OAuth2AuthorizationRequestResolver` | Creates authorization requests for the browser to start the Authorization Code Flow | Does not store access tokens |
| `OAuth2AuthorizationRequestRedirectFilter` | Redirects the browser to the Authorization Server | Does not manage issued tokens |
| `OAuth2LoginAuthenticationFilter` | Handles OAuth2/OIDC login callbacks | Coordinates token exchange for login |
| `OAuth2AuthorizedClient` | Represents a client authorized for a principal | Holds access token and refresh token if issued |
| `OAuth2AuthorizedClientRepository` | Saves/retrieves authorized clients in a Servlet request/response context | May store directly or delegate to an underlying service |
| `OAuth2AuthorizedClientService` | Saves/retrieves authorized clients by registration and principal name | Yes, depending on implementation |
| `OAuth2AuthorizedClientProvider` | Executes grant logic such as `authorization_code`, `refresh_token`, `client_credentials` | Uses/receives tokens during authorization |
| `OAuth2AuthorizedClientManager` | Coordinates registration, token lifecycle, providers, and persisting results | Orchestrates; does not store permanently itself |
| **API-calling HTTP client** | Sends Bearer tokens to the Resource Server | Supplied tokens by the manager/integration |

### 2.1. Flow Overview

~~~mermaid
flowchart TD
    B["Browser logged in via OIDC"] --> C["Controller / BFF endpoint"]
    C --> D["RestClient or WebClient with OAuth2 integration"]
    D --> M["Custom OAuth2AuthorizedClientManager"]
    M --> R["ClientRegistrationRepository"]
    M --> S["OAuth2AuthorizedClientRepository / Service"]
    M --> P["OAuth2AuthorizedClientProvider chain"]
    P --> AC["authorization_code"]
    P --> RT["refresh_token"]
    P --> CC["client_credentials"]
    RT --> AS["Authorization Server / Token endpoint"]
    CC --> AS
    AC --> AS
    AS --> M
    M --> D
    D --> API["Orders API / Reports API"]
~~~

In the flowchart, the `authorization_code` provider still requires **browser redirect/callback** when authorization does not exist yet; a `RestClient` call inside a background job cannot complete interactive login without a user.

## 3. Three Similar-Sounding Configurations That Cannot Replace Each Other

### 3.1. `oauth2Login()`

~~~java
http.oauth2Login(Customizer.withDefaults());
~~~

This configures **user login** via OAuth 2.0/OIDC: redirecting to the provider, handling callbacks, exchanging the authorization code for tokens, verifying OIDC, and creating `Authentication`/`SecurityContext`.

### 3.2. `oauth2Client()`

~~~java
http.oauth2Client(Customizer.withDefaults());
~~~

This enables **OAuth2 Client authorization** support in a Servlet application, including flows related to the Authorization Code Grant and required filter chain components. It does not automatically tell arbitrary HTTP clients which registration ID and principal to use.

### 3.3. `oauth2ResourceServer()`

~~~java
http.oauth2ResourceServer(resourceServer ->
    resourceServer.jwt(Customizer.withDefaults()));
~~~

This configures the **application to receive and verify Bearer tokens** as a Resource Server. It does **not** help the Portal actively obtain tokens to call the Orders API. If the Portal acts as both an OAuth2 Client and protects its own APIs, both sets of configurations may be needed, with clear separation of endpoints and security chains.

| Need | Appropriate Configuration / Component |
|---|---|
| User login via OIDC | `oauth2Login()` |
| OAuth2 client authorization via Servlet filters | `oauth2Client()` |
| Resolving tokens when calling APIs | `OAuth2AuthorizedClientManager` with HTTP client integration |
| Receiving Bearer tokens and validating JWTs | `oauth2ResourceServer()` |
| Customizing HTTP POST code exchange during login | Token response client on `oauth2Login().tokenEndpoint()` |
| Customizing refresh/`client_credentials` when calling APIs | Corresponding authorized-client provider/manager |

**Do not assume a custom manager replaces all token exchanges in `oauth2Login()`.** They are distinct integration points.

## 4. What Does `OAuth2AuthorizedClientManager` Do?

Servlet interface:

~~~java
package org.springframework.security.oauth2.client;

public interface OAuth2AuthorizedClientManager {
    OAuth2AuthorizedClient authorize(
        OAuth2AuthorizeRequest authorizeRequest
    );
}
~~~

An `OAuth2AuthorizeRequest` supplies context such as:

- **`clientRegistrationId`** or an existing authorized client.
- Associated **`principal`**.
- Attributes needed for the grant and HTTP request context.

The manager typically:

1. Resolves the `ClientRegistration`.
2. Loads any saved `OAuth2AuthorizedClient`.
3. Builds an `OAuth2AuthorizationContext` for providers to evaluate.
4. Calls `OAuth2AuthorizedClientProvider.authorize(context)`.
5. Saves the authorized client when newly issued/refreshed via handler.
6. Handles errors and removes invalid tokens per the failure handler/policy.
7. Returns the authorized client to the caller.

### 4.1. Returning `null` Does Not Mean the Principal Logged Out

If `authorize(...)` returns `null`, it usually means **the manager could not issue/return an authorized client matching the request and configured providers**, not that the HTTP session is no longer authenticated.

Conversely, having an `OAuth2AuthorizedClient` does not guarantee the token will be accepted by the Resource Server: the token might be revoked, lack scopes, or have the wrong audience.

### 4.2. The Manager Is Not Where User Permissions Are Overridden

The manager manages tokens and authorization grants; it does not decide which orders a user may delete. The Portal and Orders API must still enforce **authorization** by principal, tenant, resource, and scopes.

## 5. Two Common Managers on Servlet

| Criterion | `DefaultOAuth2AuthorizedClientManager` | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
|---|---|---|
| Primary design context | Servlet **`HttpServletRequest`/`HttpServletResponse`** | Outside requests, e.g., scheduled jobs, service workers |
| Dependencies | `ClientRegistrationRepository` + `OAuth2AuthorizedClientRepository` | `ClientRegistrationRepository` + `OAuth2AuthorizedClientService` |
| Token storage | Via authorized-client repository | Via authorized-client service |
| Principal | User's `Authentication` or appropriately passed principal | Service/task principal string or `Authentication` |
| Suitable for | User-authorized API calls in a web Portal | Machine-to-machine `client_credentials`, batches |
| Example | Orders API on behalf of logged-in user | Reports API from a scheduled job |

Both classes implement `OAuth2AuthorizedClientManager`, yet **cannot be swapped arbitrarily**:

- `DefaultOAuth2AuthorizedClientManager` needs Servlet request/response context to work with the repository. Using it in a job outside HTTP requests is usually inappropriate.
- `AuthorizedClientServiceOAuth2AuthorizedClientManager` requires no Servlet request; ideal for background tasks or event handlers.

Never use a single manager with a default `"admin"` principal so all web requests send tokens on behalf of an admin. **Principal identity must come from the proper authenticated context.**

## 6. `ClientRegistration` Entries Shared Across Grants

Suppose the Portal has two OAuth2 client registrations:

~~~yaml
# src/main/resources/application.yml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
          reports-service:
            provider: company
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Explanation:

- `company` uses `authorization_code` to bind to a **user** and let the Portal call the Orders API if the provider grants the corresponding scopes.
- `reports-service` uses `client_credentials` for a **service**; no user login and no redirect URI are needed.
- Both are managed under one issuer/provider `company`, yet they are **two distinct registrations** with separate client credentials and permissions.
- `OIDC_CLIENT_SECRET` and `REPORTS_CLIENT_SECRET` must be supplied at runtime via a secret manager or secure mechanism, never committed to Git.

If the OP issues access tokens with distinct audiences for Orders API vs. Reports API, ensure registration/scopes and Authorization Server configuration emit tokens for the exact target API. Never assume sharing an issuer makes every token valid for every Resource Server.

### 6.1. Distinguishing `registrationId`, `principalName`, and `scope`

~~~text
registrationId = company
principalName  = employee-0042
scopes         = openid profile orders.read

registrationId = reports-service
principalName  = reports-worker
scopes         = reports.read
~~~

`registrationId` identifies the **OAuth Client configuration**. `principalName` is the principal name used when managing authorized clients. **Scope** describes permissions requested/granted for the token. They are not interchangeable.

## 7. Dependencies and Servlet `SecurityFilterChain`

### 7.1. Gradle

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Only needed if choosing WebClient as the HTTP client in a Servlet app:
    implementation 'org.springframework:spring-webflux'
}
~~~

When an application already has `spring-boot-starter-web`, adding `WebClient` does not turn the application into WebFlux. Spring Boot normally prefers the **Servlet** web application type when both Spring MVC and WebFlux are on the classpath, unless configured otherwise.

### 7.2. `SecurityFilterChain`

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

This enables both **login** and **OAuth2 Client support** on Servlet. If API endpoints need to return 401 JSON instead of an HTML redirect to the IdP, configure appropriate exception handling / security matchers.

**No custom manager is wired to `RestClient`/`WebClient` here yet.** The next section creates the manager and passes it to the HTTP client actually used by services.

## 8. Creating a Custom Manager for Servlet Requests

Example creating `DefaultOAuth2AuthorizedClientManager` with a provider chain containing `authorization_code`, `refresh_token`, and `client_credentials`:

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class WebAuthorizedClientConfig {

    @Bean("webAuthorizedClientManager")
    OAuth2AuthorizedClientManager webAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClients
    ) {
        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

**Key points in the code:**

1. `ClientRegistrationRepository` is built by Spring Boot from `spring.security.oauth2.client.*` properties.
2. `OAuth2AuthorizedClientRepository` supports loading/saving authorized clients in the HTTP Servlet context.
3. `OAuth2AuthorizedClientProviderBuilder` defines **which grants the manager is permitted to orchestrate**.
4. `manager.setAuthorizedClientProvider(provider)` attaches the provider chain to the manager.
5. Bean name `webAuthorizedClientManager` distinguishes the web-request manager from the background-job manager.

This is a **custom manager** because you explicitly decide the provider chain and can add token persistence/handling policies later. It still builds on Spring Security's standard implementations; there is no need to hand-code HTTP POSTs to the token endpoint.

### 8.1. Do You Need to Enable All Three Grants?

No. If the manager is only used for user-authorized API calls, you may only need:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();
~~~

If the manager is only used for service-to-service calls, you can use:

~~~java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
~~~

**Grants supported by the provider chain do not alter the `authorization-grant-type` of each `ClientRegistration`.** Which registration uses which grant still depends on configuration and grant context.

Do not arbitrarily broaden grants/scopes just to “make sure we get a token”. Grants are part of authorization policy.

## 9. Wiring a Custom Manager to `RestClient` (Spring Security 6.4+)

Starting in Spring Security 6.4, there is integration for Spring Framework's `RestClient` via:

~~~java
org.springframework.security.oauth2.client.web.client
    .OAuth2ClientHttpRequestInterceptor
~~~

This HTTP interceptor calls `OAuth2AuthorizedClientManager` to look up/issue/refresh the authorized client and sets the access token in the Bearer header on outbound requests to the Resource Server.

### 9.1. `RestClient` Bean Receiving the Exact Manager

~~~java
package com.example.portal.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.web.client.RestClient;

@Configuration
public class OrdersRestClientConfig {

    @Bean("ordersRestClient")
    RestClient ordersRestClient(
        @Qualifier("webAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager
    ) {
        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(manager);

        return RestClient.builder()
            .baseUrl("https://orders.example.test")
            .requestInterceptor(oauth2)
            .build();
    }
}
~~~

In production, load `https://orders.example.test` from a controlled application property and configure appropriate timeouts/TLS/proxies. This example focuses solely on **passing the manager**.

**Crucial line:**

~~~java
new OAuth2ClientHttpRequestInterceptor(manager)
~~~

This interceptor instance **uses the passed-in manager**. Having `http.oauth2Client()` in `SecurityFilterChain` does not automatically attach the interceptor to arbitrary `RestClient` instances.

### 9.2. Specifying `clientRegistrationId` When Calling an API

A controller can use `ordersRestClient`:

~~~java
package com.example.portal.web;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;

@RestController
public class OrdersController {

    private final RestClient ordersRestClient;

    public OrdersController(
        @Qualifier("ordersRestClient") RestClient ordersRestClient
    ) {
        this.ordersRestClient = ordersRestClient;
    }

    @GetMapping("/bff/orders")
    public String orders() {
        return ordersRestClient.get()
            .uri("/api/orders")
            .attributes(clientRegistrationId("company"))
            .retrieve()
            .body(String.class);
    }
}
~~~

`clientRegistrationId("company")` specifies **which registration the HTTP client must use to resolve tokens**. Inside an authenticated HTTP request, the interceptor/manager needs the exact principal and Servlet request context; thus web integrations should be used in the context they support.

**Never use the `reports-service` registration to call the Orders API on behalf of a user** merely because `reports-service` also has an access token. Service tokens and user-issued tokens differ in subject, scopes/audience, and policy.

### 9.3. Should You Configure a Default Registration for All Requests?

Some integrations allow configuring a default registration/authorized client. If the application talks to multiple Resource Servers or uses multiple principal types, **do not** use a default Bearer token for all HTTP requests.

Prefer specifying the registration **explicitly at the API call site**, or binding a dedicated HTTP client to a controlled registration. That prevents sending user or service tokens to an unintended hostname.

### 9.4. Customizing Failure Handling

If the Orders API returns `401 invalid_token`, the integration may need an appropriate **authorized-client failure handler** to remove the invalid authorized client/token from the repository/service or require re-authorization. Exact policy depends on Spring Security version, HTTP client, and how the manager is built.

Never automatically destroy the user's HTTP session when one API token is rejected, and never infinitely retry the exact same token rejected by the Resource Server. In operations, distinguish `invalid_token` from `insufficient_scope` and 5xx service errors.

## 10. Wiring a Manager to `WebClient` in a Servlet Application

If a Spring MVC application needs `WebClient` to call APIs, Spring Security provides:

~~~java
org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction
~~~

**Having `reactive` in the package name does not mean this application must use `SecurityWebFilterChain`.** This class supports `WebClient` running in a Servlet environment with a **synchronous** `OAuth2AuthorizedClientManager`.

### 10.1. `WebClient` Bean

~~~java
package com.example.portal.config;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OrdersWebClientConfig {

    @Bean("ordersWebClient")
    WebClient ordersWebClient(
        @Qualifier("webAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager
    ) {
        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://orders.example.test")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

Spring Security automatically wires utilities for `Authorization` headers and authorized-client handling. The key thing to verify remains **that the constructor receives the exact manager we configured**.

### 10.2. Calling an API with `WebClient`

~~~java
package com.example.portal.service;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function
    .client.ServletOAuth2AuthorizedClientExchangeFilterFunction
    .clientRegistrationId;

@Service
public class OrdersGateway {

    private final WebClient client;

    public OrdersGateway(
        @Qualifier("ordersWebClient") WebClient client
    ) {
        this.client = client;
    }

    public Mono<String> fetchOrders() {
        return client.get()
            .uri("/api/orders")
            .attributes(clientRegistrationId("company"))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

This is a **Servlet application using `WebClient`**; `Mono` is `WebClient`'s return type, while **authentication and the manager remain Servlet-based**. If calling `WebClient` outside a request thread, be careful to propagate `SecurityContext`/Servlet request context properly. Do not assume Spring MVC `ThreadLocal` state propagates automatically across all reactive schedulers.

Do not switch to `ReactiveOAuth2AuthorizedClientManager` or `ServerHttpSecurity` just because an MVC application has a `WebClient` bean.

## 11. Comparing `RestClient` and `WebClient` with a Custom Manager

| Criterion | `RestClient` on Servlet | `WebClient` on Servlet |
|---|---|---|
| HTTP abstraction | Synchronous | Reactive/non-blocking API |
| OAuth2 integration | `OAuth2ClientHttpRequestInterceptor` (6.4+) | `ServletOAuth2AuthorizedClientExchangeFilterFunction` |
| Manager used | `OAuth2AuthorizedClientManager` | `OAuth2AuthorizedClientManager` |
| Security chain | `HttpSecurity` | **Still** `HttpSecurity` |
| Selecting registration | Request attributes / `clientRegistrationId` resolver | Exchange attributes `clientRegistrationId(...)` |
| Saving/refreshing tokens | Via manager/provider/repository | Via manager/provider/repository |
| Watch out for | Timeouts, pooling, never exposing Bearer tokens | Context propagation, reactive pipelines, never exposing tokens |

**Customizing a manager** is one step; **passing the manager into the HTTP integration** is the second step. Do not just create a bean and expect every `RestClient.create(...)` or `WebClient.create(...)` to automatically use the manager's tokens.

## 12. Dedicated Manager for Scheduled Jobs Using `client_credentials`

A periodic task has no browser, HTTP session, or `HttpServletRequest`. Instead of using `DefaultOAuth2AuthorizedClientManager` meant for web requests, create `AuthorizedClientServiceOAuth2AuthorizedClientManager`.

### 12.1. Configuring the Manager for a Job

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class JobAuthorizedClientConfig {

    @Bean("jobAuthorizedClientManager")
    OAuth2AuthorizedClientManager jobAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService clientService
    ) {
        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, clientService
            );
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

This manager:

- Supports only `client_credentials`, since the job needs no interactive OIDC login.
- Saves/loads authorized clients via `OAuth2AuthorizedClientService`.
- Requires no Servlet request/response.
- Uses dedicated registration `reports-service` with minimal scopes.

### 12.2. Using the Manager in a Job

~~~java
package com.example.portal.jobs;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ReportsJob {

    private final OAuth2AuthorizedClientManager manager;
    private final RestClient reportsApi =
        RestClient.create("https://reports.example.test");

    public ReportsJob(
        @Qualifier("jobAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager
    ) {
        this.manager = manager;
    }

    public String fetchDailySummary() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-service")
                .principal("reports-worker")
                .build();

        OAuth2AuthorizedClient authorizedClient =
            manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "No authorized client for reports-service"
            );
        }

        String accessToken =
            authorizedClient.getAccessToken().getTokenValue();

        return reportsApi.get()
            .uri("/api/reports/daily")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);
    }
}
~~~

Here `principal("reports-worker")` is the **stable name of the service principal in authorized-client storage**, not a Portal-authenticated OIDC user. Because the token comes from `client_credentials`, the API call relies on permissions granted to the **service client**.

The example uses `RestClient` manually to make the manager's token retrieval clear. In real applications, inject/configure the HTTP client with proper timeouts, TLS, proxies, logging, and error handling.

**Never use a `.principal("admin")` pattern with a user `authorization_code` registration to access another user's token.** A principal string is not proof of user login.

## 13. Why Define Two Clearly Named Manager Beans?

An application having both web requests and background jobs can declare:

~~~text
webAuthorizedClientManager -> DefaultOAuth2AuthorizedClientManager
jobAuthorizedClientManager -> AuthorizedClientServiceOAuth2AuthorizedClientManager
~~~

When two beans implement `OAuth2AuthorizedClientManager`, unqualified injection is ambiguous. Use `@Qualifier`:

~~~java
public MyService(
    @Qualifier("webAuthorizedClientManager")
    OAuth2AuthorizedClientManager manager
) {
    this.manager = manager;
}
~~~

or define specialized beans per type/configuration and mark a primary only when genuinely warranted.

Never rely on bean creation order, class names, or assume Spring Boot prioritizes one bean automatically. When multiple managers exist, **each consumer must explicitly know which manager it needs**.

### 13.1. Should All Grants Be Combined into One Manager?

It is possible, yet not always sensible:

- **Web manager** handles request/principal context and may include authorization code + refresh token.
- **Job manager** handles service principals and client credentials, typically using a different store.
- Keeping them separate limits which grants each component can use and reduces the chance of picking the wrong token by mistake.

Unify them only with a clear reason and strict control over principals, storage, and context so no caller crosses trust boundaries.

## 14. Do You Need to Attach the Manager to the `oauth2Client()` DSL?

This is the easiest point of confusion on this topic.

When writing:

~~~java
http.oauth2Client(Customizer.withDefaults());
~~~

you are configuring **Spring Security Servlet OAuth2 Client integration** at the filter layer. Within this DSL, customization options include **client registration repository**, **authorized client repository**, **authorized client service**, or **Authorization Code Grant** details depending on version.

However, in many Spring Security versions, there is no single method like:

~~~java
// Code illustrating a WRONG mental model; not a guaranteed API:
http.oauth2Client(oauth2 -> oauth2
    .authorizedClientManager(myManager));
~~~

Do not copy that hypothetical snippet into your project. **The manager is a separate integration point** for components consuming authorized clients:

~~~text
SecurityFilterChain:
    http.oauth2Client(...)

Manager bean:
    DefaultOAuth2AuthorizedClientManager(...)

HTTP client calling Resource Server:
    new OAuth2ClientHttpRequestInterceptor(manager)
    or
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager)
~~~

If the requirement is **customizing the provider chain / refresh / client credentials when calling APIs**, configure the manager and **pass it to the HTTP client**.

If the requirement is **customizing the authorization request or code-exchange step in the Servlet filter**, use the **`oauth2Client().authorizationCodeGrant(...)`** or **`oauth2Login()`** hooks for the appropriate flow.

### 14.1. Example Customizing Authorization Code Grant via the `oauth2Client` DSL

Spring Security Servlet allows replacing parts of the authorization-code flow:

~~~java
http.oauth2Client(oauth2 -> oauth2
    .authorizationCodeGrant(authorizationCode -> authorizationCode
        .authorizationRequestResolver(customAuthorizationRequestResolver)
        .authorizationRequestRepository(customAuthorizationRequestRepository)
    )
);
~~~

This is an **illustrative hook snippet**, where `customAuthorizationRequestResolver` and `customAuthorizationRequestRepository` are instances configured in the application. This hook handles the **initial authorization request**, not replacing the provider chain used for refresh tokens.

When using **OAuth2 Login**, the corresponding hook typically sits under:

~~~java
http.oauth2Login(login -> login
    .authorizationEndpoint(endpoint -> endpoint
        .authorizationRequestResolver(customAuthorizationRequestResolver)
    )
);
~~~

If configuring both `oauth2Login()` and `oauth2Client()`, verify filters, base URIs, repositories, and actual flows to avoid creating overlapping authorization request mechanisms. Do not assume the same resolver bean is used by every flow unless explicitly attached to the right DSL.

## 15. Customizing Login Token Exchange Differs from the API-Calling Manager

Spring Security OAuth2 Login has a step exchanging the authorization code for tokens after callback. If the requirement is a custom HTTP client/proxy/TLS for **login's token endpoint**, Servlet provides the hook:

~~~java
http.oauth2Login(login -> login
    .tokenEndpoint(tokenEndpoint -> tokenEndpoint
        .accessTokenResponseClient(customCodeTokenClient)
    )
);
~~~

Here `customCodeTokenClient` must be an:

~~~java
OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
~~~

with an implementation compatible with your Spring Security version (e.g., `RestClientAuthorizationCodeTokenResponseClient` in modern Spring Security, or `DefaultAuthorizationCodeTokenResponseClient` in older branches).

**Key distinction:**

- `oauth2Login().tokenEndpoint().accessTokenResponseClient(...)`: HTTP request **exchanging the authorization code for tokens to complete login**.
- `DefaultOAuth2AuthorizedClientManager` + provider chain: **authorizing/reissuing tokens for authorized clients when invoked by consumers**.
- `RestClient`/`WebClient` interceptor/filter: **attaching access tokens to outbound requests to Resource Servers**.

A custom manager for the Orders API does not automatically replace the HTTP token client used during the OIDC Login callback. If timeouts, CAs, or proxies must be aligned across steps, configure each relevant HTTP transport/hook explicitly.

## 16. How Do Authorized-Client Repository and Service Connect to the Manager?

In Servlet applications, the two abstractions play different roles:

~~~java
OAuth2AuthorizedClientRepository
OAuth2AuthorizedClientService
~~~

### 16.1. Repository in Web Requests

`OAuth2AuthorizedClientRepository` provides operations such as:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId,
    Authentication principal,
    HttpServletRequest request
);
~~~

along with save/remove operations in a Servlet context.

`DefaultOAuth2AuthorizedClientManager` typically uses this repository so tokens link to the current principal and HTTP request.

### 16.2. Service Outside Requests

`OAuth2AuthorizedClientService` provides save/load operations based on registration ID and principal name, without requiring `HttpServletRequest`:

~~~java
OAuth2AuthorizedClient loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
~~~

Hence, `AuthorizedClientServiceOAuth2AuthorizedClientManager` suits scheduled jobs or service workloads.

### 16.3. Some Implementations

| Implementation | Characteristics | Notes |
|---|---|---|
| `HttpSessionOAuth2AuthorizedClientRepository` | Stores authorized clients in the session | Tokens bound to session lifecycle; protect the session store |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Can delegate persistence to a service for authenticated principals | Understand branching by `Authentication` |
| `InMemoryOAuth2AuthorizedClientService` | Stores in application process memory | Not durable across restarts/scaling; risk of token loss |
| `JdbcOAuth2AuthorizedClientService` | Stores via JDBC | Requires schema management, encryption/token protection, and DB access control |

**Do not choose a repository just because it works locally.** In multi-replica production, evaluate session persistence, shared authorized-client stores, token encryption, retention, and cleanup.

## 17. When Is Token Refresh Triggered?

A common misconception: `OAuth2AuthorizedClientRepository.loadAuthorizedClient(...)` refreshes expired tokens automatically. Do not assume that.

The repository primarily **reads/writes tokens**. Only when invoked does the manager/provider decide whether to execute the **`refresh_token` grant**.

~~~mermaid
sequenceDiagram
    participant Browser as Browser
    participant C as OrdersController
    participant Http as RestClient OAuth2 Interceptor
    participant M as Custom AuthorizedClientManager
    participant Repo as Authorized Client Repository
    participant AS as Authorization Server
    participant API as Orders API

    Browser->>C: GET /bff/orders
    C->>Http: RestClient GET /api/orders, registration=company
    Http->>M: authorize(company, authenticated principal)
    M->>Repo: Load authorized client
    Repo-->>M: Access token AT1 near expiry, refresh token RT1
    M->>AS: POST token endpoint (refresh_token=RT1)
    AS-->>M: AT2 (+ RT2 if rotated)
    M->>Repo: Save new authorized client
    M-->>Http: Authorized client with AT2
    Http->>API: Authorization: Bearer AT2
    API-->>Http: 200 data
    Http-->>C: Response
    C-->>Browser: Result
~~~

The flow above assumes **the manager has a refresh provider**, the authorized client holds a refresh token, and the Authorization Server accepts the refresh. Not every grant issues a refresh token.

### 17.1. Clocks and Clock Skew

Tokens have `expiresAt`, and the manager/provider can compute an earlier refresh threshold so tokens do not expire mid-flight to the API.

When customizing providers, configure clock skew on providers that support it. Never duplicate mechanisms by both mutating `expiresAt` in the repository and adding an out-of-band async refresh cron without a clear design.

### 17.2. Refresh Token Rotation and Concurrency

Some OPs rotate refresh tokens:

~~~text
AT1 + RT1
   refresh RT1
   -> AT2 + RT2
   RT1 may be invalidated
~~~

If two requests hitting two replicas both read `RT1` and refresh simultaneously, one request can fail with `invalid_grant`. In multi-node deployments, address race conditions, consistent updates, and bounded retry policies. Never retry an already-rotated refresh token infinitely.

## 18. Difference Between Token Errors and User Logout

An OAuth2 Authorized Client can become unusable even while the user remains logged in to the Portal:

| State | Reasonable Behavior |
|---|---|
| Access token expired, refresh succeeded | Continue calling API; do not force user re-login |
| Refresh token no longer valid | Require re-authorization/consent per policy |
| Token has wrong audience/scope | Check registration/API config; refreshing with same scopes may not help |
| Resource Server 403 | Handle insufficient permissions; do not log out automatically |
| Orders API 5xx/timeout | Handle infrastructure failure and controlled retries |
| Portal HTTP session expired | Require Portal login, even if tokens remain in store |
| `reports-service` token failed | Do not log `company` users out, as it is a service registration |

Do not use a single `tokenValid` flag to represent the entire login session. OAuth2 token state and `SecurityContext` have independent lifecycles; calling an API requires checking `Authentication`, authorized client state, and Resource Server authorization policy.

## 19. Handling Token Issuance Errors in a Custom Manager

Common token endpoint errors:

- `invalid_client`: wrong client credentials or client authentication method.
- `invalid_grant`: invalid, already-used, expired, PKCE-mismatched, or revoked authorization code/refresh token.
- `invalid_scope`: requested scope not accepted.
- TLS handshake, timeout, DNS/proxy failure: network/transport error.

Spring Security has **authorization success/failure handlers** to coordinate saving or removing authorized clients after corresponding outcomes. If replacing default handlers with custom ones, ensure:

1. New/refreshed authorized clients **are saved** on success.
2. Invalid tokens **are removed from the store** when policy requires.
3. Valid authorized clients are not deleted merely due to transient network errors.
4. Client secrets, access tokens, refresh tokens, or authorization codes are never logged.
5. Errors are never swallowed to return a fake “successful” authorized client.

Wrong example:

~~~java
// Do not do this:
try {
    return manager.authorize(request);
} catch (Exception ex) {
    return oldAuthorizedClient; // May hold a rejected token.
}
~~~

If the token endpoint is disrupted, the application should return an appropriate error and follow external dependency SLO/circuit-breaker policies rather than assuming stale tokens are still trustworthy.

### 19.1. User Tokens and Service Tokens Should Not Share an Error Policy

For user `authorization_code`, failure may lead to **re-prompting user interaction**. For background `client_credentials`, failure should produce a **service error/alert/controlled retry**, never redirecting to a login screen in a browserless task.

That is another reason separating web and job managers keeps error policies clearer.

## 20. Customizing Manager Context

Beyond registration and principal, a manager needs **context attributes** when a grant requires extra data. On `DefaultOAuth2AuthorizedClientManager`, you can configure a context attributes mapper to map data from `OAuth2AuthorizeRequest` into `OAuth2AuthorizationContext`.

Situations that may need a mapper:

- The Authorization Server requires an agreed extension parameter.
- A grant customization needs a request-context attribute understood by the provider.
- Verified backend policy data needs to reach the authorization provider.

However:

- Never copy raw query parameters from the browser into token requests.
- Never let clients override `token-uri`, `client-id`, `client-secret`, or `redirect-uri` arbitrarily.
- Never place credentials into attributes that might be logged or returned to the frontend.
- Never assume a mapper turns an `authorization_code` grant into a new grant without a matching provider.

For simpler needs like adding scopes or provider parameters, consider **`ClientRegistration`** and standard token-response client/provider extension points first instead of writing a manager from scratch.

## 21. Controlling Principals in the Manager

Managers typically identify authorized clients by registration and principal. In a multi-user app:

~~~text
company + employee-0042 -> employee-0042's token
company + employee-0177 -> employee-0177's token
~~~

**Never use a browser-sent `principalName`**:

~~~http
GET /bff/orders?principalName=admin HTTP/1.1
~~~

and pass that raw string into `OAuth2AuthorizeRequest.principal(...)` to grab a token saved under `admin`. That creates a **confused deputy** vulnerability and leaks someone else's token.

For user-authorized flows, obtain the principal from the request's verified `Authentication`. For service `client_credentials`, use a fixed, controlled service principal rather than mapping to a user identity to bypass permissions.

### 21.1. When a User Changes Email

Some token stores key by `(registrationId, principalName)`. If `Authentication.getName()` is configured from email and the email changes, the application may fail to find the old authorized client.

With OIDC, design identity mapping around `(iss,sub)` and understand the impact of changing `user-name-attribute`. Never fall back to grabbing a token belonging to the same email under a different client registration.

## 22. Client Manager Does Not Replace API Authorization

Suppose the Orders API requires `orders.write` to delete an order:

~~~text
Principal logged in to Portal
    |
    v
Manager obtains token with scope orders.read
    |
    v
DELETE /api/orders/123
    |
    v
Orders API returns 403 insufficient_scope
~~~

The manager cannot grant extra permissions just because the user is logged in. A new token must be issued by the Authorization Server per registration/policy, and the Resource Server still retains authority to deny requests.

In multi-tenant systems, having scope `orders.read` is also insufficient to view every order; the Orders API must enforce tenant/ownership checks and resource-specific conditions. **Token lifecycle** is separate from **business authorization**.

## 23. When Do You Need to Implement `OAuth2AuthorizedClientManager` Yourself?

Most projects **do not need to implement the `OAuth2AuthorizedClientManager` interface** from scratch. You can customize by:

1. Picking the right manager class: web or service.
2. Using `OAuth2AuthorizedClientProviderBuilder` to build the provider chain.
3. Configuring token response clients (timeouts, TLS, client authentication) per grant if needed.
4. Selecting the authorized client repository/service.
5. Configuring context mappers and success/failure handlers when required.
6. Passing the manager into `RestClient`/`WebClient` integrations or specific consumers.

Writing a custom manager implementation may make sense for **complex multi-tenant / policy-isolation architectures**, provided you preserve validation, concurrency, token lifecycle, and OAuth2 error semantics. Avoid hand-rolling token refreshes over raw HTTP merely to adjust timeouts.

## 24. Multi-Replica Deployments and Token Storage

A production topology:

~~~text
             ┌─────────────────┐
Browser ───► │ Load Balancer   │
             └──────┬──────────┘
                 ┌──┴──┐
                 v     v
             Portal A  Portal B
                 |     |
                 └──┬──┘
                    v
              Session Store
                    |
              Authorized Client Store
                    |
                    v
              Authorization Server
~~~

Design considerations:

- **Authorization request correlation**: when the browser returns via callback, the Portal must find the saved state. This is the responsibility of the session / authorization request repository.
- **Authentication/session**: user requests hitting node B must still find the valid session's `SecurityContext`.
- **Authorized client storage**: node B must find tokens saved by node A, if sharing is required.
- **Refresh token rotation**: prevent two nodes from consuming the same old refresh token without synchronization.
- **Secret/token protection**: encryption-at-rest if required by policy, RBAC, and TTL; never log tokens.

A shared session does not automatically mean a shared authorized-client store, and vice versa. Pick storage consistent with the manager/repository in use.

## 25. Testing: How to Verify the HTTP Client Actually Uses the New Manager?

**You do not need to hit the production Authorization Server to test integration.** Several key test targets:

| Test Scenario | What to Verify |
|---|---|
| Manager bean created | Provider chain and dependencies are right, no ambiguity between web/job managers |
| `RestClient` calls Orders API | Interceptor uses `webAuthorizedClientManager` |
| Registration selection | Orders call uses `company`, not `reports-service` |
| Valid token | Manager returns existing authorized client without unnecessary token endpoint calls |
| Expired token with refresh token | Refresh provider is invoked per policy |
| Refresh returns `invalid_grant` | Proper failure handling; never returns stale token as valid |
| Job without Servlet request | `jobAuthorizedClientManager` can use `client_credentials` |
| Two concurrent users | Never picks up another principal's token |
| Resource Server 403 | Does not unconditionally log out session |
| Multi-node token rotation | Latest state/token persisted consistently on refresh |

### 25.1. Unit Test with a Mocked Manager

In HTTP integration unit tests, you can stub `OAuth2AuthorizedClientManager.authorize(...)` to return an `OAuth2AuthorizedClient` with a test access token, then use a mock HTTP server to verify the request sends the **right Bearer token** without calling a real IdP.

Conceptual example:

~~~text
Given:
  manager.authorize(registration=company, principal=employee-0042)
  -> AuthorizedClient(accessToken=TEST_AT)

When:
  ordersRestClient.get(/api/orders)
    attributes(clientRegistrationId(company))

Then:
  outbound request has Authorization: Bearer TEST_AT
  does not leak refresh token
~~~

This is a **test fixture description**, not a test execution report. Testing grant providers and refreshes can use a fake token endpoint / `MockWebServer` to simulate OAuth2 JSON success/error responses.

### 25.2. Integration Tests with Spring Security Test

In Servlet tests, you can use `spring-security-test` and `oidcLogin()` to create a mock principal, then invoke a controller backed by a mocked `RestClient`. That tests **principal and manager wiring**, yet **does not replace** testing OIDC callbacks and ID Token signature validation in an appropriate integration environment.

Never use real client secrets or production access tokens as test fixtures.

## 26. Symptom-Based Troubleshooting

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Custom manager declared yet API calls still use old config | HTTP client was not injected with new manager | Check `RestClient` interceptor / `WebClient` filter constructor |
| Injecting `OAuth2AuthorizedClientManager` fails with multiple beans | Both web and job managers exist | Use `@Qualifier` or clearer bean structure |
| Token request does not refresh | Provider chain lacks `refreshToken()`, manager not invoked, or no refresh token | Check registration, provider, and entry point |
| Job reports missing Servlet request | Using `DefaultOAuth2AuthorizedClientManager` outside HTTP request | Use `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| User login succeeds yet Orders API returns 401 | Token expired, wrong audience, or revoked | Separate session from token; inspect redacted error response |
| API returns 403 even though refresh succeeded | Missing scope/permission | Check authorization policy; do not treat refresh as privilege escalation |
| Client credentials token used for user request | Wrong registration or principal mapping chosen | Restrict managers/registrations per consumer |
| Authorized client missing after email change | Token storage principal name changed | Check `user-name-attribute` and storage key |
| OAuth2 Login token POST still uses old timeout | Only replaced API-calling manager, not login token client | Check `oauth2Login().tokenEndpoint()` |
| Background job hits `invalid_grant` | Wrong grant/provider or refresh token rotation | Check registration, concurrency, and AS policy |
| Token exists in DB yet browser is not logged in | Authorized client persists longer than session | Never use stored tokens to authenticate browser requests |
| `RestClient` sends Bearer to unknown domain | HTTP client uses default token for all URIs | Restrict base URLs/registrations and trust boundaries |
| Redirect loop during authorization | Mismatched resolver/filter/repository, callback mismatch | Check authorization URI, `state`, callback, session |

**Isolation method:** identify whether the request stopped at the **authorization redirect**, **callback**, **token endpoint**, **authorized-client manager**, or **Resource Server**. The same 401/403 at the browser can originate from very different layers.

## 27. Common Design Mistakes

**1. Enabling `oauth2Client` and assuming every `RestClient` gets tokens automatically.** No. Only HTTP clients configured with OAuth2 integration and the proper manager resolve tokens.

**2. Creating a manager bean without passing it to consumers.** Having a bean in the Spring context does not prove an HTTP client uses it.

**3. Changing OAuth2 Login's token client to fix refresh in the Orders API.** Those are two distinct integration points.

**4. Using the web manager in a scheduled job without an `HttpServletRequest`.** Use the service manager.

**5. Using a browser-supplied principal string.** Risks retrieving another user's token.

**6. Treating a `client_credentials` token as a user token.** A service grant does not replace OIDC user login.

**7. Setting a default authorized client for arbitrary requests.** Risks sending Bearer tokens to the wrong host/resource.

**8. Infinitely retrying a rotated refresh token.** Control concurrency and updated state.

**9. Checking only `expiresAt` and assuming the API will accept the token.** APIs also verify issuer, audience, scopes, revocation, and resource permissions.

**10. Logging tokens/secrets for debugging.** Access tokens, refresh tokens, authorization codes, and client secrets must all be protected.

## 28. Practical Exercises

### Exercise 1 — Custom Manager Exists Yet Is Unused

The Portal declared:

~~~java
@Bean
OAuth2AuthorizedClientManager myManager(...) {
    // ...
}
~~~

Yet the Orders API is still called with:

~~~java
RestClient restClient = RestClient.create();
~~~

**Question:** Why is the custom manager not orchestrating tokens?

**Solution:** The `RestClient` instance has no `OAuth2ClientHttpRequestInterceptor` or matching OAuth2 integration. Inject the manager into the interceptor and use that configured `RestClient` when calling the API.

### Exercise 2 — Scheduled Job Using the Wrong Manager

A job runs every morning with no user login, using `DefaultOAuth2AuthorizedClientManager` with a repository requiring a Servlet request.

**Question:** Which manager fits better?

**Solution:** `AuthorizedClientServiceOAuth2AuthorizedClientManager` with `OAuth2AuthorizedClientService` and the `clientCredentials()` provider.

### Exercise 3 — Token Expired While Session Remains Active

The user logged into `company`, the access token expired, and a refresh token exists.

**Question:** Must the user log in again?

**Solution:** No. A manager with `refreshToken()` and a valid token can refresh. Only if refresh fails is re-authorization required per policy.

### Exercise 4 — Insufficient Scope

Orders API requires `orders.write`, while registration `company` only has `orders.read`.

**Question:** Does adding `clientCredentials()` to the manager increase the user's permissions?

**Solution:** No. The client credentials grant does not grant permissions on behalf of a user and does not alter the existing registration's scopes. You need the proper permissions/scopes from the Authorization Server and API authorization.

### Exercise 5 — Changing Login Token Endpoint HTTP Transport

The team needs mTLS or a proxy when exchanging the authorization code after the OIDC callback. They updated `RestClient` for the Orders API, yet login token endpoint errors persist.

**Question:** Which hook should they inspect?

**Solution:** The token-response client wired into `oauth2Login().tokenEndpoint().accessTokenResponseClient(...)` and its HTTP transport, not just the HTTP client calling the Orders API.

### Exercise 6 — Two Managers in the Spring Context

A web application has both `webAuthorizedClientManager` and `jobAuthorizedClientManager`. A service injects `OAuth2AuthorizedClientManager` without specifying which bean.

**Question:** How should this be fixed?

**Solution:** Inject explicitly with `@Qualifier` or separate configurations by matching interfaces/types. Each consumer uses the exact manager suited to its context and grant.

## 29. Checklist for Wiring a Custom Manager

| Question | What to Verify |
|---|---|
| Is this a Servlet or Reactive application? | For Servlet, use `HttpSecurity` and `OAuth2AuthorizedClientManager` |
| Is user login needed? | `oauth2Login()` for OIDC login |
| Is OAuth2 Client authorization via filters needed? | `oauth2Client()` for flows requiring support |
| Which grants are actually used? | Authorization code, refresh token, client credentials |
| Which manager class fits? | Web request manager vs. service/background manager |
| Which repository/service stores tokens? | Matches session, persistence, HA, and security needs |
| Is the provider chain configured? | Enable only needed grants, never broaden arbitrarily |
| Does the HTTP client use the manager? | `RestClient` interceptor or Servlet `WebClient` OAuth2 filter |
| Where is registration ID selected? | Explicitly per API/consumer, never from untrusted input |
| Where does the principal come from? | User's `Authentication` or controlled service identity |
| Where does token refresh happen? | When manager/provider is called, not automatically from repository alone |
| Does the login token endpoint need custom transport? | May need hooks in `oauth2Login().tokenEndpoint()` |
| Are `invalid_grant`/revocation handled? | Failure handler, cleanup, and user recovery action |
| Can multiple replicas race on refresh tokens? | Shared store, concurrency, and refresh token rotation |
| Does the API enforce its own authorization? | Scopes, audience, tenant/ownership, and resource permissions |
| Do logs leak credentials? | Never log Bearer tokens, secrets, codes, or refresh tokens |

## 30. Summary

In Spring Security OAuth 2.0/OIDC Client on Servlet, **`oauth2Client()`** configures OAuth2 Client mechanisms in `SecurityFilterChain`, yet **does not automatically turn every HTTP client into a token-managing client**. To apply custom token policies, build an `OAuth2AuthorizedClientManager` with the right **registration repository, authorized-client repository/service, and provider chain**, and then **wire the manager into the consumers actually calling APIs**.

For user requests, `DefaultOAuth2AuthorizedClientManager` coordinates Servlet context and the authorized-client repository. For scheduled jobs or service-to-service calls without an HTTP request, `AuthorizedClientServiceOAuth2AuthorizedClientManager` fits better. For HTTP clients, `OAuth2ClientHttpRequestInterceptor` for `RestClient` (Spring Security 6.4+) or `ServletOAuth2AuthorizedClientExchangeFilterFunction` for `WebClient` on Servlet resolves tokens through the specified manager.

Finally, maintain clear boundaries between **OIDC login**, **OAuth2 authorized-client lifecycle**, **token exchange**, **Bearer tokens used at Resource Servers**, and **business authorization**. Properly wiring the right manager not only keeps refresh and token storage consistent, but also prevents misusing principals, registrations, or credentials when a Portal serves both user logins and background jobs.
