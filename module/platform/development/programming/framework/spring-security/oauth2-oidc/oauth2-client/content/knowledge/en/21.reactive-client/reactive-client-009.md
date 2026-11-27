# 21.9. `ServerOAuth2AuthorizedClientExchangeFilterFunction` in `WebClient`

In **Spring Security OAuth 2.0/OIDC Client on the Reactive stack (Spring WebFlux)**, an application does more than sign users in via OpenID Connect—it can also call downstream APIs using access tokens issued by an Authorization Server. To integrate Spring Security's **OAuth2 Authorized Client** infrastructure with the `WebClient` HTTP client, Spring provides **`ServerOAuth2AuthorizedClientExchangeFilterFunction`**.

This class is an `ExchangeFilterFunction`: it participates in WebClient's outbound HTTP request chain, finds or requests an appropriate **`OAuth2AuthorizedClient`**, and attaches the **access token** to the `Authorization: Bearer ...` header when sending the request. When the manager and grants allow, acquiring or refreshing access tokens is handled by the OAuth2 Client infrastructure without each service calling the Token Endpoint manually.

The tricky part of this topic boils down to four questions: **whose token**, **which ClientRegistration**, **which API it is sent to**, and **what to do when the token expires or the API rejects it**. On the Reactive stack, add a fifth question: **are Authentication and ServerWebExchange properly propagated through Reactor context?**

This lesson explains how to configure the filter class, select authorized clients explicitly, use it alongside `WebClient` and `ServerHttpSecurity`, handle refreshes and HTTP 401/403 responses, prevent leaking Bearer tokens, and distinguish user HTTP requests from scheduled jobs running outside requests.

## 1. Real-World Problem: WebFlux Calling an API After OIDC Login

Suppose a WebFlux portal provides a reporting dashboard:

1. A user visits `/dashboard`.
2. Spring Security performs OIDC Login with an OpenID Provider.
3. The Authorization Code Flow completes: Spring receives and validates the ID Token, creating an `OidcUser`.
4. The app stores the `Authentication` state and the token-bearing `OAuth2AuthorizedClient`.
5. A controller/service calls `https://reports-api.example.test/v1/reports`.
6. The Reports API requires an **access token** with scope `reports.read` and the right audience.

The HTTP request to the Reports API must look like:

```http
GET /v1/reports HTTP/1.1
Host: reports-api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
Accept: application/json
```

If each controller manually fetches tokens from a session map and attaches headers, the app easily falls into bugs:

- Picking the wrong user's token.
- Sending an OIDC ID Token instead of an access token.
- Sending API A's access token to API B.
- Failing to check whether the token has expired.
- Missing refresh token rotation and storage updates.
- Retrying infinitely when the API returns `401 invalid_token` or `403 insufficient_scope`.
- Reading Servlet-style `SecurityContextHolder` in WebFlux even though Reactive security context is not managed via ThreadLocal the same way.

`ServerOAuth2AuthorizedClientExchangeFilterFunction` standardizes **OAuth2 token selection/attachment** on WebClient. It does not replace **business authorization**, does not guarantee every API accepts every token, and cannot turn an unconsented request into a valid OIDC session just by adding a filter.

## 2. High-Level Architecture Model

```mermaid
flowchart LR
    Browser["Browser / User"] --> Web["Spring WebFlux endpoint"]
    Web --> Security["Reactive SecurityContext"]
    Web --> Client["WebClient"]
    Client --> Filter["ServerOAuth2AuthorizedClientExchangeFilterFunction"]
    Filter --> Manager["ReactiveOAuth2AuthorizedClientManager"]
    Manager --> Registrations["ReactiveClientRegistrationRepository"]
    Manager --> Storage["ServerOAuth2AuthorizedClientRepository / Service"]
    Manager --> Token["Authorization Server / Token Endpoint"]
    Filter --> API["Resource Server / Reports API"]
    API --> Client
```

A specific request:

```mermaid
sequenceDiagram
    autonumber
    actor User as User
    participant Portal as WebFlux Portal
    participant Filter as OAuth2 WebClient Filter
    participant Manager as Reactive Client Manager
    participant Store as Authorized Client Store
    participant AS as Authorization Server
    participant API as Reports API

    User->>Portal: GET /reports
    Portal->>Filter: WebClient GET /v1/reports
    Note over Portal,Filter: attributes(clientRegistrationId("company"))
    Filter->>Manager: authorize(registration + principal)
    Manager->>Store: Look up authorized client
    alt Token still usable per policy
        Store-->>Manager: OAuth2AuthorizedClient
    else Needs new or refreshed token and grant permits
        Manager->>AS: Token Endpoint request
        AS-->>Manager: New access token (+ new refresh token?)
        Manager->>Store: Update authorized client
    end
    Manager-->>Filter: OAuth2AuthorizedClient
    Filter->>API: Authorization: Bearer access_token
    API-->>Filter: HTTP response
    Filter-->>Portal: Mono/ClientResponse
    Portal-->>User: Report data or appropriate error
```

The diagram is a **generalized model**: the manager/provider may return an existing authorized client without calling the Token Endpoint, or fail to authorize if no matching grant exists. Do not conclude every WebClient request acquires a brand-new access token.

## 3. Distinguishing OAuth2 Login, OAuth2 Client, and Resource Server

A WebFlux application can use three distinct Spring Security capabilities:

| Capability | Purpose | Typical components |
|---|---|---|
| **`oauth2Login`** | Users sign into the portal via OP/OIDC | `ServerHttpSecurity.oauth2Login`, `OidcUser` |
| **`oauth2Client`** | App acquires/manages tokens to call APIs on behalf of users or the Client itself | `ReactiveOAuth2AuthorizedClientManager`, WebClient OAuth2 filter |
| **`oauth2ResourceServer`** | The app itself acts as an API and validates Bearer tokens from callers | `oauth2ResourceServer().jwt()` or opaque token |

In this lesson, the WebFlux portal acts as an **OAuth2 Client** when calling the Reports API. The Reports API is the **Resource Server**.

A successful OIDC login does not mean the issued access token **has permission to call every API**. The token must be issued for the right resource/audience, the right scopes, and be accepted by the Resource Server.

### 3.1. Access Token vs ID Token

- **ID Token**: JWT issued by the OpenID Provider so the Client can verify the user's identity.
- **Access token**: credential used to call APIs per granted permissions.
- **Refresh token**: credential used to request new access tokens at the Token Endpoint if issued.

The WebClient OAuth2 filter puts the **access token** in the `Authorization` header. Never put `OidcUser#getIdToken().getTokenValue()` there.

### 3.2. What Is `OAuth2AuthorizedClient`?

`OAuth2AuthorizedClient` brings together:

```text
OAuth2AuthorizedClient
  ├─ ClientRegistration
  │    ├─ registrationId
  │    ├─ clientId
  │    └─ authorizationGrantType / provider metadata
  ├─ principalName
  ├─ OAuth2AccessToken
  │    ├─ tokenValue
  │    ├─ issuedAt / expiresAt
  │    └─ scopes
  └─ OAuth2RefreshToken? (nullable)
```

**`ClientRegistration` is configuration.** **`OAuth2AuthorizedClient` is the token-bearing result**, bound to a principal. They are not interchangeable.

## 4. Related Reactive Components

| API / Class | Role |
|---|---|
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | WebClient filter to resolve tokens, attach Bearer headers, and optionally handle OAuth2 errors |
| `ReactiveClientRegistrationRepository` | Stores Client registration configurations |
| `ClientRegistration` | An OAuth2 Client registered with an Authorization Server |
| `ServerOAuth2AuthorizedClientRepository` | Saves/loads authorized clients in a `ServerWebExchange` context |
| `ReactiveOAuth2AuthorizedClientService` | Saves/loads authorized clients via reactive API without tying to HTTP exchanges |
| `ReactiveOAuth2AuthorizedClientManager` | Coordinates authorization/reauthorization |
| `DefaultReactiveOAuth2AuthorizedClientManager` | Common manager for reactive web requests |
| `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | Service-based manager for tasks outside `ServerWebExchange` |
| `ReactiveOAuth2AuthorizedClientProvider` | Provider handling grants such as authorization code, refresh token, client credentials |
| `ReactiveOAuth2AuthorizedClientProviderBuilder` | Builds a composite of grant providers |
| `OAuth2AuthorizeRequest` | Carries registration/principal/context for an authorization attempt |
| Reactive `OAuth2AuthorizationFailureHandler` | Handles authorization failures and can remove bad tokens |
| `ServerWebExchange` | Spring WebFlux HTTP exchange context |
| `ReactiveSecurityContextHolder` | Accesses `SecurityContext` via Reactor context |

Interface/class names closely resemble the Servlet stack, yet they **do not share the same contract**. For instance, `OAuth2AuthorizedClientManager` (Servlet) and `ReactiveOAuth2AuthorizedClientManager` cannot be swapped directly.

## 5. How Does `ServerOAuth2AuthorizedClientExchangeFilterFunction` Work?

Inside the WebClient processing chain:

```text
service/controller builds ClientRequest
    ↓
WebClient ExchangeFilterFunction chain
    ↓
ServerOAuth2AuthorizedClientExchangeFilterFunction
    ├─ Determine which authorized client to use
    ├─ Explicit client provided?
    ├─ If by registration: resolve principal and ask manager to authorize
    ├─ Extract matching access token
    └─ Add Authorization: Bearer <token> to outbound request
    ↓
HTTP connector
    ↓
Resource Server
    ↓
ClientResponse / Mono / Flux
```

Common ways to select the client:

1. Pass an **explicit `OAuth2AuthorizedClient`** in the WebClient request's attributes.
2. Pass **`clientRegistrationId`** so the filter/manager resolves the authorized client for the principal.
3. Enable the **default authorized client** policy only if genuinely needed and risks are understood.
4. Enable a **default registration ID** for a dedicated WebClient with a fixed, controlled host.

In most multi-integration applications, **explicit per-request selection** keeps code clear and minimizes accidental credential leakage.

## 6. Dependencies for a Spring Boot WebFlux OAuth2 Client

Compatible Spring Boot 3.x example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>
</dependencies>
```

Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
}
```

Spring Boot manages compatible versions through its BOM. Never mix incompatible Spring Security/Core/WebFlux branches manually.

**Note:** If both `spring-boot-starter-web` and `webflux` are present, auto-configuration normally favors a Servlet application by default. This lesson assumes the server runs **Reactive WebFlux**, using `SecurityWebFilterChain` and `ServerHttpSecurity`. In a Spring MVC app that merely uses WebClient as an HTTP client, the corresponding class is usually `ServletOAuth2AuthorizedClientExchangeFilterFunction`.

## 7. Configuring an OIDC Client for User Login and API Calls

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-op
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
          company-op:
            issuer-uri: https://login.example.test/realms/company
```

Explanation:

- `company` is the **registration ID** referenced in Java.
- `openid` requests OIDC Login.
- `reports.read` is an illustrative API scope; the issuer and Reports API must actually support it.
- `issuer-uri` discovers OIDC metadata, Token Endpoint, and JWKS when the provider supports discovery.
- `redirect-uri` is the **Authorization Code Flow** callback, not a downstream API path.
- `client-secret` must come from a secret manager, environment variable, or equivalent mechanism.

The `example.test` domain and credentials are placeholders; illustrative snippets cannot sign into a real IdP unchanged.

### 7.1. Do Not Assume the OIDC Login Token Has Reports API Permissions

An IdP may issue an access token only for the UserInfo Endpoint, or the Reports API may require a different audience/resource indicator. Therefore check:

- Which issuer does the Reports API accept?
- Which audience was the token issued for?
- Was the `reports.read` scope actually granted?
- If the provider issues resource-specific access tokens, did the Client request the right resource?
- Has the user or application been granted consent/policy approval?

Successfully attaching a Bearer header does not prove the API will return 200.

## 8. Configuring Reactive Security

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/error").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
```

Configuration:

- `oauth2Login` lets users sign in via OAuth2/OIDC.
- `oauth2Client` activates OAuth2 Client support per Spring Security Reactive configuration.
- `authorizeExchange` guards endpoints by authentication; business authorization rules still need to be designed separately.

`SecurityWebFilterChain` is the WebFlux class. Do not use Servlet's `HttpSecurity`/`SecurityFilterChain` here.

### 8.1. Where Does OIDC Authentication Happen?

Spring Security handles the authorization request, callback, token exchange, ID Token validation, and building `OidcUser`. This lesson's WebClient filter runs **after/independently of user verification**, whenever the backend makes an outbound HTTP call.

Never manually Base64-decode an ID Token and inject arbitrary claims into `OAuth2AuthorizeRequest` as proof of user login.

## 9. Creating WebClient with the Repositories Constructor

A common configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration
    .ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server
    .ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsWebClientConfiguration {

    @Bean("reportsWebClient")
    WebClient reportsWebClient(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        var oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                registrations,
                authorizedClients
            );

        return WebClient.builder()
            .baseUrl("https://reports-api.example.test")
            .filter(oauth2)
            .build();
    }
}
```

Long imports above are wrapped for readability. In a real Java file, each import must be a valid single-line statement:

```java
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
```

**You only need one `reportsWebClient` bean** for this approach; other configurations in this lesson are alternatives, not snippets to paste into the same class.

### 9.1. Where Is the Filter Registered?

`WebClient.Builder#filter(...)` adds an `ExchangeFilterFunction` to the request pipeline:

```java
WebClient.builder()
    .filter(oauth2)
    .build();
```

There is no `.apply(oauth2.oauth2Configuration())` call like in the **Servlet** variant. With Reactive `ServerOAuth2AuthorizedClientExchangeFilterFunction`, `.filter(oauth2)` is the direct, explicit integration.

### 9.2. What Does the Repositories Constructor Mean?

This constructor takes:

```java
ServerOAuth2AuthorizedClientExchangeFilterFunction(
    ReactiveClientRegistrationRepository clientRegistrations,
    ServerOAuth2AuthorizedClientRepository authorizedClients
)
```

It uses infrastructure suited to **Reactive web requests**, managing authorized clients per `ServerWebExchange`/principal. In modern Spring Security versions, constructing from repositories also wires a default failure handler when the Resource Server reports certain OAuth2 errors. Details on constructor/failure behavior are covered in the error-handling section.

## 10. Explicitly Selecting `clientRegistrationId` When Calling an API

Basic invocation:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> reports = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
```

`clientRegistrationId("company")` is a static helper returning a `Consumer<Map<String, Object>>` for WebClient request attributes. The filter reads this attribute to know which `ClientRegistration` is desired.

### 10.1. Why Specify the Registration on Every Request?

One user may connect multiple external APIs:

```text
Reactive Authentication = user-782

Authorized Clients:
  company         -> access token for Reports API
  calendar        -> access token for Calendar API
  accounting      -> access token for Billing API
```

If the wrong authorized client is chosen:

- Reports API may return 401 due to wrong audience.
- Billing API may return 403 due to missing scope.
- A token may be sent to a third party not authorized to receive it.
- Logs/traces become ambiguous about which Client originated the token.

Therefore, make registration selection explicit right where the outbound request is built.

### 10.2. What If No Authorized Client Exists Yet?

For a user's Authorization Code Grant, initial authorization usually requires a browser redirect to the Authorization Server, consent, and callback. The WebClient filter **cannot initiate a new browser interaction on its own from an HTTP call** if no authorization context exists yet.

Tasks sending HTTP requests on behalf of a user must rely on an already-issued `OAuth2AuthorizedClient` or Spring's login/consent flows. If authorization is missing, the application should proactively present a connect/re-authorize UX.

## 11. Passing `OAuth2AuthorizedClient` Explicitly

When an endpoint already holds a trusted authorized client, it can pass it directly:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

Mono<String> fetchReports(
        WebClient reportsWebClient,
        OAuth2AuthorizedClient authorizedClient) {

    return reportsWebClient.get()
        .uri("/v1/reports")
        .attributes(oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class);
}
```

This clearly states: "this request must use the exact authorized client I have already resolved."

### 11.1. `@RegisteredOAuth2AuthorizedClient` on a WebFlux Controller

With proper Spring Security Reactive configuration, a managed authorized client can be injected via annotation:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@RestController
public class ReportsController {

    private final WebClient reportsApi;

    public ReportsController(
            @Qualifier("reportsWebClient") WebClient reportsApi) {
        this.reportsApi = reportsApi;
    }

    @GetMapping("/reports")
    public Mono<String> reports(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient authorizedClient) {

        return reportsApi.get()
            .uri("/v1/reports")
            .attributes(oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(String.class);
    }
}
```

This illustrates dependency injection / argument resolution in Reactive OAuth2 Client. Behavior when no authorized client exists yet, how the manager supports reauthorization, and annotation support should match your exact Spring Security version.

**Never deserialize an `OAuth2AuthorizedClient` from browser-submitted JSON and trust it.** It must come from the application's repository/manager with verified principal ownership.

### 11.2. How Do the Two Selection Approaches Differ?

| Approach | Input | Benefit | Things to remember |
|---|---|---|---|
| `clientRegistrationId("company")` | Registration ID | Filter/manager resolves and authorizes for principal | Needs proper reactive context and supported grant |
| `oauth2AuthorizedClient(client)` | Pre-selected authorized client | Explicit credential attached to request | Must ensure client matches user/API; understand token lifecycle when passing a pre-fetched object |

Do not assume passing an explicit `OAuth2AuthorizedClient` always runs **the exact same reauthorization path** as looking up by registration; check the behavior of your filter/version and where the object originated. When refreshes occur regularly, a properly configured manager should serve as the reliable coordinator.

## 12. Constructor Accepting `ReactiveOAuth2AuthorizedClientManager`

When you want explicit control over providers, refresh handling, or persistence, configure a custom manager.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;

@Configuration
public class ReactiveManagerConfiguration {

    @Bean("webReactiveAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager webAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        var manager = new DefaultReactiveOAuth2AuthorizedClientManager(
            registrations,
            authorizedClients
        );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Then build the WebClient:

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean("reportsWebClient")
WebClient reportsWebClient(
        @Qualifier("webReactiveAuthorizedClientManager")
        ReactiveOAuth2AuthorizedClientManager manager) {

    var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        manager
    );

    return WebClient.builder()
        .baseUrl("https://reports-api.example.test")
        .filter(oauth2)
        .build();
}
```

The two `reportsWebClient` examples in sections 9 and 12 are **alternatives**—do not declare both with the same bean name.

### 12.1. Choosing Providers Explicitly

`ReactiveOAuth2AuthorizedClientProviderBuilder` lets you assemble grant providers, for example:

```java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
```

Enable only grants actually used by your application. Adding `refreshToken()` does not force the provider to issue refresh tokens. Adding `authorizationCode()` does not open a browser inside a scheduled task. Adding `clientCredentials()` does not convert user consent into application permissions.

### 12.2. When Can the Manager Fail to Authorize?

Possible causes:

- `registrationId` does not exist.
- The manager lacks a provider for the registration's grant.
- The user's authorized client has not been granted yet.
- No refresh token exists and the access token has expired.
- The Token Endpoint returns `invalid_client`, `invalid_grant`, or `invalid_scope`.
- Required server context/principal was not supplied.

With `ReactiveOAuth2AuthorizedClientManager#authorize(...)`, the return type is `Mono<OAuth2AuthorizedClient>`; when no supported authorization result is available, the `Mono` may complete empty. Never assume every invocation emits a valid authorized client.

## 13. Selecting Tokens by `Authentication` and `ServerWebExchange`

The Reactive stack uses Reactor context to propagate security information across pipelines, instead of relying on Servlet-style ThreadLocals across async boundaries.

`ServerOAuth2AuthorizedClientExchangeFilterFunction` provides request attributes to supply context when needed:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.authentication;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.serverWebExchange;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
```

Example when a service holds a verified `Authentication` and current `ServerWebExchange`:

```java
public Mono<String> fetchForAuthenticatedUser(
        Authentication userAuthentication,
        ServerWebExchange exchange) {

    return reportsWebClient.get()
        .uri("/v1/reports")
        .attributes(clientRegistrationId("company"))
        .attributes(authentication(userAuthentication))
        .attributes(serverWebExchange(exchange))
        .retrieve()
        .bodyToMono(String.class);
}
```

Required imports:

```java
import org.springframework.security.core.Authentication;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;
```

This illustrates passing **verified** context, not a rule that every request must manually attach all three attributes. In many Spring Security WebFlux flows, `Authentication` is resolved via Reactive SecurityContext and the exchange is supplied automatically by framework integration. Yet when pipelines are constructed and subscribed across different contexts, explicit passing makes code clearer and avoids implicit coupling.

### 13.1. Never Let Callers Arbitrarily Pick Authentication

It is extremely dangerous for an endpoint to read a username from a request and construct an "authenticated" `Authentication` to fetch that user's token.

```java
// NEVER treat a browser-supplied String as proof
// to select another user's token.
String principalName = request.getQueryParams().getFirst("userId");
```

Permission to use a user's `OAuth2AuthorizedClient` must be verified **internally**, based on a genuine session/authentication, account mapping, and ownership.

### 13.2. Reactor Context Does Not Automatically Exist in Every Background Task

A `@Scheduled` job or queue consumer may have no `ServerWebExchange` and no user `SecurityContext`.

- If the job runs with **application permissions**, use `client_credentials` with the service-based reactive manager.
- If the job runs with **user-delegated permissions**, fetch the user's stored authorized client with valid consent/refresh token and verify ownership.
- Never fabricate a fake `ServerWebExchange` to force a session-based repository to work outside a request.

### 13.3. Avoid `block()` to Read Authentication

Do not write:

```java
// Avoid in WebFlux request handling:
Authentication auth =
    ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication())
        .block();
```

Reactive flows should compose `Mono`, `flatMap`, and appropriate operators:

```java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Mono<String> authorizedRequest() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication())
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No authenticated security context")
        ))
        .flatMap(authentication ->
            reportsWebClient.get()
                .uri("/v1/reports")
                .attributes(clientRegistrationId("company"))
                .attributes(
                    ServerOAuth2AuthorizedClientExchangeFilterFunction
                        .authentication(authentication)
                )
                .retrieve()
                .bodyToMono(String.class)
        );
}
```

This method illustrates propagating `Authentication` from Reactor context. In a real application, verify `authentication.isAuthenticated()` and enforce authorization policies before fetching data—do not merely check object presence. When direct `Authentication` inspection is unnecessary, standard attributes/annotations are cleaner.

## 14. Risks of `setDefaultOAuth2AuthorizedClient(true)`

One filter method:

```java
oauth2.setDefaultOAuth2AuthorizedClient(true);
```

lets the filter default to the authorized client bound to the current OAuth2 authentication even when the WebClient request does not specify a registration.

This is convenient for demos, yet **dangerous if enabled on a shared WebClient used across multiple APIs**.

### 14.1. Token Leakage Example

Suppose:

```java
@Bean
WebClient sharedWebClient(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository authorizedClients) {

    var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        registrations, authorizedClients);

    oauth2.setDefaultOAuth2AuthorizedClient(true);

    return WebClient.builder()
        .filter(oauth2)
        .build();
}
```

Then in a service:

```java
sharedWebClient.get()
    .uri("https://unknown-host.example.test/public-data")
    .retrieve()
    .bodyToMono(String.class);
```

If the filter attaches the default access token to an HTTP call targeting another domain, the user's credential can leak. The risk exists even if that API does not require OAuth2.

**Rule:** never enable default authorized clients on a WebClient that can send requests to user-supplied URLs or multiple origins.

### 14.2. `setDefaultClientRegistrationId(...)` Also Needs Strict Scoping

You can configure:

```java
oauth2.setDefaultClientRegistrationId("company");
```

This causes requests lacking an explicit choice to use the `company` registration. If the WebClient strictly targets one fixed Resource Server, a default may be reasonable. Even then, risk arises if the client is later reused for another host.

A tighter design:

```text
reportsWebClient
  baseUrl: https://reports-api.example.test
  OAuth2 registration: company
  only relative routes from a controlled set

calendarWebClient
  baseUrl: https://calendar-api.example.test
  OAuth2 registration: calendar

publicWebClient
  no OAuth2 filter
```

### 14.3. Never Build Arbitrary URLs from Input

Dangerous pattern:

```java
@GetMapping("/proxy")
public Mono<String> proxy(@RequestParam String url) {
    return sharedWebClient.get()
        .uri(url)
        .attributes(clientRegistrationId("company"))
        .retrieve()
        .bodyToMono(String.class);
}
```

A user can direct the backend to an unintended host, causing **SSRF and token exfiltration**. Enforce server-side base URLs/allowlists, fixed routes, and strict control over redirects and cross-origin header forwarding.

Never assume "the HTTP client automatically strips `Authorization` headers on cross-host redirects" without verifying connector/version behavior and redirect policy.

## 15. Handling Expired Access Tokens and Refresh Tokens

Access tokens typically have limited lifetimes, e.g., 30 minutes. An authorized client holds:

```text
accessToken.expiresAt = 11:00 UTC
refreshToken          = RT-1 (if issued by provider)
```

When WebClient calls an API at 10:59:50, the manager/provider can treat the token as nearing expiration and execute the Refresh Token Grant if configured.

```mermaid
flowchart TD
    A["WebClient request with registrationId"] --> B["Manager loads authorized client"]
    B --> C{"Token still valid?"}
    C -->|Yes| D["Attach current access token"]
    C -->|No| E{"Refresh token and provider present?"}
    E -->|Yes| F["POST /token grant_type=refresh_token"]
    F --> G{"Refresh succeeded?"}
    G -->|Yes| H["Save new access/refresh tokens"]
    H --> D
    G -->|No| I["Handle OAuth2 error, possibly reauthorize"]
    E -->|No| J["Cannot refresh with current data alone"]
    D --> K["Call Resource Server"]
```

### 15.1. Why Not Refresh Manually in Every Service?

If controllers manually check `expiresAt` and call the Token Endpoint, code tends to:

- Reuse old refresh tokens after rotation.
- Send two concurrent refresh requests.
- Forget to persist the new refresh token.
- Ignore clock skew policy.
- Loop `invalid_grant` errors indefinitely.
- Drift out of sync across nodes.

Instead, rely on `ReactiveOAuth2AuthorizedClientManager` and `ReactiveOAuth2AuthorizedClientProvider`, paired with appropriate storage and permissions.

### 15.2. Refresh Token Rotation and Concurrent Requests

Two WebClient requests for the same user can simultaneously detect an expiring access token:

```text
Request A reads RT-1 → sends refresh → receives RT-2
Request B also read RT-1 → sends refresh → invalid_grant
```

If the Authorization Server enforces refresh token reuse detection, the entire token family may be revoked. Consider single-flight refreshes, locking/optimistic concurrency, and safely saving the latest client—especially across multiple pods.

`ReactiveOAuth2AuthorizedClientService` backed by a database or Redis does not automatically guarantee only **one** refresh request runs cluster-wide. That synchronization must be designed around your provider and workload.

### 15.3. User Login Session Differs from API Tokens

A user may still have a valid WebFlux `WebSession` and `SecurityContext` while the refresh token for the Calendar API has been revoked. The application can mark the external connection `RECONNECT_REQUIRED` and prompt the user to re-authorize instead of logging them out of the entire portal by default.

This is a business/security decision that should remain decoupled from the filter mechanism.

## 16. Token Endpoint Errors Differ from Resource Server Errors

When using OAuth2 Client, errors arise in at least two places:

1. **Token Endpoint:** the manager/provider acquires or refreshes a token.
2. **Resource Server:** WebClient attaches the Bearer token and sends the API call.

Example:

```text
Token Endpoint:
  400 invalid_grant
    -> refresh token expired/revoked/rotated/wrong Client

Resource Server:
  401 invalid_token
    -> access token rejected

Resource Server:
  403 insufficient_scope
    -> access token lacks required permissions
```

| Error | Origin | Remediation |
|---|---|---|
| `invalid_client` | Token Endpoint | Check Client ID, secret, client authentication method |
| `invalid_grant` | Token Endpoint | Never retry old refresh token infinitely; clean up broken client, reauthorize as needed |
| `invalid_scope` | Token Endpoint | Fix scope/consent/client policy |
| HTTP 401 `invalid_token` | Resource Server | Check expiry, audience, revocation; update token/connection per policy |
| HTTP 403 `insufficient_scope` | Resource Server | Request proper scope/role; do not refresh endlessly with the same scope |
| HTTP 429 | Token Endpoint or API | Bounded backoff/`Retry-After` |
| HTTP 5xx / network timeout | Token Endpoint or API | Policy-driven retry; be cautious with refresh token rotation |

Never assume every `401` is an expired access token, or every `403` is a login failure.

## 17. Filter Failure Handler and the Two Constructors

An important detail of `ServerOAuth2AuthorizedClientExchangeFilterFunction` is that **Resource Server authorization failure handling** can differ depending on how the filter is constructed.

### 17.1. When Using the Repositories Constructor

When building the filter via:

```java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveClientRegistrationRepository,
    serverOAuth2AuthorizedClientRepository
);
```

Spring Security configures a default failure handler that translates matching OAuth2 errors (typically from HTTP 401/403 responses carrying `WWW-Authenticate` Bearer errors) into removing the unusable authorized client.

### 17.2. When Using the Manager Constructor

When building the filter via:

```java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveOAuth2AuthorizedClientManager
);
```

**It does not install the same default authorization failure handler as the repositories constructor.** If you want rejected clients removed/invalidated on Resource Server `invalid_token`, check the API and attach a suitable handler:

```java
oauth2.setAuthorizationFailureHandler(
    yourReactiveAuthorizationFailureHandler
);
```

`yourReactiveAuthorizationFailureHandler` is just a placeholder. In real code, supply a `ReactiveOAuth2AuthorizationFailureHandler` implementation matched to the repository/service managing tokens, scoping removal strictly to the right registration/principal.

### 17.3. Manager Failure Handler vs Filter Failure Handler

Distinguish:

- **Manager failure handler:** handles errors during authorize/refresh at the Token Endpoint, such as `invalid_grant`.
- **WebClient filter failure handler:** handles OAuth2 errors returned by a Resource Server after an outbound API request.

Never replace the manager's handler with a custom logger that accidentally drops `invalid_grant` cleanup. Conversely, never let the WebClient filter delete a valid refresh token on every HTTP 403 insufficient-scope error.

### 17.4. Never Unconditionally Delete Tokens on 401/403

You may receive:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Which differs from:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

On `invalid_token`, discarding the stale access token makes sense in many cases. On `insufficient_scope`, deleting the authorized client usually will not grant extra permissions. Base handler policies on **OAuth2 error codes**, error source, and security requirements.

Never infinitely replay a side-effecting POST/PUT merely because the handler just removed the old token; business retries require separate idempotency.

## 18. `retrieve()`, `exchangeToMono()`, and Error Handling

`WebClient` provides reactive responses:

```java
Mono<String> response = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
```

By default, `retrieve()` turns HTTP 4xx/5xx responses into appropriate exceptions when consumed. You can map domain errors:

```java
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;

Mono<String> reports = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class)
    .onErrorResume(WebClientResponseException.Unauthorized.class, ex ->
        Mono.error(new IllegalStateException(
            "Reports API did not accept the access token"
        ))
    );
```

This shows an error-mapping pattern, not a full production error policy. Never forward raw `WWW-Authenticate` headers containing unexpected details or full upstream response bodies to the frontend.

Another option is inspecting status codes in `exchangeToMono(...)`:

```java
Mono<String> reports = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .exchangeToMono(response -> {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(String.class);
        }
        if (response.statusCode().value() == 403) {
            return Mono.error(
                new IllegalStateException("Reports access denied")
            );
        }
        return response.createException().flatMap(Mono::error);
    });
```

With reactive HTTP clients, ensure response bodies are always consumed/released per Spring's lifecycle rules; `exchangeToMono` manages the body lifecycle of the returned publisher.

### 18.1. Preserve Necessary Authorization Failure Signals

If an HTTP filter handles Bearer errors to evict bad tokens, yet application code prematurely rewrites every 401/403 before the filter observes the response, failure handling may miss required signals. Understand your WebClient filter chain ordering and your Spring version's API behavior.

### 18.2. Timeouts in WebClient

```java
import java.time.Duration;

Mono<String> reports = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class)
    .timeout(Duration.ofSeconds(8));
```

`timeout` bounds waiting on the reactive chain; it does not replace connect/response timeouts on the underlying HTTP connector. Never call `.block(Duration...)` on a Netty event loop.

With rotating Token Endpoint refreshes, timeouts carry an extra risk: the Authorization Server may already have consumed the refresh token before the response reached the Client. Never retry the same refresh token infinitely when you do not know whether the previous attempt succeeded.

## 19. WebClient Running Outside an HTTP Request: Service-to-Service

A scheduled job or queue consumer has no user `ServerWebExchange`. In that environment, the appropriate setup is normally:

- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.
- `ReactiveOAuth2AuthorizedClientService`.
- `client_credentials` for workloads acting on behalf of the application itself.
- A **stable** service principal name for saving/loading the authorized client.

### 19.1. Configuring a Service-Based Manager

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class ServiceOAuth2ClientConfiguration {

    @Bean("serviceReactiveAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager serviceClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

### 19.2. YAML for `client_credentials`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-service:
            provider: reporting-as
            client-id: ${REPORTING_SERVICE_CLIENT_ID}
            client-secret: ${REPORTING_SERVICE_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [reports.read]
        provider:
          reporting-as:
            token-uri: https://login.example.test/oauth2/token
```

This grant does not require user login, `openid`, an OIDC ID Token, or a browser callback. It issues a token to the Client per AS policy. Never use it to impersonate a specific user.

### 19.3. Reactive Service Fetching Tokens on Demand

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class ReportingServiceClient {

    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient api;

    public ReportingServiceClient(
            @Qualifier("serviceReactiveAuthorizedClientManager")
            ReactiveOAuth2AuthorizedClientManager manager,
            WebClient.Builder builder) {
        this.manager = manager;
        this.api = builder
            .baseUrl("https://reports-api.example.test")
            .build();
    }

    public Mono<String> getDailyReports() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reporting-service")
                .principal("service:reporting-service")
                .build();

        return manager.authorize(request)
            .switchIfEmpty(Mono.error(
                new IllegalStateException("No authorized service client")
            ))
            .flatMap(client ->
                api.get()
                    .uri("/v1/daily")
                    .headers(headers ->
                        headers.setBearerAuth(
                            client.getAccessToken().getTokenValue()
                        )
                    )
                    .retrieve()
                    .bodyToMono(String.class)
            );
    }
}
```

This example shows **acquiring a token from the manager inside a reactive chain** without faking a Servlet request or `ServerWebExchange`. You can integrate the service manager with the OAuth2 WebClient filter as supported by your version; the essential principle is avoiding forcing a background worker to have a Reactive web request context.

### 19.4. Principal Name Is Not a User Identity

`principal("service:reporting-service")` is merely an authorized-client storage key for the task. It does not authenticate a human user or grant a user's permissions to the service.

If a job processes user-delegated data, it needs an authorized client granted by that user via authorization code, with appropriate storage/refresh handling. Never pick another user's principal from an unverified queue payload to read their tokens.

## 20. Multi-User and Multi-Tenant: Never Mix Tokens

A Reactive OAuth2 client can manage many authorized clients:

```text
registration=company, principal=user-A           -> access token A
registration=company, principal=user-B           -> access token B
registration=calendar, principal=user-A          -> access token C
registration=service-reporting, principal=service -> access token D
```

Never allow:

- User B to select User A's principal.
- Tenant A to pass Tenant B's registration ID without authorization.
- A global WebClient to send access token D to APIs unrelated to `service-reporting`.
- A controller to match emails and use another user's authorized client.
- A cache key containing only `registrationId` without principal when tokens belong to users.

Storage keys normally represent `(clientRegistrationId, principalName)`. In multi-tenant setups, respect tenant/issuer trust boundaries even if principal names happen to collide across providers.

### 20.1. Whose Data Is It?

Spring Security OAuth2 Client handles **token authorization**; business services still must verify `account_id` and resource ownership. A valid token does not entitle User A to read all of User B's reports.

### 20.2. Use Issuer/Subject for OIDC Identity Mapping

If an application supports multiple OIDC providers, external user identities should typically map to internal accounts via verified **`(iss, sub)`** pairs rather than email. Authorized client selection still needs explicit registration, principal, and tenant boundaries; never key solely by raw `sub` across multiple issuers.

## 21. Care with Reactor Operators

### 21.1. `Mono` and `Flux` Are Typically Lazy

This snippet only **constructs the pipeline**; no request has been sent yet:

```java
Mono<String> result = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
```

Only when the framework subscribes to the publisher does the pipeline execute. Therefore:

- Never call `subscribe()` manually in a controller and immediately return a response.
- Never call `block()` on an event loop.
- When running in a background worker, ensure subscription orchestration matches the job lifecycle.
- Ensure `Authentication`/exchange propagate properly via Reactor context at execution time.

### 21.2. Avoid Losing Security Context When Spawning Separate Pipelines

Conceptually wrong:

```java
// Do not fire off background work assuming it keeps
// the original HTTP request's SecurityContext.
somePublisher.subscribe();
```

If a task outlives the request, manage context via a dedicated trusted business mechanism. Never push raw `Authentication` objects or raw tokens onto a message queue without strict security controls.

### 21.3. Bound Concurrency When APIs or Token Endpoints Are Rate-Limited

`Flux.flatMap(...)` can launch many outbound calls concurrently. If each call sees a near-expiry authorized client, a refresh storm can occur.

Consider:

- Bounding concurrency per user/registration.
- Reusing the manager/storage per policy.
- Single-flight refreshes for rotating tokens if architecture requires.
- HTTP connection pool limits and timeouts.
- Bounded retries/backoff.
- Never using a shared mutable static token field.

## 22. Security When Attaching Bearer Tokens

### 22.1. Only Send Tokens to Trusted Resource Servers

A Bearer access token allows whoever possesses it to call the target API. Therefore:

- Configure WebClients with fixed base URLs for their exact APIs.
- Build only relative paths from validated inputs.
- Never let user-supplied URLs decide which host receives a token.
- Control redirects and `Authorization` header forwarding.
- Keep `publicWebClient` separate from OAuth2-enabled WebClients.
- Never log raw tokens or URLs containing tokens.
- Enforce HTTPS and verify TLS certificates/hostnames.

### 22.2. Which Headers Must Never Be Logged?

```text
Authorization: Bearer <access_token>
Authorization: Basic <client_credentials>
access_token
refresh_token
id_token
client_secret
Authorization Code
session cookie
```

Safer logging:

```text
event=reports_api_call
registrationId=company
downstreamService=reports-api
httpStatus=200
durationMs=140
tokenWasAttached=true
```

Never use a token value as a correlation ID. When tracking identity, use sanitized internal identifiers per data policy.

### 22.3. Error Responses Can Contain Sensitive Data

An API might return an error body containing paths, subjects, stack traces, or internal messages. Never forward raw downstream error bodies to the frontend or analytics unless explicitly permitted.

### 22.4. The Filter Does Not Replace CSRF or CORS

The OAuth2 filter attaches access tokens to **outbound backend requests**. It does not replace Spring Security's CSRF protection on browser-facing endpoints, nor does it define frontend CORS policies.

OIDC Login still requires `state`/PKCE/nonce per protocol; having WebClient attach tokens does not make those checks optional.

## 23. Testing WebClient OAuth2 Integration

### 23.1. What to Verify

Tests with a mock Authorization Server/Resource Server can verify:

1. Requests selecting `clientRegistrationId("company")` receive a Bearer access token from the right registration.
2. Requests passing an explicit authorized client use the selected credential.
3. Requests through the public HTTP client **do not** attach Bearer tokens.
4. No unintended default token is enabled.
5. An API returning `401 invalid_token` triggers the corresponding handling policy.
6. An API returning `403 insufficient_scope` does not trigger an infinite retry loop.
7. When a token needs refreshing, the manager updates the authorized client if grant and provider allow.
8. When a refresh token is revoked, `invalid_grant` is handled and the broken token is not reused.
9. Two users/tenants never access each other's authorized clients.
10. Redirects to unknown hosts never carry the token along.

### 23.2. Testing with a Mock HTTP Server

Use `MockWebServer`, WireMock, or a suitable stub server to inspect outbound `Authorization` headers and simulate response statuses.

Crucially, tests **must never print real tokens**. Use fake access tokens, test session/security contexts, and dummy scopes/audiences.

### 23.3. Testing the Authorization Manager Independently

For `ReactiveOAuth2AuthorizedClientManager`, you can inject a fake manager returning:

```java
Mono.just(mockAuthorizedClient)
```

or:

```java
Mono.empty()
```

to verify how your service behaves with or without a client. When testing refresh behavior, stub valid Token Endpoint responses and verify storage side effects—do not mock only the WebClient call and skip the authorized-client lifecycle.

### 23.4. Do Not Treat Code Snippets as Executed Tests

Code snippets in this lesson illustrate APIs and design. Place them in a real project with matching dependencies, `ClientRegistration`s, security chains, test fixtures, and Spring Security version. Do not infer that every snippet was built and executed just by appearing in documentation.

## 24. Common Issues and Isolation Table

| Symptom | Possible cause | Remediation |
|---|---|---|
| WebClient does not attach Bearer token | Missing `clientRegistrationId`/authorized client/default policy | Select authorized client explicitly |
| Registration not found | Wrong `registrationId` or mismatched repository config | Compare YAML and Java |
| User lacks an authorized client | OAuth2 Login/consent incomplete, or store/principal mismatch | Check login flow and storage |
| API returns 401 even after login succeeds | Wrong audience, expired/revoked access token, or bad API config | Diagnose Resource Server, not just OIDC login |
| API returns 403 `insufficient_scope` | Insufficient scope/permissions | Request proper permissions/consent; do not refresh infinitely |
| Token Endpoint `invalid_grant` | Refresh token expired/rotated/revoked | Clean up broken state, reauthorize as needed |
| `invalid_client` | Wrong client credentials/auth method | Check registration and secret rotation |
| Using `Server...FilterFunction` in Servlet MVC | Confusing reactive with Servlet integration | Use the Servlet variant or switch stack |
| Failure when running from scheduler | No `ServerWebExchange`/user request principal | Use service-based reactive manager and `client_credentials` |
| User A's token appears in User B's request | Wrong principal/cache key/ownership | Partition authorized clients and verify accounts |
| Bearer token sent to public API | `setDefaultOAuth2AuthorizedClient(true)` on shared WebClient | Separate clients, use explicit registration |
| Excessive refreshes | Short token TTL, changing principal, storage/caching, concurrency | Inspect manager/provider, principal keys, and metrics |
| New refresh token not saved | Broken success handler/storage or race | Persist full updated authorized client consistently |
| WebClient response configured yet flow never runs | Publisher never subscribed | Let Spring manage subscriptions; avoid arbitrary `subscribe()` |
| `block()` fails on Netty event loop | Blocking call inside WebFlux | Keep reactive pipeline with `Mono`/`Flux` |
| Filter cannot find Authentication | Lost Reactor context or running outside HTTP request | Propagate context properly or use service manager |
| WebClient manager constructor does not clear bad tokens | Missing filter failure handler | Configure an appropriate failure handler |
| Retrying POST causes duplicate transactions | Retrying without idempotency | Add business-layer idempotency strategy |

### 24.1. Suggested Debugging Order

1. **Identify the stack:** WebFlux/reactive or Servlet/Spring MVC?
2. **Verify ClientRegistration:** right ID, issuer, grant, and scopes?
3. **Verify principal:** logged-in user or service task?
4. **Verify client selection:** `clientRegistrationId` attribute or explicit authorized client?
5. **Inspect authorized client storage:** does an entry exist for principal/registration?
6. **Inspect Token Endpoint:** refresh attempts and `invalid_grant`/`invalid_client`?
7. **Inspect Resource Server:** 401, 403, Bearer error code, audience/scope?
8. **Inspect outbound host:** right API and no redirects to untrusted hosts?
9. **Check Reactor context:** did the pipeline leave `SecurityContext`/exchange scope?
10. **Check failure handler:** do constructor/filter/manager clean up per policy?
11. **Check concurrency:** are multiple calls rotating the same refresh token concurrently?
12. **Log safely:** never include access tokens, refresh tokens, or callback codes.

## 25. Practice Scenarios

### Exercise 1: Choosing the Right Class

A WebFlux app using `SecurityWebFilterChain` and `ServerHttpSecurity` wants `WebClient` to attach OAuth2 access tokens automatically.

**Suggested answer:** use `ServerOAuth2AuthorizedClientExchangeFilterFunction`, not the Servlet variant.

### Exercise 2: Explicit ClientRegistration

You have `reportsWebClient`. Build a request to `/v1/reports` using the `company` registration.

```java
Mono<String> result = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company"))
    .retrieve()
    .bodyToMono(String.class);
```

### Exercise 3: User Has Two API Connections

A user has authorized clients `company` and `calendar`. The Reports API needs `company`'s token.

**Suggested answer:** pass `clientRegistrationId("company")` or the exact `OAuth2AuthorizedClient`; do not rely on a default token.

### Exercise 4: Shared WebClient Leaking Tokens

A WebClient enables `setDefaultOAuth2AuthorizedClient(true)` and calls a browser-supplied URL.

**Suggested answer:** risks SSRF/token exfiltration. Separate WebClients, use fixed API base URLs/allowlists, and select tokens explicitly.

### Exercise 5: Expired Access Token with a Refresh Token

**Suggested answer:** a manager/provider configured with `refreshToken()` can execute the Refresh Token Grant and save the new token. Do not write manual refresh loops in every service.

### Exercise 6: API 403 `insufficient_scope`

**Suggested answer:** evaluate the API's scope/consent requirements; refreshing with the same scope will not grant extra privileges—never retry infinitely.

### Exercise 7: `@Scheduled` Job

A job lacks `ServerWebExchange` and needs to call an API via client credentials.

**Suggested answer:** use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` with `ReactiveOAuth2AuthorizedClientService` and a stable service principal. Never fake a web request to obtain tokens.

### Exercise 8: Explicit `OAuth2AuthorizedClient`

A controller received a trusted authorized client via annotation and wants to pass it to WebClient.

```java
webClient.get()
    .uri("/v1/reports")
    .attributes(oauth2AuthorizedClient(client))
    .retrieve()
    .bodyToMono(String.class);
```

**Hint:** verify the client belongs to the right registration/user and its lifecycle aligns with refresh needs.

### Exercise 9: Two Concurrent Refresh Requests

Requests A and B both use RT-1; A receives RT-2, B hits `invalid_grant`.

**Suggested answer:** coordinate concurrency/rotation and token storage; never retry RT-1 indefinitely.

### Exercise 10: Reactive Context

A service reads `Authentication` via Servlet-style `SecurityContextHolder.getContext()` inside a Reactor chain and intermittently gets `null`.

**Suggested answer:** use reactive security context APIs or pass `Authentication`/`ServerWebExchange` explicitly. Never rely on Servlet ThreadLocals in WebFlux.

### Exercise 11: API 401 After Callback

OIDC Login succeeded, yet the Reports API returns `invalid_token`.

**Suggested answer:** verify the access token was issued for the right audience/scope/resource and remains valid; passing ID Token validation does not guarantee the access token works for every API.

### Exercise 12: Missing Refresh Token

The token response includes `access_token` without a `refresh_token`.

**Suggested answer:** depending on provider/consent/grant, a refresh token might not be issued. Enabling `.refreshToken()` in the manager is not enough; require fresh user authorization when access expires and the provider demands it.

## 26. Production Deployment Checklist

- [ ] Project genuinely runs **WebFlux Reactive Security** when using the Server OAuth2 filter.
- [ ] `SecurityWebFilterChain` and `oauth2Login` / `oauth2Client` are properly configured.
- [ ] `ClientRegistration`/issuer/Token Endpoint come from a trusted provider.
- [ ] Access tokens target the right Resource Server with required scopes/audience.
- [ ] WebClient selects registrations or authorized clients **explicitly**.
- [ ] Default authorized clients are not enabled on shared multi-host WebClients.
- [ ] Outbound hosts/URLs/redirects are restricted; Bearer tokens are never sent to untrusted origins.
- [ ] `ReactiveOAuth2AuthorizedClientManager`/repository saves and loads tokens under the right principal.
- [ ] When using the manager constructor, filter failure handling has been configured per version.
- [ ] Token Endpoint `invalid_grant` is handled distinctly from Resource Server 401/403.
- [ ] Refresh token rotation and concurrency policies handle multi-instance deployments.
- [ ] Background jobs use the service-based manager instead of faking `ServerWebExchange`.
- [ ] Reactor context/`Authentication` propagate cleanly in async pipelines.
- [ ] No `block()` on event loops or arbitrary `subscribe()`.
- [ ] Timeouts, bounded retries/backoff, and idempotency exist for side-effecting requests.
- [ ] Tokens, codes, client secrets, and cookies never appear in URLs, logs, or frontend responses.
- [ ] Tests cover multi-user, multi-registration, public APIs, token expiry, and failure paths.

## 27. Official References

1. [Spring Security API — ServerOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html): constructors, attributes, default client, and failure handler.
2. [Spring Security Reference — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): overview of OAuth2 Client in WebFlux.
3. [Spring Security Reference — Reactive OAuth2 Login](https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html): how users authenticate via OAuth2/OIDC on the reactive stack.
4. [Spring Security Reference — Authorized Clients](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html): managing authorized clients and WebClient integrations.
5. [Spring Security API — ReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientManager.html): reactive authorize contract.
6. [Spring Security API — DefaultReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/DefaultReactiveOAuth2AuthorizedClientManager.html): manager for reactive web requests.
7. [Spring Security API — AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.html): manager for service tiers without ServerWebExchange.
8. [Spring Security API — ReactiveOAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientProviderBuilder.html): configuring grant providers.
9. [Spring Security API — ServerOAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/server/ServerOAuth2AuthorizedClientRepository.html): authorized client store keyed by ServerWebExchange.
10. [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html): ClientRegistration, principal, and tokens.
11. [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): `ExchangeFilterFunction`, Reactor pipelines, and HTTP response handling.
12. [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): authorization code, refresh token, and grant types.
13. [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer`, `invalid_token`, and `insufficient_scope`.
14. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): OAuth2 and refresh token security guidelines.

## 28. Summary

**`ServerOAuth2AuthorizedClientExchangeFilterFunction` bridges `WebClient` and Spring Security Reactive's OAuth2 Client infrastructure.** The filter selects an authorized client, coordinates with `ReactiveOAuth2AuthorizedClientManager`/repositories to locate or renew tokens when eligible, and attaches access tokens to outbound `Authorization: Bearer` requests.

To use it safely, **explicitly choose the `ClientRegistration` or `OAuth2AuthorizedClient`**, bind the **right user/tenant principal**, restrict HTTP destinations, distinguish **Token Endpoint** errors from **Resource Server** errors, and understand failure-handler differences across constructors. Never enable default authorized clients on a shared multi-host WebClient, never substitute an ID Token for an access token, and never assume background jobs outside HTTP requests have a Reactive SecurityContext.

With these boundaries in place, WebFlux can call OAuth2 APIs in a non-blocking manner, manage token lifecycles consistently, and minimize the risk of credential leaks or privilege mix-ups across users, providers, and resources.
