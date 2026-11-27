# 30.4. mockOAuth2Client() for Calls Using an Authorized Client

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Client** application built with **Spring WebFlux**, whether a request is authenticated and whether the application holds an **authorized access token to call another API** are related yet distinct concerns. A controller may serve a user logged in via OIDC while also needing an `OAuth2AuthorizedClient` for the `reports-api` registration to attach a bearer token to `WebClient`. Another background or BFF flow might use `client_credentials`, without an interactive user login.

When testing a WebFlux controller with a `@RegisteredOAuth2AuthorizedClient` parameter, we **do not need to run a real OpenID Provider, simulate a consent screen, exchange an authorization code, and persist tokens** just so the controller receives an authorized client. Spring Security Test provides **`SecurityMockServerConfigurers.mockOAuth2Client()`** for `WebTestClient`: this mutator supplies a mock `OAuth2AuthorizedClient` in the request exchange context via the test `ServerOAuth2AuthorizedClientRepository` mechanism.

Core example:

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Client;

webTestClient
        .mutateWith(mockOAuth2Client("reports-api"))
        .get()
        .uri("/reports")
        .exchange();
```

However, clearly distinguish **"having an authorized client"** from **"being authenticated"** and from **"a real downstream API allowing access"**. `mockOAuth2Client()` is purely a tool for creating test state; its fake token **is not signed by an OP and is not verified by an Authorization Server**.

> **Principle:** Use `mockOAuth2Client()` when the goal is to test code that **consumes an existing authorized client**. Use `mockOidcLogin()`/`mockOAuth2Login()` to test the **authenticated principal**. If you need to prove `Authorization: Bearer ...` is sent to an API, control/observe the **outbound `WebClient`**. If you need to verify OAuth2 grants, refresh, or OP discovery/ID Token validation, use a different test layer.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain `ClientRegistration`, `OAuth2AuthorizedClient`, `OAuth2AccessToken`, `Authentication`, and where authorized clients are stored in WebFlux.
2. Use `WebTestClient.mutateWith(mockOAuth2Client("registration-id"))` to simulate an authorized client.
3. Know the default fixture data and how to customize `accessToken(...)`, `principalName(...)`, and `clientRegistration(...)`.
4. Test controllers using `@RegisteredOAuth2AuthorizedClient("...")`.
5. Combine an authorized client with `mockOidcLogin()` or `mockOAuth2Login()` when the endpoint requires an authenticated user.
6. Distinguish `mockOAuth2Client()` from `mockJwt()` used for inbound Resource Server authentication.
7. Test `ServerOAuth2AuthorizedClientExchangeFilterFunction` and the `oauth2AuthorizedClient(...)` helper using a downstream HTTP stub.
8. Verify the right bearer token, scope, registration ID, principal name, and behavior with multiple registrations.
9. Respect mock scope boundaries: do not claim token endpoint/refresh/revocation/JWT signature checks were verified.
10. Troubleshoot WebFlux test failures caused by missing `springSecurity()`, wrong repositories, wrong principals, or confusing mocks with real HTTP integration.

## 2. Sample Problem: Portal Calling the Reports API

Suppose the Reports Portal has an endpoint:

```text
GET /reports/summary
```

To fetch the report, the backend calls:

```text
GET https://reports-api.example.org/summary
Authorization: Bearer <access-token>
```

In a real application, the access token lives in an `OAuth2AuthorizedClient` managed by Spring Security keyed by registration ID and principal; it may come from an authorization code login, client credentials, or token refresh.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant SEC as Spring Security WebFlux
    participant C as ReportsController
    participant R as ServerOAuth2AuthorizedClientRepository
    participant W as OAuth2 WebClient Filter
    participant API as Reports API
    B->>SEC: GET /reports/summary (session cookie)
    SEC->>C: Authenticated request context
    C->>R: Resolve authorizedClient("reports-api")
    R-->>C: OAuth2AuthorizedClient + access token
    C->>W: WebClient request with oauth2AuthorizedClient(client)
    W->>API: GET /summary, Authorization: Bearer token
    API-->>W: 200 JSON
    W-->>C: Response body
    C-->>B: 200 JSON/report
```

With `mockOAuth2Client()`, the test **jumps straight to the point where the authorized client already exists**:

```mermaid
flowchart TD
    T["WebTestClient"] --> M["mutateWith(mockOAuth2Client)"]
    M --> S["Mock ServerWebExchange / test session"]
    S --> AR["Test ServerOAuth2AuthorizedClientRepository"]
    AR --> P["Controller @RegisteredOAuth2AuthorizedClient"]
    P --> F["OAuth2 WebClient filter"]
    F --> X["HTTP stub replacing Reports API"]
    X --> A["Assert: right bearer, scope, response"]
```

There is no interactive login with an OP or real token request, unless the application/test configuration itself intentionally triggers another flow.

## 3. Distinguishing Objects in OAuth2 Client

| Component | Example | Role |
|---|---|---|
| `ClientRegistration` | `reports-api` | Client config: registration ID, client ID, grant, endpoints, scopes |
| `OAuth2AccessToken` | `test-reports-token` | Access token and metadata: token type, `issuedAt`, `expiresAt`, scopes |
| `OAuth2AuthorizedClient` | Registration + `principalName` + access token | State of a client authorized for the app to call resources |
| `Authentication` | `OAuth2AuthenticationToken` / authenticated principal | Identifies which request user is authenticated in `SecurityContext` |
| `ServerOAuth2AuthorizedClientRepository` | WebSession-based repository | Stores/loads authorized clients bound to the server exchange |
| `ReactiveOAuth2AuthorizedClientService` | In-memory/JDBC/custom reactive store | Service storing authorized clients at the backend tier |
| `ReactiveOAuth2AuthorizedClientManager` | Manager/provider chain | Authorizes/re-authorizes; may use cache or token endpoint |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | `WebClient` filter | Attaches the appropriate client's bearer token to outbound requests |

### 3.1. `ClientRegistration` Differs from `OAuth2AuthorizedClient`

`ClientRegistration` is only **configuration**:

```text
registrationId = reports-api
clientId       = reports-portal
grant          = authorization_code
tokenUri       = https://idp.example.org/oauth2/token
```

`OAuth2AuthorizedClient` is **the state after a token has been obtained**:

```text
clientRegistration  = reports-api
principalName       = user
accessToken         = test-reports-token
accessToken.scopes  = [reports.read]
```

Having a registration does not mean a token has been issued. `mockOAuth2Client()` lets tests pre-populate an authorized client without going through the grant.

### 3.2. An Authorized Client Is Not `SecurityContext`

`SecurityContext` holds the request's `Authentication`; the authorized client holds tokens for the app to call APIs.

```text
SecurityContext:
  Authentication.principal.name = user
  authorities = [ROLE_USER]

AuthorizedClientRepository:
  (reports-api, user)
    accessToken = test-reports-token
```

A user may be authenticated yet **not have an access token issued for the `reports-api` registration**. Conversely, a backend may hold a service authorized client from `client_credentials` even when the request has no browser-authenticated user.

### 3.3. Registration ID Differs from OAuth2 Client ID

A `registrationId` in tests, such as `reports-api`, is a Spring Security key; whereas `clientId` might be `reports-portal-web` issued by the Authorization Server. Do not pass `clientId` instead of `registrationId` in `@RegisteredOAuth2AuthorizedClient("...")`.

### 3.4. `principalName` Is Part of the Lookup

Authorized clients are typically keyed by **registration ID + principal name**, depending on the repository/service implementation. Tests must therefore watch:

```text
(reports-api, user)   != (reports-api, alice)
(reports-api, alice)  != (inventory-api, alice)
```

If the mock principal is `user` while the controller/manager looks up a token for `alice`, the lookup may miss the client or attempt to start an authorization flow. `principalName("...")` helps test this boundary.

## 4. What Does `mockOAuth2Client()` Actually Do?

Spring Security Test has the overloads:

```java
mockOAuth2Client()
mockOAuth2Client("reports-api")
```

Both return `SecurityMockServerConfigurers.OAuth2ClientMutator`, a configurer for `WebTestClient`. The mutator supports:

```java
.accessToken(OAuth2AccessToken token)
.principalName(String principalName)
.clientRegistration(ClientRegistration registration)
.clientRegistration(Consumer<ClientRegistration.Builder> configurer)
```

It provides an `OAuth2AuthorizedClient` **inside the test `ServerWebExchange`**, via the `ServerOAuth2AuthorizedClientRepository` used by Spring Security Test, so code resolves the client as if it were already saved in session. The token value is **declarative**: it need not be a valid JWT or accepted by an Authorization Server.

### 4.1. Default Data

According to Spring Security Test documentation, the default fixture provides basic values:

| Property | Illustrative default described in docs |
|---|---|
| `ClientRegistration.clientId` | `test-client` |
| `ClientRegistration.clientSecret` | `test-secret` |
| `OAuth2AuthorizedClient.principalName` | `user` |
| `OAuth2AccessToken.scopes` | `read` |
| `registrationId` | Per selected overload/argument |

Do not rely on the fake `test-secret` to verify secret security. And do not rely on the default token string when checking important headers: **explicitly set a fixed token in your test** so assertions are clear.

### 4.2. What the Mutator Does Not Do

`mockOAuth2Client()` **does not**:

- Call an Authorization Server to obtain a token.
- Run authorization code + PKCE + `state` + `nonce`.
- Verify JWT/ID Token signatures.
- Create an authenticated `OidcUser` in all cases.
- Automatically turn a test token into a token trusted by a real downstream API.
- Prove token refresh/revocation or provider exception handling.
- Pre-mock the Reports API's JSON response.
- Guarantee the app is using the right production `ReactiveOAuth2AuthorizedClientService`.

Choose another test layer for those contracts.

## 5. Comparing Related Mutators

| Mutator | What is simulated | When to use |
|---|---|---|
| `mockUser()` | Username/password style `Authentication` in reactive `SecurityContext` | Endpoint only needs principal/roles |
| `mockOAuth2Login()` | `OAuth2AuthenticationToken` and `OAuth2User`; supports authorized client in same flow | Testing OAuth2 Login user |
| `mockOidcLogin()` | `OAuth2AuthenticationToken` and mock `OidcUser`/ID Token | Testing OIDC Login principal/claims |
| **`mockOAuth2Client()`** | **`OAuth2AuthorizedClient` in test repository/session** | **Testing code using an authorized client, regardless of how the user logged in** |
| `mockJwt()` | `JwtAuthenticationToken` for **inbound bearer token** | Testing Resource Server JWT authentication |
| `mockOpaqueToken()` | `BearerTokenAuthentication` for inbound opaque token | Testing Resource Server opaque token |

### 5.1. Illustrative Distinction

```text
Controller needs @AuthenticationPrincipal OidcUser
    -> mockOidcLogin()

Controller needs @RegisteredOAuth2AuthorizedClient("reports-api")
    -> mockOAuth2Client("reports-api")

Controller needs both OidcUser and reports-api token
    -> mockOidcLogin() + mockOAuth2Client("reports-api")

Inbound API protected by Authorization: Bearer JWT
    -> mockJwt()
```

`mockJwt()` proves a Resource Server accepts a mock `JwtAuthenticationToken` in the test; it does not automatically supply an `OAuth2AuthorizedClient` for an outbound `WebClient` to call APIs.

### 5.2. `mockOidcLogin` Can Accompany an Authorized Client

In Spring Security Test, `mockOidcLogin()` and `mockOAuth2Login()` can also prepare an authorized client tied to the login registration, depending on mutator configuration. However, if the controller needs **a different registration** (for example, the user logs in via `company-login` and calls an API via `reports-api`), still declare `mockOAuth2Client("reports-api")` explicitly to test the exact target client.

Do not assume an arbitrary login fixture happens to have the scopes/registration ID the service needs.

## 6. Dependencies for WebFlux Testing

Maven example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
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
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

If using Gradle, the corresponding dependencies:

```gradle
implementation 'org.springframework.boot:spring-boot-starter-webflux'
implementation 'org.springframework.boot:spring-boot-starter-security'
implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.springframework.security:spring-security-test'
```

Normally let Spring Boot manage Spring Security/Spring Test versions via its BOM. Never arbitrarily mix a `spring-security-test` major version different from Spring Security runtime, as test APIs may be incompatible.

### 6.1. Exact Imports

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Client;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Login;
```

This package is **Reactive test support for `WebTestClient`**. Do not mistakenly import similarly named classes from `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors`, which is for Servlet/`MockMvc`.

## 7. Configuring `WebTestClient` with Spring Security

For a test bound directly to `ApplicationContext`:

```java
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

class ReactiveReportTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient
                .bindToApplicationContext(applicationContext)
                .apply(springSecurity())
                .configureClient()
                .build();
    }
}
```

This is the **setup portion** inside a test with an appropriate Spring Test Context (`@SpringBootTest`/`@WebFluxTest` + required beans). `springSecurity()` adds Spring Security test support to the mock-server `WebTestClient` binding, allowing mutators like `mockOAuth2Client()` to be recognized.

### 7.1. Do Not Confuse with a `WebTestClient` Connected to a Real Server

`mockOAuth2Client()` is designed to mutate a **mock `ServerWebExchange`**, not to push an authorized client into the session of a server running over TCP. If you use:

```java
WebTestClient.bindToServer().baseUrl("http://localhost:8080")
```

the mutator may not work or may report unsupported because there is no mock server filter context. To test a live server, use a supported cookie/session/identity setup or a dedicated test provider; do not treat `mutateWith` as a "token injection" endpoint for a real server.

### 7.2. Auto-Configured `WebTestClient`

A Spring Boot test can inject a `WebTestClient` already configured with security test support per test slice/auto-configuration. However, do not assume every `WebTestClient` obtained from `bindToController` or a custom builder automatically has mutator plumbing. If `mockOAuth2Client` appears ineffective, check **the binding strategy and `springSecurity()` setup** before modifying business code.

### 7.3. The Test Context Needs the Right Reactive Stack

If the project has both MVC and WebFlux starters, Spring Boot may choose Servlet application mode by default. For this lesson, you need **WebFlux `ServerHttpSecurity` + `SecurityWebFilterChain`**, not Servlet `HttpSecurity + SecurityFilterChain`.

## 8. Illustrative Controller Reading the Authorized Client

First write a small endpoint to observe the injected object, **without returning the token to the browser**.

```java
import java.util.Set;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation
        .RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

record ClientSummary(
        String registrationId,
        String principalName,
        Set<String> scopes) {}

@RestController
class AuthorizedClientProbeController {

    @GetMapping("/internal/client-summary")
    Mono<ClientSummary> summary(
            @RegisteredOAuth2AuthorizedClient("reports-api")
            OAuth2AuthorizedClient authorizedClient) {

        return Mono.just(new ClientSummary(
                authorizedClient.getClientRegistration()
                        .getRegistrationId(),
                authorizedClient.getPrincipalName(),
                authorizedClient.getAccessToken().getScopes()));
    }
}
```

**Use this endpoint only for tests or protected internal diagnostics.** It does not return the token string, yet principal and scopes can still be sensitive information. Production usually has no reason to expose this data.

Key points to understand:

- `@RegisteredOAuth2AuthorizedClient("reports-api")` instructs Spring Security to resolve the authorized client with that registration ID.
- The parameter is `OAuth2AuthorizedClient`, not `Authentication`.
- The client can be retrieved from the test repository when using the mutator.
- Returning `Mono<ClientSummary>` fits WebFlux without needing `block()`.

### 8.1. Simplest Test

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Client;

class AuthorizedClientProbeTest {

    @Autowired
    WebTestClient client; // Set up with reactive security test support.

    @Test
    void resolvesMockAuthorizedClient() {
        client.mutateWith(mockOAuth2Client("reports-api"))
                .get()
                .uri("/internal/client-summary")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.registrationId").isEqualTo("reports-api")
                .jsonPath("$.principalName").isEqualTo("user")
                .jsonPath("$.scopes[0]").isEqualTo("read");
    }
}
```

This is an **illustrative snippet** inside a test context with the controller/configuration and an accessible endpoint. If the application requires an authenticated request, `mockOAuth2Client()` **alone does not create an `Authentication`**; the test will also need `mockOidcLogin()`/`mockOAuth2Login()` or an appropriate `Authentication` as shown next.

## 9. Protected Endpoint: Combining `mockOidcLogin()` with `mockOAuth2Client()`

In a real Portal, `/reports/summary` typically requires a logged-in user.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/login", "/error")
                        .permitAll()
                        .anyExchange().authenticated())
                .oauth2Login(oauth2 -> {})
                .build();
    }
}
```

Test example:

```java
import org.junit.jupiter.api.Test;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockOAuth2Client;

@Test
void authenticatedOidcUserCanResolveReportsClient() {
    client
        .mutateWith(mockOidcLogin())
        .mutateWith(mockOAuth2Client("reports-api"))
        .get().uri("/internal/client-summary")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.registrationId").isEqualTo("reports-api");
}
```

Roles of the two mutators:

```text
mockOidcLogin():
    Reactive SecurityContext -> mock OidcUser/Authentication

mockOAuth2Client("reports-api"):
    Authorized Client Repository -> mock reports-api token
```

When both are present on the same test request, the controller both passes the `authenticated()` authorization policy and receives the authorized client for the right registration.

### 9.1. Principal Must Match When Required by the Repository

By default, test helpers use principal name `user`. If you set the OIDC subject to `alice` while leaving `mockOAuth2Client()` as `user`, depending on the lookup flow you may observe a mismatch.

Example:

```java
.mutateWith(mockOAuth2Client("reports-api")
        .principalName("alice"))
```

Only pick `alice` if the `Authentication` used in the test also represents `alice` per contract. Never randomly tweak principal strings just to turn a test green without understanding token ownership.

### 9.2. Tests Without Login That Still Have an Authorized Client

A `client_credentials` service usually has no interactive OIDC user. `mockOAuth2Client` can still be used when the endpoint/service is permitted to access the token via another authentication mechanism. However, if the security policy requires `authenticated()`, the request **must still carry a valid `Authentication`** or be permitted by a matcher. That is **endpoint security**, independent of token availability for outbound APIs.

Do not disable `authorizeExchange(...)` app-wide just to resolve a test missing an authenticated principal.

## 10. Customizing Access Token and Scopes

For business logic checking the `reports.read` scope:

```java
import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

OAuth2AccessToken reportsToken = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "test-reports-token",
        Instant.now().minusSeconds(30),
        Instant.now().plusSeconds(3600),
        Set.of("reports.read"));
```

Usage:

```java
client.mutateWith(mockOidcLogin())
      .mutateWith(mockOAuth2Client("reports-api")
              .accessToken(reportsToken))
      .get().uri("/internal/client-summary")
      .exchange()
      .expectStatus().isOk()
      .expectBody()
      .jsonPath("$.scopes[0]").isEqualTo("reports.read");
```

Key points:

- `tokenValue` is a fixture string, not a real JWT.
- `issuedAt` and `expiresAt` are intentional test timestamps.
- `scopes` is metadata that the application can inspect.
- Having `reports.read` on a test token **does not prove a real API will accept the scope**.

### 10.1. Scope Is Access Token Metadata

A user having `ROLE_USER` in `Authentication` does not mean the access token has `reports.read`. Conversely, an access token having `reports.read` does not automatically grant a browser user permission to view every report; the controller/Resource Server must still enforce object-level authorization.

```text
Authentication.authorities:
  ROLE_USER

AuthorizedClient.accessToken.scopes:
  reports.read
```

When testing both, prepare separate fixtures and assert the right policy layer.

### 10.2. Testing Missing Scope

Suppose the controller has:

```java
if (!authorizedClient.getAccessToken()
        .getScopes().contains("reports.read")) {
    return Mono.error(
            new ResponseStatusException(
                    HttpStatus.FORBIDDEN,
                    "Required scope missing"));
}
```

Test:

```java
OAuth2AccessToken insufficientToken = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "test-no-reports-scope",
        Instant.now().minusSeconds(10),
        Instant.now().plusSeconds(3600),
        Set.of("profile"));

client
    .mutateWith(mockOidcLogin())
    .mutateWith(mockOAuth2Client("reports-api")
            .accessToken(insufficientToken))
    .get().uri("/reports/summary")
    .exchange()
    .expectStatus().isForbidden();
```

HTTP 403 is expected **only if the application itself has the scope-checking rule above**. `mockOAuth2Client()` does not automatically block requests missing `reports.read`; tests must verify the actual business validation in the controller/service.

### 10.3. Scope Is Not Automatically a Principal Authority

The mutator puts scopes on `OAuth2AccessToken`. It does not guarantee the principal in `ReactiveSecurityContextHolder` receives `SCOPE_reports.read` as it would from an inbound Resource Server JWT.

If method security has:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
```

that checks authorities on `Authentication`, not scopes directly inside `OAuth2AuthorizedClient`. Tests must configure `Authentication`/authorities accordingly or align the policy with the requirement.

## 11. Customizing `principalName()`

`OAuth2AuthorizedClient.getPrincipalName()` describes the resource owner/service principal to which the client is bound:

```java
client.mutateWith(mockOAuth2Client("reports-api")
        .principalName("service:report-sync"))
      .get().uri("/internal/client-summary")
      .exchange();
```

This case simulates an authorized client for a service task, not necessarily a human OIDC Login.

### 11.1. Keys Must Align

```text
Authorized Client:
  registrationId = reports-api
  principalName  = alice

Authentication:
  name           = alice
```

If code looks up the authorized client by `(reports-api, bob)`, it must not receive Alice's token. This is a critical invariant in multi-user or multi-service applications.

### 11.2. Never Use a Request-Supplied Username

A dangerous anti-pattern:

```java
String principal = exchange.getRequest()
        .getQueryParams().getFirst("user");
// Then load the authorized client for this principal.
```

A user could change `?user=alice` to `?user=bob`. In a real application, the principal must come from a server-trusted `Authentication` or a managed service identity, never from arbitrary browser query/header inputs.

Testing with `principalName("alice")` only confirms the app handles one fixture; preventing cross-user token leakage requires negative tests with user B/another registration.

## 12. Customizing `ClientRegistration`

The mutator lets you override the registration with a builder consumer:

```java
client
    .mutateWith(mockOAuth2Client("reports-api")
        .clientRegistration(builder -> builder
            .clientId("reports-web-test")
            .clientName("Reports API Test Client")))
    .get().uri("/internal/client-summary")
    .exchange();
```

Here the builder starts from the test mutator's default configuration and adjusts supported fields. Specific `ClientRegistration.Builder` methods vary by version and registration type. `clientName` is merely a metadata label; it does not alter token audience or user permissions.

### 12.1. Using a Complete `ClientRegistration`

When a test needs a specific redirect URI, grant type, scopes, token URI, or provider metadata, build an explicit registration:

```java
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

ClientRegistration reportsRegistration =
        ClientRegistration.withRegistrationId("reports-api")
                .clientId("reports-web-test")
                .clientSecret("test-only-not-real-secret")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .authorizationUri(
                        "https://idp.example.invalid/authorize")
                .tokenUri(
                        "https://idp.example.invalid/token")
                .scope("openid", "reports.read")
                .build();

client.mutateWith(mockOAuth2Client()
        .clientRegistration(reportsRegistration))
      .get().uri("/internal/client-summary")
      .exchange();
```

The `example.invalid` URIs are non-network placeholders; `mockOAuth2Client` tests do not execute the authorization code flow. If test code accidentally calls the token endpoint, mock the HTTP layer appropriately rather than pointing URIs to a real provider.

### 12.2. Retrieving `ClientRegistration` from a Reactive Repository

Spring Security docs show the pattern:

```java
@Autowired
ReactiveClientRegistrationRepository registrations;

// In test setup (not a WebFlux request handler):
ClientRegistration registration =
        registrations.findByRegistrationId("reports-api").block();

client.mutateWith(mockOAuth2Client()
        .clientRegistration(registration))
      .get().uri("/reports/summary")
      .exchange();
```

Here `block()` runs **in test setup code** to fetch the fixture, not in a Reactive controller/filter serving requests. In production reactive paths, compose `Mono` instead of calling `block()`.

If `findByRegistrationId(...)` returns empty, the test should fail clearly on missing configuration rather than silently inventing the wrong registration.

### 12.3. Tests Do Not Need a Production Client Secret

Tests may use a fake string such as `test-only-not-real-secret`. Never load production secrets just to make `mockOAuth2Client()` work. Token fixtures and client registrations here are test-only data.

## 13. `WebClient`: Passing the Authorized Client to Outbound Requests

In WebFlux, `ServerOAuth2AuthorizedClientExchangeFilterFunction` can use an `OAuth2AuthorizedClient` passed via request attributes:

```java
import static org.springframework.security.oauth2.client.web.reactive
        .function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction
        .oauth2AuthorizedClient;

@GetMapping("/reports/summary")
Mono<String> getReport(
        @RegisteredOAuth2AuthorizedClient("reports-api")
        OAuth2AuthorizedClient authorizedClient) {

    return reportsWebClient
            .get()
            .uri("/summary")
            .attributes(oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(String.class);
}
```

### 13.1. The Filter Must Be Installed on `WebClient`

`oauth2AuthorizedClient(authorizedClient)` sets an attribute consumed by the OAuth2 `WebClient` filter. If `reportsWebClient` does not attach `ServerOAuth2AuthorizedClientExchangeFilterFunction`, a plain `WebClient` **will not automatically read that attribute or add an `Authorization` header**.

Configuration example:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive
        .function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
WebClient reportsWebClient(
        ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

    var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            authorizedClientManager);

    return WebClient.builder()
            .baseUrl("https://reports-api.example.org")
            .filter(oauth2)
            .build();
}
```

This illustrates Reactive OAuth2 `WebClient` configuration. Depending on the Spring Security version, if you need to handle 401/403 by removing stale authorized clients, you must also configure an appropriate `ReactiveOAuth2AuthorizationFailureHandler`; do not assume the manager constructor automatically includes all cleanup behavior.

### 13.2. Why Use an Explicit Authorized Client?

With:

```java
.attributes(oauth2AuthorizedClient(authorizedClient))
```

the controller makes explicit **which token is chosen for which request**. This is generally safer than enabling:

```java
oauth2.setDefaultOAuth2AuthorizedClient(true);
```

and letting every outbound request on the same `WebClient` pick up the authenticated user's default token. A token could leak to an unintended API/audience if the client is reused carelessly.

### 13.3. Testing Milestone

`mockOAuth2Client()` proves the controller **receives the object**. To prove the token is sent to the API, you must also observe:

```http
GET /summary HTTP/1.1
Host: reports-api.example.org
Authorization: Bearer test-reports-token
```

Do not test by returning the access token to the browser. Use an HTTP stub/`ExchangeFunction` test double at the **outbound boundary**, without sending requests to production APIs.

## 14. Testing Outgoing Bearer Headers with an `ExchangeFunction` Stub

`ExchangeFunction` is the HTTP exchange boundary of `WebClient`. We can replace it with a function that returns a fake response and records the request.

### 14.1. Fake Downstream Exchange

```java
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import reactor.core.publisher.Mono;

AtomicReference<ClientRequest> capturedRequest =
        new AtomicReference<>();

ExchangeFunction downstreamStub = request -> {
    capturedRequest.set(request);
    return Mono.just(
            ClientResponse.create(HttpStatus.OK)
                    .header(
                            HttpHeaders.CONTENT_TYPE,
                            MediaType.TEXT_PLAIN_VALUE)
                    .body("report-ok")
                    .build());
};
```

This pattern sends no network requests. `ClientRequest` holds headers and URL so tests can verify the exact bearer token and target. `AtomicReference` is a test utility; in concurrent tests, isolate fixtures per test to avoid state races.

### 14.2. Attaching the OAuth2 Filter Before the Stub

```java
import org.springframework.security.oauth2.client
        .ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive
        .function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

// Test bean/fixture: manager uses an appropriate test implementation.
ReactiveOAuth2AuthorizedClientManager manager =
        authorizeRequest -> Mono.just(testAuthorizedClient);

WebClient reportsWebClient = WebClient.builder()
        .baseUrl("https://reports-api.example.invalid")
        .filter(
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                        manager))
        .exchangeFunction(downstreamStub)
        .build();
```

`testAuthorizedClient` is an `OAuth2AuthorizedClient` built by the test; the manager above is simply a **Reactive fixture** to avoid calling a token endpoint. This is a snippet of `WebClient` test setup, not a full app test context.

If the controller is injected with a different `WebClient` bean, the test will **not** observe the request. When integrating via `@SpringBootTest`/`@WebFluxTest`, replace the exact `reportsWebClient` bean or inject the stub into it; do not create a `WebClient` unused by the code under test.

### 14.3. Asserting Bearer Token and Destination

Assuming the test invoked the controller:

```java
ClientRequest actual = capturedRequest.get();

assertThat(actual).isNotNull();
assertThat(actual.url().getHost())
        .isEqualTo("reports-api.example.invalid");
assertThat(actual.headers().getFirst(HttpHeaders.AUTHORIZATION))
        .isEqualTo("Bearer test-reports-token");
```

Set the access token via `mockOAuth2Client("reports-api").accessToken(...)` on the `WebTestClient` request to wire the right fixture through the controller. Never use real access tokens in assertions.

### 14.4. A Concise Option: Testing the `WebClient` Filter Separately

Before full controller integration, you can test the filter directly:

```java
OAuth2AuthorizedClient authorizedClient = testAuthorizedClient;

String body = reportsWebClient.get()
        .uri("/summary")
        .attributes(oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class)
        .block(); // Only in unit/integration TESTS.

assertThat(body).isEqualTo("report-ok");
assertThat(capturedRequest.get().headers()
        .getFirst(HttpHeaders.AUTHORIZATION))
        .isEqualTo("Bearer test-reports-token");
```

This tests **`WebClient` bearer forwarding** without `mockOAuth2Client()`, since there is no incoming `ServerWebExchange`. The two test levels complement each other:

1. `WebTestClient + mockOAuth2Client`: argument resolution on the inbound controller.
2. `WebClient + ExchangeFunction stub`: outbound `Authorization` header.
3. Integration test combining both: controller resolves client from mock repository and passes it through the filter.

### 14.5. Distinguishing a Stub Manager from `mockOAuth2Client`

If you use:

```java
ReactiveOAuth2AuthorizedClientManager manager =
        authorizeRequest -> Mono.just(testAuthorizedClient);
```

the fixture manager may return a client even when no repository entry exists. A test relying **solely** on such a fake manager does not prove `@RegisteredOAuth2AuthorizedClient` resolved the right registration from the repository. Match assertions to your test goal and avoid letting a fake manager mask missing authorized-client errors in primary tests.

## 15. Sample Test Suite: Only Valid Scopes Call the Reports API

A fuller controller:

```java
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation
        .RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ResponseStatusException;
import reactor.core.publisher.Mono;

@RestController
class ReportsController {

    private final WebClient reportsWebClient;

    ReportsController(WebClient reportsWebClient) {
        this.reportsWebClient = reportsWebClient;
    }

    @GetMapping("/reports/summary")
    Mono<String> summary(
            @RegisteredOAuth2AuthorizedClient("reports-api")
            OAuth2AuthorizedClient authorizedClient) {

        if (!authorizedClient.getAccessToken().getScopes()
                .contains("reports.read")) {
            return Mono.error(new ResponseStatusException(
                    HttpStatus.FORBIDDEN,
                    "Missing reports.read scope"));
        }

        return reportsWebClient.get()
                .uri("/summary")
                .attributes(oauth2AuthorizedClient(authorizedClient))
                .retrieve()
                .bodyToMono(String.class);
    }
}
```

The snippet needs the static import of `oauth2AuthorizedClient` (as in section 13) and the right `WebClient` bean. If the application has multiple `WebClient` beans, use `@Qualifier("reportsWebClient")` or explicit constructor injection instead of relying on arbitrary selection.

### 15.1. Happy Path

```java
OAuth2AccessToken readToken = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "test-reports-token",
        Instant.now().minusSeconds(30),
        Instant.now().plusSeconds(3600),
        Set.of("reports.read"));

client.mutateWith(mockOidcLogin())
      .mutateWith(mockOAuth2Client("reports-api")
              .accessToken(readToken))
      .get().uri("/reports/summary")
      .exchange()
      .expectStatus().isOk()
      .expectBody(String.class).isEqualTo("report-ok");
```

For the test to truly pass, inject `reportsWebClient` backed by a fake downstream response `"report-ok"` and an appropriate `SecurityWebFilterChain`.

### 15.2. Missing Scope

```java
OAuth2AccessToken noReadScope = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "test-no-scope",
        Instant.now().minusSeconds(30),
        Instant.now().plusSeconds(3600),
        Set.of("profile"));

client.mutateWith(mockOidcLogin())
      .mutateWith(mockOAuth2Client("reports-api")
              .accessToken(noReadScope))
      .get().uri("/reports/summary")
      .exchange()
      .expectStatus().isForbidden();
```

If using `capturedRequest`, assert **`downstreamStub` was not invoked**. Asserting 403 alone does not prove the controller did not send the token in a side effect before checking the scope.

### 15.3. No `Authentication`

```java
client.mutateWith(mockOAuth2Client("reports-api")
        .accessToken(readToken))
      .get().uri("/reports/summary")
      .exchange()
      .expectStatus().is3xxRedirection();
```

Expecting a redirect fits **when the application's security entry point is an OIDC Login redirect**. With an API-first configuration, the response may be 401. The key assertion is that the request **is not accepted merely because a test authorized client exists** when the route requires an authenticated user.

## 16. When to Use `mockOAuth2Client()` vs. Mocking `WebClient`

The two test doubles sit at two different boundaries:

| Boundary | How to test | What is proven |
|---|---|---|
| Incoming WebFlux request | `WebTestClient + mockOAuth2Client` | Controller/resolver obtains the authorized client |
| Authenticated user | `mockOidcLogin`/`mockOAuth2Login` | `SecurityContext`/authorities/claims in request |
| Authorized client manager | Fake/mock `ReactiveOAuth2AuthorizedClientManager` | Service requests the right registration/principal/context |
| Outbound HTTP to API | Stub `ExchangeFunction`, WireMock/MockWebServer | Bearer header/URL/method/body/status |
| Token endpoint | Fake Authorization Server/token server | Grant requests, token parsing, errors, retries |
| OIDC Login end-to-end | Test OP/discovery/JWKS/callback server | `state`, `nonce`, code exchange, ID Token validation |

If the controller only returns data read from the authorized client, no HTTP stub is needed. If the controller calls a downstream API, `mockOAuth2Client()` **does not** automatically make the API return 200; you must still mock the network boundary.

### 16.1. Testing with a Mock Manager

When logic calls:

```java
authorizedClientManager.authorize(
        OAuth2AuthorizeRequest.withClientRegistrationId("inventory-api")
                .principal("service:import")
                .build())
```

you may need to mock/fake the manager to verify the exact `registrationId`/principal rather than only using `mockOAuth2Client` on the inbound request. On WebFlux, the actual reactive method is `ReactiveOAuth2AuthorizedClientManager.authorize(OAuth2AuthorizeRequest)` returning `Mono<OAuth2AuthorizedClient>`.

Do not confuse the **Servlet** manager (`OAuth2AuthorizedClientManager`) with the **Reactive** manager.

### 16.2. Testing `client_credentials` Flow

`client_credentials` typically has a service principal, without a human OIDC user. `mockOAuth2Client("inventory-api").principalName("service:import")` works when the method receives **an already-issued authorized client**. If the method **requests a new token itself** via the manager, mocking only the inbound client is insufficient; fake the manager/token response client or stand up a test Authorization Server.

## 17. Multiple Registrations: Never Send the Wrong Token

A Portal may have:

```text
reports-api:
  access token: test-reports-token
  audience: reports-api

inventory-api:
  access token: test-inventory-token
  audience: inventory-api
```

When a controller calls the Reports API, it must never use the Inventory API token just because both clients belong to the same user.

### 17.1. Creating Two Authorized Clients in a Test

```java
var reports = mockOAuth2Client("reports-api")
        .principalName("user")
        .accessToken(new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "test-reports-token",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(3600),
                Set.of("reports.read")));

var inventory = mockOAuth2Client("inventory-api")
        .principalName("user")
        .accessToken(new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "test-inventory-token",
                Instant.now().minusSeconds(30),
                Instant.now().plusSeconds(3600),
                Set.of("inventory.read")));

client.mutateWith(mockOidcLogin())
      .mutateWith(reports)
      .mutateWith(inventory)
      .get().uri("/reports/summary")
      .exchange();
```

This pattern demonstrates multiple client fixtures. Behavior when multiple mutators are applied to the same exchange depends on test plumbing and session repository handling; verify via test assertions and avoid sharing global clients/sessions across tests. If the project uses another custom repository, seed fixtures through that repository directly.

### 17.2. Assert the Exact Header

```text
GET Reports API
  Authorization: Bearer test-reports-token

Must NOT be:
  Authorization: Bearer test-inventory-token
```

Do not check only the response body. If the HTTP stub always returns 200 regardless of headers, a registration selection bug can still slip through.

### 17.3. Risk of Default Authorized Client

If `ServerOAuth2AuthorizedClientExchangeFilterFunction` is configured to use a default authorized client, a `WebClient` shared across multiple hosts could send a user token to an unintended endpoint. Security tests should check:

- API A receives token A.
- API B receives token B or no token.
- A browser-supplied URL is never permitted to receive a bearer token.
- Missing registration/authorized client **fails closed**, without falling back to a global service token.

## 18. With Multi-Tenant Apps, `principalName` Must Be Meaningful

Suppose North and South share an OAuth2 provider:

```text
tenant North -> reports-north -> North token
tenant South -> reports-south -> South token
```

Tests need to confirm:

1. A North tenant request selects `reports-north`.
2. The North token only goes to the Reports North API.
3. A North user cannot change `?tenant=south` and obtain the South client.
4. Principal names or storage keys do not collide in a way that leaks tokens cross-tenant.
5. The Resource Server validates audience/tenant itself, rather than blindly trusting a Portal-added header.

`mockOAuth2Client()` helps construct fixtures; it **does not perform tenant authorization**.

### 18.1. `(issuer, subject)` Pair

If OIDC Logins from two different issuers share the same `sub`, they must never be treated as the same user. When testing an authorized client keyed by `principalName`, understand whether the application maps external identities by `(iss, sub)`.

A fixed fake `principalName` `"user"` is convenient for testing a controller, but it does not prove production storage is safe across multiple tenants/providers.

### 18.2. Testing Token Storage Isolation

If a custom `ReactiveOAuth2AuthorizedClientService` uses Redis/JDBC with tenant namespaces, test that service/store separately. The `mockOAuth2Client()` mutator uses a test repository and does not replace integration tests for production storage schemas, encryption, refresh token rotation, and key lookup.

## 19. Expired Tokens and Refresh: Limitations of `mockOAuth2Client()`

An `OAuth2AuthorizedClient` holds an access token and optionally a refresh token. When a token is about to expire, `ReactiveOAuth2AuthorizedClientManager` or the `WebClient` filter may attempt to re-authorize/refresh depending on configuration.

### 19.1. Valid Tokens: Suitable for Forwarding Tests

In this lesson, token fixtures usually use:

```java
Instant.now().plusSeconds(3600)
```

to avoid accidentally triggering a refresh when the test goal is simply attaching a bearer header. This keeps tests simple and isolated from the network.

### 19.2. Expired Tokens: A Different Test

```java
OAuth2AccessToken expired = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "expired-test-token",
        Instant.now().minusSeconds(3600),
        Instant.now().minusSeconds(30),
        Set.of("reports.read"));
```

Putting an expired token in `mockOAuth2Client` alone **is not enough** to prove refresh works. To test refresh:

- The authorized client must have an appropriate refresh token.
- A `ReactiveOAuth2AuthorizedClientManager`/provider chain supporting `refresh_token` must be active.
- The token response client must be stubbed to return a new token or an error.
- Persistence/repository must be tested to verify the new token is stored/read correctly.
- Test concurrent refresh and `invalid_grant` separately if required by business rules.

Never call a real OP or use production refresh tokens just to write tests.

### 19.3. No Refresh Token

If the authorized client has no refresh token, `WebClient`/manager cannot refresh via the `refresh_token` grant; the flow may require reauthorization. Behavior depends on the authorized client provider chain and login/client credentials configuration, not on `mockOAuth2Client`.

### 19.4. What Cannot Be Concluded

A test with `mockOAuth2Client("reports-api").accessToken(expired)` where the controller still returns 200 does not prove the Token Endpoint renewed the token; a fake manager may have returned another client or the stub API may have ignored authorization. Place assertions at the right points: token exchange call, resulting token, storage update, and downstream header.

## 20. `OAuth2AuthorizedClientRepository` in WebFlux Tests

`ServerOAuth2AuthorizedClientRepository` binds `OAuth2AuthorizedClient` to `ServerWebExchange` (typically `WebSession`). `mockOAuth2Client()` uses the test mechanism to supply the client for the exchange being processed.

### 20.1. Do Not Confuse with `ReactiveOAuth2AuthorizedClientService`

There are two abstractions:

```text
ServerOAuth2AuthorizedClientRepository
  - bound to ServerWebExchange and Authentication
  - suited for request/session-aware WebFlux

ReactiveOAuth2AuthorizedClientService
  - load/save/remove by registration + principal
  - suited for backend stores and service-level access
```

If the real app only uses a custom `ReactiveOAuth2AuthorizedClientService`, yet the test injects an authorized client into a different test repository, tests may pass while production queries the wrong store. When testing the contract of a custom service/manager, mock/inject that exact implementation.

### 20.2. `@RegisteredOAuth2AuthorizedClient` Resolution

The annotation relies on the OAuth2 Client argument resolver and appropriate authorized client infrastructure. A test can fail if:

- `SecurityWebFilterChain`/OAuth2 Client integration is not configured.
- The test context lacks the needed resolver/registration.
- The registration ID does not match.
- The test repository entry was not attached to the same exchange.
- The principal/authentication differs from the entry.
- The app uses a custom resolver that does not read the test repository.

Never "fix" this by switching the controller to `@RequestParam("access_token")`. Bearer tokens must not be accepted arbitrarily from browser query parameters.

### 20.3. With `bindToController` Tests

`WebTestClient.bindToController(new Controller(...))` may lack `HandlerMethodArgumentResolver`s from OAuth2 Client configuration unless you register the corresponding WebFlux security/application context. For `@RegisteredOAuth2AuthorizedClient`, the most reliable approach is usually `bindToApplicationContext(context).apply(springSecurity())` with the module's real/necessary beans.

If you intentionally build a narrow slice, register the argument resolvers/filters and authorized client repository explicitly.

## 21. `WebTestClient` and Annotation Authorization

In an application with method security:

```java
@PreAuthorize("hasRole('REPORT_VIEWER')")
@GetMapping("/reports/summary")
Mono<String> summary(...) { ... }
```

`mockOAuth2Client()` does not automatically grant `ROLE_REPORT_VIEWER` to `Authentication`. The test needs:

```java
client.mutateWith(mockOidcLogin()
        .authorities(
                new SimpleGrantedAuthority("ROLE_REPORT_VIEWER")))
      .mutateWith(mockOAuth2Client("reports-api")
              .accessToken(readToken))
      .get().uri("/reports/summary")
      .exchange();
```

`mockOidcLogin().authorities(...)` is the mutator API for customizing the `Authentication` principal/authorities in Spring Security Test. You must also enable Reactive method security on the application/test context when testing `@PreAuthorize`.

Do not confuse:

```text
ROLE_REPORT_VIEWER in Authentication
    -> Portal web/method authorization

reports.read scope on authorized client token
    -> permission evaluated by the downstream API
```

Both control layers may need to be satisfied together.

## 22. Negative Tests You Should Not Skip

### 22.1. Wrong Registration

```text
Controller requires @RegisteredOAuth2AuthorizedClient("reports-api")
Test only prepares inventory-api
```

Expectations depend on infrastructure: missing client, error/redirect to start authorization, or manager attempting to acquire a new token. In isolated tests, configure the manager/provider so it **does not unintentionally call an OP**. The key assertion is **never sending the Inventory token to the Reports API**.

### 22.2. Wrong Principal

```text
Authenticated user = alice
AuthorizedClient stored for bob
```

The system must never let Alice retrieve Bob's token from the repository/service. Test production storage/resolution and multi-user separation separately, as an in-memory fake manager returning a fixed client can mask bugs.

### 22.3. Missing Scope

An access token lacking `reports.read` must be handled per policy. If the Portal does not check the scope itself and the downstream API returns 403, the stub API in tests should simulate 403 rather than always returning success.

### 22.4. Downstream 401

An API returning 401 can trigger failure handling/removal of the authorized client depending on `ServerOAuth2AuthorizedClientExchangeFilterFunction` configuration. To test:

1. Stub the API to return 401 (with an appropriate OAuth2 error header when needed).
2. Verify the Portal's response matches the error mapping contract.
3. If a failure handler is configured, verify it is invoked and removes the right authorized client.
4. Do not assume every 401 removes the client; it depends on the failure handler and error payload.

### 22.5. Downstream 403

403 typically indicates insufficient permissions/scopes/resource policy, not an expired token. Never let the manager retry token acquisition indefinitely just because the API returns 403. In tests, verify error mapping, auditing, and zero token leakage.

### 22.6. Downstream 5xx/Timeout

`mockOAuth2Client()` only creates the token; the test HTTP stub must return 5xx or a timeout/error publisher to test retries, fallbacks, and exception handling. Use `StepVerifier`/virtual time in service-level tests if Reactor retry/backoff is used to avoid real waits.

### 22.7. Missing Authorized Client

If an endpoint requires an authorized client yet none is injected, choose expected behavior per contract. Do not cause a null dereference and expect 500 everywhere; the app should have explicit error handling or valid reauthorization management.

### 22.8. Protecting Tokens from Being Sent to Wrong Hosts

Test with a fake non-allowlisted URL:

```text
GET /proxy?target=https://untrusted.example.invalid
```

Endpoints must never let the browser pick an arbitrary destination and forward a bearer token; `ServerOAuth2AuthorizedClientExchangeFilterFunction` will attach the token to requests created by your code if you pass the authorized client. Test host allowlists/URI construction separately.

## 23. Recommended Test Matrix

| Test | `Authentication` | Authorized client | Downstream stub | Expected |
|---|---|---|---|---|
| Happy path | `mockOidcLogin()` | `mockOAuth2Client("reports-api")` with right scope | 200 | API called with right bearer |
| Anonymous | None | Test client present | Not called | 401/302 per security entry point |
| Authenticated without client | Present | None | Not called or fake authorize flow | Clear missing-client behavior |
| Wrong registration | Present | `inventory-api` | Reports not called with Inventory token | No token leak |
| Wrong principal | Alice | Bob's client | Bob's token not used | Denied/not resolved |
| Missing scope | Present | Token with only `profile` | Not called or API 403 | 403 per policy |
| Valid scope | Present | Token with `reports.read` | 200 | Data succeeds |
| API returns 401 | Present | Test-valid token | 401 + OAuth error | Proper failure handler/error mapping |
| API returns 403 | Present | Valid token | 403 | Not turned into login success |
| API timeout | Present | Valid token | `Mono.error`/timeout | Error contract and retry budget |
| Expired token | Present | Expired token | Dedicated fake token client | Separate refresh/re-auth test |
| Multiple clients | Present | Reports + Inventory | Stub verifies per host | No cross-bearer leak |
| Multi-tenant | Present | North + South | Stub verifies tenant API | No cross-tenant leak |
| Client credentials | Service authentication/policy | Service authorized client | 200 | Uses right service token |
| Test isolation | Per-request fixtures | Per-test repository state | Per-test stub | No leak across tests |

Do not write only one happy-path test; the most dangerous OAuth2 Client bugs usually involve **selecting the wrong registration, principal, or outbound destination**.

## 24. Common Issues with Timing and Reactive Context

### 24.1. Do Not Block in Handlers

Do not do:

```java
// Do NOT use in a Reactive controller:
OAuth2AuthorizedClient client = manager
        .authorize(request)
        .block();
```

In the application, compose with `Mono`/`flatMap`. In a short **test setup**, calling `block()` to fetch a `ClientRegistration` from a test repository is acceptable per documentation examples, but never copy it into production request paths.

### 24.2. Do Not Set `Authorization` Header Directly on Inbound `WebTestClient`

```java
client.get()
      .header(HttpHeaders.AUTHORIZATION, "Bearer test-reports-token")
      .uri("/reports/summary")
```

This is an **inbound HTTP `Authorization` header** from the browser to the Portal. It can be used when testing a Resource Server, but it is **not** how you create an `OAuth2AuthorizedClient` for outbound tokens. When the Portal uses an OIDC browser session and needs `WebClient` to call APIs on the user's behalf, mock the client repository/manager properly.

### 24.3. `ReactiveSecurityContextHolder` Is Not a Regular `ThreadLocal`

`ReactiveSecurityContextHolder` relies on the Reactor Context; do not use `SecurityContextHolder.getContext()` in reactive callbacks and assume a user is always present. `mockOidcLogin()` prepares `Authentication` via the Reactive test mechanism, while `mockOAuth2Client()` prepares client state via the exchange/repository. Propagate context properly through `Mono`/`Flux`.

### 24.4. Subscription and Cancellation

If a `WebClient` request is canceled before the exchange completes, the HTTP stub or manager may not be invoked. When verifying interactions, always subscribe via `WebTestClient.exchange()`/`StepVerifier.verify()` rather than merely constructing a `Mono`.

### 24.5. Tokens Near Expiration

Some OAuth2 authorized client managers treat a token as "expiring soon" before `expiresAt` based on default clock skew. In forwarding tests, set `expiresAt` far enough in the future (e.g., +1 hour) to avoid accidentally triggering a refresh.

### 24.6. Fixed Clock for Expiry Tests

For tests specifically covering token expiration/refresh, use `Clock.fixed(...)` or clock abstractions on components instead of relying on wall-clock time and `Thread.sleep()`. `mockOAuth2Client` does not control the clock of the OAuth2 provider chain.

## 25. Using Kotlin in WebFlux Tests

In Kotlin, static imports and mutator calls look similar:

```kotlin
import org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Client
import org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin

@Test
fun reportClientIsAvailable() {
    webTestClient
        .mutateWith(mockOidcLogin())
        .mutateWith(mockOAuth2Client("reports-api"))
        .get()
        .uri("/internal/client-summary")
        .exchange()
        .expectStatus().isOk
        .expectBody()
        .jsonPath("$.registrationId").isEqualTo("reports-api")
}
```

This Kotlin example assumes `WebTestClient` and the test context are configured with Spring Security. If the endpoint checks non-default scopes, customize `OAuth2AccessToken` just as in Java. Java builder APIs can be called directly from Kotlin or wrapped in helpers for fixture reuse.

### 25.1. Reusable Test Fixture Builder

A test-layer helper can build tokens:

```java
static OAuth2AccessToken testAccessToken(
        String value, String... scopes) {

    return new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            value,
            Instant.now().minusSeconds(30),
            Instant.now().plusSeconds(3600),
            Set.of(scopes));
}
```

Use a distinguishable fake string for `value`. Never create values matching real tokens and never embed production secrets in fixtures.

### 25.2. Helpers Must Not Switch Registration Based on Browser Input

Reusing fixtures is good, but avoid helpers like:

```java
mockOAuth2Client(request.getQueryParams()
        .getFirst("registrationId"))
```

because that leads tests to assert client-chosen registrations are valid without allowlist checks. In production, registrations must be chosen by verified policy.

## 26. When Tests Are Green Yet Production Fails

`mockOAuth2Client()` **deliberately skips** many external dependencies, so a passing controller test does not guarantee complete integration.

| Production failure | Why mock tests miss it | Complementary test |
|---|---|---|
| `redirect_uri_mismatch` | No OIDC authorization redirect | Authorization Request/OP test |
| `invalid_state` | Real callback/authorization request repository not run | OIDC Login integration test |
| Wrong client secret | Token endpoint not called | Token HTTP client/OP stub |
| Truststore/PKIX error | No TLS handshake to OP | TLS client integration test |
| Invalid ID Token issuer/signature | Mock token is declarative | OIDC decoder/JWKS test |
| Refresh token `invalid_grant` | Mock pre-supplies non-expired access token | Refresh provider/manager integration test |
| Authorized client not saved in Redis/JDBC | Uses dedicated test repository | Storage/manager integration test |
| Wrong token audience at Reports API | API stub does not validate token | Resource Server integration/contract test |
| Token sent to wrong host | Stub does not assert URL/header | Outbound request assertion |
| Logout does not remove token | Mutator only seeds fixture | Logout + repository/revocation test |
| Two concurrent requests refresh same RT | No concurrency/rotation | Concurrent manager/token store test |

This is not a flaw of the mock. Its purpose is to **isolate controllers/services that use authorized clients**, keeping tests fast, stable, and free of external identity infrastructure.

## 27. Diagnosing Failures in `WebTestClient`

| Symptom | Common cause | Resolution |
|---|---|---|
| `mockOAuth2Client` not found | Missing `spring-security-test` or imported Servlet test API | Add test dependency, import `SecurityMockServerConfigurers` |
| Mutator not applied | `WebTestClient` uses `bindToServer` or lacks mock security test plumbing | Use `bindToApplicationContext` + `springSecurity()` |
| `@RegisteredOAuth2AuthorizedClient` is null/unresolved | Mismatched registration ID or missing resolver/repository | Check `reports-api`, OAuth2 Client config, and `WebTestClient` binding |
| Endpoint returns 302/401 despite client | Missing authenticated principal | Add `mockOidcLogin()`/`mockOAuth2Login()` per policy |
| Endpoint returns 403 | Missing authorities or business scopes | Distinguish `Authentication` authorities from token scopes |
| `WebClient` does not send Bearer | Missing OAuth2 filter or request attribute | Attach `ServerOAuth2AuthorizedClientExchangeFilterFunction` and `oauth2AuthorizedClient` |
| `WebClient` sends wrong Bearer | Wrong default client/registration selected | Use explicit authorized client, assert header and URL |
| Test accidentally calls real OP | Manager/argument resolver tries to acquire token | Fake manager/token response client or add proper client fixture |
| Test still misses token despite mutate | Controller uses custom service instead of test repository | Inject/mock the actual storage/manager |
| Scope test mismatches | Default token fixture only has `read` | Use `accessToken(...)` with needed scopes |
| Unexpected token refresh | `expiresAt` too close or in the past | Use long-lived test token or stub refresh path |
| Multiple tests interfere | Shared mutable repository, mock server, `capturedRequest` | Create per-test fixtures, reset stubs |
| HTTP client returns 200 but token unverified | Stub does not check bearer | Assert `Authorization` header on outbound request |
| Test uses `mockJwt` when controller needs authorized client | Inbound JWT differs from OAuth2 client token | Use the right mutator |
| Client exists but wrong `principalName` | `Authentication` name and stored client owner differ | Use `principalName(...)`/check identity |
| Tests pass individually, fail in suite | Test order/parallel session or mutable bean state | Isolate test context and fake stores |

### 27.1. Diagnostic Flowchart

```mermaid
flowchart TD
    A["Test using mockOAuth2Client fails"] --> B{"WebTestClient mock binding correct?"}
    B -- No --> C["bindToApplicationContext + springSecurity()"]
    B -- Yes --> D{"Request passes authorization policy?"}
    D -- No --> E["mockOidcLogin / authorities / CSRF if applicable"]
    D -- Yes --> F{"Controller resolves right registration/principal?"}
    F -- No --> G["Check @RegisteredOAuth2AuthorizedClient and repository"]
    F -- Yes --> H{"WebClient has OAuth2 filter and attributes?"}
    H -- No --> I["Attach filter, pass explicit authorized client"]
    H -- Yes --> J{"Stub observes right Bearer header?"}
    J -- No --> K["Check token expiry, manager, client selection"]
    J -- Yes --> L{"API stub response/contract correct?"}
    L -- No --> M["Status, body, error mapping, timeout/retry"]
    L -- Yes --> N["Test passing: matches contract under test"]
```

## 28. Common Mistakes

1. **Treating `mockOAuth2Client()` as a mock OIDC Login**, when it only creates an authorized client.
2. **Using `mockJwt()` to create an outbound token**, confusing Resource Server with OAuth2 Client.
3. **Creating only a `ClientRegistration` and expecting the controller to have an access token**, forgetting the authorized client.
4. **Setting the wrong `registrationId`** (confusing it with `clientId`/provider ID).
5. **Testing only the happy path with default scope `read`**, overlooking business scopes.
6. **Believing access token scopes automatically become `GrantedAuthority` instances in `Authentication`**.
7. **Forgetting `mockOidcLogin()` when the endpoint requires an authenticated user**.
8. **Using one fake `principalName` for all users/tenants** and skipping cross-user token isolation.
9. **Asserting only status 200**, without verifying the outgoing `Authorization: Bearer ...`.
10. **Setting a token on inbound `WebTestClient.header("Authorization", ...)`** and thinking it creates an authorized client.
11. **Forgetting the OAuth2 `WebClient` filter**, rendering the `oauth2AuthorizedClient(...)` attribute ineffective.
12. **Using a default `OAuth2AuthorizedClient` for every `WebClient` request**, risking bearer leakage.
13. **Configuring a different `WebClient` bean in tests than the one injected into the controller**, bypassing the stub.
14. **Using an expired token for forwarding tests**, inadvertently triggering refresh.
15. **Letting tests call a production OP/token endpoint** to "get a real token".
16. **Expecting mock tests to verify ID Token/JWT signatures or PKCE**, exceeding the tool's scope.
17. **Confusing `ServerOAuth2AuthorizedClientRepository` with `ReactiveOAuth2AuthorizedClientService`**.
18. **Forgetting to apply `springSecurity()` to mock `WebTestClient` bindings** when building the client manually.
19. **Using `bindToServer()` and expecting mutators to inject into a real session**.
20. **Calling `block()` inside a Reactive controller** to fetch an authorized client.
21. **Ignoring downstream 401/403/timeouts**, stubbing only HTTP 200.
22. **Treating fake test tokens as real credentials** and sending them over the network.
23. **Not resetting mocks/captured HTTP requests between tests**, creating flaky tests.
24. **Not testing security context checks when using an authorized client**, leaving endpoints open to anonymous access.

## 29. Hands-On Exercises

### Exercise 1: Reading the Authorized Client

Create a WebFlux endpoint:

```text
GET /client/info
-> returns registrationId and scopes (does not return the token)
```

Write a test using `mockOAuth2Client("reports-api")` and assert the registration ID.

### Exercise 2: Checking Scope

Replace the access token with one carrying `reports.read`, then with one carrying only `profile`. Verify the controller only allows requests with the required scope; do not rely on the default `read` scope.

### Exercise 3: Combining with OIDC Login

Configure `anyExchange().authenticated()`. Demonstrate that:

1. `mockOAuth2Client` alone does not make the request authenticated.
2. Adding `mockOidcLogin()` lets the request pass the security policy.
3. Authorized client resolution remains independent of authorities.

### Exercise 4: Verifying Outbound Bearer

Replace the Reports API with a fake `ExchangeFunction` or HTTP stub. Verify:

```text
Authorization: Bearer test-reports-token
Host = reports-api.example.invalid
Response body = report-ok
```

Do not expose the token string via the inbound response for testing.

### Exercise 5: Multiple Registrations

Create `reports-api` and `inventory-api` with distinct token strings. Verify Reports requests only use the Reports token, even when both share `principalName` `user`.

### Exercise 6: Token Refresh

Create an expired authorized client and a fake `ReactiveOAuth2AuthorizedClientManager`/token response client. Verify the token refresh is requested exactly once, the new token appears in the outbound request, and storage updates per policy. Do not treat an expired access token fixture alone as proof of refresh.

## 30. Review Questions

1. How does `OAuth2AuthorizedClient` differ from `ClientRegistration` and `Authentication`?
2. Why is `mockOAuth2Client()` suited for testing `@RegisteredOAuth2AuthorizedClient`?
3. Where does `mockOAuth2Client("reports-api")` store the authorized client in a Reactive test?
4. What are the four key customization methods on `OAuth2ClientMutator`?
5. What default values are documented by Spring Security Test?
6. Why do the client secret/token in a fixture not need to be issued or signed by an OP?
7. Why does `mockOAuth2Client()` not automatically grant access to an `authenticated()` endpoint?
8. When should `mockOidcLogin()` and `mockOAuth2Client()` be combined?
9. Is `mockJwt()` used for inbound JWTs or outbound `OAuth2AuthorizedClient`?
10. Why shouldn't you set the `Authorization` header on `WebTestClient` to mock an outbound token?
11. Does `@RegisteredOAuth2AuthorizedClient("reports-api")` take a client ID or a registration ID?
12. How does `principalName("alice")` affect authorized client lookup?
13. How does the `reports.read` scope on an access token differ from `ROLE_REPORT_VIEWER` on `Authentication`?
14. Why should you use `accessToken(...)` instead of the default `read` when testing business logic?
15. What does `oauth2AuthorizedClient(authorizedClient)` do inside `WebClient.attributes(...)`?
16. If `WebClient` lacks `ServerOAuth2AuthorizedClientExchangeFilterFunction`, does the request attribute add a bearer header automatically?
17. Why do `WebClient` tests need a separate HTTP exchange stub alongside `mockOAuth2Client()`?
18. How do you verify a token is not sent to a host with the wrong audience?
19. If a controller receives the authorized client but the API stub always returns 200, what test gap might be missed?
20. When a manager can use caching, why shouldn't `mockOAuth2Client` be used to conclude token acquisition succeeded?
21. Is an expired access token fixture sufficient to prove the refresh grant works?
22. How does `ServerOAuth2AuthorizedClientRepository` differ from `ReactiveOAuth2AuthorizedClientService`?
23. Why is `bindToServer()` unsuitable for mutating a real server's mock session?
24. In a test using both OAuth2 Login and client credentials, which keys/registrations should be verified?
25. When a downstream API returns 401 or 403, which layers need to be tested?
26. How do you avoid using a `principalName` supplied by a browser query parameter?
27. Why shouldn't you call `block()` inside a Reactive controller?
28. When is `mockOAuth2Client()` insufficient and a dedicated mock OP/token endpoint/JWKS needed?

## References

- [Spring Security Reference — Testing OAuth 2.0 (Reactive): Testing OAuth 2.0 Clients](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security Reference — WebTestClient Security Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html)
- [Spring Security Reference — Testing Authentication (Reactive)](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html)
- [Spring Security API — SecurityMockServerConfigurers](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html)
- [Spring Security API — SecurityMockServerConfigurers.OAuth2ClientMutator](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.OAuth2ClientMutator.html)
- [Spring Security Reference — Reactive OAuth2 Client Core](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html)
- [Spring Security Reference — Reactive Authorized Client Features](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html)
- [Spring Security Reference — OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/reactive/oauth2/)
- [Spring Security API — ServerOAuth2AuthorizedClientExchangeFilterFunction](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html)
- [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html)
- [Spring Security API — ReactiveOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/ReactiveOAuth2AuthorizedClientManager.html)
- [Spring Security API — ServerOAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/server/ServerOAuth2AuthorizedClientRepository.html)
- [Spring Framework Reference — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://datatracker.ietf.org/doc/html/rfc6749)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700.html)
