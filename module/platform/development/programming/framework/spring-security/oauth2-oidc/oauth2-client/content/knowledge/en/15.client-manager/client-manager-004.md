# 15.4. OAuth2AuthorizedClientProvider and Provider Composition

## 1. Context: How Does the Client Manager Obtain Tokens?

In **Spring Security OAuth 2.0/OIDC Client**, an application may need access tokens in several situations:

- A user logs in using the Authorization Code Grant, and the application later calls an API on their behalf.
- A user's access token expires and the application wants to **refresh** it without forcing a re-login, if the Authorization Server issued a refresh token.
- A backend task calls an API using the **Client Credentials Grant**, without representing a specific user.
- The application needs to apply an extension grant supported by the Authorization Server, or a grant-selection policy based on client type.

The central component for managing these scenarios is **`OAuth2AuthorizedClientManager`**. The manager works with client registrations, principals, where `OAuth2AuthorizedClient` instances are stored, and token issuance/extension mechanisms.

However, the manager should not hardcode the logic of every OAuth2 grant itself. Spring Security separates that concern through:

**`OAuth2AuthorizedClientProvider` — a strategy that can attempt to authorize or reauthorize an OAuth2 client given the current context.**

To support multiple grants, Spring Security can **compose multiple providers into a chain**. When the manager wants to authorize, it invokes the composite provider; that provider tries its components in order and determines the outcome.

This lesson focuses on **how providers work, how providers are composed, and how to choose policies when configuring a manager**.

### Objectives

After this lesson, you will be able to:

1. Understand the relationship between `OAuth2AuthorizedClientManager`, `OAuth2AuthorizedClientProvider`, and `OAuth2AuthorizedClient`.
2. Understand the meaning of **non-null**, **`null`**, and **exception** results from `authorize(...)`.
3. Distinguish between `authorization_code`, `refresh_token`, and `client_credentials` strategies.
4. Use `OAuth2AuthorizedClientProviderBuilder` to compose multiple providers.
5. Understand **execution order**, stopping rules, and why a composite is not a retry/failover mechanism.
6. Configure the right manager for **Servlet HTTP requests** and **background services**.
7. Know the customization points for token response clients, clock skew, success/failure handling, and token storage.
8. Know how to extend with a custom provider when genuinely needed.
9. Understand corresponding differences in Spring WebFlux/reactive.
10. Diagnose common errors without confusing token-issuance failures with token-persistence failures.

The URLs, registration IDs, and tokens in this lesson are illustrative data only. Code snippets demonstrate modern Spring Security; choose APIs compatible with the version you are using.

## 2. Classes Participating in Authorized Client Management

Before examining providers, distinguish these components:

| Component | Responsibility |
|---|---|
| `ClientRegistration` | Describes an OAuth2 client: client ID, token URI, grant type, scopes, client authentication method, etc. |
| `ClientRegistrationRepository` | Looks up `ClientRegistration` by `registrationId`. |
| `OAuth2AuthorizedClient` | Combines client registration, principal name, access token, and refresh token if present. |
| `OAuth2AuthorizedClientService` | Saves/reads authorized clients by `registrationId` and principal name, without needing an HTTP request. |
| `OAuth2AuthorizedClientRepository` | Saves/reads authorized clients by Servlet web request context and principal. |
| `OAuth2AuthorizedClientManager` | Coordinates client lookup, authorize/re-authorize, and saving/removing results per policy. |
| **`OAuth2AuthorizedClientProvider`** | **Decides whether authorization or re-authorization can/needs to be performed via a specific mechanism.** |
| `OAuth2AccessTokenResponseClient` | Sends the token request for a specific grant to the Authorization Server and parses the response. |

Conceptual diagram:

```mermaid
flowchart TD
    A["Application needs OAuth2AuthorizedClient"] --> B["OAuth2AuthorizedClientManager"]
    B --> C["ClientRegistrationRepository"]
    B --> D["OAuth2AuthorizedClientRepository / Service"]
    B --> E["OAuth2AuthorizedClientProvider"]
    E --> F["authorization_code strategy"]
    E --> G["refresh_token strategy"]
    E --> H["client_credentials strategy"]
    E --> I["custom strategy if needed"]
    G --> J["Token Endpoint"]
    H --> J
    D --> K["Session / InMemory / JDBC / custom store"]
```

Key distinction:

> The **Manager** decides how to orchestrate; the **Provider** decides how to attempt authorization/reauthorization; the **Token Response Client** executes the token request; the **Repository/Service** decides where to store the result.

An `OAuth2AuthorizedClientProvider` is **not** an identity provider like Google, Keycloak, or an OpenID Provider. In this lesson, *provider* means an **OAuth2 grant-handling strategy**, not an Authorization Server/IdP.

## 3. The `OAuth2AuthorizedClientProvider` Contract

The interface belongs to package:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider
```

Conceptual shape:

```java
public interface OAuth2AuthorizedClientProvider {

    OAuth2AuthorizedClient authorize(
        OAuth2AuthorizationContext context
    );
}
```

The `authorize(...)` method receives an `OAuth2AuthorizationContext` containing necessary information, such as:

- The `ClientRegistration` being authorized.
- The corresponding `Authentication` or principal.
- The existing `OAuth2AuthorizedClient`, if previously authorized.
- Additional attributes required by a grant/implementation.
- Other contextual data supplied by the manager.

### 3.1. Three Important Outcomes

| Result | Meaning | How the Manager / Composite Provider Handles It |
|---|---|---|
| Returns **`OAuth2AuthorizedClient`** | The provider successfully authorized/reauthorized or returned a result per contract. | Treated as the outcome of the attempt; the manager may persist it per success handling. |
| Returns **`null`** | The provider does not support this context/grant, or re-authorization is not yet needed. | The composite provider can try the next provider; the manager may keep using the existing authorized client if appropriate. |
| Throws **`OAuth2AuthorizationException`** or a related exception | Authorization encountered a real error or requires a special interactive step. | Usually stops the chain and hands error handling to the manager/web infrastructure. |

**`null` does not mean the token is invalid**, nor does it mean authorization failed. A current access token that is still valid may cause the provider to do nothing and return `null`.

Conversely, **an exception is not a signal to “try the next grant”**. When the AS returns a client authentication error or invalid refresh token, silently falling back to another grant could violate security policy.

### 3.2. `OAuth2AuthorizationContext` Is Not `ClientRegistration`

`ClientRegistration` is the static configuration of the client. `OAuth2AuthorizationContext` is **the context of the current authorization attempt**.

Example with the same registration:

```text
registrationId = corporate
authorizationGrantType = authorization_code

Attempt 1:
    no authorized client yet
    -> interactive authorization may be needed

Attempt 2:
    authorized client exists, access token is still valid
    -> no new token request needed

Attempt 3:
    access token expired, refresh token exists
    -> refresh_token provider can handle it

Attempt 4:
    refresh token was revoked
    -> error handling needed, possibly requiring new authorization
```

Looking only at a registration's `authorizationGrantType` is not enough to determine all behavior. You need to know **whether an authorized client already exists**, whether the token is still valid, and whether a refresh token is present.

## 4. Composite Provider: Chaining Strategies by Order

Spring Security provides a composite implementation:

```java
org.springframework.security.oauth2.client.DelegatingOAuth2AuthorizedClientProvider
```

Idea:

```text
Composite Provider
    |
    +-- Provider A
    |      -> returns null? Try B
    |      -> returns authorized client? Finish
    |      -> throws exception? Stop and report error
    |
    +-- Provider B
    |      -> returns null? Try C
    |      -> returns authorized client? Finish
    |      -> throws exception? Stop and report error
    |
    +-- Provider C
           -> ...
```

Diagram:

```mermaid
flowchart TD
    A["authorize(context)"] --> B["Provider 1"]
    B --> C{"Result?"}
    C -->|Authorized Client| Z["Return result"]
    C -->|Exception| X["Stop and report error"]
    C -->|null| D["Provider 2"]
    D --> E{"Result?"}
    E -->|Authorized Client| Z
    E -->|Exception| X
    E -->|null| F["Provider 3"]
    F --> G{"Result?"}
    G -->|Authorized Client| Z
    G -->|Exception| X
    G -->|null| N["Return null"]
```

### 4.1. The “First Provider Returning Non-Null” Rule

If the first provider returns an authorized client, subsequent providers **are not invoked** for that turn.

Therefore, order can affect behavior when:

- A custom provider accepts multiple registration types.
- Two providers could both apply to the same context.
- The first provider proactively decides authorization must be performed.
- A provider throws a specific error instead of returning `null`.

### 4.2. A Composite Is Not a Load Balancer or API Failover

Do not treat:

```text
refresh_token error -> retry client_credentials -> try authorization_code
```

as a default fallback policy.

In OAuth2 flows, each grant represents **a distinct authorization mechanism with its own semantics**. `client_credentials` issues a token for the client/service, and cannot arbitrarily replace a token representing a user. An `invalid_grant` error on refresh token does not permit the application to silently grab a service token and pretend it still represents the user.

**Only a `null` return causes the composite to evaluate the next provider; a real error is not an invitation to switch grants.**

## 5. `OAuth2AuthorizedClientProviderBuilder`

The most common configuration approach is the builder:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
```

The builder produces a composite provider with the registered strategies.

Read this snippet as:

- `authorizationCode()` adds handling related to the Authorization Code Grant.
- `refreshToken()` adds the ability to refresh access tokens when a suitable refresh token is present.
- `clientCredentials()` adds the ability to obtain/reissue tokens via the Client Credentials Grant.
- `build()` creates a provider for the manager to use.

This is **configuring the capabilities of the manager**, not requiring every manager call to use all three grants.

### 5.1. Why Use the Builder?

- Clearly declares the grants supported by the application.
- Easier to read than manually instantiating and wiring multiple strategy objects.
- Can add custom providers or customize a specific grant depending on version APIs.
- Easy to attach the same configured provider to appropriate managers.
- Reduces the risk of reimplementing OAuth2 protocol logic with a hand-rolled HTTP client.

### 5.2. Do Not Enable Every Grant Reflexively

Some applications only need:

```java
OAuth2AuthorizedClientProvider serviceProvider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
```

An interactive user portal might need:

```java
OAuth2AuthorizedClientProvider userProvider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();
```

What matters is that the grant is actually permitted by the Authorization Server for the registration and fits the context.

**Do not enable Resource Owner Password Credentials (password grant) by default** as a convenience for new applications. This grant has been dropped from modern OAuth2 guidance, and supporting APIs in Spring Security have changed/been deprecated across versions. This lesson uses Authorization Code + PKCE or Client Credentials appropriately instead of encouraging the password grant.

## 6. `authorizationCode()`: When Is User Interaction Needed?

The Authorization Code Grant typically requires a browser redirect, login, and consent:

```mermaid
sequenceDiagram
    autonumber
    actor U as User/Browser
    participant C as Spring OAuth2 Client
    participant AS as Authorization Server

    U->>C: Request resource/authorization
    Note over C: No authorized client yet
    C-->>U: Redirect to Authorization Endpoint
    U->>AS: Authorization request
    AS-->>U: Login/consent
    AS-->>U: Callback with code
    U->>C: Callback
    C->>AS: Token request exchanging code (and PKCE verifier)
    AS-->>C: Tokens
    Note over C: Save OAuth2AuthorizedClient
```

In the OAuth2 Client Manager, `authorizationCode()` is not a “machine that invents authorization codes” inside a backend task. When no suitable authorized client exists yet, this strategy can **signal that interactive authorization is required** through Spring Security's exception/signal mechanism.

Redirects, callbacks, `state`, PKCE, and code exchange are coordinated by **OAuth2 Login/Client filters and the authorization request infrastructure** in the appropriate web context.

### 6.1. Without a Browser, the Authorization Code Grant Cannot Complete Itself

A scheduled job calling:

```java
manager.authorize(request);
```

with an `authorization_code` registration before any user authorization has happened cannot expect the manager to log in on the user's behalf. The job has no browser, cookies, consent, or ungranted user authority.

If a background task needs to call an API on behalf of a user, you must first design an interactive authorization flow, save valid tokens (if allowed), and then use the authorized client/service for the right principal. If only application permissions are needed, consider `client_credentials`.

### 6.2. PKCE Is Not Generated by the Provider Chain Alone

PKCE binds the authorization code between the authorization request and the token request. Spring Security handles it in the corresponding authorization request and Token Endpoint components.

Merely adding `.authorizationCode()` to the provider builder **does not guarantee** every client has PKCE S256 in every version/configuration. Check your provider policy and Spring Security configuration, especially for confidential clients.

### 6.3. OIDC Still Uses the Authorization Code Grant

An OIDC client with the `openid` scope can use:

```yaml
authorization-grant-type: authorization_code
scope: [openid, profile, email]
```

`authorizationCode()` is an **OAuth2 grant** strategy; verifying the ID Token belongs to the **OIDC authentication** flow, not the composite provider's job.

## 7. `refreshToken()`: Extending Granted Authorization

An `OAuth2AuthorizedClient` may contain:

```text
access token:  AT1, near expiry
refresh token: RT1
```

If the Authorization Server issued a refresh token and the registration allows it, the `refreshToken()` provider can execute:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=refresh_token&refresh_token=RT1
```

The provider reads the token response and creates a new authorized client or updates the token information for the manager to save.

### 7.1. Typical Preconditions for Refresh

- An existing authorized client is present.
- The access token has expired or is about to expire within **clock skew**.
- The authorized client has a valid refresh token.
- The client is permitted to use the refresh token grant.
- The Token Endpoint accepts the refresh token along with the required client authentication.

If the access token still has sufficient lifetime remaining, the refresh provider usually **returns `null`** to avoid unnecessary token requests.

If no refresh token is present, the refresh provider cannot invent one. Requesting `offline_access` does not guarantee every provider will issue a refresh token; it still depends on policy, consent, and client type.

### 7.2. Refresh Token Rotation

A provider may return:

```text
Before:
  access_token = AT1
  refresh_token = RT1

After refresh:
  access_token = AT2
  refresh_token = RT2
```

The application must persist the **new refresh token** if the AS rotates tokens. Keeping `RT1` and reusing it may be rejected or trigger reuse detection.

In a multi-instance environment, two requests grabbing `RT1` to refresh concurrently can cause a race condition. The provider builder does not solve token storage concurrency by itself; you need locking/update policies aligned with `OAuth2AuthorizedClientService` or the repository.

### 7.3. A Refresh Error Does Not Mean Try Client Credentials

For example, the AS returns:

```json
{
  "error": "invalid_grant",
  "error_description": "Refresh token is invalid or revoked"
}
```

The manager/failure handler must handle this according to OAuth2 semantics and application policy. Never fetch a `client_credentials` token and use it as a user token. If user permissions need to be re-granted, a valid authorization flow is required.

## 8. `clientCredentials()`: Tokens for Services/Backends

The Client Credentials Grant is suitable when a service needs to call an API **with the client's own permissions**, not on behalf of a user.

Example registration:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-api:
            provider: internal-as
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [inventory.read]
        provider:
          internal-as:
            token-uri: https://auth.internal.example/oauth2/token
```

Conceptual token request:

```http
POST /oauth2/token HTTP/1.1
Host: auth.internal.example
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=client_credentials&scope=inventory.read
```

When no authorized client exists yet, `ClientCredentialsOAuth2AuthorizedClientProvider` can request a token. While the access token remains valid, it does not need to reissue. Once expired, it can make a new token request.

The Client Credentials Grant usually **does not use refresh tokens**; when the access token expires, the client uses this grant again to request a new token.

### 8.1. The Token Carries the Client's Permissions, Not a User's

If the backend serves both Alice and Bob, distinguish:

```text
Alice's access token:
    authorization_code / refresh_token
    represents authorization granted in Alice's context

Inventory service's access token:
    client_credentials
    represents the inventory application itself
```

Never use a service token to bypass user authorization in business logic. The Resource Server still needs to check scopes, audience, and access policies appropriate to the principal/service type.

### 8.2. Principal Name Is a Storage Key, Not Something That Turns a Token into a User Token

When calling the authorized client manager for a service, you can choose a stable principal name like `inventory-batch`. This name serves as the **authorized client storage/cache key**; it does not make a Client Credentials Grant access token represent a human user.

## 9. Provider Composition Order: Looking at Concrete Scenarios

Suppose the configuration is:

```java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
```

Scenarios:

| Context | `authorizationCode()` | `refreshToken()` | `clientCredentials()` | Expected Outcome |
|---|---|---|---|---|
| `authorization_code` registration, no authorized client yet | May require interactive authorization | No token to refresh | Does not support this grant | Web infrastructure handles login/redirect if present. |
| `authorization_code` registration, token still valid | No new authorization needed | No refresh needed | Does not support grant | Manager continues using existing authorized client per contract. |
| `authorization_code` registration, token expired, refresh token present | Does not start a new auth flow for already-authorized client | Attempts refresh | Does not support grant | Token is refreshed if AS accepts. |
| `client_credentials` registration, no token yet | Does not support grant | No authorized client/refresh token | Attempts to issue new token | Client Credentials Token Request. |
| `client_credentials` registration, token still valid | Does not support | Normally no refresh token/refresh needed | Does not reissue | Uses still-valid token. |
| Registration not supported by any provider | Returns `null`/not applicable | Returns `null`/not applicable | Returns `null`/not applicable | No mechanism to auto-authorize from this chain. |

The table describes conceptual outcomes and does not replace reading the contract and testing against your framework version. When the Authorization Server returns an error or the flow requires interaction, the outcome may be an exception rather than `null`.

### 9.1. Why Does Putting `authorizationCode()` Before `refreshToken()` Still Make Sense?

If an authorized client **already exists**, the authorization code provider should not force a new login session merely because the access token is near expiry; the refresh provider can proceed with its work.

If an authorized client **does not exist yet**, authorization code may need to initiate the interactive flow rather than trying to refresh a nonexistent token.

### 9.2. What Happens When a Custom Provider Comes First?

Suppose you put a custom provider first that returns **a non-null authorized client** for every request, even when it did not properly handle the grant. Subsequent providers will never run. The manager may assume authorization succeeded and persist an incorrect result.

Rules for writing a custom provider:

- **Only return non-null when you have a valid result per contract.**
- Return `null` when you **do not support** the context or **do not need** to re-authorize.
- Throw an error when the transaction genuinely fails or policy requires rejection.
- Never return a dummy authorized client as a “placeholder”.

## 10. Configuring the Manager in Spring Security Servlet

For a Servlet/MVC application handling HTTP requests, the appropriate manager is typically:

```java
org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager
```

The constructor requires:

- `ClientRegistrationRepository`.
- `OAuth2AuthorizedClientRepository`.

Java example:

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
public class AuthorizedClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

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
```

What this configuration makes explicit:

1. The manager looks up the registration by `registrationId`.
2. The manager reads the existing authorized client from the repository per HTTP/principal context.
3. The manager invokes the composite provider.
4. The provider decides whether authorization is possible/needed.
5. If a result is returned, the manager persists or updates it via the success handler.
6. If an error occurs, the manager delegates to failure handling and the caller per contract.

This snippet only creates the **Servlet manager**. OAuth2 Login filters, sessions, and redirects still must be configured for the web application.

### 10.1. Securing the Servlet App for User Login

Example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
```

`oauth2Login()` handles user authentication. `oauth2Client()` supports OAuth2 Client features when the app needs tokens to call APIs. Some applications only need one of the two depending on their goals.

If the application already has a `SecurityFilterChain`, integrate the configuration into the existing chain rather than accidentally duplicating a chain with overlapping matchers.

### 10.2. The Manager Does Not Replace OAuth2 Client Registration

You still need `ClientRegistrationRepository`, typically built by Spring Boot from `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal-login:
            provider: company-oidc
            client-id: ${PORTAL_CLIENT_ID}
            client-secret: ${PORTAL_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
          inventory-api:
            provider: company-oidc
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [inventory.read]
        provider:
          company-oidc:
            issuer-uri: https://id.example.com
```

This assumes the illustrative provider supports both grants and has the corresponding client registrations permitted. A `client_credentials` registration cannot by default be used to log users in with `oauth2Login()`.

## 11. Calling the Manager from Application Code

Interface:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager
```

Primary method:

```java
OAuth2AuthorizedClient authorize(
    OAuth2AuthorizeRequest authorizeRequest
);
```

`OAuth2AuthorizeRequest` specifies:

- The registration ID or authorized client being requested.
- The principal serving as the authorization context.
- Additional attributes when needed.

Example:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

public final class InventoryTokenService {

    private final OAuth2AuthorizedClientManager manager;

    public InventoryTokenService(
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public OAuth2AuthorizedClient getAuthorizedClient() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("inventory-api")
                .principal("inventory-worker")
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                "No authorized client available for inventory-api"
            );
        }

        return client;
    }
}
```

This snippet shows how to call the manager, though **in background jobs** you should use `AuthorizedClientServiceOAuth2AuthorizedClientManager` as shown in the next section. If multiple manager beans exist for injection, select the right one explicitly.

Never return a raw `OAuth2AuthorizedClient` over a REST API because it contains an access token and possibly a refresh token. When calling APIs, fetch the token on the server and use it only for the designated registered resource server.

### 11.1. Distinguishing `authorize()` on the Manager vs. the Provider

- `OAuth2AuthorizedClientManager.authorize(request)` is the API **application code** normally calls.
- `OAuth2AuthorizedClientProvider.authorize(context)` is the API **the manager** uses to execute a strategy.

In business code, you almost never **call `OAuth2AuthorizedClientProvider` directly**, because doing so forces you to manage context, repositories, success/failure handling, and token lifecycles yourself.

## 12. Manager for Background Jobs: Independent of Servlet HTTP Requests

`DefaultOAuth2AuthorizedClientManager` is built for Servlet web request contexts. In scheduled jobs, batch processes, or service-to-service backends without an `HttpServletRequest`, the right choice is:

```java
org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager
```

Constructor:

```java
AuthorizedClientServiceOAuth2AuthorizedClientManager(
    ClientRegistrationRepository clientRegistrationRepository,
    OAuth2AuthorizedClientService authorizedClientService
)
```

**Client Credentials** example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class ServiceTokenManagerConfig {

    @Bean("serviceAuthorizedClientManager")
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClientService
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

If the application has both a Servlet manager and a background manager, assign clear names/qualifiers so injection is unambiguous. You can configure **two different sets of providers** for the two managers instead of sharing one composite for everything.

### 12.1. `principalName` Used as a Storage Key

With the service manager:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-api")
        .principal("inventory-worker")
        .build();
```

The string `"inventory-worker"` is the **principal name used to look up/save the authorized client**; it does not automatically give the access token the permissions of a user with that name.

When using `client_credentials`, the token represents the client/service. If different workloads require token isolation, choose appropriate principal names, registrations, and security boundaries.

### 12.2. Background Job Needing a User's Token

If a job needs to call an API on behalf of Alice, the system must already have an authorization granted by Alice, persist tokens/refresh tokens per policy, and pass the matching principal when authorizing.

Never substitute a service's `client_credentials` token for Alice's token. Never reuse Alice's token for Bob due to a shared registration ID.

## 13. Clock Skew and Expiration Conditions

A token's expiration time is typically represented via `OAuth2AccessToken.getExpiresAt()`. A provider can treat a token as **about to expire** ahead of the actual timestamp by a **clock skew** margin.

Example:

```text
Now = 10:00:00
Access token expiresAt = 10:00:40
Clock skew = 60 seconds

The provider may treat the token as needing renewal
immediately since only 40 seconds of safe use remain.
```

Benefits:

- Reduces calls to APIs with tokens that expire mid-flight.
- Mitigates minor clock drift between the client and AS.
- Provides a buffer for network latency and token processing.

### 13.1. Customizing Clock Skew

In Spring Security versions that support the corresponding customizers on the builder, for example:

```java
import java.time.Duration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .refreshToken(refresh -> refresh
            .clockSkew(Duration.ofSeconds(45))
        )
        .clientCredentials(clientCredentials -> clientCredentials
            .clockSkew(Duration.ofSeconds(45))
        )
        .build();
```

Or configure provider instances directly per your API version, such as `RefreshTokenOAuth2AuthorizedClientProvider.setClockSkew(...)` and `ClientCredentialsOAuth2AuthorizedClientProvider.setClockSkew(...)`.

Do not set skew too large relative to the token lifetime such that every request asks for a new token. Do not use skew as a workaround when the AS issues already-expired tokens or when server clocks are hours off.

### 13.2. Do Not Confuse Clock Skew with Refresh Token Expiry

Clock skew here applies primarily to the **access token** and the decision to re-authorize early. Refresh tokens have a separate lifecycle and policy; some providers do not even publish refresh token expiration times in the token response.

If a refresh token has been revoked, no amount of clock skew adjustment will make it valid again.

## 14. Customizing the HTTP Client per Grant

Different strategies can use **different token response clients**:

| Grant | Modern Servlet Client | When Used |
|---|---|---|
| Authorization Code | `RestClientAuthorizationCodeTokenResponseClient` | Exchanging the authorization code after callback. |
| Refresh Token | `RestClientRefreshTokenTokenResponseClient` | Sending refresh token requests. |
| Client Credentials | `RestClientClientCredentialsTokenResponseClient` | Requesting a service token from the Token Endpoint. |

Exact APIs and classes depend on the Spring Security version. Prior to Spring Security 6.4, some grants used `RestTemplate`-based token response clients; newer releases offer corresponding `RestClient` implementations.

### 14.1. Why Configure per Grant?

An application might:

- Successfully exchange authorization codes through a proxy.
- Fail refresh token calls because the refresh token response client still uses the default HTTP transport without the proxy.
- Or hit timeouts on client credentials because timeouts were only configured for the authorization code grant.

When customizing via the provider builder, APIs like:

```java
.refreshToken(refresh -> refresh
    .accessTokenResponseClient(customRefreshClient)
)
.clientCredentials(clientCredentials -> clientCredentials
    .accessTokenResponseClient(customClientCredentialsClient)
)
```

allow passing the corresponding token response clients if your version supports those overloads.

Here `customRefreshClient` and `customClientCredentialsClient` are **instances constructed with the matching generic grant request type**, not built-in class names.

### 14.2. Do Not Rewrite Token Requests Just to Change Timeouts

If you need a proxy, TLS, or connect/read timeouts, customize the `RestClient`/request factory of the token response client rather than manually POSTing JSON/form bodies and parsing tokens by hand.

OAuth2 token response clients already handle details like client authentication, form encoding, token responses, OAuth2 errors, and grant extensions. Replacing them with hand-rolled HTTP requests easily breaks protocol compliance.

## 15. Persisting the Authorized Client After a Provider Returns a Result

A provider returning an `OAuth2AuthorizedClient` does not mean the token is already saved where subsequent requests can find it. The manager usually pairs a **success handler** with a **repository/service** to save the result.

Relationship:

```text
Provider authorize(context)
    |
    +-- Returns null:
    |      Manager may keep the current authorized client
    |
    +-- Returns OAuth2AuthorizedClient:
    |      Manager handles success
    |      |
    |      +-- Repository / Service saves the new token
    |
    +-- Throws error:
           Manager handles failure per policy
           May remove authorized client in certain cases
```

### 15.1. How Do InMemory, JDBC, and Session Differ?

| Store | Characteristics |
|---|---|
| `InMemoryOAuth2AuthorizedClientService` | Easy to test, stored in RAM, not shared across nodes, lost on restart. |
| `JdbcOAuth2AuthorizedClientService` | DB persistence; requires schema, TLS, encryption, backups, and lifecycle policies. |
| `HttpSessionOAuth2AuthorizedClientRepository` | Stored in the HTTP session, suited for session-bound flows; depends on session lifecycle. |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Routes authenticated principals to a service, anonymous ones to session by default. |
| Custom store | Can target Redis/DB/token vault, but must ensure correctness, confidentiality, and concurrency yourself. |

**The provider chain determines the token-issuance strategy, not where tokens are stored.** Choosing storage is the responsibility of the manager and the repository/service implementations.

### 15.2. When Changing Stores, Verify the Manager Uses the Right One

A project might declare a JDBC service while a custom manager still points to a separate InMemory service. Result: after restart, tokens vanish even though the DB table exists.

Ensure everything wires from the same configuration source. Do not confuse `ClientRegistrationRepository` (metadata) with `OAuth2AuthorizedClientService` (issued tokens).

## 16. Success Handler and Failure Handler

Managers can expose extension points for **authorization success** and **authorization failure**.

### 16.1. Success

When a provider succeeds, the manager normally saves the corresponding authorized client. If you replace the success handler, ensure that:

- The new token is saved under the exact registration ID and principal.
- Refresh token rotation updates are persisted.
- Sensitive tokens are not written to logs.
- User tokens are never accidentally saved under a different service principal.

### 16.2. Failure

When the token endpoint returns an error, some errors indicate the current token/authorization is no longer usable. For example, `invalid_grant` on a revoked refresh token may lead to removing the authorized client from the store under appropriate failure handling.

However, not every error is a sign to delete permanently:

| Error | Common Meaning | What to Do |
|---|---|---|
| `invalid_grant` on refresh | Refresh token invalid/expired/reused | Review policy for deleting the authorized client and reauthorization. |
| `invalid_client` | Client authentication failed | Fix client ID, secret, assertion, or method. |
| HTTP 503/timeout | AS/proxy/network temporarily unavailable | Do not treat all tokens as revoked. |
| `insufficient_scope` when calling API | Access token lacks sufficient permissions | Grant proper scopes/consent; not directly a provider chain bug. |
| API 401 due to mismatched audience | Token not intended for that resource | Check API, registration, audience/resource. |

**Never install an exception handler that swallows all errors and requests a `client_credentials` token in place of a user's token.** That is a principal-type security flaw.

## 17. Provider Order Does Not Replace Security Rules

An ordered composite can feel like a policy engine. Keep these distinct:

- Providers decide which grant can authorize in a given context.
- The Authorization Server validates client credentials, grant types, scopes, PKCE, and policies.
- The Resource Server validates tokens, audience, scopes, and API access permissions.
- The application must still enforce business authorization.

For instance, a request from Alice must not be allowed to read Bob's order data. Even if the provider returns a valid access token, that **does not mean** Alice is allowed to view every order.

### 17.1. Never Combine User Grants and Service Grants to Bypass Permissions

A dangerous design:

```text
Try Alice's token
    |
    +-- access token lacks permissions?
    |
    +-- silently switch to backend's client_credentials token
    |
    +-- call API with broader permissions
```

The provider chain is **not** a privilege-escalation mechanism when a user lacks scopes or a token expires. If an API supports a proper delegated access/token exchange architecture, trust, audience, and authorization policies must be explicitly designed.

## 18. Custom `OAuth2AuthorizedClientProvider`: When Is It Needed?

Use built-in providers first. A custom provider can make sense when:

- The Authorization Server supports an extension grant or token-exchange mechanism not yet directly provided by your Spring Security version.
- You need to enforce a specific policy layer before invoking built-in providers.
- You need a special strategy per tenant or registration that cannot be expressed via the default manager/builder.
- You need observability/structured metrics around authorization attempts while preserving standard logic.

**Do not write a custom provider merely to set a connect timeout or proxy.** Those changes belong in the token response client / HTTP transport.

### 18.1. Implementation Principles

A custom provider must adhere to these rules:

1. Return `null` if the context is outside the provider's scope.
2. Never manipulate tokens belonging to another registration/tenant.
3. Never issue a new token if the existing authorized client is still valid and the contract does not require it.
4. Never return a dummy authorized client.
5. Propagate appropriate protocol errors so the manager can handle them.
6. Do not manually save/delete tokens inside the provider when the manager already manages persistence, unless explicitly designed to do so.
7. Never log tokens/secrets.
8. Never blindly retry grants containing single-use credentials.
9. Never turn a service token into a user token.
10. Write tests covering `null`, success, and failure branches.

### 18.2. A Provider Filtering Registrations via Delegation

Suppose you want a strategy to run only for a specific group of registrations:

```java
import java.util.Set;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;

public final class RegistrationScopedProvider
        implements OAuth2AuthorizedClientProvider {

    private final Set<String> registrations;
    private final OAuth2AuthorizedClientProvider delegate;

    public RegistrationScopedProvider(
            Set<String> registrations,
            OAuth2AuthorizedClientProvider delegate) {
        this.registrations = Set.copyOf(registrations);
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthorizedClient authorize(
            OAuth2AuthorizationContext context) {

        String registrationId = context
            .getClientRegistration()
            .getRegistrationId();

        if (!registrations.contains(registrationId)) {
            return null;
        }

        return delegate.authorize(context);
    }
}
```

Example usage:

```java
OAuth2AuthorizedClientProvider builtIn =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();

OAuth2AuthorizedClientProvider scoped =
    new RegistrationScopedProvider(
        Set.of("inventory-api"),
        builtIn
    );
```

If `scoped` is the **sole provider** of the manager for the service-token use case, the manager only attempts the delegate-supported grant for the allowlisted registrations.

**Warning:** returning `null` is not an access-blocking mechanism if you chain another provider after it that can authorize the same registration. The next provider can still run. If the goal is to **strictly deny** a registration, enforce the policy at the authoritative boundary or throw an appropriate policy error from a wrapper enclosing the whole chain, alongside authorization policies across relevant layers.

### 18.3. Composing Directly with `DelegatingOAuth2AuthorizedClientProvider`

Besides the builder, you can compose provider instances explicitly:

```java
import org.springframework.security.oauth2.client.DelegatingOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.RefreshTokenOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ClientCredentialsOAuth2AuthorizedClientProvider;

OAuth2AuthorizedClientProvider provider =
    new DelegatingOAuth2AuthorizedClientProvider(
        new RefreshTokenOAuth2AuthorizedClientProvider(),
        new ClientCredentialsOAuth2AuthorizedClientProvider()
    );
```

This is useful when you need fine-grained instance configuration or want to include a custom provider. Only include grants that truly match the manager and registrations.

## 19. Customizing a Grant vs. Writing a New Grant

There are multiple levels of extensibility:

| Need | Approach |
|---|---|
| Support authorization code + refresh + client credentials | `OAuth2AuthorizedClientProviderBuilder`. |
| Change timeout, proxy, TLS of token HTTP requests | Token response client / `RestClient` / `WebClient`. |
| Add token request parameters per provider contract | Token response client converter/customizer. |
| Change clock skew | Builder grant customizer or provider setter. |
| Choose storage for authorized clients | Manager's Repository/Service. |
| Handle token refresh failures | Failure handler/policy on the manager. |
| Support a completely custom grant | Custom `OAuth2AuthorizedClientProvider` and matching token response client. |
| Change how resource APIs are called | The API's HTTP client, not the provider chain. |

### 19.1. Do Not Add a Grant That the AS Does Not Support

For example, OAuth2 token exchange or JWT bearer assertions only make sense when the Authorization Server implements that grant and the client is authorized to use it. Depending on the Spring Security version, built-in support may exist or a custom extension may be required.

You cannot simply change an `authorizationGrantType` in Java and assume the AS will accept it. Always verify AS metadata, policies, and registration settings.

### 19.2. Testing a Custom Grant with a Clear Contract

A custom provider should be tested across these scenarios:

```text
Unsupported registration -> returns null.
Matching registration, token still valid -> does not reauthorize.
Matching registration, token needed -> calls the right token client.
Valid token response -> returns OAuth2AuthorizedClient.
Token endpoint invalid_client -> throws error, does not randomly switch grants.
Network timeout -> informative error, never logs credentials.
```

Ensure principal name, audience/scopes, and refresh token lifecycle conform to the contract.

## 20. Reactive/WebFlux Uses the Same Provider Composition Idea

In **Spring Security WebFlux**, the corresponding API family is:

```java
ReactiveOAuth2AuthorizedClientProvider
ReactiveOAuth2AuthorizedClientProviderBuilder
DefaultReactiveOAuth2AuthorizedClientManager
AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
```

The main difference is the reactive return type, typically:

```java
Mono<OAuth2AuthorizedClient>
```

Equivalent semantics:

- `Mono` emitting an authorized client: the provider succeeded.
- `Mono.empty()`: the provider does not apply or reauthorization is unnecessary.
- `Mono.error(...)`: an error occurred; not automatically treated as a grant fallback.

### 20.1. Example Reactive Provider Builder

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;

@Configuration
public class ReactiveProviderConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientProvider reactiveAuthorizedClientProvider() {
        return ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .authorizationCode()
            .refreshToken()
            .clientCredentials()
            .build();
    }
}
```

To use it, attach the provider to the chosen reactive manager. For web requests, the manager typically uses `ReactiveClientRegistrationRepository` and `ServerOAuth2AuthorizedClientRepository`. For non-web tasks, use `ReactiveOAuth2AuthorizedClientService` with the service-oriented reactive manager.

### 20.2. Do Not Put a Servlet Provider into a Reactive Manager

The types:

```text
OAuth2AuthorizedClientProvider
ReactiveOAuth2AuthorizedClientProvider
```

are not interchangeable. Servlet providers produce synchronous results, whereas reactive providers use reactive publishers. Never call a blocking token HTTP client inside a WebFlux event loop and expect non-blocking behavior.

## 21. Choosing Manager and Provider by Architecture

| Application | Appropriate Manager | Typical Provider Chain | Store |
|---|---|---|---|
| MVC portal with OAuth2/OIDC login | `DefaultOAuth2AuthorizedClientManager` for web requests; OAuth2 Login infrastructure | `authorizationCode` + `refreshToken` | Servlet repository/session/service |
| MVC portal also calling service APIs | Combine a manager for users and a separate manager for services | User: `authorizationCode`/`refreshToken`; Service: `clientCredentials` | Separate principal namespaces and stores if needed |
| Scheduled backend job | `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `clientCredentials` | `OAuth2AuthorizedClientService` |
| Background job acting on behalf of consented user | Service-oriented manager with prior policy/authorization | `refreshToken` and valid reissuance mechanism | Persistent service where permitted |
| WebFlux web application | `DefaultReactiveOAuth2AuthorizedClientManager` | Reactive `authorizationCode`/`refreshToken`... | Reactive repositories |
| Reactive background job | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | Reactive `clientCredentials` or appropriate grant | Reactive authorized client service |

There is no requirement to build one composite containing every grant for every application. **Prefer the minimal configuration that satisfies the exact authorizations required.**

## 22. Troubleshooting: Composing Providers Without Getting a Token

| Symptom | Likely Cause | What to Check |
|---|---|---|
| Manager returns `null` | No provider supports context, no authorized client yet, or preconditions unmet | Registration grant type, provider chain, context |
| Manager throws `ClientAuthorizationRequiredException` | Authorization Code Grant requires browser interaction | Login/redirect flow, HTTP request context |
| Client credentials not running | Chain lacks `.clientCredentials()` or registration uses another grant | Builder and `authorization-grant-type` |
| Not refreshing | Missing `.refreshToken()`, no refresh token, or token still valid | Existing authorized client, refresh token, clock skew |
| Refresh fails with `invalid_grant` | Refresh token expired/revoked/rotated, wrong binding | AS logs per policy, refresh token lifecycle |
| OAuth2 `invalid_client` | Wrong client secret/method/assertion | Client registration and token HTTP client |
| Token endpoint timeout | Proxy/TLS/connect/read timeout | Grant-specific token response client |
| Token lost after restart | InMemory service or local session | Repository/service persistence |
| Random refresh failures across multiple pods | Rotation race | Shared storage and concurrency control |
| User token replaced by service token | Improperly composed grants / wrong principal | Separate managers and authorization contexts |
| Token obtained but API returns 403 | Insufficient scope/role/business authorization | Resource Server policy, scopes, audience |
| Token obtained but API returns 401 | Expired token / wrong audience / wrong issuer | API validation, token lifecycle |
| Custom provider returns non-null too early | Wrong chain order and return semantics | Return `null` when unhandled, test provider chain |
| Custom provider throws and fallback never runs | Composite stops on exception | Distinguish no-op from failure, do not swallow errors |
| OIDC login fails ID Token signature check | JWKS/issuer/audience/nonce | OIDC validation, not the provider chain |
| Background task fails due to missing HTTP request | Using Servlet manager outside request context | Choose service-oriented manager |

### 22.1. Provider `null` and Manager `null` Are Not the Same Thing

A provider returning `null` may simply mean **no token change is needed**, for example because the current token is still valid. The manager can continue returning the existing authorized client.

If the **manager returns `null`**, the caller has no usable authorized client for the current request. Inspect the client registration, existing authorized client, provider chain, and active flow rather than immediately concluding the Authorization Server is broken.

### 22.2. A Provider Chain Does Not Mean Tokens Always Refresh Automatically

`refreshToken()` can only work if the manager has an authorized client with a valid refresh token. If custom code fails to save the authorized client, subsequent calls will not find the old token to refresh.

Configure the repository/service and success/failure handling properly.

### 22.3. Do Not Log Secrets While Debugging

Token requests/responses may contain:

```text
client_secret
client_assertion
authorization_code
code_verifier
access_token
refresh_token
id_token
```

Log only approved registration IDs, grant types, timings, HTTP statuses, and redacted error codes. Never print tokens, Basic Authorization headers, or signed assertions.

## 23. Applied Scenarios

### Scenario A: OIDC Portal with `authorizationCode` + `refreshToken`

Users log in with `portal-login`, tokens expire after one hour, and the provider issues refresh tokens.

**Configuration:** manager supporting `authorizationCode()` and `refreshToken()`. Ensure authorized clients are stored under the right user/principal, and the refresh token response client can reach the Token Endpoint. Do not force browser re-login if refresh succeeds per policy.

### Scenario B: Service Fetching Tokens with `clientCredentials`

An inventory scheduler has no user session.

**Configuration:** service-oriented manager and `.clientCredentials()`. Use a stable principal name to cache the service token without impersonating a user.

### Scenario C: Using `.clientCredentials()` to Fix Expired User Tokens

A team appends `.clientCredentials()` after `.refreshToken()` hoping that if refreshing a user's token fails, a service token will automatically step in.

**Conclusion:** Wrong model. A refresh error is normally an exception; the provider chain does not automatically fall back. Furthermore, a service token cannot represent a user unless authorization/policy permits it.

### Scenario D: Custom Provider Always Returns the Old Authorized Client

A custom provider receives the context, sees an existing client, and returns it even though the access token has expired.

**Conclusion:** Returning non-null too early prevents subsequent providers from running. When handling is unnecessary or unsupported, return `null` per contract so the manager can decide about the existing client.

### Scenario E: Background Job Using `authorizationCode` with No Token Yet

A job runs without a browser and the manager reports authorization is required.

**Solution:** design an interactive authorization flow beforehand, or use a grant that fits the model such as client credentials when service permissions are appropriate. Never hardcode a user's username/password into the job.

### Scenario F: Partner API Requires Refresh Token Rotation

Two nodes refresh token `RT1` at the same time.

**Solution:** token storage and concurrency policies must handle rotation. The provider builder does not automatically lock distributed refreshes.

### Scenario G: Builder Configured, Yet a Different Manager Is Used

The application has two `OAuth2AuthorizedClientManager` beans; the controller injects the wrong manager that does not support refresh tokens.

**Solution:** use explicit bean names/qualifiers and configure the provider chain on the exact manager being used.

### Scenario H: Custom Token Response Client Loses OAuth2 Error Handling

When refresh returns HTTP 400, custom hand-rolled code only reads JSON and swallows the error.

**Solution:** use Spring Security's token response clients and customize transport/converters via the official API to preserve protocol error handling.

### Scenario I: One Application with Two Registrations Using Different Grants

`portal-login` is authorization code; `inventory-api` is client credentials.

**Understanding:** a chain can support both grants, yet each authorize request must select the right registration/principal. Consider two separate managers to reduce the risk of mixing tokens.

### Scenario J: OIDC Login Succeeds, API Call Fails

The provider chain successfully yields an authorized client, yet the API returns 403.

**How to handle:** check access token scopes/audience and Resource Server policies. Successfully issuing a token does not automatically grant every business permission.

## 24. Self-Check Questions

**Question 1.** How do `OAuth2AuthorizedClientProvider` and `OAuth2AuthorizedClientManager` differ?

**Answer:** The manager coordinates registration, context, persistence, and the authorization lifecycle; the provider decides whether authorization or reauthorization can/should happen under a specific OAuth2 strategy.

**Question 2.** Does a provider returning `null` mean authorization failed?

**Answer:** Not necessarily. The provider might not support the grant, or the current token might still be valid so nothing needs to be done.

**Question 3.** What does the composite do if the first provider returns an authorized client?

**Answer:** It returns the result immediately and does not invoke subsequent providers.

**Question 4.** What does the composite do if the first provider throws `OAuth2AuthorizationException`?

**Answer:** The error normally propagates per contract and the chain does not automatically try the next provider as a failover.

**Question 5.** Does adding `.refreshToken()` guarantee an access token can always be refreshed?

**Answer:** No. You need an existing authorized client, a valid refresh token, matching grant/policy, and acceptance by the Authorization Server.

**Question 6.** Why can't `client_credentials` be used to replace a user's token?

**Answer:** It represents the client/service and does not carry user authorization.

**Question 7.** When should `AuthorizedClientServiceOAuth2AuthorizedClientManager` be used?

**Answer:** When authorization is managed outside a Servlet request, such as scheduled jobs or backend services.

**Question 8.** Why are tokens still lost after restart even after changing the provider builder?

**Answer:** The builder does not control storage; check the authorized client repository/service.

**Question 9.** Which class should be customized to configure an HTTP proxy for refresh token requests?

**Answer:** The token response client / HTTP transport used by the refresh token provider, not `ClientRegistrationRepository`.

**Question 10.** What should a custom provider return when it does not support a registration?

**Answer:** `null`, so the composite can evaluate the next provider if designed that way.

**Question 11.** Can a single fixed principal name be used for all users in the service manager?

**Answer:** Not if tokens represent different users; doing so can lead to cross-account token sharing. With client credentials, a stable service principal may be appropriate if it truly represents one shared service authorization.

**Question 12.** What is clock skew used for?

**Answer:** Treating an access token as nearing expiration slightly early to reduce the risk of expiring mid-flight and to absorb small clock drift.

## 25. Key Takeaways

| Concept | What to Remember |
|---|---|
| **`OAuth2AuthorizedClientProvider`** | Strategy performing authorization/reauthorization based on context. |
| **`authorize(context)` returns authorized client** | Processing produced a result; the manager can persist it. |
| **`authorize(context)` returns `null`** | Provider does not apply or reauthorization is unnecessary. |
| **`authorize(context)` throws exception** | Error/situation requiring special handling; not a grant fallback. |
| **`DelegatingOAuth2AuthorizedClientProvider`** | Chains providers in order; stops at first non-null result or error. |
| **`OAuth2AuthorizedClientProviderBuilder`** | Creates an easily configured composite for selected grants. |
| **`authorizationCode()`** | Interacts with the authorization code flow, potentially needing a browser redirect. |
| **`refreshToken()`** | Reauthorizes via refresh token when present and needed. |
| **`clientCredentials()`** | Token for client/service, not representing a user. |
| **`DefaultOAuth2AuthorizedClientManager`** | Manager for Servlet web requests, using an authorized client repository. |
| **`AuthorizedClientServiceOAuth2AuthorizedClientManager`** | Manager for tasks outside Servlet requests, using an authorized client service. |
| **`OAuth2AuthorizedClientService` / Repository** | Determines how tokens are retrieved/stored; independent of the provider chain. |
| **Clock skew** | Buffer window when determining whether an access token is about to expire. |
| **Refresh token rotation** | Requires saving the new token and managing concurrency across nodes. |
| **Token response client** | Place to customize HTTP transport/parameters per grant. |
| **OIDC ID Token validation** | Belongs to the separate OIDC authentication flow, not a builder provider. |

**Conclusion:** `OAuth2AuthorizedClientProvider` is the **strategy** layer that `OAuth2AuthorizedClientManager` uses to issue or reissue authorized clients as needed. `OAuth2AuthorizedClientProviderBuilder` builds a chain of providers such as `authorizationCode`, `refreshToken`, and `clientCredentials`; that chain **is not an arbitrary failover between grants**. Properly understanding `null`, non-null, exceptions, provider order, and principal context keeps token management safe and clear. Choose the provider chain according to the authorizations genuinely permitted, choose the manager according to HTTP/background context, and configure storage and token response clients independently per operational requirements.

## References

- [Spring Security — OAuth2 Client Authorized Clients (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): authorized client manager, providers, service, and repository.
- [Spring Security — OAuth2 Client Authorization Grants (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): grants and token response client customization.
- [Spring Security API — OAuth2AuthorizedClientProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProvider.html): contract of `authorize(...)`.
- [Spring Security API — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html): configuring the provider chain.
- [Spring Security API — DefaultOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html): managing OAuth2 clients in Servlet requests.
- [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): managing clients outside HTTP requests.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): corresponding reactive managers and providers.
