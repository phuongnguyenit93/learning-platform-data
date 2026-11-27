# 17.4. `RefreshTokenReactiveOAuth2AuthorizedClientProvider` in Reactive

## 1. Problem Statement: Login Is Still Valid, Yet the Access Token Has Expired

Suppose **Employee Portal** uses **Spring Boot, Spring Security OAuth 2.0 Client, and WebFlux**. The user logs in via OpenID Connect (OIDC), and the Portal then calls the **Orders API** on their behalf. The Authorization Server issues:

~~~text
Access token AT-1:
  issued_at  = 09:00
  expires_at = 09:05

Refresh token RT-1:
  used to request a new access token per Authorization Server policy
~~~

At **09:07**, the Portal's HTTP session is still active and the user still has a valid `Authentication`, yet **AT-1 has expired**. If the Portal sends AT-1 to the Orders API, the Resource Server may reject it with `401 invalid_token`.

The system can use the **Refresh Token Grant** to request AT-2 without forcing the user through another full interactive login:

~~~text
Access token expired
       |
       v
Check whether authorized client has a refresh token?
       |
       +-- No --> Cannot refresh via this grant
       |
       +-- Yes
             |
             v
POST token endpoint (grant_type=refresh_token)
             |
             v
Receive AT-2, and possibly RT-2 if the server rotates refresh tokens
             |
             v
Save updated OAuth2AuthorizedClient
             |
             v
Call Orders API with AT-2
~~~

In **Spring Security Reactive**, the class responsible for deciding **whether an authorized client should be refreshed** is:

~~~java
org.springframework.security.oauth2.client
    .RefreshTokenReactiveOAuth2AuthorizedClientProvider
~~~

This is the focus of this lesson. This class **does not run on a schedule**, does not create OIDC sessions on its own, and is not the HTTP client calling the Orders API. It is a **`ReactiveOAuth2AuthorizedClientProvider`** that `ReactiveOAuth2AuthorizedClientManager` can invoke whenever an appropriate authorized client is needed.

> Example context: Java 17+, Spring Boot 3, Spring Security 6, **Spring WebFlux / Reactive**, and Reactor. Domains, tokens, and client IDs are illustrative. Specific configuration methods may differ across Spring Security versions; use the API provided by your project's dependencies.

## 2. Where the Refresh Token Provider Fits in the Architecture

Spring Security OAuth2 Client has three easily confused component types:

| Component | Responsibility |
|---|---|
| **`ReactiveOAuth2AuthorizedClientManager`** | Coordinates loading, issuing, refreshing, and saving authorized clients |
| **`ReactiveOAuth2AuthorizedClientProvider`** | Determines whether a grant can be used in the current context and executes it if applicable |
| **`ReactiveOAuth2AccessTokenResponseClient`** | Executes the HTTP token request to the Authorization Server and parses the token response into Java objects |

For the Refresh Token Grant:

~~~mermaid
flowchart TD
    A["WebFlux handler / WebClient needs access token"] --> B["ReactiveOAuth2AuthorizedClientManager"]
    B --> C["Reactive authorized-client repository/service"]
    C --> D["Current OAuth2AuthorizedClient"]
    D --> E["RefreshTokenReactiveOAuth2AuthorizedClientProvider"]
    E --> F{"Has refresh token and access token needs refresh?"}
    F -->|No| G["Mono.empty() - provider does not perform refresh"]
    F -->|Yes| H["WebClientReactiveRefreshTokenTokenResponseClient"]
    H --> I["POST token endpoint"]
    I --> J["OAuth2AccessTokenResponse"]
    J --> K["New OAuth2AuthorizedClient"]
    K --> B
    B --> L["Save authorized client and return result"]
    L --> M["WebClient calls Orders API with access token"]
~~~

The **provider** returns its result via a Reactor `Mono`. When the grant does not apply, the provider typically returns `Mono.empty()` so the manager or another provider can continue. When it refreshes successfully, it emits a new `OAuth2AuthorizedClient`. When the token endpoint fails, it emits an **error signal** rather than a fake token.

### 2.1. Distinguishing three lifecycles

1. **OIDC login / Authentication**: the browser and app establish that the user has logged in via the Authorization Code Flow.
2. **`OAuth2AuthorizedClient`**: token information issued for a `ClientRegistration` and principal.
3. **Refresh Token Grant**: issues a new access token from an authorized client that holds a valid refresh token.

A refresh token **does not mean the login session is still valid**, and a successful refresh **does not automatically create a new `Authentication`** in `SecurityContext`.

## 3. What Does `RefreshTokenReactiveOAuth2AuthorizedClientProvider` Do?

Full name:

~~~java
import org.springframework.security.oauth2.client
    .RefreshTokenReactiveOAuth2AuthorizedClientProvider;
~~~

It implements:

~~~java
import org.springframework.security.oauth2.client
    .ReactiveOAuth2AuthorizedClientProvider;
~~~

Conceptual interface contract:

~~~java
public interface ReactiveOAuth2AuthorizedClientProvider {
    Mono<OAuth2AuthorizedClient> authorize(
        OAuth2AuthorizationContext context
    );
}
~~~

When called, the provider inspects the authorized client in the context:

- **Does an already-authorized client exist?**
- **Does the authorized client have a refresh token?**
- **Has the access token expired or come close to expiring per clock skew?**
- **If eligible, does the token-response client exchange the refresh token successfully?**

The provider **does not need a browser redirect** to execute the refresh token grant. The HTTP request is sent **server-to-server** to the Authorization Server's token endpoint.

### 3.1. Cases and outcomes

| Authorized client | Refresh token | Access token | Refresh provider behavior |
|---|---|---|---|
| Does not exist yet | — | — | Nothing to refresh, returns `Mono.empty()` |
| Exists | Absent | Expired | Cannot use Refresh Token Grant, typically `Mono.empty()` |
| Exists | Present | Valid outside clock skew | Does not refresh, typically `Mono.empty()` |
| Exists | Present | Expired or within clock skew window | Calls token endpoint with refresh token |
| Exists | Present | Needs refresh, token endpoint succeeds | Emits new `OAuth2AuthorizedClient` |
| Exists | Present | Needs refresh, token endpoint rejects | Emits Reactor error `Mono.error(...)` |

**`Mono.empty()` does not mean "the user has logged out"**, nor does it mean "the current token is unusable". It indicates that **this provider did not perform a new authorization in that context**.

### 3.2. Which responsibilities do NOT belong to the provider?

The provider does not:

- Decide resource permissions for the Orders API.
- Re-verify passwords or perform interactive OIDC login.
- Permanently persist tokens in a database by itself.
- Invalidate user sessions when a refresh fails.
- Run scheduled cron refreshes when nobody requests an authorized client.
- Revoke refresh tokens at the Authorization Server when the user logs out.

Those behaviors belong to the **manager**, **repository/service**, **security/session policy**, and **Authorization Server**.

## 4. `Mono` and Reactive's Non-Blocking Model

The Reactive API describes an asynchronous operation:

~~~java
Mono<OAuth2AuthorizedClient> refreshed =
    refreshProvider.authorize(context);
~~~

In a Reactive pipeline, **compose/return the Publisher** to the upstream caller:

~~~java
return refreshProvider.authorize(context)
    .flatMap(client -> callOrdersApi(client.getAccessToken()))
    .switchIfEmpty(Mono.defer(() -> handleNoRefresh()));
~~~

This snippet illustrates the concept; `callOrdersApi(...)` and `handleNoRefresh()` are example business functions. In typical WebFlux applications, **the manager and WebClient OAuth2 filter** handle most orchestration, so controllers do not call the refresh provider directly.

**Never call `.block()` inside the request-handling event loop:**

~~~java
// Do not do this inside a reactive HTTP handler:
OAuth2AuthorizedClient value =
    refreshProvider.authorize(context).block();
~~~

Blocking on a Reactor event loop can throw runtime errors or severely degrade throughput if the IdP is slow.

### 4.1. Creating a `Mono` does not mean the token is refreshed immediately

Reactor Publishers are typically **lazy**: building a `Mono` does not immediately fire an HTTP request. Spring Security/WebClient integration handles subscription when the request actually executes.

Do not manually call `.subscribe()` in a service just to "pre-refresh a token" and discard the result; that easily drops error handling, context, and the new token result. If proactive refresh is needed, build a workflow with explicit lifecycle and storage rather than fire-and-forget calls in a controller.

## 5. Access Token Expiration and Clock Skew

Suppose an access token has:

~~~text
issuedAt  = 2026-11-16T02:00:00Z
expiresAt = 2026-11-16T02:05:00Z
clockSkew = 60 seconds
~~~

If the system considers the token **about to expire** when:

\[
\text{now} \geq \text{expiresAt} - \text{clockSkew}
\]

then the token can be refreshed starting at **02:04:00Z**, before `expiresAt`.

The goal of clock skew is to reduce cases where:

1. The client thinks the token still has a few seconds remaining.
2. The request traverses networks, queues, or gateways.
3. The Resource Server receives the token after it has already expired.

### 5.1. Customizing clock skew

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.client
    .RefreshTokenReactiveOAuth2AuthorizedClientProvider;

RefreshTokenReactiveOAuth2AuthorizedClientProvider refreshProvider =
    new RefreshTokenReactiveOAuth2AuthorizedClientProvider();

refreshProvider.setClockSkew(Duration.ofSeconds(90));
~~~

In this example, the provider treats a token as **needing early refresh** if remaining validity falls within 90 seconds. An appropriate value depends on latency, token lifetime, clock drift, and system load.

**Do not set clock skew nearly as large as or larger than the access token lifetime**, as that can cause overly frequent refreshes. Synchronize clocks across the application and Authorization Server, monitor latency, and never arbitrarily modify `expiresAt` in the database to "force a refresh".

### 5.2. Clock skew does not extend sessions

`setClockSkew(...)` only adjusts **when the provider decides an access token needs refreshing**. It does not change:

- HTTP session timeout.
- ID Token expiry.
- OIDC `max_age` or reauthentication requirements.
- Refresh token lifetime.
- Resource permissions on the Resource Server.

## 6. What Does the Refresh Token Grant Send to the Token Endpoint?

When an access token needs refreshing, the provider delegates to the token-response client. At the protocol level, the HTTP request looks like:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <redacted-client-credentials>

grant_type=refresh_token&refresh_token=<redacted-refresh-token>
~~~

This is an **illustrative request** for a confidential client using `client_secret_basic`. Providers may require a different authentication method, an additional scope, or documented extension parameters. The client must follow its registered configuration and the Authorization Server's contract.

Response:

~~~json
{
  "access_token": "EXAMPLE_AT_2",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "EXAMPLE_RT_2",
  "scope": "orders.read"
}
~~~

Some servers **do not return a new refresh token** in the response. In that case, the client can keep using the existing refresh token per library/server token response handling policies. If the server returns RT-2 under **refresh token rotation**, RT-1 may immediately become unusable.

**Never log these credentials or send them to the browser.** A refresh token can mint new access tokens and must remain protected on the backend.

## 7. `WebClientReactiveRefreshTokenTokenResponseClient`

The refresh provider needs a token-response client matching the grant:

~~~java
import org.springframework.security.oauth2.client.endpoint
    .ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.endpoint
    .OAuth2RefreshTokenGrantRequest;
import org.springframework.security.oauth2.client.endpoint
    .WebClientReactiveRefreshTokenTokenResponseClient;
~~~

Contract:

~~~java
ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
~~~

This client is responsible for **POSTing to the token endpoint** and converting the response into an `OAuth2AccessTokenResponse` wrapped in a `Mono`.

The provider decides **when to call that client** and **constructs the new `OAuth2AuthorizedClient`**. The manager handles **orchestration and saving** per storage policy.

### 7.1. Initializing the provider with a custom token response client

~~~java
import java.time.Duration;
import org.springframework.security.oauth2.client.RefreshTokenReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveRefreshTokenTokenResponseClient;

WebClientReactiveRefreshTokenTokenResponseClient tokenClient =
    new WebClientReactiveRefreshTokenTokenResponseClient();

RefreshTokenReactiveOAuth2AuthorizedClientProvider refreshProvider =
    new RefreshTokenReactiveOAuth2AuthorizedClientProvider();

refreshProvider.setAccessTokenResponseClient(tokenClient);
refreshProvider.setClockSkew(Duration.ofSeconds(60));
~~~

Here we have not yet built a full manager—only configured a **refresh provider**. If the app already uses Spring Security's default provider chain, creating this instance **without attaching it to the chain/manager actually in use** will not change runtime behavior.

### 7.2. Customizing the `WebClient` HTTP transport

When timeouts are needed for the HTTP token request:

~~~java
import java.time.Duration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.security.oauth2.client.endpoint.WebClientReactiveRefreshTokenTokenResponseClient;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

HttpClient httpClient = HttpClient.create()
    .responseTimeout(Duration.ofSeconds(5));

WebClient tokenWebClient = WebClient.builder()
    .clientConnector(new ReactorClientHttpConnector(httpClient))
    .build();

WebClientReactiveRefreshTokenTokenResponseClient tokenClient =
    new WebClientReactiveRefreshTokenTokenResponseClient();

tokenClient.setWebClient(tokenWebClient);
~~~

This is an **example of tuning transport**, not a reason to rewrite OAuth2 token conversion or error handling from scratch. In production systems, configure connection timeouts, egress proxies, TLS trust/mTLS, connection pools, and load limits according to your architecture.

Never disable TLS hostname/certificate verification to work around token endpoint errors. Never enable HTTP wire logging containing client secrets or refresh tokens.

### 7.3. Avoid confusing the two `WebClient` instances

~~~text
WebClient A:
  used by WebClientReactiveRefreshTokenTokenResponseClient
  -> POST https://login.example.test/oauth2/token

WebClient B:
  used by the application to call the Resource Server
  -> GET https://orders.example.test/api/orders
     Authorization: Bearer <access-token>
~~~

Customizing WebClient B **does not change WebClient A**. Customizing WebClient A **does not attach access tokens to WebClient B**. Both parts must be connected properly via the provider, manager, and authorized-client integration.

## 8. Spring Boot WebFlux and `ClientRegistration`

Dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Example OIDC registration:

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
        provider:
          company:
            issuer-uri: ${OIDC_ISSUER_URI}
~~~

Where:

- `company` is the **registration ID**, not a user ID.
- `openid` enables OIDC login when supported by the provider.
- `orders.read` requests scope for the Orders API, though actual tokens must be authorized by the server with the proper audience.
- `OIDC_CLIENT_SECRET` must come from a secret manager/runtime environment, never from the repository or frontend.
- **A refresh token may not be issued**, depending on provider settings, grant, client policy, and consent. Never assume having the `openid` scope always produces a refresh token.

### 8.1. Callback and token refresh are different

Authorization Code Flow has a **front-channel callback**, whereas the Refresh Token Grant needs no browser callback:

~~~text
OIDC login:
  Browser -> OP -> /login/oauth2/code/company -> exchange code for tokens

Refresh:
  WebFlux backend -> POST token endpoint with refresh_token -> new tokens
~~~

If the callback fails with `invalid_state`, `redirect_uri_mismatch`, or a lost session, tweaking the refresh provider will not fix it. Troubleshoot the authorization request, callback URL, cookies/sessions, and OIDC login flow separately.

## 9. `SecurityWebFilterChain` and OAuth2 Login

For a WebFlux application:

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
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

`oauth2Login()` configures OIDC login on WebFlux. `oauth2Client()` enables OAuth2 Client support. This configuration **does not require writing a custom callback controller** and **does not guarantee a refresh token always exists**.

**WebFlux does not use `SecurityFilterChain(HttpSecurity)` or `HttpServletRequest` for the security flow.** Reactive security uses `SecurityWebFilterChain`, `ServerHttpSecurity`, and `ServerWebExchange`.

## 10. `ReactiveOAuth2AuthorizedClientManager` Actually Triggers Refresh

On WebFlux, the manager coordinates providers and persistence. A common configuration for **HTTP request context**:

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
public class ReactiveAuthorizedClientConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository authorizedClients
    ) {
        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

**Key points:**

1. `ReactiveClientRegistrationRepository` supplies the configured client registrations.
2. `ServerOAuth2AuthorizedClientRepository` loads/saves authorized clients in the WebFlux request context.
3. The provider chain supports `authorization_code` and `refresh_token`.
4. The manager invokes the provider, receives the result, and saves it via the repository/handler.

If an app only configures `.authorizationCode()` without a refresh provider, an expired token **will not automatically refresh via the `refresh_token` grant** through that manager.

### 10.1. Why not call the provider directly in a controller?

Normally, a controller should not do:

~~~java
// Hard-to-maintain design: controller calls refresh provider and saves token manually.
return refreshProvider.authorize(context)
    .flatMap(refreshed -> repository.saveAuthorizedClient(...));
~~~

Let the **manager** handle selecting the registration, creating the context, calling the provider, and persisting tokens. Controllers and HTTP clients use the manager or framework-provided integrations.

### 10.2. Attaching a customized refresh provider to the manager

If you need a custom clock skew or token-response client, one option is configuring a manager **that only refreshes already-existing authorized clients**:

~~~java
package com.example.portal.reactive;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.RefreshTokenReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
class RefreshOnlyManagerConfig {

    @Bean("refreshOnlyManager")
    ReactiveOAuth2AuthorizedClientManager refreshOnlyManager(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository authorizedClients
    ) {
        RefreshTokenReactiveOAuth2AuthorizedClientProvider refresh =
            new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        refresh.setClockSkew(Duration.ofSeconds(90));

        DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients
            );
        manager.setAuthorizedClientProvider(refresh);
        return manager;
    }
}
~~~

This is an example of a **refresh-only manager**, shown to understand the wiring. It **does not execute the `authorization_code` grant to create a new authorized client**, because the provider chain only contains refresh. When no authorized client exists yet, the manager cannot initiate an authorization flow using the refresh provider alone.

In an application supporting both login/authorization code and refresh, combine the needed providers or use Spring Security's provider builder with refresh configuration appropriate to your version. Never register two manager beans for the same consumer without knowing which instance is wired.

## 11. Using the Manager to Obtain an Authorized Client in WebFlux

After a user completes OIDC login, a controller or WebClient integration can invoke the manager by registration and principal.

An example usage pattern from a service **when a valid `Authentication` and proper WebFlux context are already present**:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import reactor.core.publisher.Mono;

Mono<OAuth2AuthorizedClient> authorizeCompany(
    ReactiveOAuth2AuthorizedClientManager manager,
    Authentication authentication
) {
    OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest
            .withClientRegistrationId("company")
            .principal(authentication)
            .build();

    return manager.authorize(request);
}
~~~

**Note:** `DefaultReactiveOAuth2AuthorizedClientManager` for WebFlux requests also needs `ServerWebExchange` or corresponding context attributes to interact with `ServerOAuth2AuthorizedClientRepository`. If calling the manager manually outside framework integration, pass/map the HTTP exchange context per your version's API. A plain `Authentication` Java object alone may not provide enough context for every repository.

For typical WebFlux controllers, it is more convenient to use a **WebClient OAuth2 filter** integrated with the manager.

### 11.1. `WebClient` using the right manager

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class OrdersWebClientConfig {

    @Bean("ordersWebClient")
    WebClient ordersWebClient(
        ReactiveOAuth2AuthorizedClientManager manager
    ) {
        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://orders.example.test")
            .filter(oauth2)
            .build();
    }
}
~~~

And when calling the API:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

public Mono<String> listOrders(WebClient ordersWebClient) {
    return ordersWebClient.get()
        .uri("/api/orders")
        .attributes(clientRegistrationId("company"))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

Within an authenticated WebFlux request, the filter asks the manager to locate or refresh the authorized client. The manager/provider chain must include `refreshToken()`; otherwise, an expired token will not be renewed via that grant.

**Do not configure a "default authorized client" for arbitrary requests.** Specify the registration matching the Resource Server and the principal's permissions. One client/tenant's token must never be sent to an unauthorized API.

### 11.2. Do you need to call `refreshToken()` directly?

You do not need a `refreshToken()` method in a controller. Refreshing is triggered when **`manager.authorize(...)`** is called and the provider finds the conditions met. A request using the HTTP client's OAuth2 filter indirectly triggers that behavior.

If you merely read `OAuth2AuthorizedClient` from a repository without calling the manager/provider, do not assume reading will refresh via the token endpoint.

## 12. Manager for Background Jobs Without `ServerWebExchange`

A scheduled job using `client_credentials` or a task with its own valid delegation mechanism **has no WebFlux HTTP request**. In that case, `DefaultReactiveOAuth2AuthorizedClientManager` bound to a server exchange is not the right choice.

Spring Security provides:

~~~java
org.springframework.security.oauth2.client
    .AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
~~~

Example:

~~~java
package com.example.portal.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
class BackgroundManagerConfig {

    @Bean("backgroundAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager backgroundAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService clientService
    ) {
        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, clientService
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

This is a **dedicated service-to-service manager**, not the same instance used in the controller examples above. Client credentials normally do not receive refresh tokens; when an access token expires, the manager requests a new access token via the **`client_credentials` grant** instead of the `refresh_token` grant.

If a background workflow genuinely manages authorized clients with refresh tokens, the provider chain may include `refreshToken()` per policy. However, you must establish **the source of the principal and authority to act on the user's behalf**, never pulling an arbitrary token from the repository by guessing a principal name inside the job.

## 13. `RefreshTokenReactiveOAuth2AuthorizedClientProvider` vs. Other Providers

| Provider / Grant | Initial input required | Outcome | Requires browser interaction? |
|---|---|---|---|
| **Authorization Code** | Authorization request/callback, code, and state | Initial authorized client after authorization | Yes, during initial authorization |
| **Refresh Token** | Existing authorized client + refresh token | New access token, optionally new refresh token | Normally no |
| **Client Credentials** | Client registration/credentials | Access token for a service identity | No |

Depending on configuration, a provider chain may include:

~~~java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
~~~

**Having three providers does not mean a single registration uses all three grants simultaneously.** The `authorization-grant-type` on `ClientRegistration` and the authorization context determine which grant applies.

An OIDC client registration with `authorization_code` cannot turn into `client_credentials` just because the manager supports `.clientCredentials()`. Likewise, a service token must not be treated as a user token.

## 14. Token State After Refreshing

Suppose before refreshing:

~~~text
OAuth2AuthorizedClient
  registrationId = company
  principalName  = employee-0042
  accessToken    = AT-1, expires 09:05
  refreshToken   = RT-1
~~~

After a successful refresh:

~~~text
OAuth2AuthorizedClient
  registrationId = company
  principalName  = employee-0042
  accessToken    = AT-2, expires 09:10
  refreshToken   = RT-2 (if rotated) or value per response handling
~~~

**The registration and principal do not switch to another user** just because a new token was issued. The manager must save the updated record in the proper location, typically keyed by registration ID and principal name or repository context.

Some providers may return updated scopes or extra data in the token response. The application must rely on the parsed token response per the OAuth2 specification, never inventing arbitrary `expiresAt` values or assuming scopes always expand.

### 14.1. Refresh does not automatically update OIDC Authentication

If the user's `SecurityContext` holds an `OidcUser`, refreshing the access token normally **does not replace `OidcUser` with a freshly authenticated principal** or reload all UserInfo claims.

Example:

~~~text
09:00 login: OidcUser.email = minh@example.test
09:10 email changes at the IdP
09:12 access token refresh succeeds
~~~

You cannot conclude from a successful refresh that `OidcUser.email` in the Portal session has updated. Profile synchronization and reauthentication are separate concerns with separate policies.

Even if a refresh response includes supplemental OIDC fields in a specific setup, never treat it as a brand-new ID Token login while bypassing OIDC validation rules.

## 15. `invalid_grant` Errors and Failure Handling

The token endpoint may reject a refresh:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant",
  "error_description": "Refresh token is invalid or expired"
}
~~~

Common causes:

- The refresh token expired per Authorization Server policy.
- The refresh token was revoked due to logout, admin action, or policy change.
- Refresh token rotation invalidated the old token.
- The refresh token does not belong to the client, is invalid, or is disallowed for the grant.
- Authorized-client store synchronization failed, causing the client to reuse an old refresh token.

Errors from the WebClient/token endpoint flow through a **Reactor error signal**. The manager can apply an authorization failure handler to remove the invalid authorized client from the store, depending on implementation and configuration.

### 15.1. Distinguishing `invalid_grant` from network errors

| Case | Meaning | Resolution approach |
|---|---|---|
| `invalid_grant` | Refresh token/grant rejected by the Authorization Server | Remove invalid token per policy; require re-authorization when needed |
| `invalid_client` | Client authentication failed | Check client ID/secret, mTLS, or authentication method |
| `invalid_scope` | Invalid scope in request | Check registration and provider policy |
| HTTP 429 | Token endpoint rate limiting | Apply appropriate backoff/throttling; do not spam refreshes |
| HTTP 500/503 | Authorization Server outage | Return infrastructure error; bounded retries without wiping all user sessions |
| Timeout/TLS failure | Network or transport error | Check proxy, DNS, CA, mTLS, and timeouts |

**Do not destroy every WebFlux session when a single refresh token fails.** Users may remain authenticated in the Portal under session policy while lacking a valid token for a specific Resource Server. Classify the impact and guide the user to re-authorize when needed.

### 15.2. Do not swallow error signals

Dangerous example:

~~~java
// Do not return the old authorized client as if the refresh succeeded:
return refreshProvider.authorize(context)
    .onErrorResume(ex -> Mono.just(oldAuthorizedClient));
~~~

If the old token has already been rejected, this fallback makes the Portal keep sending an invalid Bearer token and creates an error loop. Handle exceptions by type, apply cleanup policies, and prompt the user to re-authorize.

### 15.3. Manager failure handlers

In Spring Security Reactive, authorization success/failure handlers save or remove authorized clients in the appropriate cases. Check the default behavior of your **manager and Spring Security version**: certain `invalid_grant` errors remove the authorized client record, though not **every error** warrants deleting the token.

Never log raw token endpoint error responses if they might contain credentials or user data. Log masked error codes, registration ID, correlation ID, and timestamps sufficient for investigation.

## 16. Refresh Token Rotation and Concurrency Issues

This scenario is especially important in Reactive systems handling many concurrent requests:

~~~mermaid
sequenceDiagram
    participant A as Request A / Node A
    participant B as Request B / Node B
    participant Store as Authorized Client Store
    participant AS as Authorization Server

    A->>Store: Load AT-1 + RT-1
    B->>Store: Load AT-1 + RT-1
    A->>AS: Refresh RT-1
    AS-->>A: AT-2 + RT-2
    B->>AS: Refresh RT-1
    AS-->>B: invalid_grant (RT-1 already used)
    A->>Store: Save AT-2 + RT-2
    Note over A,B: If a failure handler deletes the record at the wrong moment, the successful refresh result can be affected
~~~

On some OPs, the same refresh token can be used multiple times; on others, **rotation/reuse detection** can revoke the entire token family upon detecting reuse. Consequently, no single retry strategy works for every provider.

Design approaches:

1. Use an **authorized-client store that maintains consistency** across replicas.
2. When needed, coordinate refreshes by `(registrationId, principalName)` or the store's actual key.
3. Choose a **single-flight / lock / optimistic concurrency** strategy appropriate to your architecture.
4. Persist both the new access token and the new refresh token **atomically** after rotation.
5. Never blindly retry the same RT-1 after `invalid_grant`.
6. Avoid deleting newer token data when another request fails with an older token, if storage supports checking version/generation.

**`Mono` does not automatically solve race conditions.** Non-blocking I/O does not turn multiple requests into a single transaction or a single refresh.

### 16.1. Early refreshes can increase collisions

If clock skew is too large, many requests will treat valid tokens as "about to expire" early. Under heavy load, the number of requests racing to refresh simultaneously can spike.

Tune clock skew based on actual lifetime, latency, and concurrency; do not set it overly large just to "be sure tokens are always fresh".

## 17. Multi-Instance: Session and Token Store Are Two Separate Things

~~~text
                     +--> WebFlux Node A
Browser -> Gateway --|
                     +--> WebFlux Node B
                               |
                +--------------+---------------+
                |                              |
          Web Session Store             Authorized Client Store
                |                              |
          SecurityContext               AT / RT for principal
~~~

With OIDC login, the browser needs to preserve its session so Spring Security can handle the callback and establish `Authentication`. With authorized clients, the manager needs to load the right issued/refreshed tokens.

If sessions are shared while the authorized client store is local to each node, Node B will not find Node A's RT-1. If authorized clients are shared while the session is lost, the browser is no longer authenticated and must not arbitrarily use tokens for a browser-specified principal.

**Separate stores should be designed for their distinct roles**:

- WebSession persistence/correlation: e.g., a Reactive session store.
- Authorized-client repository/service: stores AT/RT, protected with encryption/access control/TTL/auditing per policy.
- Role/tenant membership: application authorization policy, possibly backed by its own data source.

Do not confuse a **refresh token** with a **login cookie**. Refresh tokens normally never need to travel to the browser in a BFF/server-side web client.

## 18. Are Refresh Tokens Always Issued in OIDC?

No. Reasons a refresh token may be absent:

- The Authorization Server does not allow refresh tokens for this client type.
- Grant, scope, or consent does not satisfy policy.
- A provider-required condition is missing, such as offline access permission in some systems.
- The client is registered under a profile that disallows holding long-lived refresh credentials.
- The user revoked permissions or policy was updated.

If the authorized client has no refresh token:

~~~text
Existing authorized client
  accessToken = expired
  refreshToken = null
~~~

`RefreshTokenReactiveOAuth2AuthorizedClientProvider` cannot refresh it. The application needs a **new authorization code flow**, another token issuance mechanism allowed by the client registration, or a prompt asking the user to re-authorize.

**Never synthesize a refresh token** from an ID Token, access token, session cookie, or `sub`. Refresh tokens must be issued and protected by the Authorization Server.

## 19. Refresh Does Not Replace Reauthentication, Consent, or Authorization

Suppose a user had `orders.read` permission at login. Later, their permission is revoked in the Orders API.

~~~text
WebFlux session remains active
Refresh token remains valid
Access token refreshes to AT-2
Orders API can still return 403
~~~

Refreshing only requests **a new token** under the existing grant/authorization and Authorization Server policy—it does not guarantee the Resource Server will re-grant permissions.

The application must distinguish:

| Question | Primary mechanism |
|---|---|
| Is the user signed into the Portal? | WebFlux Authentication / SecurityContext / session |
| Does the access token need renewal? | Reactive authorized-client manager + refresh provider |
| Must the user re-enter password/MFA? | OIDC authentication / reauthentication policy |
| Is fresh consent required? | Authorization Code Flow / provider policy |
| Does the token have permission to read/modify orders? | Scope/audience and Resource Server authorization |
| Does the user still belong to the tenant? | Business authorization / membership |

If the OP requires interactive user action again, the refresh token grant cannot "force" the user past that requirement.

## 20. Refresh Token vs. ID Token vs. Login Session

An OIDC ID Token authenticates the user to the client at a point in time and is validated per OIDC rules at login. When an access token refreshes successfully:

- It does not prove the user reauthenticated.
- It does not automatically replace the Session/Authentication in the Portal.
- It does not automatically refresh all claims inside `OidcUser`.
- It does not automatically update `auth_time` or satisfy `max_age` for a fresh login policy.

And when the user logs out of the Portal:

- The WebFlux SecurityContext/session ends per configuration.
- Access tokens or refresh tokens may still be valid on the Authorization Server if not revoked.
- The authorized client record in persistent storage may remain depending on cleanup policy.

If the application requires revoking refresh tokens on logout, implement proper cleanup/revocation and OP logout—do not expect the refresh provider to revoke tokens by itself.

## 21. Securing Refresh Tokens in a Reactive Backend

**A refresh token is a sensitive credential**; follow at least these principles:

1. Use HTTPS/TLS when calling the token endpoint; verify certificates and hostnames.
2. Never send refresh tokens to the browser in a BFF/server-side architecture.
3. Never write refresh tokens, access tokens, client secrets, authorization codes, or raw token responses to logs.
4. Never store refresh tokens in widely readable caches, logs, or traces.
5. Protect the authorized-client store: encryption, access control, retention, and backups per policy.
6. Bind tokens to the exact registration/principal; never accept `?principalName=admin` from the browser to load another user's token.
7. Evaluate refresh token rotation, revocation, device/session binding, and token theft risks per provider.
8. Enforce timeouts, concurrency limits, bounded retries, and rate limits when calling the token endpoint.
9. Revoke or purge tokens when a user/account is disabled per policy; do not wait for the refresh provider to infer administrative actions.
10. Use the client authentication method registered with the OP; never place client secrets in URL query parameters.

### 21.1. Safe logging

Instead of:

~~~text
refresh_token=real-secret-value
access_token=real-bearer-value
client_secret=real-client-secret
~~~

log in a controlled format:

~~~text
event=oauth_refresh_failed
registration=company
error=invalid_grant
duration_ms=...
correlation_id=...
~~~

Do not log full usernames/emails or raw JWTs. Auditing and tracing must follow personal data minimization principles.

## 22. Observing the Refresh Token Provider in Operations

Useful metrics:

| Metric / event | Meaning |
|---|---|
| Refresh attempted | How often the provider decided to send a refresh request |
| Refresh success/failure | Grant success rate |
| Token endpoint latency | Authorization Server / back-channel latency |
| `invalid_grant` | Signal that a refresh token is no longer usable |
| `invalid_client` | Incorrect client configuration/secret/mTLS |
| HTTP 429/503 | Rate limiting or provider outage |
| Concurrent refresh conflict | Risk of RT rotation reuse |
| Token `expiresAt`/skew | Whether refreshes happen too early or too late |
| Authorized client load/save failure | Persistence error |
| API 401 `invalid_token` | Token rejected by Resource Server after issuance |

Do not infer "refresh success" merely because a `Mono` was created. Observe that **the token response actually completed and the authorized client was saved**.

In logs, exclude `tokenValue`, client secrets, or personal claims unnecessary for computing metrics.

## 23. Testing `RefreshTokenReactiveOAuth2AuthorizedClientProvider`

Tests should verify the provider's **decision rules** without hitting a production Authorization Server:

1. Authorized client and RT exist, AT expired → calls token client and returns new authorized client.
2. AT valid outside clock skew → does not call token endpoint.
3. No refresh token → does not send token request.
4. Token endpoint returns `invalid_grant` → emits Mono error.
5. Token response rotates RT → new authorized client holds the new RT.
6. Token response omits new RT → authorized client handles RT per library/provider rules.
7. Two concurrent requests → test application and store behavior; do not expect the provider to hold a global lock.

### 23.1. Minimal unit test with `StepVerifier`

A Java/JUnit 5 example stubbing the refresh response and verifying the provider emits a new authorized client:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.TestingAuthenticationToken;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.RefreshTokenReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.endpoint.OAuth2RefreshTokenGrantRequest;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AccessTokenResponse;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveRefreshProviderTest {

    @Test
    void expiredTokenWithRefreshTokenProducesNewAuthorizedClient() {
        ClientRegistration registration =
            ClientRegistration.withRegistrationId("company")
                .clientId("test-client")
                .clientSecret("test-secret")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationUri(
                    "https://login.example.test/oauth2/authorize")
                .tokenUri("https://login.example.test/oauth2/token")
                .redirectUri(
                    "{baseUrl}/login/oauth2/code/{registrationId}")
                .build();

        Instant now = Instant.now();

        OAuth2AccessToken oldAccess = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "test-old-access",
            now.minusSeconds(600),
            now.minusSeconds(60),
            Set.of("orders.read")
        );

        OAuth2RefreshToken oldRefresh = new OAuth2RefreshToken(
            "test-old-refresh",
            now.minusSeconds(600)
        );

        OAuth2AuthorizedClient oldClient =
            new OAuth2AuthorizedClient(
                registration,
                "employee-42",
                oldAccess,
                oldRefresh
            );

        OAuth2AuthorizationContext context =
            OAuth2AuthorizationContext.withAuthorizedClient(oldClient)
                .principal(new TestingAuthenticationToken(
                    "employee-42", "ignored", "ROLE_USER"))
                .build();

        ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
            fakeTokenClient = request -> Mono.just(
                OAuth2AccessTokenResponse
                    .withToken("test-new-access")
                    .tokenType(OAuth2AccessToken.TokenType.BEARER)
                    .expiresIn(300)
                    .refreshToken("test-new-refresh")
                    .scopes(Set.of("orders.read"))
                    .build()
            );

        RefreshTokenReactiveOAuth2AuthorizedClientProvider provider =
            new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        provider.setClockSkew(Duration.ofSeconds(60));
        provider.setAccessTokenResponseClient(fakeTokenClient);

        StepVerifier.create(provider.authorize(context))
            .assertNext(refreshed -> {
                org.junit.jupiter.api.Assertions.assertEquals(
                    "test-new-access",
                    refreshed.getAccessToken().getTokenValue()
                );
                org.junit.jupiter.api.Assertions.assertEquals(
                    "test-new-refresh",
                    refreshed.getRefreshToken().getTokenValue()
                );
                org.junit.jupiter.api.Assertions.assertEquals(
                    "employee-42",
                    refreshed.getPrincipalName()
                );
            })
            .verifyComplete();
    }
}
~~~

This example only tests **provider logic**. It is **not an OIDC login integration test**, and does not verify ID Token signatures, callback state, or a real token endpoint. All token strings are dummy test fixtures, not production credentials.

### 23.2. Testing `Mono.empty()`

When the access token still has plenty of time left and an RT is present:

~~~java
// Use a fixture with an access token valid for > clockSkew.
StepVerifier.create(provider.authorize(contextWithFreshToken))
    .verifyComplete();
~~~

A thorough test should assert that the fake token response client **was never called**. With Mockito, use `verifyNoInteractions(tokenClient)`; with a hand-written fake, use a thread-safe counter. `contextWithFreshToken` is a test fixture, not a pre-existing variable.

If the refresh token is null, behavior is similar: the provider has no valid grant to execute and typically returns `Mono.empty()`.

### 23.3. Testing token endpoint errors

The token response client can return:

~~~java
return Mono.error(new RuntimeException(
    "Simulated token endpoint failure"));
~~~

Then:

~~~java
StepVerifier.create(provider.authorize(expiredContext))
    .expectError()
    .verify();
~~~

This only mocks a technical failure. When testing OAuth2 `invalid_grant`, simulate the exact exception/error code handled by Spring Security, and verify whether the manager's failure handler and repository remove the authorized client per policy.

## 24. Comparison with the Servlet Refresh Token Provider

In a Spring MVC/Servlet application, the corresponding class is:

~~~java
org.springframework.security.oauth2.client
    .RefreshTokenOAuth2AuthorizedClientProvider
~~~

And in WebFlux/Reactive:

~~~java
org.springframework.security.oauth2.client
    .RefreshTokenReactiveOAuth2AuthorizedClientProvider
~~~

| Criterion | Servlet | Reactive |
|---|---|---|
| Provider | `RefreshTokenOAuth2AuthorizedClientProvider` | `RefreshTokenReactiveOAuth2AuthorizedClientProvider` |
| Interface | `OAuth2AuthorizedClientProvider` | `ReactiveOAuth2AuthorizedClientProvider` |
| Authorize result | Authorized client or null per synchronous contract | `Mono<OAuth2AuthorizedClient>` or empty/error |
| Token-response client | `OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>` | `ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>` |
| Typical HTTP engine | `RestClient` or `RestOperations` depending on version | `WebClient` |
| Authorized client manager | `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| Web application stack | `HttpSecurity / SecurityFilterChain` | `ServerHttpSecurity / SecurityWebFilterChain` |
| What to avoid | Blocking indefinitely on request-handling threads | Calling `block()` on the event loop |

**You cannot inject a Servlet provider into a Reactive manager** by renaming a variable. They have different interfaces and execution semantics. If Spring Boot uses WebFlux, choose reactive providers and reactive client repositories.

## 25. Troubleshooting by Symptom

| Symptom | Possible cause | How to isolate |
|---|---|---|
| Token expired, yet no HTTP refresh occurs | Manager/provider chain omits refresh provider, or manager is never called | Inspect `ReactiveOAuth2AuthorizedClientProviderBuilder` config and HTTP client integration |
| Provider returns `Mono.empty()` | No authorized client, no RT, or AT not yet due for refresh | Inspect metadata; do not treat this as a user session error |
| `invalid_grant` on refresh | RT expired/revoked/reused, or rotation race | Check OP policy and store concurrency |
| `invalid_client` | Wrong client secret or authentication method | Check runtime secrets, mTLS, registration |
| Refresh succeeds, yet next request uses old AT | Updated authorized client was not saved or loaded from wrong store | Check manager save handler, repository/service, and principal key |
| Repeated refreshes back-to-back | Clock skew too large, wrong `expiresAt`, or store not updating | Check expiry, time sync, refresh latency, and cache |
| Reactive HTTP handler stalls | `.block()` or blocking HTTP client on the event loop | Inspect Reactor stack traces and remove blocking |
| Refresh fails only when scaling out | RT rotation race or unshared store | Check multi-instance persistence and concurrency |
| OIDC login succeeds, yet no refresh token | OP/client policy does not issue RT | Check grant, consent, and provider policy |
| Portal stays logged in, yet Orders API returns 401 | Token expired/revoked/wrong audience, or manager did not refresh | Distinguish Authentication from authorized client |
| API returns 403 after refresh | Insufficient scopes or resource permissions | Check Resource Server policy; do not expect refresh to escalate scopes |
| `WebClient` calling API does not auto-refresh | Filter lacks the right manager or registration ID | Check `ServerOAuth2AuthorizedClientExchangeFilterFunction` |
| Background job complains of missing `ServerWebExchange` | Using web manager outside an HTTP request | Use a service-based reactive manager |
| Changing API `WebClient` doesn't affect token endpoint timeout | Token `WebClient` is a separate instance | Customize the token-response client's `WebClient` |
| Logging out of Portal leaves RT behind | Local logout does not automatically revoke tokens | Design token cleanup/revocation policy |

Do not modify multiple layers at once. First determine whether the error belongs to **WebFlux request/session**, **authorized-client manager/provider**, **token endpoint**, **repository**, or **Resource Server**.

## 26. Common Misconceptions

**"The refresh provider automatically refreshes tokens every 5 minutes."** No. It is invoked during authorization flows when a consumer/manager needs a token; it is not a scheduler.

**"Having a refresh token means the user is always logged in."** No. A refresh token is neither a web session cookie nor an `Authentication`.

**"`Mono.empty()` means refresh failed."** No. Providers normally emit empty when the grant does not apply.

**"The reactive provider automatically stores tokens in Redis."** No. The manager/repository/service handles persistence.

**"WebFlux includes `WebClient`, so tokens auto-refresh."** No. `WebClient` must integrate the appropriate OAuth2 manager/filter.

**"If refresh returns a new access token, `OidcUser` claims update too."** Not by default; profile updates and reauthentication require separate handling.

**"As long as AT hasn't expired, the API will accept it."** No. The API also checks audience, scopes, revocation, and resource permissions.

**"Larger clock skew is always safer."** No. Too large a skew causes premature refreshes and increases contention across concurrent requests.

**"On `invalid_grant`, just retry the same old RT."** Dangerous when rotation or reuse detection is enabled.

**"If there's no refresh token, construct one from the ID Token."** Invalid; tokens must be issued by the Authorization Server.

**"Reactive never has race conditions."** False. Concurrent requests and multi-node stores still require synchronization.

## 27. Practice Exercises

### Exercise 1 — Access token not yet due for refresh

~~~text
expiresAt = 10:10:00Z
now       = 10:08:00Z
clockSkew = 60 seconds
RT        = present
~~~

**Question:** Should the provider refresh immediately?

**Solution:** Not yet. The token still has 120 seconds left, which is greater than the 60-second clock skew. The provider typically returns `Mono.empty()` when queried in this context.

### Exercise 2 — Token nearing expiration

~~~text
expiresAt = 10:10:00Z
now       = 10:09:30Z
clockSkew = 60 seconds
RT        = present
~~~

**Question:** Why can the provider refresh before 10:10?

**Solution:** The token has 30 seconds remaining, falling within the 60-second skew window; refreshing early avoids the token expiring in transit over the network.

### Exercise 3 — No refresh token

~~~text
authorizedClient.accessToken = expired
authorizedClient.refreshToken = null
~~~

**Question:** What does the provider do?

**Solution:** It cannot use the `refresh_token` grant and typically returns `Mono.empty()`. Obtaining a new token requires an appropriate grant/authorization flow permitted for the client.

### Exercise 4 — WebFlux handler calling `block()`

~~~java
OAuth2AuthorizedClient client =
    manager.authorize(request).block();
~~~

**Question:** What is wrong here?

**Solution:** Blocking on a reactive event loop violates the execution model and can cause runtime errors or degrade throughput. Return a `Mono`, compose with `flatMap`, and let the framework subscribe.

### Exercise 5 — Concurrent refresh token rotation

Two requests both load RT-1 and send two refresh requests. The OP returns RT-2 to the first request and `invalid_grant` to the second.

**Question:** Will simply adding `retry(3)` solve this?

**Solution:** No. RT-1 has already been consumed; retrying may worsen reuse-detection penalties. You need concurrency control, a consistent token store, and handling for the latest token generation.

### Exercise 6 — `WebClient` not using the custom manager

A manager with a refresh provider was configured, yet the API call code uses:

~~~java
WebClient.create("https://orders.example.test")
    .get()
    .uri("/api/orders")
    .retrieve()
    .bodyToMono(String.class);
~~~

**Question:** Why doesn't the token auto-refresh?

**Solution:** This `WebClient` lacks an OAuth2 exchange filter wired to the right manager. Build the `WebClient` with `ServerOAuth2AuthorizedClientExchangeFilterFunction` and supply the registration ID and principal context.

### Exercise 7 — Refresh succeeds, API returns 403

AT-2 is valid, yet the API requires `orders.write` while the token only has `orders.read`.

**Question:** Should you immediately refresh again?

**Solution:** Never treat refresh as privilege escalation. Request the proper permissions/scopes and check the Resource Server's policy.

## 28. Reactive Refresh Token Integration Checklist

| Question | What to ensure |
|---|---|
| Is the application truly WebFlux? | `SecurityWebFilterChain`, `ServerHttpSecurity`, reactive repositories |
| Is `ClientRegistration` valid? | Correct grant, issuer/token endpoint, scopes, and client authentication |
| Does the authorized client have a refresh token? | Never assume it does; inspect actual data |
| Does the provider chain include `refreshToken()`? | Present when the app needs the Refresh Token Grant |
| Is clock skew reasonable? | Not excessive; time sync and latency accounted for |
| Which token response client is used? | Appropriate `WebClientReactiveRefreshTokenTokenResponseClient` |
| Is the token HTTP transport configured? | HTTPS, timeouts, egress proxy, TLS trust/mTLS |
| Does the API `WebClient` use the right manager? | `ServerOAuth2AuthorizedClientExchangeFilterFunction` and registration ID |
| Is the web context complete? | Authenticated principal and `ServerWebExchange` when needed |
| Which manager do background tasks use? | Service-based reactive manager, independent of HTTP requests |
| How are `invalid_grant` errors handled? | Failure handler/cleanup and reauthorization policy |
| Is there an RT rotation concurrency policy? | Consistent store and locking/versioning if required |
| Are refresh responses persisted? | Manager/repository/service saves the updated authorized client |
| Does refresh log the user in automatically? | No; Authentication/session is managed separately |
| Do logs leak tokens or secrets? | Never write `tokenValue`, refresh tokens, or secrets to logs |
| Are empty/success/error paths tested? | `StepVerifier`, fake token response client, store integration tests |

## 29. Summary

`RefreshTokenReactiveOAuth2AuthorizedClientProvider` is the **Refresh Token Grant provider for Spring Security Reactive**. It inspects the current authorized client, refresh token, and access token expiration (accounting for clock skew), and when appropriate uses **`ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>`** to call the token endpoint. Results are represented as **`Mono<OAuth2AuthorizedClient>`**; when conditions are not met, the provider typically returns **`Mono.empty()`**.

In WebFlux, the provider is properly used through **`ReactiveOAuth2AuthorizedClientManager`** and an authorized-client repository/service. For web requests, `DefaultReactiveOAuth2AuthorizedClientManager` coordinates with the WebFlux context; for background tasks without a request, `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` is the better fit. The HTTP client calling a Resource Server must use that manager via **`ServerOAuth2AuthorizedClientExchangeFilterFunction`** or equivalent integration; merely declaring a provider bean does not make every `WebClient` refresh automatically.

Finally, **a refresh token is not an HTTP session, not an ID Token, and does not grant new permissions on its own**. Design clock skew, the token-response client, saving updated tokens, `invalid_grant` handling, refresh token rotation, concurrency, and security boundaries explicitly. That forms the foundation for reliable API calls while preserving the non-blocking, login, and authorization model of Spring Security WebFlux.
