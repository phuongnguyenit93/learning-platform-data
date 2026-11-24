# OAuth2AuthorizedClient and the Access Token and Refresh Token Lifecycle

> **Scope:** OAuth2 Client on **Spring Security reactive / Spring WebFlux**, not to be confused with OAuth2 Resource Server. This lesson uses Java 17+, Spring Boot 3.x, and Spring Security 6.5.x APIs to explain `OAuth2AuthorizedClient`, issuing/refreshing tokens, storage, expiration timing, refresh-token rotation, handling `invalid_grant`, integrating `WebClient`, and testing without a real IdP.

## 1. Objectives

After completing this lesson, you will be able to:

1. Distinguish `ClientRegistration`, `OAuth2AuthorizedClient`, `Authentication`, `OAuth2AccessToken`, and `OAuth2RefreshToken`.
2. Describe the access token lifecycle from issuance, usage, near-expiration, and refresh/re-authorization through token revocation.
3. Explain why **a refresh token may not exist** and why not every grant uses a refresh token.
4. Configure `ReactiveOAuth2AuthorizedClientManager` with `authorizationCode()`, `refreshToken()`, or `clientCredentials()` depending on the flow.
5. Choose between `DefaultReactiveOAuth2AuthorizedClientManager` in HTTP requests and `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` for scheduled jobs.
6. Distinguish `ServerOAuth2AuthorizedClientRepository` from `ReactiveOAuth2AuthorizedClientService` and store tokens under the proper principal/registration.
7. Use `ServerOAuth2AuthorizedClientExchangeFilterFunction` with `WebClient` to attach the Bearer **access token** without accidentally sending tokens to other hosts.
8. Handle `invalid_grant` from the Token Endpoint and 401/403 errors from the Resource Server, including the WebClient failure handler.
9. Understand refresh token rotation, concurrent refresh, multi-pod persistence, logout, revocation, and information leakage.
10. Write `StepVerifier` tests proving that a valid token is reused, an expired token is refreshed and saved, a missing refresh token cannot be refreshed, and `invalid_grant` removes stale state.

## 2. What Is an Application Acting as an OAuth2 Client?

A WebFlux application acts as an **OAuth2 Client** when it wants to call a **Resource Server** using an access token issued by an **Authorization Server/Identity Provider (IdP)**.

Typical example: user `alice` logs into the web app, approves the `reports.read` scope, and the app calls a reports API using a Bearer access token bound to alice's account.

```text
Browser alice
   |
   | GET /reports/current
   v
Spring WebFlux + Spring Security OAuth2 Client
   |
   | If not yet authorized: authorization-code redirect
   v
Authorization Server / IdP
   |
   | Token Endpoint after login/consent:
   |   access token
   |   refresh token (depending on provider/policy)
   v
WebFlux saves OAuth2AuthorizedClient
   |
   | When calling reports API:
   |   load, check expiry, possibly refresh
   v
WebClient: Authorization: Bearer <ACCESS_TOKEN>
   |
   v
Resource Server: validates issuer/audience/scope/resource permissions
   |
   v
Report response
```

**A refresh token is strictly never a Bearer token sent to the reports API.** It is only used with the **IdP's Token Endpoint** to request a new access token. And tokens must never appear in browser URLs, frontend JSON, logs, or metrics.

### 2.1 OAuth2 Client vs. Resource Server

| Role | What Does It Do? | Spring Security Configuration |
| --- | --- | --- |
| OAuth2 Client | Obtains/stores tokens and attaches Bearer to outbound requests | `oauth2Client()`, reactive authorized-client manager |
| OAuth2 Login | Browser interaction, code redirect, establishes user login | `oauth2Login()` |
| Resource Server | Validates **inbound** Bearer tokens and authorities | `oauth2ResourceServer(...)` |
| Authorization Server | Issues codes/access/refresh tokens, provides authorize/token endpoints | A separate IdP/Authorization Server |

The same WebFlux app can act as both a Resource Server for inbound requests and an OAuth2 Client when calling downstream services. However, **having an OAuth2 client registration does not mean inbound tokens have their signatures verified**; the two responsibilities must be configured separately.

### 2.2 An ID Token Is Not an Access Token

With OpenID Connect, the IdP can return an **ID token** representing the login event and identity claims. The ID token has the client/Relying Party as its audience, whereas the **access token** is used to call the Resource Server. Do not send an ID token instead of a Bearer access token just because both look like JWTs. A refresh token, in turn, is a credential authorizing retrieval of a new access token, not proof of identity sent to a Resource Server.

## 3. What Does OAuth2AuthorizedClient Contain?

According to Spring Security, `OAuth2AuthorizedClient` binds together:

- A **`ClientRegistration`**: registration ID, client ID, grant type, auth/token URIs, scopes, client authentication method.
- **Principal name**: the authorized subject or service principal.
- An **`OAuth2AccessToken`**: token type, secret value, issuedAt/expiresAt, scopes.
- Optionally an **`OAuth2RefreshToken`**: secret value, issuedAt, and time metadata if provided.

An **explanatory-only** representation, not JSON that Spring Security returns directly:

```text
ClientRegistration:
  registrationId: reports
  clientId: server-side-report-client
  grantType: authorization_code
  tokenUri: https://idp.example.test/oauth2/token

OAuth2AuthorizedClient:
  registration: reports
  principalName: alice
  accessToken:
    type: Bearer
    value: <SECRET>
    issuedAt:  2026-01-01T10:00:00Z
    expiresAt: 2026-01-01T11:00:00Z
    scopes: [reports.read]
  refreshToken:
    value: <SECRET_IF_ISSUED>
    issuedAt: 2026-01-01T10:00:00Z
```

Token values are **credentials**, not information to debug by logging. `authorizedClient.getRefreshToken()` can be `null`: never call `getTokenValue()` without checking for null.

### 3.1 ClientRegistration Does Not Mean Already Authorized

A `ClientRegistration` exists right from application startup, even when no user has logged in or no token exists yet.

An `OAuth2AuthorizedClient` is only formed when authorized client state exists — for example, after a successful authorization-code exchange or after a client-credentials token request. Therefore:

```text
client registration != authorized client != authenticated user session
```

A user can be logged into the app without having granted authorization for reports; there can be multiple authorized clients for multiple registrations; a user can log out of the app while the token at the IdP remains valid. Conversely, a scheduled job has an authorized client without any browser session.

### 3.2 Access Token vs. Refresh Token Differences

| Criterion | Access token | Refresh token |
| --- | --- | --- |
| Target destination | Protected Resource Server | Authorization Server Token Endpoint |
| Purpose | Grants API access according to scope/audience/permissions | Requests a new access token according to grant/policy |
| Lifetime | Usually short | May be longer, or not issued at all |
| Sent in API requests | `Authorization: Bearer <access_token>` | **No** |
| Where stored | Server-side authorized-client repository/service | Server-side, must be strictly protected |
| When expired/revoked | API may return 401 | Refresh request may return `invalid_grant` |
| When stolen | Can call APIs within token limits | Can obtain additional access tokens if unblocked; high risk |

Do not assume a token is a JWT: many IdPs issue **opaque access tokens**, so let the Resource Server use appropriate JWT validation or introspection. Client-side `expiresAt` metadata assists with scheduling; it does not replace Resource Server validation.

## 4. Token Lifecycle in the authorization_code Flow

```text
No OAuth2AuthorizedClient yet for ("reports", "alice")
        |
        | 1. Browser starts OAuth2 authorization request
        | 2. IdP authenticates user and asks for consent (if needed)
        | 3. Authorization code redirects back to WebFlux
        | 4. Backend exchanges code at Token Endpoint
        v
Authorized Client { access A1, refresh R1 if issued }
        |
        | 5. WebClient uses access A1 to call Resource Server
        |
        +-- Access A1 still valid: reuse
        |
        +-- Access A1 near/past expiry:
              |
              +-- Has R1 and refreshToken() provider?
              |     |
              |     +-- Accepted by IdP:
              |     |      access A2
              |     |      refresh R2 if rotated
              |     |      save new Authorized Client
              |     |
              |     +-- invalid_grant:
              |            stale Authorized Client is removed
              |            authorization-code/consent needed again
              |
              +-- No refresh token:
                    appropriate re-authorization needed
```

**Automatic refresh is not guaranteed just because you declared an OAuth2 Client.** The manager must be used in the request, a refresh-token provider must be configured, the authorized client must hold a valid refresh token, the access token must require refreshing, and the IdP must accept it.

### 4.1 Expiration and Clock Skew Window

`OAuth2AccessToken` typically has `Instant getIssuedAt()` and `getExpiresAt()`. Waiting until right at `expiresAt` before sending a token can cause 401 errors because of network latency and clock differences between the app, IdP, and API.

`RefreshTokenReactiveOAuth2AuthorizedClientProvider` can configure clock skew via `setClockSkew(...)` or the builder. For example, if **60 seconds** is chosen:

```text
10:00:00 token issued, expiresAt = 11:00:00
10:58:30 token is far from threshold -> can be reused
10:59:10 token within 60s of expiry -> refresh provider can act
11:00:00 token expired according to expiresAt
```

This is an example **with the chosen skew**, not evidence that every system uses the same default threshold. Expiry tests should use `Instant` and sufficiently wide intervals, avoiding tests sensitive to milliseconds or machine time zones.

### 4.2 Why Might a Refresh Token Not Be Issued?

The behavior depends on the provider and policy: scopes, offline access, consent, client type, grant type, rotation/expiry, and the OAuth2 app's security settings.

- Authorization code **may** receive a refresh token, not guaranteed.
- Client credentials **usually do not** receive a refresh token; a new grant is needed when the access token expires.
- Public clients require PKCE and appropriate refresh-token rotation/replay protection policies.
- If there is no refresh token, never artificially "extend" `expiresAt` or send an expired access token as if it were valid.

### 4.3 Refresh-Token Rotation

The IdP may issue `R2` after `R1` is successfully used. Token `R1` may immediately become invalid. The client must persist the **new state** rather than keeping `R1` in the DB/cache and reusing it next time.

```json
{
  "access_token": "<REDACTED_NEW_ACCESS>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "reports.read",
  "refresh_token": "<REDACTED_ROTATED_REFRESH>"
}
```

This is only a response shape example, with no real tokens. If the IdP does not issue a new refresh token, handle it according to the provider's token response semantics; do not erase the old one if the policy allows keeping it.

## 5. Reactive OAuth2 Client Manager and Providers

### 5.1 ReactiveOAuth2AuthorizedClientManager

`ReactiveOAuth2AuthorizedClientManager` coordinates four responsibilities:

1. Look up the authorized client by registration + principal.
2. Decide whether (re-)authorization is needed based on provider/grant/expiry.
3. Save the updated authorized client via the repository/service and success handler.
4. Handle authorization failures, such as removing stale state when the IdP returns `invalid_grant`.

The manager itself uses `ReactiveOAuth2AuthorizedClientProvider` to execute grant logic. Do not hand-write a controller calling the Token Endpoint and storing token values via manual HTTP string concatenation when Spring Security already provides standard integration.

### 5.2 Composite Provider

Builder example:

```java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
```

This is a **snippet requiring Spring Security OAuth2 Client imports**. Each provider has a distinct role:

- `authorizationCode()`: browser redirect/authorization code flow.
- `refreshToken()`: obtains a new access token using a refresh token when conditions apply.
- `clientCredentials()`: requests an access token for the app/service; does not require a refresh token.
- Some older 6.x docs still mention `password()`; the Resource Owner Password Credentials grant is legacy/deprecated and is not a choice for new applications.

`Mono.empty()` from a provider can mean the provider **does not support the grant or does not need re-authorization** for that context. Do not interpret it as issuing an empty access token. The manager may return the existing authorized client; callers still need to watch expiry when there is no way to refresh.

### 5.3 Manager for WebFlux HTTP Requests

Use `DefaultReactiveOAuth2AuthorizedClientManager` with `ReactiveClientRegistrationRepository` and `ServerOAuth2AuthorizedClientRepository` inside a **ServerWebExchange**:

```java
var manager = new DefaultReactiveOAuth2AuthorizedClientManager(
    registrations, authorizedClientRepository
);
manager.setAuthorizedClientProvider(
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build()
);
```

This is a snippet. This manager is bound to web requests and uses the repository keyed by principal/exchange. The default authorization success handler saves the client; the default failure handler can remove state on error codes such as `invalid_grant`. When customizing handlers, ensure accurate storage and preserve stale-token cleanup.

### 5.4 Manager for Background Jobs / Service Tier

When there is no `ServerWebExchange` (scheduled task, message consumer, background processor), use:

```java
var manager =
    new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
        registrations, authorizedClientService
    );
manager.setAuthorizedClientProvider(
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build()
);
```

This is a snippet for a service identity, requiring a configured service and registration. Do not fabricate a fake web exchange just to reuse the controller's manager.

### 5.5 Which Manager to Choose?

| Context | Choice | State Store |
| --- | --- | --- |
| WebFlux controller calling API on behalf of logged-in user | `DefaultReactiveOAuth2AuthorizedClientManager` | `ServerOAuth2AuthorizedClientRepository` |
| WebClient in an HTTP exchange with a principal | Appropriate web manager | Repository bound to web exchange |
| Cron job requesting `client_credentials` token | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientService` |
| Message consumer with a service principal | Service manager | Shared authorized-client service if needed |
| Multiple replicas needing state across restarts | Manager + durable persistence | DB/shared store protecting credentials |

If you register **multiple managers of the same interface**, use bean names/`@Qualifier` so injection is unambiguous.

## 6. Storing OAuth2AuthorizedClient in the Right Place

### 6.1 ServerOAuth2AuthorizedClientRepository

The repository manages authorized clients within a web context, with operations:

```java
Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
    String registrationId,
    Authentication principal,
    ServerWebExchange exchange
);

Mono<Void> saveAuthorizedClient(
    OAuth2AuthorizedClient client,
    Authentication principal,
    ServerWebExchange exchange
);

Mono<Void> removeAuthorizedClient(
    String registrationId,
    Authentication principal,
    ServerWebExchange exchange
);
```

These are **illustrative signatures**, not the full Java interface file. Implementations may use WebSession or delegate to a service depending on the setup; do not assume every application persists to a database just because this interface exists.

### 6.2 ReactiveOAuth2AuthorizedClientService

The service operates at the application level and provides operations:

```java
Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
    String registrationId, String principalName
);

Mono<Void> saveAuthorizedClient(
    OAuth2AuthorizedClient client, Authentication principal
);

Mono<Void> removeAuthorizedClient(
    String registrationId, String principalName
);
```

`InMemoryReactiveOAuth2AuthorizedClientService` is useful for unit tests and demos; `R2dbcReactiveOAuth2AuthorizedClientService` supports R2DBC-backed storage when you provide the corresponding schema/database.

**Important:** An in-memory store is not shared across pods, loses tokens on restart, and struggles with rotation races. Production requires deciding on persistence, data encryption, session retention, backup/restore, and a concurrency strategy.

### 6.3 Storage Keys Must Isolate Principals

Example:

```text
("reports", "alice") -> access A / refresh RA
("reports", "bob")   -> access B / refresh RB
("mail",    "alice") -> access C / refresh RC
```

Never store a single global token keyed only by `registrationId` for a user-delegated flow. Users A and B may have different permissions, tenants, and consents. With multiple issuers/tenants, a stable identifier with a trusted issuer/tenant boundary is required; never take the principal name directly from a query parameter. For service `client_credentials`, an app-controlled principal such as `nightly-job` can be used to reuse the token.

## 7. Complete Spring Boot 3.x + WebFlux Configuration

User-delegated OAuth2 authorization code example: browser login with a simulated provider under the `example.test` domain; when a real IdP and corresponding registration are present, `WebClient` calls a fixed reports resource using the access token bound to the user.

**To run the application end-to-end**, a real IdP/Authorization Server, exact redirect URI, scopes, and a real Resource Server are mandatory. The `example.test` domains are not live services. However, the Java sources are standalone classes suited to a Boot/WebFlux/Security project with the dependencies; the offline manager tests in section 9 **do not require an IdP**.

### 7.1 Gradle

`build.gradle` in a Spring Boot project generated by Spring Initializr already includes plugins and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Choose the WebFlux stack properly; `HttpSecurity` and Servlet `OAuth2AuthorizedClientManager` do **not** replace `ServerHttpSecurity` and `ReactiveOAuth2AuthorizedClientManager`. When both the MVC starter and WebFlux starter are present, Spring Boot typically defaults to MVC.

### 7.2 File Layout

```text
src/main/java/com/example/oauthtokens/
  TokenLifecycleApplication.java
  OAuthClientConfiguration.java
  ReportsController.java
src/main/resources/application.yml
src/test/java/com/example/oauthtokens/
  AuthorizedClientLifecycleTest.java
```

Each `public class` resides in its own file, in the proper package. The project requires JDK 17+ and Gradle/Spring dependencies; it is not compiled with bare `javac`.

### 7.3 application.yml

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports:
            provider: training-idp
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - reports.read
        provider:
          training-idp:
            authorization-uri: https://idp.example.test/oauth2/authorize
            token-uri: https://idp.example.test/oauth2/token
            user-info-uri: https://idp.example.test/userinfo
            user-name-attribute: sub
```

`reports` is the registration ID used by WebClient. `REPORTS_CLIENT_ID`/`REPORTS_CLIENT_SECRET` must come from environment variables or a secrets manager; **never commit real values**. `authorization-uri` is used for browser redirects; `token-uri` is used on the backend for code exchange and refresh. With a real OIDC provider using the `openid` scope/issuer metadata, the provider config will differ. The IdP must have the exact redirect URI registered and valid callbacks; never accept arbitrary redirects.

### 7.4 TokenLifecycleApplication.java

`src/main/java/com/example/oauthtokens/TokenLifecycleApplication.java`:

```java
package com.example.oauthtokens;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TokenLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(TokenLifecycleApplication.class, args);
    }
}
```

### 7.5 OAuthClientConfiguration.java

`src/main/java/com/example/oauthtokens/OAuthClientConfiguration.java`:

```java
package com.example.oauthtokens;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class OAuthClientConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/", "/error").permitAll()
                .pathMatchers("/reports/**").authenticated()
                .anyExchange().denyAll()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository clients) {

        var provider = ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .authorizationCode()
            .refreshToken()
            .build();

        var manager = new DefaultReactiveOAuth2AuthorizedClientManager(
            registrations, clients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean
    WebClient reportsWebClient(
            ReactiveOAuth2AuthorizedClientManager manager) {
        var filter =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
        // Do not send a default bearer token to every outbound host.
        return WebClient.builder().filter(filter).build();
    }
}
```

The code above enables `oauth2Login()`, `oauth2Client()`, uses a request-context manager with authorization code/refresh-token providers, and attaches the WebClient filter. According to the **Spring Security 6.5 Javadoc**, when the WebClient filter is created using the **constructor accepting a manager**, a handler that removes the authorized client on downstream Resource Server 401/403 responses **is not automatically installed**. Production code needs to decide on configuring `setAuthorizationFailureHandler(...)` with a remover using the **same backing repository/service** and an appropriate error code policy; see section 11.

### 7.6 ReportsController.java

`src/main/java/com/example/oauthtokens/ReportsController.java`:

```java
package com.example.oauthtokens;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

@RestController
public class ReportsController {

    private final WebClient reportsWebClient;

    public ReportsController(WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    @GetMapping("/reports/current")
    public Mono<Map> currentReport() {
        return reportsWebClient.get()
            // Only call a fixed resource server host; do not take it from user input.
            .uri("https://api.example.test/reports/current")
            .attributes(clientRegistrationId("reports"))
            .retrieve()
            .bodyToMono(Map.class);
    }
}
```

**Explanation of a request's lifecycle:**

1. The browser must be logged in to call `GET /reports/current`.
2. The WebClient filter receives `clientRegistrationId("reports")`, and the manager looks up the authorized client by principal.
3. If reports authorization has not been granted yet, an authorization_code flow involving browser/consent may be required; a background job cannot log in on behalf of the user.
4. If the access token is valid, the filter attaches `Authorization: Bearer <access_token>` to the API on the proper host.
5. If the token needs refreshing and a refresh token/provider is present, the manager can call the Token Endpoint and save the new authorized client before sending the HTTP request.
6. If downstream returns 401, this is a Resource Server error regarding the access token or auth policy, **not** an `invalid_grant` from the Token Endpoint.
7. Never return the token value from the controller, and never enable a shared default authorized client on a WebClient used with user-controlled URLs.

### 7.7 Reading Metadata with @RegisteredOAuth2AuthorizedClient

Spring Security reactive allows receiving `OAuth2AuthorizedClient` as a controller parameter:

```java
@GetMapping("/reports/token-info")
public Mono<Map<String, String>> tokenInfo(
    @RegisteredOAuth2AuthorizedClient("reports")
    OAuth2AuthorizedClient client) {

    return Mono.just(Map.of(
        "registration", client.getClientRegistration().getRegistrationId(),
        "expiresAt", client.getAccessToken().getExpiresAt().toString()
    ));
}
```

This is a **method snippet**, requiring imports for `RegisteredOAuth2AuthorizedClient` from `org.springframework.security.oauth2.client.annotation`, `OAuth2AuthorizedClient`, `Mono`, and `Map`. Never return `getTokenValue()` and do not expose such a debug/metadata endpoint in production without a clear security requirement.

## 8. Service-to-Service client_credentials Without a Browser Refresh Token

A scheduled job wants to call an API using an **application identity**, with no user session. Declare a separate registration with `authorization-grant-type: client_credentials`, and a service manager using `ReactiveOAuth2AuthorizedClientService`.

Bean example **as an alternative or for use in a separate background module**:

```java
package com.example.oauthtokens;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration(proxyBeanMethods = false)
public class ServiceAuthorizedClientExample {

    @Bean("serviceAuthorizedClientManager")
    ReactiveOAuth2AuthorizedClientManager serviceManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService service) {

        var provider = ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

When **two managers** exist, use `@Qualifier("serviceAuthorizedClientManager")` in the background component to avoid ambiguous constructor injection. The job can build an authorize request:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("service-api")
        .principal("nightly-report-job")
        .build();

return serviceManager.authorize(request)
    .switchIfEmpty(Mono.error(
        new IllegalStateException("No authorized client")))
    .map(client -> client.getAccessToken().getTokenValue());
```

This is a **snippet**, requiring `OAuth2AuthorizeRequest` and `Mono`, and the token value must only be used **internally** when attaching Bearer to WebClient; never return it from a public endpoint or log it. The principal `nightly-report-job` must be a trusted service identity, not derived from a client-supplied query or header. When a `client_credentials` access token expires, the provider calls the token endpoint to request a **new token** under that grant rather than refreshing with a refresh token.

## 9. Testing the Manager Offline with JUnit 5 + StepVerifier

We test token management logic **without a real IdP**: create a test `ClientRegistration`, an in-memory authorized-client service, and a fake `ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>` so the `refreshToken` provider receives a new token or an `invalid_grant` error.

This test runs with Spring Security 6.5, JUnit 5, Reactor Test, and the dependencies in `build.gradle`; no HTTP server needs to run. In particular, it verifies that **a successful token refresh must be persisted**, not merely returned by the provider.

Create `src/test/java/com/example/oauthtokens/AuthorizedClientLifecycleTest.java`:

```java
package com.example.oauthtokens;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.endpoint.OAuth2RefreshTokenGrantRequest;
import org.springframework.security.oauth2.client.endpoint.ReactiveOAuth2AccessTokenResponseClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class AuthorizedClientLifecycleTest {

    private ClientRegistration registration;
    private InMemoryReactiveClientRegistrationRepository registrations;
    private InMemoryReactiveOAuth2AuthorizedClientService service;
    private Authentication alice;

    @BeforeEach
    void setUp() {
        registration = ClientRegistration.withRegistrationId("reports")
            .clientId("offline-test-client")
            .clientSecret("offline-test-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationUri("https://idp.example.test/authorize")
            .tokenUri("https://idp.example.test/token")
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("reports.read")
            .build();

        registrations =
            new InMemoryReactiveClientRegistrationRepository(registration);
        service = new InMemoryReactiveOAuth2AuthorizedClientService(
            registrations
        );
        alice = UsernamePasswordAuthenticationToken.authenticated(
            "alice",
            null,
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }

    private OAuth2AuthorizedClient createClient(
            String accessValue, Instant expiresAt, String refreshValue) {
        Instant issuedAt = expiresAt.minusSeconds(3600);

        OAuth2AccessToken access = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            accessValue, issuedAt, expiresAt,
            Set.of("reports.read")
        );

        OAuth2RefreshToken refresh = refreshValue == null
            ? null
            : new OAuth2RefreshToken(refreshValue, issuedAt);

        return new OAuth2AuthorizedClient(
            registration, "alice", access, refresh
        );
    }

    private void save(OAuth2AuthorizedClient authorizedClient) {
        StepVerifier.create(
            service.saveAuthorizedClient(authorizedClient, alice)
        ).verifyComplete();
    }

    private OAuth2AuthorizeRequest authorizeRequest() {
        return OAuth2AuthorizeRequest
            .withClientRegistrationId("reports")
            .principal(alice)
            .build();
    }

    private AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
            managerWithRefresh(AtomicInteger calls, boolean invalidGrant) {

        ReactiveOAuth2AccessTokenResponseClient<
            OAuth2RefreshTokenGrantRequest> tokenClient = grant -> {
                calls.incrementAndGet();

                if (invalidGrant) {
                    return Mono.error(new OAuth2AuthorizationException(
                        new OAuth2Error("invalid_grant")
                    ));
                }

                OAuth2AccessTokenResponse response =
                    OAuth2AccessTokenResponse.withToken("access-new")
                        .tokenType(OAuth2AccessToken.TokenType.BEARER)
                        .expiresIn(3600)
                        .refreshToken("refresh-new")
                        .scopes(Set.of("reports.read"))
                        .build();

                return Mono.just(response);
            };

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken(config ->
                    config.accessTokenResponseClient(tokenClient))
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Test
    void expiredTokenRefreshesAndSavesNewTokens() {
        save(createClient(
            "access-old", Instant.now().minusSeconds(120), "refresh-old"
        ));

        AtomicInteger calls = new AtomicInteger();
        var manager = managerWithRefresh(calls, false);

        StepVerifier.create(manager.authorize(authorizeRequest()))
            .assertNext(client -> {
                assertThat(client.getAccessToken().getTokenValue())
                    .isEqualTo("access-new");
                assertThat(client.getRefreshToken().getTokenValue())
                    .isEqualTo("refresh-new");
            })
            .verifyComplete();

        assertThat(calls.get()).isEqualTo(1);

        StepVerifier.create(
            service.<OAuth2AuthorizedClient>loadAuthorizedClient(
                "reports", "alice")
        )
            .assertNext(saved -> {
                assertThat(saved.getAccessToken().getTokenValue())
                    .isEqualTo("access-new");
                assertThat(saved.getRefreshToken().getTokenValue())
                    .isEqualTo("refresh-new");
            })
            .verifyComplete();
    }

    @Test
    void validAccessTokenDoesNotTriggerRefresh() {
        save(createClient(
            "access-valid", Instant.now().plusSeconds(3600), "refresh-old"
        ));

        AtomicInteger calls = new AtomicInteger();
        var manager = managerWithRefresh(calls, false);

        StepVerifier.create(manager.authorize(authorizeRequest()))
            .assertNext(client ->
                assertThat(client.getAccessToken().getTokenValue())
                    .isEqualTo("access-valid")
            )
            .verifyComplete();

        assertThat(calls.get()).isZero();
    }

    @Test
    void expiredTokenWithoutRefreshCannotBeRefreshed() {
        save(createClient(
            "access-expired", Instant.now().minusSeconds(120), null
        ));

        AtomicInteger calls = new AtomicInteger();
        var manager = managerWithRefresh(calls, false);

        StepVerifier.create(manager.authorize(authorizeRequest()))
            .assertNext(client -> {
                assertThat(client.getRefreshToken()).isNull();
                assertThat(client.getAccessToken().getTokenValue())
                    .isEqualTo("access-expired");
            })
            .verifyComplete();

        assertThat(calls.get()).isZero();
        // Do not send an expired token to the API; a new authorization-code flow is required.
    }

    @Test
    void invalidGrantRemovesStaleAuthorizedClient() {
        save(createClient(
            "access-expired",
            Instant.now().minusSeconds(120),
            "refresh-invalid"
        ));

        AtomicInteger calls = new AtomicInteger();
        var manager = managerWithRefresh(calls, true);

        StepVerifier.create(manager.authorize(authorizeRequest()))
            .expectError(OAuth2AuthorizationException.class)
            .verify();

        assertThat(calls.get()).isEqualTo(1);

        StepVerifier.create(
            service.<OAuth2AuthorizedClient>loadAuthorizedClient(
                "reports", "alice")
        ).verifyComplete();
    }

    @Test
    void authorizedClientIsolatedByPrincipal() {
        save(createClient(
            "alice-access", Instant.now().plusSeconds(3600), "alice-refresh"
        ));

        StepVerifier.create(
            service.<OAuth2AuthorizedClient>loadAuthorizedClient(
                "reports", "alice")
        )
            .assertNext(client ->
                assertThat(client.getPrincipalName()).isEqualTo("alice")
            )
            .verifyComplete();

        StepVerifier.create(
            service.<OAuth2AuthorizedClient>loadAuthorizedClient(
                "reports", "bob")
        ).verifyComplete();
    }
}
```

**What do these tests prove?**

| Test | Expected Result |
| --- | --- |
| `expiredTokenRefreshesAndSavesNewTokens` | Fake token response client is called once; new access/refresh tokens are saved |
| `validAccessTokenDoesNotTriggerRefresh` | Token is still valid; fake refresh client is not called |
| `expiredTokenWithoutRefreshCannotBeRefreshed` | Without a refresh token, the provider cannot "invent" a refresh; the old client may be returned |
| `invalidGrantRemovesStaleAuthorizedClient` | Token Endpoint reports `invalid_grant`; default failure handler removes stale client |
| `authorizedClientIsolatedByPrincipal` | Looking up principal bob does not retrieve alice's token |

**Important semantics:** When an expired access token has **no refresh token**, a manager/provider that does not support reauthorization may **return the old client** instead of issuing a new token. Therefore, callers must not infer that `authorize()` completing successfully means the token is always unexpired. With user-delegated flows, restart the authorization code flow if needed.

Run tests:

```bash
./gradlew test --tests '*AuthorizedClientLifecycleTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*AuthorizedClientLifecycleTest'
```

This is the **expected outcome from the Java code**, not a build/test run executed in the authoring environment. The test does not reach a real IdP because `ReactiveOAuth2AccessTokenResponseClient` returns a `Mono` directly in-process.

## 10. WebClient Attaching Bearer Tokens: Avoid Sending to the Wrong Host

`ServerOAuth2AuthorizedClientExchangeFilterFunction` reads the authorized client or registration ID from the `WebClient` request attributes. When selected and processed by the manager, the filter attaches the access token to the header:

```http
GET /reports/current HTTP/1.1
Host: api.example.test
Authorization: Bearer <ACCESS_TOKEN_ONLY>
```

Common selection patterns:

```java
webClient.get()
    .uri("https://api.example.test/reports/current")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("reports")
    )
    .retrieve()
    .bodyToMono(String.class);
```

Or when an `OAuth2AuthorizedClient` has already been resolved:

```java
webClient.get()
    .uri("https://api.example.test/reports/current")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .oauth2AuthorizedClient(authorizedClient)
    )
    .retrieve()
    .bodyToMono(String.class);
```

These are **snippets** inside a method that has `webClient` and `authorizedClient` variables. They demonstrate explicit selection, not standalone classes.

### 10.1 Why Not Enable a Default Authorized Client?

Options like `setDefaultOAuth2AuthorizedClient(true)` or `setDefaultClientRegistrationId(...)` can cause **many WebClient requests** to automatically carry a Bearer token, even when the target URL is not a trusted Resource Server. If a URL is user-supplied or attacker-controlled, or if WebClient follows a redirect to an unlisted host, the token can be leaked.

**Prefer:**
- A dedicated WebClient for a single trusted downstream host, with a fixed URL or host allowlist.
- Explicit `clientRegistrationId` or `oauth2AuthorizedClient` per request.
- Never accepting arbitrary URLs from query/body and passing them to a WebClient configured with an OAuth2 filter.
- Separating user-delegated tokens and service-to-service tokens.
- Checking Resource Server audience, scopes, and trust; do not rely on a URL merely "looking like" an allowed domain.

### 10.2 WebClient Failure Handler and Invalid Access Tokens

According to the Spring Security 6.5 Javadoc, the filter constructor accepting a **manager** does not automatically install `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` when the Resource Server returns an error. If unconfigured, the client may continue using a stale token on subsequent calls.

In production, use `filter.setAuthorizationFailureHandler(...)` with a remover backed by the **exact storage** of the manager. The failure handler should only remove on appropriate OAuth2 error codes, not blindly delete on every 403. Note: the **Manager failure handler** handles Authorization Server/token grant errors; the **WebClient filter failure handler** handles Resource Server responses.

## 11. Expiration Errors, invalid_grant, and HTTP 401/403

### 11.1 invalid_grant Is a Token Endpoint Error

OAuth2 `invalid_grant` may indicate that the refresh token was revoked, expired, already rotated, mismatched with the client, or no longer valid according to the IdP. Safe reactions:

1. Do not keep resending the old refresh token.
2. Remove the stale authorized client, or handle via optimistic-state checking if a newer token was already saved by another request.
3. If there is a user session, prompt for authorization code/consent again; never impersonate the user.
4. For `client_credentials`, use a new corresponding grant rather than "refreshing" with a nonexistent token.
5. Record **error code** and registration ID in metrics/logs; never log the refresh token.

### 11.2 Resource Server 401 Is Not Equivalent to invalid_grant

`401 Unauthorized` from a downstream API may be caused by an expired/revoked access token, wrong audience/issuer, or other trust misconfiguration. Do not assume a refresh token alone is needed. Inspect the `WWW-Authenticate` error code if present, register an appropriate failure handler, and verify the token targets the **right resource**.

### 11.3 Resource Server 403 Is Not Necessarily Token Expiration

`403 Forbidden` usually indicates missing scopes, roles, resource ownership, or policy denial. Refreshing an access token generally **does not grant higher scopes**. Do not write an unbounded "403 -> refresh -> retry" loop; it can trigger token storms and will not fix missing permissions.

### 11.4 Do Not Carelessly Retry POST/PUT Requests

After refreshing a token, retrying an outbound request requires care:
- GET/idempotent requests are generally safer to retry than write APIs.
- POST/PUT/PATCH can cause partial side effects that have already executed.
- Use idempotency keys, deduplication, and transaction boundaries for write APIs.
- Bound retries/backoff/timeouts, and do not retry unrecoverable error codes.
- If the request body is a non-replayable stream, do not attempt retries without a safe way to recreate the publisher.

## 12. Concurrent Refresh, Refresh-Token Rotation, and Multi-Pod

This is often the hardest production problem:

```text
Store at time T0:
  principal=alice, registration=reports
  access=A1 (near expiry), refresh=R1

Request A -> refresh(R1) -> IdP returns A2 + R2
Request B -> refresh(R1) -> IdP returns invalid_grant
Request A -> save A2/R2
Request B -> remove stale -> blind deletion may wipe out A2/R2
```

When the IdP enables one-time refresh tokens and reuse detection, concurrent refreshes across multiple pods can cause the client to lose authorization even though one request refreshed successfully.

**Solutions to evaluate:**

1. **Single-flight / per-key lock** keyed by registration + principal + tenant; do not use a single global lock for all users.
2. Use **versioned storage/optimistic locking** so request B cannot delete or overwrite the newer client saved by A.
3. Upon receiving `invalid_grant`, check whether the store has already been updated/rotated before deciding to delete.
4. Add lock timeouts and process-crash handling; avoid deadlocks or infinite waits.
5. Distinguish providers with rotation/reuse detection from providers that allow reusable refresh tokens.
6. Implement refresh throttling, appropriate clock skew, and metrics for attempt/error counts.
7. Do not let each replica maintain an isolated in-memory token store if refreshes must be synchronized.

**The framework does not automatically guarantee distributed locking/atomic rotation for every application.** Storage and concurrency control are part of production design and cannot be solved solely by calling `refreshToken()`.

## 13. Token Storage, Security, Logout, and Revocation

### 13.1 Where Should Tokens Be Stored?

- Store access and refresh tokens **server-side**, with encryption at rest / key management and minimal read access.
- Use a `ReactiveOAuth2AuthorizedClientService` suited to your persistence needs, avoiding token leaks in logs/traces/backups.
- Protect `client-secret` in environment variables or a secrets manager; never commit secrets to Git or embed them in JS bundles.
- Use HTTPS/TLS to the IdP, Resource Server, and browser; verify certificates and redirect URIs.
- Apply least-privilege scopes, proper audience/issuer checks, session security, and PKCE/state protection in the authorization code flow.
- Store tokens keyed by trusted principal/tenant/issuer; never allow clients to arbitrarily request another user's token.
- Implement cleanup for stale authorized clients upon user deletion, logout, or consent revocation.

### 13.2 Local Logout Is Not Revocation at the IdP

Ending the app's WebSession **does not necessarily** invalidate issued access/refresh tokens at the Authorization Server. There are three distinct actions:

1. **Local logout:** invalidates the user session.
2. **Local authorized-client removal:** removes `OAuth2AuthorizedClient` from the repository/service.
3. **Remote token revocation:** if supported by the IdP, calls the token revocation endpoint (RFC 7009) for the tokens to revoke; OIDC has related logout mechanisms.

Never log "token revoked" if the application only deleted a local DB record. A token extracted outside the store may remain valid until expiration or until revoked at the IdP.

### 13.3 Never Return Tokens in APIs or Logs

Avoid:

```java
// DO NOT use in a controller:
return Mono.just(authorizedClient.getRefreshToken().getTokenValue());
```

Instead, if genuinely needed for operations, log only allowlisted metadata such as:
- registration ID;
- grant type;
- token expiry **without the token value**;
- sanitized error code;
- request correlation ID containing no secrets.

Never log the entire `OAuth2AuthorizedClient`, OAuth2 token response, `Authorization` header, or unnecessary emails/PII. A refresh token can carry long-lived authority and must be treated as a highly sensitive secret.

## 14. Testing Checklist

A token lifecycle test suite should cover:

| Scenario | Expectation |
| --- | --- |
| No authorized client | Grant/authorization code requested via proper flow, no user impersonation |
| Token far from expiry | Reused without calling Token Endpoint |
| Token near expiry within skew | Refresh provider invoked if refresh token exists |
| Expired token with refresh token | New token response; saves new access and rotated refresh token |
| Expired token without refresh | Does not fake a refresh; reauthorizes when needed |
| Token Endpoint returns invalid_grant | Removes stale state/reauthorizes, no infinite retry |
| IdP timeout/5xx | Fail closed, bounded retry, never grants access without a valid token |
| Resource Server 401 invalid_token | Failure handler manages storage/error code properly |
| Resource Server 403 insufficient_scope | Does not escalate privileges via refresh |
| Users alice and bob on same registration | Tokens are not cross-used |
| Two concurrent refresh requests | Atomic/optimistic update does not delete the newer token |
| Logout/revocation | Local cleanup distinct from remote revocation |
| Multi-replica restart | Shared store or reauth strategy functions properly |
| WebClient calls unknown host | Does not automatically attach Bearer token |
| Scheduled job | Uses service manager, requires no ServerWebExchange |

## 15. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Confusing `ClientRegistration` with `OAuth2AuthorizedClient` | Fails to store tokens properly per principal | Understand client config vs. authorized state |
| Assuming app login implies authorized clients exist for all APIs | Missing consent/scopes | Check corresponding registration + authorized client |
| Sending access token instead of refresh token to Token Endpoint | Invalid grant request | Use refresh tokens only at the Token Endpoint |
| Sending refresh token as Bearer to Resource Server | Critical credential exposure | Send only access tokens outbound |
| Assuming authorization_code always yields a refresh token | Null refresh token/errors | Check IdP policy and offline access |
| Assuming client_credentials uses refresh tokens | Broken renewal logic | Request a new access token via client_credentials |
| Using web manager in a scheduled job | Missing ServerWebExchange | Use the service manager |
| Storing tokens by registration ID without principal isolation | User A's token sent for user B | Key by registration+principal+tenant |
| Defaulting WebClient to send tokens to every host | Token exfiltration/SSRF | Explicit authorized client + trusted URLs |
| Confusing outbound client with inbound resource validation | Inbound tokens left unverified | Separate `oauth2ResourceServer` configuration |
| Retrying `invalid_grant` indefinitely | Token Endpoint storm, state unfixed | Remove stale authorized client / re-authorize |
| Concurrent multi-pod refreshes without locks during rotation | Reuse error, accidental deletion of new token | Per-key sync/CAS |
| Relying only on in-memory store when scaling | Lost/divergent state | Persistent/shared store |
| Overlooking filter failure handler on manager constructor | Reusing stale bearer after downstream 401 | Configure handler matching the backing store |
| Refreshing on 403 regardless of scope | Gains no extra permission, infinite retry | Check insufficient_scope/authorization |
| Logging out of app and claiming tokens are revoked | Tokens may remain valid at IdP | RFC 7009/OIDC logout when required |
| Leaking secrets in logs, metrics, traces | Token/client secret compromise | Redaction, allowlisted metadata |
| Testing only the happy path | Misses expiry, errors, races, and principal leakage | Unit + integration negative cases |

## 16. Self-Check Questions

**1. Does `OAuth2AuthorizedClient` hold the client ID and tokens for all users in a single object?** No. Each authorized client binds one registration to **one principal** and its corresponding tokens; multiple users produce multiple authorized clients.

**2. Where is an access token used?** Sent to the appropriate Resource Server via `Authorization: Bearer`. Do not use it as a refresh token.

**3. Where is a refresh token used?** Sent to the Authorization Server Token Endpoint in a refresh-token grant. Never send it to the browser or business APIs.

**4. Why can `getRefreshToken()` be null?** The IdP is not required to issue a refresh token depending on grant/scope/policy; code must handle this case.

**5. Does `refreshToken()` refresh immediately after login?** No. It runs when the access token requires reauthorization, a refresh token is present, and the manager invokes the provider.

**6. What should be done when `client_credentials` expires?** Request a new token using the `client_credentials` grant, typically without a refresh token.

**7. When do you use `DefaultReactiveOAuth2AuthorizedClientManager`?** When a `ServerWebExchange` is available in a reactive HTTP request.

**8. When do you use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`?** In jobs, services, or background processes without a web exchange.

**9. Is `invalid_grant` an HTTP 401 from a downstream API?** No. It is an OAuth2 error from the Token Endpoint when the grant/refresh is invalid; a Resource Server 401 is a different layer.

**10. What does refresh token rotation require on the client side?** Persisting the new token and preventing concurrent refreshes from overwriting or deleting one another, especially across multiple pods.

**11. Why avoid enabling a default bearer token for all WebClient calls?** It can send credentials to the wrong host or to attacker-controlled URLs.

**12. Does a new token automatically elevate scopes on a 403?** No. Appropriate IdP consent/policy and Resource Server authorization are required.

**13. Does app logout automatically revoke tokens at the IdP?** Not guaranteed; local cleanup is separate from remote revocation.

**14. Is it possible for the manager to return an authorized client even when its access token is expired?** Yes, if the provider cannot reauthorize (e.g., missing refresh token); callers must never send an expired token as valid.

**15. Does a unit test with a fake Token Endpoint replace real IdP testing?** No. It verifies the manager/persistence, whereas OIDC metadata, redirects, PKCE, scopes, rotation, and downstream authorization require dedicated integration tests.

## 17. Summary

**`OAuth2AuthorizedClient` represents the authorization result for an OAuth2 Client**: it binds a `ClientRegistration` with a principal, an access token, and an optional refresh token. `ReactiveOAuth2AuthorizedClientManager` coordinates issuance, expiry checks, refresh, and state persistence. `ServerOAuth2AuthorizedClientRepository` / `ReactiveOAuth2AuthorizedClientService` handle persistence; `ServerOAuth2AuthorizedClientExchangeFilterFunction` attaches Bearer **access tokens** for `WebClient`.

Key takeaways: **access tokens and refresh tokens serve two different destinations; refresh tokens are not always issued; client_credentials normally requests a new token instead of refreshing; `invalid_grant` requires cleaning up stale state; and refresh-token rotation must be handled safely across concurrent requests and pods**. Spring Security handles standard lifecycle mechanics, but does not automatically solve token leakage, revocation, distributed locking, or data-level authorization.

### Official References

- [Spring Security 6.5 — Reactive OAuth2 Client Core Interfaces](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html)
- [Spring Security 6.5 — Authorized Client Features and WebClient Integration](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — Reactive OAuth2 Authorization Grants](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html)
- [Spring Security 6.5 — Reactive OAuth2 Client Overview](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/)
- [Spring Security 6.5 — ServerOAuth2AuthorizedClientExchangeFilterFunction API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Spring Security 6.5 — ReactiveOAuth2AuthorizedClientManager API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientManager.html)
- [Spring Boot 3.5 — OAuth2 Client Registration](https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html)
- [RFC 6749 — Refresh an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6)
- [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
