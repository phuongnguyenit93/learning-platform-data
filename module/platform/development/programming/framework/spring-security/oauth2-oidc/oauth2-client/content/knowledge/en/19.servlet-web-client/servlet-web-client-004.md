# 19.4. Selecting clientRegistrationId via Request Attributes

In **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client**, a Servlet application (Spring MVC) can use `WebClient` to call downstream APIs with an access token issued by an Authorization Server. If the application connects to only one API, default configuration is sometimes enough. However, when the backend calls multiple APIs, integrates with multiple identity providers, or uses both user tokens and `client_credentials` tokens, the application must **select the exact OAuth2 client registration for each outbound request**.

With Servlet OAuth2 Client integration, Spring Security provides `ServletOAuth2AuthorizedClientExchangeFilterFunction`. A common way to choose the registration is by passing a **request attribute** when building a `WebClient` call:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> result = webClient.get()
        .uri("https://reports-api.example.org/v1/reports")
        .attributes(clientRegistrationId("reports-client"))
        .retrieve()
        .bodyToMono(String.class);
```

This is the core idea of this lesson: `clientRegistrationId("reports-client")` puts a value into **the attributes of the individual `ClientRequest`** created by `WebClient`. If `WebClient` has the appropriate OAuth2 exchange filter installed, the filter uses that information to identify the `ClientRegistration`/`OAuth2AuthorizedClient` and attach the corresponding access token to the HTTP request sent to the API.

**Do not confuse this `request attribute` with an HTTP header, query parameter, cookie, or `HttpServletRequest` attribute.** It is internal coordination data between the application and `WebClient`'s `ExchangeFilterFunction`s; it does not automatically become a parameter sent to the Resource Server.

## 1. Context: WebClient in a Servlet Application

`WebClient` is a Reactor-based HTTP client, often introduced alongside Spring WebFlux. However, it **can be used in a Spring MVC/Servlet application** to call downstream APIs. In that setup:

- **Inbound** requests to the application are handled by the Servlet filter chain and `SecurityContextHolder`.
- **Outbound** requests are created by `WebClient` and can carry a bearer access token.
- `ServletOAuth2AuthorizedClientExchangeFilterFunction` bridges the two worlds by using the `Authentication` context, Servlet request/response when available, and the corresponding `OAuth2AuthorizedClientManager` or repository.
- The Resource Server on the receiving end still validates the access token on its own against issuer, audience, expiration, scope, and API policy.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant M as Spring MVC + SecurityContext
    participant W as WebClient
    participant F as Servlet OAuth2 Exchange Filter
    participant S as Authorized Client Store
    participant OP as Authorization Server
    participant A as Reports API
    B->>M: GET /dashboard/reports
    M->>W: GET Reports API, attribute registrationId
    W->>F: ClientRequest + attributes
    F->>S: Look up authorized client by registration + principal
    alt Missing or needs reauthorization
        F->>OP: OAuth2 authorize/refresh per grant and context
        OP-->>F: New access token
        F->>S: Save authorized client when appropriate
    end
    F->>A: GET /reports, Bearer Access Token
    A-->>W: HTTP response
    W-->>M: Report data
    M-->>B: Dashboard response
```

This diagram illustrates overall responsibilities and does not imply every registration can run a login flow inside a single HTTP call. With `authorization_code`, initial authorization requires a browser and an Authorization Request/Callback; the filter cannot simulate user interaction with an OpenID Provider on its own.

### 1.1. Goal of Explicit Selection

A backend may hold:

| Registration ID | Grant | Purpose |
|---|---|---|
| `company-login` | `authorization_code` | Users sign in with OIDC via the Corporate OP; issued access token can be used for appropriate APIs |
| `partner-login` | `authorization_code` | Users sign in via the Partner OP, obtaining a token tied to the partner account |
| `inventory-service` | `client_credentials` | Backend/job calls the Inventory API under the application's own authority |
| `audit-service` | `client_credentials` | Backend calls the Audit API using a dedicated service account |

Without explicit selection, a default registration might be applied to unsuitable requests, or no registration might be selected at all. Setting `clientRegistrationId` per call makes the source code clearly state **which API maps to which OAuth2 client**.

### 1.2. Selecting a Client Registration Is Different from Selecting a User Account

`clientRegistrationId` is the key Spring Security uses to look up a `ClientRegistration`. It is not:

- the `client-id` issued by the Authorization Server;
- the name of the user's `OAuth2AuthorizedClient`;
- the OIDC `sub` or `iss` in an ID Token;
- an authorization `scope` or `audience`;
- a bearer token that can be placed in a header;
- a browser session ID.

Actual principal and authorized client data still matter. The same `registrationId` can correspond to distinct authorized clients for Alice and Bob, or to a service principal used in `client_credentials`.

## 2. ClientRegistration, OAuth2AuthorizedClient, and clientRegistrationId

To understand a line like `.attributes(clientRegistrationId("reports-client"))`, start from three Spring Security types.

### 2.1. ClientRegistration

`ClientRegistration` holds the OAuth2 client configuration, for example:

```text
registrationId = "reports-client"
clientId       = "reports-portal-prod"
grantType      = "authorization_code"
provider       = "company-idp"
scopes         = ["openid", "profile", "reports.read"]
redirectUri    = "{baseUrl}/login/oauth2/code/{registrationId}"
```

Spring Boot typically reads configuration from `spring.security.oauth2.client.registration.*` and constructs a `ClientRegistrationRepository`.

### 2.2. OAuth2AuthorizedClient

`OAuth2AuthorizedClient` represents a registration **that has been authorized** in a principal's context. It holds the registration, principal name, access token, and refresh token if present. Hence there can be:

```text
(reports-client, alice) -> Alice's Access Token
(reports-client, bob)   -> Bob's Access Token
(audit-service, service:audit-export) -> Service's Access Token
```

`clientRegistrationId(...)` only selects the **registration** for a call; the filter/manager must still locate the right authorized client by **principal**, storage, and grant.

### 2.3. WebClient Request Attributes

A WebClient `ClientRequest` carries a URL, HTTP method, headers, body, and attributes. `attributes(...)` is a DSL for client-side processing metadata, for example:

```java
webClient.get()
        .uri("https://reports-api.example.org/v1/summary")
        .attributes(clientRegistrationId("reports-client"))
        .retrieve()
        .bodyToMono(String.class);
```

Here Spring Security reads the attribute to choose the registration; **the Resource Server does not receive the string `reports-client` as a separate HTTP header**, unless the application explicitly writes other logic to send it.

## 3. Basic Configuration of a WebClient with the Servlet OAuth2 Filter

For Spring MVC, main starters and components:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

`spring-boot-starter-webflux` can be included to obtain `WebClient` and Reactor Netty as an HTTP client, **without requiring the application to become a WebFlux server** when Spring MVC remains the primary web stack. Spring Boot auto-detection and combining both starters should be verified for your application version.

Example OAuth2 Client declaration in `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company-login:
            provider: company
            client-id: "${COMPANY_CLIENT_ID}"
            client-secret: "${COMPANY_CLIENT_SECRET}"
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, reports.read]
          inventory-service:
            provider: company
            client-id: "${INVENTORY_CLIENT_ID}"
            client-secret: "${INVENTORY_CLIENT_SECRET}"
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [inventory.read]
        provider:
          company:
            issuer-uri: "https://idp.example.org/realms/company"
```

The provider must permit the corresponding scopes and redirect URIs. `reports.read` and `inventory.read` are non-standard illustrative scopes that must be supported by the Authorization Server. Client secrets must come from a secret manager/environment variables, never hard-coded into Git.

### 3.1. Creating WebClient via ClientRegistrationRepository and AuthorizedClientRepository

Integration for Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class OAuth2WebClientConfig {

    @Bean
    WebClient oauth2WebClient(
            ClientRegistrationRepository clientRegistrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        var oauth2 =
                new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                        clientRegistrations, authorizedClients);

        return WebClient.builder()
                .apply(oauth2.oauth2Configuration())
                .build();
    }
}
```

`oauth2Configuration()` registers the exchange filter and the integration settings it provides. This is **`ServletOAuth2AuthorizedClientExchangeFilterFunction`**, not `ServerOAuth2AuthorizedClientExchangeFilterFunction` meant for a WebFlux server.

With this setup, the filter must receive sufficient context from the Servlet request and Authentication to find the right authorized client. Depending on execution context and initialization, you can also configure the filter with a dedicated `OAuth2AuthorizedClientManager` (see section 8).

### 3.2. Configuring SecurityFilterChain for User Login

If client `company-login` serves OIDC Login:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/", "/error").permitAll()
                        .anyRequest().authenticated())
                .oauth2Login(Customizer.withDefaults())
                .build();
    }
}
```

Users can initiate login at `/oauth2/authorization/company-login`. After a successful callback, Spring Security creates an `Authentication` and saves the login's authorized client via the configured repository/service.

**Having a configured registration does not mean authorization has already completed.** If a user has never authorized another registration, selecting that registration in WebClient does not guarantee the backend already has an access token to call the API.

## 4. Selecting the Registration Directly on Each WebClient Request

The key helper is:

```java
ServletOAuth2AuthorizedClientExchangeFilterFunction
        .clientRegistrationId("company-login")
```

Used in the DSL:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<ReportSummary> result = webClient.get()
        .uri("https://reports-api.example.org/v1/summary")
        .attributes(clientRegistrationId("company-login"))
        .retrieve()
        .bodyToMono(ReportSummary.class);
```

This example assumes:

1. `webClient` was created with the Servlet OAuth2 filter from section 3.
2. The current user has logged in via `company-login` and the authorized client holds a suitable access token.
3. The token has the scope/audience required by the Reports API.
4. `ReportSummary` is an application-implemented DTO.

`clientRegistrationId(...)` is **not a method on `WebClient`**, but an OAuth2 filter helper that returns a consumer to add metadata to `ClientRequest` attributes.

### 4.1. Calling from a Spring MVC Service

A Servlet service can use WebClient while returning synchronously at the service boundary:

```java
import java.time.Duration;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

@Service
class ReportsGateway {

    private final WebClient oauth2WebClient;

    ReportsGateway(WebClient oauth2WebClient) {
        this.oauth2WebClient = oauth2WebClient;
    }

    ReportSummary loadSummary() {
        return oauth2WebClient.get()
                .uri("https://reports-api.example.org/v1/summary")
                .attributes(clientRegistrationId("company-login"))
                .retrieve()
                .bodyToMono(ReportSummary.class)
                .block(Duration.ofSeconds(5));
    }
}
```

`block(Duration)` can be used on a blocking Servlet thread when the architecture permits, but should never be used on a Reactor event loop. Configure HTTP client **connect/read/response timeouts**, handle `null`/timeout errors, and avoid holding Servlet threads indefinitely. This code is illustrative; production APIs also need trusted base URLs, retry policies, circuit breakers, and business authorization.

### 4.2. Switching Registration by Operation Type, Not Arbitrary User Input

Suppose two **server-determined** flows exist:

```java
Mono<String> companyResult = oauth2WebClient.get()
        .uri("https://reports-api.example.org/v1/public-summary")
        .attributes(clientRegistrationId("company-login"))
        .retrieve()
        .bodyToMono(String.class);

Mono<String> partnerResult = oauth2WebClient.get()
        .uri("https://partner-api.example.org/v1/account")
        .attributes(clientRegistrationId("partner-login"))
        .retrieve()
        .bodyToMono(String.class);
```

`partner-login` must be registered, and the user must hold an appropriate authorized client if it is an authorization-code registration. You cannot simply use `company-login`'s token as `partner-login`'s token.

If the service chooses dynamically by operation, use an allowlist instead of accepting a raw `registrationId` in request queries/bodies:

```java
enum DataSource {
    COMPANY_REPORTS,
    PARTNER_ACCOUNT
}

record OutboundTarget(String registrationId, String baseUrl) {}

static final Map<DataSource, OutboundTarget> TARGETS = Map.of(
        DataSource.COMPANY_REPORTS,
        new OutboundTarget(
                "company-login",
                "https://reports-api.example.org"),
        DataSource.PARTNER_ACCOUNT,
        new OutboundTarget(
                "partner-login",
                "https://partner-api.example.org"));
```

This is an illustrative routing table. Before selecting a target, the application must still verify that the user is authorized to use that data source and access the corresponding account/tenant.

### 4.3. Specifying the Attribute on the Final Request

A helpful guideline is placing `clientRegistrationId` **right alongside the target API URL**:

```java
webClient.post()
        .uri("https://billing-api.example.org/v1/invoices")
        .attributes(clientRegistrationId("billing-writer"))
        .bodyValue(invoiceRequest)
        .retrieve()
        .bodyToMono(InvoiceReceipt.class);
```

Reading this snippet, it is immediately clear the request uses registration `billing-writer`. However, **the OAuth2 filter only adds the authorization header when an authorized client already exists or can be authorized under the configured grant**. For instance, `billing-writer` must exist in `ClientRegistrationRepository` and be wired with an appropriate manager mechanism.

For business HTTP POSTs, do not blindly replay requests just because a token expired or the API returned 401; consider idempotency and the Billing API contract.

## 5. Why Request Attributes Are Better Than an Uncontrolled Default Registration

`ServletOAuth2AuthorizedClientExchangeFilterFunction` provides default configuration options, such as using a default registration ID or using the authorized client tied to the current authentication. These features work well in apps calling a single API, but carry risks when a WebClient is reused across **multiple hosts and APIs**.

### 5.1. setDefaultClientRegistrationId

Example:

```java
var oauth2 =
        new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                registrations, authorizedClientRepository);

oauth2.setDefaultClientRegistrationId("inventory-service");

WebClient client = WebClient.builder()
        .apply(oauth2.oauth2Configuration())
        .build();
```

With this WebClient, if a request does not explicitly specify a registration, the filter can fall back to the default `inventory-service`. This works well when **the entire WebClient is dedicated solely to the Inventory API** and token access permissions are properly configured.

However, a shared WebClient calling Inventory, Billing, and Partner APIs could accidentally send tokens to the wrong recipient. With multiple targets, prefer explicit `.attributes(clientRegistrationId(...))` and allowlisted URL routing.

### 5.2. setDefaultOAuth2AuthorizedClient(true)

Another option is using the authorized client from the current authentication as the default:

```java
oauth2.setDefaultOAuth2AuthorizedClient(true);
```

This can be very convenient if every outbound call targets APIs meant for the user's login token. Yet if a shared WebClient is used to call arbitrary URLs, **the user's token may be attached to unintended requests**, including other hosts that the developer never intended to receive credentials.

**Design recommendation:** in systems calling multiple APIs or multiple OAuth2 clients, avoid attaching tokens by default to every request. Pick the registration/authorized client explicitly at the call site, or split WebClients by host and policy.

### 5.3. Comparing Token Selection Approaches

| Selection Approach | Example | When Suitable |
|---|---|---|
| Registration per request | `.attributes(clientRegistrationId("company-login"))` | Multiple clients/APIs requiring explicitness |
| Specific authorized client | `.attributes(oauth2AuthorizedClient(client))` | Already hold a valid authorized client object and want to use that exact object |
| Default registration on filter | `setDefaultClientRegistrationId(...)` | WebClient dedicated to a single registration |
| Default authorized client from Authentication | `setDefaultOAuth2AuthorizedClient(true)` | Only when every request on the WebClient is allowed to carry the current Authentication's token |
| Manually setting Bearer token | `headers(h -> h.setBearerAuth(...))` | Only in integrations with careful manual token lifecycle management; error-prone/leaky if used instead of the filter |

Do not rely on assumptions about precedence when code supplies multiple sources simultaneously. For complex APIs, choose **one explicit source** and verify the exact contract of your Spring Security version.

## 6. Request Attributes: What Is Passed and What Is Not?

A call like:

```java
webClient.get()
        .uri("https://reports-api.example.org/v1/reports")
        .attributes(clientRegistrationId("company-login"))
        .retrieve()
        .bodyToMono(String.class);
```

can be understood as:

```text
ClientRequest (inside WebClient)
    method     = GET
    url        = https://reports-api.example.org/v1/reports
    attributes = {
        oauth2.clientRegistrationId: "company-login"  # internal key name defined by the filter
    }
    |
    v
ServletOAuth2AuthorizedClientExchangeFilterFunction
    |
    +-- reads attribute, resolves authorized client
    +-- attaches Authorization: Bearer <ACCESS_TOKEN> when appropriate
    |
    v
HTTP request to Reports API
    GET /v1/reports
    Authorization: Bearer <ACCESS_TOKEN>
```

The key name in the diagram is **illustrative of its meaning**, not a constant name that applications should hard-code. Always use the public helper `clientRegistrationId(...)` to avoid coupling to implementation details.

### 6.1. Not a Servlet HTTP Request Attribute

In Spring MVC:

```java
servletRequest.setAttribute("tenantId", "tenant-north");
```

stores data on `HttpServletRequest`. Conversely:

```java
webClient.get()
        .uri(target)
        .attributes(clientRegistrationId("company-login"));
```

puts metadata into WebClient's `ClientRequest`. These two maps do not synchronize automatically.

If choosing a registration based on a tenant in the Servlet request, the application must **verify the tenant first**, map it via backend policy, and pass the approved registration to WebClient.

### 6.2. Not an HTTP Query Parameter

Calling `clientRegistrationId(...)` does **not** cause:

```text
https://reports-api.example.org/reports?clientRegistrationId=company-login
```

to be appended to the URL. The downstream API receives a bearer token and does not need to know the BFF's internal registration name.

### 6.3. Not `OAuth2AuthorizeRequest.attributes`

Spring Security also has another API:

```java
OAuth2AuthorizeRequest.withClientRegistrationId("company-login")
        .principal(authentication)
        .attributes(attrs -> attrs.put("app.operation", "reports.read"))
        .build();
```

These are attributes on **`OAuth2AuthorizeRequest`** passed into `OAuth2AuthorizedClientManager`. They are not the same thing as **WebClient's `ClientRequest.attributes`**, even though adapters/filters may forward certain details per contract.

Specifying `clientRegistrationId` in WebClient has one specific purpose: **selecting the registration**. Do not put custom attributes there expecting them to be forwarded to the token endpoint or alter OAuth2 scopes automatically.

## 7. Selecting by Registration vs. Specifying OAuth2AuthorizedClient

If the application already holds an `OAuth2AuthorizedClient` object retrieved through a trusted mechanism, the helper:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

webClient.get()
        .uri("https://reports-api.example.org/v1/summary")
        .attributes(oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class);
```

specifies the already-authorized client instead of asking the filter to resolve by registration name.

| Criterion | `clientRegistrationId("x")` | `oauth2AuthorizedClient(client)` |
|---|---|---|
| Input | Registration ID string | Authorized client object |
| Selecting client config | Filter/manager looks up by registration ID | Registration is already inside the authorized client |
| Binding to principal | Filter/manager must determine the right principal | Object already has `principalName`, though ownership policy still applies |
| When to use | Explicit at call site, want manager to resolve/reauthorize | Already hold authorized client from repository/service/argument resolver |
| Risk if sourced from untrusted input | Picking the wrong registration/overly broad permissions | Using another user's token if a service returns a client for the wrong owner |

**Never accept an arbitrary user-chosen authorized client.** The backend must guarantee that the authorized client belongs to the exact principal and registration the caller is permitted to use.

### 7.1. Interaction with `@RegisteredOAuth2AuthorizedClient`

Spring Security Servlet provides the argument resolver:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@RestController
class PortfolioController {

    private final WebClient webClient;

    PortfolioController(WebClient webClient) {
        this.webClient = webClient;
    }

    @GetMapping("/portfolio")
    String portfolio(
            @RegisteredOAuth2AuthorizedClient("company-login")
            OAuth2AuthorizedClient client) {

        return webClient.get()
                .uri("https://reports-api.example.org/v1/portfolio")
                .attributes(oauth2AuthorizedClient(client))
                .retrieve()
                .bodyToMono(String.class)
                .block(java.time.Duration.ofSeconds(5));
    }
}
```

This illustrates a secured endpoint accessed after OAuth2 Login. The controller does not return the access token to the browser; it uses the token on the backend to call the Reports API. You still need to handle missing authorized clients and real API errors.

### 7.2. If an Authorized Client Is Already Specified, Is Registration ID Still Needed?

Normally you do not need to supply both for the same selection: `OAuth2AuthorizedClient` already holds its registration. Combining both mechanisms simultaneously can confuse developers and complicate diagnostics.

For clarity, each request should pick **one approach**:

```java
.attributes(clientRegistrationId("company-login"))
```

or:

```java
.attributes(oauth2AuthorizedClient(client))
```

For security-sensitive methods, verify the principal's authority/tenant before using the client.

## 8. Using `OAuth2AuthorizedClientManager` with Servlet WebClient

When an application has its own manager configuration, `ServletOAuth2AuthorizedClientExchangeFilterFunction` accepts `OAuth2AuthorizedClientManager` directly instead of constructing one from repositories.

### 8.1. Creating a Manager for Servlet Requests

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
class ServletAuthorizedClientConfig {

    @Bean
    OAuth2AuthorizedClientManager servletAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository repository) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .clientCredentials()
                        .build();

        var manager = new DefaultOAuth2AuthorizedClientManager(
                registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

`authorizationCode()` is for flows with browser Authorization Requests/Callbacks; `refreshToken()` handles renewals when a refresh token exists; `clientCredentials()` supports service tokens as configured. Do not enable unused grants just to be “feature-complete”; the provider list should match your architecture.

### 8.2. Attaching the Manager to the Filter

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
WebClient oauth2WebClient(OAuth2AuthorizedClientManager servletAuthorizedClientManager) {

    var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
            servletAuthorizedClientManager);

    return WebClient.builder()
            .filter(oauth2)
            .build();
}
```

This is an **alternative configuration** to the WebClient in section 3; do not register two beans with the same name and purpose in a real application. If the application has multiple manager beans, use explicit qualifiers so Spring does not accidentally inject a service manager instead of the Servlet manager.

### 8.3. Why Do the Manager and Storage Matter?

In Servlet:

- `DefaultOAuth2AuthorizedClientManager` works with `OAuth2AuthorizedClientRepository` and the Servlet request/response context.
- `AuthorizedClientServiceOAuth2AuthorizedClientManager` works with `OAuth2AuthorizedClientService`, typically suited for background/service tasks outside web requests.

If authorized clients are stored in an HTTP session repository, a separate service manager will not necessarily see those tokens. Even if both receive `clientRegistrationId("company-login")`, outcomes differ when **storage or principal does not match**.

For `client_credentials` in a backend handling both web traffic and background jobs, you usually want a **separate service token manager** with a stable logical principal rather than storing service tokens per browser user.

## 9. Passing Servlet Request/Response and Authentication When Needed

In many Servlet controllers, the filter can pull `Authentication` and the HTTP request/response from the current Spring Security/Spring MVC context. However, asynchronous flows, callbacks running on another thread, schedulers, or components invoking WebClient outside a request may **lack thread-local Servlet context**.

Spring Security provides helpers to pass context explicitly in request attributes when needed, for example:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.authentication;
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.servletRequest;
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.servletResponse;
import static org.springframework.security.oauth2.client.web.reactive.function.client
        .ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> response = webClient.get()
        .uri("https://reports-api.example.org/v1/summary")
        .attributes(clientRegistrationId("company-login"))
        .attributes(authentication(authentication))
        .attributes(servletRequest(request))
        .attributes(servletResponse(response))
        .retrieve()
        .bodyToMono(String.class);
```

In this snippet, `authentication`, `request`, and `response` passed to the helper are variables from the controller/service context; naming a variable `response` while also declaring `Mono<String> response` should be avoided in real code. A clearer naming:

```java
Mono<String> downstreamResult = webClient.get()
        .uri("https://reports-api.example.org/v1/summary")
        .attributes(clientRegistrationId("company-login"))
        .attributes(authentication(currentAuthentication))
        .attributes(servletRequest(httpServletRequest))
        .attributes(servletResponse(httpServletResponse))
        .retrieve()
        .bodyToMono(String.class);
```

This code illustrates passing context when those variables have already been obtained from an application Servlet method. It does not turn a background job into a browser login, nor does it authorize on a user's behalf.

**Never retain `HttpServletRequest` or `HttpServletResponse` in static fields, caches, or long-running queues.** They have request-scoped lifecycles and may become invalid by the time an async task runs. In background jobs, choose a manager/service storage that does not depend on Servlet.

### 9.1. The Principal Must Come from an Authenticated Source

Dangerous example:

```java
// DO NOT DO THIS: principalName sent by the browser used to fetch another user's token.
String selectedUser = httpServletRequest.getParameter("principalName");
```

Then constructing a fake Authentication for `selectedUser` to resolve an authorized client can cause token leakage or unauthorized access to another user's data. When using a user's bearer token, the principal must come from the authenticated `SecurityContext` and backend tenant/resource policies.

### 9.2. Reactor Context and Thread-Local Are Not the Same

`WebClient` uses Reactor publishers. In an asynchronous call chain, the executing thread can switch. Never assume thread-local `SecurityContextHolder` always exists on every Reactor scheduler or callback.

If execution crosses schedulers/threads, **pass the needed Authentication/context explicitly via supported APIs**, or use context propagation supported by your Spring version. Do not read thread-locals in an uncontrolled callback and falsely conclude a null principal means the token expired.

## 10. Selecting Registrations by Business Operation: Safe Design

A reporting portal has two APIs:

```text
Operation: READ_FINANCE_REPORTS
    -> registrationId: company-login
    -> URL: https://reports-api.example.org

Operation: READ_PARTNER_ACCOUNT
    -> registrationId: partner-login
    -> URL: https://partner-api.example.org
```

Selection can be performed by a server-side service:

```java
enum DownstreamOperation {
    FINANCE_REPORTS,
    PARTNER_ACCOUNT
}

record OAuth2Target(
        String registrationId,
        String endpoint) {}

final class TargetRegistry {

    private static final Map<DownstreamOperation, OAuth2Target> TARGETS =
            Map.of(
                    DownstreamOperation.FINANCE_REPORTS,
                    new OAuth2Target(
                            "company-login",
                            "https://reports-api.example.org/v1/finance"),
                    DownstreamOperation.PARTNER_ACCOUNT,
                    new OAuth2Target(
                            "partner-login",
                            "https://partner-api.example.org/v1/account"));

    static OAuth2Target forOperation(DownstreamOperation operation) {
        OAuth2Target target = TARGETS.get(operation);
        if (target == null) {
            throw new IllegalArgumentException("Unsupported operation");
        }
        return target;
    }
}
```

Service using the registry:

```java
Mono<String> load(DownstreamOperation operation) {
    OAuth2Target target = TargetRegistry.forOperation(operation);

    return webClient.get()
            .uri(target.endpoint())
            .attributes(clientRegistrationId(target.registrationId()))
            .retrieve()
            .bodyToMono(String.class);
}
```

This is an example of **server-side configuration routing**, not an authorization policy. Before calling `load`, the application must verify that the user is allowed to perform the operation and access the corresponding partner account and tenant. Even if the browser can pass an enum operation, the service must still block unauthorized operations.

### 10.1. Why Not Accept registrationId Directly Through an API?

Anti-pattern:

```java
@GetMapping("/proxy")
String proxy(
        @RequestParam String clientRegistrationId,
        @RequestParam String url) {

    return webClient.get()
            .uri(url)
            .attributes(clientRegistrationId(clientRegistrationId))
            .retrieve()
            .bodyToMono(String.class)
            .block();
}
```

This code is **unsafe** because a caller can:

1. Pick a registration with higher privileges than their own.
2. Change the URL to an attacker-controlled host.
3. Once the filter attaches the bearer token, exfiltrate the token to an untrusted server.
4. Use the backend as a proxy into the internal network (SSRF).

The fix is not merely a regex on registration ID: you must bind **operation → registration → target URL/API → user/tenant permissions** via server-side allowlists and authorization.

### 10.2. Registration ID Is Not a Security Permission

Selecting `company-login` does not prove a user is permitted to export all reports. It only tells the filter which kind of authorized client to pick. The receiving API must validate the access token and object-level permissions.

Similarly, a registration with scope `reports.read` does not automatically mean the user can read every organization's reports. Object-level authorization still must be enforced at the Resource Server/service.

## 11. Client Credentials via Servlet WebClient

Beyond user-delegated tokens, a Servlet application can also call APIs using the backend's own `client_credentials` token. However, if you let the Servlet filter pick the principal from the currently logged-in user, service tokens can end up stored per user, creating unnecessary duplicate entries.

### 11.1. Dedicated Manager for Background/Service Identity

Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClients) {

    var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                    registrations, authorizedClients);

    manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build());

    return manager;
}
```

Service layer using a stable logical principal:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

OAuth2AuthorizeRequest authorizeRequest =
        OAuth2AuthorizeRequest.withClientRegistrationId("inventory-service")
                .principal("service:inventory-sync")
                .build();

OAuth2AuthorizedClient authorized =
        serviceAuthorizedClientManager.authorize(authorizeRequest);

if (authorized == null) {
    throw new IllegalStateException("Cannot authorize inventory-service");
}
```

This snippet acquires a token via the manager outside a browser and needs no `OidcUser`. If you want to use WebClient, you can create a separate WebClient with a filter backed by the service manager, **or use the token returned by the manager** via an appropriate integration; never use default user authentication to select a service principal.

### 11.2. A Separate WebClient for Service Tokens

```java
@Bean
WebClient serviceWebClient(
        @Qualifier("serviceAuthorizedClientManager")
        OAuth2AuthorizedClientManager manager) {

    var oauth2 = new ServletOAuth2AuthorizedClientExchangeFilterFunction(
            manager);

    return WebClient.builder()
            .filter(oauth2)
            .build();
}
```

If calling `serviceWebClient` from a job that has no `Authentication` in `SecurityContext`, the cleanest control is **supplying a server-created logical service principal through the integration API**:

```java
Mono<String> inventory = serviceWebClient.get()
        .uri("https://inventory-api.example.org/v1/items")
        .attributes(clientRegistrationId("inventory-service"))
        .attributes(
                ServletOAuth2AuthorizedClientExchangeFilterFunction.authentication(
                        serviceAuthentication))
        .retrieve()
        .bodyToMono(String.class);
```

`serviceAuthentication` must be an identity **created and trusted by the backend application**, never taken from the browser. In many background jobs, invoking the manager directly with `.principal("service:inventory-sync")` as in section 11.1 is clearer; you can then pass `oauth2AuthorizedClient(authorized)` on the request if you want to feed the resolved authorized client into the filter.

Never turn a client credentials token into an end-user identity; the BFF must still check the user/operation before executing sensitive work with a service credential.

### 11.3. Scoping to the Target API's Token

When `inventory-service` has scope `inventory.read`, send that token only to the configured Inventory API. Never use an `inventory-service` access token to call the Partner API merely because WebClient can connect to any URL.

The Resource Server must check `aud`/resource, issuer, expiration, scope, and policy. `clientRegistrationId` is a client-side choice and **does not replace API-side token validation**.

## 12. Multiple Issuers, Multiple Tenants, and Same Registration Name

A system may integrate:

```text
registrationId "company-login" -> Corporate OP
registrationId "partner-login" -> Partner OP
registrationId "inventory-service" -> Corporate service realm
```

Each `ClientRegistration` must point to the right provider, token endpoint, client ID, scopes, and client authentication method. Selecting the wrong registration can cause:

- The filter failing to find an authorized client.
- Requests hitting a different Authorization Server where the client is not registered.
- Access tokens having an issuer/audience different from what the API expects.
- Token leakage to an unauthorized recipient if HTTP routing is also misconfigured.
- A user from a partner provider receiving internal employee policies if identity linking is wrong.

### 12.1. A Tenant ID Is Not Automatically a Registration ID

If a SaaS has tenants A and B:

```text
tenant-a -> registrationId partner-a-client
tenant-b -> registrationId partner-b-client
```

You can use a registry mapping verified tenants to their dedicated registrations. Never write:

```java
String registrationId = "partner-" + request.getParameter("tenant") + "-client";
```

and treat the result as trustworthy. First verify that the user/job has access to the tenant; then retrieve the registration from a protected server-side configuration source.

### 12.2. Principal Name and Token Storage

`OAuth2AuthorizedClientService` usually keys by `(registrationId, principalName)`. For user logins, `principalName` may be `Authentication.getName()`/OIDC `sub` depending on configuration. For service jobs, it is usually a logical service name.

If one registration serves multiple tenants sharing the same `principalName` and the tokens actually carry different permissions, evaluate isolation in both storage and the Authorization Server. Changing the `clientRegistrationId` request attribute alone is **not enough** to resolve every tenant conflict.

Likewise, an OIDC `sub` is only stable within its issuer's context. Never automatically merge local users across two issuers based solely on a subject string or email.

## 13. When a Registration Has No Authorized Client

Distinguish between two categories of registrations:

| Grant | When No Authorized Client Exists | Can Handle Automatically in a Background Request? |
|---|---|---|
| `client_credentials` | Manager can use client credentials to request a new token | Yes, with valid client registration, credentials, and network |
| `authorization_code` | Requires user authorization via a browser per protocol | Cannot fabricate an authorization code from a headless job |
| `refresh_token` | Requires a valid refresh token already bound to a prior authorized client | Cannot mint a refresh token if none was issued |

Suppose a user logs in via `company-login`, yet WebClient code specifies:

```java
.attributes(clientRegistrationId("partner-login"))
```

If there is no `partner-login` authorized client yet, the call may fail or attempt to trigger an authorization flow depending on manager/config—it cannot silently convert a Corporate OP token into a Partner OP token. The application must display or redirect the user to the appropriate flow if it intends to allow linking/signing in to that provider.

### 13.1. Registration Mismatch with Resource Audience

Having an authorized client does not mean its token works with every API. For example:

```text
company-login token:
    aud = portal-client
    scope = openid profile

Reports API expects:
    aud = reports-api
    scope = reports.read
```

In that case `company-login` can log in successfully, yet the token will be rejected by the Reports API. The fix is updating the token issuance/provider contract or the corresponding registration/authorization—**never removing audience validation on the API**.

## 14. Debugging Errors When Selecting clientRegistrationId

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Outbound request lacks Authorization header | WebClient missing OAuth2 filter; no authorized client; wrong principal context; filter cannot resolve | Verify WebClient bean, `clientRegistrationId` helper, manager, and storage |
| `clientRegistrationId` does not exist | Typo in registration name; passed `clientId` instead of registration ID | Check `spring.security.oauth2.client.registration` and internal keys |
| Filter uses unexpected token | Default registration/authorized client mixed with per-request selection; different mapper or manager | Pick one explicit source; inspect filter configuration |
| OIDC login succeeds yet API returns 403 | Access token lacks scope/audience or user lacks report permissions | Inspect API contract, resource policy, and matching registration |
| Calling partner API prompts for login again | No authorized client yet for `partner-login` | Initiate a supported authorization flow and inform the user |
| MVC app sees WebClient lose Authentication | Different reactive thread/thread switch, outside Servlet request, or wrong context passed | Pass valid context explicitly or use an appropriate manager |
| Batch job reports missing Servlet request | Using HTTP-request-based `DefaultOAuth2AuthorizedClientManager` outside web context | Use a service manager for background jobs |
| Service tokens saved per user instead of shared | `client_credentials` using principal from web user's SecurityContext | Use a stable logical service principal and service manager |
| API A's token sent to API B | WebClient uses default token across multiple hosts or input-controlled URL | Separate WebClients per target, allowlist routing, select registration explicitly |
| Access token expired and API returns 401 | Client failed to refresh/reauthorize or used a stale token | Check provider chain, refresh token, expiration, and manager |
| One user gets another user's token | Principal name spoofed or client loaded without ownership check | Get Authentication from SecurityContext; verify identity/tenant |
| Tokens missing after deploy | In-memory/node-local session storage; principal name changed | Check repository/service, session stickiness/shared store, and keys |

### 14.1. Quick Diagnostic Flowchart

```mermaid
flowchart TD
    A["WebClient OAuth2 request fails"] --> B{"Has Servlet OAuth2 filter?"}
    B -- No --> C["Configure ServletOAuth2AuthorizedClientExchangeFilterFunction"]
    B -- Yes --> D{"Correct clientRegistrationId?"}
    D -- No --> E["Check ClientRegistrationRepository and routing"]
    D -- Yes --> F{"Correct principal and storage?"}
    F -- No --> G["Check Authentication, repository/service, session"]
    F -- Yes --> H{"Authorized client or suitable grant exists?"}
    H -- No --> I["Perform user authorization or client_credentials per contract"]
    H -- Yes --> J{"Token matches target API?"}
    J -- No --> K["Check issuer, audience, scope, URL routing"]
    J -- Yes --> L{"Business policy allows it?"}
    L -- No --> M["Check tenant/resource authorization"]
    L -- Yes --> N["Check downstream HTTP/network errors"]
```

Do not start by printing the raw access token to logs and decoding it: tokens and headers may contain sensitive credentials. Separate errors in **registration selection**, **authorized client storage**, **token issuance**, and **Resource Server authorization**.

### 14.2. Safe Observability

A controlled log can record:

```text
operation=reports.summary
oauth2.registrationId=company-login
downstream=reports-api
outbound.status=403
correlationId=server-generated
```

Avoid putting `principalName`/tenant ID into high-cardinality metric labels or exposing personal data. Strictly avoid logging:

- `Authorization: Bearer ...`;
- `client-secret`, private keys/client assertions;
- access tokens, refresh tokens, ID Tokens;
- authorization codes, PKCE verifiers, session cookies;
- full HTTP token request/response bodies or complete OIDC claims.

To verify a token came from the right registration, rely on approved observable metadata such as `registrationId`, fixed downstream host, error codes, expected scopes, and API authorization results — never log raw tokens.

## 15. Testing Registration Selection

A system calling two APIs should have independent test layers:

| Test Level | What to Prove |
|---|---|
| Routing unit test | Permitted operations select the right registration ID and URL; non-allowlisted operations are rejected |
| OAuth2 filter integration | `.attributes(clientRegistrationId("x"))` causes the filter to use the right authorized client in test context |
| Spring MVC integration | After OIDC Login, the right user's principal and authorized client are used on outbound calls |
| Multi-registration | Registration A never leaks or mixes with B's token |
| Client credentials | Backend obtains service token with a stable principal, independent of browser users |
| Token expiry | When a token expires, manager refreshes/reauthorizes per the appropriate grant |
| Resource Server contract | API rejects tokens with wrong issuer/audience/scope |
| SSRF/token leak | Browser input cannot alter URL or registration to send bearer tokens to unauthorized hosts |
| Concurrent requests | Concurrent requests never mix up Alice/Bob or tenant A/B tokens |

### 15.1. A Test Idea with Dummy Tokens

Suppose the test token store holds:

```text
(company-login, alice) -> fake-company-access-token
(partner-login, alice) -> fake-partner-access-token
```

With the filtered WebClient and downstream mock servers:

1. Call Reports API with `clientRegistrationId("company-login")`.
2. Reports API mock server receives `Authorization: Bearer fake-company-access-token`.
3. Call Partner API with `clientRegistrationId("partner-login")`.
4. Partner API mock server receives the partner token.
5. Attempting a registration disallowed by business routing is blocked **before sending the request**.

Dummy tokens do not need to be valid JWTs because the test target here is **WebClient routing and header attachment**, not signature validation at the Resource Server. Full integration tests should also verify the provider, user login, and API authorization contracts.

### 15.2. Testing When WebClient Lacks an OAuth2 Filter

A plain `WebClient` still compiles with:

```java
.attributes(clientRegistrationId("company-login"))
```

yet without an exchange filter that understands that attribute, **nothing attaches a bearer token**. This test catches cases where a developer calls `WebClient.create()` in a service instead of injecting the configured `oauth2WebClient` bean.

## 16. Composite Scenario: Portal Calling Two APIs with Two Token Types

An internal portal has:

- `company-login`: OIDC Login for employees to call the Reports API with user permissions.
- `inventory-service`: `client_credentials` for backend inventory-reading jobs.
- Reports API checks the user token; Inventory API checks the service token.

```text
Browser / employee
    |
    v
Spring MVC Portal (SecurityContext has OidcUser)
    |
    +--> GET /dashboard/reports
    |       WebClient:
    |       .attributes(clientRegistrationId("company-login"))
    |             |
    |             v
    |       Reports API (User access token)
    |
    +--> GET /dashboard/inventory
            Business authorization: can user view inventory?
            Service AuthorizedClientManager:
                registrationId = inventory-service
                principal      = service:inventory-sync
                    |
                    v
            Inventory API (Client Credentials access token)
```

The two paths have different semantics:

1. An OIDC/Login token can represent permissions granted **on behalf of the user**, if the Authorization Server issues an access token for that API.
2. A `client_credentials` token represents the **application/service**, not Alice.
3. The same Portal can use both, but must enforce business checks before letting a user trigger a backend task that uses a service credential.
4. `clientRegistrationId` only picks the registration; the token must still match the API's audience/scope.
5. Whether using a shared WebClient or separate WebClients, never send a bearer token to the wrong host.

### 16.1. A Controllable Design

```text
ReportsGateway
    allowed URL: reports-api.example.org
    registration: company-login
    principal: authenticated user

InventoryGateway
    allowed URL: inventory-api.example.org
    registration: inventory-service
    principal: service:inventory-sync
    authorization: business policy at Portal + API policy
```

Each gateway restricts its own URL and registration. When adding a Partner API, build explicit mappings and tenant checks rather than just adding an arbitrary path to a shared WebClient.

## 17. Design Mistakes to Avoid

1. **Confusing `registrationId` with `clientId`**, causing the filter to fail to locate the registration.
2. **Using `WebClient.create()` without an OAuth2 filter** and expecting attributes to attach tokens automatically.
3. **Setting a default registration on a WebClient calling multiple APIs**, leaking tokens to the wrong host.
4. **Uncontrolled `setDefaultOAuth2AuthorizedClient(true)`**, attaching user tokens to inappropriate outbound calls.
5. **Reading registration ID or target URL from query parameters without an allowlist**, inviting token leaks/SSRF.
6. **Treating registration selection as granted authorization**, skipping user/tenant and Resource Server authorization.
7. **Forgetting that an authorization-code registration requires user consent**, and cannot be obtained headlessly for another provider in the background.
8. **Using a user principal for shared client credentials tokens**, inadvertently creating per-user token entries.
9. **Failing to distinguish Servlet managers from Reactive managers**, leading to wrong storage/context lookups.
10. **Assuming thread-local SecurityContext exists in every Reactor callback**, especially across scheduler switches.
11. **Sending an ID Token instead of an access token** when calling APIs, confusing authentication tokens with resource tokens.
12. **Blindly replaying business HTTP POSTs on 401**, ignoring idempotency and side effects.
13. **Logging bearer tokens or full OAuth2AuthorizedClient objects** while investigating errors.
14. **Treating `clientRegistrationId` as an HTTP header**, when it is client-side WebClient request metadata.
15. **Relying solely on YAML scopes to assume API access**, without checking granted scopes and the API contract.

## 18. Review Questions

1. What role does `ServletOAuth2AuthorizedClientExchangeFilterFunction` play in a Spring MVC app using `WebClient`?
2. Which part of `ClientRequest` does `.attributes(clientRegistrationId("company-login"))` modify, and is it sent verbatim to the API?
3. How does `registrationId` differ from `clientId`? Why can passing a client ID to the helper fail?
4. Why does a configured `ClientRegistration` not mean an `OAuth2AuthorizedClient` already exists for every user?
5. When should you choose `clientRegistrationId(...)` versus passing `oauth2AuthorizedClient(...)`?
6. What risks do `setDefaultClientRegistrationId(...)` and `setDefaultOAuth2AuthorizedClient(true)` pose when WebClient calls multiple hosts?
7. Why should registration IDs and target URLs never be taken directly from `@RequestParam`?
8. When using WebClient outside a Servlet request, which manager should be used for background `client_credentials`?
9. How do `HttpServletRequest` attributes differ from WebClient `ClientRequest.attributes`?
10. If WebClient has an OAuth2 filter yet the API returns 403, besides registration ID, what factors should be checked?
11. How do you ensure the `inventory-service` token is never sent to the Reports API?
12. If a user logged in via the Corporate OP while WebClient picks `partner-login`, why cannot you assume a partner token exists?
13. In a multi-tenant app, who must decide which tenant and authorized client are permitted?
14. How can you test that request attributes select the right token without using real credentials?
15. Why does using `WebClient` inside MVC not turn the security context into a WebFlux security context?

## References

- [Spring Security Reference — OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — OAuth2 Client with WebClient (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Security Reference — OAuth2 Login (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html)
- [Spring Security API — ServletOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServletOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Spring Security API — OAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html)
- [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html)
- [Spring Security API — ClientRegistration](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/registration/ClientRegistration.html)
- [Spring Security API — OAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizedClientRepository.html)
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://datatracker.ietf.org/doc/html/rfc6749)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html)
