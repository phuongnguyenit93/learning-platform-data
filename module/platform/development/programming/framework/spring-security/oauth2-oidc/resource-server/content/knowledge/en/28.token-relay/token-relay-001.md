# A Resource Server Calling Other Services Can Simultaneously Act as an OAuth2 Client

A Spring Security application can act as both an **OAuth 2.0 Resource Server** for incoming requests and an **OAuth 2.0 Client** when calling another protected service. This is a common pattern in microservices architectures: the Orders API receives a user's access token, verifies the token and access permissions, and then calls the Inventory API, Pricing API, or Shipping API using an access token appropriate for the target service.

These two roles are not mutually exclusive. A single service can simultaneously:

- Receive and verify access tokens from upstream Clients as a Resource Server.
- Use an OAuth2 Client to obtain or manage access tokens for outbound requests.
- Choose the outbound credential based on the business purpose: the service's own identity, a delegated user identity, or a new token exchanged by the Authorization Server from the incoming token.

**You should not assume that the incoming token is the token to forward outbound.** That token may only be intended for the current service's audience, may lack the scope required by the downstream service, or may not be permitted to be forwarded. Outbound token selection must follow the contract between the services and the Authorization Server.

> **Principle:** The Resource Server verifies **who is calling the current service and what they are allowed to do here**. The OAuth2 Client determines **whom the current service will represent when calling another system**. These two decisions are related, not identical. Choose the outbound token based on least privilege, the right audience, the right scope, and the right delegation model.

## 1. A Service Can Hold Two OAuth2 Roles

Suppose a retail system has:

- **Shop Web**: OAuth2 Client, which obtains an access token to call the Orders API.
- **Orders API**: Resource Server for Shop Web; also an OAuth2 Client when calling the Inventory API.
- **Inventory API**: Resource Server, providing inventory data.
- **Authorization Server**: issues access tokens for each resource server.

~~~mermaid
flowchart LR
    U["User / Shop Web"]
    AS["Authorization Server"]
    O["Orders API<br/>Resource Server + OAuth2 Client"]
    I["Inventory API<br/>Resource Server"]

    U -->|"Bearer token for Orders API"| O
    O <-->|"Verify JWT / introspection"| AS
    O -->|"Appropriate outbound token"| I
    I <-->|"Verify Inventory's token"| AS
~~~

During a request:

1. Shop Web sends a token intended for the Orders API.
2. The Orders API verifies the token, audience, expiration, and scope.
3. The Orders API performs business authorization, such as whether the user can view the order.
4. If it needs to call the Inventory API, the Orders API selects an OAuth2 Client mechanism to obtain an outbound credential.
5. The Inventory API verifies the token intended for itself and enforces inventory permissions.

**The Orders API does not simply forward the incoming token out of habit.** It may use a different token with the service's identity or a token exchange representing the user.

## 2. Distinguishing Resource Server and OAuth2 Client in the Same Application

| Role | Request Direction | Responsibility |
| --- | --- | --- |
| **Resource Server** | Inbound: Client → Orders API | Read the Bearer token, verify the token, create an Authentication, check scopes/authorities, and protect endpoints |
| **OAuth2 Client** | Outbound: Orders API → Inventory API | Select a ClientRegistration, request/exchange an access token, manage the authorized client, and attach the token to outbound requests |
| **Authorization Server** | Token endpoint | Authenticate the OAuth2 Client, issue tokens, and handle grants and delegation policies |

Spring Security provides two corresponding sets of features:

- `oauth2ResourceServer()` in `HttpSecurity` or `ServerHttpSecurity` to protect APIs.
- `oauth2Client()` and `OAuth2AuthorizedClientManager`/`ReactiveOAuth2AuthorizedClientManager` components to execute OAuth2 Client flows.

A Servlet configuration example can enable both:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults()))
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

This is a skeleton configuration. The JWT decoder, issuer/audience validators, ClientRegistration, grant providers, authorized-client storage, and specific scope rules must still be configured according to your system.

**Enabling `oauth2Client()` does not automatically decide which token will be sent to each downstream service.** The code calling the downstream service must select the appropriate registration and principal/context.

### 2.1. An Incoming Authentication Does Not Automatically Become an Outbound OAuth2AuthorizedClient

When a Resource Server verifies a JWT, Spring Security typically creates a `JwtAuthenticationToken`. It represents the current request and holds the verified JWT along with its authorities.

`OAuth2AuthorizedClient` is a different concept: it associates a `ClientRegistration` with an `OAuth2AccessToken`, optionally an `OAuth2RefreshToken`, and a principal under which the authorized client is stored/identified.

`OAuth2AuthorizedClientManager` manages the authorization or re-authorization process, invokes the corresponding provider, and stores the authorized client via a repository/service. It does not take the inbound JWT and send it verbatim to every downstream service by default.

## 3. Choosing an Outbound Token Strategy

There are three common strategies:

| Strategy | Who Does the Outbound Token Represent? | When Appropriate |
| --- | --- | --- |
| **Client Credentials** | The Orders API/service itself | Downstream only needs to know which service is calling, without user context |
| **Token relay / forward incoming token** | The user or principal issued the inbound token | The original token was designed to be used downstream, has the right audience/scope, and policy permits it |
| **Token Exchange / On-Behalf-Of** | The delegated user, via a new token intended for downstream | Downstream needs user identity, but the inbound token is not intended for it or needs reduced scope/audience |

### 3.1. Client Credentials: Service Calls Using Its Own Identity

For example, the Orders API needs aggregated inventory information to process an internal task. The Inventory API only needs to know that the caller is `orders-api`, not whether Alice or Bob sent the request.

Flow:

~~~text
Orders API
  -> client_id/client_secret or private_key_jwt
  -> Authorization Server token endpoint
  -> grant_type=client_credentials
  -> access token audience=inventory-api, scope=inventory.read
  -> Inventory API
~~~

This token represents the **OAuth2 Client**, not the end user. Therefore, the Inventory API can audit `client_id=orders-api` instead of `sub=alice`.

Client Credentials is suitable for background tasks, schedulers, batch jobs, or service-to-service calls when downstream needs service identity. Do not use Client Credentials to pretend a user has authorized the call. If downstream must check Alice's permissions, a token representing only the Orders API will not provide sufficient user context.

### 3.2. Token Relay: Forwarding the Incoming Token

Some architectures allow the Orders API to forward the incoming access token unchanged:

~~~text
Shop Web -- token T --> Orders API -- token T --> Inventory API
~~~

Only do this if **token T was issued for the Inventory API or an audience set that includes the Inventory API**, and the scopes/permissions in the token are sufficient for the operation there.

For example, a token containing:

~~~json
{
  "iss": "https://identity.example.test",
  "sub": "alice",
  "aud": ["orders-api", "inventory-api"],
  "scope": "orders.read inventory.read",
  "exp": 1893459600
}
~~~

If the token only has `aud=["orders-api"]`, the Inventory API should reject it. Do not ask downstream services to disable audience validation just to make relay work.

Token relay can be appropriate when multiple APIs trust the same issuer and token profile, and the AS intentionally issues audiences/scopes for the relevant downstream services. The risk is that the token traverses multiple services, increasing its exposure surface and potentially carrying broader scopes than the downstream service needs.

**Do not relay tokens to arbitrary URLs supplied by the request/body.** Choose downstream hosts from a configuration/allowlist; avoid turning your API into a confused deputy or a token exfiltration proxy.

### 3.3. Token Exchange: Exchanging the Incoming Token for a New Downstream Token

Token Exchange per **RFC 8693** allows a Client to send the current token as a `subject_token` to the Authorization Server to receive another token suitable for a new resource/actor/scope, if the AS supports that policy.

~~~text
Client -> Orders API: access token T1 (aud=orders-api)
Orders API -> Authorization Server:
    grant_type=urn:ietf:params:oauth:grant-type:token-exchange
    subject_token=T1
    subject_token_type=urn:ietf:params:oauth:token-type:access_token
    audience/resource=inventory-api
    scope=inventory.read
Authorization Server -> Orders API: access token T2
Orders API -> Inventory API: Authorization: Bearer T2
~~~

T2 can have its own audience and smaller scope while still representing the user subject per AS policy. Token Exchange is a useful option for cross-service delegation.

It does not mean the Orders API signs another JWT itself. The Authorization Server is the party that decides whether to issue the new token.

### 3.4. On-Behalf-Of (OBO) Is One Way to Implement Delegation

Some platforms refer to this model as **On-Behalf-Of**. OBO generally describes a service using an inbound token to request a downstream token on behalf of a user. RFC 8693 Token Exchange provides a general standard for token exchange; vendors may implement OBO with their own parameters, endpoints, or policies.

Do not assume every Authorization Server supports the same OBO protocol simply because it supports OAuth2 Client Credentials.

## 4. Choosing the Right Strategy

| Downstream Requirement | Typically Appropriate Strategy |
| --- | --- |
| Only need to identify Orders API as the caller | Client Credentials |
| Need user permissions, inbound token already has the right audience/scope | Controlled token relay |
| Need user permissions, but inbound token is only for Orders API | Token Exchange/OBO |
| Need user permissions and service identity in the delegation chain | Token Exchange with subject token and actor token if supported by the AS |
| Background task with no user request | Client Credentials |
| Service should only read a narrow subset of data | Client Credentials with narrow scope or a downscoped exchanged token |

**Do not use Client Credentials for every case just because it is easy to configure.** If downstream needs to know whether Alice has permission to view Order 42, a token representing the Orders API may lose the subject information or leave downstream seeing only the service's permissions.

Conversely, **do not use token exchange when downstream only needs service identity**. There is no need to carry user context into an internal task if policy does not require it.

## 5. Configuring OAuth2 Client for Client Credentials

The examples use **Spring Boot 3 / Spring Security 6+ with the Servlet stack**. The classes/APIs below continue to be available in the Spring Security 7.1 documentation.

### 5.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
~~~

The Resource Server starter protects the inbound API; the OAuth2 Client starter provides ClientRegistration, the authorized-client manager, and HTTP client integration.

### 5.2. Registering the Client in application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test
      client:
        registration:
          inventory:
            provider: identity
            client-id: orders-api
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          identity:
            token-uri: https://identity.example.test/oauth2/token
~~~

These values are examples:

- `inventory` is Spring's internal registration ID, used to select the ClientRegistration.
- `client-id`/`client-secret` authenticates Orders API with the AS.
- `client_credentials` requests a token representing the service.
- `inventory.read` is the scope required for the Inventory API.
- `token-uri` is the token endpoint of the AS.

Do not commit real secrets to the repository. Use a secret manager, workload identity, private_key_jwt, or an environment-appropriate client authentication mechanism. If the AS supports private-key JWT, you can choose the corresponding `client-authentication-method` instead of a client secret.

### 5.3. Creating an OAuth2AuthorizedClientManager for Service/Background Work

`DefaultOAuth2AuthorizedClientManager` is designed to operate in an `HttpServletRequest` context. For service applications, schedulers, or tasks running outside a request, use **`AuthorizedClientServiceOAuth2AuthorizedClientManager`**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;

@Configuration
class OAuth2ClientConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        OAuth2AuthorizedClientProvider provider =
                OAuth2AuthorizedClientProviderBuilder.builder()
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

The manager can look up a stored authorized client, request a new access token when no suitable token exists, re-authorize when the token expires according to the configured provider, store the authorized client via `OAuth2AuthorizedClientService`, and handle authorization errors via success/failure handlers.

The provider in this example only enables `client_credentials`. If you need refresh-token grants or extension grants, add the corresponding providers according to your contract. Do not enable every grant unnecessarily.

### 5.4. Obtaining an Access Token for a Service Principal

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
class InventoryAccessTokenService {

    private final OAuth2AuthorizedClientManager manager;

    InventoryAccessTokenService(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    String getAccessToken() {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                    .withClientRegistrationId("inventory")
                    .principal("orders-api")
                    .build();

        OAuth2AuthorizedClient authorizedClient =
                manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "Could not authorize Inventory API client");
        }

        return authorizedClient.getAccessToken().getTokenValue();
    }
}
~~~

`principal("orders-api")` is the principal name used to associate the stored authorized client with the service. It is neither an access token nor an end user. Use a stable identifier for the service client to avoid creating excessive per-user authorized-client entries when using Client Credentials.

### 5.5. Using the Token with RestClient

A straightforward approach is to obtain the token via the manager and attach it to the request:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class InventoryClient {

    private final InventoryAccessTokenService tokens;
    private final RestClient restClient;

    InventoryClient(InventoryAccessTokenService tokens,
                    RestClient.Builder builder) {
        this.tokens = tokens;
        this.restClient = builder
            .baseUrl("https://inventory.example.test")
            .build();
    }

    InventoryDto getInventory(String sku) {
        String token = tokens.getAccessToken();

        return restClient.get()
            .uri("/api/inventory/{sku}", sku)
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .body(InventoryDto.class);
    }
}

record InventoryDto(String sku, int available) {}
~~~

Here, the Orders API uses a **service identity token** for the outbound request. Alice's token is not present in this Authorization header.

### 5.6. Integrating OAuth2 Client Directly into RestClient

Spring Security 7.1 provides `OAuth2ClientHttpRequestInterceptor` to use `OAuth2AuthorizedClientManager` to automatically attach a Bearer token to outbound requests.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver;
import org.springframework.web.client.RestClient;

@Configuration
class InventoryRestClientConfiguration {

    @Bean
    RestClient inventoryRestClient(
            OAuth2AuthorizedClientManager manager) {

        OAuth2ClientHttpRequestInterceptor interceptor =
                new OAuth2ClientHttpRequestInterceptor(manager);

        // Application-specific principal, not tied to the current user.
        interceptor.setPrincipalResolver(
                new RequestAttributePrincipalResolver());

        return RestClient.builder()
            .baseUrl("https://inventory.example.test")
            .requestInterceptor(interceptor)
            .build();
    }
}
~~~

When calling:

~~~java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributePrincipalResolver.principal;

InventoryDto inventory = inventoryRestClient.get()
    .uri("/api/inventory/{sku}", sku)
    .attributes(clientRegistrationId("inventory"))
    .attributes(principal("orders-api"))
    .retrieve()
    .body(InventoryDto.class);
~~~

The interceptor uses the registration ID and principal attributes to find/authorize the right client. This approach is useful when an application calls multiple downstream services with different registrations.

**Note:** if you do not configure an appropriate principal resolver/request attribute, the interceptor may default to using the current principal in the SecurityContext. For Client Credentials, that can create per-user authorized-client records when the goal is a shared service identity. Choose the principal intentionally.

## 6. Controlled Forwarding of the Incoming Access Token

If the incoming token was already issued with an audience and scope intended for downstream, you can use that token in the outbound request.

Example controller receiving a JWT:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrdersController {

    private final InventoryRelayService inventory;

    OrdersController(InventoryRelayService inventory) {
        this.inventory = inventory;
    }

    @GetMapping("/api/orders/inventory-check")
    InventoryDto checkInventory(@AuthenticationPrincipal Jwt jwt) {
        return inventory.getForUser(jwt, "SKU-42");
    }
}
~~~

The service can read the token value from the verified JWT:

~~~java
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class InventoryRelayService {

    private final RestClient restClient;

    InventoryRelayService(RestClient.Builder builder) {
        this.restClient = builder
            .baseUrl("https://inventory.example.test")
            .build();
    }

    InventoryDto getForUser(Jwt jwt, String sku) {
        return restClient.get()
            .uri("/api/inventory/{sku}", sku)
            .headers(headers ->
                headers.setBearerAuth(jwt.getTokenValue()))
            .retrieve()
            .body(InventoryDto.class);
    }
}
~~~

The code above is only the **transport mechanism for the token**. It does not by itself prove the token is allowed to reach the Inventory API. Before using it, the system must ensure the token was verified by the Orders API, the audience includes the Inventory API, the scopes are sufficient for the operation, the Inventory API trusts that issuer/profile, forwarding complies with privacy policies, and the downstream host is configured as trusted.

If the token's `aud` is only `orders-api`, do not use relay. Have the AS intentionally issue a multi-audience token or use token exchange to obtain a token intended for Inventory.

### 6.1. Opaque Token Relay

With opaque tokens, the principal after introspection is not necessarily a `Jwt`. If you want to relay the raw token, you must retrieve the token value from the proper authentication type, such as `BearerTokenAuthentication` depending on your configuration. Do not attempt to call `getTokenValue()` on a principal that does not have that method.

Opaque token relay must also satisfy audience, scope, and trust contracts. Successful token introspection at the Orders API does not automatically prove the Inventory API will accept the token.

### 6.2. Do Not Manually Construct Headers from Unverified Tokens

Do not write a filter that reads the raw `Authorization` header and forwards the token to an arbitrary URL. If the token has not gone through Resource Server authentication or the destination is not allowlisted, the service can become a proxy that leaks credentials.

## 7. Token Exchange with Spring Security

Spring Security includes a provider for **Token Exchange**. Per current documentation, this provider must be explicitly added to `OAuth2AuthorizedClientProvider`; it is not part of the default set of providers such as authorization code, refresh token, and client credentials.

Token Exchange is appropriate when the inbound token was issued for the Orders API, the Orders API needs a different token for the Inventory API, downstream still needs to know the user subject, and the AS has a policy allowing the Orders API to exchange the token for a new audience/scope.

### 7.1. Configuring a Registration for Token Exchange

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-exchange:
            provider: identity
            client-id: orders-api
            client-secret: ${INVENTORY_EXCHANGE_CLIENT_SECRET}
            authorization-grant-type: urn:ietf:params:oauth:grant-type:token-exchange
            scope:
              - inventory.read
        provider:
          identity:
            token-uri: https://identity.example.test/oauth2/token
~~~

The registration ID `inventory-exchange` is a local name within the application. The Authorization Server must support RFC 8693 or the corresponding extension, and must permit client `orders-api` to exchange the subject token for the required audience/resource.

### 7.2. Enabling TokenExchangeOAuth2AuthorizedClientProvider

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;

@Configuration
class TokenExchangeConfiguration {

    @Bean
    OAuth2AuthorizedClientManager tokenExchangeManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        TokenExchangeOAuth2AuthorizedClientProvider exchangeProvider =
                new TokenExchangeOAuth2AuthorizedClientProvider();

        OAuth2AuthorizedClientProvider providers =
                OAuth2AuthorizedClientProviderBuilder.builder()
                    .provider(exchangeProvider)
                    .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                    registrations, authorizedClientService);
        manager.setAuthorizedClientProvider(providers);
        return manager;
    }
}
~~~

This is a service-tier configuration. If the application runs inside an HTTP request context and needs a request/session-scoped repository, you can use `DefaultOAuth2AuthorizedClientManager` with the corresponding `OAuth2AuthorizedClientRepository`.

### 7.2.1. Adding Audience or Resource per the Authorization Server Contract

`TokenExchangeOAuth2AuthorizedClientProvider` uses `TokenExchangeGrantRequest` and a token response client to send requests to the token endpoint. If the AS requires additional parameters such as `audience` or `resource`, configure `TokenExchangeOAuth2AuthorizedClientProvider` with a customized `RestClientTokenExchangeTokenResponseClient`:

~~~java
import org.springframework.security.oauth2.client.endpoint.RestClientTokenExchangeTokenResponseClient;
import org.springframework.security.oauth2.client.TokenExchangeOAuth2AuthorizedClientProvider;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;

RestClientTokenExchangeTokenResponseClient responseClient =
        new RestClientTokenExchangeTokenResponseClient();

responseClient.addParametersConverter(grantRequest -> {
    MultiValueMap<String, String> parameters =
            new LinkedMultiValueMap<>();

    // "audience" is an example depending on the AS; another AS may use "resource".
    parameters.set("audience", "inventory-api");
    return parameters;
});

TokenExchangeOAuth2AuthorizedClientProvider exchangeProvider =
        new TokenExchangeOAuth2AuthorizedClientProvider();
exchangeProvider.setAccessTokenResponseClient(responseClient);
~~~

This is supplementary configuration for the manager example in section 7.2; pass the configured `exchangeProvider` into `OAuth2AuthorizedClientProviderBuilder`. Do not send both `audience` and `resource` arbitrarily: choose the parameter according to the AS contract, and verify that the token response actually contains the desired audience/scope. `resource` per RFC 8707 is one way to specify a resource; `audience` is commonly a parameter supported by some providers.

### 7.3. Exchanging a Token from JwtAuthenticationToken

By default, Spring Security can resolve the subject token from the principal of a `JwtAuthenticationToken`. For example:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
class InventoryTokenExchangeService {

    private final OAuth2AuthorizedClientManager manager;

    InventoryTokenExchangeService(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    OAuth2AuthorizedClient exchange(Authentication incomingAuthentication) {
        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                    .withClientRegistrationId("inventory-exchange")
                    .principal(incomingAuthentication)
                    .build();

        OAuth2AuthorizedClient authorizedClient =
                manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "Token exchange did not return an authorized client");
        }
        return authorizedClient;
    }
}
~~~

When the authentication is a `JwtAuthenticationToken`, the provider defaults to taking the `Jwt` from `Authentication.getPrincipal()` as the subject token. If the principal type differs, or the subject token comes from another source, you must configure `setSubjectTokenResolver(...)`.

### 7.4. Sending the New Token to the Inventory API

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
class ExchangedInventoryClient {

    private final InventoryTokenExchangeService tokenExchange;
    private final RestClient restClient;

    ExchangedInventoryClient(
            InventoryTokenExchangeService tokenExchange,
            RestClient.Builder builder) {
        this.tokenExchange = tokenExchange;
        this.restClient = builder
            .baseUrl("https://inventory.example.test")
            .build();
    }

    InventoryDto getInventory(Authentication incoming, String sku) {
        OAuth2AuthorizedClient exchanged =
                tokenExchange.exchange(incoming);

        String downstreamToken =
                exchanged.getAccessToken().getTokenValue();

        return restClient.get()
            .uri("/api/inventory/{sku}", sku)
            .headers(headers ->
                headers.setBearerAuth(downstreamToken))
            .retrieve()
            .body(InventoryDto.class);
    }
}
~~~

The received token must be intended for the Inventory API, carry minimal scopes, and still represent the right user/actor per AS policy. Do not log this token or return it to the browser.

### 7.5. Subject Token and Actor Token

RFC 8693 distinguishes between:

- **Subject token**: the token representing the subject on whose behalf the delegation is being performed.
- **Actor token**: the token representing the actor performing the action on behalf of the subject.

In the Shop Web → Orders API → Inventory API chain, token exchange can preserve Alice as the subject and record Orders API as the actor, if the AS supports actor tokens/actor claims. Spring Security's `TokenExchangeOAuth2AuthorizedClientProvider` **does not resolve an actor token by default**; you must configure `setActorTokenResolver(...)` if your use case requires it.

This is an important distinction for auditing and the delegation chain. If only a subject token is present, the Inventory API can see Alice, but lacks full evidence of which service performed the call step.

### 7.6. Token Exchange Does Not Automatically Downscope

The client must request the appropriate audience/resource/scope and the AS must enforce the policy. Simply registering the token exchange grant type does not guarantee the new token will have narrower permissions. You must inspect response claims/metadata and test the issued tokens.

## 8. WebFlux: Coexisting Resource Server and Reactive OAuth2 Client

In WebFlux, the corresponding components are:

| Servlet | Reactive |
| --- | --- |
| `OAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientManager` |
| `OAuth2AuthorizedClientProvider` | `ReactiveOAuth2AuthorizedClientProvider` |
| `ClientRegistrationRepository` | `ReactiveClientRegistrationRepository` |
| `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| `ServletOAuth2AuthorizedClientExchangeFilterFunction` | `ServerOAuth2AuthorizedClientExchangeFilterFunction` |
| `HttpSecurity` | `ServerHttpSecurity` |

### 8.1. Configuring WebFlux Resource Server + OAuth2 Client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll())
            .oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(Customizer.withDefaults()))
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

WebFlux requires configuring a `ReactiveJwtDecoder` or opaque introspector for inbound tokens, along with OAuth2 Client registrations and a reactive authorized-client manager for outbound calls.

### 8.2. Reactive Client Credentials Manager

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;

@Configuration
class ReactiveOAuth2ClientConfiguration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager reactiveAuthorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClientService) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                    registrations, authorizedClientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` is suitable when running outside a `ServerWebExchange`, such as service-tier/background work. Inside a WebFlux request context, use `DefaultReactiveOAuth2AuthorizedClientManager` with `ServerOAuth2AuthorizedClientRepository`.

### 8.3. Calling Downstream with Reactive WebClient

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class InventoryWebClientConfiguration {

    @Bean
    WebClient inventoryWebClient(
            ReactiveOAuth2AuthorizedClientManager manager) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

        return WebClient.builder()
            .baseUrl("https://inventory.example.test")
            .filter(oauth)
            .build();
    }
}
~~~

Using a registration for the request:

~~~java
Mono<InventoryDto> inventory =
    inventoryWebClient.get()
        .uri("/api/inventory/{sku}", sku)
        .attributes(clientRegistrationId("inventory"))
        .retrieve()
        .bodyToMono(InventoryDto.class);
~~~

The filter function uses the manager to authorize/re-authorize the client and places the Bearer token on the outbound request. You can provide a specific `OAuth2AuthorizedClient` or `clientRegistrationId` via request attributes.

### 8.4. Do Not Attach Tokens to Every WebClient Request by Default

Spring Security allows setting a default authorized client or default registration ID on the exchange filter function. The documentation advises caution because **every request passing through that WebClient can receive the access token**.

Better practices:

- Use a dedicated WebClient per downstream trust boundary.
- Select the registration ID explicitly on each request.
- Do not use a WebClient with an OAuth filter for arbitrary URLs.
- Do not let callers control the host/URI and allow the interceptor to attach a token.

### 8.5. Reactive Token Exchange

WebFlux has `TokenExchangeReactiveOAuth2AuthorizedClientProvider` and `WebClientReactiveTokenExchangeTokenResponseClient`. As with Servlet, the provider must be explicitly configured and the Authorization Server must support the grant/policy.

When using `JwtAuthenticationToken`, the provider can resolve the subject token from the JWT principal. If an actor token or a different subject token source is needed, configure the corresponding reactive resolver. Do not call `block()` to fetch a token inside a WebFlux controller/service; keep the entire flow in `Mono`/`Flux`.

## 9. Choosing the Principal for Storing Authorized Clients

An easily overlooked detail is that **authorized clients are keyed by principal name**. The same registration can create different authorized-client records per principal.

| Principal Used | Storage Semantics |
| --- | --- |
| `orders-api` | A shared service-level authorized client for the service identity |
| `alice` | Authorized client tied to user Alice |
| `JwtAuthenticationToken` | Can use the current principal for token exchange/delegation |
| `anonymousUser` | Can create a shared record if used intentionally; usually needs semantics review |

### 9.1. Client Credentials Typically Uses an Application Principal

If the `inventory` registration uses `client_credentials`, the authorized client is usually a service identity. Using a stable principal such as `orders-api` avoids creating a separate token cache entry for every end user unnecessarily.

### 9.2. Delegated Tokens Should Be Scoped per User/Context

If using authorization code or token exchange on behalf of a user, the authorized client may need to be differentiated by user or delegation context. If all users are stored under the `orders-api` principal, Alice's token could mistakenly be used for Bob.

Do not use a global principal for delegated tokens unless the cache/storage key also safely binds the subject/tenant/delegation context.

### 9.3. Principal Name Is Not Automatically the Token Subject

The principal used to store the authorized client is a key for Spring's persistence. It does not automatically change the `sub` inside the access token. When you need to audit the subject/actor, read claims/tokens per contract or use metadata from token exchange.

## 10. Token Lifetime, Refresh, and Persistence

`OAuth2AuthorizedClientManager` manages authorized clients, not just one-off token fetches.

### 10.1. Client Credentials

Client Credentials typically does not return a refresh token on many Authorization Servers. When the access token expires, the manager can request a new token using the client credentials grant. Thus, the `clientCredentials()` provider can re-authorize when the token expires.

### 10.2. Authorization Code

If an authorized client has a refresh token and the `refreshToken()` provider is configured, the manager can use the refresh token to obtain a new access token. Expired or invalid refresh tokens must be handled via a failure handler.

### 10.3. Token Exchange

The token exchange lifecycle depends on the AS and provider. Do not assume every exchanged token comes with a refresh token. Upon expiration, the application may have to exchange again from a still-valid subject token; if the subject token has expired, a new authentication/delegation flow is required.

### 10.4. Authorized-Client Storage

Spring provides:

- `OAuth2AuthorizedClientRepository`: persists authorized clients across web requests.
- `OAuth2AuthorizedClientService`: manages authorized clients at the application level.
- `InMemoryOAuth2AuthorizedClientService`: in-memory default in some configurations.
- `JdbcOAuth2AuthorizedClientService`: persistence backed by JDBC.

Choose storage based on replica count, restarts, scale, and sensitivity. If multiple instances need the same authorized client, in-memory storage can lead to repeated token requests and unshared caches. JDBC/shared stores provide persistence, but tokens must be protected at rest/in transit and retention must be managed.

### 10.5. Removing the Authorized Client When Downstream Reports an Invalid Token

Spring Security supports an authorization failure handler to remove an invalid authorized client, for example when downstream returns `invalid_token`. Configuring an appropriate handler allows the manager to request a fresh token on the next request.

Do not blindly delete the authorized client on every 401/403 error:

- 401 can mean an expired/invalid token.
- 403 often indicates a missing scope/permission; repeatedly requesting a new token will not resolve policy denials.
- 5xx/timeouts do not prove the token is invalid.

## 11. Token Audience and Scope Downstream

Audience answers: **which Resource Server was this token issued for?** Scope answers: **what types of operations does this token allow?**

Example:

~~~json
{
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

You should not send this token to the Inventory API and ask the Inventory API to accept it merely because the issuer is the same.

A token for downstream may need:

~~~json
{
  "aud": ["inventory-api"],
  "scope": "inventory.read"
}
~~~

### 11.1. Downstream Should Not Trust Every Token from the Same Issuer

The Inventory API needs to verify a trusted issuer, that the audience includes the Inventory API, that the token is still valid, that scopes/authorities are sufficient for the endpoint, that the token type/profile matches, and tenant/owner/business authorization if required.

A shared issuer does not imply a shared audience. A token valid for the Orders API can still be invalid for the Inventory API.

### 11.2. Downscoping

When exchanging, request minimal permissions for downstream:

~~~text
Inbound token:
    aud = orders-api
    scope = orders.read orders.cancel inventory.read inventory.write

Exchanged token:
    aud = inventory-api
    scope = inventory.read
~~~

This illustration shows the new token retaining only the scope the Inventory API needs. The AS must enforce downscoping; the Orders API does not strip claims from the old token itself and treat the result as a valid new token.

### 11.3. Tenant and User Context

If the Inventory API enforces tenant-based authorization, token exchange or Client Credentials must carry a tenant context issued per policy. Do not take a caller-supplied `X-Tenant-Id` and pass it into a token request as proof of membership.

With a service token, dedicated scopes for tenant operations or policies verifying membership via service identity may be required. With a delegated token, preserve the user subject and tenant context according to the AS/downstream contract.

## 12. Token Relay and Token Exchange: Deciding by Audience

**Case 1: Intentional multi-audience token**

~~~text
Inbound token:
  aud = [orders-api, inventory-api]
  scope = orders.read inventory.read

Orders API -> Inventory API:
  can relay the token if the contract allows
~~~

**Case 2: Token intended only for Orders API**

~~~text
Inbound token:
  aud = orders-api
  scope = orders.read

Orders API -> Inventory API:
  do not relay
  -> Client Credentials if only service identity is needed
  -> Token Exchange if user delegation is needed
~~~

### 12.1. Do Not Modify the Audience in a JWT

Do not take an inbound token, decode the payload, change `aud` to `inventory-api`, and forward it. The signature will no longer be valid. Nor should you re-sign the token with the Orders API's private key and claim it is an access token from the AS.

Only the Authorization Server may issue access tokens according to its policy. Token Exchange is the standard way to request a new token.

## 13. Security Risks When a Resource Server Is Also an OAuth2 Client

### 13.1. Confused Deputy

The Orders API has permission to call the Inventory API using a service token. If an endpoint lets a Client pass an arbitrary URL and the Orders API attaches a token to the request, an attacker can trick the service into sending credentials to an attacker-controlled host.

**Solution:** allowlist destination hosts, use dedicated clients for specific downstream services, do not take arbitrary URIs from requests, and only add the Authorization header after validating that the destination is trusted.

### 13.2. Token Leakage via Logs/Traces

Do not log:

- Inbound `Authorization` headers.
- Outbound `Authorization` headers.
- Access/refresh token values.
- Token response bodies.
- Client secrets/private keys.

Traces may record destination, registration ID, status, latency, and correlation ID, but credentials must be redacted. HTTP wiretap/debug logging configurations must be reviewed carefully.

### 13.3. Over-Privileged Service Tokens

A Client Credentials token represents the service. If you grant `inventory.admin` to the Orders API when it only needs `inventory.read`, any SSRF or compromise in the Orders API can escalate into inventory admin privileges.

Require minimal scopes, specific audiences, and dedicated service account policies.

### 13.4. Delegation Confusion

If the Orders API uses Client Credentials instead of a delegated token, the Inventory API may only see the service identity and fail to verify user permissions. Conversely, relaying an overly broad inbound token may give Inventory unnecessary scopes.

Explicitly choose between service identity and user delegation; do not conflate the two.

### 13.5. User/Tenant Context Misuse in Caches

Authorized-client caches must be keyed by the appropriate principal/context. If Alice's exchanged token is stored under the global principal `orders-api`, Bob could receive a token representing Alice. If Client Credentials uses per-user principals, the cache bloats unnecessarily.

### 13.6. Redirects and Outbound Hosts

If an HTTP client automatically follows redirects from a trusted host to another host, ensure the Authorization header is not forwarded unintentionally. Configure redirect policies, allowlists, and test redirects to external hosts.

### 13.7. Retries Can Generate Many Token Requests

Retrying the entire pipeline when the Authorization Server times out can generate storms of token requests and increase load. Use timeouts, retries with backoff/jitter, and only retry transient errors; do not continuously retry `invalid_client`/`invalid_scope`.

### 13.8. Inbound Token Expiring Mid-Workflow

A long-running request may start while the token is valid, only for the token to expire before the service performs token exchange or downstream processing. Design appropriate token lifetimes, timeouts, and re-auth/delegation flows; do not skip validation to complete the workflow.

## 14. Error Handling Between Services

| Outbound Error | Interpretation | Typically Appropriate Action |
| --- | --- | --- |
| Token endpoint `invalid_client` | Invalid/unauthorized client credentials | Report configuration error; do not retry indefinitely |
| Token endpoint `invalid_scope` | Requested scope not granted | Fix policy/request; do not weaken validation |
| Token exchange `invalid_grant` | Subject token invalid/ineligible | Inspect inbound token/delegation; do not fall back to higher service privileges |
| Token endpoint timeout/5xx | AS temporarily unavailable | Timeout/backoff/circuit breaker |
| Downstream 401 `invalid_token` | Outbound token rejected | Can remove authorized client and re-authorize via handler |
| Downstream 403 | Valid token but insufficient permissions | Do not retry with a stronger token; handle authorization denial |
| Downstream 404 | Resource does not exist/not visible | Preserve API contract; do not switch credentials |
| Downstream 429 | Rate limit | Respect Retry-After and back off |
| Downstream 5xx | Target service error | Controlled retry if the operation is idempotent |

**Do not turn every downstream error into a 401 for the Client calling the Orders API.** The inbound token may be completely valid; the error lies with the outbound token, the AS, or the Inventory API. Error mapping must preserve boundaries and never expose tokens/secrets.

## 15. End-to-End Example: Orders API Using Client Credentials

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant S as Shop Web
    participant AS as Authorization Server
    participant O as Orders API
    participant I as Inventory API

    U->>S: View order
    S->>O: Bearer token for Orders API
    O->>O: Resource Server verifies JWT + orders.read
    O->>O: Check if Alice is authorized to view order
    O->>AS: Client Credentials for inventory.read
    AS-->>O: Service identity token, aud=inventory-api
    O->>I: Service identity Bearer token
    I->>I: Verify aud + inventory.read
    I-->>O: Inventory
    O-->>S: Order result
~~~

In this flow:

- The inbound token identifies Alice.
- The outbound token identifies the Orders API.
- The Inventory API only sees the service identity.
- If Inventory needs to check Alice's permissions, Client Credentials is insufficient; switch to token exchange/relay per the contract.

## 16. End-to-End Example: Orders API Exchanging a Token on Behalf of Alice

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant S as Shop Web
    participant AS as Authorization Server
    participant O as Orders API
    participant I as Inventory API

    U->>S: View order-related inventory info
    S->>O: Inbound token T1 (aud=orders-api)
    O->>O: Verify T1 and authorization
    O->>AS: Token Exchange: subject_token=T1, audience=inventory-api, scope=inventory.read
    AS->>AS: Check client, user, grant, and delegation policy
    AS-->>O: Token T2 (aud=inventory-api)
    O->>I: Bearer T2
    I->>I: Verify T2, subject, scope, and tenant policy
    I-->>O: Permitted inventory
    O-->>S: Response
~~~

T2 is a new token issued by the AS. The Inventory API can see Alice as the subject, while the Orders API can be recorded as the actor if token exchange uses an actor token/claim per policy.

## 17. Testing When a Service Is Both a Resource Server and an OAuth2 Client

A test suite should be divided into inbound, outbound, and end-to-end tests:

| Area | What to Verify |
| --- | --- |
| Inbound Resource Server | Tokens with invalid signature/issuer/audience/expiry are rejected; scopes and user policies are enforced |
| Client Credentials | Correct client registration, grant type, client authentication, and scope |
| Token relay | Outbound token matches inbound token; only used with appropriate audience/scope |
| Token Exchange | Correct subject token, target audience/resource, and scope; actor token if needed |
| Authorized-client persistence | Principal key does not mix up users/services |
| Refresh/re-authorize | Expired tokens are re-acquired; invalid_grant is handled properly |
| Downstream request | Correct Authorization scheme/token; tokens are never sent to untrusted hosts |
| Error handling | 401/403/429/5xx are classified; retries and authorized-client removal behave properly |
| Secrets/logging | No tokens, refresh tokens, or client secrets appear in logs |

### 17.1. Mocking the Authorization Server and Downstream

You can use WireMock/MockWebServer or a test Authorization Server to:

1. Receive token requests.
2. Verify `grant_type` and client authentication.
3. Return a test access token with expiry/scope/audience per scenario.
4. Receive outbound requests from the Orders API.
5. Verify that the Authorization header contains the expected token.

For inbound JWTs, use JWTs signed with a test key and a real Resource Server decoder in integration tests. For service unit tests, you can mock `JwtAuthenticationToken` or the manager, but there must be real pipeline tests proving the filter/decoder works.

### 17.2. Testing That Client Credentials Does Not Depend on the End User

Send requests with two different users:

~~~text
Alice -> Orders API -> Inventory API
Bob   -> Orders API -> Inventory API
~~~

If the outbound identity is the Orders API, the service-level token can be reused under the `orders-api` principal. Tests verify:

- The Inventory API receives the right service token.
- Neither Alice's nor Bob's token is sent by mistake.
- The cache does not unintentionally create or mix user-specific authorized clients.

### 17.3. Testing Audience-Compliant Token Relay

Scenario:

- Token A has audience `orders-api` and scope `orders.read`.
- The Orders API accepts A as valid.
- The Inventory API only accepts audience `inventory-api`.

Expectation: the Orders API **does not relay A** to Inventory as if that token were valid there. Tests must prove the API selects an exchanged/service token or denies per policy.

### 17.4. Testing Token Exchange

Test token requests containing:

~~~text
grant_type=urn:ietf:params:oauth:grant-type:token-exchange
subject_token=T1
subject_token_type=urn:ietf:params:oauth:token-type:access_token
scope=inventory.read
audience=inventory-api
~~~

Specific parameters may vary by AS contract; what needs verification is that the subject token, target audience/resource, and scope are passed accurately. Then verify downstream receives T2, not T1.

Negative cases:

- Expired subject token.
- Client not permitted to exchange.
- Scope exceeds policy.
- Audience/resource not permitted by the AS.
- Invalid or missing actor token when policy requires it.
- AS timeout or returning `invalid_grant`.

### 17.5. Testing Principal Isolation

For delegated tokens:

~~~text
Alice -> token exchange -> T_A (sub=alice)
Bob   -> token exchange -> T_B (sub=bob)
~~~

Tests verify that the authorized-client storage key does not cause T_A to be returned for Bob. For Client Credentials:

~~~text
principal=orders-api -> service token
~~~

Tests verify that the service token is not cached as a user token or vice versa.

### 17.6. Testing Downstream 401 and 403

- Downstream returns `401 invalid_token`: verify the failure handler removes the invalid authorized client if configured.
- Subsequent request: the manager can re-authorize.
- Downstream returns `403 insufficient_scope`: do not repeat token requests indefinitely or escalate scopes automatically.
- Downstream returns `500`: do not remove the authorized client solely due to a server error.

## 18. Common Misconceptions

**"Because the Resource Server already verified the token, it can use that token to call any service."** False. The audience and scope may only be intended for the current service.

**"Simply enabling `oauth2Client()` makes Spring automatically know which outbound token to use."** No. You must select the ClientRegistration, principal, and grant/provider.

**"Client Credentials represents the logged-in user."** No. It represents the OAuth2 Client/service.

**"Token relay is always better than token exchange because it avoids calling the token endpoint."** No. Relay can violate audience, scope, and delegation policies.

**"Token Exchange is automatically enabled alongside client_credentials."** No. The Token Exchange provider must be explicitly registered/configured per documentation.

**"Token exchange means the Orders API re-signs the JWT itself."** No. The AS issues a new token according to policy.

**"Token exchange always downscopes."** No. The client must request the right scope/resource and the AS must enforce it.

**"Once a token is exchanged, downstream authorization checks are unnecessary."** False. Downstream still checks audience, scope, tenant, owner, and business policies.

**"Using the current principal for every outbound client is safe."** No. Client Credentials may need an application principal; delegated tokens need a per-user/context key.

**"Using one WebClient with a default OAuth client for all hosts is fine."** This risks sending tokens to unintended destinations. Use dedicated clients and explicit registrations.

**"A 401 from downstream means the user's inbound token is wrong."** Not necessarily. The outbound token may be expired/invalid or have the wrong audience.

**"On 403, request a new token with stronger scopes."** No. 403 is typically an authorization denial; do not self-escalate privileges.

**"Broadly scoped service tokens make downstream simpler."** They expand the blast radius if the service is compromised. Grant the minimum required scope.

**"WebFlux can call the manager using `block()`."** Avoid doing so inside a reactive pipeline; keep `Mono`/`Flux` intact to avoid blocking the event loop.

## 19. Implementation Checklist

### Inbound Resource Server

- [ ] Verify signature/introspection, issuer, audience, expiry, and token profile.
- [ ] Check endpoint scopes/authorities.
- [ ] Check owner, tenant, and business policies before processing.
- [ ] Do not treat the inbound token as a credential for every downstream service.

### Outbound OAuth2 Client

- [ ] Give each downstream service an appropriate ClientRegistration and audience/scope.
- [ ] Explicitly choose between Client Credentials, token relay, and token exchange.
- [ ] Choose the right principal: service-level or user/delegation context.
- [ ] Use `OAuth2AuthorizedClientManager` or `ReactiveOAuth2AuthorizedClientManager`.
- [ ] Choose an authorized-client repository/service suited to the lifecycle and replica count.
- [ ] Configure refresh/re-authorization and failure handlers.
- [ ] Never send tokens to arbitrary URLs.
- [ ] Never log tokens/secrets.

### Delegation/Token Exchange

- [ ] Ensure the Authorization Server supports the grant and policy.
- [ ] Ensure the subject token is a verified inbound token.
- [ ] Target audience/resource matches downstream.
- [ ] Scopes are downscoped according to least privilege.
- [ ] Actor token is configured if delegation chain auditing is required.
- [ ] Token exchange failures do not fall back to higher service privileges outside policy.

### WebFlux

- [ ] Use reactive managers/providers/repositories.
- [ ] Never call `block()` in the request pipeline.
- [ ] Choose the right manager inside vs. outside `ServerWebExchange`.
- [ ] Select specific WebClients and registrations per downstream service.

## 20. Practice Scenarios

**A.** The Orders API receives a JWT with audience `orders-api` and needs to call the Inventory API. Can it send the raw token?

**No**, unless the token contract includes an appropriate audience for Inventory. Otherwise, use Client Credentials if only service identity is needed, or Token Exchange if user delegation is needed.

**B.** The Inventory API only needs to know that the Orders API is calling. Which grant should be chosen?

Usually **Client Credentials** with the Inventory audience and minimal scope.

**C.** Inventory needs to check Alice's permissions, but the inbound token is only for the Orders API. What should be done?

Use **Token Exchange/OBO** if the AS supports it, obtaining a new token intended for Inventory and representing Alice per policy.

**D.** Can `DefaultOAuth2AuthorizedClientManager` be used in a scheduler?

This manager is designed for an `HttpServletRequest` context. For service/background work, use `AuthorizedClientServiceOAuth2AuthorizedClientManager`.

**E.** A WebFlux scheduler needs a Client Credentials token. Which manager should be used?

Use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` outside `ServerWebExchange`, with a reactive client registration/service.

**F.** Does the Token Exchange provider resolve an actor token automatically?

Not by default. If an actor token is needed, configure `setActorTokenResolver` per the appropriate API.

**G.** Downstream returns 403 due to a missing scope. Should we automatically request a token with admin scope?

No. Update the authorization policy/request according to approved requirements; do not self-escalate privileges.

**H.** Is a WebClient configured to attach an access token by default to every request safe?

Risky. Select the client registration per request and restrict to trusted hosts/destinations.

**I.** Two users, Alice and Bob, both call the Orders API; Alice's exchanged token is cached under the shared principal `orders-api`. What is the issue?

Yes, there is a problem. Alice's token could be returned for Bob. Delegated authorized clients must be isolated by user/delegation context.

**J.** Since the Orders API already verified the inbound JWT, can authorization checks in the Inventory API be skipped?

No. The Inventory API must verify its outbound token and enforce resource permissions per its own policy.

---

## Conclusion

A **Spring Security Resource Server application can simultaneously act as an OAuth2 Client**. On the inbound side, the Resource Server verifies access tokens and caller permissions. On the outbound side, the OAuth2 Client manages authorized clients and access tokens intended for downstream services. The two flows may be related, but they do not automatically share credentials.

Choose **Client Credentials** when downstream only needs service identity; **token relay** when the inbound token was issued for downstream and has the right scope; and **Token Exchange/OBO** when a new downstream-specific token is required while preserving user delegation. Spring Security provides `OAuth2AuthorizedClientManager`/`ReactiveOAuth2AuthorizedClientManager`, providers, and WebClient/RestClient integrations to manage tokens; Token Exchange requires an explicitly configured provider and Authorization Server policy support.

In all cases, verify **audience, scope, principal, tenant, and resource permissions** at each boundary. Never forward tokens to untrusted hosts, attach overly broad service tokens, cache user tokens under a global principal, or log credentials. **A service can play two OAuth2 roles in the same request flow, but it must clearly define which identity is being represented on each outbound call.**

## References

1. [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/)
2. [Spring Security — Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
3. [Spring Security — Authorized Client Features](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
4. [Spring Security 7.1 — Authorization Grant Support / Token Exchange](https://docs.spring.io/spring-security/reference/7.1/servlet/oauth2/client/authorization-grants.html)
5. [Spring Security — Reactive OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/)
6. [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693.html)
7. [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749.html)
