# ServletBearerExchangeFilterFunction and WebClient Support in Servlet

In a Spring MVC application protected by Spring Security Resource Server, incoming requests may carry an access token in the `Authorization` header. After the Resource Server verifies the token, the application sometimes needs to call another API on behalf of the current user. **`ServletBearerExchangeFilterFunction`** forwards the Bearer token attached to the current `Authentication` onto outbound requests made by **`WebClient`**.

This is a **token relay** feature: the application forwards the received and verified access token. The filter does not request a new token, refresh an expired token, change the audience, add scopes, or convert a user's token into a service identity token.

You must distinguish two requirements:

- **Forwarding a user token:** downstream needs to receive the exact access token sent to the current Resource Server. Use `ServletBearerExchangeFilterFunction`.
- **Obtaining an access token via an OAuth2 client registration:** the application needs its own token for a client/service, potentially requiring `client_credentials`, `authorization_code`, or refresh. Use `ServletOAuth2AuthorizedClientExchangeFilterFunction` with `OAuth2AuthorizedClientManager`.

This lesson explains how to integrate `WebClient` in Servlet applications, how `Authentication` is retrieved, how to configure the filter, audience/scope boundaries, common errors, protecting tokens from being sent to the wrong destination, and how to test it.

## 1. Token Relay in a Multi-Service Architecture

Suppose a user calls the Orders API with an access token:

~~~http
GET /api/orders/42 HTTP/1.1
Host: orders.example.com
Authorization: Bearer user-access-token
~~~

The Orders API verifies the token and then needs to call the Inventory API to fetch item details.

~~~mermaid
sequenceDiagram
    participant U as User / Client
    participant O as Orders API (Servlet)
    participant S as Spring Security
    participant W as WebClient
    participant I as Inventory API

    U->>O: GET /api/orders/42 + Bearer token
    O->>S: Verify access token
    S-->>O: Authenticated Authentication
    O->>W: Call Inventory API
    W->>W: ServletBearerExchangeFilterFunction
    W->>I: Authorization: Bearer same access token
    I->>I: Verify token and check permissions
    I-->>W: Inventory response
    W-->>O: Mono response
    O-->>U: Orders response
~~~

**`ServletBearerExchangeFilterFunction`** automatically adds the `Authorization` header to outbound requests if it finds an OAuth2 token credential attached to the current `Authentication`.

The Inventory API must still verify the token itself. The fact that the Orders API already authenticated the request does not let the Inventory API assume the request is valid.

### 1.1. Why Use Token Relay?

Token relay is useful when:

- A user's request traverses multiple APIs.
- Downstream needs to know the original user's identity and permissions.
- Downstream enforces authorization itself by scope, role, or tenant.
- The system shares a common trust domain and the access token was issued for the appropriate resources.
- The intermediary application does not need to change client identity or obtain a different token.

For example, the Orders API receives a token with the `orders.read` scope and forwards that token to a downstream service permitted to receive the same access token. Downstream checks scope and audience according to its own policy.

### 1.2. Token Relay Is Not Token Exchange

Relay keeps the access token unchanged. **Token exchange** creates a new token under a different authorization contract, typically with an audience/resource or scope narrowed for downstream.

If the incoming token only has audience `orders-api`, do not assume that token is valid for `inventory-api`. Forwarding the exact token can cause the Inventory API to return 401/403 because the audience or scope does not match.

When downstream needs its own token, use OAuth2 Client or a token exchange flow supported by the Authorization Server, rather than trying to edit the JWT payload or merely changing headers.

## 2. What Is ServletBearerExchangeFilterFunction?

This class belongs to the package:

~~~java
org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServletBearerExchangeFilterFunction
~~~

It implements Spring WebClient's **`ExchangeFilterFunction`**. Therefore, it can be registered on a `WebClient` builder as an outbound filter.

Minimal configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServletBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class DownstreamWebClientConfiguration {

    @Bean
    WebClient downstreamWebClient() {
        return WebClient.builder()
            .filter(new ServletBearerExchangeFilterFunction())
            .build();
    }
}
~~~

When `WebClient` executes a request, the filter looks up the current `Authentication` and extracts its credentials if they are an **`AbstractOAuth2Token`**. If found, it puts the token value into the header:

~~~http
Authorization: Bearer <token-value>
~~~

This is the behavior documented by Spring Security Resource Server under **Bearer Token Propagation**.

### 2.1. Where Does the Filter Get the Token From?

The authenticated `Authentication` is normally stored in the `SecurityContext`. The Servlet stack defaults to `SecurityContextHolder`, typically backed by `ThreadLocal` during request processing.

The Javadoc for `ServletBearerExchangeFilterFunction` describes looking up `Authentication` in the **Reactor Context** under the `Authentication` type key. This reflects how the filter integrates with `WebClient`'s reactive publisher. When used inside a Servlet request flow managed by Spring Security, keep the publisher tied to the request lifecycle and use context propagation per your running Spring configuration.

Do not assume `SecurityContextHolder` `ThreadLocal` will automatically appear on arbitrary threads. If you spawn raw threads manually, subscribe to publishers detached from the request, or offload work across an execution boundary that does not propagate context, the filter may fail to find `Authentication`.

### 2.2. Credentials Must Be AbstractOAuth2Token

The filter does not forward every kind of `Authentication`.

| Current Authentication | Can Be Relayed by This Filter? | Explanation |
|---|---|---|
| `JwtAuthenticationToken` from Resource Server | Yes, if credentials are `AbstractOAuth2Token` | The JWT is verified and attached to `Authentication` |
| `OpaqueTokenAuthenticationToken` | Yes, if credentials are an OAuth2 token | Opaque tokens can also be `AbstractOAuth2Token` |
| `UsernamePasswordAuthenticationToken` | No | Credentials are typically a password, not an OAuth2 token |
| `AnonymousAuthenticationToken` | No | No OAuth2 access token credential |
| `OAuth2AuthenticationToken` from `oauth2Login` | Do not assume | OAuth2 Login stores authorized clients separately; use an OAuth2 Client filter to obtain the access token |
| Custom Authentication | Depends on implementation | Credentials must be `AbstractOAuth2Token` |

When no suitable token is present, the filter does not generate a new access token. The request proceeds down the filter chain without a relayed token.

### 2.3. The Filter Does Not Re-Verify the Token

This filter is not a `JwtDecoder` or `OpaqueTokenIntrospector`. It does not:

- Verify the JWT signature.
- Call the introspection endpoint.
- Check issuer or audience.
- Check `exp` and refresh.
- Add authorities.
- Translate scopes.
- Create an `OAuth2AuthorizedClient`.
- Exchange the token for a downstream-specific token.

It solely forwards the token credential attached to the current `Authentication`. Verifying the inbound token belongs to the Resource Server; verifying the outbound token belongs to the downstream Resource Server.

## 3. Configuring WebClient for a Servlet Application

`WebClient` lives in the Spring WebFlux API, yet it can be used as an HTTP client in Spring MVC/Servlet applications. Using `WebClient` **does not turn a Spring MVC application into a WebFlux server**.

To use `WebClient`, the project needs the Spring WebFlux client API and a suitable HTTP connector, such as Reactor Netty. With Spring Boot, dependency management selects versions compatible with Spring Framework/Security.

Example Gradle dependencies:

~~~groovy
dependencies {
    implementation("org.springframework:spring-webflux")
    implementation("io.projectreactor.netty:reactor-netty")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
}
~~~

If the project already manages dependencies with the Spring Boot BOM, do not override Spring WebFlux or Reactor Netty with incompatible versions.

### 3.1. Creating a Dedicated WebClient for Downstream

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.web.reactive.function.client.ServletBearerExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class InventoryClientConfiguration {

    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
            .baseUrl("https://inventory.internal.example")
            .filter(new ServletBearerExchangeFilterFunction())
            .build();
    }
}
~~~

This example uses a fixed base URL. In practice, you can add:

- Appropriate connect/response timeouts.
- Connection pool and pending request limits.
- TLS trust configuration.
- Observability/correlation IDs.
- Response body size limits.
- Error handling per the API contract.

**Do not attach the token relay filter to a `WebClient` used for arbitrary external URLs.** The filter would have the opportunity to add the token to every matching request sent through that client.

### 3.2. Calling Downstream from a Service

~~~java
import java.time.Duration;

import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
class InventoryService {

    private final WebClient inventoryWebClient;

    InventoryService(WebClient inventoryWebClient) {
        this.inventoryWebClient = inventoryWebClient;
    }

    Inventory findInventory(String productId) {
        return this.inventoryWebClient.get()
            .uri("/api/inventory/{id}", productId)
            .retrieve()
            .bodyToMono(Inventory.class)
            .block(Duration.ofSeconds(3));
    }
}
~~~

This is a synchronous example for a service called from Servlet/MVC. `block(Duration)` waits for the result and holds the servlet request thread for the duration of the outbound call. Timeouts bound wait time, but do not make the code nonblocking on the caller side.

If you want asynchronous return types in Spring MVC, you can return `Mono`/`CompletableFuture` depending on framework/version capabilities. In that case, test context propagation in the actual request lifecycle. Never call `subscribe()` inside a controller/service to detach the outbound call from the response lifecycle.

### 3.3. Illustrative Controller

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class InventoryController {

    private final InventoryService inventoryService;

    InventoryController(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    @GetMapping("/api/products/{id}/inventory")
    ResponseEntity<Inventory> inventory(@PathVariable String id) {
        Inventory inventory = this.inventoryService.findInventory(id);
        return ResponseEntity.ok(inventory);
    }
}
~~~

The controller does not need to manually read the `Authorization` header and copy it to `WebClient`. The filter handles relaying from `Authentication` per Spring Security's mechanism.

## 4. How It Works When WebClient Sends a Request

The filter can be described as follows:

~~~text
WebClient request is subscribed
  -> ServletBearerExchangeFilterFunction runs
  -> look up Authentication in security/reactor context
  -> read Authentication.credentials
  -> are credentials an AbstractOAuth2Token?
       Yes:
         extract tokenValue
         add Authorization: Bearer <token>
       No:
         do not add token
  -> forward request to the next ExchangeFunction
~~~

This is a behavioral description, not Spring Security's internal code.

### 4.1. Request Already Has an Authorization Header

If the application explicitly sets an `Authorization` header for a specific request, the filter can leave that header intact and forward the request.

Example:

~~~java
return inventoryWebClient.get()
    .uri("/api/inventory/{id}", productId)
    .headers(headers ->
        headers.setBearerAuth(serviceSpecificToken))
    .retrieve()
    .bodyToMono(Inventory.class);
~~~

When the request already has an `Authorization` header set by the caller, the override behavior documented by Spring Security is that the filter does not replace it and passes the request along.

This is useful when a specific request must use a dedicated token. However, **do not mix user tokens and service tokens arbitrarily**. Document clearly which token represents which principal and which credential types downstream is allowed to accept.

### 4.2. No Suitable Authentication Present

Cases:

- Unauthenticated public request.
- `Authentication` is `AnonymousAuthenticationToken`.
- `Authentication` has no OAuth2 token credential.
- Publisher did not receive `Authentication` in the Reactor Context.

In these cases, the filter has no suitable token to relay. The request can still be sent without an `Authorization` header, and downstream enforces its own policy.

If downstream requires authentication, the response may be 401. Do not treat a successfully constructed `WebClient` call as proof that a token was forwarded.

## 5. Token Relay Does Not Refresh Expired Access Tokens

One key point to remember:

**`ServletBearerExchangeFilterFunction` does not attempt to renew the token if it has expired.**

Suppose:

~~~text
Inbound request authenticated at 10:00
Access token exp at 10:01
Application calls downstream at 10:02
~~~

The filter can still forward the current token credential. Downstream checks `exp` and rejects the expired token.

The filter does not call the token endpoint, use a refresh token, or mint a new access token.

### 5.1. When Should You Use an OAuth2 Client Filter?

If the application needs to:

- Request an access token when no authorized client exists yet.
- Use `client_credentials` to represent the service.
- Retrieve an authorized client by client registration.
- Refresh an access token using the `refresh_token` grant when the provider supports it.
- Manage authorized client lifecycle and failure handling.

then use **`ServletOAuth2AuthorizedClientExchangeFilterFunction`** together with **`OAuth2AuthorizedClientManager`**.

These are two distinct mechanisms:

| Criterion | ServletBearerExchangeFilterFunction | ServletOAuth2AuthorizedClientExchangeFilterFunction |
|---|---|---|
| Token source | Credential attached to current `Authentication` | `OAuth2AuthorizedClient` managed by the manager |
| Purpose | Relay inbound access token | Obtain/use token for an OAuth2 client registration |
| Obtains new token | No | Potentially, depending on provider/grant |
| Refreshes token | No | Potentially, if refresh provider is configured |
| Client credentials | Does not request automatically | Supported |
| Custom audience/scope | Does not alter token | Per client registration/authorization server policy |
| How specified | Current `Authentication` | Client registration/authorized client request attributes |

## 6. OAuth2AuthorizedClientManager and WebClient

When an application calls downstream using its own service identity, configure OAuth2 Client.

### 6.1. Creating OAuth2AuthorizedClientManager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class OAuth2ClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

This example uses `AuthorizedClientServiceOAuth2AuthorizedClientManager` for service-level authorized clients. For requests bound to `HttpServletRequest`/`HttpServletResponse`, you can use `DefaultOAuth2AuthorizedClientManager` and `OAuth2AuthorizedClientRepository` per the Spring Security guide.

### 6.2. Creating a WebClient with the OAuth2 Client Filter

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class OAuth2WebClientConfiguration {

    @Bean
    WebClient serviceWebClient(
            OAuth2AuthorizedClientManager authorizedClientManager) {

        ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServletOAuth2AuthorizedClientExchangeFilterFunction(
                authorizedClientManager);

        return WebClient.builder()
            .baseUrl("https://inventory.internal.example")
            .apply(oauth2.oauth2Configuration())
            .build();
    }
}
~~~

To select a specific registration for a request:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

return serviceWebClient.get()
    .uri("/api/inventory/{id}", productId)
    .attributes(clientRegistrationId("inventory-service"))
    .retrieve()
    .bodyToMono(Inventory.class);
~~~

The registration ID must match the OAuth2 Client configuration in the application. The Authorization Server must permit that client to obtain an access token with the appropriate audience/scope.

### 6.3. Client Credentials Differs from User Token Relay

When using `client_credentials`, downstream typically sees the service client as the caller. It does not automatically know which original user made the request unless the application passes user context via a dedicated mechanism.

When relaying a user token, downstream can authenticate the original user if the token is intended for downstream and issuer policy permits it.

Do not choose `client_credentials` simply because a relayed token expired; the two approaches represent **two different principal/trust contracts**.

## 7. Audience, Scope, and Downstream Authorization

Suppose the inbound token is:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

The Orders API can verify the token because its audience is `orders-api`. However, the Inventory API requires:

~~~json
{
  "aud": ["inventory-api"],
  "scope": "inventory.read"
}
~~~

Relaying the token verbatim does not change the `orders-api` audience to `inventory-api` or add `inventory.read`.

### 7.1. What Downstream Must Check

The downstream Resource Server should independently verify:

- Signature or introspection state.
- Issuer.
- Audience intended for downstream.
- `exp`, `nbf`, and token profile.
- Scopes/authorities.
- Tenant, client, and domain authorization.
- Business-specific claims/constraints.

Do not rely on the request coming from the Orders API to skip token verification, unless there is a separate, deliberately designed and controlled service-to-service trust mechanism such as mTLS or gateway identity.

### 7.2. When the Audience Does Not Match

Options:

1. The Authorization Server issues an access token with multiple audiences according to policy.
2. Use **OAuth 2.0 Token Exchange (RFC 8693)** to swap the incoming token for one intended for downstream.
3. Use OAuth2 Client with `client_credentials` if downstream only needs service identity.
4. Design a delegation mechanism supported by the AS and verified by downstream.

Never edit claims inside a signed JWT or fabricate fake tokens in middleware.

### 7.3. Scopes Cannot Be Expanded During Relay

If the inbound token only has `orders.read`, the relay filter cannot add `inventory.write`. Downstream must not assume a token passing through an intermediary service has gained extra permissions.

This is a vital principle for maintaining least privilege across multiple services.

## 8. Token Leakage Risks via a Shared WebClient

A `WebClient` configured with `ServletBearerExchangeFilterFunction` is capable of attaching the current token to outbound requests. Therefore, **the destination of that `WebClient` becomes a security boundary**.

Dangerous example:

~~~java
String userSuppliedUrl = request.getParameter("url");

return sharedWebClient.get()
    .uri(userSuppliedUrl)
    .retrieve()
    .bodyToMono(String.class);
~~~

If this `WebClient` has token relay enabled and the URL is user-controlled, the application risks sending the access token to an unintended host.

### 8.1. Use Dedicated Clients per Downstream

Recommendations:

- A separate `WebClient` for the Inventory API.
- Base URL configured in server-side configuration.
- Do not let callers supply absolute URLs.
- Do not put the token-relay client inside a general-purpose HTTP utility.
- Restrict redirects/hosts via network policy and connector behavior.
- Never log the `Authorization` header.
- Use TLS and verify certificates/hostnames.
- Do not reuse the same token-relay client for telemetry, webhooks, or public URLs.

Note: **`baseUrl` is not an absolute security allowlist** if code still allows an absolute request URI to override the base URL. Never accept arbitrary URIs from user requests.

### 8.2. Avoid Logging the Token

Never log:

~~~http
Authorization: Bearer eyJhbGciOi...
~~~

Do not place token values into:

- Application logs.
- Trace tags or baggage.
- Metrics labels.
- Exception messages.
- Unprotected audit events.
- URL query parameters.

You can log correlation IDs, downstream logical service names, statuses, and error categories without exposing credentials.

### 8.3. Do Not Cache Relayed Tokens in Singleton Fields

A singleton `WebClient` is normal; user tokens must never be stored in a mutable field on a bean.

Avoid:

~~~java
class UnsafeClient {
    private String currentUserToken;
}
~~~

Concurrent requests can overwrite each other's tokens, causing cross-user credential leakage.

The filter must retrieve `Authentication` from the request/publisher context rather than storing the current token in a global variable.

## 9. Header Overrides and Multiple ExchangeFilterFunctions

Spring `WebClient` allows stacking multiple `ExchangeFilterFunction` instances. Filter ordering can affect how the request is modified before being sent.

If a request explicitly sets an `Authorization` header, Spring Security's documentation states that `ServletBearerExchangeFilterFunction` will not overwrite that header and passes the request to the next filter.

Example token override:

~~~java
return inventoryWebClient.get()
    .uri("/api/inventory/{id}", productId)
    .headers(headers ->
        headers.setBearerAuth(explicitToken))
    .retrieve()
    .bodyToMono(Inventory.class);
~~~

Use overrides intentionally, such as when a service method receives an authorized token already issued for the target downstream. Avoid accepting `explicitToken` from untrusted callers.

### 9.1. Avoid Two Filters Both Setting Authorization

A `WebClient` might have:

- `ServletBearerExchangeFilterFunction`.
- An OAuth2 client filter.
- A custom API-key filter.
- A custom header interceptor.

If multiple filters manipulate `Authorization`, define the ordering and policy explicitly. A single request should have only one appropriate credential scheme.

Do not let a request carry both a user token and a service token in a way that prevents downstream from distinguishing the principal.

## 10. Handling Errors from Downstream

`ServletBearerExchangeFilterFunction` only handles attaching the token. It does not manage all HTTP errors returned downstream.

Example:

~~~java
return inventoryWebClient.get()
    .uri("/api/inventory/{id}", productId)
    .retrieve()
    .onStatus(
        status -> status.value() == 401,
        response -> response.createException()
    )
    .onStatus(
        status -> status.value() == 403,
        response -> response.createException()
    )
    .bodyToMono(Inventory.class);
~~~

Common responses:

| Downstream Response | Possible Cause |
|---|---|
| 401 Unauthorized | Missing, expired, wrong issuer/audience, bad signature, or inactive token |
| 403 Forbidden | Valid token but missing scope/role/tenant permission |
| 429 Too Many Requests | Downstream rate limit |
| 5xx | Downstream or its dependency encountered an error |
| Timeout | Response not received within budget |

### 10.1. 401 Does Not Auto-Trigger Refresh with the Relay Filter

When downstream returns 401, `ServletBearerExchangeFilterFunction` does not call the token endpoint to refresh. It is not an `OAuth2AuthorizedClientManager`.

The application can record the error and return an appropriate response to the caller. If refreshing or obtaining a new token is required, use the OAuth2 Client filter with an appropriate provider/failure handler.

### 10.2. Do Not Retry Blindly

Retrying the same expired token will continue to fail. Retrying a `POST`/`DELETE` request can cause duplicate side effects if downstream processed the request before the connection dropped.

You must consider:

- HTTP method and idempotency.
- Error category.
- Access token expiration.
- Downstream retry contract.
- Overall deadline.
- Idempotency keys if supported by the business domain.

## 11. Token Relay Across Multiple Downstream Services

An application may call several services:

~~~text
Inbound user token
    |
    +--> Orders service
    |
    +--> Inventory service
    |
    +--> Shipping service
    |
    +--> Billing service
~~~

Not every downstream service should receive the same token.

| Downstream | Required Audience | Can Relay the Same Token? |
|---|---|---|
| Orders API | orders-api | If the token was issued for the right audience |
| Inventory API | inventory-api | Only if audience/contract permits |
| Billing API | billing-api | No if the token is only for Orders |
| Telemetry endpoint | telemetry resource | Usually should not send user tokens |
| Public webhook | Outside trust domain | No |

Designing separate `WebClient` instances per logical downstream makes policies readable and limits accidental token misrouting.

If a downstream service needs service identity instead of user identity, use OAuth2 Client/`client_credentials` or an appropriate workload identity mechanism.

## 12. ServletBearerExchangeFilterFunction vs. ServerBearerExchangeFilterFunction

Spring Security provides two similarly named classes for two different environments:

| Class | Environment | Role |
|---|---|---|
| **ServletBearerExchangeFilterFunction** | Spring MVC / Servlet application | Relay Bearer token attached to current `Authentication` |
| **ServerBearerExchangeFilterFunction** | WebFlux reactive server | Relay Bearer token from reactive `Authentication` context |

For Servlet applications, use `ServletBearerExchangeFilterFunction`. For WebFlux servers, use `ServerBearerExchangeFilterFunction`.

Both are `WebClient` `ExchangeFilterFunction` implementations, but do not pick the class solely because the application uses `WebClient`. Choose based on your **server security stack**.

## 13. Testing Token Relay

A useful test must verify that the outbound HTTP request actually carries the expected header. Testing only that the controller returns 200 is not enough.

You can use `MockWebServer` or an equivalent HTTP stub.

### 13.1. Positive Test

1. Start the test Servlet application with Spring Security Resource Server.
2. Send an inbound request with a verified test JWT.
3. The controller calls the `WebClient` configured with `ServletBearerExchangeFilterFunction`.
4. The downstream stub receives the request.
5. Verify the `Authorization` header has the exact Bearer token.
6. Verify the downstream response is returned to the caller.

### 13.2. Negative Tests

| Scenario | Expected Outcome |
|---|---|
| No `Authentication` | Does not synthesize a Bearer token |
| `Authentication` without `AbstractOAuth2Token` credential | Does not arbitrarily relay credentials |
| `Authentication` with JWT token | Relays the corresponding token value |
| Request already has explicit `Authorization` | Preserves defined override policy |
| Inbound token expires after authentication | Filter does not auto-refresh |
| Token audience wrong for downstream | Downstream rejects |
| Missing downstream scope | Downstream returns 403 |
| Calling host outside allowlist | Relay client must not be used |
| Two users call concurrently | Tokens must not cross between requests |
| Publisher runs detached from request context | Do not assume `Authentication` remains present |

### 13.3. Example Stub Verification of Outbound Authorization

An integration test can inspect the received request:

~~~java
RecordedRequest recorded = mockWebServer.takeRequest();

assertEquals(
    "Bearer test-access-token",
    recorded.getHeader("Authorization")
);
~~~

This example assumes the test sent an inbound request and `MockWebServer` received the outbound call. Use a test token, not real credentials.

### 13.4. Testing Two Concurrent Requests

Create two inbound requests with two distinct access tokens:

~~~text
Request A -> token-A -> downstream call A
Request B -> token-B -> downstream call B
~~~

Verify:

- Request A does not carry `token-B`.
- Request B does not carry `token-A`.
- No static field holds the current token.
- Each publisher receives the right request's `Authentication`.
- Cancellation or timeout of Request A does not alter Request B's context.

This is an essential test for a concurrently shared singleton `WebClient`.

## 14. Common Design Mistakes

**1. Confusing token relay with token refresh.** `ServletBearerExchangeFilterFunction` does not obtain or refresh tokens on its own.

**2. Confusing token relay with OAuth2 Client.** The relay filter uses the current credential; OAuth2 Client manager manages authorized clients and token acquisition.

**3. Forwarding tokens to every URL.** Risks leaking Bearer credentials to hosts outside the trust boundary.

**4. Assuming downstream automatically accepts the token.** Audience, issuer, and scopes must still match.

**5. Using an ID Token as an access token.** ID Tokens are for OIDC clients; Resource Servers need an access token with the right audience.

**6. Using `client_credentials` when user identity must be preserved.** Service tokens represent the application, not automatically the original user.

**7. Adding scopes by editing the JWT.** The signature becomes invalid; permissions must be granted by the Authorization Server.

**8. Calling `subscribe()` manually inside a service.** Detaches the outbound request from the caller's lifecycle, errors, and cancellation.

**9. Storing tokens in a singleton field.** Risks sending one user's token on another user's request.

**10. Logging the `Authorization` header.** Exposes Bearer credentials.

**11. Omitting timeouts on outbound `WebClient`.** Can hold servlet request threads too long when using `block()`.

**12. Treating a downstream 401 as an inbound Resource Server bug.** Two services can have different audience/scope/token policies.

**13. Using `ServletBearerExchangeFilterFunction` in a WebFlux server.** Choose the filter matching Servlet vs. reactive server stack.

**14. Using a relay filter for every integration.** Webhooks, telemetry, and public APIs do not necessarily belong in the user-token trust boundary.

## 15. Selection and Implementation Workflow

**Step 1 — Identify the principal downstream needs to see.** Is it the original user or the current service?

**Step 2 — Check the access token contract.** Do issuer, audience, scope, expiration, and token type match downstream?

**Step 3 — Choose the mechanism.**
- User token accepted by downstream: `ServletBearerExchangeFilterFunction`.
- Dedicated service token: `OAuth2AuthorizedClientManager`/`client_credentials`.
- Token requiring a different audience or scope: token exchange where supported by the AS.

**Step 4 — Create a dedicated `WebClient`.** Use a fixed base URL, TLS, timeouts, pooling, and metrics.

**Step 5 — Add the stack-appropriate filter.** `ServletBearerExchangeFilterFunction` for Servlet; `ServerBearerExchangeFilterFunction` for WebFlux.

**Step 6 — Preserve request-scoped context.** Do not manually subscribe or spawn threads detached from the request; test async propagation.

**Step 7 — Verify downstream authorization.** Never assume a token valid at the current service is valid at another service.

**Step 8 — Control token leakage.** Never send to user-controlled URLs, never log headers, and never store tokens in singleton state.

**Step 9 — Handle 401/403 and timeouts.** Distinguish invalid tokens, insufficient permissions, upstream failures, and timeouts; only refresh when using an appropriate OAuth2 Client flow.

**Step 10 — Test end-to-end.** Verify the right token, right destination, right context, and no token cross-contamination between requests.

## 16. Self-Check Questions

**1. What does `ServletBearerExchangeFilterFunction` do?**

It retrieves the OAuth2 token credential attached to the current `Authentication` and adds it to the `Authorization` Bearer header of outbound `WebClient` requests.

**2. Does it request a new access token on its own?**

No. It only forwards the existing token.

**3. Does it refresh an expired access token?**

No. Use `ServletOAuth2AuthorizedClientExchangeFilterFunction` with `OAuth2AuthorizedClientManager` if refreshing via configured providers is needed.

**4. Does it send every kind of `Authentication` credential?**

No. It looks for a credential that is an `AbstractOAuth2Token`.

**5. Does it automatically change the audience for the downstream API?**

No. The token is relayed intact; downstream must check its own audience.

**6. Why shouldn't you attach the filter to a `WebClient` used for arbitrary URLs?**

Because the access token could be sent to untrusted hosts.

**7. Can `ServletBearerExchangeFilterFunction` be used in a WebFlux server?**

It should not be. WebFlux servers have the corresponding `ServerBearerExchangeFilterFunction`.

**8. Does token relay add scopes?**

No. It does not grant extra permissions or modify the token.

**9. Is an OAuth2 Login session automatically relayed via this filter?**

Do not assume so. Use an OAuth2 Client filter to obtain the access token from `OAuth2AuthorizedClient`.

**10. When downstream returns 401, does the filter auto-refresh or remove the token?**

No. The filter only attaches the header; refreshing and failure handling belong to the OAuth2 Client manager or application logic.

## Conclusion

**`ServletBearerExchangeFilterFunction`** enables Spring MVC/Servlet applications to forward the access token attached to the current `Authentication` when calling downstream services via `WebClient`. Basic usage registers it on the `WebClient` builder:

~~~java
WebClient.builder()
    .filter(new ServletBearerExchangeFilterFunction())
    .build();
~~~

This mechanism only performs **token relay**. It does not request tokens, refresh tokens, change audiences, expand scopes, or verify downstream permissions. If your application needs tokens per client registration, use **`ServletOAuth2AuthorizedClientExchangeFilterFunction`** with **`OAuth2AuthorizedClientManager`**.

Create dedicated `WebClient` instances for each trusted downstream service, verify audience/scope, keep `Authentication` tied to the request context, never send tokens to arbitrary URLs, and never log `Authorization` headers. **A token should only be forwarded when downstream has an explicit contract to verify and accept that exact token.**

### References

- [Spring Security — OAuth 2.0 Bearer Token Propagation](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security API — ServletBearerExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/reactive/function/client/ServletBearerExchangeFilterFunction.html)
- [Spring Security — Authorized Client Features and WebClient Integration for Servlet Environments](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Security API — ServletOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServletOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Project Reactor — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693)
