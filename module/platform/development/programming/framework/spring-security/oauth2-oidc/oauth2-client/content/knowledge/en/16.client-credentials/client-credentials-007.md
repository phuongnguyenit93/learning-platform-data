# 16.7. Reusing Valid Tokens and Fetching New Tokens on Expiration

## 1. Why Does Client Credentials Need Access Token Reuse?

In **Spring Security OAuth 2.0/OIDC Client**, a backend application may need to call a protected API with no logged-in user. Examples:

- An inventory service calling an inventory-check API.
- A billing worker calling a reconciliation API.
- A scheduled job synchronizing data with a partner system.
- A backend-for-backend integration calling an internal API using permissions granted to the application itself.

These scenarios typically use the **OAuth 2.0 Client Credentials Grant**. The client proves its identity to the Authorization Server (AS) and receives an **access token** to call the Resource Server (API).

An unsound implementation is **calling the Token Endpoint before every API request**:

```text
API Request #1 -> POST /token -> access token -> GET /inventory
API Request #2 -> POST /token -> access token -> GET /inventory
API Request #3 -> POST /token -> access token -> GET /inventory
...
```

If the access token has a 30-minute lifetime, consecutive token requests like these are wasteful. They increase latency, Authorization Server load, outbound connections, and the risk of hitting rate limits.

A better approach:

```text
First call:
    No token yet
    -> POST /token
    -> receive access token AT1
    -> save OAuth2AuthorizedClient
    -> call API using AT1

Subsequent calls while AT1 is still valid:
    -> look up OAuth2AuthorizedClient
    -> call API using AT1
    -> no POST /token

When AT1 expires or is about to expire:
    -> POST /token with client_credentials
    -> receive access token AT2
    -> replace saved authorized client
    -> call API using AT2
```

In Spring Security, this can be achieved using **`OAuth2AuthorizedClientManager`** and **`ClientCredentialsOAuth2AuthorizedClientProvider`**, combined with an **`OAuth2AuthorizedClientService`** to retain tokens across calls.

**Core idea:** _Do not manually write a `static String accessToken` variable_. Let Spring Security's OAuth2 Client components manage tokens, expiration, client registrations, principals, and storage.

### Lesson Objectives

After this lesson, you will:

1. Understand the difference between **reusing an access token** and **sending a new token request**.
2. Know why Client Credentials typically does not use a refresh token.
3. Understand `OAuth2AuthorizedClient`, `OAuth2AuthorizedClientService`, `OAuth2AuthorizedClientProvider`, and `OAuth2AuthorizedClientManager`.
4. Grasp how Spring Security decides whether a token is still valid or needs re-issuance, including `expiresAt` and `clockSkew`.
5. Configure `AuthorizedClientServiceOAuth2AuthorizedClientManager` for backend applications and scheduled jobs.
6. Implement Java examples using tokens to call APIs.
7. Understand token storage keys composed of **`registrationId` and `principalName`**.
8. Compare InMemory, JDBC, and distributed token storage.
9. Identify concurrency problems when multiple threads or instances request tokens simultaneously.
10. Handle errors, protect credentials, and avoid reusing tokens with the wrong audience/scope.

In these examples, all URLs, IDs, secrets, and token values are illustrative data.

## 2. Client Credentials Grant: Tokens for Applications, Not Users

The Client Credentials Grant is defined in OAuth 2.0. A **confidential client** proves its own identity to the AS to obtain an access token under its registered permissions.

Diagram:

```mermaid
sequenceDiagram
    autonumber
    participant C as Spring Boot Service
    participant AS as Authorization Server
    participant API as Resource Server

    C->>AS: POST /token: grant_type=client_credentials + client authentication
    AS-->>C: access_token, token_type, expires_in
    C->>API: Authorization: Bearer access_token
    API-->>C: Data
```

Token request example:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.net
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=client_credentials&scope=inventory.read
```

A typical token response:

```json
{
  "access_token": "ACCESS_TOKEN_EXAMPLE",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "inventory.read"
}
```

Fields:

| Field | Meaning |
|---|---|
| `access_token` | Credential sent to the protected API. |
| `token_type` | How the token is used, typically `Bearer`. |
| `expires_in` | Seconds the token remains valid from issuance per AS contract. |
| `scope` | Permissions granted to the token. |
| `refresh_token` | **Normally not issued** with the Client Credentials Grant. |

According to OAuth 2.0, a Client Credentials response **should not include a refresh token**. When the access token expires, the client normally **re-executes the Client Credentials Grant** to obtain a new token.

This is a critical distinction:

```text
Authorization Code / User Delegation:
    access token expires
    -> can use refresh token if issued by AS and still valid

Client Credentials:
    access token expires
    -> call grant_type=client_credentials again
    -> re-prove client identity to the AS
```

Do not add `refresh_token` to a Client Credentials token request just because you see a `refreshToken()` method in Spring Security.

### 2.1. Is There an OIDC ID Token?

Although this module covers **OAuth 2.0/OIDC Client**, the Client Credentials Grant is not a user OIDC Login mechanism. There is no browser login step, no End-User consent in this flow, and you should not expect an ID Token to identify a user.

A Client Credentials access token typically represents the permissions of a **client/service**. Depending on the AS, the token may be a JWT or opaque. Clients must not decode a JWT by default expecting to extract a logged-in human user.

## 3. Why Not Request a New Token for Every Request?

Access tokens are typically issued with a finite lifetime. A valid token can be reused multiple times within the policies of the Authorization Server and Resource Server.

Example:

```text
10:00:00 -> Token Endpoint issues AT1, expires_in = 1800 seconds
10:00:03 -> API call 1 with AT1
10:00:20 -> API call 2 with AT1
10:02:10 -> API call 3 with AT1
10:15:00 -> API call 4 with AT1

If not re-issued early:
10:30:00 -> AT1 expires
```

Each API call **does not need a different access token** if the current token remains eligible for use.

Benefits:

- Fewer requests to the Authorization Server.
- Lower latency for regular API calls.
- Lower risk of hitting token issuance rate limits.
- Fewer repeated TLS handshakes and client authentications.
- Reduced load on the AS under high request volume.
- Allows the app to keep operating temporarily with a still-valid access token even during a brief Token Endpoint outage, **if the API still accepts that token**.

However, **reuse does not mean using a token indefinitely**. Once a token expires, is revoked, has the wrong audience/scope, or is rejected by the Resource Server, keeping it in memory or a database does not make it valid again.

## 4. `OAuth2AuthorizedClient`: The Object Holding the Access Token

Spring Security represents a client's authorization via:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClient
```

It holds key information:

```text
OAuth2AuthorizedClient
    |
    +-- ClientRegistration
    |       registrationId
    |       authorizationGrantType
    |       tokenUri
    |       clientId
    |
    +-- principalName
    |
    +-- OAuth2AccessToken
    |       tokenValue
    |       issuedAt
    |       expiresAt
    |       scopes
    |
    +-- OAuth2RefreshToken (if issued)
```

With Client Credentials, `getRefreshToken()` is normally `null`.

Example of reading metadata **without exposing credentials**:

```java
import java.time.Instant;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

void inspect(OAuth2AuthorizedClient authorizedClient) {
    String registrationId = authorizedClient
        .getClientRegistration()
        .getRegistrationId();

    String principalName = authorizedClient.getPrincipalName();

    OAuth2AccessToken token = authorizedClient.getAccessToken();

    Instant issuedAt = token.getIssuedAt();
    Instant expiresAt = token.getExpiresAt();

    // Use metadata solely for observability.
    // Never print token.getTokenValue() to logs.
}
```

`issuedAt` and `expiresAt` are built by Spring Security from the token response and related metadata. They can be used to determine when a token needs re-issuance.

### 4.1. `OAuth2AuthorizedClient` vs. `ClientRegistration`

| `ClientRegistration` | `OAuth2AuthorizedClient` |
|---|---|
| Client and provider configuration. | Authorization/token issued for a client and principal. |
| Holds client ID, token URI, grant type, requested scopes. | Holds access token and expiration, plus optional refresh token. |
| Usually declared via YAML/code. | Produced after successful authorization. |
| Looked up by `registrationId`. | Usually stored by `registrationId` + `principalName`. |
| Not an access token store. | The object representing data to cache/persist. |

If you only have a `ClientRegistrationRepository`, the application knows **how to request tokens** but has nowhere to store issued tokens. Hence you also need an authorized client service/repository and an appropriate manager.

## 5. Components Coordinating Token Reuse

Spring Security provides these classes:

| Component | Role |
|---|---|
| `ClientRegistrationRepository` | Reads client/provider configuration. |
| `OAuth2AuthorizedClientService` | Stores and retrieves authorized clients across calls. |
| `OAuth2AuthorizedClientManager` | Coordinates finding current tokens and authorizing/re-authorizing. |
| `OAuth2AuthorizedClientProvider` | Decides whether a token needs/can be obtained via a grant. |
| `ClientCredentialsOAuth2AuthorizedClientProvider` | Strategy for the Client Credentials Grant. |
| `OAuth2AccessTokenResponseClient<OAuth2ClientCredentialsGrantRequest>` | Sends token requests to the AS and parses responses. |

A diagram showing each role accurately:

```mermaid
flowchart TD
    A["Application needs to call API"] --> B["OAuth2AuthorizedClientManager.authorize()"]
    B --> C["OAuth2AuthorizedClientService.loadAuthorizedClient()"]
    C --> D{"Saved token exists?"}
    D -->|No| E["ClientCredentialsOAuth2AuthorizedClientProvider"]
    D -->|Yes| E
    E --> F{"Does token need re-issuance?"}
    F -->|"No: still valid"| G["Provider returns null"]
    G --> H["Manager returns existing authorized client"]
    F -->|"Yes: missing or near expiry"| I["POST /token using client_credentials"]
    I --> J["Receive new access token"]
    J --> K["Manager saves new authorized client"]
    K --> L["Return new authorized client"]
    H --> M["Application calls API"]
    L --> M
```

This diagram illustrates conceptual behavior, not the complete internal source code of a specific Spring Security version. The key point is that **the manager combines storage and provider**, so applications do not need to manually check token expiry on every request when using this API properly.

## 6. `ClientCredentialsOAuth2AuthorizedClientProvider` Decides When to Fetch a New Token

Implementation for Client Credentials:

```java
org.springframework.security.oauth2.client.ClientCredentialsOAuth2AuthorizedClientProvider
```

It implements the contract:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider
```

with the method:

```java
OAuth2AuthorizedClient authorize(
    OAuth2AuthorizationContext context
);
```

### 6.1. Main Branches

Assuming the context contains a `ClientRegistration` with grant type `client_credentials`:

1. **No authorized client yet:** calls the Token Endpoint to request a new access token.
2. **Authorized client exists and access token is still valid:** the provider does not need to re-authorize; typically returns `null`.
3. **Access token is expired or near expiry:** executes a new Client Credentials Grant to get another token.
4. **Registration's grant type is not `client_credentials`:** provider does not apply, returns `null`.
5. **Token request fails:** throws an exception or propagates error per Spring Security; never fabricates a fake token.

Notably, when the provider returns `null` because the current token is still valid, **the manager returns the previously found authorized client**. Do not interpret `null` from the provider as a signal to discard the existing token.

### 6.2. Illustrative Pseudocode

The following merely **models the idea**, not Spring Security's internal code:

```java
OAuth2AuthorizedClient existing =
    authorizedClientService.loadAuthorizedClient(
        registrationId, principalName
    );

OAuth2AuthorizedClient replacement =
    clientCredentialsProvider.authorize(
        contextContaining(registration, principal, existing)
    );

if (replacement != null) {
    authorizedClientService.saveAuthorizedClient(
        replacement, principal
    );
    return replacement;
}

return existing;
```

Real applications should call `OAuth2AuthorizedClientManager.authorize(...)` rather than mimicking the manager with this pseudocode. The manager enforces its own rules around context, success/failure handlers, and persistence.

### 6.3. The Provider Does Not Proactively Run on a Schedule

Normally, tokens are not automatically re-fetched at the exact instant of `expiresAt` while the application is idle. The provider triggers when **the manager is asked to authorize**, such as right before the backend calls an API.

In other words:

```text
Token expires at 10:30.
No request at 10:30 -> normally no /token call yet.

API call request at 10:41
    -> manager sees old token has expired
    -> fetches a new token right then
    -> uses new token for the API.
```

That is an **on-demand token acquisition** mechanism, not a background scheduled refresh by default.

## 7. `expiresAt` and `clockSkew`: Do Not Wait Until the Last Second

Sending a request before a token expires does not guarantee the API receives/validates it while still valid. For example, a token with 5 seconds left may arrive after expiration due to network latency, retries, or queueing.

Spring Security provides **clock skew** to treat a token as “needing re-issuance” slightly earlier.

Example:

```text
Token AT1:
    issuedAt = 10:00:00
    expiresAt = 10:30:00

clockSkew = 60 seconds

Re-issuance threshold:
    10:29:00
```

Timeline:

| Time | Time Remaining Until `expiresAt`? | Illustrative Handling with 60s Skew |
|---|---:|---|
| 10:10:00 | 20 minutes | Reuse AT1. |
| 10:25:00 | 5 minutes | Reuse AT1. |
| 10:28:59 | 61 seconds | Typically still reusable. |
| 10:29:10 | 50 seconds | Proactively request a new token. |
| 10:30:01 | Expired | Must not continue using AT1 per expiry. |

The conceptual calculation:

```text
token needs re-issuance if:
    now >= expiresAt - clockSkew
```

Exact boundary checks are implemented by the provider, so do not treat this illustrative table as a millisecond-level specification.

### 7.1. What Does Clock Skew Solve?

- Reduces the risk of a token expiring between sending and API processing.
- Compensates for minor clock drift between client and AS.
- Lets the application proactively request a new token when expiration approaches.

### 7.2. What Does Clock Skew Not Do?

- Does not extend an old access token's lifetime.
- Does not prove a token has not been revoked.
- Does not fix a JWT with the wrong audience/scope.
- Does not guarantee the token endpoint is always available.
- Does not replace system clock synchronization.

Too large a skew can cause the client to request tokens incessantly, especially when the AS issues very short-lived tokens. Too small a skew risks the API receiving a token right at expiration. Choose based on token lifetime, p95/p99 network latency, and infrastructure clock accuracy.

## 8. Spring Boot Configuration for Client Credentials Grant

Example Spring Boot 3.x Servlet application with Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

With Spring Boot 4.x, recommended starter names may be `spring-boot-starter-webmvc` and `spring-boot-starter-security-oauth2-client`; align BOM/plugins to a single release line.

### 8.1. `application.yml`

Suppose the service calls `https://inventory.example.net/v1/items`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-service:
            provider: corporate-as
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          corporate-as:
            token-uri: https://auth.example.net/oauth2/token
```

Explanation:

- `registrationId = inventory-service`: configuration lookup key in Spring Security.
- `client-id` and `client-secret`: AS-issued credentials, kept secret on the backend.
- `client-authentication-method: client_secret_basic`: client authenticates with the AS using the registered method.
- `authorization-grant-type: client_credentials`: no browser or redirect URI required.
- `scope`: requested scopes; actual granted token depends on AS policy.
- `token-uri`: where the client sends grant requests.

**You do not need `redirect-uri` or `oauth2Login()` to execute the Client Credentials Grant** in a scheduled/backend service-only use case.

Provider metadata/discovery can be used if appropriate, but the example configures `token-uri` explicitly to focus on token reuse mechanics.

### 8.2. Never Store Client Secrets in the Repository

Use a secret manager, environment variables, or deployment-platform secret injection. Never hardcode `INVENTORY_CLIENT_SECRET` in Java, commit it to YAML, or log Basic Authentication headers.

If the AS requires `private_key_jwt` or mTLS instead of a client secret, client registration and token HTTP client configuration must reflect that method. Token caching does not replace client authentication.

## 9. Configuring `OAuth2AuthorizedClientService` to Store Tokens

A backend without an HTTP session can use:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientService
```

Common implementations:

- `InMemoryOAuth2AuthorizedClientService`: stores in the application instance's RAM.
- `JdbcOAuth2AuthorizedClientService`: persists in a database via JDBC.
- Custom service: persists in custom storage such as a database, token vault, or controlled distributed store.

For illustration, using InMemory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class AuthorizedClientStoreConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            ClientRegistrationRepository registrations) {

        return new InMemoryOAuth2AuthorizedClientService(registrations);
    }
}
```

Note: this is an illustrative application bean, **not a requirement to define manually if Spring Boot already auto-configures one**. When defining a custom bean, ensure the manager uses that exact bean.

### 9.1. Under What Key Are Tokens Stored?

Typically:

```text
(clientRegistrationId, principalName)
```

Examples:

```text
("inventory-service", "inventory-backend")
    -> OAuth2AuthorizedClient containing AT1

("billing-service", "billing-backend")
    -> OAuth2AuthorizedClient containing AT2
```

**`principalName` matters even in the Client Credentials Grant.** It serves as the logical key for managing the authorized client; it does not mean the token was issued to a human user.

If you pass a different principal on every manager call, Spring Security will fail to find the stored authorized client and will request a new token continuously.

## 10. Using `AuthorizedClientServiceOAuth2AuthorizedClientManager`

For service-to-service calls or scheduled jobs **without a Servlet HTTP request**, use:

```java
org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager
```

It is designed to work with:

- `ClientRegistrationRepository`.
- `OAuth2AuthorizedClientService`.
- `OAuth2AuthorizedClientProvider`.

Complete configuration example:

```java
import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class ClientCredentialsManagerConfig {

    @Bean("inventoryAuthorizedClientManager")
    OAuth2AuthorizedClientManager inventoryAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials(clientCredentials -> clientCredentials
                    .clockSkew(Duration.ofSeconds(60))
                )
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                service
            );

        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
```

In this setup:

1. The manager is created **once** as a Spring bean.
2. The manager retrieves the registration by `registrationId`.
3. The manager checks `OAuth2AuthorizedClientService` before deciding a new token is needed.
4. The `clientCredentials` provider requests a token only if none exists or the current one needs re-issuance.
5. Upon success, the manager saves the new authorized client via the service and success handling.
6. Subsequent calls look up the same service and principal name to reuse the token.

`Duration.ofSeconds(60)` is only an example **clock skew**, not a fixed requirement for every token.

### 10.1. Why Not Use `DefaultOAuth2AuthorizedClientManager` Everywhere?

`DefaultOAuth2AuthorizedClientManager` belongs to the **Servlet web request context**, typically paired with `OAuth2AuthorizedClientRepository`, and may require `HttpServletRequest`/`HttpServletResponse`.

In scheduled jobs or workers without HTTP requests, `AuthorizedClientServiceOAuth2AuthorizedClientManager` fits better because it interacts directly with the authorized client service.

Comparison:

| Need | Suitable Manager |
|---|---|
| MVC web request with principal/session and authorized client repository | `DefaultOAuth2AuthorizedClientManager` |
| Scheduled job, worker, backend service without Servlet request | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
| WebFlux reactive application | Corresponding reactive authorized client managers |

Each manager needs providers and storage configured for its exact use case.

## 11. Obtaining the Access Token Before Calling an API

When the application wants to call an API, it builds an `OAuth2AuthorizeRequest` with the registration ID and a **stable principal name**:

```java
OAuth2AuthorizeRequest authorizeRequest =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-service")
        .principal("inventory-backend")
        .build();
```

Then:

```java
OAuth2AuthorizedClient authorizedClient =
    manager.authorize(authorizeRequest);
```

- First call: manager calls Token Endpoint and saves token.
- Next call while token is valid: manager finds saved token and returns it.
- When token needs re-issuance: manager calls Token Endpoint, saves the new result, and returns it.

### 11.1. Controlled Java Service for Fetching Tokens

```java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class InventoryAccessTokenService {

    private static final String REGISTRATION_ID = "inventory-service";
    private static final String PRINCIPAL_NAME = "inventory-backend";

    private final OAuth2AuthorizedClientManager manager;

    public InventoryAccessTokenService(
            @Qualifier("inventoryAuthorizedClientManager")
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public String currentAccessToken() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId(REGISTRATION_ID)
                .principal(PRINCIPAL_NAME)
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                "Unable to authorize inventory-service"
            );
        }

        return client.getAccessToken().getTokenValue();
    }
}
```

`getTokenValue()` is used **on the backend** to call a trusted API. Never write it to logs or return it needlessly to browsers. In real applications, consider restricting token retrieval solely to a dedicated gateway client rather than letting arbitrary controllers request tokens.

### 11.2. Why Must `principal("inventory-backend")` Be Stable?

Because the authorized client service typically indexes records by:

```text
("inventory-service", "inventory-backend")
```

If each call generates a random principal:

```java
// Wrong when the goal is sharing one service authorization.
.principal(java.util.UUID.randomUUID().toString())
```

then each call looks up **a different key**, missing the cached token and requesting a new token unnecessarily.

Conversely, sharing the same principal name across tenants/clients **not permitted to share privileges** is also dangerous. A stable key must align with **security boundaries for that authorization**, not merely boost cache hits.

## 12. Using the Token to Call REST APIs on the Backend

With Spring Framework's `RestClient` (e.g., Boot 3.2+), you can build a gateway:

```java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryGateway {

    private final RestClient api;
    private final InventoryAccessTokenService tokenService;

    public InventoryGateway(
            RestClient.Builder restClientBuilder,
            InventoryAccessTokenService tokenService) {

        this.api = restClientBuilder
            .baseUrl("https://inventory.example.net")
            .build();

        this.tokenService = tokenService;
    }

    public StockResponse getStock(String sku) {
        String accessToken = tokenService.currentAccessToken();

        return api.get()
            .uri("/v1/stocks/{sku}", sku)
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(StockResponse.class);
    }

    public record StockResponse(String sku, int available) {
    }
}
```

`InventoryAccessTokenService`, `InventoryGateway`, and the beans above belong to the same illustrative application.

Meaning:

1. `InventoryGateway` knows nothing about the client secret.
2. When it needs to call the API, the gateway asks the manager for a token.
3. The manager decides whether to reuse an existing token or fetch a new one.
4. The API request sends `Authorization: Bearer ...`.
5. The JSON API response maps to the `StockResponse` DTO.

**Never hardcode an access token** in `RestClient`. Tokens must follow lifecycle management, not static configuration variables.

### 12.1. Should You Call the Manager Before Every API Request?

Yes, you can. It is the simplest pattern because the manager/service checks the authorized client state and usually **does not call the Token Endpoint** if the token remains valid.

However, calling the manager may involve looking up a database or external store. Under very high throughput, measure latency and consider appropriate storage/caching layers. Never replace the manager with a `static String token` just to save one lookup while sacrificing expiration and policy checks.

### 12.2. Can You Use an Interceptor to Attach the Bearer Token Automatically?

Yes. Modern Spring Security versions provide OAuth2 Client integrations for `RestClient`/`WebClient` with appropriate interceptors/filters. This automatically obtains the authorized client and adds the Bearer token.

Whether using an interceptor or the illustrative gateway code, **reuse mechanics still depend on the manager, provider, and authorized client store**. An interceptor is not an Authorization Server and cannot work around token expiration if the manager/store is misconfigured.

When working across versions, check the matching Spring Security documentation for interceptor/filter names and how registration ID / principal are resolved.

## 13. First Call, Second Call, and After Token Expiration

Suppose `expires_in = 1800` seconds and `clockSkew = 60` seconds.

### 13.1. First Call: No Authorized Client Yet

```text
Time: 09:00:00

InventoryGateway.getStock("SKU-01")
    |
    v
manager.authorize(registration=inventory-service,
                  principal=inventory-backend)
    |
    v
OAuth2AuthorizedClientService.load(...)
    -> null
    |
    v
ClientCredentialsOAuth2AuthorizedClientProvider
    -> POST /oauth2/token
    -> receives AT1 (expiresAt=09:30:00)
    |
    v
Manager saves OAuth2AuthorizedClient containing AT1
    |
    v
Gateway calls API with AT1
```

### 13.2. Second Call: Token Still Valid

```text
Time: 09:05:00

Gateway requests token
    |
    v
Service finds AT1
    |
    v
Provider checks expiration:
    09:05:00 < 09:29:00
    -> no re-issuance needed
    -> returns null
    |
    v
Manager returns existing authorized client
    |
    v
Gateway calls API with AT1
```

**No new `POST /token`** occurs in the successful reuse branch.

### 13.3. Third Call: Token About to Expire

```text
Time: 09:29:20

Gateway requests token
    |
    v
Service finds AT1
    |
    v
Provider sees token inside clockSkew window
    -> requests new token
    |
    v
POST /oauth2/token grant_type=client_credentials
    -> AS returns AT2 (expiresAt=09:59:20)
    |
    v
Manager updates store with AT2
    |
    v
Gateway calls API with AT2
```

From then on, API requests continue using AT2 until it approaches expiration.

### 13.4. Combined Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    participant API as InventoryGateway
    participant M as AuthorizedClientManager
    participant S as OAuth2AuthorizedClientService
    participant P as ClientCredentialsProvider
    participant AS as Authorization Server
    participant RS as Resource Server

    API->>M: authorize(registrationId, stablePrincipal)
    M->>S: loadAuthorizedClient
    S-->>M: null
    M->>P: authorize(context)
    P->>AS: POST /token client_credentials
    AS-->>P: AT1, expires_in
    P-->>M: OAuth2AuthorizedClient(AT1)
    M->>S: saveAuthorizedClient(AT1)
    M-->>API: AT1
    API->>RS: GET resource with AT1
    RS-->>API: 200

    Note over API,M: Next API call, AT1 still valid
    API->>M: authorize(registrationId, samePrincipal)
    M->>S: loadAuthorizedClient
    S-->>M: AT1
    M->>P: authorize(context with AT1)
    P-->>M: null - no new token needed yet
    M-->>API: AT1
    API->>RS: GET resource with AT1
    RS-->>API: 200

    Note over API,M: Later call, AT1 near expiry
    API->>M: authorize(registrationId, samePrincipal)
    M->>S: loadAuthorizedClient
    S-->>M: AT1
    M->>P: authorize(context with AT1)
    P->>AS: POST /token client_credentials
    AS-->>P: AT2, expires_in
    P-->>M: OAuth2AuthorizedClient(AT2)
    M->>S: saveAuthorizedClient(AT2)
    M-->>API: AT2
```

## 14. Reusing Tokens Does Not Mean Refresh Tokens

The phrase “refresh access token” is often used loosely, yet you must distinguish **grant protocols**:

| Action | Token Endpoint Request | Condition |
|---|---|---|
| **Reuse valid token** | No request sent | Authorized client holds an access token that can continue being used. |
| **Client Credentials fetches new token** | `grant_type=client_credentials` | No token yet or token needs re-issuance. |
| **Refresh Token Grant** | `grant_type=refresh_token` | A refresh token was issued and is accepted by the AS. |
| **New Authorization Code Grant** | Browser authorize then `grant_type=authorization_code` | New user authorization needed or no token exists. |

With Client Credentials, a new grant uses **client authentication** to request a token rather than relying on an old refresh token.

Thus, the builder usually needs only:

```java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
```

**You do not need `.refreshToken()` for Client Credentials to fetch a new token upon expiration.** Adding a refresh provider to a multi-grant manager may make sense in another application, but it does not turn Client Credentials into a Refresh Token Grant.

## 15. Why Not Cache Manually in a `static` Variable?

Approach to avoid:

```java
public final class BadTokenHolder {

    public static String accessToken;

    // Stores no expiresAt, principal, client registration, audience...
}
```

Risks:

1. No tracking of when the token expires.
2. No clock skew handling.
3. Cannot distinguish tokens across different registrations.
4. Cannot isolate tenants or permissions.
5. Risks sending API A's token to API B.
6. Concurrency bugs when multiple threads update the variable.
7. No safe lifecycle or cleanup.
8. No integration with token errors or success/failure handlers.
9. No persistence across restarts if required.
10. Hard to migrate from InMemory to a shared store without rewriting every API call site.

A static variable may look like caching works in a tiny demo, yet it quickly breaks security boundaries as the system grows.

**Alternative:** use `OAuth2AuthorizedClientManager` with `OAuth2AuthorizedClientService`/repository, and choose the right keys.

## 16. When Cache Hits Yet the API Still Returns 401 or 403

The manager may see a token **before `expiresAt`**, yet the Resource Server still rejects it.

Possible reasons:

- The token was revoked at the Authorization Server.
- The API requires a different audience.
- The API requires a scope that was never granted.
- JWT signature/issuer fails Resource Server policy.
- Excessive clock skew between the API and AS.
- The client used a token from the wrong registration.
- The issued token is valid, yet lacks business authorization.

Distinction:

| Response | Common Meaning |
|---|---|
| HTTP 401 `invalid_token` | Token missing/invalid/expired according to the Resource Server. |
| HTTP 403 `insufficient_scope` | Token may be valid, yet lacks the required scope. |
| HTTP 403 due to API policy | Token may be valid, yet caller lacks permission on that specific resource. |
| HTTP 429 from Token Endpoint | AS token-issuance rate limit hit. |
| HTTP 400 `invalid_client` | Client authentication with the AS failed. |
| HTTP 400 `invalid_scope` | Requested scope was not accepted. |

**Never retry infinitely** on API 401 responses by requesting new tokens in a tight loop. If audience/scope/config is wrong, every new token will also fail and can overload the AS.

Depending on the API contract, the application can:

1. Determine whether the 401 was genuinely caused by an expired/revoked token.
2. Evict the corresponding authorized client if policy allows.
3. Perform a single bounded re-authorization and retry the API if the HTTP operation is safe/idempotent or uses an idempotency mechanism.
4. If it still fails, surface the true error rather than masking it with another token.

For mutating POSTs creating transactions, API retries must evaluate **idempotency**: the API may have processed the request before the response was lost. Never apply one blanket retry policy to all operations.

## 17. Right Cache Keys: Registration ID and Principal Name

`OAuth2AuthorizedClientService` typically stores records by:

```text
clientRegistrationId + principalName
```

Examples:

| `registrationId` | `principalName` | Authorized Client |
|---|---|---|
| `inventory-service` | `inventory-backend` | Token for inventory API. |
| `billing-service` | `billing-backend` | Token for billing API. |
| `inventory-service` | `inventory-tenant-a` | Separate token for tenant A, if authorization is designed that way. |
| `inventory-service` | `inventory-tenant-b` | Separate token for tenant B, if authorization is designed that way. |

### 17.1. Practices That Break Reuse

Do not do this:

```java
.principal("request-" + UUID.randomUUID())
```

Do not instantiate a new manager/store per API request:

```java
// Anti-pattern illustration:
OAuth2AuthorizedClientService service =
    new InMemoryOAuth2AuthorizedClientService(registrations);

// If recreated on every request, any saved token immediately disappears
// from the perspective of the next request.
```

Use singleton beans or a shared store per architecture.

### 17.2. Be Careful with `principalName` in Client Credentials

In Client Credentials, the principal name in the manager API can be a stable service name. It **is not a user login** and does not prove the token carries user permissions.

Do not substitute real user names for a service principal if the goal is sharing one client authorization, as the app will create many entries and call the AS unnecessarily. Equally, do not merge authorizations belonging to separate tenants/permissions under one service name if the AS requires isolation.

### 17.3. Tokens with Different Scopes/Audiences Must Not Be Reused Arbitrarily

Suppose:

```text
Token A:
    scope = inventory.read
    audience = inventory-api

Token B needs:
    scope = billing.write
    audience = billing-api
```

Never reuse Token A to call the billing API simply because it has not expired. The `registrationId`/`principalName` cache key scheme must align with the **client registration, scope, audience, and tenant** the application uses.

If a provider supports varying `resource`/`audience` parameters in token requests, design separate registrations or explicit custom authorized client storage/keys. Never inject different audiences into token requests while sharing one cache entry and assuming the manager tracks every variant.

## 18. InMemory: Reuse Within a Single Application Instance

`InMemoryOAuth2AuthorizedClientService` is typically suitable for:

- Demos and learning exercises.
- Single-instance backends.
- Simple tasks that can request a new token after restarts.
- Test environments not requiring persistent token storage.

Example:

```text
Process A:
    ("inventory-service", "inventory-backend") -> AT1
    AT1 is reused across all requests handled by process A.

Process restart:
    InMemory store is empty.
    The next call sends POST /token to fetch AT2.
```

**Losing the cache does not break functionality** as long as the Token Endpoint is up and client credentials remain valid; however, it increases token requests and can cause a “burst” after multi-instance deploys/restarts.

### 18.1. InMemory Is Not a Cluster-Wide Cache

If a backend has 3 pods:

```text
Pod A: AT1
Pod B: AT2
Pod C: AT3
```

Each pod can request its own token and reuse it in local memory. This is not necessarily an error, though it creates redundant token issuance when multiple pods start together.

If the system requires a shared authorization cache, evaluate a persistent/shared store and concurrency. Never define an InMemory bean and expect it to synchronize across the network automatically.

## 19. JDBC and Persistent Storage

Spring Security provides:

```java
org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService
```

This can be configured when tokens need to survive restarts or be shared across instances.

Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class PersistentTokenStoreConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcOperations jdbc,
            ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbc,
            registrations
        );
    }
}
```

This configuration **replaces** the InMemory bean of the same type from the previous section; do not define both without a qualifier/selection policy.

The application needs a database schema matching **the exact Spring Security version** in use. Columns typically include:

```text
oauth2_authorized_client
    client_registration_id
    principal_name
    access_token_value
    access_token_issued_at
    access_token_expires_at
    access_token_scopes
    refresh_token_value
    ...
```

With Client Credentials, the refresh token is usually absent, though the schema supports multiple grant types.

### 19.1. When Should You Choose JDBC?

- Multiple nodes need to see the same authorized client.
- You want to reduce token requests after restarts/deploys.
- Token audit/retention rules apply.
- You need storage managed separately from process memory.
- There is a defined policy for sharing tokens across workloads.

However, **a shared database does not automatically prevent two requests from asking for a new token simultaneously**. Concurrency is covered next.

### 19.2. Token Storage Must Be Protected

An access token is a credential. For JDBC or custom stores, consider:

- TLS on database connections.
- Encryption at rest and, if required by your threat model, application/column-level encryption.
- Least-privilege read/write permissions for the database account.
- Never logging SQL bind parameters containing access tokens.
- Protecting backups, exports, replicas, and snapshots.
- Policies to purge expired or revoked tokens.
- Key/secret rotation governance.
- Isolation between tenants and services.

Never treat a table containing plaintext tokens as safe merely because the database sits in a private subnet.

## 20. High Concurrency: Avoiding a “Thundering Herd” at the Token Endpoint

A major risk arises when hundreds of requests arrive simultaneously right as a token expires:

```text
12:00:00 - AT1 expires

Thread 1 -> Load AT1 -> expired -> POST /token
Thread 2 -> Load AT1 -> expired -> POST /token
Thread 3 -> Load AT1 -> expired -> POST /token
...
Thread 50 -> Load AT1 -> expired -> POST /token
```

Even though the service stores one authorized client per key, **do not assume the entire load-check-POST-save sequence is globally synchronized**. With many threads or instances, multiple concurrent token requests can occur.

### 20.1. Impact

- Traffic spike hitting the Authorization Server.
- Token endpoint rate limiting returning HTTP 429.
- Multiple tokens issued almost simultaneously for one client.
- Nodes overwriting each other's saved tokens depending on response order.
- Increased connections, CPU, and latency.
- If the AS enforces limits on concurrent active tokens, repeated issuance can interact undesirably with that policy.

Client Credentials tokens usually avoid refresh-token rotation conflicts seen in Refresh Token Grants, yet **they still face token request storms**.

### 20.2. Load-Reduction Strategies

Consider:

1. Reusing authorized clients from a stable store.
2. Setting a reasonable **clock skew** rather than waiting until the exact expiration second.
3. Using proper connection pooling and timeouts.
4. Limiting token acquisition concurrency per **`registrationId` + `principalName`**.
5. On a single node, using a **single-flight** mechanism for requests sharing the same key.
6. Across multiple nodes, using distributed locking or shared coordination when genuinely required.
7. After acquiring a lock, **re-read the store** before requesting a new token, since another node may have already updated it.
8. Bounding retries/backoff on transient errors and HTTP 429 per AS contract.
9. Avoiding creating new manager/service instances per request.
10. Monitoring token issuance count versus API call count.

### 20.3. Why “Double-Checking After Acquiring the Lock” Matters

Example:

```text
Node A: Sees AT1 expired
Node B: Sees AT1 expired

Node A acquires distributed lock
    -> reloads AT1
    -> POST /token, receives AT2
    -> saves AT2
    -> releases lock

Node B acquires lock
    -> must reload store
    -> sees AT2 is valid
    -> reuses AT2, skips POST /token
```

If Node B fails to re-read the store after acquiring the lock, it would request an unnecessary AT3.

### 20.4. Do Not Unconditionally Lock Every API Call

A distributed lock around every API call becomes a bottleneck and inflates latency. Coordination is normally only needed when a token is **missing or needs re-issuance**. While the token is valid, most requests should quickly use the stored token.

Exact lock integration depends on architecture and must preserve the manager's success/failure handling. Any wrapper must still delegate properly to the manager/provider and store.

## 21. Clock Skew Rules and Very Short Token Lifetimes

Suppose an AS issues tokens with `expires_in = 30` seconds while `clockSkew = 60` seconds is configured.

The application may treat the token as near expiry **immediately upon receipt** or very soon after, causing nearly every API call to request a new token.

Illustrative table:

| Token Lifetime | Clock Skew | Assessment |
|---:|---:|---|
| 60 minutes | 60 seconds | Buffer is negligible relative to lifetime. |
| 10 minutes | 60 seconds | Often suitable, depending on latency. |
| 2 minutes | 60 seconds | Needs consideration since 50% of lifetime is treated as near expiry. |
| 30 seconds | 60 seconds | Likely triggers continuous token re-issuance. |
| 10 minutes | 0 seconds | Risks tokens expiring while the API is processing. |

**No single skew value fits every system.** Evaluate based on AS-issued lifetime, token issuance latency, API latency, clock sync, and request frequency.

### 21.1. What If the Token Endpoint Omits `expires_in`?

This depends on the Authorization Server contract. Spring Security typically relies on the token response and metadata to compute access token expiration.

If a provider does not publish a reliable lifetime, never assume tokens live forever. Clarify the contract with the AS or apply standard/provider-specific token response conversion, and configure a safe caching policy.

### 21.2. If the Access Token Is a JWT, Should You Parse `exp` Yourself to Decide Reuse?

Usually unnecessary. `OAuth2AuthorizedClient` already holds the expiration timestamp used by Spring Security in the token lifecycle. An access token **is not required to be a JWT**; many providers issue opaque tokens.

Decoding a JWT yourself without a contract or validation mechanism couples the client to an unstable token format meant for the Resource Server.

## 22. Error Mechanics: Do Not Chase a New Token at All Costs

Errors can occur at several layers:

| Layer | Example Error | Resolution |
|---|---|---|
| `ClientRegistration` | Wrong `registrationId`, missing token URI | Fix client/provider configuration. |
| Client authentication | HTTP 400 `invalid_client` | Check client ID/secret, method, mTLS, or JWT assertion. |
| Scope | HTTP 400 `invalid_scope` | Request scopes granted to the client by the AS. |
| Token Endpoint | Connect/read timeout, TLS/PKIX | Check network, proxy, truststore, and HTTP transport. |
| Token Endpoint | HTTP 429 | Respect rate limits, bounded backoff, avoid thundering herd. |
| Token Endpoint | HTTP 500/503 | Reduce retries, monitor AS outage; no infinite loops. |
| Resource Server | HTTP 401 | Invalid/expired/revoked token, wrong issuer/audience. |
| Resource Server | HTTP 403 | Insufficient scope/business permissions. |
| Storage | JDBC/Redis unreachable | Check authorized client store availability. |

### 22.1. Valid Cached Token Remaining During an AS Outage

If AT1 **is still unexpired and accepted by the API**, the application can typically keep calling the API with AT1 without needing the Token Endpoint. This is a key benefit of reuse.

Once AT1 expires, do not keep using it indefinitely just to ignore an AS outage. The Resource Server will reject it; sending expired tokens degrades correctness and generates downstream errors.

### 22.2. Do Not Retry Continuously on `invalid_client`

`invalid_client` is usually a configuration or credential error, not a transient load failure. If a client secret rotated while the app was not updated, every retry simply sends the wrong credential again.

Update the secret, ensure the token client uses the right authentication method, and coordinate with the AS per rotation policy.

### 22.3. Retries Must Be Bounded

With Client Credentials, retrying a token request is more feasible than in the Authorization Code Grant because there is no single-use authorization code. Nevertheless:

- A timeout does not prove the AS failed to issue a token.
- Reckless retries can mint multiple valid tokens unnecessarily.
- Configure bounded retry counts and backoff.
- Distinguish `invalid_client`/`invalid_scope` from timeouts/503s.
- When receiving 429, respect policy and trusted rate-limit headers if provided.
- Never retry non-idempotent API operations solely because a new token was obtained.

## 23. Automatic Token Usage with `WebClient`/`RestClient`

Modern applications usually prefer not to write manually:

```java
String accessToken = service.currentAccessToken();
headers.setBearerAuth(accessToken);
```

at every API call site. Spring Security provides OAuth2 Client integrations with HTTP clients. Exact class names and APIs vary by version and stack:

- Servlet apps using `RestClient` can use appropriate OAuth2 client request interceptors.
- WebFlux apps using `WebClient` can use OAuth2 authorized client exchange filters.
- Backend jobs can use a dedicated service manager and a stable principal name.

The core flow stays the same:

```text
API HTTP client
    |
    v
OAuth2AuthorizedClientManager
    |
    v
ClientCredentials provider + AuthorizedClientService
    |
    +-- Valid token exists? -> reuse
    |
    +-- Token needed? -> POST /token
    |
    v
HTTP request sends Bearer access token
```

When using automatic integration, configure **the exact registration ID and principal**, avoiding accidentally picking up a logged-in user's token when a service token is intended, or vice versa.

### 23.1. Spring WebFlux / Reactive

In a WebFlux application, use the corresponding reactive APIs, such as:

```text
ReactiveOAuth2AuthorizedClientProvider
ReactiveOAuth2AuthorizedClientProviderBuilder
ReactiveOAuth2AuthorizedClientService
AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
```

The semantics remain the same:

- Reuse the authorized client if the token is still valid.
- Request a new token via Client Credentials if missing or needing re-issuance.
- Use `Mono`/reactive pipelines instead of blocking calls.
- Never block a Reactor event loop with `RestTemplate` or `.block()` during request processing.

Do not mix a Servlet `OAuth2AuthorizedClientManager` with a reactive manager without an explicit design.

## 24. Token Lifecycle Across Deployment Topologies

### 24.1. Single Instance, Token in RAM

```text
Service A
    |
    +-- InMemory authorized client service
            |
            +-- AT1 -> API calls reuse AT1
```

When the application restarts, the store is cleared and the next API call fetches a new token.

### 24.2. Multiple Instances, Each with InMemory

```text
Pod A -> token AT1
Pod B -> token AT2
Pod C -> token AT3
```

Each pod caches its own token. This is valid in some systems if the AS allows it and sharing is unnecessary, though token request volume should be measured.

### 24.3. Multiple Instances, Shared Authorized Client Service

```text
Pod A \
Pod B  ---> JDBC / distributed store ---> AT1
Pod C /
```

Nodes share visibility of the authorized client. However, cache lookups and token replacement can still race; add concurrency control when required by AS/rate limits.

### 24.4. When Is Persistence Unnecessary?

If token issuance is fast, lifetimes are long, pod counts are low, and the AS is not tightly rate-limited, InMemory suffices. Do not add JDBC merely out of a belief that “caching requires a database.”

If you need authorizations to survive restarts, be shared across nodes, be audited, or support multiple systems sharing credentials, a persistent store may fit better—provided security and lifecycle are properly governed.

## 25. Distinguishing Token Reuse from API Response Caching

Two distinct caches:

| Cache Type | What Is Stored? | What Governs Expiration? |
|---|---|---|
| OAuth2 Authorized Client cache | Access token, metadata, and optional refresh token. | OAuth2 token lifetime and re-issuance policy. |
| Business/API response cache | Data such as product lists, prices, inventory. | API TTL / ETag / business freshness. |

An unexpired access token does not mean an inventory response from 10 minutes ago is still accurate. Conversely, a cached API response does not permit using an old token to call a different API.

Avoid mixing token caches and business caches under the same key/value without explicit lifecycle and security boundaries.

## 26. Observing Token Reuse Effectiveness

To verify whether configuration works efficiently, measure:

- Number of API requests needing tokens.
- Number of manager `authorize` invocations.
- Number of token requests actually sent to the AS.
- Ratio of token reuse to new token issuance.
- Token endpoint response latency.
- Count of token endpoint 429/500/503 responses.
- Count of client authentication errors.
- Count of API 401/403 responses.
- Cache misses after restarts or deployments.
- Duplicate token requests for the same registration within the same time window.

Example:

```text
Over 10 minutes:
    API requests: 15,000
    Token Endpoint POSTs: 3
    Service instances: 3
    Token lifetime: 30 minutes
```

This is sensible behavior if each instance requested one token and reused it. If you see **15,000 token requests for 15,000 API calls**, inspect keys, service lifecycle, and manager wiring.

### 26.1. What Can Be Logged

Safe to log:

```text
registrationId=inventory-service
grantType=client_credentials
action=token_acquired / token_reused
tokenExpiresAt=...
httpStatus=200
elapsedMs=...
```

Never log:

```text
access_token
client_secret
client_assertion
Authorization header
mTLS private key
```

Never place tokens in span tags, analytics, or SQL logs. For correlation, use a random request ID and non-sensitive metadata.

## 27. Common Errors When Reusing Tokens

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Every API call sends POST `/token` | Principal name changes, store recreated per request, or skew too large | Keep principal stable, use singleton manager/store, check skew. |
| Token still used after expiration | Manual `String` caching instead of manager/provider | Use `OAuth2AuthorizedClientManager` and `expiresAt`/`clockSkew`. |
| Token lost after restart | InMemory store | Accept cache miss or use a persistent store. |
| Token not shared across pods | Per-node InMemory store | Use a shared service if genuinely needed. |
| Multiple POST `/token` at the same time | Concurrent requests see expired token | Single-flight/lock per key, re-read store. |
| API returns 401 despite unexpired token | Token revoked, wrong issuer/audience/scope | Check Resource Server validation. |
| API returns 403 | Missing scope/permissions | Check AS registration and API policy. |
| Token Endpoint 400 `invalid_client` | Wrong secret/mTLS/assertion | Fix client authentication. |
| Token Endpoint 400 `invalid_scope` | Scope not granted to client | Fix requested scopes. |
| Token Endpoint 429 | Requesting tokens too frequently | Improve reuse, limit concurrency, backoff. |
| Token Endpoint timeout | Proxy, TLS, network, or slow AS | Configure HTTP transport, timeouts, and TLS properly. |
| Manager returns `null` | Registration/provider/context cannot authorize as expected | Check provider chain, registration ID, and manager. |
| No HTTP request yet manager asks for Servlet context | Wrong manager used for background service | Use `AuthorizedClientServiceOAuth2AuthorizedClientManager`. |
| Inventory token sent to billing API | Wrong registration/HTTP client chosen | Separate registrations, audience, and resource boundaries. |
| Added `.refreshToken()` yet Client Credentials still POSTs `/token` | Grant does not rely on refresh tokens | This is expected behavior: new access token obtained via client credentials. |
| Refresh token field is null | Client Credentials usually issues no refresh token | Do not treat as an error. |
| Token considered near expiry immediately after issuance | Token lifetime shorter than or equal to clock skew | Adjust skew to match lifetime. |
| Cannot get new token after secret rotation | App still holds old credentials | Reload secrets/transport per policy. |

### 27.1. Isolation Checklist

If the application keeps requesting new tokens:

1. Check that `registrationId` is fixed and accurate.
2. Check that `principalName` is stable across calls.
3. Check that the manager and authorized client service are proper singleton/shared beans.
4. Check that `loadAuthorizedClient()` finds the recently saved authorized client.
5. Check `expiresAt` from the token response and `clockSkew`.
6. Check that the AS actually returns an appropriate `expires_in`/lifetime.
7. Check whether a custom handler/provider always deletes or overwrites the token.
8. With multiple instances, verify whether the store is shared or per-node InMemory.
9. Check concurrent request volume right at token expiration.
10. Separate token endpoint errors from Resource Server errors before changing configuration.

You never need to log a token value to answer these questions.

## 28. Thought Exercises

### Exercise 1 — First Call Without a Token

A backend has `registrationId = inventory-service`, `principalName = inventory-backend`, and the service has not stored an authorized client yet.

**Question:** What does the manager do?

**Answer:** The Client Credentials provider sends a token request to the AS, receives an access token, the manager stores an `OAuth2AuthorizedClient`, and returns it to the application.

### Exercise 2 — Token Still Valid

Five minutes later, the app calls the API again. The token has 25 minutes left, with a 60-second clock skew.

**Question:** Is a POST `/token` needed?

**Answer:** No. The provider does not need to re-issue; the manager can return the saved authorized client.

### Exercise 3 — Token Has 20 Seconds Left

The token has 20 seconds remaining, with a 60-second skew.

**Question:** What can the manager do?

**Answer:** Treat the token as near expiry and request a new token via `client_credentials`.

### Exercise 4 — No Refresh Token

The Client Credentials token response has no `refresh_token`.

**Question:** Is the AS broken?

**Answer:** No. For Client Credentials, refresh tokens are usually not issued; new tokens are obtained through the Client Credentials Grant itself.

### Exercise 5 — Principal Keeps Changing

Code uses `.principal(UUID.randomUUID().toString())`.

**Question:** Why might every request ask for a new token?

**Answer:** The manager looks up authorized clients by registration ID and principal name; a different principal produces a different key, missing the old entry.

### Exercise 6 — Three Pods Using InMemory

Each pod starts up and calls the API.

**Question:** Is there necessarily only one token request across the entire cluster?

**Answer:** No. Each pod has its own RAM store, so each can request its own token and reuse it locally.

### Exercise 7 — Shared DB Yet 10 Concurrent Token Requests Still Happen

Multiple threads see the token expire at the exact same moment.

**Question:** Why can this happen?

**Answer:** Shared storage does not guarantee the entire load-check-POST-save sequence executes atomically. Per-key coordination is needed if load/rate limits demand it.

### Exercise 8 — API Returns 403 After Getting a New Token

**Question:** Should you delete the token and re-request repeatedly?

**Answer:** No. A 403 may stem from missing scopes/business permissions, which a new token will not fix unless registration/policy changes.

### Exercise 9 — Scheduled Job Using Servlet Manager

A background task calls `DefaultOAuth2AuthorizedClientManager` with no HTTP request.

**Question:** Which manager is more appropriate?

**Answer:** `AuthorizedClientServiceOAuth2AuthorizedClientManager` with `OAuth2AuthorizedClientService`.

### Exercise 10 — 30-Second Token Lifetime, 60-Second Skew

**Question:** What can this lead to?

**Answer:** Tokens may be treated as immediately near expiry, defeating reuse and spiking token requests. Adjust skew accordingly.

### Exercise 11 — Using API A's Token for API B

A service holds a valid `inventory.read` token and uses it to call `billing.write`.

**Question:** Can it be reused?

**Answer:** No, if the token lacks the required scope/audience. Reuse is valid only within the granted authorization boundaries.

### Exercise 12 — AS Outage, Token Still Has 10 Minutes Left

**Question:** Should you force a Token Endpoint call just to be sure you get a fresh token?

**Answer:** Usually no. If the token still has enough lifetime and the API accepts it, the manager can reuse the existing token. Do not request new tokens before every API call.

## 29. Quick Summary by Component

| Component | Key Point to Remember |
|---|---|
| `client_credentials` | Grant for services to obtain access tokens using the client's own permissions. |
| `OAuth2AuthorizedClient` | Holds access token, expiration, client registration, and principal name. |
| `OAuth2AuthorizedClientService` | Persists authorized clients across calls. |
| `OAuth2AuthorizedClientManager` | Coordinates lookup, authorization, and saving tokens. |
| `ClientCredentialsOAuth2AuthorizedClientProvider` | Chooses between reuse and requesting a new token based on context and expiry. |
| `OAuth2AuthorizedClientProviderBuilder.clientCredentials()` | Enables the Client Credentials provider inside the manager. |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Manager suited for background/service contexts. |
| `expiresAt` | Token expiration timestamp per metadata. |
| `clockSkew` | Buffer for requesting a new token before expiration. |
| `registrationId + principalName` | Common key used to store/reuse authorized clients. |
| `InMemoryOAuth2AuthorizedClientService` | Cache scoped to a single application instance. |
| `JdbcOAuth2AuthorizedClientService` | Shared persistence via database when configured. |
| New Client Credentials token | Normally obtained via `grant_type=client_credentials`, not a refresh token. |
| Concurrency control | Reduces simultaneous token requests on cache miss/expiration. |
| Resource Server 401/403 | Analyze issuer/audience/scope/policy rather than retrying tokens infinitely. |

**Conclusion:** In the Client Credentials Grant, **reusing valid tokens** is essential to reduce Authorization Server load and lower API call latency. Spring Security supports this via **`OAuth2AuthorizedClientManager` + `ClientCredentialsOAuth2AuthorizedClientProvider` + `OAuth2AuthorizedClientService`**. The manager looks up the authorized client by registration/principal; while the token remains valid, it reuses it, and when expired or near expiry, the provider **sends a new Client Credentials Token Request** and the manager saves the result.

For this mechanism to work reliably in production, keep `principalName` stable, choose storage suited to your instance count, tune `clockSkew` to token lifetime, control concurrency during token re-issuance, and protect access tokens and client credentials. **Never treat a service token as representing a human user, and never request new tokens just to work around scope, audience, or authorization errors.**

## Official References

- [RFC 6749 — OAuth 2.0, Client Credentials Grant](https://datatracker.ietf.org/doc/html/rfc6749#section-4.4): grant, token request/response, and refresh token notes.
- [Spring Security — OAuth2 Client Authorized Clients (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): authorized client manager and storage.
- [Spring Security — OAuth2 Client Authorization Grants (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): Client Credentials and customizing grant/token response clients.
- [Spring Security API — ClientCredentialsOAuth2AuthorizedClientProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ClientCredentialsOAuth2AuthorizedClientProvider.html): authorization conditions and clock skew.
- [Spring Security API — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html): provider configuration.
- [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): manager using authorized client service outside HTTP requests.
- [Spring Security API — OAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html): contract for saving and retrieving authorized clients.
