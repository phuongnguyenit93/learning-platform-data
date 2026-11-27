# 17.3. `RefreshTokenOAuth2AuthorizedClientProvider` in Servlet

## 1. Problem Statement: Access Tokens Expire, but Users Should Not Log In Repeatedly

A **Spring Security OAuth 2.0/OIDC Client** application typically receives an access token after a user completes **Authorization Code** or **OIDC Login**. Access tokens have a limited lifetime; when the backend needs to call a Resource Server after some time has passed, the initial access token may already be expired.

If the Authorization Server also issued a **refresh token**, the OAuth2 Client can use that refresh token to request a new access token at the **Token Endpoint** without sending the browser back to the Authorization Endpoint on every API usage.

In the **Servlet/non-reactive** stack of Spring Security, the component responsible for executing this refresh grant is:

```java
org.springframework.security.oauth2.client.RefreshTokenOAuth2AuthorizedClientProvider
```

The class name is long, yet straightforward to break down:

- **`RefreshToken`**: handles the **OAuth 2.0 Refresh Token Grant** (`grant_type=refresh_token`).
- **`OAuth2AuthorizedClient`**: operates on an existing authorized client containing the `ClientRegistration`, access token, and refresh token if issued.
- **`Provider`**: a strategy invoked by `OAuth2AuthorizedClientManager` when authorization needs to be granted or renewed.

**Key takeaway:** `RefreshTokenOAuth2AuthorizedClientProvider` **does not create refresh tokens on its own** for a client. It can only refresh when an `OAuth2AuthorizedClient` already holds a valid refresh token, the current token needs renewal, and the Token Endpoint accepts the refresh request.

### 1.1. Learning objectives

After this lesson, you should understand:

1. At which step the manager invokes the provider and when it returns `null`.
2. The relationship between `ClientRegistration`, `OAuth2AuthorizedClient`, `OAuth2AuthorizedClientService`/`Repository`, and the provider.
3. How to enable `refreshToken()` in `OAuth2AuthorizedClientProviderBuilder`.
4. How to use `DefaultOAuth2AuthorizedClientManager` in an HTTP Servlet request, and when to use a manager for background jobs.
5. How a refresh token is sent to the Token Endpoint and how the updated authorized client is persisted.
6. The effects of `clockSkew`, expiry, refresh token rotation, logout, and concurrency.
7. How to diagnose `invalid_grant`, missing refresh tokens, incorrect client authentication, and post-refresh API errors.
8. Differences from the reactive/WebFlux API.

### 1.2. Scope boundaries

This lesson focuses on **OAuth2 Client with Servlet**. It does not cover implementing an Authorization Server that issues refresh tokens, renewing login sessions via `JSESSIONID`, or automatically refreshing arbitrary JWTs received by a Resource Server.

In a system using `client_credentials`, access tokens are normally reissued via the **`client_credentials` grant**, not via a refresh token. Therefore, do not add `refreshToken()` expecting every registration to have a refresh token.

## 2. Distinguishing Access Tokens, Refresh Tokens, ID Tokens, and Web Sessions

| Component | What is it used for? | Typically used by | Lifetime and storage |
| --- | --- | --- | --- |
| **Access token** | Presented to a Resource Server to call APIs | Sent by OAuth2 Client; verified by Resource Server | Usually short-lived; held in `OAuth2AuthorizedClient` |
| **Refresh token** | Requests a new access token from the Token Endpoint | OAuth2 Client and Authorization Server | Usually longer-lived than access tokens; sensitive credential |
| **ID Token (OIDC)** | Conveys authentication identity details to the client | OIDC Client | Verified per OIDC; **not** a refresh token |
| **Web session** | Maintains browser authentication in the web app | Browser and Spring Security app | Governed by session policy; can outlive or expire before tokens |
| **Authorization code** | Exchanged for tokens after the Authorization Code callback | OAuth2 Client and Token Endpoint | Single-use, short-lived; not used for subsequent refreshes |
| **`OAuth2AuthorizedClient`** | Bundles registration and issued tokens for a principal | Spring Security OAuth2 Client | Persisted by service/repository per policy |

A user may still access the website because **the session cookie is still valid** even while the access token for calling an API has expired. Conversely, an access token may still be valid after the application session has logged out.

**The refresh token grant is solely about obtaining new tokens**; it does not guarantee the user still has an active session, does not automatically update business permissions, and does not automatically mint a new `OidcUser`/ID Token.

## 3. Refresh Lifecycle in an OAuth2/OIDC Login Flow

Suppose a user has signed in with OIDC:

```text
Client registration: corporate
Principal name:     user-123
Access token A:     expiresAt = 10:30
Refresh token R1:   issued by Authorization Server
```

At 10:15, the backend calls an API and the manager returns access token A because it is still considered usable per policy.

When the backend calls the API near or past expiration, the manager calls the refresh provider to send:

```http
POST /oauth2/token HTTP/1.1
Host: idp.example.com
Authorization: Basic <client-authentication-if-required>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<R1>
```

Upon success, the Authorization Server returns access token B; it may return a new refresh token R2, or omit a new refresh token depending on policy. Spring Security constructs a new `OAuth2AuthorizedClient`, and the manager **persists** it via the authorized-client repository/service.

Diagram:

```mermaid
sequenceDiagram
    autonumber
    participant API as Spring MVC Service / Gateway
    participant M as DefaultOAuth2AuthorizedClientManager
    participant S as OAuth2AuthorizedClientRepository
    participant P as RefreshTokenOAuth2AuthorizedClientProvider
    participant AS as Authorization Server
    participant RS as Resource Server

    API->>M: authorize(registration=corporate, principal=user-123)
    M->>S: load(corporate, user-123, request)
    S-->>M: AuthorizedClient(access A, refresh R1)
    M->>P: authorize(context with authorized client)
    alt Access A does not need refresh yet
        P-->>M: null - no token replacement needed
        M-->>API: Current AuthorizedClient
    else Access A has reached refresh threshold
        P->>AS: POST /token grant_type=refresh_token, refresh_token=R1
        AS->>AS: Authenticate client and verify refresh token
        AS-->>P: access token B; optionally refresh token R2
        P-->>M: New AuthorizedClient
        M->>S: save(corporate, user-123, B, R2 or R1 per response)
        M-->>API: New AuthorizedClient
    end
    API->>RS: Current Bearer access token
    RS-->>API: Result or 401/403 error
```

The diagram shows logical responsibilities. The exact order of providers in the chain, how the manager saves, success/failure handlers, and renewal timing depend on Spring Security configuration and version.

### 3.1. What if there is no refresh token?

If the authorized client has no refresh token, `RefreshTokenOAuth2AuthorizedClientProvider` **cannot execute the refresh token grant**. In that case, the provider returns `null`, indicating re-authorization cannot be performed by this strategy.

Depending on the registration, manager, and provider chain, the application can:

- Use the current access token while it remains valid.
- Prompt the user to re-initiate Authorization Code / OIDC Login to get new tokens.
- For `client_credentials`, request a new access token using client credentials via the provider for that grant.
- Return an appropriate API/user-facing error if no token can be obtained.

**Never fabricate a refresh token from an access token, never use an ID Token as a refresh token, and never assume `scope=offline_access` always causes a provider to issue a refresh token.**

## 4. The `OAuth2AuthorizedClientProvider` Contract

`RefreshTokenOAuth2AuthorizedClientProvider` implements the interface:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider
```

Central method:

```java
OAuth2AuthorizedClient authorize(
    OAuth2AuthorizationContext context);
```

`OAuth2AuthorizationContext` supplies the necessary inputs, such as:

- The selected `ClientRegistration`.
- The `Authentication`/principal associated with the authorized client.
- The current `OAuth2AuthorizedClient` if previously authorized.
- Relevant attributes placed into the context by the manager/application.

For the refresh token provider, the conceptual logic is:

```text
authorize(context):
    current = context.authorizedClient

    if current does not exist:
        return null

    refresh = current.refreshToken
    if refresh does not exist:
        return null

    access = current.accessToken
    if access has not reached refresh threshold:
        return null

    send Refresh Token Grant Request to Token Endpoint
    if successful:
        return new OAuth2AuthorizedClient with new tokens
    if failed:
        throw corresponding OAuth2 authorization error
```

This is **explanatory pseudocode**, not verbatim Spring Security source code. Exact rules for considering a token "expired", clock skew, and validation depend on version and configuration.

### 4.1. What it means when `authorize(...)` returns `null`

A very common misunderstanding: `null` from a **provider** does not necessarily mean the entire API call failed.

In the provider chain architecture, `null` can mean:

- The current provider **does not support/apply** to this context.
- The access token **does not need refreshing yet**.
- The authorized client has no refresh token.

The manager can keep the existing authorized client or try another provider in the chain according to its rules.

Therefore, to know whether a refresh actually occurred, observe **the token request**, sanitized token/expiry metadata, and the success handler—never infer it merely from a provider returning `null`.

### 4.2. When does this class make an HTTP request?

The provider only makes a token request when the manager gives it sufficient context and refresh conditions are met. It **does not run a background timer** and does not continuously scan tokens in the store.

Example:

```text
10:00 Token A issued, expiresAt=10:30.
10:20 No code calls authorizedClientManager.authorize(...).
10:31 Token A has expired, but the provider does not "wake up" by itself.
10:35 authorize(...) is called, giving refresh a chance to happen.
```

If the system needs proactive scheduled refreshes, that is a **separate workflow** that must call the appropriate manager, with retry and concurrency policies, without requiring the user to keep a browser open.

## 5. Related Classes in Servlet

| Component | Role | Persists tokens itself? |
| --- | --- | --- |
| `ClientRegistrationRepository` | Looks up client config by registration ID | No |
| `OAuth2AuthorizedClient` | Holds access token and refresh token (if present) | Data object |
| `OAuth2AuthorizedClientRepository` | Loads/saves/removes authorized clients by Servlet request/response and principal | Yes |
| `OAuth2AuthorizedClientService` | Loads/saves/removes by registration ID/principal, independent of Servlet request | Yes |
| `DefaultOAuth2AuthorizedClientManager` | Coordinates authorization inside **HTTP Servlet requests** | Uses repository |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Coordinates authorization outside HTTP Servlet requests | Uses service |
| `OAuth2AuthorizedClientProvider` | Strategy for issuing/reissuing tokens | Not a store itself |
| `RefreshTokenOAuth2AuthorizedClientProvider` | Executes the Refresh Token Grant | No |
| `OAuth2AuthorizedClientProviderBuilder` | Builds/delegates a chain of grant providers | No |
| `OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>` | Executes the HTTP Token Request and parses the response | Not a store |

Notably, **`AuthorizationRequestRepository`** is a separate repository holding `OAuth2AuthorizationRequest` with `state`/PKCE prior to the callback. It is not the authorized client store after tokens are obtained.

### 5.1. Why go through the manager?

If business services called the provider directly everywhere, the application would have to manually manage:

- Which registration and principal are in use?
- Where to load the existing authorized client from?
- When the provider returns `null`?
- Who writes the new tokens back to storage?
- On `invalid_grant`, who removes the unusable entry?
- Who handles other grants, such as authorization code or client credentials?

`OAuth2AuthorizedClientManager` is the right abstraction because it wires the provider to the repository/service and success/failure handling. An individual provider is only **one strategy**.

## 6. Configuring Spring Boot for OIDC Login Capable of Receiving Refresh Tokens

### 6.1. Dependencies

Gradle example for a Spring MVC application:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

### 6.2. `application.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - offline_access

        provider:
          company-oidc:
            issuer-uri: https://idp.example.com/realms/employees
```

**Notes on `offline_access`:**

- This is the OIDC scope related to offline access, yet **it does not guarantee** every provider will issue a refresh token just because this scope is present.
- The IdP may require consent, a specific policy, an eligible client type, or additional login parameters.
- Some providers issue refresh tokens for Authorization Code even without requesting `offline_access`, depending on their contract.
- Some providers restrict refresh tokens by client, device, session, tenant, idle timeout, or absolute lifetime.
- Never blindly copy `prompt=consent`, `access_type=offline`, or vendor-specific parameters from one provider to another.

**Never store real client secrets in Git.** Variables like `${CORPORATE_CLIENT_ID}`/`${CORPORATE_CLIENT_SECRET}` should come from environment configuration or a secret manager.

### 6.3. Minimal `SecurityFilterChain`

```java
@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
```

With proper configuration, Spring Security handles Authorization Code/OIDC Login, verifies the ID Token, and manages the authorized client through the appropriate components. **You do not need to write a custom callback controller just to capture the refresh token.**

You should understand whether the provider actually issues a refresh token and which repository/service stores the authorized client.

## 7. Enabling the Refresh Token Provider in the Servlet Manager

### 7.1. Common configuration: `OAuth2AuthorizedClientProviderBuilder`

A `DefaultOAuth2AuthorizedClientManager` can receive a chain consisting of `authorizationCode()` and `refreshToken()`:

```java
@Configuration
class OAuth2ClientManagerConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        var manager = new DefaultOAuth2AuthorizedClientManager(
            registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Classes used in the example belong to Spring Security; `@Bean` and `@Configuration` belong to Spring Framework. Imports are omitted to focus on the structure.

Here:

- `authorizationCode()` handles the Authorization Code grant when applicable.
- `refreshToken()` adds the `RefreshTokenOAuth2AuthorizedClientProvider` strategy.
- `DefaultOAuth2AuthorizedClientManager` works with HTTP Servlet requests and `OAuth2AuthorizedClientRepository`.
- The manager connects **loading the existing authorized client**, **invoking the provider**, **saving new tokens**, and running configured success/failure handling.

**Do not enable `clientCredentials()` if the app only uses interactive OIDC Login.** If the same backend also has machine-to-machine registrations, build provider chains/managers for each context with the right grant and storage.

### 7.2. Do you always need to register the provider manually?

Spring Boot/Spring Security auto-configuration can provide a suitable manager/provider for common use cases. **Do not define a duplicate manager bean just to "turn on refresh" without first checking which bean the system is already using.**

When you need to customize clock skew, the token response client, or success/failure handlers, configure an explicit manager at the point of use and verify that your HTTP client/controller actually invokes that manager.

### 7.3. Using `@RegisteredOAuth2AuthorizedClient` in a Controller

Spring Security provides an annotation to resolve an authorized client in an MVC handler:

```java
@RestController
class ReportsController {

    @GetMapping("/reports/token-status")
    Map<String, Object> tokenStatus(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient client) {

        OAuth2AccessToken accessToken = client.getAccessToken();

        return Map.of(
            "registrationId",
                client.getClientRegistration().getRegistrationId(),
            "expiresAt",
                accessToken.getExpiresAt() == null
                    ? "unknown"
                    : accessToken.getExpiresAt().toString()
        );
    }
}
```

The annotation is `org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient`. Depending on configuration, the resolver/manager may return the existing authorized client or re-authorize through the provider chain.

The example returns only **metadata**, never token values. Similar endpoints must be properly access-controlled. In addition, the annotation operates in an HTTP request context; for background jobs, use a service-based manager rather than expecting an MVC method argument.

### 7.4. Calling the manager explicitly in an HTTP Servlet request

Example of a service invoked from a controller with an authenticated user:

```java
@Service
class CorporateApiClient {

    private final OAuth2AuthorizedClientManager manager;
    private final RestClient api;

    CorporateApiClient(
            OAuth2AuthorizedClientManager manager,
            RestClient.Builder builder) {

        this.manager = manager;
        this.api = builder
            .baseUrl("https://hr-api.example.com")
            .build();
    }

    String currentProfile(Authentication authentication) {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("corporate")
                .principal(authentication)
                .build();

        OAuth2AuthorizedClient authorizedClient =
            manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "OAuth2 authorization unavailable");
        }

        return api.get()
            .uri("/api/profile")
            .headers(headers -> headers.setBearerAuth(
                authorizedClient.getAccessToken().getTokenValue()))
            .retrieve()
            .body(String.class);
    }
}
```

This illustrates a service called **within an authenticated HTTP Servlet request**, where `DefaultOAuth2AuthorizedClientManager` can use the appropriate request/response context. If called from a thread/task without a Servlet request, pass context per the manager contract or use a **service-based manager**.

Use a **fixed, trusted base URL** for the target API; never accept an arbitrary URL from input and attach an access token to it, which risks leaking tokens via redirects or SSRF.

`RestClient` is available in Spring Framework 6.1+. On earlier versions, you can use `WebClient` or another appropriate HTTP client following the same principles.

## 8. Configuring `RefreshTokenOAuth2AuthorizedClientProvider` Directly

Sometimes you need to adjust clock skew or pass a custom token response client. In that case, instantiate the provider directly:

```java
RefreshTokenOAuth2AuthorizedClientProvider refreshProvider =
    new RefreshTokenOAuth2AuthorizedClientProvider();

refreshProvider.setClock(Clock.systemUTC());
refreshProvider.setClockSkew(Duration.ofSeconds(90));
```

Supported configuration APIs depend on the Spring Security version, so check your project's library version when upgrading. In common Servlet versions, the provider allows configuring clock/clock skew and the HTTP token response client.

### 8.1. Wiring the provider directly into a chain

If you need both `authorization_code` and a custom refresh provider:

```java
OAuth2AuthorizedClientProvider provider =
    new DelegatingOAuth2AuthorizedClientProvider(
        new AuthorizationCodeOAuth2AuthorizedClientProvider(),
        refreshProvider
    );

DefaultOAuth2AuthorizedClientManager manager =
    new DefaultOAuth2AuthorizedClientManager(
        clientRegistrations, authorizedClientRepository);

manager.setAuthorizedClientProvider(provider);
```

This example assumes `clientRegistrations` and `authorizedClientRepository` are properly injected; its goal is to show that **the refresh provider does not need to stand alone**. Using the builder when deep customization is unnecessary is usually simpler and easier to maintain.

Another configuration option is using customizers on `OAuth2AuthorizedClientProviderBuilder` if your Spring Security version exposes that API; verify method names rather than copying blindly across versions.

### 8.2. What do `Clock` and `clockSkew` do?

An access token has an `expiresAt` timestamp. If a token only has a few seconds left while the backend makes multi-hop API calls, it might expire before the Resource Server receives the request. Therefore, the provider can **treat the token as due for renewal earlier than its actual expiration**.

Example:

```text
Access token expiresAt: 10:30:00
clockSkew:             90 seconds

10:28:00 -> not yet at refresh threshold
10:28:30 -> begins treating token as needing refresh per safety margin
10:30:00 -> token actually expires per expiresAt
```

This is a simplified model of the time comparison. The `90 seconds` value is only a **design example**, not a mandatory default across all versions.

Choosing `clockSkew` should consider:

- Are system clocks synchronized across hosts?
- Average and p99 latency when calling the Resource Server.
- Minimum lifetime/characteristics of access tokens issued by the provider.
- API call frequency and unnecessary refresh rate.
- Token Endpoint processing time and retries.

**Do not set clock skew too large relative to the token lifetime**, as that can cause unnecessarily frequent token requests. And clock skew cannot fix systems whose clocks drift by minutes or tokens revoked by the provider.

### 8.3. `OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>`

The provider uses a dedicated HTTP client to build the **Refresh Token Grant Request** and parse the token response:

```java
OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
```

Illustrative configuration structure:

```java
RefreshTokenOAuth2AuthorizedClientProvider provider =
    new RefreshTokenOAuth2AuthorizedClientProvider();

provider.setAccessTokenResponseClient(customRefreshTokenResponseClient);
```

Here `customRefreshTokenResponseClient` is an implementation **supplied and configured separately**, not a default bean created by the snippet above.

You may need a custom response client when:

- The Token Endpoint sits behind a proxy requiring custom SSL context or timeouts.
- The provider documents extended form parameters.
- The system uses advanced client authentication such as mTLS or private-key JWT.
- The token response has compatibility quirks that must be handled via supported APIs.

Implementations and extension APIs of Token Response Client can change across Spring Security versions (for example, between clients using `RestOperations` vs. `RestClient`). **Never replace the HTTP client with a manual `POST` if doing so bypasses client authentication, OAuth2 error handling, or refresh token update logic.**

## 9. HTTP Refresh Token Request Contents

At the protocol level, the Token Endpoint typically receives:

```http
POST /oauth2/token HTTP/1.1
Host: idp.example.com
Authorization: Basic <client-credentials-if-required>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=refresh_token&refresh_token=<refresh-token-value>
```

If provider policy permits requesting a narrower scope, the token request may include an appropriate `scope`. Per OAuth2, the refresh grant is not a way to **expand permissions** beyond the original grant.

Illustrative successful token response:

```json
{
  "access_token": "REDACTED_ACCESS_TOKEN_B",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "reports.read",
  "refresh_token": "REDACTED_REFRESH_TOKEN_R2"
}
```

Another provider may not issue a new `refresh_token` in the response. How the client preserves the old refresh token or replaces it with a new one must follow the contract/library and **never discard a still-valid refresh token** when the response omits that field.

**An ID Token is not mandatory in a Refresh Token Grant** as it is in an OIDC Authorization Code token response. OIDC has specific rules for when the Token Endpoint returns an ID Token on refresh; do not assume refreshing the access token automatically updates `OidcUser` or the full `Authentication` in the session.

### 9.1. Client authentication still matters on refresh

If the original client registration uses a confidential client (`client_secret_basic`, `client_secret_post`, private-key JWT, mTLS, etc.), the Token Endpoint may require **re-authenticating the client** when using a refresh token.

An `invalid_client` error during refresh can be caused by:

- The client secret rotated without updating the application.
- The authentication method does not match the registration.
- `ClientRegistration` points to the wrong realm/tenant/token endpoint.
- The client's certificate/key is no longer valid.

Do not "fix" this by removing client authentication or passing the refresh token via a browser URL. Refresh tokens must be sent over **back-channel HTTPS** from the backend to the Token Endpoint.

### 9.2. Do new scopes appear automatically?

If the application just changed YAML from `scope: reports.read` to `scope: reports.read, reports.admin`, refreshing with the old refresh token **does not guarantee** the provider will also grant `reports.admin`.

Initially granted scopes, consent, and Authorization Server policy bound the grant. When new permissions are needed, the application may have to initiate a new Authorization Code/consent flow or register the new permissions at the provider.

## 10. Where Are Refresh Tokens and Authorized Clients Stored?

### 10.1. Per HTTP request: `OAuth2AuthorizedClientRepository`

In a Servlet web app, `DefaultOAuth2AuthorizedClientManager` uses `OAuth2AuthorizedClientRepository` to load/save/remove authorized clients within the request/response context.

An implementation can delegate to an `OAuth2AuthorizedClientService` underneath. Specifically, `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` typically delegates saving authorized clients for authenticated principals to a service, while optionally using a session repository in other contexts.

Therefore, when a refresh fails to find a saved token, check **which repository is actually in use**, rather than looking only at an arbitrary service bean.

### 10.2. For background tasks: `OAuth2AuthorizedClientService`

A background task without an `HttpServletRequest` should typically use:

```java
AuthorizedClientServiceOAuth2AuthorizedClientManager
```

Example:

```java
@Configuration
class BackgroundOAuth2ClientConfig {

    @Bean
    OAuth2AuthorizedClientManager backgroundAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Here:

- `refreshToken()` serves **authorized clients that already have a refresh token**.
- `clientCredentials()` serves `client_credentials` registrations per policy.
- **Browser-initiated Authorization Code/Login cannot run automatically from a background job**; if a user-specific authorized client is missing or its refresh token is no longer usable, the job cannot perform a browser login on the user's behalf.

A background job using a user's refresh token also raises consent, lifetime, storage, and revocation concerns. Never use long-lived user refresh tokens for batch jobs when service-to-service `client_credentials` meets the business requirement.

### 10.3. RAM, session, JDBC, and shared stores

| Storage | Benefits | Limitations / risks |
| --- | --- | --- |
| In-memory authorized-client service | Simple, fast | Lost on restart, not shared across pods, no built-in TTL |
| HTTP session repository | Bound to browser session | Session expiry/logout, multiple instances need session management |
| JDBC authorized-client service | Persistent, shareable when configured properly | Requires schema, security, transactions, cleanup |
| Custom Redis/database | Can add TTL, indexing, and concurrency control | Must preserve token/refresh token integrity, binding, and atomic updates |

**A refresh token is a sensitive credential.** When storing it in a database or Redis, protect it with TLS, least-privilege access control, encryption when required by policy, and explicit retention/cleanup.

**Never log raw refresh tokens.** Never send them to the frontend merely for "convenient refreshing" when the backend architecture holds the tokens.

## 11. Refresh Token Rotation: Why Concurrency Matters So Much

Many Authorization Servers use **refresh token rotation**. After the client uses R1, the server can issue R2 and invalidate R1.

Example:

```text
Time T0:
  access = A1
  refresh = R1

Request X:
  refresh with R1
  -> receives A2 + R2
  -> saves A2/R2

Request Y:
  nearly simultaneously also refreshes with R1
  -> may receive invalid_grant
```

Some servers implement **refresh token reuse detection**: reusing R1 can trigger revocation of the entire associated token family. Exact policies depend on the provider.

### 11.1. Race conditions to consider

- Two HTTP requests both see the access token nearing expiration.
- Two pods both read the stale authorized client record from a shared store.
- Both call the Token Endpoint using the same refresh token.
- A successful response with R2 is overwritten by a slow write containing R1.
- A failure handler deletes an entry that another request just refreshed successfully.
- One request reads the token right before logout/revocation, then writes the entry back after the logout event.

**`InMemoryOAuth2AuthorizedClientService` may have thread-safe map operations, yet it does not guarantee refresh token rotation runs only once across a cluster.**

### 11.2. Ways to handle it

Depending on your system, consider:

1. **Single-flight** per `(registrationId, principalName)` within a process.
2. **Distributed lock/CAS/version** when multiple processes share a refresh token.
3. **Atomic update** to write new tokens only if the record version matches what was read.
4. **Conditional failure handling**, avoiding deleting newly succeeded data due to a parallel refresh failure.
5. **Bounded timeout/backoff** for network errors; never retry infinitely on `invalid_grant`.
6. **Limiting parallel API calls** right as a token nears expiry if the provider is strict about rotation.
7. **Monitoring refresh failures and reuse detection** from the IdP to improve architecture.

Do not assume every application must hand-roll a distributed lock. First understand the concurrency behavior of your manager, provider, storage, and IdP; add only the coordination level needed.

## 12. Common Refresh Errors

### 12.1. `invalid_grant` at the Token Endpoint

Example:

```json
{
  "error": "invalid_grant"
}
```

Possible causes:

- The refresh token expired.
- The refresh token was revoked when the user logged out or revoked consent.
- The token was already used and invalidated by rotation.
- The refresh token belongs to a different client.
- IdP policy requires reauthentication.
- The request sent the wrong refresh token or wrong client context.

**Do not treat `invalid_grant` as a transient network error and retry endlessly with the same token.** The manager can be configured with a failure handler that removes the invalid authorized client; for user-specific Authorization Code flows, the app may need to send the user through a new login/consent flow.

### 12.2. `invalid_client`

Usually involves client authentication at the Token Endpoint: wrong/expired secret, mismatched client authentication method, or invalid client certificate/JWT assertion.

The fix is to correct the client/secret configuration—not to mint a new refresh token or disable TLS.

### 12.3. Provider returns success, yet the API still returns 401/403

Distinguish between:

- **401 at the Token Endpoint:** client authentication or token grant issue.
- **401 at the Resource Server:** wrong/expired/revoked token, or rejected audience or signature.
- **403 at the Resource Server:** the token may be authentic, yet lacks required scopes, roles, or policy permissions.

Refreshing an access token **does not automatically grant extra API permissions** if the provider did not issue new scopes or audiences.

### 12.4. Refresh token vanishes after restart or pod swap

If the authorized client lived only in **one JVM's RAM**, a new pod will not have the previous record. The web session might still survive via a shared session store, yet the token store does not automatically become shared if it uses an in-memory service.

Inspect the actual repository/service wiring and persistence requirements. Move to JDBC or a custom shared store if refresh tokens must survive deployments.

## 13. Observing the Lifecycle Safely

Some metadata safe to track:

```text
registrationId=corporate
principalRef=<internal-correlation-id>
grantAttempt=refresh_token
accessTokenExpiresAt=...
refreshAttemptStartedAt=...
refreshOutcome=success
```

Never log:

```text
refresh_token=...
access_token=...
Authorization: Basic ...
client_secret=...
Cookie: JSESSIONID=...
```

In multi-tenant systems, avoid putting full user IDs, raw tokens, emails, or sensitive `principalName` values into high-cardinality metric labels.

Useful operational signals:

| Metric / event | Meaning |
| --- | --- |
| `oauth2_refresh_attempt` | Number of times the manager actually invoked the refresh grant |
| `oauth2_refresh_success` | Valid token response received |
| `oauth2_refresh_failure{error=invalid_grant}` | Refresh token expired/rotated/revoked |
| `oauth2_refresh_failure{error=invalid_client}` | Incorrect client configuration/authentication |
| `oauth2_token_endpoint_latency` | Token Endpoint latency |
| `oauth2_authorized_client_missing` | Stored record not found |
| `oauth2_access_token_expiry_remaining` | Remaining time before refresh is needed |
| `oauth2_api_401` / `oauth2_api_403` | Resource Server rejected the request after sending the token |

These are **suggested event names**, not built-in metrics guaranteed to be emitted by Spring Security.

## 14. Time, Session, and Refresh Pitfalls

### 14.1. Clock skew is not token lifetime

The provider uses `accessToken.getExpiresAt()` with clock skew to avoid sending an access token right as it expires. Clock skew does not make an expired token valid and does not extend a refresh token's lifetime.

If backend hosts have severe clock drift, synchronize system clocks. Never inflate clock skew arbitrarily to mask NTP issues.

### 14.2. User session expiration

In a web app, a user can be logged out due to session timeout while the authorized-client store still retains a refresh token. That **does not automatically mean** the user is allowed to continue performing operations that require an authenticated session.

Separate the two policies:

- **Web authentication session**: whether the browser is still allowed to access the website.
- **OAuth2 token authorization**: whether a new access token can be obtained to call APIs.

A still-valid refresh token is not a reason to automatically log a browser back in without going through the application's session/reauthentication policy.

### 14.3. Logout and revocation

| Action | Consequence |
| --- | --- |
| Clear SecurityContext/session | Browser no longer has an authenticated session per config |
| `removeAuthorizedClient` | Deletes local token record by registration/principal |
| Refresh Token Revocation Endpoint | Authorization Server receives request to revoke refresh token per policy |
| OIDC RP-Initiated Logout | Handles SSO session at the IdP; does not by default revoke all tokens |
| Rotation R1 -> R2 | Advances the refresh token chain per provider policy |

Logging out of a session **does not guarantee** all authorized clients were deleted. Local removal **does not guarantee** the refresh token was revoked at the IdP. When strict security is required, design synchronized logout, revocation, and session invalidation per policy.

## 15. Customizing the Token Response Client: TLS and Proxy Notes

The Token Endpoint often sits inside an enterprise network or behind an egress proxy. Errors that can appear when the provider attempts a refresh:

| Symptom | Possible cause | Where to investigate |
| --- | --- | --- |
| `UnknownHostException` | Pod DNS cannot resolve Token Endpoint | Container DNS / service discovery |
| Connect timeout | Firewall, NAT, NetworkPolicy, proxy | Inspect egress routing |
| `PKIX path building failed` | JVM/HTTP client does not trust the CA | Truststore, certificate chain |
| Hostname verification failed | TLS certificate does not match hostname | SAN, SNI, proxy interception |
| HTTP 407 | Proxy requires authentication | Proxy credentials/policy |
| HTTP 429 | Token Endpoint rate limit | Throttling, backoff, token reuse |
| HTTP 503 | Provider temporarily unavailable | Bounded retry, circuit breaker, incident |
| Token response parse error | Received HTML/WAF page or malformed JSON | Actual URL and redacted HTTP response |

Know **which HTTP client `RefreshTokenOAuth2AuthorizedClientProvider` actually uses to call the Token Endpoint**, not just the `RestClient`/`WebClient` your application uses for API calls. Extension points for the token response client vary across Spring Security versions.

Never disable certificate validation to bypass TLS errors. Refresh tokens and client credentials are sensitive data requiring HTTPS.

## 16. Verifying Refresh Behavior: Useful Scenarios

The scenarios below illustrate provider and manager design. These are **learning scenarios**, not results from an executed test suite.

| Case | Current authorized client | Expected provider/manager outcome |
| --- | --- | --- |
| No authorized client | `null` | Refresh provider does not obtain a token via refresh grant |
| Access token present, no refresh token | Access token A only | Cannot use refresh token grant |
| Refresh token present, access token still valid | A has remaining validity | Does not refresh before threshold |
| Refresh token present, access token nearing expiry | A about to expire | Refreshes per clock skew |
| Token Endpoint issues access token B | A + R1 | Creates new authorized client with B |
| Token Endpoint returns new R2 | A + R1 | Saves new token per response; stops using R1 if rotated |
| Token Endpoint omits new refresh token | A + R1 | Applies library/provider logic to retain/interpret refresh token |
| Token Endpoint `invalid_grant` | A + invalid R1 | No infinite retry; handles error and policy cleanup |
| Token Endpoint timeout | A + R1 | Does not treat as successful refresh; handles network error per policy |
| Session lost while token store remains | Local refresh token exists | Does not bypass session authentication |
| Two requests refresh same R1 | Shared authorized client | Must consider concurrency/rotation |
| JVM restart with in-memory service | Record lost | Cannot refresh without refresh token |
| API returns 403 after refresh | B still exists | Inspect Resource Server scopes/permissions |

### 16.1. Example approach to testing with `Clock`

To test time thresholds reproducibly, configure the provider with a controllable clock:

```java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-11-16T02:00:00Z"),
    ZoneOffset.UTC);

var provider = new RefreshTokenOAuth2AuthorizedClientProvider();
provider.setClock(fixedClock);
provider.setClockSkew(Duration.ofSeconds(60));
```

This snippet only **sets the input time**. To test provider logic, construct an `OAuth2AuthorizationContext` holding an authorized client and a suitable test-double/mocked `OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>`, then assert whether a token request occurs as `expiresAt` changes.

Do not use `Thread.sleep(...)` for minutes just to wait for an access token to expire; using a controllable clock keeps tests fast and deterministic.

## 17. Practical Scenarios

### Scenario A — Access token expires while user still has a session

A user logged in via OIDC in the morning. In the afternoon the website still accepts `JSESSIONID`, yet the backend calls the Reports API with expired access token A.

**Resolution:** check whether the user's `OAuth2AuthorizedClient` has a refresh token; ensure the manager configures `refreshToken()`, uses the right repository, and invokes `authorize(...)` before sending the access token. Do not force a browser re-login if the refresh grant is valid and policy permits it.

### Scenario B — Manager does not refresh despite expired access token

Code calls `OAuth2AuthorizedClientService.loadAuthorizedClient(...)` and attaches the token directly to the HTTP header.

**Cause:** `loadAuthorizedClient` is just a read operation; it does not invoke any provider. Use a properly configured manager or OAuth2 HTTP client integration.

### Scenario C — `offline_access` is present, yet refresh token is null

The provider withheld a refresh token due to policy, consent, or client configuration.

**Resolution:** inspect the token response, allowed scopes/grants, provider documentation, and when consent is requested. `offline_access` does not guarantee issuance by itself. Never derive a refresh token from an ID Token.

### Scenario D — Two concurrent requests cause the refresh token to be revoked

The provider uses rotation; two requests refresh simultaneously using R1. One receives R2, while the other gets `invalid_grant`, potentially causing the failure handler to delete the newly saved token.

**Resolution:** analyze manager/storage concurrency and apply coordination/atomic updates if needed; never ignore `invalid_grant` or retry R1 endlessly.

### Scenario E — Pod restart loses the refresh token

The app stores authorized clients in RAM without persistent storage. After deployment, the login session may survive via a shared session store, while the authorized client is gone.

**Resolution:** identify the actual token store; if persistence is needed, use JDBC or a shared store and protect refresh tokens. Never expect an in-memory service to share state across pods.

### Scenario F — New token obtained, yet API still returns `403`

Refresh succeeds and access token B has a fresh expiry, yet the API reports missing `reports.admin`.

**Resolution:** inspect granted scopes and Resource Server policy. A refresh grant cannot expand permissions beyond the initial grant or self-approve an admin scope.

### Scenario G — Client secret rotated

The refresh request fails with `invalid_client` even though R1 has not expired.

**Resolution:** check the client authentication method, secret version, issuer/realm, and how the Token Response Client uses the new credential. Never assume every refresh failure means an expired refresh token.

### Scenario H — Wanting to refresh a `client_credentials` access token

A `client_credentials` backend registration has access token A and **no refresh token**; the developer only added `refreshToken()` to the provider chain.

**Resolution:** use `.clientCredentials()` with an appropriate manager to **obtain a new access token via client credentials**. This grant is distinct from `refresh_token`.

## 18. Misconceptions to Avoid

**"Having `RefreshTokenOAuth2AuthorizedClientProvider` means every access token is automatically refreshed on a schedule."** False. The provider is only called when the manager/app performs authorization; it has no internal scheduler.

**"The provider can extract a refresh token from the ID Token."** False. A refresh token is a separate credential issued by the Authorization Server per policy.

**"When the access token expires, `loadAuthorizedClient(...)` refreshes automatically."** False. Storage only loads the record.

**"Having `offline_access` guarantees receiving a refresh token."** False. The provider may require consent, policies, and specific settings.

**"`refreshToken()` also helps `client_credentials` get a new token."** Fundamentally incorrect. For `client_credentials`, you need the provider for that grant; refresh tokens are normally not issued.

**"Refresh returned 200, so the user's session automatically updates all permissions."** No. New tokens and Authentication/session/authorities can have separate lifecycles.

**"If the Token Endpoint returns `invalid_grant`, just keep retrying."** No. The refresh token may be expired, revoked, or rotated; retrying can make the incident worse.

**"A thread-safe map is enough to solve refresh token rotation across multiple pods."** No. Concurrency and atomic updates must be considered across both provider and store.

**"Deleting the local authorized client revokes the refresh token at the IdP."** No. You must use a proper revocation mechanism if policy requires it.

**"A new access token is guaranteed to have permission to call every API."** No. The Resource Server still verifies audience/scopes and business policies.

## 19. Review Questions

**1. What is `RefreshTokenOAuth2AuthorizedClientProvider` responsible for?**

It is the provider that executes the **Refresh Token Grant** when the authorized client already has a refresh token, the access token needs renewal, and the Token Endpoint accepts the request.

**2. Who normally invokes this provider?**

`OAuth2AuthorizedClientManager` via a configured provider chain, for example with `OAuth2AuthorizedClientProviderBuilder.builder().authorizationCode().refreshToken().build()`.

**3. Is returning `null` from the provider necessarily an error?**

No. The token may not need refreshing yet or may not meet the conditions for a refresh grant. The manager handles the result based on context and the chain.

**4. Why can't you refresh when `OAuth2AuthorizedClient.getRefreshToken()` is null?**

Because the refresh grant requires a refresh token previously issued by the Authorization Server; the provider cannot fabricate that credential.

**5. Does refreshing require a browser redirect or a new authorization code?**

No, when a valid refresh token is available. It is a **back-channel Token Request** to the Token Endpoint.

**6. What does `clockSkew` affect?**

It allows treating an access token as due for refresh **before** actual expiry, reducing the risk of the token expiring mid-flight during API calls.

**7. When is `DefaultOAuth2AuthorizedClientManager` appropriate?**

When using the OAuth2 Client inside **HTTP Servlet requests** together with `OAuth2AuthorizedClientRepository`.

**8. Which manager fits a background job wanting to use a saved authorized client's refresh token?**

`AuthorizedClientServiceOAuth2AuthorizedClientManager`, configured with an appropriate provider chain and `OAuth2AuthorizedClientService`.

**9. What error can refresh token rotation cause when two requests run in parallel?**

Both use R1; one receives R2 while the other may get `invalid_grant` and even trigger reuse-detection policies. Coordination and consistent token persistence must be considered.

**10. Why does deleting a local token not equal revoking it at the IdP?**

Because local storage and the Authorization Server are two separate systems; revocation requires a dedicated workflow/endpoint.

**11. Is a refresh token part of an OIDC ID Token?**

No. An ID Token proves identity authentication; a refresh token requests new access tokens at the Token Endpoint.

**12. Why might an API still return `403` after a successful refresh?**

Because the new access token may lack the scopes/roles/permissions required by the target API. Refreshing does not guarantee expanded permissions.

**13. If an app uses `client_credentials`, which provider must be enabled?**

`clientCredentials()` in the provider builder for that grant; do not rely on `refreshToken()` when no refresh token exists.

**14. Can a scheduled job rely on `@RegisteredOAuth2AuthorizedClient`?**

No. The annotation works with web handler argument resolution; out-of-request tasks should use an appropriate service-based manager API.

**15. When should persistent storage be chosen over in-memory?**

When refresh tokens must survive restarts/rolling deployments, be shared across multiple instances, or require policy-based coordination, auditing, cleanup, and revocation.

## 20. References

- [Spring Security Reference — OAuth 2.0 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — Authorized Clients (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Security API — `RefreshTokenOAuth2AuthorizedClientProvider`](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/RefreshTokenOAuth2AuthorizedClientProvider.html)
- [Spring Security API — `OAuth2AuthorizedClientProvider`](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProvider.html)
- [Spring Security API — `OAuth2AuthorizedClientProviderBuilder`](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html)
- [Spring Security API — `DefaultOAuth2AuthorizedClientManager`](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html)
- [Spring Security API — `AuthorizedClientServiceOAuth2AuthorizedClientManager`](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html)
- [Spring Security API — `OAuth2AuthorizedClient`](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html)
- [Spring Security Reference — OAuth 2.0 Client (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [RFC 6749 — Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — Refresh Token Flow](https://openid.net/specs/openid-connect-core-1_0.html#RefreshTokens)

**Remember:** `RefreshTokenOAuth2AuthorizedClientProvider` is **the Refresh Token Grant strategy in Spring Security Servlet**, not a timer or a token store. It only refreshes when the authorized client already holds a refresh token and the access token has reached the refresh threshold. The manager coordinates the provider and persists the authorized client after renewal; the repository/service holds the data, while the Authorization Server decides whether new tokens are issued. Protect refresh tokens, pick the right manager for requests vs. background tasks, handle `invalid_grant` and refresh token rotation carefully, and remember that **refreshing an access token does not replace OIDC Login, web sessions, or Resource Server authorization**.
