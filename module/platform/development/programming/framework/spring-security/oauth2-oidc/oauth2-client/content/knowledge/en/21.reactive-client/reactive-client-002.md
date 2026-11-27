# 21.2. DefaultReactiveOAuth2AuthorizedClientManager in ServerWebExchange

## 1. Problem: Obtaining an Access Token in a WebFlux HTTP Request

Suppose a reporting portal is built with **Spring Boot WebFlux**. Users sign in with OpenID Connect (OIDC) through the enterprise identity provider. Afterward, they open the reports page; the backend needs to call the Reports API using an **access token issued for the right ClientRegistration and the right user**.

Typical steps in a request are:

1. The browser sends <code>GET /reports</code> to the WebFlux application.
2. Spring Security restores the <code>Authentication</code> from the reactive security context/WebSession.
3. The application selects a <code>ClientRegistration</code>, for example <code>company</code>.
4. The application retrieves the stored <code>OAuth2AuthorizedClient</code>, or requests a refresh if the access token is about to expire and a suitable refresh token exists.
5. <code>WebClient</code> sends the access token to the authorized Reports API.
6. The backend processes the returned data, or handles HTTP 401/403 according to the exact cause.

In Servlet, learners may already know <code>DefaultOAuth2AuthorizedClientManager</code> combining <code>OAuth2AuthorizedClientRepository</code> and <code>HttpServletRequest</code>. In **Reactive WebFlux**, the corresponding component for HTTP requests is:

**<code>DefaultReactiveOAuth2AuthorizedClientManager</code>**.

It coordinates the **reactive registration repository**, **server authorized-client repository**, **authorization providers**, and **<code>ServerWebExchange</code>** to issue, refresh, save, and return authorized clients without using the Servlet API.

> **Key point to remember:** <code>DefaultReactiveOAuth2AuthorizedClientManager</code> is designed for the **WebFlux HTTP request context**. It is not a token store, not an OpenID Provider, does not automatically know the target API's business permissions, and is not necessarily the best manager for background jobs without a <code>ServerWebExchange</code>.

## 2. Lesson Objectives

After this lesson, you will be able to:

- Explain the role of <code>ReactiveOAuth2AuthorizedClientManager</code> and the default implementation for <code>ServerWebExchange</code>.
- Distinguish <code>ReactiveClientRegistrationRepository</code>, <code>ServerOAuth2AuthorizedClientRepository</code>, <code>ReactiveOAuth2AuthorizedClientService</code>, and <code>OAuth2AuthorizedClient</code>.
- Understand how <code>OAuth2AuthorizeRequest</code> carries the registration ID, <code>Authentication</code>, and WebFlux exchange context.
- Configure <code>ReactiveOAuth2AuthorizedClientProvider</code> for Authorization Code, Refresh Token, and Client Credentials.
- Use <code>manager.authorize(...)</code> with <code>Mono&lt;OAuth2AuthorizedClient&gt;</code> **without calling <code>block()</code>** inside a WebFlux request.
- Combine an authorized client with <code>WebClient</code> to call a Resource Server with the right audience/scope.
- Choose a manager **independent of web exchange** when running a scheduler/job.
- Diagnose errors caused by missing exchange, wrong registration, wrong principal, expired tokens, and multi-instance storage configuration.

## 3. Related Components

### 3.1. The Big Picture

~~~mermaid
flowchart TD
    B["Browser request"] --> W["WebFlux ServerWebExchange"]
    W --> SEC["SecurityWebFilterChain / Authentication"]
    W --> APP["Reactive Controller / Service"]
    SEC --> APP
    APP --> M["DefaultReactiveOAuth2AuthorizedClientManager"]
    M --> REG["ReactiveClientRegistrationRepository"]
    M --> STORE["ServerOAuth2AuthorizedClientRepository"]
    M --> P["ReactiveOAuth2AuthorizedClientProvider"]
    P --> G1["authorization_code"]
    P --> G2["refresh_token"]
    P --> G3["client_credentials"]
    G2 --> AS["Authorization Server / Token Endpoint"]
    G3 --> AS
    M --> AC["Mono<OAuth2AuthorizedClient>"]
    AC --> CLIENT["WebClient / Bearer access token"]
    CLIENT --> API["Resource Server"]
~~~

Not every request goes through every grant. The provider is chosen based on the <code>ClientRegistration</code>, existing authorized client, token refresh conditions, and request context.

### 3.2. Responsibility Comparison Table

| Component | Primary responsibility | What not to confuse it with |
|---|---|---|
| <code>ClientRegistration</code> | Configures Client ID, grant type, scopes, token endpoint, issuer | Not an issued token |
| <code>ReactiveClientRegistrationRepository</code> | Finds <code>ClientRegistration</code> by registration ID via reactive API | Does not store access tokens |
| <code>OAuth2AuthorizedClient</code> | Binds ClientRegistration + principalName + access token + optional refresh token | Not an <code>OidcUser</code> |
| <code>ServerOAuth2AuthorizedClientRepository</code> | Load/save/remove authorized clients in <code>ServerWebExchange</code> | Does not refresh tokens by itself |
| <code>ReactiveOAuth2AuthorizedClientService</code> | Reactive load/save/remove authorized clients by registration/principal | Does not require Servlet request |
| <code>ReactiveOAuth2AuthorizedClientProvider</code> | Executes authorization/refresh grant when appropriate | Does not perform storage itself |
| <code>DefaultReactiveOAuth2AuthorizedClientManager</code> | Coordinates the components above in a web request | Does not open browser login on its own instead of filters |
| <code>ServerWebExchange</code> | Wraps reactive request/response/session/context of one HTTP turn | Not a global singleton |
| <code>WebClient</code> | Sends asynchronous downstream HTTP requests | Does not know audience/scope unless configured |

### 3.3. The Authorized Client Key

In common service implementations, an authorized client is identified by:

~~~text
(clientRegistrationId, principalName)
~~~

For example:

~~~text
(company, user-123)  → user-123's access token for registration company
(company, user-456)  → user-456's access token
(partner, user-123)  → a different access token of user-123 at partner
~~~

These usernames are illustrative only. <code>principalName</code> is usually taken from <code>Authentication.getName()</code>; with OIDC it may be based on the <code>sub</code> claim, though applications can customize it. Never assume principal name is always an email or always equals <code>sub</code>.

If multiple issuers/tenants can share the same subject string, partition the principal key to avoid collisions. Keying locks/storage solely by subject without issuer or tenant scope can mix up tokens across different accounts.

## 4. What Is ServerWebExchange and Why Does the Manager Need It?

In Spring WebFlux, <code>ServerWebExchange</code> represents the context of **one HTTP exchange**, containing:

- <code>ServerHttpRequest</code>.
- <code>ServerHttpResponse</code>.
- Access to <code>WebSession</code> via reactive API.
- Exchange attributes and related routing/request metadata.
- The bridge to web security, session, and authorized-client repository mechanisms.

It is **not** an <code>HttpServletRequest</code>, <code>HttpServletResponse</code>, nor a global object allowed to be stored in a static field for reuse across requests.

A <code>ServerOAuth2AuthorizedClientRepository</code> needs the request, authentication, and exchange to decide where to load the authorized client from and how to save it.

Example interface methods:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        ServerWebExchange exchange);

Mono<Void> saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal,
        ServerWebExchange exchange);

Mono<Void> removeAuthorizedClient(
        String clientRegistrationId,
        Authentication principal,
        ServerWebExchange exchange);
~~~

This is an excerpt of *illustrative method signatures*, not a complete copy-paste class. They highlight the difference from a service that only accepts a registration ID and principalName.

### 4.1. ServerWebExchange and Reactor Context Are Different Concepts

<code>ServerWebExchange</code> describes an HTTP exchange; <code>ReactiveSecurityContextHolder</code> carries the security context in the **Reactor Context**. An application should not assume that having an exchange automatically provides the right <code>Authentication</code>, or that having an Authentication automatically allows fetching the exchange from a thread-local.

~~~text
ServerWebExchange           → HTTP request, response, WebSession
Authentication              → principal, authorities, authenticated state
Reactor Context             → reactive context propagated through the pipeline
OAuth2AuthorizeRequest      → registration + principal + attributes needed by manager
~~~

A WebFlux controller can accept <code>Authentication</code> and <code>ServerWebExchange</code> as method parameters, then pass both to a dedicated service.

### 4.2. Distinguishing Web Requests from Background Jobs

A scheduled job does not inherently have an exchange:

~~~java
@Scheduled(fixedDelay = 60_000)
public void runJob() {
    // There is no browser ServerWebExchange here.
}
~~~

Never fabricate an arbitrary fake <code>ServerWebExchange</code> just to use the web manager inside a job. In environments without an HTTP exchange, Spring Security provides **<code>AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager</code>** backed by <code>ReactiveOAuth2AuthorizedClientService</code>, which is usually much more appropriate.

## 5. How the Manager Processes authorize(...)

Abstraction:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import reactor.core.publisher.Mono;

Mono<OAuth2AuthorizedClient> authorizedClient =
    manager.authorize(authorizeRequest);
~~~

<code>authorize(...)</code> is a **reactive operation**. The result is represented as <code>Mono&lt;OAuth2AuthorizedClient&gt;</code>, not a synchronous authorized client returned immediately.

Conceptual flow:

~~~mermaid
flowchart TD
    A["manager.authorize(request)"] --> B["Extract registration ID and principal"]
    B --> C["Look up ClientRegistration"]
    C --> D["Look up authorized client in repository"]
    D --> E{"Is current token eligible for use?"}
    E -->|Yes| F["Return existing authorized client"]
    E -->|No / absent| G["Pass OAuth2AuthorizationContext to providers"]
    G --> H{"Can a provider handle it?"}
    H -->|Yes| I["Token request / refresh when appropriate"]
    I --> J["Save new authorized client via success handler"]
    J --> K["Return Mono<OAuth2AuthorizedClient>"]
    H -->|No| L["Mono.empty or context-dependent result"]
    I -->|Failure| M["OAuth2AuthorizationException / failure handler"]
~~~

The diagram depicts **conceptual** logic; exact framework ordering, handling of existing authorized clients, and decisions to return <code>Mono.empty()</code> depend on the provider/manager/version. Never catch every <code>Mono.empty()</code> and fabricate a fake token.

### 5.1. When a Valid Access Token Already Exists

Suppose the repository currently holds:

~~~text
registrationId=company
principalName=user-123
accessToken.expiresAt=11:00
now=10:30
~~~

If the token is still usable under expiry/clock-skew policy and no reauthorization is requested, the manager can normally reuse the existing authorized client, avoiding unnecessary Token Endpoint calls.

### 5.2. Access Token Close to Expiration with a Refresh Token

~~~text
registrationId=company
principalName=user-123
accessToken.expiresAt=10:31
refreshToken=R0
now=10:30:30
~~~

If the <code>refreshToken()</code> provider is configured and the refresh token is accepted by the Authorization Server, the manager can refresh:

~~~text
R0 → POST /token grant_type=refresh_token
   → access token A1
   → refresh token R1 if provider rotates
   → save new authorized client
~~~

Not every OIDC Authorization Code Flow receives a refresh token. The provider, scopes, consent, and policy determine whether a refresh token exists.

### 5.3. When No Authorized Client Exists Yet

If the repository does not hold a token yet, whether the manager can create an authorized client depends on the ClientRegistration and providers:

- For Client Credentials Grant, the manager can request a service access token if client authentication and providers are suitable.
- For Authorization Code Grant, a proper browser authorization flow must occur; without an authorization code, the manager cannot open the OP page from a service method.
- With only a Refresh Token Provider, no refresh can occur without an existing refresh token.

### 5.4. Mono.empty, Errors, and Null

With the reactive API, do not write:

~~~java
OAuth2AuthorizedClient result = manager.authorize(request); // wrong type
~~~

Instead:

~~~java
return manager.authorize(request)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No OAuth2 authorized client")));
~~~

<code>Mono.empty()</code> represents a publisher that emits no value. <code>Mono.error(...)</code> represents a failure to handle. Never use <code>onErrorResume</code> to fall back to another user's token.

## 6. Creating a Minimal WebFlux OAuth2/OIDC Client Application

### 6.1. Dependencies

Example using Java 17, Spring Boot 3, and Spring Security 6:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

For an application intended to run on Reactive WebFlux, avoid accidentally adding <code>spring-boot-starter-web</code>. When both MVC and WebFlux are present, Spring Boot typically prefers MVC/Servlet; in that case <code>SecurityWebFilterChain</code> configuration may not be used as expected.

### 6.2. ClientRegistration for OIDC Authorization Code

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
              - reports.read
        provider:
          company:
            issuer-uri: https://idp.example.org/realms/company
~~~

These values are placeholders. The <code>reports.read</code> scope is only meaningful if the OP actually grants permission for the Reports API, and the Reports API is designed to accept tokens with that matching audience/scope. Do not send an access token intended only for UserInfo to an unrelated business API.

Secrets should live in a secret manager or environment variables. Redirect URIs must be registered accurately at the OP, and production systems must use trusted HTTPS.

### 6.3. SecurityWebFilterChain

~~~java
package example.security;

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
    SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error", "/assets/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Here:

- <code>oauth2Login()</code> handles browser login, the authorization code callback, OIDC authentication, and creating the user principal.
- <code>oauth2Client()</code> provides OAuth2 Client support in WebFlux for use cases that obtain authorized clients/call APIs.
- <code>SecurityWebFilterChain</code> serves reactive requests; do not use Servlet's <code>HttpSecurity</code>.
- Browser login typically involves WebSession and CSRF protection according to Spring Security's web policy.

If an application only needs login and does not call downstream APIs, enabling every OAuth2 Client feature beyond what is needed is unnecessary. The example enables both because this lesson requires the authorized-client manager.

## 7. Configuring DefaultReactiveOAuth2AuthorizedClientManager

We explicitly configure the manager with a repository and provider:

~~~java
package example.security;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
public class ReactiveAuthorizedClientManagerConfig {

    @Bean("webAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager webAuthorizedClientManager(
        ReactiveClientRegistrationRepository clientRegistrations,
        ServerOAuth2AuthorizedClientRepository authorizedClientRepository) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken(configurer -> configurer
                    .clockSkew(Duration.ofSeconds(60)))
                .build();

        var manager = new DefaultReactiveOAuth2AuthorizedClientManager(
            clientRegistrations, authorizedClientRepository);

        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

This is an **explicit configuration to learn how the abstractions wire together**, which does not mean Spring Boot cannot auto-configure equivalent components. When a project already has a manager, avoid creating multiple beans of the same type without specifying which bean is used by HTTP clients/services.

### 7.1. Constructor Accepts Two Dependencies

~~~java
new DefaultReactiveOAuth2AuthorizedClientManager(
    clientRegistrations,
    authorizedClientRepository)
~~~

**<code>clientRegistrations</code>** is a <code>ReactiveClientRegistrationRepository</code> used to look up Client configurations by <code>registrationId</code>.

**<code>authorizedClientRepository</code>** is a <code>ServerOAuth2AuthorizedClientRepository</code> handling authorized client storage within a <code>ServerWebExchange</code> context.

Do not pass a Servlet-style <code>ClientRegistrationRepository</code> or synchronous <code>OAuth2AuthorizedClientService</code> into the reactive constructor.

### 7.2. Provider Matching the Active Grants

~~~java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();
~~~

For example, web login uses Authorization Code Flow, while the refresh token provider handles updating existing tokens when needed.

**Adding <code>authorizationCode()</code> does not replace authorization redirect/callback WebFilters.** The phase where the user signs in at the OP is still handled by <code>oauth2Login()</code> and the reactive security configuration.

If a registration uses client credentials inside a web request under a valid policy, <code>clientCredentials()</code> can be added to the delegating provider. However, never treat a service token as representing a logged-in user.

### 7.3. Clock Skew

~~~java
.refreshToken(configurer ->
    configurer.clockSkew(Duration.ofSeconds(60)))
~~~

The token can be considered in need of refresh 60 seconds before expiry to reduce the risk of expiring mid-request. The 60-second value is an example; adjust it based on token lifetime, clock drift, and network latency.

Clock skew does not extend the actual token lifetime, does not guarantee the refresh token is still valid, and does not solve refresh races across multiple replicas.

## 8. OAuth2AuthorizeRequest: Connecting Registration, Authentication, and Exchange

This is the most important aspect when calling <code>DefaultReactiveOAuth2AuthorizedClientManager</code> directly.

A request contains these parts:

~~~text
OAuth2AuthorizeRequest
  ├── clientRegistrationId: company
  ├── principal: current user's Authentication
  └── attributes: HTTP request's ServerWebExchange
~~~

Example inside a reactive web request:

~~~java
OAuth2AuthorizeRequest authorizeRequest =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("company")
        .principal(authentication)
        .attribute(ServerWebExchange.class.getName(), exchange)
        .build();
~~~

Key distinctions:

- <code>"company"</code> identifies which ClientRegistration will be looked up.
- <code>authentication</code> represents the current principal; use it instead of a username sent by the browser.
- <code>exchange</code> provides the WebFlux HTTP request context so the repository can perform load/save/remove.
- The key <code>ServerWebExchange.class.getName()</code> is recognized by the manager/web integration in context per the Spring Security API.

Without a ServerWebExchange in a flow that requires an exchange, loading/saving the authorized client may fail or not work as expected. **Do not create a fake exchange outside an HTTP request to mask an architectural flaw**; background jobs should use the service manager.

### 8.1. Why Use Authentication Instead of a Subject String?

For user logins:

~~~java
.principal(authentication)
~~~

binds the authorized client to the <code>Authentication</code> verified by Spring Security.

Do not do:

~~~java
.principal(exchange.getRequest().getQueryParams()
    .getFirst("user"))
~~~

The latter lets the caller pick an arbitrary principal key. If the store holds tokens for multiple users, this risks accessing the wrong token or leaking another user's token.

### 8.2. principalName Is Not Scope

<code>principalName</code> identifies the user/service in storage. It does **not** determine OAuth scopes or token audience. Obtaining the <code>reports.read</code> scope requires configuring ClientRegistration and having the Authorization Server issue it; the Resource Server still verifies permissions when receiving the token.

### 8.3. Do Not Store ServerWebExchange in a Singleton

Wrong:

~~~java
@Component
class BadExchangeHolder {
    private ServerWebExchange currentExchange; // dangerous
}
~~~

A Spring singleton can serve many concurrent requests. Keeping an exchange in a shared mutable field causes races and user mix-ups. Pass the exchange via method parameters or keep it within the request's reactive execution context.

## 9. Complete Example: Using the Manager Directly in a Reactive Service

The example below uses the manager configured in section 7, obtains an authorized client, and calls the Reports API with WebClient.

### 9.1. Dedicated WebClient for the Reports API

~~~java
package example.reports;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsWebClientConfig {

    @Bean("reportsWebClient")
    WebClient reportsWebClient(
        WebClient.Builder builder,
        @Value("${app.reports-api.base-url}") String baseUrl) {
        return builder.baseUrl(baseUrl).build();
    }
}
~~~

Property:

~~~yaml
app:
  reports-api:
    base-url: https://api.example.org
~~~

This is the **Resource Server**, not the OP's Token Endpoint. The base URL comes from trusted configuration; never let the browser supply arbitrary URLs to prevent SSRF or bearer token leakage.

### 9.2. Reactive Service Retrieving an Authorized Client

~~~java
package example.reports;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Service
public class ReactiveReportsService {

    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient reportsWebClient;

    public ReactiveReportsService(
        @Qualifier("webAuthorizedClientManager")
        ReactiveOAuth2AuthorizedClientManager manager,
        @Qualifier("reportsWebClient") WebClient reportsWebClient) {
        this.manager = manager;
        this.reportsWebClient = reportsWebClient;
    }

    public Mono<String> loadReports(
        Authentication authentication,
        ServerWebExchange exchange) {

        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("company")
                .principal(authentication)
                .attribute(ServerWebExchange.class.getName(), exchange)
                .build();

        return manager.authorize(request)
            .switchIfEmpty(Mono.error(
                new IllegalStateException(
                    "No authorized client for company")))
            .flatMap(client -> callReportsApi(client));
    }

    private Mono<String> callReportsApi(
        OAuth2AuthorizedClient client) {

        String token = client.getAccessToken().getTokenValue();

        return reportsWebClient.get()
            .uri("/v1/reports")
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .bodyToMono(String.class);
    }
}
~~~

**Important points:**

1. <code>manager.authorize(request)</code> returns a <code>Mono</code>.
2. <code>switchIfEmpty(...)</code> handles the case where no authorized client exists.
3. <code>flatMap</code> calls the Reports API only after obtaining the token.
4. WebClient sends the Bearer token **server-to-server**; never return the access token to the browser.
5. The code does not call <code>block()</code> or manual <code>subscribe()</code>.
6. Each request passes the right <code>Authentication</code> and <code>ServerWebExchange</code>.

In production, use DTOs, timeouts, response validation, payload size limits, and HTTP error handling. Returning <code>String</code> here keeps focus on the manager lifecycle.

### 9.3. Controller Calling the Service

~~~java
package example.reports;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ReportsController {

    private final ReactiveReportsService reports;

    public ReportsController(ReactiveReportsService reports) {
        this.reports = reports;
    }

    @GetMapping("/reports")
    public Mono<String> loadReports(
        Authentication authentication,
        ServerWebExchange exchange) {
        return reports.loadReports(authentication, exchange);
    }
}
~~~

This controller is protected by <code>anyExchange().authenticated()</code> from the web configuration. If the application has multiple Authentication types or multiple login providers, the service should verify the principal is appropriate for the <code>company</code> registration before authorizing.

**Never blindly use User A's registration to obtain a token for User B.** An <code>Authentication</code> may belong to a different service/tenant/issuer; verify registration and principal per integration policy.

### 9.4. Do Not block() to Resolve a Mono

Wrong inside a WebFlux handler:

~~~java
OAuth2AuthorizedClient client =
    manager.authorize(request).block();
~~~

Blocking can tie up event-loop threads, causing latency, thread exhaustion, or runtime errors. Use <code>flatMap</code>, <code>map</code>, <code>switchIfEmpty</code>, and <code>onErrorResume</code> when recovery is genuinely needed.

Do not call <code>subscribe()</code> manually in a controller and return a response before the token request/API call completes; doing so loses error propagation, cancellation, and reactive context.

## 10. Using the WebClient OAuth2 Filter Instead of Setting Bearer Manually

Spring Security provides:

**<code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code>**.

This filter integrates OAuth2 authorized clients with <code>WebClient</code> and can use <code>ReactiveOAuth2AuthorizedClientManager</code> to authorize/refresh.

### 10.1. Configuring the Filter with an Existing Manager

~~~java
package example.reports;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OAuth2ReportsWebClientConfig {

    @Bean("oauth2ReportsWebClient")
    WebClient oauth2ReportsWebClient(
        @Qualifier("webAuthorizedClientManager")
        ReactiveOAuth2AuthorizedClientManager manager) {

        var oauth2Filter =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://api.example.org")
            .filter(oauth2Filter)
            .build();
    }
}
~~~

This is an **alternative** to the manual token-attaching <code>reportsWebClient</code> in section 9. You should not both manually set the Bearer header and have the OAuth2 filter overwrite it.

### 10.2. Selecting the Registration per Request

Example inside a reactive web handler that has authentication/exchange context:

~~~java
return oauth2ReportsWebClient.get()
    .uri("/v1/reports")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
~~~

During a web exchange handled by Spring Security, the filter can resolve the appropriate principal and exchange to invoke the manager. When using WebClient **outside** a request context, do not assume those details are automatically available.

For scenarios requiring explicit context passing, the filter's API lets you provide <code>Authentication</code>, <code>ServerWebExchange</code>, or an authorized client via request attributes depending on your Spring Security version. Check the exact API of your deployed version when choosing helpers.

### 10.3. Attaching an Explicit Authorized Client

When an <code>OAuth2AuthorizedClient</code> has already been resolved:

~~~java
return oauth2ReportsWebClient.get()
    .uri("/v1/reports")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class);
~~~

In this example, <code>authorizedClient</code> is a resolved variable, not a user-constructed object from browser input.

Advantage: the code clearly shows which registration/principal owns the token. Drawback: the caller must ensure the authorized client is fetched/refreshed in time; never reuse an expired instance cached in a singleton.

### 10.4. Be Careful with Default OAuth2 Authorized Client Mode

The filter can support a mode that picks a default authorized client. If enabled indiscriminately and the same WebClient calls multiple hosts, there is a risk of accidentally sending the Bearer token to an untrusted URL.

Safer practices:

- Use a dedicated WebClient per trusted downstream API.
- Explicitly select the Registration ID via configuration/backend policy.
- Never pass arbitrary request URLs from the browser to a WebClient that auto-attaches tokens.
- Avoid using a token from UserInfo/API A for API B if audience/scope do not match.
- Configure timeouts, redirect restrictions, and proper HTTP failure handling.

## 11. ServerOAuth2AuthorizedClientRepository: Where Is State Stored?

In a reactive HTTP exchange, the authorized-client repository may use WebSession or delegate to a reactive service.

Key classes to know:

- <code>WebSessionServerOAuth2AuthorizedClientRepository</code>.
- <code>AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository</code>.
- <code>ReactiveOAuth2AuthorizedClientService</code> and an implementation such as <code>InMemoryReactiveOAuth2AuthorizedClientService</code>.

### 11.1. WebSessionServerOAuth2AuthorizedClientRepository

This repository stores authorized clients in WebSession, suitable when tokens should stay scoped to the web session context.

~~~text
Browser → Session Cookie
             └── WebSession
                   └── authorized client state
~~~

If the browser loses its session or the callback lands on another node that cannot find the session, the authorized-client lookup may fail to return the saved token.

### 11.2. AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository

Another common repository switches based on authentication state:

~~~text
Authenticated principal
    → load/save via ReactiveOAuth2AuthorizedClientService

When not yet authenticated
    → fallback repository backed by WebSession per configuration
~~~

Exact behavior depends on the implementation and configuration. The key takeaway is that **a web repository can be backed by a service**, so not every authorized client necessarily resides inside the same WebSession.

### 11.3. ReactiveOAuth2AuthorizedClientService

The interface has methods such as:

~~~java
Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
    String clientRegistrationId,
    String principalName);

Mono<Void> saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal);

Mono<Void> removeAuthorizedClient(
    String clientRegistrationId,
    String principalName);
~~~

This is a **reactive contract**, unlike the synchronous <code>OAuth2AuthorizedClientService</code> interface. Implementing the API with blocking operations directly on the event loop can undermine the benefits of WebFlux.

### 11.4. Session Repository vs Authorization Request Repository

Do not confuse them:

| Repository | Data | Lifecycle |
|---|---|---|
| <code>WebSessionOAuth2ServerAuthorizationRequestRepository</code> | Authorization request holding state/PKCE before callback | From redirect to callback |
| <code>ServerOAuth2AuthorizedClientRepository</code> | Issued access/refresh tokens in web context | After authorize/token exchange |
| <code>ServerSecurityContextRepository</code> | User's Authentication/SecurityContext | Requests belonging to the login session |

In Spring WebFlux, these three state stores serve distinct purposes; never use the authorization request repository to hold long-lived refresh tokens.

## 12. ReactiveOAuth2AuthorizedClientProvider: Configuring the Right Grants

The manager coordinates providers, while the providers actually execute grants when eligible:

~~~java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
~~~

This is an example of composing providers, **not a recommendation to enable every grant for every application**.

| Provider | When to use | Limitations to remember |
|---|---|---|
| <code>authorizationCode()</code> | OAuth2/OIDC browser authorization initiated via a valid flow | Does not render OP login from a job |
| <code>refreshToken()</code> | Authorized client exists with a usable refresh token | Does not elevate scopes on its own |
| <code>clientCredentials()</code> | Service-to-service using Client Credentials | Does not create an End-User Authentication |

### 12.1. Authorization Code and Login

WebFlux's <code>oauth2Login()</code> handles authorization initiation/callback. <code>DefaultReactiveOAuth2AuthorizedClientManager</code> supports the authorized client lifecycle but does not replace WebFilters, state/correlation, OIDC nonce, PKCE, or ID Token validation.

### 12.2. Refresh Token

<code>refreshToken()</code> typically refreshes the access token when the old one is expired/about to expire and a refresh token is present.

If refresh fails with <code>invalid_grant</code>, the refresh token may have expired, been revoked, or another node may have already used it when the provider enforces rotation. Do not assume every error simply means the user logged out.

### 12.3. Client Credentials

If a user web request needs to call an **independent service API** using backend authority, a separate client credentials registration can be configured apart from OIDC login. Keep them distinct:

~~~text
company-login   → user token / authorization_code
reports-service → service token / client_credentials
~~~

Never use a service token to impersonate a user, nor use an OIDC access token meant for UserInfo to call an arbitrary service API.

In background jobs without an exchange, pick the service reactive manager to handle client credentials.

## 13. When to Use AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager?

Both managers have similar names but serve different contexts:

| Criterion | DefaultReactiveOAuth2AuthorizedClientManager | AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager |
|---|---|---|
| Primary context | WebFlux HTTP request | Service/background |
| Requires ServerWebExchange | Usually yes in web flows | No |
| Storage | ServerOAuth2AuthorizedClientRepository | ReactiveOAuth2AuthorizedClientService |
| Example | WebFlux controller calling Reports API on behalf of user | Scheduled job using client credentials |
| Supports custom providers | Yes | Yes |

### 13.1. Example Manager for a Job

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class BackgroundOAuth2ManagerConfig {

    @Bean("jobAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager jobAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService service) {

        var provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

The job invokes:

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-service")
        .principal("reports-worker-runtime")
        .build();

Mono<OAuth2AuthorizedClient> client =
    jobAuthorizedClientManager.authorize(request);
~~~

In this case no <code>ServerWebExchange</code> is passed. <code>reports-worker-runtime</code> is a **synthetic principal** used to partition storage in the service manager; it does not turn the access token into an End-User token.

Corresponding registration example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: service-auth
            client-id: reports-worker
            client-secret: ${REPORTS_WORKER_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [reports.read]
        provider:
          service-auth:
            token-uri: https://auth.example.org/oauth2/token
~~~

If a project has both a web manager and a job manager, use consistent bean names and <code>@Qualifier</code>; never inject a manager arbitrarily just because both share the same interface.

### 13.2. Schedulers and Blocking

A Spring <code>@Scheduled</code> method usually has a different lifecycle than an HTTP request. You can orchestrate reactive pipelines from a job runner suited to your framework/version; never call <code>subscribe()</code> carelessly and mark a job successful before the pipeline finishes.

If a scheduling framework requires a synchronous method, design explicit thread boundaries and completion/error handling rather than calling <code>block()</code> on a Netty event loop. Lacking a WebFlux exchange in a scheduler remains the primary reason to choose the service manager.

## 14. Authorization Success/Failure Handlers

<code>DefaultReactiveOAuth2AuthorizedClientManager</code> has hooks to handle success/failure when a provider executes authorization.

Conceptually:

~~~text
manager.authorize(request)
    ├── load authorized client from repository
    ├── provider issues/refreshes token
    ├── success handler: save authorized client
    └── failure handler: handle token/authorization failure per policy
~~~

### 14.1. Default Persistence of Results

The manager is designed to save the authorized client after a successful token issuance or refresh using the repository-appropriate mechanism. If an application replaces the success handler merely to log:

~~~text
authorize → new token A1
custom success handler → log only
next request → repository still contains A0
~~~

then the new token will not be saved. If customizing the success handler, preserve proper context persistence.

### 14.2. Failure Handler and invalid_grant

If the OP returns <code>invalid_grant</code> during a refresh flow, the refresh token may no longer be valid. Some handlers may remove the authorized client from storage to avoid repeatedly retrying an old token.

However, **not every error means the token must be deleted**:

- Timeout/HTTP 503 may be a transient outage, not confirmation that the token was revoked.
- HTTP 401 from a downstream API could be due to wrong audience, Resource Server config, or an expired token.
- HTTP 403 may just be missing scope/role; refreshing will not elevate permissions.
- Storage may have just been updated by another instance; unconditional deletion can wipe out a fresh token.

Failure policies should classify errors by **Token Endpoint vs Resource Server**, OAuth2 error codes, and concurrency context.

### 14.3. WebClient Filter Does Not Automatically Handle Every API Failure

If you attach the Bearer header manually in <code>WebClient</code> as in section 9, the manager **does not automatically observe** downstream 401/403 responses. When using <code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code>, an appropriate failure handler can be configured; default behavior depends on the constructor and Spring Security version.

Do not assume calling <code>manager.authorize()</code> again will always produce a different token. The manager may return a token that is still valid per its metadata, even if a Resource Server just rejected it due to wrong audience or out-of-band revocation.

## 15. Handling HTTP 401/403 Errors from the Resource Server

| Response | Common meaning | Client handling |
|---|---|---|
| <code>401</code> + Bearer <code>invalid_token</code> | Token rejected (expiry/revoked/issuer/audience...) | Identify cause, refresh/reauthorize when appropriate |
| <code>401</code> without Bearer error | Possibly missing credentials or a different auth mechanism | Check Authorization header and gateway |
| <code>403</code> + Bearer <code>insufficient_scope</code> | Token lacks required scope | Check grant/scopes/consent; do not refresh blindly |
| <code>403</code> other | Role, tenant, ownership, WAF, gateway | Investigate policy and response origin |
| <code>429</code> | Rate limit | Bounded backoff/retry |
| <code>5xx</code> | Downstream error | Safe retry according to policy |

**Distinguish the ID Token from the access token.** A successful OIDC Login proves the user's identity to the Client, but does not automatically grant permission to call any API. The Resource Server still validates the access token.

Example WebClient error classification:

~~~java
return webClient.get()
    .uri("/v1/reports")
    .retrieve()
    .onStatus(
        status -> status.value() == 403,
        response -> Mono.error(
            new IllegalStateException("Reports permission denied")))
    .onStatus(
        status -> status.value() == 401,
        response -> Mono.error(
            new IllegalStateException("Reports token rejected")))
    .bodyToMono(String.class);
~~~

In production, use domain-specific exceptions/DTOs and never forward raw upstream error descriptions to the browser. Inspect <code>WWW-Authenticate</code> alongside the API contract when distinguishing <code>invalid_token</code> from <code>insufficient_scope</code>.

Never automatically retry POST/PUT requests with side effects without an idempotency/recovery policy.

## 16. Multi-Instance: WebSession and Authorized-Client Storage

When running two WebFlux instances:

~~~text
Browser → Load Balancer
            ├── Instance A
            └── Instance B
~~~

A user initiates OAuth2 Login on A, but the callback is routed to B. If WebSession is stored locally only on A without session affinity, B may fail to find the authorization request/state.

After login, the authorized client may reside in <code>WebSession</code> or a dedicated reactive service, depending on the repository. If storage is not shared, requests reaching B might fail to find the token even if the session is restored.

### 16.1. Do Not Confuse the Three State Stores

~~~text
Authorization request repository:
    state, nonce/PKCE data before callback

SecurityContext repository:
    Authenticated user's Authentication

ServerOAuth2AuthorizedClientRepository:
    Issued access token and refresh token
~~~

All three can interact with WebSession yet serve different purposes. Moving sessions to Redis does not automatically turn an independent authorized-client service into distributed storage.

### 16.2. Refresh Token Rotation and Races

Suppose A and B both fetch refresh token R0:

~~~text
A: POST /token with R0 → receives access A1, refresh R1
B: POST /token with R0 → invalid_grant or token reuse detection
~~~

If the OP enforces strict refresh token rotation, B can trigger compromise of the token family. Shared storage **does not automatically lock** the entire refresh operation.

Strategy:

1. Use a coordinator/lock keyed by the authorized client key.
2. After acquiring the lock, re-read the latest authorized client.
3. If the token was already updated by A and is usable, B skips refreshing.
4. Atomically save both access and refresh tokens when the OP issues new tokens.
5. Protect against stale updates/deletes using version/CAS/fencing if required.
6. Never unconditionally delete a new authorized client just because an older request reported <code>invalid_grant</code>.

These mechanisms must be designed at the application/token-store level; <code>DefaultReactiveOAuth2AuthorizedClientManager</code> does not provide distributed single-flight refresh out of the box.

### 16.3. WebSession, Cookies, and State

Session cookies can be lost due to wrong domain, path, Secure/SameSite flags, reverse proxy configuration, or browser policies. The <code>/login/oauth2/code/company</code> callback will fail if the authorization request/state cannot be found.

Never work around this by disabling state validation. Check trusted proxies, HTTPS, session store, and cookies first.

## 17. Reactive Context Propagation and Event-Loop Limits

In WebFlux, the security context is attached to the reactive pipeline:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> currentUser =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
~~~

Do not rely on a static ThreadLocal to determine the user inside every <code>flatMap</code>. A request can execute across multiple threads, and Reactor Context is not the same as a Servlet request thread.

### 17.1. Do Not Use a Blocking Token Store on the Event Loop

A <code>ReactiveOAuth2AuthorizedClientService</code> must not perform synchronous JDBC directly on a Netty event-loop thread, even if its signature returns <code>Mono</code>.

If a blocking library must be used, isolate it on an appropriate scheduler, for example:

~~~java
return Mono.fromCallable(() ->
        blockingTokenRepository.load(registrationId, principalName))
    .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic());
~~~

This is a bridge when no reactive alternative exists; it does not make the I/O non-blocking. Bound thread/connection pools and monitor latency. For truly reactive systems, consider appropriate non-blocking data access.

### 17.2. Avoid Manual subscribe()

Wrong:

~~~java
manager.authorize(request)
    .subscribe(client -> doSomething(client));

return Mono.just("done");
~~~

The request response can be sent before authorization and the API call finish; errors are detached from the response, losing cancellation and context propagation.

Better:

~~~java
return manager.authorize(request)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("Client not authorized")))
    .flatMap(client -> callApi(client));
~~~

Let Spring WebFlux subscribe to the handler's publisher according to the request lifecycle.

## 18. Multiple SecurityWebFilterChains and ServerWebExchange

An application may simultaneously:

- Use OIDC browser login for <code>/app/**</code>.
- Use JWT Resource Server authentication for <code>/api/**</code>.

In that case, ensure:

1. Browser authorization initiation and callbacks belong to the web chain with <code>oauth2Login()</code>.
2. Web requests carry the proper Authentication and WebSession type.
3. The API chain does not accidentally match the callback path before the web chain.
4. Stateless API routes do not trigger unwanted web login redirects.
5. WebClient calls APIs with the right token and audience.

Example with two chains:

~~~java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class SplitReactiveChains {

    @Bean
    @Order(1)
    SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain webChain(ServerHttpSecurity http) {
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

This is an **alternative** to the single chain in section 6.3; do not paste all example configurations into one project and create unintended chains.

An API chain with a JWT Resource Server requires the appropriate dependencies and issuer/audience validation. Only disable CSRF on stateless bearer APIs when the security model allows it; never disable CSRF on the cookie/session-based web chain.

### 18.1. Matchers and Access Rules Serve Different Purposes

<code>securityMatcher(...)</code> selects the chain.

<code>authorizeExchange(...).pathMatchers(...)</code> sets authorization rules inside the selected chain.

A <code>permitAll()</code> rule in the second chain will not help the callback if the first chain already matched that path.

## 19. Testing: Verifying the Reactive Manager in Web Requests

With <code>WebTestClient</code> and Spring Security Test, you can simulate an OAuth2/OIDC principal to test authorized client handling without needing a real OP for every unit test.

### 19.1. Test Dependencies

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
~~~

### 19.2. Testing Route Security with Mock OIDC Login

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;

@SpringBootTest
@AutoConfigureWebTestClient
class ReportsSecurityTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void authenticatedUserCanEnterProtectedRoute() {
        webTestClient
            .mutateWith(mockOidcLogin())
            .get()
            .uri("/reports")
            .exchange()
            .expectStatus().is2xxSuccessful();
    }
}
~~~

This is a **route security test skeleton**; you need to mock/stub <code>ReactiveReportsService</code> and external dependencies so the 2xx assertion reflects authorization policy rather than failing against a real Reports API. If you only want to test security rules, use an internal endpoint with no downstream calls or mock the corresponding service.

<code>mockOidcLogin()</code> creates a test authentication in WebFlux and **does not actually verify** the token endpoint, ID Token signature, issuer, state/nonce/PKCE, or UserInfo. Keep separate integration tests for those protocol aspects when required by the project.

### 19.3. Unit Testing the Manager/Coordinator with StepVerifier

A service using the reactive manager can be tested with a stub manager:

~~~java
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ManagerCallerTest {

    @Test
    void propagatesAuthorizationFailure() {
        var manager =
            Mockito.mock(ReactiveOAuth2AuthorizedClientManager.class);

        when(manager.authorize(any())).thenReturn(Mono.empty());

        // Illustrative publisher for handling Mono.empty():
        Mono<OAuth2AuthorizedClient> pipeline =
            manager.authorize(
                org.springframework.security.oauth2.client.OAuth2AuthorizeRequest
                    .withClientRegistrationId("company")
                    .principal("test-principal")
                    .build())
                .switchIfEmpty(Mono.error(
                    new IllegalStateException("Not authorized")));

        StepVerifier.create(pipeline)
            .expectError(IllegalStateException.class)
            .verify();
    }
}
~~~

To use <code>StepVerifier</code>, add the <code>reactor-test</code> test dependency if current dependency management does not already include it:

~~~groovy
testImplementation 'io.projectreactor:reactor-test'
~~~

This is an example of **reactive result handling**, not an integration test of the real manager with ServerWebExchange. To test exchange behavior, use <code>MockServerWebExchange</code> with a mock repository and verify the manager receives the expected registration/principal/exchange context.

### 19.4. Cases to Verify

| Scenario | What to verify |
|---|---|
| User completed OIDC Login and has authorized client | API is called with token for the right registration/principal |
| Manager cannot find registration | Error/empty is handled; never falls back to another user's token |
| Manager lacks required exchange | Does not fall back to an untrusted fake context |
| Access token still valid | Reuses authorized client when eligible |
| Access token near expiry, refresh token present | Refresh flow executes per provider |
| Token endpoint returns <code>invalid_grant</code> | Failure handling does not loop infinitely |
| API returns 403 insufficient scope | Does not auto-refresh/reauthorize indiscriminately |
| Two users share the same registration | User A's token never appears in User B's request |
| Multi-instance refresh rotation | Coordination/conditional update per policy |
| Reactive controller | Does not call <code>block()</code> on request event loop |

## 20. Troubleshooting: Common Issues

| Symptom | Possible cause | Remediation |
|---|---|---|
| Missing <code>ReactiveClientRegistrationRepository</code> bean | Missing starter, properties, or app runs MVC/Servlet | Check dependencies, application type, registration |
| Cannot create manager bean | Missing <code>ServerOAuth2AuthorizedClientRepository</code> | Check WebFlux Security auto-configuration or beans |
| <code>manager.authorize(...)</code> emits no client | Wrong registration, mismatched grant/provider, or not yet authorized | Inspect <code>OAuth2AuthorizeRequest</code> and storage |
| Manager reports missing exchange | ServerWebExchange context not passed | Pass exchange to web manager or use service manager outside requests |
| User A uses User B's token | Principal taken from query param or static cache | Read from trusted Authentication, partition storage properly |
| Login succeeds but service cannot find token | Different storage/repository or principal name mismatch | Check wiring and principal key |
| <code>block()</code> throws error on event loop | Treating reactive publisher synchronously | Compose with <code>flatMap</code>, avoid blocking |
| WebClient does not send Authorization | Token not set or filter/attributes misconfigured | Check WebClient filter and authorized client selection |
| Downstream API returns 401 | Token expired, wrong issuer/audience, revoked | Inspect Token Endpoint and Resource Server |
| Downstream API returns 403 | Missing scope/role/tenant/ownership | Investigate authorization; do not blindly retry refresh |
| Does not refresh despite expired access token | Missing refresh token/provider or wrong manager called | Check grant, refresh setup, and repository |
| Refreshing on every request | Clock skew too large, short token lifetime, or result not persisted | Check success handler and storage |
| Callback state mismatch | WebSession cookie/session store/chain misconfigured | Check authorization request repo and proxy |
| Only node A has the token | In-memory authorized client service or local WebSession | Design shared storage/affinity as needed |
| Multiple nodes refresh R0 simultaneously | No distributed single-flight | Lock by key, re-read, CAS/conditional delete |
| Scheduler fails to authorize | Using web manager without ServerWebExchange | Use AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager |
| Bean ambiguity | Multiple ReactiveOAuth2AuthorizedClientManager beans | Use @Qualifier or explicit bean wiring |
| Callback intercepted by API chain | Wrong SecurityWebFilterChain order/matcher | Narrow API matcher and route callback to web chain |

### 20.1. Diagnostic Sequence

~~~text
Is the app running reactive WebFlux?
   |
   v
Does ReactiveClientRegistration "company" exist?
   |
   v
Has the request completed OIDC Login / Authentication?
   |
   v
Are ServerWebExchange and principal accurate?
   |
   v
Is the right DefaultReactiveOAuth2AuthorizedClientManager bean used?
   |
   v
Is ServerOAuth2AuthorizedClientRepository using the right storage?
   |
   v
Does a grant provider support the registration/context?
   |
   v
Is the access token valid or in need of refresh?
   |
   v
Is the authorized client saved and emitted in Mono?
   |
   v
Does WebClient attach the right Bearer access token?
   |
   v
Does the Resource Server accept the audience/scope/policy?
~~~

Never log raw access tokens, refresh tokens, ID Tokens, authorization codes, PKCE verifiers, session cookies, or client secrets for diagnostics. Only log the registration ID, HTTP status, sanitized error codes, route template, correlation ID, and permitted token metadata.

## 21. Practice Scenarios and Exercises

### Exercise 1 — Choosing the Right Manager

A WebFlux controller needs to obtain the access token of a user logged in via OIDC and uses <code>ServerWebExchange</code>.

**Question:** Which manager should you choose?

**Answer:** <code>DefaultReactiveOAuth2AuthorizedClientManager</code> with <code>ReactiveClientRegistrationRepository</code>, <code>ServerOAuth2AuthorizedClientRepository</code>, and the appropriate providers.

### Exercise 2 — Background Job Without an Exchange

A periodic job needs a client credentials access token but has no HTTP request.

**Question:** Should you construct a <code>MockServerWebExchange</code> in production?

**Answer:** No. Use <code>AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager</code> with <code>ReactiveOAuth2AuthorizedClientService</code> and <code>clientCredentials()</code>.

### Exercise 3 — OAuth2AuthorizeRequest

Code snippet:

~~~java
OAuth2AuthorizeRequest.withClientRegistrationId("company")
    .principal(authentication)
    .attribute(ServerWebExchange.class.getName(), exchange)
    .build();
~~~

**Question:** What do the three parts tell the manager?

**Answer:** Registration ID selects the ClientRegistration; Authentication identifies the principal; exchange provides the HTTP context for the web repository.

### Exercise 4 — Principal from the Browser

A developer writes:

~~~java
.principal(exchange.getRequest().getQueryParams().getFirst("user"))
~~~

**Question:** What is the risk?

**Answer:** The browser can pick another user's principalName, leading to unauthorized lookups/token leakage. Obtain the principal from the verified Authentication.

### Exercise 5 — Mono.empty()

A manager cannot authorize and returns <code>Mono.empty()</code>.

**Question:** Can you cast the result of <code>authorize(...)</code> to <code>OAuth2AuthorizedClient</code>?

**Answer:** No. You must compose the reactive pipeline and handle empty/error with <code>switchIfEmpty</code>, never falling back to another user's token.

### Exercise 6 — Missing Refresh Token

The user has a valid OIDC login, but the authorized client has <code>refreshToken=null</code> and the access token expired.

**Question:** Can the manager refresh the token with <code>refreshToken()</code>?

**Answer:** Not without a valid refresh token. Depending on grant/provider, a new authorization code flow or another appropriate token-issuing mechanism may be needed.

### Exercise 7 — Browser Login Does Not Automatically Grant Reports API Access

The ID Token is valid, but the access token was only issued for the UserInfo Endpoint. WebClient sends that token to the Reports API.

**Question:** Does the manager guarantee the API accepts the token?

**Answer:** No. The manager manages tokens; the Resource Server still enforces its own audience/scope and policy checks.

### Exercise 8 — Logout and Storage

The user logs out of the WebFlux session. The authorized client is stored in a persistent reactive service.

**Question:** Can you assume the access/refresh tokens were revoked at the OP?

**Answer:** No. Session logout, local authorized client removal, and token revocation are separate operations; design cleanup/revocation when required.

### Exercise 9 — Multiple Instances and Refresh Race

Instances A and B both hold refresh token R0. A refreshes successfully, while B receives <code>invalid_grant</code>.

**Question:** Does a shared database solve the race on its own?

**Answer:** No. You need coordination before refreshing, re-reading the authorized client under a lock, and conditional save/remove protection.

### Exercise 10 — Blocking Controller

~~~java
return Mono.just(manager.authorize(request).block());
~~~

**Question:** Why should you avoid this?

**Answer:** It blocks the event loop and breaks reactive flow. Return the Mono directly or compose with <code>flatMap</code>.

### Exercise 11 — Project Configuration Practice

1. Create a Spring Boot WebFlux app with the OAuth2 Client starter.
2. Configure OIDC registration <code>company</code> using a test OP's issuer.
3. Create a <code>SecurityWebFilterChain</code> with <code>oauth2Login()</code>/<code>oauth2Client()</code>.
4. Create a <code>DefaultReactiveOAuth2AuthorizedClientManager</code> with Authorization Code and Refresh Token providers.
5. Build an <code>OAuth2AuthorizeRequest</code> from the registration ID, Authentication, and ServerWebExchange.
6. Call <code>manager.authorize()</code> and handle the Mono reactively without <code>block()</code>.
7. Wire the authorized client into WebClient to call a test API **with the right audience/scope**.
8. Test missing registration, missing authorized client, token expiry, HTTP 401, and 403.
9. Try deploying two instances, evaluating WebSession and authorized client storage.
10. Verify the access token never appears in browser responses or application logs.

## 22. Key Takeaways

- **<code>DefaultReactiveOAuth2AuthorizedClientManager</code>** is the <code>ReactiveOAuth2AuthorizedClientManager</code> implementation designed for **WebFlux HTTP requests with <code>ServerWebExchange</code>**.
- The manager combines <code>ReactiveClientRegistrationRepository</code>, <code>ServerOAuth2AuthorizedClientRepository</code>, and <code>ReactiveOAuth2AuthorizedClientProvider</code> to manage authorized clients.
- <code>OAuth2AuthorizeRequest</code> requires a registration ID, a **trusted principal**, and the proper exchange context. Never read an arbitrary principalName from the browser.
- <code>authorize(...)</code> returns <code>Mono&lt;OAuth2AuthorizedClient&gt;</code>; use <code>flatMap</code>/<code>switchIfEmpty</code>, never <code>block()</code> or arbitrary <code>subscribe()</code> inside request handlers.
- <code>OAuth2AuthorizedClient</code> holds issued access/refresh tokens; it is distinct from <code>ClientRegistration</code> and <code>OidcUser</code>.
- <code>ServerOAuth2AuthorizedClientRepository</code> stores tokens in the web context; <code>ReactiveOAuth2AuthorizedClientService</code> can serve as the storage backend depending on configuration.
- For **background jobs without an exchange**, typically choose **<code>AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager</code>**.
- <code>ServerOAuth2AuthorizedClientExchangeFilterFunction</code> can integrate the manager with WebClient, but you must specify the right registration/principal and avoid sending Bearer tokens to untrusted hosts.
- A valid access token does not inherently grant access to every Resource Server. Proper audience, scope, role/tenant/ownership, and authorization checks are still required.
- When running multiple instances, account for WebSession sharing, token persistence, refresh token rotation, and race conditions; the default manager does not provide distributed locking.
- Protect client secrets, access/refresh tokens, and session cookies; maintain HTTPS, protocol CSRF/state/nonce/PKCE, and never log credentials.

### References

- **Spring Security Reference — Reactive OAuth2 Client:** <code>ReactiveOAuth2AuthorizedClientManager</code>, providers, and authorized client repositories.
- **Spring Security Java API — DefaultReactiveOAuth2AuthorizedClientManager:** constructor, <code>authorize</code>, providers, context attributes, and success/failure handlers.
- **Spring Security Java API — AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager:** managing authorized clients outside ServerWebExchange.
- **Spring Security Java API — ServerOAuth2AuthorizedClientRepository:** load/save/remove authorized clients within an HTTP exchange.
- **Spring Security Java API — ServerOAuth2AuthorizedClientExchangeFilterFunction:** WebClient integration, request attributes, and failure handling.
- **Spring Security Reference — Reactive OAuth2 Login:** SecurityWebFilterChain, Authorization Code callback, OIDC authentication.
- **Spring Framework Reference — WebFlux/WebClient:** ServerWebExchange, Reactor Context, non-blocking HTTP.
- **Spring Security Test — WebTestClient:** mock OIDC authentication and reactive security tests.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** Authorization Code, Client Credentials, and Refresh Token grants.
- **RFC 7636 — Proof Key for Code Exchange:** PKCE for Authorization Code Flow.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** refresh token protection/rotation.
- **OpenID Connect Core 1.0:** ID Token, subject/issuer, authentication flow, and UserInfo.
