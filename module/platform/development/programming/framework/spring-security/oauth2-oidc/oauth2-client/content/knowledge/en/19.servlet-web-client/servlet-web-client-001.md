# 19.1. `ServletOAuth2AuthorizedClientExchangeFilterFunction` and `WebClient`

In a **Spring Security OAuth 2.0/OIDC Client** application running on the **Servlet stack (Spring MVC)**, a user may log in via OpenID Connect, after which the backend needs to call an OAuth 2.0-protected API on their behalf. Instead of manually fetching the access token, concatenating `Authorization: Bearer ...` at every call site, and checking token expiration yourself, Spring Security provides **`ServletOAuth2AuthorizedClientExchangeFilterFunction`** to connect **`WebClient`** with the **OAuth2 Authorized Client** infrastructure.

This class acts as an **`ExchangeFilterFunction`** for WebClient: before WebClient sends an outbound request, the filter can look up or re-authorize the `OAuth2AuthorizedClient` corresponding to a `ClientRegistration` and a principal, and then attach the appropriate access token to the HTTP request.

The easiest point of confusion in this topic is that **`WebClient` uses a reactive API while the application runs in a Servlet environment**, whereas principal information, request/session state, and the authorized client store belong to Spring Security Servlet. Understanding this boundary helps avoid errors such as “authorized client not found”, “no Servlet request”, sending tokens to the wrong API, or misunderstanding token refresh.

## 1. The Problem: A Spring MVC Backend Calling an API After User Login

Suppose a reporting portal works as follows:

1. The user opens `https://portal.example.test`.
2. Spring Security redirects the user to the company's OpenID Provider.
3. The user authenticates; Spring receives the authorization code, exchanges it, and verifies the ID Token.
4. Spring maintains the login via `SecurityContext`/session and stores the `OAuth2AuthorizedClient` for the authorized Client.
5. A controller calls `https://reports-api.example.test/v1/reports` to retrieve reports according to the user's permissions.
6. The Reports API requires the HTTP header `Authorization: Bearer <access_token>`.

If written manually:

```java
// Poor approach: each controller manages the token on its own.
String token = someSessionMap.get("access_token");

String result = webClient.get()
    .uri("https://reports-api.example.test/v1/reports")
    .headers(headers -> headers.setBearerAuth(token))
    .retrieve()
    .bodyToMono(String.class)
    .block();
```

you would have to solve a whole series of issues yourself:

- Which `ClientRegistration` does the token belong to?
- Is the token being used an access token, ID Token, or refresh token?
- Does the token belong to the current user?
- Has the access token expired, and is there a refresh token to renew it?
- How do you update the new refresh token when the provider enables rotation?
- How do you handle HTTP 401/403 responses from the Resource Server?
- How do you prevent sending the Bearer token to another API or a user-controlled redirect URL?

`ServletOAuth2AuthorizedClientExchangeFilterFunction` helps **centralize the mechanism for selecting and attaching access tokens** through Spring Security abstractions. However, the filter does not automatically solve all business authorization or guarantee that the issued token has the right audience/scope. The application must still select the `ClientRegistration` and target API in a controlled manner.

## 2. Two Sides of the Architecture: Servlet Security and Reactive WebClient

A Spring Boot application can simultaneously use:

- **`spring-boot-starter-web`**: runs the Servlet stack with Spring MVC, `HttpServletRequest`, `HttpSession`, and the Servlet filter chain.
- **`spring-boot-starter-oauth2-client`**: handles OAuth2 Login, ClientRegistration, authorized clients, and token management.
- **`spring-boot-starter-webflux`**: provides `WebClient` and Reactor APIs to make HTTP client calls.

Adding `spring-boot-starter-webflux` to an application that already has Spring MVC **does not necessarily turn the server into WebFlux**. In typical Spring Boot setups, when both MVC and WebFlux are present, the server-side web application continues running Servlet MVC, while WebClient is used as a reactive-capable HTTP client.

| Component | Layer | Responsibility |
|---|---|---|
| `SecurityFilterChain` / `oauth2Login` | Spring Security Servlet | Authenticates HTTP requests from the browser, handles callbacks |
| `HttpServletRequest` / `HttpSession` | Servlet container | User request/session |
| `OAuth2AuthorizedClientRepository` | OAuth2 Client in web requests | Stores and looks up authorized clients bound to the Servlet context |
| `OAuth2AuthorizedClientManager` | OAuth2 Client | Decides whether a token needs to be authorized or refreshed |
| `ServletOAuth2AuthorizedClientExchangeFilterFunction` | Servlet Security → WebClient bridge | Retrieves the authorized client and attaches the token |
| `WebClient` | Reactor HTTP client | Sends HTTP requests to downstream APIs |
| `Resource Server` | Target API | Validates the access token, audience, scope, and permissions |

```mermaid
flowchart LR
    B["Browser"] --> MVC["Spring MVC Controller"]
    MVC --> SC["SecurityContext / OidcUser"]
    MVC --> WC["WebClient"]
    WC --> F["ServletOAuth2AuthorizedClientExchangeFilterFunction"]
    F --> M["OAuth2AuthorizedClientManager / Repository"]
    M --> CR["ClientRegistrationRepository"]
    M --> TK["Token Endpoint if refresh is needed"]
    F --> API["Downstream Resource Server"]
    API --> WC
    WC --> MVC
```

**Note:** Simplified diagram. In actual execution, the filter runs before the HTTP client sends the request and may skip calling the Token Endpoint if the authorized client already has a suitable access token.

### 2.1. Why Not Use `ServerOAuth2AuthorizedClientExchangeFilterFunction`?

Spring Security has two similar names:

| Class | Primary Environment | Related Mechanism |
|---|---|---|
| `ServletOAuth2AuthorizedClientExchangeFilterFunction` | **Servlet / Spring MVC** | `OAuth2AuthorizedClientRepository` or Servlet-compatible manager |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | **Reactive / Spring WebFlux server** | Reactive client repositories/managers and reactive security context |

In a backend using `HttpServletRequest`, Servlet-based `oauth2Login`, and `SecurityFilterChain`, choose the **Servlet** variant. Do not copy a `ServerOAuth2AuthorizedClientExchangeFilterFunction` configuration from a WebFlux tutorial and paste it into Spring MVC without checking the differences in repository, principal, and Reactor context.

## 3. Core Classes to Know

### 3.1. `ClientRegistration`

`ClientRegistration` describes the Client application registered with the Authorization Server. It may include:

```text
registrationId = company-api
clientId = portal-web
clientSecret = (kept secret on the backend)
authorizationGrantType = authorization_code
redirectUri = {baseUrl}/login/oauth2/code/{registrationId}
scopes = [openid, profile, reports.read]
provider = company-op
```

This is the **Client configuration**, not an access token yet.

### 3.2. `OAuth2AuthorizedClient`

Once the Client is authorized, Spring represents the result with:

```text
OAuth2AuthorizedClient
  ├── clientRegistration
  ├── principalName
  ├── accessToken
  │    ├── tokenValue
  │    ├── tokenType (usually Bearer)
  │    ├── issuedAt
  │    ├── expiresAt
  │    └── scopes
  └── refreshToken? (may be null)
```

An authorized client is typically distinguished by **registration** and **principal**. When browser user A and user B both log in through the same OP, they must never share each other's access tokens.

### 3.3. `OAuth2AuthorizedClientRepository` and `OAuth2AuthorizedClientService`

- `OAuth2AuthorizedClientRepository` provides the mechanism to save/find authorized clients within an HTTP Servlet request context.
- `OAuth2AuthorizedClientService` provides a save/find mechanism that does not require an `HttpServletRequest`.
- A repository may delegate storage to a service in some configurations, but **you should not assume the two stores are identical** without checking.

### 3.4. `OAuth2AuthorizedClientManager`

The manager coordinates authorizing and re-authorizing authorized clients through providers for grants such as `authorization_code`, `refresh_token`, or `client_credentials`, according to configuration and context.

This is important because the filter function does not create a “new token on every request” on its own. It delegates to the manager/repository to find the appropriate authorized client; if needed, the manager/provider can perform a refresh.

### 3.5. `ExchangeFilterFunction`

`ExchangeFilterFunction` is a filter in the WebClient pipeline. It can process a `ClientRequest` before invoking the next `ExchangeFunction`, for example:

```text
Application WebClient call
  -> OAuth2 ExchangeFilterFunction
     -> obtain/authorize OAuth2AuthorizedClient
     -> attach Authorization: Bearer ...
     -> call HTTP client/Resource Server
  -> return ClientResponse
  -> handle status/body
```

A filter is a sensible extension point for attaching tokens, but **it should not be turned into an automatic mechanism that sends every token to every URL**.

## 4. Configuring Dependencies for Spring MVC + WebClient

Maven example for a Spring Boot 3.x application using Servlet and OAuth2 Client:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
</dependencies>
```

Do not manually pin individual dependency versions if the Spring Boot BOM manages them. Artifact names and WebClient integration may change in newer Boot/Security versions; use starters compatible with your actual project.

Gradle Kotlin DSL example:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
    implementation("org.springframework.boot:spring-boot-starter-webflux")
}
```

In systems that only use Spring MVC and want a synchronous HTTP client, `RestClient` can be an alternative. This lesson intentionally focuses on **WebClient in Servlet** because that is the scenario where `ServletOAuth2AuthorizedClientExchangeFilterFunction` is needed.

## 5. Registering the OIDC Client in `application.yml`

Example of a trusted OP via OIDC discovery:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-api:
            provider: company-op
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            scope:
              - openid
              - profile
              - reports.read
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"

        provider:
          company-op:
            issuer-uri: https://login.example.test/realms/company
```

Explanation:

- `company-api` is the **registration ID** used in Java.
- `openid` enables OIDC login and the ID Token.
- `reports.read` is a hypothetical API scope; the provider must actually support, issue, and include it in the access token for the target resource.
- `issuer-uri` identifies the OP for discovery metadata, the Token Endpoint, and JWKS.
- `redirect-uri` is used for the Authorization Code callback; it is not the reports URL.
- `client-secret` is provided via a secret manager/environment variable; do not hard-code it in source code.

**Warning about audience:** A successful OAuth2 Login does not guarantee that the issued access token can call any arbitrary downstream API. A Resource Server may require a specific audience, resource indicator, or scope per its contract with the OP. If an API requires a token for a different resource, you must register/grant permissions accurately according to the provider.

### 5.1. Configuring Servlet Login

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
```

`oauth2Login` handles the user login flow; `oauth2Client` adds OAuth2 Client support configuration when needed. In real-world applications with multiple security filter chains/paths, request matchers and CSRF/session policies must be designed appropriately.

## 6. Creating a WebClient with the Servlet OAuth2 Filter

A common direct configuration creates the filter from `ClientRegistrationRepository` and `OAuth2AuthorizedClientRepository`:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsWebClientConfig {

    @Bean("reportsWebClient")
    WebClient reportsWebClient(
            ClientRegistrationRepository clientRegistrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
            clientRegistrations,
            authorizedClients
        );

        return WebClient.builder()
            .baseUrl("https://reports-api.example.test")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
```

The long package name is wrapped onto two lines after `import` purely for presentation; **Java does not allow arbitrary line breaks inside an identifier**. In an actual source file, write the import on a single line:

```java
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
```

Or use your IDE's auto-import feature accurately.

### 6.1. Why Call `oauth2Configuration()`?

`oauth2.oauth2Configuration()` is a `Consumer<WebClient.Builder>` that registers the OAuth2 filter and supporting configuration so the filter works properly with the Servlet context.

Using:

```java
WebClient.builder()
    .apply(oauth2.oauth2Configuration())
    .build();
```

follows Spring Security's configuration pattern. Compared to building a custom filter that sets the `Authorization` header manually, it keeps authorized client lookup within the framework's abstraction.

### 6.2. When to Use the Constructor Accepting `OAuth2AuthorizedClientManager`?

You may want to explicitly choose grant providers, refresh behavior, and persistence:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientConfig {

    @Bean
    OAuth2AuthorizedClientManager webAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository repository) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, repository
            );
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
```

Then:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean("reportsWebClient")
WebClient reportsWebClient(
        OAuth2AuthorizedClientManager webAuthorizedClientManager) {

    var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
        webAuthorizedClientManager
    );

    return WebClient.builder()
        .baseUrl("https://reports-api.example.test")
        .apply(oauth2.oauth2Configuration())
        .build();
}
```

**Choose only one of the two `reportsWebClient` configurations**—do not declare two beans with the same name in one project. The constructor taking a manager is useful when the application already defines a manager with custom policies.

### 6.3. Differences in Default Failure Handler

An important operational detail of `ServletOAuth2AuthorizedClientExchangeFilterFunction`:

- When the filter is created with **`ClientRegistrationRepository` + `OAuth2AuthorizedClientRepository`**, modern Spring Security versions support configuring a default `RemoveAuthorizedClientOAuth2AuthorizationFailureHandler` for OAuth2 error responses from a Resource Server.
- When the filter is created with **`OAuth2AuthorizedClientManager`**, check and **explicitly configure a failure handler** if the application needs to remove the authorized client on API errors such as `invalid_token`. Do not assume every constructor has the same default behavior.

Always check the documentation for the exact **Spring Security version** you are using. In addition, the failure handler for API 401/403 responses differs from the failure handler when the Token Endpoint rejects a refresh token.

## 7. Explicitly Selecting a ClientRegistration When Calling WebClient

A safe, controllable approach is to specify the registration for requests requiring a Bearer token using the static helper:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

String response = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company-api"))
    .retrieve()
    .bodyToMono(String.class)
    .block();
```

In a Servlet controller with the appropriate principal and request context, the filter will look up or authorize the client corresponding to registration `company-api` and send the access token to the Reports API.

### 7.1. Why Set `clientRegistrationId` on Each Request?

A single WebClient may be used to call multiple endpoints, or multiple `ClientRegistration`s may share the same API host. Explicit selection helps:

- Make it clear in code reviews which Client's token will be used.
- Avoid accidentally attaching the current user's token to an API that does not need a token.
- Apply separate permission/audience policies per registration.
- Avoid relying on a single “default token” for all HTTP requests.
- Easily distinguish `invalid_scope`, `invalid_client`, and provider mapping errors.

### 7.2. An MVC Controller Using WebClient

```java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

@RestController
public class ReportsController {

    private final WebClient reportsWebClient;

    public ReportsController(
            @Qualifier("reportsWebClient") WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    @GetMapping("/reports")
    public String reports() {
        return reportsWebClient.get()
            .uri("/v1/reports")
            .attributes(clientRegistrationId("company-api"))
            .retrieve()
            .bodyToMono(String.class)
            .block(Duration.ofSeconds(10));
    }
}
```

The `import static` line in the example is split for readability; in a real Java file, write it on one continuous line:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
```

This controller snippet illustrates how to attach OAuth2 attributes. When using `.block(...)` in Spring MVC, the **Servlet request thread is blocked** until the downstream API returns data. This can be acceptable for some MVC systems, but requires timeouts, concurrency limits, and load evaluation.

Do not call `block()` on a **Reactor non-blocking event-loop thread** or in a WebFlux runtime with non-blocking rules. You can keep the reactive pipeline and let MVC handle asynchronous return types when supported by the framework/version, while making sure the full OAuth2 context is propagated.

### 7.3. UserInfo Is Not Needed to Call APIs

`OidcUser` may contain an ID Token and UserInfo claims, but APIs require an **access token** with the proper scope/audience. The filter uses `OAuth2AuthorizedClient#getAccessToken()`, not `OidcUser#getIdToken()`, to send as Bearer.

Do not write:

```java
// WRONG purpose:
String idToken = oidcUser.getIdToken().getTokenValue();
headers.setBearerAuth(idToken);
```

The ID Token is for the OIDC Client to verify identity, not an access token for calling a Resource Server.

## 8. Passing a Known `OAuth2AuthorizedClient` Directly

In Servlet MVC, Spring Security supports `@RegisteredOAuth2AuthorizedClient` to resolve the authorized client for a given registration. Once you already have the authorized client, you can pass that object directly to the filter:

```java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@RestController
public class ProfileProxyController {

    private final WebClient reportsWebClient;

    public ProfileProxyController(
            @Qualifier("reportsWebClient") WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    @GetMapping("/reports/profile")
    public String profile(
            @RegisteredOAuth2AuthorizedClient("company-api")
            OAuth2AuthorizedClient authorizedClient) {

        return reportsWebClient.get()
            .uri("/v1/me")
            .attributes(oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(String.class)
            .block(Duration.ofSeconds(10));
    }
}
```

With this approach, the **authorized client is selected upfront** and passed directly to the WebClient request. The benefit is transparency: the filter does not need to guess the registration from the security context or default rules.

### 8.1. Differences Between the Two Helpers

| Helper | Passed Value | When to Use |
|---|---|---|
| `clientRegistrationId("company-api")` | Client configuration ID | When you want the filter/manager to look up the right authorized client for the principal |
| `oauth2AuthorizedClient(authorizedClient)` | Pre-selected/resolved object | When the controller/service already holds a valid authorized client |

Do not construct an `OAuth2AuthorizedClient` yourself from a raw token sent by the browser and pass it to the helper; the object must belong to a trusted registration and principal.

### 8.2. What If the Client Is Not Yet Authorized?

`@RegisteredOAuth2AuthorizedClient` and the manager can trigger supported authorization operations depending on the context. However, if the required authorization code/consent does not exist yet, an HTTP client filter **cannot display a real login screen** inside a background thread.

With OAuth2 Login, let the user go through `/oauth2/authorization/{registrationId}`, receive the callback, and store the authorized client. Only then should you call downstream APIs on behalf of the authenticated user.

## 9. Risks of `setDefaultOAuth2AuthorizedClient(true)`

Some examples use:

```java
var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
    clientRegistrations, authorizedClients
);

oauth2.setDefaultOAuth2AuthorizedClient(true);
```

This configuration instructs the filter to use the authorized client associated with the current `OAuth2AuthenticationToken` as the **default** when no client is specified on a request.

This feature is convenient, but **requires extreme caution**. As Spring Security notes, a WebClient configured this way may attach the access token to **every request** passing through it, including requests that do not need OAuth2 or requests sent to unrelated hosts.

### 9.1. Risk Example

```java
// Shared WebClient with defaultOAuth2AuthorizedClient(true) enabled
sharedWebClient.get()
    .uri("https://third-party.example.test/public-data")
    .retrieve()
    .bodyToMono(String.class);
```

If the filter selects the authorized client from the current user and attaches the Bearer token, the system's access token can be leaked to a third party. This is a credential exposure risk, not just a logic bug.

**Design recommendations:**

1. Do not enable `setDefaultOAuth2AuthorizedClient(true)` on a WebClient shared across multiple origins.
2. Prefer `clientRegistrationId(...)` or `oauth2AuthorizedClient(...)` on specific requests.
3. Create a dedicated WebClient for each trusted Resource Server with a fixed `baseUrl`.
4. Never let users directly control the absolute URL to which the backend sends a Bearer token.
5. Control HTTP redirects, proxies, and forwarding of the `Authorization` header to other hosts.
6. If a default is truly necessary, restrict it to a very narrowly scoped client and test end-to-end.

### 9.2. `setDefaultClientRegistrationId(...)` Also Requires Care

Besides defaulting to the currently logged-in principal's client, the filter can also be given a **default client registration ID**:

```java
oauth2.setDefaultClientRegistrationId("service-api");
```

This is useful for a dedicated WebClient that only calls one API, but it also allows requests without a specified registration to use the default token.

If that WebClient is reused for an unintended host, the token leakage issue still exists. **Defaults do not replace a target API allowlist**.

### 9.3. WebClient Following the Principle of Least Privilege

A good design might look like:

```text
reportsWebClient:
  baseUrl = https://reports-api.example.test
  only uses company-api authorized client
  scope = reports.read

billingWebClient:
  baseUrl = https://billing-api.example.test
  only uses billing-api authorized client
  scope = invoices.read

publicWebClient:
  no OAuth2 filter
  only used for public data
```

Separating clients like this clarifies token boundaries and reduces the risk of accidentally reusing a Bearer token across different Resource Servers.

## 10. How Are the OAuth2 Login Principal and Authorized Client Selected?

When a user logs in via OIDC, Spring Security holds an `Authentication` in `SecurityContext`. With OAuth2 Login, this is typically an `OAuth2AuthenticationToken` containing:

- A principal that is an `OidcUser` or `OAuth2User`.
- The session's authorities.
- `authorizedClientRegistrationId` identifying the registration used for login.

`OAuth2AuthorizedClientRepository` and the manager use the appropriate principal/context to look up the granted authorized client.

### 10.1. One User Can Have Multiple Authorized Clients

For example, an internal account connected to both calendar and reports:

```text
Principal: user-782
  ├── registrationId = company-api   -> access token A
  └── registrationId = calendar-api  -> access token B
```

When calling the Reports API, you must choose `company-api` rather than grabbing the “most recent authorized client”. Two tokens can have different issuers, audiences, scopes, and consents.

### 10.2. The Principal Name Must Be Stable and Match the User

An authorized client is usually keyed by `(clientRegistrationId, principalName)` in the service or via the appropriate repository/session. If you arbitrarily change `principalName` after login or use a different user's name, the filter may fail to find the token or use the wrong one.

Never pass a user ID taken from an HTTP query parameter to access someone else's authorized client. Selecting a token by principal must be tied to a verified **SecurityContext and ownership**.

### 10.3. Scopes and Roles Are Two Different Things

The scope `reports.read` describes the access token's permissions with the API, which is not synonymous with an application role like `ROLE_REPORT_ADMIN`. The Resource Server checks scopes/audience; the Spring MVC backend must still enforce user authorization on internal resources.

Do not treat the filter successfully attaching a token as proof that the user is allowed to view another account's reports.

## 11. Token Lifecycle: When Does WebClient Perform a Refresh?

`ServletOAuth2AuthorizedClientExchangeFilterFunction` does not “exchange tokens” on its own by parsing JWTs and minting a new Bearer token. It uses Spring Security's authorized-client infrastructure.

A call can proceed as follows:

```mermaid
sequenceDiagram
    autonumber
    participant C as MVC Controller
    participant F as OAuth2 WebClient Filter
    participant M as Authorized Client Manager
    participant S as Authorized Client Repository/Service
    participant AS as Authorization Server
    participant API as Reports API

    C->>F: WebClient.get() with clientRegistrationId
    F->>M: authorize by registration + principal
    M->>S: Read existing authorized client
    alt Access token still valid
        S-->>M: Current authorized client
        M-->>F: Current token
    else Has refresh token, token needs renewal
        M->>AS: POST /token grant_type=refresh_token
        AS-->>M: New access token (+ new refresh token?)
        M->>S: Save new authorized client
        M-->>F: New access token
    end
    F->>API: GET /v1/reports + Bearer access token
    API-->>F: HTTP response
    F-->>C: Mono / returned data
```

### 11.1. Expired Access Token vs. Revoked Refresh Token

- An expired access token is a normal OAuth2 scenario.
- A refresh token can help obtain a new access token when allowed by the Authorization Server.
- When a refresh token has been revoked or already rotated, the Token Endpoint may return `invalid_grant`.
- Spring Security managers have failure handling mechanisms to remove broken authorized clients according to configuration.
- Do not assume every `OAuth2AuthorizedClient` has a refresh token.
- A user's HTTP session may still be valid even though a downstream API connection requires reauthorization.

### 11.2. `expiresAt` Is Not Proof That the API Accepts the Token

`OAuth2AccessToken#getExpiresAt()` indicates the expiration tracked by the Client. The API may still reject the token due to:

- The token having been revoked.
- Audience mismatch.
- Insufficient scope.
- Invalid issuer or signing key for the API.
- Different tenant/resource policy.
- Clock skew between systems.

Therefore, distinguish **Token Endpoint** errors (requesting/refreshing tokens) from **Resource Server** errors (using the access token).

### 11.3. Where Do PKCE, Nonce, and the OIDC ID Token Fit?

`ServletOAuth2AuthorizedClientExchangeFilterFunction` handles **outbound API calls**, not the protocol steps during OAuth2 Login:

- `state`/PKCE relate to the authorization request/callback.
- `nonce`/ID Token validation relate to OIDC Login.
- The refresh token is used at the Token Endpoint when needed.
- The access token is attached to outbound API requests.
- The ID Token must not be placed in an API's `Authorization` header as an access token.

## 12. Handling 401 and 403 Responses from the Resource Server

Suppose WebClient sends:

```http
GET /v1/reports HTTP/1.1
Host: reports-api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

The API may return:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

or:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

These two errors have different meanings:

| Error | Common Meaning | Appropriate Action |
|---|---|---|
| HTTP 401 `invalid_token` | Access token is no longer accepted by the API | Check expiry, revocation, audience; consider invalidating/reacquiring per policy |
| HTTP 403 `insufficient_scope` | Token lacks required permissions | Check scope/consent/role; do not refresh infinitely |
| HTTP 401 without OAuth error | Possibly a different API auth scheme or proxy | Inspect response/Resource Server |
| HTTP 429 | API rate limit | Bounded backoff; do not delete the token arbitrarily |
| HTTP 5xx | API error | Retry per idempotency policy; do not assume OAuth2 failure |
| Token Endpoint `invalid_grant` | Invalid refresh token/code | Clean up broken authorized client and require reauthorization if needed |

### 12.1. Distinguishing Manager and Filter Failure Handlers

There are two stages:

1. The manager/provider requests or refreshes a token. If the Token Endpoint rejects it, the error belongs to **authorization/reauthorization**.
2. WebClient has sent the access token to the API. If the API returns 401/403, the error belongs to **resource access**.

With the repository-based constructor, the filter can configure a default handler that removes the authorized client based on certain OAuth2 errors returned by the Resource Server. With the manager-based constructor, you may need to attach a handler explicitly.

Do not write a catch-all “on any 401/403, delete all tokens and redirect to login”. Missing scope or wrong resource errors will not be fixed by infinite re-logins.

### 12.2. `retrieve()` and WebClient Exceptions

By default, WebClient converts HTTP 4xx/5xx responses into `WebClientResponseException` when using `retrieve()`.

```java
import org.springframework.web.reactive.function.client.WebClientResponseException;

try {
    String body = reportsWebClient.get()
        .uri("/v1/reports")
        .attributes(clientRegistrationId("company-api"))
        .retrieve()
        .bodyToMono(String.class)
        .block();
} catch (WebClientResponseException.Unauthorized ex) {
    // 401 from downstream API; do not assume invalid_grant.
} catch (WebClientResponseException.Forbidden ex) {
    // 403, possibly due to insufficient_scope or business policy.
}
```

`clientRegistrationId` requires a static import as in the earlier example. This snippet illustrates error handling, not a complete service.

You can configure `onStatus(...)` to produce a domain exception:

```java
String body = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company-api"))
    .retrieve()
    .onStatus(status -> status.value() == 401,
        response -> Mono.error(
            new IllegalStateException("Downstream API rejected token")
        ))
    .bodyToMono(String.class)
    .block();
```

You need to import `reactor.core.publisher.Mono`. Do not include response headers containing credentials or raw tokens in exceptions returned to the frontend. When using `onStatus`, understand how custom error mapping interacts with the filter's failure handling in your version so you do not accidentally strip out required OAuth2 error details.

### 12.3. When Should 401 Be Handled Automatically?

You might want a request that receives 401 `invalid_token` to be retried after the authorized client has been removed or refreshed. However, set clear limits:

- Only retry when the API operation is safe to repeat.
- Never retry infinitely.
- Do not treat 403 `insufficient_scope` as an expired-token error.
- Avoid retrying POST requests with side effects if there is no idempotency strategy.
- Do not send a new token to a host controlled by redirects or user input.
- With refresh token rotation, handle concurrency if multiple requests refresh at the same time.

## 13. When the Filter Has a Custom `OAuth2AuthorizedClientManager`

If a project wants to control Token Endpoint behavior, it can explicitly configure a manager and pass it to the filter.

Example:

```java
@Bean("webAuthorizedClientManager")
OAuth2AuthorizedClientManager webAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientRepository authorizedClients) {

    var provider = OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();

    var manager = new DefaultOAuth2AuthorizedClientManager(
        registrations, authorizedClients);

    manager.setAuthorizedClientProvider(provider);

    return manager;
}
```

Imports are needed as in section 6.2. Then:

```java
@Bean("reportsWebClient")
WebClient reportsWebClient(
        @Qualifier("webAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager) {

    var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
        manager);

    // When custom handling of OAuth2 resource errors is desired, configure
    // oauth2.setAuthorizationFailureHandler(...) according to your version
    // and actual authorized client store.

    return WebClient.builder()
        .baseUrl("https://reports-api.example.test")
        .apply(oauth2.oauth2Configuration())
        .build();
}
```

### 13.1. When Is a Custom Manager Needed?

- Multiple ClientRegistrations/grants require an explicit grant selection policy.
- You want to configure Clock Skew on the refresh token provider per your version.
- You have a custom access token response client or provider-specific Token Endpoint.
- You need failure handlers/persistence different from the defaults.
- Multiple different authorized client sources exist in the application.
- You want to share a common manager across multiple HTTP client integrations.

However, **more customization increases security and operational responsibility**. If the defaults already meet your needs, there is no reason to create a custom manager for every project.

### 13.2. Handler on `invalid_grant`

When a refresh token is rejected, Spring Security managers have default failure handling to remove the broken authorized client from the appropriate repository/service. If you replace the handler, preserve the necessary behavior; otherwise, the next request may keep using the broken refresh token and cause a loop.

Do not confuse a Token Endpoint `invalid_grant` error with an API 401 `invalid_token`. A handler for one is not necessarily invoked for the other.

## 14. Servlet Request Context and Asynchronous Calls

`WebClient` builds a Reactor pipeline. This **does not eliminate** the fact that OAuth2 state in a Servlet application can depend on:

- The current `HttpServletRequest`.
- The `HttpServletResponse`, when the repository needs to save an authorized client.
- The `Authentication` in `SecurityContext`.
- The session/cookie and principal name used to look up the authorized client.

So think carefully about how context is passed to the filter.

### 14.1. On an MVC Controller Thread

A `WebClient` call initiated and executed immediately within a Servlet request can usually obtain the appropriate context through the integration. However, if execution shifts to a scheduler/async worker or runs from a lazily subscribed pipeline, **do not assume all ThreadLocal Servlet/SecurityContext state remains intact**.

Example:

```java
@GetMapping("/reports")
public Mono<String> reports() {
    return reportsWebClient.get()
        .uri("/v1/reports")
        .attributes(clientRegistrationId("company-api"))
        .retrieve()
        .bodyToMono(String.class);
}
```

Spring MVC can support a `Mono` return type via reactive adapters, yet subscription timing and the executing thread may differ from when the controller returns. In such architectures, providing the appropriate authorized client/principal **explicitly** reduces reliance on ThreadLocal.

### 14.2. Resolving the Authorized Client Before Building the Pipeline

```java
@GetMapping("/reports")
public Mono<String> reports(
        @RegisteredOAuth2AuthorizedClient("company-api")
        OAuth2AuthorizedClient authorizedClient) {

    return reportsWebClient.get()
        .uri("/v1/reports")
        .attributes(oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class);
}
```

In many cases, this approach is easier to reason about when the downstream call is subscribed at a later time. Even so, an upfront authorized client object can become stale if the response is delayed for a long time or refreshed elsewhere; the application must understand its lifecycle during long-running async processing.

### 14.3. Do Not Pass Tokens Freely Through Message Queues

If work is offloaded to a queue/background job, do not stuff a raw access token into the message and hope it is still valid when the worker runs.

A better option is for the message to carry a **trusted business identifier**, and for the worker to use `AuthorizedClientServiceOAuth2AuthorizedClientManager` or an appropriate token service mechanism to obtain credentials at execution time. The worker must verify ownership before looking up a user's token.

## 15. When Should `ServletOAuth2AuthorizedClientExchangeFilterFunction` Not Be Used?

The class name states its primary target: **OAuth2 WebClient on Servlet**. Some situations call for other approaches:

| Context | Appropriate Approach |
|---|---|
| Spring MVC controller calling an API for the logged-in user | `ServletOAuth2AuthorizedClientExchangeFilterFunction` with the user's authorized client |
| Spring WebFlux reactive server | `ServerOAuth2AuthorizedClientExchangeFilterFunction` and reactive repositories/managers |
| `@Scheduled`, queue worker, command-line task outside an HTTP request | `AuthorizedClientServiceOAuth2AuthorizedClientManager`; HTTP client integration using a service context |
| Calling a public API that requires no token | WebClient without an OAuth2 filter |
| Spring MVC backend wanting a simple synchronous client | `RestClient` and OAuth2 Client interceptor in supported versions |
| Calling a resource under application authority without a user | Client Credentials Grant with a service manager |
| Receiving tokens sent by external clients to your API | Resource Server configuration, not OAuth2 Client filter |

### 15.1. Which Manager Should a `@Scheduled` Job Use?

If a scheduled job calls an API using `client_credentials`, it has no `HttpServletRequest`. In that case, configure:

```java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();

var manager =
    new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        clientRegistrationRepository,
        oauth2AuthorizedClientService
    );
manager.setAuthorizedClientProvider(provider);
```

This snippet requires imports and the actual beans. The job invokes the manager with a stable service principal name. **Do not mock a Servlet request** just to use a filter designed for web requests.

### 15.2. WebClient Does Not Decide User Permissions

For user-delegated API calls, the Authorization Server grants permissions via scopes/consent, the Resource Server validates the access token, and the application must still protect its own endpoints. The filter only attaches a token matching the context it was configured for; it does not check ownership of individual reports or invoices in the business database.

## 16. A More Complete Example: A Dedicated Service for the Reports API

Separating HTTP client configuration from controllers and business logic prevents controllers from knowing too much about tokens.

### 16.1. Dedicated WebClient Bean

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ReportsClientConfiguration {

    @Bean("reportsWebClient")
    WebClient reportsWebClient(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClientRepository) {

        var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
            registrations, authorizedClientRepository);

        return WebClient.builder()
            .baseUrl("https://reports-api.example.test")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
```

### 16.2. Service Accepting the Authorized Client

```java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@Service
public class ReportsApiClient {

    private final WebClient reportsWebClient;

    public ReportsApiClient(
            @Qualifier("reportsWebClient") WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    public String listReports(OAuth2AuthorizedClient client) {
        if (!"company-api".equals(
                client.getClientRegistration().getRegistrationId())) {
            throw new IllegalArgumentException(
                "Unexpected OAuth2 client registration");
        }

        return reportsWebClient.get()
            .uri("/v1/reports")
            .attributes(oauth2AuthorizedClient(client))
            .retrieve()
            .bodyToMono(String.class)
            .block(Duration.ofSeconds(10));
    }
}
```

Here the service proactively validates the registration ID, preventing an authorized client from another API from being passed in. In a production application, deserialize the response into a schema-defined DTO, configure timeouts on the HTTP client, and handle API errors according to your domain.

### 16.3. Controller Only Coordinates

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportsController {

    private final ReportsApiClient api;

    public ReportsController(ReportsApiClient api) {
        this.api = api;
    }

    @GetMapping("/reports")
    public String reports(
            @RegisteredOAuth2AuthorizedClient("company-api")
            OAuth2AuthorizedClient authorizedClient) {

        return api.listReports(authorizedClient);
    }
}
```

`ReportsClientConfiguration`, `ReportsApiClient`, and `ReportsController` are three parts of the same application. Do not declare another `reportsWebClient` bean with the same name from earlier examples.

### 16.4. Responsibilities Still Belong to the Application

When using this pattern:

- The `company-api` registration must be granted an access token for the Reports API by the provider.
- The user must hold the scopes and permissions per the contract.
- The controller endpoint must be protected by Spring Security.
- Do not expose the access token to the browser.
- The target API host/routes must be controlled.
- If the token expires or is revoked, the authorized-client manager and failure handler must handle it according to policy.
- Do not use an ID Token or refresh token as a Bearer token for a Resource Server.

## 17. Adding Timeouts and Connection Management

WebClient uses a reactive HTTP client but still needs proper timeouts and resource limits. Do not call `.block()` indefinitely on a Servlet thread.

Example timeout at the reactive chain level:

```java
import java.time.Duration;

String result = reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company-api"))
    .retrieve()
    .bodyToMono(String.class)
    .timeout(Duration.ofSeconds(8))
    .block(Duration.ofSeconds(10));
```

These are illustrative values, not standard thresholds. For production, configure connection timeouts, response timeouts, connection pools, and retries according to your SLOs. Also:

- A timeout in the chain stops waiting on the Client side, but the target server may have already processed the request.
- Do not retry a POST with side effects without an idempotency strategy.
- Timeouts during refresh token rotation must be handled carefully because the Token Endpoint may have already consumed the refresh token.
- Do not log the HTTP Authorization header while diagnosing timeouts.
- Distinguish API timeouts from Token Endpoint timeouts in error metrics.

### 17.1. SSL/TLS

Outbound OAuth2/API requests must use HTTPS in production environments, except in controlled development setups. Do not disable certificate validation, hostname verification, or configure a “trust all” HTTP client to work around TLS errors.

If the backend runs behind a proxy or uses mTLS, configure truststores, client credentials, and transport settings according to infrastructure policy; never put tokens in query strings to “make debugging easier”.

## 18. Security When Using the WebClient OAuth2 Filter

### 18.1. Do Not Send Bearer Tokens to Arbitrary Hosts

Suppose a controller accepts:

```java
@GetMapping("/proxy")
public String proxy(@RequestParam String url) {
    return reportsWebClient.get()
        .uri(url)
        .attributes(clientRegistrationId("company-api"))
        .retrieve()
        .bodyToMono(String.class)
        .block();
}
```

This is a dangerous design: a user can supply a URL pointing to an external host while the filter still attaches the access token, causing **credential exfiltration** and **SSRF**.

Instead:

- Configure a fixed base URL and allow only controlled relative paths.
- Separate public HTTP clients from authenticated HTTP clients.
- Never let users choose the scheme/host/port of an outbound request carrying a token.
- Control redirect behavior; consider blocking cross-origin redirects for requests containing `Authorization`.
- Only select `ClientRegistration` from a server-side allowlist.

### 18.2. Notes on HTTP Redirects

An HTTP client may automatically follow 301/302/307/308 responses depending on configuration. If the target server returns a redirect to another host, ensure the token is not forwarded to an untrusted origin.

Do not rely on the assumption that “every HTTP client strips the Authorization header when the host changes”. Check the behavior of your HTTP connector/version and design target URLs and redirect policies accordingly.

### 18.3. Do Not Log Tokens

Do not log:

```text
Authorization: Bearer ...
access_token
refresh_token
id_token
client_secret
OAuth2 callback authorization code
raw Token Endpoint response
```

More useful logs look like:

```text
registrationId=company-api
downstreamService=reports-api
httpStatus=200
oauth2Stage=RESOURCE_CALL
durationMs=123
```

An `OAuth2AuthorizedClient` holds credentials; do not call `toString()` and dump the entire object into logs unless you know the exact redaction behavior of your version. For technical support, only share sanitized HAR files/traces.

### 18.4. Do Not Confuse CORS and CSRF

CORS controls browser JavaScript calling cross-origin resources; a **backend WebClient** calling an API is a server-to-server call and generally does not require CORS configuration on the backend caller in the same way.

CSRF protection remains critical for HTTP endpoints using cookie-based sessions in a Spring MVC application. Using an OAuth2 filter on WebClient does not replace CSRF validation for POST/PUT/DELETE requests sent by the browser to the portal.

## 19. Observing Configuration and Debugging

### 19.1. Stage-by-Stage Checklist

When a WebClient call fails, categorize the issue:

1. **SecurityContext:** Is the user authenticated? Is it the right principal/OIDC provider?
2. **ClientRegistration:** Does the requested `registrationId` exist? Are grant/issuer/scope correct?
3. **Authorized client lookup:** Is there a stored token for the principal and registration?
4. **Token acquisition/refresh:** Are there Token Endpoint errors like `invalid_client` or `invalid_grant`?
5. **Outbound HTTP:** Is WebClient attaching the Bearer token to the right host/path?
6. **Resource Server:** Did the API return 401, 403, 429, or 5xx? Is there a Bearer error code?
7. **Response mapping:** Is it a JSON decoding error, content type issue, timeout, or business rule?
8. **Persistence/concurrency:** Was the new token saved, or is there a refresh token rotation race?

### 19.2. Common Errors Table

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `No qualifying bean of type WebClient` | No WebClient bean declared, missing WebFlux dependency | Create the appropriate WebClient/Builder bean |
| Registration not found | Wrong `registrationId` | Compare YAML and `clientRegistrationId(...)` |
| `ClientAuthorizationRequiredException` or user authorization required | No authorized client yet and the flow requires a browser | Initiate the appropriate OAuth2 Login/consent flow |
| `No thread-bound request` | Invoking a request-based manager in the background | Use a service-based manager or explicit context |
| API 401 `invalid_token` | Token expired/revoked/wrong audience | Diagnose token/API; apply cleanup mechanism if appropriate |
| API 403 `insufficient_scope` | Token lacks permissions | Check scope/consent; do not refresh infinitely |
| Token Endpoint `invalid_grant` | Refresh token expired, revoked, rotation race | Clean up broken state; require reauthorization when needed |
| Only this controller fails to attach token | Missing `attributes(...)` or default not enabled | Specify the client explicitly |
| Public request receives Bearer token | `defaultOAuth2AuthorizedClient` enabled on a shared WebClient | Separate HTTP clients, remove default, use explicit selection |
| Valid token yet API still returns 401 | Different audience, issuer mismatch, proxy header | Check Resource Server contract, not just expiry |
| New refresh token is not saved | Wrong manager/repository/persistence | Inspect success handler/storage |
| Two concurrent refresh requests | Rotation and concurrency | Evaluate single-flight/locking/versioned storage |
| Controller hangs | `.block()` missing timeout, slow downstream | Set timeouts, limit resources |
| `block()` throws error on non-blocking thread | Calling blocking method on Reactor event loop | Keep the reactive chain or use an appropriate client |
| GitHub OAuth2 login yields `OAuth2User`, not `OidcUser` | Provider is not OIDC | Do not force cast to OIDC; use appropriate Client registration |
| WebClient bean wired with wrong manager | Multiple managers of same type, ambiguous DI | Use `@Qualifier`/distinct bean names |
| User still logged in but API token is no longer valid | HTTP session and access token have separate lifecycles | Refresh/reconnect the specific connection; do not log out of the whole portal |

### 19.3. How to Diagnose Safely

In development environments, you can raise Spring Security logging enough to trace the flow:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

However, do not enable wire-level HTTP logging that could write Token Endpoint requests, Bearer headers, or cookies into shared logs.

A safer set of operational fields:

```text
event=reports_api_call
registrationId=company-api
principalCategory=authenticated_user
tokenPresent=true
httpStatus=403
oauth2Error=insufficient_scope
```

Do not use access tokens or `state` as correlation IDs in logs. For user/tenant data, apply appropriate privacy policies.

## 20. Testing Ideas Without Exposing Tokens

### 20.1. Testing Outbound Headers

A WebClient integration test can use an HTTP mock server to verify:

1. The call targets `https://reports-api.example.test/v1/reports` or the mock base URL.
2. The `Authorization` header has the Bearer format when an authorized client is selected.
3. A WebClient calling a public API **does not** send a token when no OAuth2 filter is attached.
4. When a request does not select a registration, the application does not accidentally send a default token.
5. Error responses 401/403 are mapped to domain errors as required by policy.

Never print actual token values into test logs or snapshots.

### 20.2. Testing Multiple Registrations

Given:

```text
registrationId=reports -> access token token-A
registrationId=billing -> access token token-B
```

Test to ensure:

- Reports API receives token A.
- Billing API receives token B.
- Public API receives no token.
- Requests attempting to use token B on Reports API are rejected according to client/service policy.
- No code path automatically attaches token A to a user-specified host.

### 20.3. Testing Refresh Token Rotation

Mock the Token Endpoint:

```text
Refresh 1:
  request refresh_token=RT-1
  response access_token=AT-2, refresh_token=RT-2

Refresh 2:
  request refresh_token=RT-2
  response access_token=AT-3, refresh_token=RT-3
```

The goal is to confirm the manager/repository saves the new token and stops using RT-1. For multi-instance systems, test race/concurrency conditions and `invalid_grant` handling policies.

These are **suggested test scenarios**, not a certification that the demo code has been executed or QA'd.

## 21. Practice Exercises

### Exercise 1: Choosing the Right Filter

A Spring Boot application has a Spring MVC controller, `SecurityFilterChain`, and `HttpServletRequest`. A developer chooses `ServerOAuth2AuthorizedClientExchangeFilterFunction` from a WebFlux guide.

**Question:** Is this appropriate?

**Suggested answer:** On the Servlet stack, you should use `ServletOAuth2AuthorizedClientExchangeFilterFunction` and the appropriate Servlet repository/manager. The `Server...` variant targets a reactive server context.

### Exercise 2: Attaching an Access Token for a Specific API

You have a `reportsWebClient` bean with an OAuth2 filter. Request the `company-api` registration on a `GET /v1/reports` call.

**Suggested answer:**

```java
reportsWebClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("company-api"))
    .retrieve()
    .bodyToMono(String.class);
```

### Exercise 3: Preventing Token Leakage to Public APIs

A shared WebClient enables `setDefaultOAuth2AuthorizedClient(true)` and calls both a private API and a public API on a different host.

**Suggested answer:** This risks sending the Bearer token to the wrong target. Separate out a public WebClient with no OAuth2 filter, and on the private client prefer explicit registration selection and restrict to trusted hosts.

### Exercise 4: Expired Token

A user's access token has expired; the Client holds a still-valid refresh token.

**Suggested answer:** The configured manager/provider can execute the Refresh Token Grant and update the authorized client. There is no need for the controller to manually parse the JWT and POST a token refresh if Spring Security is already managing it.

### Exercise 5: API Returns 401 Before `expiresAt`

**Suggested answer:** This can be caused by revocation, audience, or issuer. `expiresAt` is time metadata held by the Client; it does not prove the Resource Server will definitely accept the token.

### Exercise 6: Background Task Using WebClient

A `@Scheduled` job running outside an HTTP request needs to call an API using `client_credentials`.

**Suggested answer:** Use `AuthorizedClientServiceOAuth2AuthorizedClientManager` with a `clientCredentials()` provider and a stable service principal. Do not attempt to rely on a Servlet request/session.

### Exercise 7: Using an ID Token to Call a Resource Server

A developer sees `OidcUser#getIdToken()` and uses it in `Authorization: Bearer`.

**Suggested answer:** Wrong purpose. Use the access token from the authorized client with the API's correct audience and scope; the ID Token is only for identity verification at the OIDC Client.

### Exercise 8: WebClient Redirects to an Unknown Host

Reports API returns a 302 redirect to a user-supplied domain. WebClient is carrying a Bearer token.

**Suggested answer:** You must control redirects and ensure the `Authorization` header is not forwarded to untrusted hosts. Do not assume the connector always handles this safely without verifying its configuration.

### Exercise 9: Multiple Authorized Clients for One User

A user connects both `company-api` and `billing-api`. The reports controller calls WebClient with a default “current authorized client”.

**Suggested answer:** It is easy to pick the wrong one. Specify `clientRegistrationId("company-api")` or pass the exact `OAuth2AuthorizedClient` to avoid token leakage and wrong permissions.

### Exercise 10: 403 Due to Missing Scope

The API returns `insufficient_scope`. Should you automatically refresh the token 100 times?

**Suggested answer:** No. Refreshing a token usually does not grant additional permissions. You need to request the appropriate scope/consent or deny the operation per policy.

## 22. Design Checklist

- [ ] The application is Servlet MVC and uses the **Servlet** variant of the OAuth2 WebClient filter.
- [ ] `ClientRegistration` and the OIDC issuer are configured from a trusted provider.
- [ ] Access tokens are issued with the right **Resource Server audience/scope**; do not assume login implies permission for every API.
- [ ] WebClient has a trusted base URL and does not accept arbitrary external URLs.
- [ ] Requests explicitly specify `clientRegistrationId(...)` or `oauth2AuthorizedClient(...)`.
- [ ] Default authorized client is not enabled on a WebClient shared across multiple origins.
- [ ] Neither ID Tokens nor refresh tokens are placed into `Authorization: Bearer` for API calls.
- [ ] Repository/manager selection matches the Servlet context and user principal.
- [ ] There is a policy for refresh tokens/rotation and handling `invalid_grant`.
- [ ] Token Endpoint errors are distinguished from Resource Server HTTP 401/403 responses.
- [ ] When using the manager constructor, check the filter's failure handler for your version.
- [ ] For HTTP client redirects, control target hosts and the `Authorization` header.
- [ ] Timeouts and idempotency-aware retry limits are configured.
- [ ] Background jobs do not depend on a request-based manager.
- [ ] Tokens/secrets never appear in URLs, logs, or frontend responses.
- [ ] Test cases are planned for public APIs, multi-registration, and expired tokens.

## 23. References

1. [Spring Security Reference — OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): overview of OAuth2 Authorized Client and HTTP client integration.
2. [Spring Security Reference — Authorized Clients](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): configuring WebClient, selecting authorized clients, and failure handling.
3. [Spring Security API — ServletOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServletOAuth2AuthorizedClientExchangeFilterFunction.html): constructors, `clientRegistrationId(...)`, `oauth2AuthorizedClient(...)`, `oauth2Configuration()`, and default settings.
4. [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html): access token, refresh token, and ClientRegistration.
5. [Spring Security API — OAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html): managing authorization and reauthorization.
6. [Spring Security API — DefaultOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html): manager for Servlet HTTP requests.
7. [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): manager for tasks outside HTTP requests.
8. [Spring Security API — RegisteredOAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/annotation/RegisteredOAuth2AuthorizedClient.html): injecting the authorized client by registration in a controller.
9. [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): `ExchangeFilterFunction`, request/response, status handling, and Reactor.
10. [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): authorization code, access/refresh tokens, and the Token Endpoint.
11. [RFC 6750 — Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): `Authorization: Bearer` and `WWW-Authenticate` errors.
12. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): token management, permission constraints, and security practices.

## 24. Summary

**`ServletOAuth2AuthorizedClientExchangeFilterFunction` is the bridge between Spring Security OAuth2 Client on the Servlet stack and HTTP requests made with `WebClient`.** It enables an application to use the appropriate authorized client, integrate with a manager/repository to obtain or refresh access tokens when allowed, and attach the token to `Authorization: Bearer` for downstream APIs.

The non-negotiable rules are **explicitly selecting the ClientRegistration**, **using the principal's proper access token**, **protecting which HTTP targets are allowed to receive tokens**, and **distinguishing Token Endpoint errors from Resource Server errors**. Use `clientRegistrationId(...)` or `oauth2AuthorizedClient(...)` whenever possible, and avoid enabling a default authorized client on a shared WebClient. For schedulers/workers outside HTTP requests, switch to a service-based authorized client manager instead of depending on a Servlet request.

When these boundaries are properly maintained, Spring MVC can still leverage WebClient and Reactor to call OAuth2 APIs securely, centralize token lifecycle management, and reduce errors as the application grows.
