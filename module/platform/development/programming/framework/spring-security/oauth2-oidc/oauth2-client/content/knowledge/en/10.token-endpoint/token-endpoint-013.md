# 10.13. Distinguishing Token Client Configuration in Servlet and Reactive

## 1. Problem: Same Token Endpoint, Two Integration Models in Spring Security

A **Spring Security OAuth 2.0/OIDC Client** application frequently needs to contact the Authorization Server's **token endpoint** to:

1. Exchange an **authorization code** for tokens after the browser redirects back to the callback.
2. Use a **refresh token** to obtain a new access token when authorized and permitted.
3. Use the **`client_credentials`** grant to obtain an access token for a service calling APIs under the client's own identity.

Across **Spring MVC/Servlet** and **Spring WebFlux/Reactive**, the protocol request sent to the Authorization Server is fundamentally identical: HTTP POST over TLS, grant type, client credentials, and corresponding parameters. However, the **HTTP client type**, **token-response client interface**, **asynchronous execution model**, and **wiring point in the security chain** all differ.

Key takeaway:

- **Servlet** typically uses `OAuth2AccessTokenResponseClient<T>` to receive an `OAuth2AccessTokenResponse` synchronously. Modern HTTP clients can be built on Spring's `RestClient`.
- **Reactive** uses `ReactiveOAuth2AccessTokenResponseClient<T>`, returning `Mono<OAuth2AccessTokenResponse>`; common implementations use `WebClient`.

You cannot drop a Servlet token client where a Reactive token client is expected just because both are called "OAuth2 Client." This lesson explains the mechanics, APIs, configuration examples, and operational differences.

> Example scope: Java 17+, **Spring Security 6**, Spring Boot 3. Several `RestClient`-based classes appeared in **Spring Security 6.4+**; older versions use `Default*TokenResponseClient` classes based on `RestOperations`. Use APIs matching the Spring Security version your project actually manages; never mix packages or methods from both generations in the same example.

## 2. Where Does the Token Endpoint Sit in the Authorization Code Flow?

Suppose **Employee Portal** signs users in via **Company IdP** and then calls **Orders API** on the user's behalf.

~~~mermaid
sequenceDiagram
    actor U as User
    participant B as Browser
    participant P as Employee Portal (OAuth2 Client)
    participant AS as Authorization Server / OIDC Provider
    participant API as Orders API (Resource Server)

    U->>B: Click Company Sign In
    B->>P: GET /oauth2/authorization/company
    P-->>B: Redirect to authorization endpoint
    B->>AS: Authorization request with state, redirect_uri, ...
    AS->>U: Authenticate and consent when needed
    AS-->>B: Redirect callback with code and state
    B->>P: GET /login/oauth2/code/company?code=...&state=...
    P->>P: Verify callback and matching request
    P->>AS: POST token endpoint, grant_type=authorization_code
    AS-->>P: access_token (+ id_token / refresh_token if issued)
    P->>P: Verify OIDC login, save SecurityContext/authorized client
    B->>P: Request orders page via session
    P->>API: Authorization: Bearer <access_token>
    API-->>P: Authorized data
    P-->>B: Result
~~~

The **token endpoint** and **authorization endpoint** are two separate endpoints:

| Endpoint | Caller | Typical Communication | Responsibility |
|---|---|---|---|
| **Authorization endpoint** | Browser via redirect from Portal | Front-channel GET, user-interactive | Authentication, consent, and issuing authorization code |
| **Token endpoint** | Portal backend | Back-channel HTTPS POST | Exchanging code or another grant for tokens |
| **Orders API** | Portal after obtaining token | HTTP request with Bearer header | Verifying access token and resource permissions |

The **token client** in this lesson is the component executing the **HTTP request to the token endpoint**. It is **not** the OAuth2 Client registration, login form, redirect resolver, or the HTTP client used to call Orders API.

## 3. What Is Shared Between Servlet and Reactive?

Whether using Servlet or Reactive, OAuth 2.0 Client configuration requires similar metadata:

- **client registration ID**: internal name, e.g., `company`.
- **client-id**, **client-secret**, or another client authentication method per IdP registration.
- **authorization-grant-type**: `authorization_code`, `client_credentials`, etc.
- **redirect-uri**: callback registered at the Authorization Server, when the grant requires redirects.
- **provider.issuer-uri** or explicitly configured endpoints when the provider lacks discovery.
- **scope**: permissions requested by the application.

The protocol must still uphold these requirements:

1. Use proper **TLS** when sending credentials, authorization codes, refresh tokens, and receiving tokens.
2. Send **client authentication** accepted by the IdP, such as `client_secret_basic`.
3. When using PKCE, send **`code_verifier`** in the token request matching the earlier code challenge.
4. When the Authorization Server requires **`redirect_uri`** in the token request, keep it consistent with the authorization request.
5. Accept only valid token responses, then safeguard access tokens, refresh tokens, and ID Tokens.

The **difference** lies in how Java components execute those steps.

## 4. Quick Comparison Table

| Criterion | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Security builder | `HttpSecurity` | `ServerHttpSecurity` |
| HTTP request abstraction | `HttpServletRequest` | `ServerWebExchange` |
| Token-response interface | `OAuth2AccessTokenResponseClient<T>` | `ReactiveOAuth2AccessTokenResponseClient<T>` |
| Token client API result | `OAuth2AccessTokenResponse` | `Mono<OAuth2AccessTokenResponse>` |
| Authorization Code implementation | `RestClientAuthorizationCodeTokenResponseClient` (6.4+) or legacy Default class | `WebClientReactiveAuthorizationCodeTokenResponseClient` |
| Client Credentials implementation | `RestClientClientCredentialsTokenResponseClient` (6.4+) or legacy Default | `WebClientReactiveClientCredentialsTokenResponseClient` |
| Refresh Token implementation | `RestClientRefreshTokenTokenResponseClient` (6.4+) or legacy Default | `WebClientReactiveRefreshTokenTokenResponseClient` |
| Common HTTP engine | `RestClient` / `RestOperations` | `WebClient` |
| Authorized-client manager | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| Client registrations | `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| Token/result processing | Synchronous per call | Non-blocking via reactive pipeline |
| OAuth2 Login configuration | `http.oauth2Login(...)` | `http.oauth2Login(...)` on `ServerHttpSecurity` |
| Programming model | Blocking/synchronous on app thread | Returns Publisher; never `block()` on event loop |

**Version note:** the `RestClient*TokenResponseClient` class names in the table apply to modern Spring Security; if a project uses Spring Security 6.2/6.3, use the implementations actually present in that release (typically `DefaultAuthorizationCodeTokenResponseClient` and the `Default*` family). Never hand-roll HTTP token exchange just because an online snippet targets another version.

## 5. The Two Core Token Client Interfaces

### 5.1. Servlet: `OAuth2AccessTokenResponseClient`

Core API:

~~~java
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.core.OAuth2AccessTokenResponse;

public interface OAuth2AccessTokenResponseClient<T> {
    OAuth2AccessTokenResponse getTokenResponse(T authorizationGrantRequest);
}
~~~

In practice, generic `T` is bound to a grant request type, such as:

~~~java
OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
~~~

`getTokenResponse(...)` returns the response directly. The HTTP client may perform synchronous I/O during token exchange, so pay attention to **timeouts**, IdP reachability, and avoiding thread pool exhaustion.

### 5.2. Reactive: `ReactiveOAuth2AccessTokenResponseClient`

Reactive counterpart:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.core.OAuth2AccessTokenResponse;

public interface ReactiveOAuth2AccessTokenResponseClient<T> {
    Mono<OAuth2AccessTokenResponse> getTokenResponse(T authorizationGrantRequest);
}
~~~

`Mono<OAuth2AccessTokenResponse>` is a Publisher representing the token response emitted once I/O and processing finish. With a non-blocking implementation, the pipeline proceeds without holding a thread waiting on the network.

**Never call `.block()` on a reactive request-handling thread** to "turn" the Reactive token client into a synchronous API. Blocking the event loop negates non-blocking benefits, degrades throughput, and triggers Reactor errors where blocking is disallowed.

### 5.3. The Two Interfaces Are Not Interchangeable

Type-incorrect example:

~~~java
// Wrong: a synchronous token client is not a reactive token client.
ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
    tokenClient = new RestClientAuthorizationCodeTokenResponseClient();
~~~

The reverse is also wrong: returning a `Mono` does not satisfy `OAuth2AccessTokenResponseClient`. Converting between them would require an explicit adapter, which is generally **unnecessary and discouraged** when the framework already provides native Servlet and Reactive implementations.

## 6. HTTP Token Exchange Example Executed by Both Stacks

After Portal verifies the callback and holds the authorization code, the token request typically looks like:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <base64-client-credentials>

grant_type=authorization_code&code=<authorization-code>&redirect_uri=https%3A%2F%2Fportal.example.test%2Flogin%2Foauth2%2Fcode%2Fcompany&code_verifier=<pkce-verifier-if-used>
~~~

The `Authorization: Basic` header illustrates confidential client authentication when the registration uses `client_secret_basic`. Providers may use other methods; the exact request must match the IdP configuration.

A successful token response might be:

~~~json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile orders.read",
  "refresh_token": "EXAMPLE_REFRESH_TOKEN",
  "id_token": "EXAMPLE_ID_TOKEN_JWT"
}
~~~

This is **illustrative data** only, not a valid token. In OIDC, the ID Token is dedicated to authenticating the user at the client, while the access token is for the Resource Server. Refresh tokens and ID Tokens depend on grant, scopes, and provider policies.

In Servlet, calling the token-response client returns an `OAuth2AccessTokenResponse`. In Reactive, the token-response client emits the exact same response model via `Mono`. **HTTP wire content does not change just because the application uses WebFlux.**

## 7. Shared Registration Configuration for Servlet and Reactive

Spring Boot uses the same OAuth2 Client properties on both stacks:

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
              - email
              - orders.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

**`company`** is the application's registration ID; `OIDC_CLIENT_ID` is the client ID from the Authorization Server. `OIDC_CLIENT_SECRET` must be supplied from a protected runtime secret source, never committed directly to Git.

Spring Boot can read token endpoint metadata from the issuer via OIDC/OAuth discovery if supported by the provider. The same YAML produces different repository beans depending on application type:

~~~text
Servlet application:
  spring.security.oauth2.client.*
     -> ClientRegistrationRepository
     -> Servlet OAuth2 login / authorized client components

Reactive application:
  spring.security.oauth2.client.*
     -> ReactiveClientRegistrationRepository
     -> WebFlux OAuth2 login / reactive authorized client components
~~~

**The YAML file does not select Servlet vs. Reactive.** Application type depends on the web stack on the classpath and how Spring Boot initializes. If both Spring MVC and WebFlux are on the classpath, Spring Boot normally prefers **Servlet/MVC** unless explicitly configured otherwise. Thus, merely seeing `spring-webflux` or a `WebClient` bean is not enough to conclude the app runs a reactive security chain.

## 8. Servlet: Configuring the Token Client for Authorization Code Flow

### 8.1. Dependencies and `SecurityFilterChain`

A Servlet application uses:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Basic OAuth2/OIDC login:

~~~java
package com.example.portal.servlet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletSecurityConfig {

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

With default settings, Spring Security automatically chooses a version-compatible token response client to exchange codes for tokens. You **do not need custom code** when the IdP follows standards and default HTTP client, timeout, and authentication behavior already fit.

### 8.2. Using `RestClientAuthorizationCodeTokenResponseClient` (Spring Security 6.4+)

When explicit token client configuration is needed in Servlet:

~~~java
package com.example.portal.servlet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.endpoint.RestClientAuthorizationCodeTokenResponseClient;

@Configuration
class ServletTokenClientConfig {

    @Bean
    OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
    authorizationCodeTokenResponseClient() {
        return new RestClientAuthorizationCodeTokenResponseClient();
    }
}
~~~

To wire it into the token exchange step of **OAuth2 Login**:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.endpoint.OAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletLoginTokenConfig {

    @Bean
    SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
            codeTokenClient
    ) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(login -> login
                .tokenEndpoint(token -> token
                    .accessTokenResponseClient(codeTokenClient)))
            .build();
    }
}
~~~

These two snippets are parts of **one configuration option**. In a real project, keep only **one `SecurityFilterChain`** covering the same URL group—do not also keep the chain from section 8.1 with overlapping matchers.

The Servlet hook point is:

~~~java
http.oauth2Login(login -> login
    .tokenEndpoint(token -> token
        .accessTokenResponseClient(codeTokenClient))
);
~~~

**`tokenEndpoint()`** here is the DSL configuring **OAuth2 Login's authorization-code-to-token exchange step**; it does not mean Portal is hosting its own token endpoint or Authorization Server.

### 8.3. Customizing `RestClient` to Control Timeouts

When you need to bound how long the app waits on the IdP, build a `RestClient` with a request factory:

~~~java
import java.time.Duration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.security.oauth2.client.endpoint.RestClientAuthorizationCodeTokenResponseClient;
import org.springframework.web.client.RestClient;

SimpleClientHttpRequestFactory requestFactory =
    new SimpleClientHttpRequestFactory();
requestFactory.setConnectTimeout(Duration.ofSeconds(3));
requestFactory.setReadTimeout(Duration.ofSeconds(5));

RestClient httpClient = RestClient.builder()
    .requestFactory(requestFactory)
    .build();

RestClientAuthorizationCodeTokenResponseClient tokenClient =
    new RestClientAuthorizationCodeTokenResponseClient();
tokenClient.setRestClient(httpClient);
~~~

This illustrates **HTTP transport** configuration, not a full `SecurityFilterChain`. **When replacing the default HTTP client**, if the provider requires specific converters or error handlers, make sure token requests/responses still undergo OAuth2 processing. Never return raw JSON and bypass error checks or token response conversion.

In production systems, you can pick other HTTP transports for connection pooling, TLS trust, mTLS, and proxies. Protect client secrets, authorization codes, and refresh tokens, and never write token endpoint payloads to logs.

### 8.4. When Using an Older Spring Security Version

Some older Spring Security 6.x projects use:

~~~java
import org.springframework.security.oauth2.client.endpoint.DefaultAuthorizationCodeTokenResponseClient;

var tokenClient = new DefaultAuthorizationCodeTokenResponseClient();
~~~

The older class relies on `RestOperations` (typically `RestTemplate`) and exposes `setRestOperations(...)` per that version's API. **Never call `setRestClient(...)` on the `Default` class**, as that is a different HTTP client type. When upgrading, check the migration guide and actual dependencies before changing code.

## 9. Reactive: Using `WebClientReactiveAuthorizationCodeTokenResponseClient`

### 9.1. Dependencies and `SecurityWebFilterChain`

A WebFlux application uses:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

Security chain for a reactive application:

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

In WebFlux, `ServerHttpSecurity` operates with a **WebFilter chain** and reactive types. Do not declare `SecurityFilterChain(HttpSecurity)` to control a WebFlux authorization flow.

### 9.2. Creating a Reactive Token Client for `authorization_code`

Standard implementation:

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.endpoint.OAuth2AuthorizationCodeGrantRequest;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveAuthorizationCodeTokenResponseClient;

@Configuration
class ReactiveTokenClientConfig {

    @Bean
    ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
    reactiveAuthorizationCodeTokenClient() {
        return new WebClientReactiveAuthorizationCodeTokenResponseClient();
    }
}
~~~

`ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>` accepts a grant request and returns `Mono<OAuth2AccessTokenResponse>`. When no HTTP transport customization is needed, Spring Security provides a compatible reactive token client out of the box for OIDC/OAuth2 Login.

**A critical difference from Servlet:** do not copy `http.oauth2Login().tokenEndpoint(...).accessTokenResponseClient(...)` verbatim onto `ServerHttpSecurity`. The WebFlux DSL is not a 1:1 mirror of the Servlet DSL. Wiring a reactive token client into **callback authentication** goes through the corresponding **`ReactiveAuthenticationManager` / OIDC authentication manager** components or hooks documented by your application's Spring Security version.

Simply declaring a `@Bean ReactiveOAuth2AccessTokenResponseClient` as above **does not guarantee** overriding the token client used across the entire OAuth2 Login filter by default. To be certain login's token endpoint client is customized, configure the matching authentication manager or hook and wire it into the WebFlux security chain. Never assume Spring discovers arbitrary beans automatically.

### 9.3. Customizing the `WebClient` Used for the Token Endpoint

Example configuring a Reactor Netty HTTP client with a response timeout:

~~~java
import java.time.Duration;
import reactor.netty.http.client.HttpClient;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveAuthorizationCodeTokenResponseClient;
import org.springframework.web.reactive.function.client.WebClient;

HttpClient nettyClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(5));

WebClient tokenWebClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(nettyClient))
    .build();

WebClientReactiveAuthorizationCodeTokenResponseClient tokenClient =
    new WebClientReactiveAuthorizationCodeTokenResponseClient();
tokenClient.setWebClient(tokenWebClient);
~~~

This illustrates **non-blocking HTTP transport**. When replacing the token response client's default `WebClient`, preserve form parameter handling, content types, and OAuth2 token response decoding; choose an HTTP connector, codecs, and HTTP error handling compatible with your Spring Security version.

Set deliberate timeouts so the app does not hang indefinitely when the IdP is slow, while avoiding blindly retrying requests that exchange a **single-use authorization code**. If a timeout occurs after the IdP has already consumed the code, resending the same code typically returns `invalid_grant`.

### 9.4. Never Block a `Mono` in WebFlux

Pattern to avoid in reactive request handling:

~~~java
// Do not use this in a reactive request thread:
OAuth2AccessTokenResponse response =
    reactiveTokenClient.getTokenResponse(grantRequest).block();
~~~

Instead, let the framework or reactive pipeline **subscribe to and compose the `Mono`**:

~~~java
Mono<OAuth2AccessTokenResponse> responseMono =
    reactiveTokenClient.getTokenResponse(grantRequest)
        .doOnError(error -> {
            // Log safe error category; never log tokens or secrets.
        });
~~~

The snippet above illustrates **the Reactive programming style**; in a normal WebFlux app, Spring Security orchestrates token exchange inside the authentication manager. Do not manually invoke the token client in a callback controller when `oauth2Login()` is already configured.

## 10. Configuring Token Clients per Grant Type

There is no single default "token client" covering all grants. Depending on the grant, Spring Security uses the matching grant request and implementation.

| Grant | Servlet (Spring Security 6.4+) | Reactive | Context |
|---|---|---|---|
| `authorization_code` | `RestClientAuthorizationCodeTokenResponseClient` | `WebClientReactiveAuthorizationCodeTokenResponseClient` | Exchanging code after callback |
| `refresh_token` | `RestClientRefreshTokenTokenResponseClient` | `WebClientReactiveRefreshTokenTokenResponseClient` | Renewing access token when refresh token exists |
| `client_credentials` | `RestClientClientCredentialsTokenResponseClient` | `WebClientReactiveClientCredentialsTokenResponseClient` | Service-to-service, not user login |

Example instantiating all three Servlet token clients:

~~~java
import org.springframework.security.oauth2.client.endpoint.RestClientAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.RestClientRefreshTokenTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.RestClientClientCredentialsTokenResponseClient;

var authorizationCodeClient =
    new RestClientAuthorizationCodeTokenResponseClient();
var refreshTokenClient =
    new RestClientRefreshTokenTokenResponseClient();
var clientCredentialsClient =
    new RestClientClientCredentialsTokenResponseClient();
~~~

In Reactive:

~~~java
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveAuthorizationCodeTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveRefreshTokenTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveClientCredentialsTokenResponseClient;

var reactiveCodeClient =
    new WebClientReactiveAuthorizationCodeTokenResponseClient();
var reactiveRefreshClient =
    new WebClientReactiveRefreshTokenTokenResponseClient();
var reactiveClientCredentialsClient =
    new WebClientReactiveClientCredentialsTokenResponseClient();
~~~

**These three token clients do not replace `ClientRegistration`.** They are HTTP executors for specific grant types. When building an app, typically customize only the grant that genuinely needs custom HTTP handling.

## 11. OAuth2 Login and Authorized Client Manager Are Not the Same Mechanism

In an application, distinguish **the login step** from **acquiring/maintaining access tokens when calling APIs**.

### 11.1. OAuth2 Login

When the browser returns with `code` and `state`, Spring Security needs to:

1. Correlate the callback with the prior authorization request.
2. Exchange the authorization code for tokens at the token endpoint.
3. Validate the ID Token / OIDC User per spec when using OIDC.
4. Create `Authentication` and persist `SecurityContext` and the authorized client.

In Servlet, `oauth2Login().tokenEndpoint().accessTokenResponseClient(...)` is the directly supported hook for the token response step.

In Reactive, OAuth2 Login delegates to a **reactive authentication manager** and underlying reactive token client; customization does not use the same method chain. Separate managers handle OIDC vs. plain OAuth2 login, so you cannot just plug a raw `WebClient` into a login filter and call it done.

### 11.2. Authorized Client Manager

When the app **already holds an authorized client** or needs service-to-service tokens, the authorized client manager selects grants and manages token lifecycles:

- **Servlet**: `OAuth2AuthorizedClientManager` and `OAuth2AuthorizedClientProvider`.
- **Reactive**: `ReactiveOAuth2AuthorizedClientManager` and `ReactiveOAuth2AuthorizedClientProvider`.

An authorized client provider can support `authorization_code`, `refresh_token`, and `client_credentials` depending on configuration. The manager's **refresh token response client** and **client credentials response client** can be customized independently of the login flow's token client.

Customizing the token client for **OAuth2 Login** does not mean subsequent refresh or client credentials flows automatically use that same HTTP client. Identify **the exact hook point for each flow**.

## 12. Servlet Example: Custom Token Client for `client_credentials` in `AuthorizedClientManager`

Suppose Portal calls an internal API under its service identity (not a user token) using the `client_credentials` grant.

Dedicated registration config:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          service-api:
            provider: company
            client-id: ${SERVICE_CLIENT_ID}
            client-secret: ${SERVICE_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - reports.read
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

This is an **illustrative replacement/addition registration**, so do not overwrite an existing `company` provider block in your project. It omits `openid` and redirect URIs because there is no user login.

Servlet **`AuthorizedClientManager` example for tasks not tied to an HTTP request**:

~~~java
package com.example.portal.servlet;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ClientCredentialsOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.endpoint.RestClientClientCredentialsTokenResponseClient;

@Configuration
class ServletMachineTokenConfig {

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService clientService
    ) {
        ClientCredentialsOAuth2AuthorizedClientProvider provider =
            new ClientCredentialsOAuth2AuthorizedClientProvider();

        provider.setAccessTokenResponseClient(
            new RestClientClientCredentialsTokenResponseClient());

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, clientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Meaning:

- `ClientRegistrationRepository` resolves the `service-api` registration.
- `OAuth2AuthorizedClientService` persists the authorized client in an appropriate store.
- `ClientCredentialsOAuth2AuthorizedClientProvider` handles the `client_credentials` grant.
- `RestClientClientCredentialsTokenResponseClient` executes synchronous HTTP token exchange.

Note that `AuthorizedClientServiceOAuth2AuthorizedClientManager` fits **service/background workloads** independent of an active Servlet request/response. Inside user-facing web requests with a principal, `DefaultOAuth2AuthorizedClientManager` paired with an authorized-client repository typically manages request/user-scoped authorized clients.

## 13. Reactive Example: Custom Token Client for `client_credentials`

In WebFlux, the counterparts are the **reactive client credentials provider** and reactive manager:

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ClientCredentialsReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveClientCredentialsTokenResponseClient;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
class ReactiveMachineTokenConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository authorizedClients
    ) {
        ClientCredentialsReactiveOAuth2AuthorizedClientProvider provider =
            new ClientCredentialsReactiveOAuth2AuthorizedClientProvider();

        provider.setAccessTokenResponseClient(
            new WebClientReactiveClientCredentialsTokenResponseClient());

        DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

This illustrates **`ReactiveOAuth2AuthorizedClientManager`** used when a `ServerWebExchange` or server request context exists. For **scheduled jobs/background tasks without a `ServerWebExchange`**, use an appropriate manager such as `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` paired with `ReactiveOAuth2AuthorizedClientService`. Never blindly reuse a web-exchange-bound manager for background tasks.

Differences from Servlet:

| Servlet | Reactive |
|---|---|
| `ClientCredentialsOAuth2AuthorizedClientProvider` | `ClientCredentialsReactiveOAuth2AuthorizedClientProvider` |
| `RestClientClientCredentialsTokenResponseClient` | `WebClientReactiveClientCredentialsTokenResponseClient` |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| Synchronous | Returns Publisher; never blocks reactive pipeline |

To support multiple grants, use the appropriate Servlet/Reactive **authorized client provider builders** to combine client credentials, refresh token, and other grants instead of a single provider as shown in the two examples above. When combining them, verify each provider's token client independently.

## 14. `WebClient` for Calling APIs Differs from `WebClient` for Token Exchange

In a Reactive app, the name **`WebClient`** typically appears in two places:

1. **Token `WebClient`**: used inside `WebClientReactive*TokenResponseClient` to call the Authorization Server's token endpoint.
2. **Resource `WebClient`**: used after obtaining an access token to call Orders API with a Bearer header.

These two components **are not the same**, even if they share certain controlled network settings.

~~~text
Reactive OAuth2AuthorizedClientManager
     |
     +--> WebClientReactiveClientCredentialsTokenResponseClient
     |       |
     |       +--> POST https://login.example.test/oauth2/token
     |              (client credentials / grant parameters)
     |
     +--> Authorized client / access token
             |
             +--> WebClient with OAuth2 filter
                     |
                     +--> GET https://orders.example.test/api/orders
                            Authorization: Bearer <access_token>
~~~

An API-calling `WebClient` can use **`ServerOAuth2AuthorizedClientExchangeFilterFunction`** to obtain and attach access tokens from the reactive authorized client manager:

~~~java
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

WebClient ordersApi = WebClient.builder()
    .baseUrl("https://orders.example.test")
    .filter(oauth2)
    .build();
~~~

This is an **integration illustration** where `manager` must be a pre-configured reactive authorized client manager. When calling an API, specify the appropriate authorized client/registration in the request context, or configure a policy-compliant default—never assume every request automatically picks the right user token.

A `WebClient` with an OAuth2 filter for a Resource Server **does not automatically replace the HTTP client used for the token endpoint**. To change token HTTP transport, configure the token-response client itself and wire it into the authorized client provider or login authentication manager.

## 15. What About Using `WebClient` Inside a Servlet Application?

A Spring MVC/Servlet application **can use `WebClient`** to call APIs while its `SecurityFilterChain` remains Servlet-based. Conversely, a WebFlux application may invoke synchronous libraries in background tasks without turning its security stack into Servlet.

Choose the token client based on the application's **authentication/authorized-client infrastructure**, not merely which HTTP client a controller happens to use:

~~~text
Spring MVC + HttpSecurity + ClientRegistrationRepository
    -> OAuth2AccessTokenResponseClient (Servlet)

Spring WebFlux + ServerHttpSecurity + ReactiveClientRegistrationRepository
    -> ReactiveOAuth2AccessTokenResponseClient (Reactive)
~~~

If a project includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, verify Spring Boot's actual **web application type**. Looking only at Maven/Gradle or seeing a `WebClient` bean is not enough to determine which DSL applies.

**Never force a `Mono` to a synchronous value** with `block()` on an event loop just to reuse MVC configuration. Integrating blocking libraries inside a WebFlux app is an explicit scheduler/boundary architecture problem, not a default feature of token clients.

## 16. Timeouts, Proxies, TLS, and System Resources

The token endpoint is a critical dependency for login and token refresh. If it slows down or becomes unavailable, users cannot finish logging in or refresh tokens.

### 16.1. Servlet

With a synchronous token client, requests to the IdP can **hold a thread** until a response arrives or times out. Define clearly:

- **Connection timeout**: maximum time to establish a connection to the IdP.
- **Read/response timeout**: time spent waiting for the token response.
- **Connection pool** and connection limits under heavy load.
- **Proxy** for server egress to the Authorization Server.
- **TLS trust/certificates** and mTLS if required by the client authentication method.

Selecting `RestClient` and an underlying request factory configures the HTTP transport. Never disable TLS certificate/hostname verification as a "quick fix" for connection failures.

### 16.2. Reactive

With `WebClient` and Reactor Netty, I/O is non-blocking. That does not mean connections live forever or need no timeouts:

- Configure **response timeouts**, connection timeout/pool policies, and proper TLS.
- Monitor concurrent requests, error rates, and token endpoint latency.
- Avoid blocking calls on the Reactor event loop.
- When using reactive timeout/retry operators, consider **whether the grant is safely retryable**.

Specifically, authorization codes are typically **single-use**. When a POST exchanging a code times out, the client cannot know whether the IdP already received and consumed the code. **Never unconditionally auto-retry** code exchange requests.

### 16.3. Browser Reverse Proxy vs. Token Client Network Egress

The two network paths can be completely separate:

~~~text
Browser -> HTTPS public ingress -> Portal callback
Portal  -> HTTPS egress / corporate proxy -> IdP Token endpoint
~~~

If callback `redirect_uri` fails due to ingress scheme/host, that is a front-channel/public URL issue. If Portal's call to the token endpoint times out because of an egress proxy/firewall, that is a back-channel/network issue. Never tweak `redirectionEndpoint.baseUri` to fix TCP/TLS problems on token requests.

## 17. Protecting Credentials and Tokens in Both Stacks

The token endpoint can receive:

- **Client secret** or signed client assertion per registration.
- **Authorization code** and PKCE `code_verifier`.
- **Refresh token** during refresh grants.
- **Grant type** and other agreed parameters.

Therefore:

1. **Never put client secrets in committed `application.yml`**, frontend JavaScript, URL query strings, or exception outputs.
2. **Never log raw requests/responses** from the token endpoint: Authorization headers, form bodies, and token responses all contain sensitive data.
3. **Never send token responses to the browser** when a BFF architecture only needs a session cookie.
4. **Never use plain HTTP** for the token endpoint in production; verify certificates/TLS against trusted policies.
5. **Never override issuer/token-uri from client-supplied input**; endpoints must come from trusted provider configuration.
6. **Restrict scopes/audience** and access rights of client registrations.

Runtime secret management example:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
~~~

In production, Kubernetes Secrets, cloud secret managers, or mounted secrets are viable options per organizational policy. **Environment variables are a delivery channel into the process**, not a substitute for secret manager protections, RBAC, or restricting process diagnostics.

## 18. Unusual Token Response Configurations

In practice, providers sometimes have non-standard requirements or extensions such as:

- Adding a **form parameter** documented by the IdP during token exchange.
- Using another **client authentication** method, like `client_secret_post` or `private_key_jwt`.
- Requiring an egress proxy, mTLS, or a custom truststore.
- Returning extra extension parameters in the token response.

Handling principles:

1. **Read the provider's token endpoint contract/specification** to confirm exact requirements.
2. Prefer **extension point APIs on the token-response client** matching your Spring Security version.
3. Write custom converters/HTTP clients only when necessary; never replace the entire security flow.
4. Never strip standard parameters like `grant_type`, `code`, `redirect_uri`, PKCE verifier, or client authentication.
5. Ensure error responses become proper OAuth2 errors rather than swallowing exceptions and faking a successful login.

In modern Servlet, many `RestClient*TokenResponseClient` classes expose parameter converters/customizers and HTTP client setters. In Reactive, `WebClientReactive*TokenResponseClient` classes offer version-specific extension points. **Exact method names must match the class and version**; never assume every class shares the same API just because names look similar.

### 18.1. Why Shouldn't You POST Manually from a Controller?

Anti-pattern to avoid:

~~~java
@GetMapping("/login/oauth2/code/company")
public String callback(@RequestParam String code) {
    // Manually send POST, manually parse JWT, manually establish login...
    return "home";
}
~~~

This bypasses Spring Security's standard components for correlation, `state`, PKCE, token validation, and `SecurityContext`. OIDC login is far more than receiving an access token. Use the OAuth2 Login filter and customize **only the token-response client/hook** when you need to adjust how token requests are sent.

## 19. Comparing Token Endpoint Error Handling

The token endpoint can return OAuth2 errors:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_grant","error_description":"Authorization code invalid or expired"}
~~~

Common errors:

| Code / Symptom | Possible Cause | Which Stack? |
|---|---|---|
| `invalid_client` | Wrong client secret, client-authentication method, key/certificate | Both Servlet and Reactive |
| `invalid_grant` | Expired/used code, mismatched `redirect_uri` or PKCE | Both |
| `invalid_scope` | Rejected scope | Both |
| HTTP 429/503 | Authorization Server rate-limiting / unavailable | Both |
| TLS handshake failure | Wrong truststore/certificate/mTLS | Both |
| Timeout | Slow token endpoint or network/proxy | Both |
| Blocking event loop | Reactive code accidentally calling blocking APIs or `block()` | Primarily Reactive |
| Thread pool exhaustion when IdP slows | Many synchronous requests waiting on HTTP responses | Primarily Servlet |
| Reactive bean unused | Declared bean without wiring into the matching manager/hook | Primarily when customizing Reactive |

In Servlet, token client failures are typically thrown and handled by the corresponding exception/filter chain. In Reactive, errors travel as **Mono error signals** processed by the reactive authentication infrastructure. If you write `onErrorResume`, never turn `invalid_grant` into an empty token response treated as valid.

**Never diagnose solely from a single HTTP status code.** Separate unmatched login callbacks, state mismatches, token endpoint HTTP errors, ID Token verification failures, and Resource Server access-token rejections.

## 20. Testing Token Clients in Both Stacks

### 20.1. Testing Servlet Token-Response Clients

Approach:

- Use a mock HTTP server or controllable HTTP request factory to simulate the token endpoint.
- Pass a valid `OAuth2AuthorizationCodeGrantRequest` in the test environment.
- Assert the client builds the form request, client authentication, redirect URI, and PKCE per configuration.
- Return both success JSON token responses and OAuth2 error responses to test both paths.

Never use production secrets or authorization codes in tests. In full OIDC integration tests, supply valid client registrations and provider metadata if booting the full Spring context.

### 20.2. Testing Reactive Token-Response Clients

Approach:

- Stub `WebClient`/`ExchangeFunction` or use a mock HTTP server to emit token responses and errors in Reactor context.
- Use **`StepVerifier`** to assert emissions and error signals of `Mono<OAuth2AccessTokenResponse>`.
- Test timeouts, connection failures, subscription cancellation, and non-blocking execution inside reactive flows.
- For end-to-end OIDC login tests, also verify callback state/session and ID Token validation—not just a JSON token response.

Illustrative snippet showing how to test a `Mono` (not a full standalone login test):

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import org.springframework.security.oauth2.core.OAuth2AccessTokenResponse;

Mono<OAuth2AccessTokenResponse> response =
    reactiveTokenClient.getTokenResponse(grantRequest);

StepVerifier.create(response)
    .assertNext(token -> {
        // Assert required properties in the test.
    })
    .verifyComplete();
~~~

Using `reactor.test.StepVerifier` requires the `reactor-test` dependency. In the snippet above, `reactiveTokenClient` and `grantRequest` are pre-built test fixtures, not a complete standalone runnable test.

## 21. Checklist for Selecting and Integrating a Token Client

| Question | Servlet | Reactive |
|---|---|---|
| Which security chain is active? | `SecurityFilterChain` / `HttpSecurity` | `SecurityWebFilterChain` / `ServerHttpSecurity` |
| Which token-response API is needed? | `OAuth2AccessTokenResponseClient` | `ReactiveOAuth2AccessTokenResponseClient` |
| Which HTTP transport fits? | `RestClient` or `RestOperations` in older versions | `WebClient` |
| Which grant is actually used? | Code, refresh, or client credentials | Code, refresh, or client credentials |
| Configuring for login or API calls? | `oauth2Login().tokenEndpoint()` or authorized-client provider | Reactive authentication manager/hook or reactive authorized-client provider |
| Is a custom token HTTP client needed? | Only when required by provider/network | Only when required by provider/network |
| How are requests executed? | Synchronous; tune timeouts/thread capacity | Reactive pipeline; never block |
| Are secrets/tokens protected? | TLS, secret manager, redaction, right issuer | Same security requirements |
| Using the right API version? | Check `RestClient` 6.4+ vs. legacy `Default` | Check version's `WebClient` reactive token client |
| Testing success/error paths? | Mock token endpoint; no prod IdP needed | Mock `WebClient`/HTTP + `StepVerifier`; no prod IdP needed |

A good engineering decision is not "pick Reactive because it sounds modern," but **choosing the token client that matches your application's web stack and authorized-client infrastructure**, then customizing only what is truly needed.

## 22. Applied Exercises

### Exercise 1: Spotting Interface Mismatches

Given:

~~~java
ReactiveOAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>
    tokenClient = new RestClientAuthorizationCodeTokenResponseClient();
~~~

**Question:** Why does this fail?

**Hint:** The left side requires a Reactive contract returning `Mono`, while the right side is a synchronous Servlet token client. In WebFlux, use `WebClientReactiveAuthorizationCodeTokenResponseClient`. In Servlet, change the variable type to `OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>`.

### Exercise 2: Choosing Where to Configure

A Spring MVC app needs to adjust the HTTP timeout for **exchanging an authorization code**. A developer edits the `RestClient` used to call Orders API, yet login still times out.

**Question:** Why?

**Hint:** The Resource Server API client and the token response client are two separate integration points. Change the HTTP transport on `OAuth2AccessTokenResponseClient<OAuth2AuthorizationCodeGrantRequest>` and wire it into `oauth2Login()`'s token endpoint.

### Exercise 3: Reactive Yet Blocking

A WebFlux app executes:

~~~java
OAuth2AccessTokenResponse response =
    reactiveTokenClient.getTokenResponse(grantRequest).block();
~~~

**Question:** What is wrong here?

**Hint:** Blocking on the event loop degrades throughput and can throw errors. Let the framework/`ReactiveAuthenticationManager` orchestrate the `Mono` or compose it in the reactive pipeline using non-blocking operators.

### Exercise 4: Refresh Token

An app logs in successfully and receives a refresh token. When the access token expires, the developer only customized the authorization-code token client, so refresh requests still use default HTTP settings.

**Question:** Why?

**Hint:** Authorization code and refresh token are **two different grants**. Configure the refresh-token response client on the corresponding authorized-client provider/manager to customize HTTP transport or parameters for refresh requests.

### Exercise 5: Errors Not Caused by the Token Client

The IdP reports `redirect_uri_mismatch` immediately when the browser is sent to the authorization endpoint.

**Question:** Should you change the `RestClient`/`WebClient` token response client?

**Hint:** No. This is an **authorization request / registered redirect URI** error occurring before Portal ever calls the token endpoint. Check public URLs, proxy/forwarded headers, `ClientRegistration.redirectUri`, and IdP configuration.

## 23. Key Takeaways

In Spring Security OAuth 2.0/OIDC Client, **Servlet and Reactive share the same protocol goals when calling the token endpoint, yet use distinct execution APIs**:

1. **Servlet** uses `OAuth2AccessTokenResponseClient<T>` with typically synchronous HTTP clients; Spring Security 6.4+ provides the `RestClient*TokenResponseClient` family.
2. **Reactive** uses `ReactiveOAuth2AccessTokenResponseClient<T>`, returning `Mono<OAuth2AccessTokenResponse>`, typically via the `WebClientReactive*TokenResponseClient` family.
3. **Each grant has its matching token client**: authorization code, refresh token, and client credentials are not identical requests.
4. **OAuth2 Login** and **authorized-client management** are two separate integration points; wire custom token clients into whichever component actually sends the request.
5. **An API-calling `WebClient` does not automatically become the token endpoint's `WebClient`**; your web stack is determined by the Servlet/WebFlux security infrastructure, not HTTP client names in code.
6. **Protecting credentials, tokens, and IdP connectivity** is universal: TLS, timeouts, no logging of secrets/tokens, controlled network egress, and no blind retries of single-use code grants.

When designing from scratch, prefer **Spring Security's default token client for your stack and version**. Add custom configuration only for concrete requirements around timeouts, TLS, proxies, provider parameters, or grant lifecycles. This keeps Authorization Code/OIDC login flows secure, upgrade-friendly, and consistent across Servlet and Reactive.
