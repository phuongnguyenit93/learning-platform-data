# ReactiveOAuth2AuthorizedClientManager, ReactiveOAuth2AuthorizedClientService, and ServerOAuth2AuthorizedClientRepository

## Objectives and Scope

This lesson belongs to **Spring Security – reactive**, topic **OAuth2 Client**. After completing this lesson, learners will be able to:

1. Distinguish `ClientRegistration`, `OAuth2AuthorizedClient`, `ReactiveOAuth2AuthorizedClientManager`, `ReactiveOAuth2AuthorizedClientProvider`, `ReactiveOAuth2AuthorizedClientService`, and `ServerOAuth2AuthorizedClientRepository`.
2. Clearly understand that the **manager coordinates issuing/exchanging tokens**, the **service manages authorized-client records at the application layer**, and the **server repository connects those records to the WebFlux request/principal/session**. Do not confuse them with a user store or an OAuth2 Authorization Server.
3. Choose `DefaultReactiveOAuth2AuthorizedClientManager` for requests with a `ServerWebExchange` and `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` for jobs/services without a request.
4. Write `OAuth2AuthorizeRequest` with the proper principal, registrationId, and exchange attribute; understand `Mono<OAuth2AuthorizedClient>`, `Mono.empty()`, success/failure handlers, and token refresh.
5. Explain `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository`, `WebSessionServerOAuth2AuthorizedClientRepository`, `InMemoryReactiveOAuth2AuthorizedClientService`, and `R2dbcReactiveOAuth2AuthorizedClientService`, along with token storage risks.
6. Integrate `WebClient` with explicit client selection via `ServerOAuth2AuthorizedClientExchangeFilterFunction` without accidentally attaching tokens to every outbound HTTP request.
7. Run a Java 17+ / Spring Boot 3.x project with Spring Security 6.5 and `WebTestClient` / `StepVerifier` tests. Contrast a **learning-simulated provider** with a real OAuth2 provider.
8. Enforce fail-closed behavior, refresh tokens, multiple principals, `client_credentials`, logout/revocation, multi-instance deployments, and OAuth2 client secrets.

> **Safety boundary:** the practice project uses `LearningAuthorizedClientProvider`, which generates **fake token strings with no access to any real resource**, so that manager/service/repository tests run offline without needing an Identity Provider. This is **not an OAuth2 Authorization Server**, does not perform standard token exchange, and **must never be used in production**. Real provider configuration for `authorization_code`, `refresh_token`, and `client_credentials` is covered separately. Full demo project files are in sections 8–11; other snippets are explicitly marked as illustrative.

---

## 1. Putting the Concepts in the Right Place

In OAuth2, a WebFlux backend application can **act as a Client**: obtaining an access token from an Authorization Server and calling a Resource Server's API. It does not become an Authorization Server merely by enabling `oauth2Client()`.

```text
User / background job
       |
       v
Spring Security OAuth2 Client (WebFlux)
       |
       +-- ReactiveClientRegistrationRepository
       |      +-- ClientRegistration("crm", clientId, tokenUri, scopes...)
       |
       +-- ReactiveOAuth2AuthorizedClientManager
       |      +-- ReactiveOAuth2AuthorizedClientProvider
       |      |      authorization_code / refresh_token / client_credentials
       |      |
       |      +-- Where to load/save/remove OAuth2AuthorizedClient:
       |              A. ServerOAuth2AuthorizedClientRepository
       |                 (request + principal + ServerWebExchange)
       |              B. ReactiveOAuth2AuthorizedClientService
       |                 (registrationId + principalName)
       |
       v
OAuth2AuthorizedClient = registration + principalName + accessToken
                                           + optional refreshToken
       |
       v
WebClient -> Authorization: Bearer <access token>
       |
       v
Resource Server: checks token, scope/role, resource policy
```

### Definitions Table

| Type | Function | Does It Issue Tokens Itself? |
| --- | --- | --- |
| `ClientRegistration` | Configuration of a Client registered with the IdP: ID, grant type, client auth, token endpoint, scopes | No |
| `ReactiveClientRegistrationRepository` | Looks up configuration by `registrationId` (e.g., `crm`, `billing`) | No |
| `OAuth2AuthorizedClient` | Record that **already holds** an access token and optionally a refresh token, bound to registration + principal | No |
| `ReactiveOAuth2AuthorizedClientProvider` | Strategy executing a grant/token exchange or refresh when needed | Can request tokens from Authorization Server |
| `ReactiveOAuth2AuthorizedClientManager` | Coordinates providers, load/save/remove of tokens, and handlers | Not itself an Authorization Server |
| `ReactiveOAuth2AuthorizedClientService` | Reactive CRUD of authorized clients at application/principal-name scope | No |
| `ServerOAuth2AuthorizedClientRepository` | CRUD of authorized clients scoped to a WebFlux request, principal, and exchange | No |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Attaches Bearer access token to outbound `WebClient` requests once an authorized client is selected | Does not issue tokens independently; uses manager |

**Distinguishing registrations from authorized clients:**

- `ClientRegistration("crm")` can exist right from app startup, **with no token yet**.
- When an OAuth2 flow succeeds, `OAuth2AuthorizedClient` binds registration `crm` with `principalName` and tokens. For `authorization_code`, that is usually the end-user who granted authorization. For `client_credentials`, the principal name is an **application/service context key** chosen by you, not a real Resource Owner.
- One registration can yield many authorized-client records for different principals. Keying only by registrationId risks mixing tokens across users.

### OAuth2 Client vs. Resource Server

An application can be both a Resource Server (validating **inbound** Bearer tokens) and an OAuth2 Client (obtaining **outbound** Bearer tokens). The two roles are configured and managed differently. `ServerOAuth2AuthorizedClientRepository` is neither a `ReactiveAuthenticationManager` nor a JWT decoder's JWK set/cache.

## 2. OAuth2AuthorizedClient Lifecycle

When code needs to call a target API:

1. Select the right `clientRegistrationId` and determine the appropriate principal.
2. Build an `OAuth2AuthorizeRequest`.
3. `ReactiveOAuth2AuthorizedClientManager.authorize(request)` looks up a saved authorized client via the service or repository.
4. If absent or expired/needing renewal, the manager delegates to a `ReactiveOAuth2AuthorizedClientProvider` matching the grant.
5. The provider can communicate with the token endpoint to obtain a new access token or use a refresh token to renew it.
6. Upon success, the manager invokes `ReactiveOAuth2AuthorizationSuccessHandler`; the default configuration saves the authorized client through the chosen persistence.
7. The caller receives `Mono<OAuth2AuthorizedClient>` and uses `client.getAccessToken()` for outbound requests; never add tokens to logs or URLs.
8. If the grant fails, the manager emits an error or unsupported result depending on the case. On `invalid_grant`, the default failure handler can remove the saved authorized client to prevent reusing an invalid refresh token.

```text
authorize(request)
  |
  +-- Valid clientRegistrationId?
  |       |
  |       +-- No: error/cannot authorize per contract, no fake permit
  |
  +-- load OAuth2AuthorizedClient (principal + registrationId)
  |       |
  |       +-- Token valid, no refresh needed: can reuse
  |       |
  |       +-- Missing/expired:
  |               +-- Does a provider support the grant?
  |                       +-- Yes -> token request/refresh -> save -> return
  |                       +-- No -> Mono.empty or old authorized client
  |
  +-- Provider error:
          +-- failure handler per policy, may remove on invalid_grant
          +-- caller handles error safely, never sends arbitrary tokens
```

### `Mono.empty()` Is Neither 403 Nor an Empty Access Token

The contract of `ReactiveOAuth2AuthorizedClientManager.authorize` allows `Mono.empty()` if the grant is unsupported and no suitable authorized client exists. Calling code should handle it:

```java
return manager.authorize(authorizeRequest)
        .switchIfEmpty(Mono.error(
                new IllegalStateException("OAuth2 client unavailable")))
        .flatMap(client -> callProtectedApi(client));
```

This is a fragment: `callProtectedApi(...)` is a business method you define. **Never** write `.defaultIfEmpty(fakeToken)` or fall back to another principal's token. A `Mono.error` from the token endpoint must never be turned into authorization for a downstream API.

### Token Expiry and Refresh

An access token has `issuedAt`/`expiresAt`; the provider can consider a clock skew window to decide when to renew a token before actual expiration. Refresh tokens do not always exist; `client_credentials` typically obtains a new access token from the token endpoint when the old one expires rather than using a refresh token. `authorization_code` may receive a refresh token if the Authorization Server issues one and policy allows it.

Do not assume every `OAuth2AuthorizedClient` has a refresh token or that the manager replaces IdP policies on consent, scopes, and rotation. You should test expired tokens, `invalid_grant`, revocation, and timeouts.

## 3. ReactiveOAuth2AuthorizedClientManager — The Coordinator

The interface lives in:

```java
org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager
```

Key contract:

```java
Mono<OAuth2AuthorizedClient> authorize(
        OAuth2AuthorizeRequest authorizeRequest);
```

It has no synchronous `authorize(...)` returning a blocking object like Servlet `OAuth2AuthorizedClientManager`. To stay non-blocking:

- Use `return manager.authorize(...).flatMap(...)`; never call `.block()` on the Netty event loop.
- Do not manually `.subscribe()` and immediately read a mutable variable afterward.
- For background jobs, the scheduler must subscribe **once** by design; avoid duplicate subscriptions that trigger uncontrolled token requests.
- When a provider does not support a grant, detect `Mono.empty()` and stop safely.
- When making outbound `WebClient` calls, bound timeouts, retries, and concurrency, and never log the Authorization header.

### 3.1. DefaultReactiveOAuth2AuthorizedClientManager

This implementation is used **within a `ServerWebExchange` context**, paired with `ServerOAuth2AuthorizedClientRepository`.

Typical configuration for an application handling user requests:

```java
@Bean
ReactiveOAuth2AuthorizedClientManager browserAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ServerOAuth2AuthorizedClientRepository repository) {

    ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                    .authorizationCode()
                    .refreshToken()
                    .clientCredentials()
                    .build();

    DefaultReactiveOAuth2AuthorizedClientManager manager =
            new DefaultReactiveOAuth2AuthorizedClientManager(
                    registrations, repository);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

This is a fragment of a **real** configuration requiring Spring Security OAuth2 reactive imports. Depending on requirements, enable only the grants supported by the registered clients. The learning project code below uses a fake provider **as a substitute**, so never mix the mock and real providers in production.

Inside a controller:

```java
OAuth2AuthorizeRequest authorizeRequest =
        OAuth2AuthorizeRequest.withClientRegistrationId("crm")
                .principal(authentication)
                .attribute(ServerWebExchange.class.getName(), exchange)
                .build();

return browserAuthorizedClientManager.authorize(authorizeRequest);
```

`authentication` comes from Spring Security and `exchange` is the current request. `ServerWebExchange.class.getName()` is the attribute key this implementation uses to retrieve the exchange. Take registration IDs from trusted configuration; never let clients pass arbitrary registration names to borrow another application's token.

**Never use DefaultReactive... directly inside a `@Scheduled` job without a ServerWebExchange**, because that request context does not exist. Use the service-based implementation instead.

### 3.2. AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager

This implementation is intended for the service tier, batch/jobs, and cases **without an HTTP request**:

```java
@Bean
ReactiveOAuth2AuthorizedClientManager systemAuthorizedClientManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService service) {

    ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                    .clientCredentials()
                    .build();

    AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                    registrations, service);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

A job uses a stable principal name such as `system:reports` as the key to cache the `client_credentials` token:

```java
Authentication servicePrincipal =
        new UsernamePasswordAuthenticationToken(
                "system:reports", "N/A",
                List.of(new SimpleGrantedAuthority("ROLE_SYSTEM")));

OAuth2AuthorizeRequest request =
        OAuth2AuthorizeRequest.withClientRegistrationId("machine")
                .principal(servicePrincipal)
                .build();

return systemAuthorizedClientManager.authorize(request);
```

This is a fragment: never grant `ROLE_SYSTEM` to external callers; the principal here merely represents a **trusted** job. With `client_credentials`, never equate that principal name with a logged-in user or use a user's token to perform system tasks.

### 3.3. Can Both Managers Share Storage?

Yes, **if designed intentionally**: the web manager saving through a repository can delegate down to the same `ReactiveOAuth2AuthorizedClientService`; the service manager also uses that service. When sharing `(registrationId, principalName)`, records are visible in both contexts. This is why end-user and service-account principal names must be kept separate. Never use `"system"` across all tenants/customers if tokens carry different permissions.

If you use a separate `WebSessionServerOAuth2AuthorizedClientRepository` for the browser and an application service for jobs, the two stores do not synchronize automatically. Never assume a user who just performed OAuth2 login has a token in every service store.

## 4. ReactiveOAuth2AuthorizedClientService — Application-Tier Authorized Client Store

Interface:

```java
org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService
```

Three core operations:

```java
<T extends OAuth2AuthorizedClient> Mono<T> loadAuthorizedClient(
        String clientRegistrationId, String principalName);

Mono<Void> saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal);

Mono<Void> removeAuthorizedClient(
        String clientRegistrationId, String principalName);
```

The **logical key** is `(registrationId, principalName)`. Identical principal names across two tenants must be differentiated via a tenant-verified identity or appropriate storage design.

### 4.1. InMemoryReactiveOAuth2AuthorizedClientService

Suitable for demos, integration tests, or small workloads that do not need tokens persisted across restarts:

```java
@Bean
ReactiveOAuth2AuthorizedClientService authorizedClientService(
        ReactiveClientRegistrationRepository registrations) {
    return new InMemoryReactiveOAuth2AuthorizedClientService(
            registrations);
}
```

Notes:

- Data is lost when the app restarts.
- Multiple instances do not share memory.
- Do not use where durability, a multi-instance token cache, revocation tracking, or unevaluated encryption-at-rest policies are required.
- Even when stored in memory, tokens remain sensitive credentials; never dump the object or access token in debug logs.

### 4.2. R2dbcReactiveOAuth2AuthorizedClientService

Spring Security 6.5 provides `R2dbcReactiveOAuth2AuthorizedClientService` to persist authorized clients in a reactive database when R2DBC is configured. You need the OAuth2 Authorized Client table schema described in Spring Security documentation, a connection factory, and policies for:

- Encrypting access/refresh tokens **at rest**, key management, and database read permissions.
- Tenant/principal isolation, expired token data, and cleanup after revocation.
- Transaction semantics and concurrency when two requests refresh simultaneously.
- Connection pooling, latency, and failing closed if the database is unavailable.
- Never writing access/refresh tokens to telemetry, exception bodies, or analytics.

**Do not blindly copy the JDBC OAuth2 schema or use Servlet `JdbcOAuth2AuthorizedClientService`**; choose the reactive implementation and verify the matching schema/version. A production application can use a custom service to store encrypted records or integrate a central secret store, while preserving semantics and tests.

### 4.3. The Service Does Not Request Tokens by Itself

Calling `loadAuthorizedClient(...)` only looks up an **existing record**:

```java
return authorizedClientService
        .<OAuth2AuthorizedClient>loadAuthorizedClient(
                "crm", authentication.getName())
        .map(client -> client.getAccessToken().getExpiresAt());
```

This snippet does not refresh the token and does not guarantee the token is still usable; if the goal is **obtaining a fresh token to call an API**, prefer `manager.authorize(...)`. Direct service lookup fits status audits, checking whether authorization has been granted, admin cleanup, or controlled management operations.

## 5. ServerOAuth2AuthorizedClientRepository — Store Bound to the WebFlux Exchange

Interface:

```java
org.springframework.security.oauth2.client.web.server
        .ServerOAuth2AuthorizedClientRepository
```

Method signatures:

```java
<T extends OAuth2AuthorizedClient> Mono<T> loadAuthorizedClient(
        String registrationId,
        Authentication principal,
        ServerWebExchange exchange);

Mono<Void> saveAuthorizedClient(
        OAuth2AuthorizedClient authorizedClient,
        Authentication principal,
        ServerWebExchange exchange);

Mono<Void> removeAuthorizedClient(
        String registrationId,
        Authentication principal,
        ServerWebExchange exchange);
```

Difference from the service: **the repository accepts both Authentication and ServerWebExchange**, allowing it to use session/request context and authenticated/anonymous policies. The service only uses registration ID + principal name and does not require an HTTP request.

### 5.1. WebSessionServerOAuth2AuthorizedClientRepository

`WebSessionServerOAuth2AuthorizedClientRepository` stores authorized clients inside `WebSession`. For browser OAuth2 flows or anonymous requests, this is useful when state is tied to the web session.

- Sessions can be lost when expired or invalidated.
- If using distributed sessions, storage semantics follow the session infrastructure.
- Logout or invalidating the WebSession can delete records held only in the session.
- It does not automatically remove all authorized clients in an application-level service or call a remote IdP revocation endpoint.

### 5.2. AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository

This implementation **acts as a bridge**:

- When the principal is authenticated, it delegates to the `ReactiveOAuth2AuthorizedClientService` you supply.
- When the principal is anonymous/unauthenticated, it delegates to another repository, defaulting to `WebSessionServerOAuth2AuthorizedClientRepository`.
- This lets the web manager use a request-aware repository contract while persisting via the application service for logged-in principals.

```java
@Bean
ServerOAuth2AuthorizedClientRepository serverAuthorizedClients(
        ReactiveOAuth2AuthorizedClientService authorizedClientService) {
    return new AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository(
            authorizedClientService);
}
```

Do not assume **every** `ServerOAuth2AuthorizedClientRepository` implementation automatically writes to the service. That holds for this bridge implementation when the principal is authenticated, not for a pure WebSession repository.

### 5.3. Save/Remove Is Different from Revoke

`removeAuthorizedClient(...)` only deletes the record held by the application. Already-issued tokens may **still remain valid at the Resource Server** until they expire, are revoked via an OAuth2 revocation endpoint (if available), or are invalidated by IdP/token policies.

For user logout, explicitly decide:

- Delete the local SecurityContext/WebSession?
- Remove the user's authorized clients from the repository/service?
- Revoke refresh/access tokens at the Authorization Server?
- Trigger OIDC RP-initiated logout from the IdP?
- Should other background clients remain usable?

These are **distinct operations**. Do not call `save/remove` and then claim remote tokens have been revoked.

## 6. Choosing the Right Implementation by Scenario

| Scenario | Appropriate Manager | Typical Persistence |
| --- | --- | --- |
| User logs in via OAuth2 in browser, calls API on behalf of user | `DefaultReactiveOAuth2AuthorizedClientManager` | `ServerOAuth2AuthorizedClientRepository` |
| User authenticated via Basic/session, app needs outbound client token in request | `DefaultReactiveOAuth2AuthorizedClientManager` | Request-bound repository; bridged to service when appropriate |
| `@Scheduled` job acquiring `client_credentials` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | `ReactiveOAuth2AuthorizedClientService` |
| Consumer/queue without `ServerWebExchange` | Service-based manager | Application service |
| Test inspecting an existing token record | Can call service/repository directly | Same storage used by the workflow |
| WebClient sending Bearer token outbound | WebClient OAuth2 filter using appropriate manager | Manager controls refresh/persistence |
| Multi-instance app requiring shared token cache | Context-appropriate manager | Persistent store with durability and cross-instance consistency |

**Never choose a manager just because its class name contains "Default".** The criteria are whether an HTTP exchange is present at the call site and which principal owns the token.

## 7. Integrating WebClient with OAuth2 Client

In WebFlux, Spring Security provides:

```java
org.springframework.security.oauth2.client.web.reactive.function.client
        .ServerOAuth2AuthorizedClientExchangeFilterFunction
```

WebClient example using a reactive manager:

```java
@Bean
WebClient resourceWebClient(
        ReactiveOAuth2AuthorizedClientManager webAuthorizedClientManager) {

    ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                    webAuthorizedClientManager);

    return WebClient.builder()
            .filter(oauth2)
            .build();
}
```

When calling an API, select a **specific client registration**:

```java
return resourceWebClient.get()
        .uri("https://api.example.test/v1/profile")
        .attributes(ServerOAuth2AuthorizedClientExchangeFilterFunction
                .clientRegistrationId("crm"))
        .retrieve()
        .bodyToMono(String.class);
```

**Warning:** this is a snippet integrating a **real OAuth2 provider** and an illustrative endpoint, not part of the offline fake-token demo. This request could send a real Bearer credential to the target API; only call allowlisted hostnames and never let users control arbitrary outbound URLs (SSRF/token exfiltration).

You can also use:

```java
.attributes(ServerOAuth2AuthorizedClientExchangeFilterFunction
        .oauth2AuthorizedClient(authorizedClient))
```

when you already have a specific authorized client. The `@RegisteredOAuth2AuthorizedClient("crm")` annotation can resolve an authorized client in a WebFlux controller, but it **does not replace** the underlying manager and storage mechanism.

### Default Authorized Client: Convenient but Risky

`setDefaultOAuth2AuthorizedClient(true)` or `setDefaultClientRegistrationId("crm")` can cause **every outbound request from that WebClient** to receive the default access token, including requests to unintended hosts. Spring Security advises caution. Prefer specifying the registration **per request**, or creating a dedicated WebClient for a single protected API with a fixed host and safeguards preventing redirects to other hosts.

### When the Resource Server Returns 401/403 for Bearer

Having a token does not guarantee the Resource Server will accept it. Distinguish:

- `401 invalid_token`: may require removing the invalid token record / re-authorizing per policy.
- `403 insufficient_scope`: should not simply fetch another token or retry endlessly to bypass permissions.
- Token endpoint error: manager reports an OAuth2 error; never substitute a fake token or another user's token.
- Refresh rotation and revocation: must comply with IdP policies.
- When using the WebClient filter with a manager, inspect the exact failure handler and wire `OAuth2AuthorizationFailureHandler` according to the constructor/configuration/version so stale invalid tokens are not retained forever.

## 8. Offline Demo Project: Simulated Provider with Real Manager/Service/Repository

**Practice goal:** learn how the **three components work together** using a provider that generates a fixed fake token inside the test process. The project contacts no IdP, needs no real client secret, and calls no real Resource Server. Capabilities such as real refresh grants are covered in section 12.

### 8.1. Structure

```text
authorized-client-lab/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/oauth2lab/
        AuthorizedClientLabApplication.java
        SecurityConfiguration.java
        AuthorizedClientConfiguration.java
        LearningAuthorizedClientProvider.java
        AuthorizedClientController.java
        MachineJob.java
      resources/
        application.yml
    test/
      java/example/oauth2lab/
        AuthorizedClientIntegrationTest.java
```

### 8.2. Gradle and Java 17

**`settings.gradle`:**

```groovy
rootProject.name = 'authorized-client-lab'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/resources/application.yml`:**

```yaml
spring:
  application:
    name: authorized-client-lab

server:
  port: 8080
```

Do not configure `spring.security.oauth2.client.registration` in this lab project because the code below creates an explicit `ClientRegistration`. Do not add the MVC starter. For a real OAuth2 client, Boot properties can be used to configure the provider/registration; see section 12.

### 8.3. Main Class

**`src/main/java/example/oauth2lab/AuthorizedClientLabApplication.java`:**

```java
package example.oauth2lab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AuthorizedClientLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(AuthorizedClientLabApplication.class, args);
    }
}
```

### 8.4. SecurityWebFilterChain: HTTP Basic, Keeping CSRF

**`src/main/java/example/oauth2lab/SecurityConfiguration.java`:**

```java
package example.oauth2lab;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService demoUsers(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("local-demo-password"))
                .roles("USER")
                .build();
        UserDetails bob = User.withUsername("bob")
                .password(encoder.encode("local-demo-password"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice, bob);
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/public/ping")
                            .permitAll()
                        .anyExchange().authenticated()
                )
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

Here, **inbound** authentication to the application is Basic solely for testing. It is **different** from OAuth2 `client_credentials` used to obtain **outbound** tokens. OAuth2 login is not enabled yet; the demo drives authorized clients directly through the manager bean so no browser authorization-code redirect is needed.

CSRF remains enabled by default. POST endpoints in the demo must send a CSRF token, even when authenticated. Do not disable CSRF just to make a test return 200. Sample passwords must never be used in production, and HTTP Basic should only be used over HTTPS outside localhost.

### 8.5. LearningAuthorizedClientProvider: Lab Use Only

**`src/main/java/example/oauth2lab/LearningAuthorizedClientProvider.java`:**

```java
package example.oauth2lab;

import java.time.Duration;
import java.time.Instant;
import java.util.Set;

import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component("learningProvider")
public class LearningAuthorizedClientProvider
        implements ReactiveOAuth2AuthorizedClientProvider {

    @Override
    public Mono<OAuth2AuthorizedClient> authorize(
            OAuth2AuthorizationContext context) {

        if (!"sandbox".equals(
                context.getClientRegistration().getRegistrationId())) {
            return Mono.empty();
        }

        OAuth2AuthorizedClient existing = context.getAuthorizedClient();
        Instant now = Instant.now();

        if (existing != null
                && existing.getAccessToken().getExpiresAt() != null
                && existing.getAccessToken().getExpiresAt()
                        .isAfter(now.plusSeconds(60))) {
            // Existing record is valid: manager can reuse it.
            return Mono.empty();
        }

        // ONLY FOR TESTS: no network, no signature, no real OAuth2 grant.
        OAuth2AccessToken fake = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "not-a-real-access-token",
                now,
                now.plus(Duration.ofMinutes(15)),
                Set.of("demo.read"));

        return Mono.just(new OAuth2AuthorizedClient(
                context.getClientRegistration(),
                context.getPrincipal().getName(),
                fake));
    }
}
```

**Security:** this class intentionally contacts no token endpoint, produces no valid JWT, validates no consent, and revokes no tokens; **for lab use only**. Never configure it in production. When replaced with a real provider, tokens will be issued by the Authorization Server according to the registered grant and client registration.

The `Mono.empty()` branch when an existing client is still valid signals that the provider does not need to issue a new token; the manager can return the already-loaded authorized client. When no authorized client exists yet, the provider returns a fake record to verify save/load/remove.

### 8.6. Declaring the Three Components and Two Managers

**`src/main/java/example/oauth2lab/AuthorizedClientConfiguration.java`:**

```java
package example.oauth2lab;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;

@Configuration(proxyBeanMethods = false)
public class AuthorizedClientConfiguration {

    @Bean
    ReactiveClientRegistrationRepository registrations() {
        ClientRegistration registration = ClientRegistration
                .withRegistrationId("sandbox")
                .clientId("learning-client")
                .clientSecret("not-a-real-client-secret")
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://idp.example.invalid/oauth2/token")
                .scope("demo.read")
                .build();

        return new InMemoryReactiveClientRegistrationRepository(registration);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientService authorizedClientService(
            ReactiveClientRegistrationRepository registrations) {
        return new InMemoryReactiveOAuth2AuthorizedClientService(
                registrations);
    }

    @Bean
    ServerOAuth2AuthorizedClientRepository authorizedClientRepository(
            ReactiveOAuth2AuthorizedClientService service) {
        return new AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository(
                service);
    }

    @Bean("browserManager")
    ReactiveOAuth2AuthorizedClientManager browserManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository repository,
            @Qualifier("learningProvider")
                    ReactiveOAuth2AuthorizedClientProvider provider) {

        DefaultReactiveOAuth2AuthorizedClientManager manager =
                new DefaultReactiveOAuth2AuthorizedClientManager(
                        registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean("jobManager")
    ReactiveOAuth2AuthorizedClientManager jobManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService service,
            @Qualifier("learningProvider")
                    ReactiveOAuth2AuthorizedClientProvider provider) {

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, service);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

**What does each bean mean?**

- `registrations()` builds the `sandbox` registration config. The URI `idp.example.invalid` is a placeholder **not called** in the lab because the fake provider completes authorization in memory. The client secret is also a fake string; never use it in production.
- `authorizedClientService()` is the application store, keyed by `principalName + registrationId`.
- `authorizedClientRepository()` uses the bridge: for authenticated principals, the repository operates through **this same service**; for anonymous principals, the bridge uses the WebSession repository by default.
- `browserManager` requires `ServerWebExchange` because it uses `DefaultReactiveOAuth2AuthorizedClientManager`.
- `jobManager` requires no exchange because it uses `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.
- Both receive the same `learningProvider` to create fake records. The two managers share the **same service** with different principals, which is an intentional illustrative design decision.
- Bean names and `@Qualifier` prevent ambiguity when **two beans implement the same `ReactiveOAuth2AuthorizedClientManager` interface**.
- Real systems should not write a custom "fake provider" but instead use `ReactiveOAuth2AuthorizedClientProviderBuilder` for real grants and load secrets from a secrets manager.

## 9. WebFlux Controller: Saving, Reading, and Removing Authorized Clients per Request

**`src/main/java/example/oauth2lab/AuthorizedClientController.java`:**

```java
package example.oauth2lab;

import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class AuthorizedClientController {

    private final ReactiveOAuth2AuthorizedClientManager browserManager;
    private final ServerOAuth2AuthorizedClientRepository repository;

    public AuthorizedClientController(
            @Qualifier("browserManager")
                    ReactiveOAuth2AuthorizedClientManager browserManager,
            ServerOAuth2AuthorizedClientRepository repository) {
        this.browserManager = browserManager;
        this.repository = repository;
    }

    private Mono<Authentication> currentAuthentication() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication());
    }

    private Map<String, String> summary(OAuth2AuthorizedClient client) {
        return Map.of(
                "state", "present",
                "registration", client.getClientRegistration()
                        .getRegistrationId(),
                "principal", client.getPrincipalName()
        );
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @PostMapping("/demo/browser/authorize")
    public Mono<Map<String, String>> authorize(ServerWebExchange exchange) {
        return currentAuthentication()
                .flatMap(authentication -> {
                    OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
                            .withClientRegistrationId("sandbox")
                            .principal(authentication)
                            .attribute(
                                    ServerWebExchange.class.getName(),
                                    exchange)
                            .build();

                    return browserManager.authorize(request);
                })
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.BAD_GATEWAY,
                                "Authorized client unavailable")))
                .map(this::summary);
    }

    @GetMapping("/demo/browser/status")
    public Mono<Map<String, String>> status(ServerWebExchange exchange) {
        return currentAuthentication()
                .flatMap(authentication ->
                        repository.<OAuth2AuthorizedClient>
                                loadAuthorizedClient(
                                        "sandbox", authentication, exchange))
                .map(this::summary)
                .defaultIfEmpty(Map.of("state", "absent"));
    }

    @PostMapping("/demo/browser/remove")
    public Mono<Map<String, String>> remove(ServerWebExchange exchange) {
        return currentAuthentication()
                .flatMap(authentication ->
                        repository.removeAuthorizedClient(
                                "sandbox", authentication, exchange))
                .thenReturn(Map.of("state", "removed"));
    }
}
```

**Detailed explanation:**

1. The controller obtains `Authentication` from `ReactiveSecurityContextHolder` of the **request subscription**, not from thread-local `SecurityContextHolder.getContext()`.
2. `authorize()` passes the `ServerWebExchange.class.getName()` attribute; the manager invokes the provider, saves the record via the repository, and returns the result. It does not manually call `service.save...` a second time.
3. `status()` only reads the repository and **does not call the manager**, so it does not attempt to request or refresh a token if the record is missing. It returns `"absent"` or low-sensitivity metadata, **never returning raw access tokens**.
4. `remove()` deletes the local record and **does not revoke the token at the IdP**. This is strictly a storage-management demo and must not be turned into a public production endpoint.
5. Every `/demo/...` endpoint requires authentication; POST routes are also subject to default CSRF protection. The local demo uses Basic in tests to establish an identity.
6. The repository uses the bridge for authenticated users, so after browser authorization, a direct service lookup with the **same principal name** can find the record.
7. This is learning application logic, not an OAuth2 callback endpoint, Authorization Server, or real token-protecting gateway. Do not expose this API on Internet production.

## 10. Job/Service Without ServerWebExchange

**`src/main/java/example/oauth2lab/MachineJob.java`:**

```java
package example.oauth2lab;

import java.util.List;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class MachineJob {

    private final ReactiveOAuth2AuthorizedClientManager manager;

    public MachineJob(
            @Qualifier("jobManager")
                    ReactiveOAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public Mono<String> runOnce() {
        // A trusted service identity, not an HTTP user's identity.
        Authentication principal =
                new UsernamePasswordAuthenticationToken(
                        "system:reports", "N/A",
                        List.of(new SimpleGrantedAuthority("ROLE_SYSTEM")));

        OAuth2AuthorizeRequest request =
                OAuth2AuthorizeRequest
                        .withClientRegistrationId("sandbox")
                        .principal(principal)
                        .build();

        return manager.authorize(request)
                .switchIfEmpty(Mono.error(
                        new IllegalStateException(
                                "No client authorization available")))
                .map(client -> client.getClientRegistration()
                        .getRegistrationId() + ":" + client.getPrincipalName());
    }
}
```

This method **does not accept ServerWebExchange** and does not depend on the HTTP Reactor Context. In production, a trusted scheduler or queue consumer can call `runOnce()` as part of the job's pipeline. Never call `.subscribe()` inside the service to return success before receiving a token. Never expose a public endpoint allowing users to pick an arbitrary `principalName` and acquire the application's `client_credentials`.

Expected test result:

```text
sandbox:system:reports
```

This is the **registration + principal name**, not a token. With a dedicated principal name, the job's token never mixes with records belonging to `alice` or `bob`.

## 11. Testing with WebTestClient and StepVerifier

The tests focus squarely on the three components: the manager **coordinates**; the repository **stores per request/principal**; and the service **reads application-level data**. The mock provider produces fake tokens, so the tests need no real token endpoint.

**`src/test/java/example/oauth2lab/AuthorizedClientIntegrationTest.java`:**

```java
package example.oauth2lab;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class AuthorizedClientIntegrationTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    ReactiveOAuth2AuthorizedClientService service;

    @Autowired
    MachineJob job;

    private WebTestClient client;

    @BeforeEach
    void prepare() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();

        StepVerifier.create(Mono.when(
                service.removeAuthorizedClient("sandbox", "alice"),
                service.removeAuthorizedClient("sandbox", "bob"),
                service.removeAuthorizedClient(
                        "sandbox", "system:reports")))
                .verifyComplete();
    }

    @Test
    void publicPingWorks() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("pong");
    }

    @Test
    void anonymousCannotInspectAuthorizedClient() {
        client.get().uri("/demo/browser/status")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void aliceStartsWithoutAuthorizedClient() {
        client.mutateWith(mockUser("alice"))
                .get().uri("/demo/browser/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.state").isEqualTo("absent");
    }

    @Test
    void authorizeWithoutCsrfIsRejected() {
        client.mutateWith(mockUser("alice"))
                .post().uri("/demo/browser/authorize")
                .exchange()
                .expectStatus().isForbidden();

        StepVerifier.create(service
                .<OAuth2AuthorizedClient>loadAuthorizedClient(
                        "sandbox", "alice"))
                .verifyComplete();
    }

    @Test
    void authorizeWithCsrfPersistsForAlice() {
        client.mutateWith(mockUser("alice"))
                .mutateWith(csrf())
                .post().uri("/demo/browser/authorize")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.registration").isEqualTo("sandbox")
                .jsonPath("$.principal").isEqualTo("alice")
                .jsonPath("$.state").isEqualTo("present");

        StepVerifier.create(service
                .<OAuth2AuthorizedClient>loadAuthorizedClient(
                        "sandbox", "alice"))
                .assertNext(saved -> {
                    assertEquals("sandbox",
                            saved.getClientRegistration().getRegistrationId());
                    assertEquals("alice", saved.getPrincipalName());
                    assertTrue(saved.getAccessToken().getExpiresAt()
                            .isAfter(java.time.Instant.now()));
                })
                .verifyComplete();
    }

    @Test
    void bobDoesNotReuseAlicesAuthorizedClient() {
        client.mutateWith(mockUser("alice"))
                .mutateWith(csrf())
                .post().uri("/demo/browser/authorize")
                .exchange()
                .expectStatus().isOk();

        client.mutateWith(mockUser("bob"))
                .get().uri("/demo/browser/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.state").isEqualTo("absent");
    }

    @Test
    void sameAuthenticatedPrincipalFindsSavedRecord() {
        client.mutateWith(mockUser("alice"))
                .mutateWith(csrf())
                .post().uri("/demo/browser/authorize")
                .exchange()
                .expectStatus().isOk();

        client.mutateWith(mockUser("alice"))
                .get().uri("/demo/browser/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.state").isEqualTo("present")
                .jsonPath("$.principal").isEqualTo("alice");
    }

    @Test
    void removingLocalRecordMakesStatusAbsent() {
        client.mutateWith(mockUser("alice"))
                .mutateWith(csrf())
                .post().uri("/demo/browser/authorize")
                .exchange()
                .expectStatus().isOk();

        client.mutateWith(mockUser("alice"))
                .mutateWith(csrf())
                .post().uri("/demo/browser/remove")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.state").isEqualTo("removed");

        client.mutateWith(mockUser("alice"))
                .get().uri("/demo/browser/status")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.state").isEqualTo("absent");
    }

    @Test
    void jobWorksWithoutServerWebExchange() {
        StepVerifier.create(job.runOnce())
                .expectNext("sandbox:system:reports")
                .verifyComplete();
    }

    @Test
    void jobRecordIsSeparateFromAlice() {
        StepVerifier.create(job.runOnce())
                .expectNext("sandbox:system:reports")
                .verifyComplete();

        StepVerifier.create(service
                .<OAuth2AuthorizedClient>loadAuthorizedClient(
                        "sandbox", "system:reports"))
                .assertNext(saved ->
                        assertEquals("system:reports",
                                saved.getPrincipalName()))
                .verifyComplete();

        StepVerifier.create(service
                .<OAuth2AuthorizedClient>loadAuthorizedClient(
                        "sandbox", "alice"))
                .verifyComplete();
    }
}
```

Run:

```bash
./gradlew test --tests example.oauth2lab.AuthorizedClientIntegrationTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.oauth2lab.AuthorizedClientIntegrationTest
```

Expect **10 PASS tests** when using the project, dependencies, and mock provider as shown in the lesson. This is an **expectation from the source code**, not an actual compile/test run executed in the learner's environment.

### What the Tests Verify

| Test | Meaning |
| --- | --- |
| Public ping and anonymous | HTTP security remains active; OAuth2 storage does not authenticate callers by itself |
| Alice status before authorize | Repository does not create a token merely upon being read |
| Alice POST without CSRF | Request is blocked before the manager saves; the service stays empty |
| Alice POST with CSRF | Web manager invokes the mock provider and **saves through repository -> service** |
| Bob does not see Alice's token | Records are isolated by `principalName` |
| Same Alice reads status | Repository bridges to the service across two requests using mock identity |
| Remove local record | Local storage deletes the record, distinct from remote revocation |
| Job without exchange | Service-based manager works outside HTTP |
| Job principal distinct from Alice | User tokens and service identities are not mixed |

**Test limitations:**

- `mockUser` builds a synthetic Authentication per request; it does not verify real Basic passwords or OAuth2 login callbacks.
- `csrf()` injects a valid test CSRF token; it does not prove real HTML/browser token handling.
- The fake provider performs no token requests or refreshes, so these tests do not prove `authorization_code`, PKCE, consent, refresh rotation, token endpoint timeouts, distributed DB persistence, or JWT validation.
- `InMemoryReactiveOAuth2AuthorizedClientService` is a shared store in the test context. The tests above reset state before each test; if **parallel testing** is enabled, isolate contexts/storage or adjust the test mechanism to avoid races.
- Real access token security is not checked because the project intentionally contains no real tokens.

## 12. Replacing the Fake Provider with Real OAuth2 Grants

When integrating with a real IdP, **delete `LearningAuthorizedClientProvider`** and replace the manager configuration with the provider builder:

```java
ReactiveOAuth2AuthorizedClientProvider provider =
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

DefaultReactiveOAuth2AuthorizedClientManager webManager =
        new DefaultReactiveOAuth2AuthorizedClientManager(
                registrations, serverRepository);
webManager.setAuthorizedClientProvider(provider);

AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager jobManager =
        new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClientService);
jobManager.setAuthorizedClientProvider(
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build());
```

This is a **production-oriented fragment**, assuming registrations/repository/service are configured for a real IdP. Do not define two beans with the same names as the demo beans in section 8; replace the configuration rather than pasting them side by side.

### 12.1. Boot Properties Example for client_credentials

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory:
            provider: company-idp
            client-id: inventory-service
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: inventory.read
        provider:
          company-idp:
            token-uri: https://idp.example.test/oauth2/token
```

The value in `${INVENTORY_CLIENT_SECRET}` is resolved by Spring from environment variables or a secrets manager at runtime; **never** place real secrets in Git, READMEs, logs, or exceptions. This URL only describes topology; replace it with a real IdP endpoint over TLS and valid client configuration. Even in sample code above, string placeholders must still resolve at application startup.

To obtain a token from the service-based manager in a job:

```java
return jobManager.authorize(
        OAuth2AuthorizeRequest.withClientRegistrationId("inventory")
                .principal("system:inventory")
                .build()
).switchIfEmpty(Mono.error(
        new IllegalStateException("Token grant not supported")));
```

This is an illustrative fragment inside a service with `jobManager` injected; `principal(String)` is a builder overload to name the principal, not proof of a user login.

### 12.2. authorization_code vs. client_credentials

| Characteristic | authorization_code | client_credentials |
| --- | --- | --- |
| Authority holder | Resource Owner user granting consent | Client application acquiring authority per client registration |
| Browser redirect | Yes, with login/authorization request and callback | No user redirect needed |
| PKCE | Recommended when required by provider/client flow, especially public clients | Not a mechanism of this grant |
| Refresh token | May be present, depending on IdP | Typically unnecessary; request a new access token upon expiry |
| PrincipalName in authorized client | Logged-in/authorizing user | Stable system service principal |
| Sensible manager | Web exchange manager | Service-based manager for background jobs |
| Risk when misused | Alice's token used for Bob | Service permissions broader than user permissions, confused deputy |

Spring Security WebFlux provides `oauth2Login(...)` (user login via OAuth2/OIDC) and `oauth2Client(...)` (Client support); they are related but **do not serve the same purpose**. Client credentials do not create a user session and do not replace authorization on inbound APIs.

### 12.3. application.yml Example for authorization_code

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: company-idp
            client-id: portal-web
            client-secret: ${PORTAL_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile
        provider:
          company-idp:
            issuer-uri: https://idp.example.test
```

This is an **illustrative configuration for a real IdP**, not runnable offline in the lab project. It requires the IdP to publish proper metadata, an exact registered redirect URI, accurate TLS/proxy forwarded headers configuration, client authentication, and PKCE according to client type and IdP policy. In a WebFlux app, `ServerHttpSecurity.oauth2Login(Customizer.withDefaults())` can be configured alongside `oauth2Client(Customizer.withDefaults())` when needed.

### 12.4. When Are Tokens Refreshed?

- An `authorization_code` client with a refresh token: the `refreshToken()` provider can request a new access token.
- `client_credentials`: normally uses the `clientCredentials()` provider to request another access token when near expiry, needing no refresh token.
- When the provider receives `invalid_grant`, the default failure handler can remove the old authorized client; log by error code (never log raw tokens).
- If the token does not yet need renewal, the manager can return the current authorized client without calling the token endpoint.
- Concurrent refreshes across many requests: do not assume the manager/service performs single-flight across a cluster; consider distributed synchronization/caching and metrics in practice.

## 13. Preventing Token Leaks and Principal-Level Security Bugs

### 13.1. Principal Isolation

An authorized client is identified by `registrationId` and `principalName`, not solely by registration name. In multi-tenant systems:

- Do not use `getName()` if it is a mutable email or collides across tenants without a tenant namespace.
- Use an immutable subject ID combined with a verified tenant from `Authentication`.
- Never accept `principalName` from an HTTP query parameter to look up another user's token.
- When users Alice and Bob share registration `crm`, never use Alice's token for Bob's request.
- For `client_credentials`, use a dedicated service identity name; never arbitrarily impersonate a user.

### 13.2. Storage and Secret Handling

Access tokens and refresh tokens are secrets. Ensure:

- Encryption at rest, least-privilege DB permissions, log masking, and secret rotation.
- TTLs, expiration cleanup, and distinguishing local record deletion from remote revocation.
- Never placing tokens in exception messages, response JSON, URL query strings, or unnecessary browser `localStorage`.
- Avoiding a default WebClient configuration that attaches tokens to every hostname/redirect.
- Validating TLS on the token endpoint and Resource Server; never disabling certificate checks in production.
- If tokens are stored in `WebSession`, protect the session store/backups; browser cookies should only hold an opaque session ID, never raw refresh tokens.
- Ensuring secrets are injected solely from the environment or a secrets manager, with no values committed to the repository.

### 13.3. Refresh Token Rotation

The IdP may return a **new refresh token** when an old one is used. The service/repository must save the new authorized client accurately; if custom persistence drops the new refresh token, the session may fail on the next renewal. Handle concurrent refreshes and `invalid_grant` per policy: avoid infinite retries with the same stale refresh token.

### 13.4. Logout Does Not Automatically Revoke Access Tokens

If a user logs out of Spring Security while the authorized client remains stored in the service, tokens may still exist in the app store. Decisions required:

- Delete local authorized clients when a session/user is revoked?
- Call the remote token revocation endpoint if supported by the IdP?
- Is OIDC RP-initiated logout required?
- Keep or remove service-level tokens used by jobs?
- How to invalidate distributed caches?

Do not attach a single `SecurityContextServerLogoutHandler` and claim that `ReactiveOAuth2AuthorizedClientService` automatically deletes every related token.

## 14. Typical Configuration Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Job without HTTP request calls DefaultReactive... | Missing `ServerWebExchange` | Use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| Manager receives wrong registrationId | `ClientRegistration` not found or grant differs | Configure registration properly, test expected grant |
| `authorize(...)` returns `Mono.empty()` | Provider does not support grant or no authorized client exists | Check grant/provider, fail closed; never use a fake permit |
| Service lookup empty while repository has token | Repository stores in WebSession rather than delegating to service | Identify the actual implementation and storage |
| Alice sees Bob's token | Shared `principalName` or client-supplied name | Obtain identity from authenticated SecurityContext |
| Token exists but resource returns 401 | Token expired/revoked/wrong audience | Refresh/re-authorize per policy, validate IdP config |
| Resource returns 403 `insufficient_scope` | Client lacks scope/permission | Configure proper grants/scopes and resource policy |
| Refresh token repeatedly returns `invalid_grant` | Inconsistent rotation/revocation/concurrency | Remove cached invalid client, require reauth if needed |
| Demo POST returns 403 | Missing CSRF token with browser session | Send valid CSRF token; do not carelessly disable CSRF |
| WebClient calls other APIs with Bearer attached | Default client on shared WebClient | Select registration per request, allowlist hosts |
| Netty blocked event loop error | Calling `block()` in WebFlux or blocking JDBC | Compose Mono/Flux, use reactive drivers |
| Handler calls `subscribe()` and returns early | Token acquisition incomplete, context lost | Return the full publisher |
| Tokens lost after restart | `InMemoryReactiveOAuth2AuthorizedClientService` | Use R2DBC or custom persistent storage when needed |
| Multi-instance repeated refreshes | Isolated in-memory caches or lack of coordination | Distributed persistence/caching and bounded retries |
| Secrets written in `application.yml` in Git | Client secret exposed | Env vars, secrets manager, rotation |
| Local logout leaves tokens active | Session deletion does not revoke remote tokens | Design revocation/logout/IdP coordination |
| OAuth2 login callback has wrong host/scheme | Reverse proxy forwarded headers wrong | Trusted Forwarded strategy, public HTTPS |
| Outbound JWT fails with wrong audience | Confusing inbound access token with client token | Separate Resource Server and OAuth2 Client policies |
| Using Servlet `OAuth2AuthorizedClientService` | Wrong synchronous stack | Choose `ReactiveOAuth2AuthorizedClientService` |
| Using one bearer token for all requests | Confused deputy / overprivileged client | Least privilege, principal isolation, scope policy |

## 15. Additional Production Testing Needed

The offline test suite in section 11 does **not** replace real OAuth2 integration tests. Extended checklist:

1. Verify `authorization_code` with browser redirects and callbacks, and state/PKCE/consent per IdP policy.
2. Test `client_credentials` against a sandbox token endpoint you control: client authentication, scopes, and token audience.
3. Mock `invalid_grant` and verify the failure handler removes the old client from the right storage (without deleting the wrong principal).
4. Mock token endpoint timeout/5xx/429 responses: no fallback granting access, bounded retries, and telemetry.
5. Test clock skew, token `expiresAt`, preemptive refresh, rotation, and concurrent requests.
6. Test Alice/Bob under the same registration and across multiple tenants, ensuring no cross-user token leakage.
7. Test the service-based manager running inside a job without a `ServerWebExchange`.
8. Test that `WebClient` attaches Bearer tokens only for allowed hostnames/resources, never on arbitrary redirects or hosts.
9. Test encrypted persistence, R2DBC schema, restarts, multi-instance behavior, and TTL cleanup.
10. Test logout/session invalidation and token revocation separately.
11. Test that the inbound Resource Server does not accidentally rely on client token state to authenticate callers.
12. Test that 401/403/503/timeouts are semantically accurate and do not leak access tokens in logs.

### Distinguishing Test Types

| Test Type | Proves | Does Not Prove |
| --- | --- | --- |
| InMemory service save/load/remove | Storage keyed by registration/principal | Real OAuth2 token validity |
| Mock provider + browser manager | Manager calls provider and persistence | Real Authorization Server token issuance |
| WebTestClient with mockUser + csrf | WebFlux filters, request principal, and CSRF | Real OAuth2 login or cross-origin browser behavior |
| Service manager + StepVerifier | Job requires no HTTP exchange | Secret rotation / IdP token grant |
| Real sandbox token endpoint | HTTP/TLS grant and OAuth2 errors | That Resource Server accepts scope/audience |
| Browser + reverse proxy + IdP | End-to-end login/callback/TLS | Absence of bugs in service data policies |

## 16. Practice Exercises

1. Add a `billing` client registration alongside `sandbox`, and write a test proving each `registrationId` has an independent authorized client.
2. Call POST authorize with `mockUser("alice")` then GET status as Bob: why must it return `"absent"`? What is the storage key?
3. Switch `AuthenticatedPrincipalServerOAuth2AuthorizedClientRepository` to a pure `WebSessionServerOAuth2AuthorizedClientRepository` in a test branch; observe the difference with service lookup.
4. Write a test calling direct service `saveAuthorizedClient(...)` then `loadAuthorizedClient(...)`/`removeAuthorizedClient(...)` without passing `ServerWebExchange`. Explain which applications suit this pattern.
5. Replace the mock provider with `ReactiveOAuth2AuthorizedClientProviderBuilder.builder().clientCredentials().build()`, connecting to a sandbox token endpoint. Explain the expected HTTP exchange.
6. Add an `authorizationCode().refreshToken()` manager and build a real OAuth2 login flow on staging; test user consent, callback, and refresh.
7. Simulate an expired access token and an `invalid_grant` refresh failure: is the record removed or retained? Verify the exact handler for your version.
8. Migrate the service from in-memory to `R2dbcReactiveOAuth2AuthorizedClientService` with the schema from Spring documentation, encrypting tokens when stored.
9. Create two jobs using different service principals and prove they never mix up tokens.
10. Add an outbound `WebClient` request to a mock resource server; use `clientRegistrationId("sandbox")` without sending fake tokens to a real endpoint. Assert the Bearer header via the mock server.
11. Attach the token filter to a shared `WebClient` and try calling an untrusted host; fix it so tokens cannot leak via SSRF/redirects.
12. Redraw the flow: client registration -> manager/provider -> service/repository -> WebClient -> resource server, annotating where tokens can expire or be revoked.
13. Add a test ensuring the production profile does **not** load the `LearningAuthorizedClientProvider` bean, preventing deployment of mock tokens.
14. Compare what happens if a user logs out of the session while the authorized client remains stored in the application service; propose a remove/revoke policy.
15. Explain why `oauth2Client()` is not synonymous with `oauth2Login()` and why an OAuth2 Resource Server needs separate inbound configuration.

## 17. Summary

**The three core concepts represent three distinct responsibilities:**

- `ReactiveOAuth2AuthorizedClientManager` **coordinates**: looks up authorized clients, uses a grant-appropriate provider to obtain/exchange tokens, invokes success/failure handlers, and maintains state via storage.
- `ReactiveOAuth2AuthorizedClientService` **manages at the application level**: saves/reads/removes authorized clients by `registrationId + principalName` without needing an HTTP request; suited to jobs, the service tier, and shared data stores.
- `ServerOAuth2AuthorizedClientRepository` **manages within the WebFlux context**: saves/reads/removes authorized clients by `Authentication + ServerWebExchange`; depending on the implementation, it can store in WebSession or delegate to the application service.

**Choose the right manager:** `DefaultReactiveOAuth2AuthorizedClientManager` when a WebFlux request is present; `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` when running outside `ServerWebExchange`. Never equate a registration with a token, a token with a user identity, or local removal with remote revocation. All tokens must be managed as secrets; outbound `WebClient` calls should only target trusted APIs with appropriate grants, scopes, and principals.

## Official Documentation

- [Spring Security 6.5 — OAuth2 Client Core Interfaces and Classes (reactive)](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html)
- [Spring Security 6.5 — Reactive Authorized Client Features / WebClient](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — OAuth2 WebFlux Client](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html)
- [ReactiveOAuth2AuthorizedClientManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientManager.html)
- [ReactiveOAuth2AuthorizedClientService Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientService.html)
- [ServerOAuth2AuthorizedClientRepository Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/server/ServerOAuth2AuthorizedClientRepository.html)
- [AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager.html)
- [Spring Security — OAuth2 Client Schema](https://docs.spring.io/spring-security/reference/6.5/appendix/database-schema.html)
- [Spring Security 6.5 — Reactive WebClient Test Setup](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
