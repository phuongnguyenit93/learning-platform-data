# Testing `mockOAuth2Client()` and `WebClient` Calls with `OAuth2AuthorizedClient`

> Scope: **Spring Security for WebFlux (reactive) applications**; focused on testing an authorized OAuth 2.0 Client and verifying that the access token is attached to outgoing HTTP requests. Java examples use Java 17+, Spring Security 6.x/7.x, and JUnit 5. This lesson covers **OAuth2 Client**, not verifying JWT signatures at a Resource Server.

## 1. Learning objectives

After this lesson, you will be able to:

1. Distinguish `ClientRegistration`, `OAuth2AuthorizedClient`, `ReactiveOAuth2AuthorizedClientManager`, and `ServerOAuth2AuthorizedClientRepository`.
2. Use `WebTestClient.mutateWith(mockOAuth2Client("catalog"))` to supply a mock authorized client to a WebFlux request without calling a real authorization server.
3. Customize `registrationId`, `principalName`, `accessToken`, scopes, and `ClientRegistration` across test branches.
4. Pass the authorized client from `@RegisteredOAuth2AuthorizedClient` into `WebClient` via `.attributes(oauth2AuthorizedClient(client))` and assert the `Authorization: Bearer ...` header on outbound requests.
5. Recognize mock limitations: it does not verify grant flows, refresh tokens, OAuth2 login authentication, or connectivity to external services; those require separate tests.

## 2. Understanding the objects and token path

| Component | Role | What to test |
| --- | --- | --- |
| `ClientRegistration` | Client configuration: `registrationId`, `clientId`, grant type, token URI, scopes… | Correct OAuth2 registration selected |
| `OAuth2AccessToken` | Issued token with `tokenValue`, validity window, scopes | Exact Bearer value sent |
| `OAuth2AuthorizedClient` | Binds `ClientRegistration` and access token to `principalName` | Controller/service receives the right client |
| `ServerOAuth2AuthorizedClientRepository` | Stores/loads authorized clients per server request context | Mock client appears during WebFlux handling |
| `ReactiveOAuth2AuthorizedClientManager` | Finds, authorizes, or re-authorizes/refreshes per provider | Avoid calling real IdP when tests only need a fake token |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | `WebClient` filter that selects the authorized client and attaches Bearer to outgoing HTTP requests | Downstream request header has the right token |

Typical flow:

```text
HTTP GET /catalog
  -> WebFlux Security / ServerWebExchange
  -> @RegisteredOAuth2AuthorizedClient("catalog")
     (resolves OAuth2AuthorizedClient from the configured context)
  -> WebClient.get().attributes(oauth2AuthorizedClient(client))
  -> ServerOAuth2AuthorizedClientExchangeFilterFunction
  -> Authorization: Bearer <access-token>
  -> downstream resource server
```

`mockOAuth2Client()` acts on the **inbound application request** in `WebTestClient`: it stages a fake authorized client in the repository mechanism provided by Spring Security Test. It **does not automatically add Bearer to WebClient** if `WebClient` has no OAuth2 filter or the application fails to select the authorized client. Therefore, test both boundaries: *inbound client resolution* and *outbound request*.

### Distinguishing three commonly confused mock groups

- `mockOAuth2Client()`: prepares an `OAuth2AuthorizedClient`; by itself it **does not create an authenticated `SecurityContext`**.
- `mockOAuth2Login()` or `mockOidcLogin()`: simulates an OAuth2/OIDC logged-in user, creates an `Authentication`, and attaches an accompanying authorized client.
- `mockJwt()`: simulates a `JwtAuthenticationToken` for a **Resource Server** receiving a Bearer token; it does not replace `mockOAuth2Client()` in WebClient OAuth2 Client scenarios.

If an endpoint requires `authenticated()`, `mockOAuth2Client()` alone may be insufficient: pair it with an appropriate authentication such as `.mutateWith(mockUser("alice"))`, or use `mockOAuth2Login()` when testing a user-login scenario. User login and permission to call external services are independent concepts.

## 3. Test setup and preparing WebClient

For a Spring Boot app using Gradle Kotlin DSL (illustrating required dependencies; versions managed by the Spring Boot BOM):

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Configuration for registration `catalog` using the `client_credentials` grant (example-only URI, never called in tests using mock tokens):

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          catalog:
            client-id: demo-client
            client-secret: demo-secret
            authorization-grant-type: client_credentials
            scope: item.read
        provider:
          catalog:
            token-uri: https://auth.example.invalid/oauth/token
```

In application code, `WebClient` must have the **reactive OAuth2 filter**:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
class ClientWebConfig {
    @Bean
    WebClient securedWebClient(ReactiveOAuth2AuthorizedClientManager manager) {
        var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);
        return WebClient.builder().filter(oauth2).build();
    }
}
```

This configuration class is for a Spring Boot application with OAuth2 Client enabled; `manager` is configured by the application/auto-configuration. In environments with multiple `WebClient` beans, inject the exact bean carrying the filter. Never take Spring MVC's `ServletOAuth2AuthorizedClientExchangeFilterFunction` for use in WebFlux.

The controller receives the client by registration ID and passes it explicitly to `WebClient`:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@RestController
class CatalogController {
    private final WebClient securedWebClient;

    CatalogController(WebClient securedWebClient) {
        this.securedWebClient = securedWebClient;
    }

    @GetMapping("/catalog")
    Mono<String> catalog(
            @RegisteredOAuth2AuthorizedClient("catalog")
            OAuth2AuthorizedClient authorizedClient) {
        return securedWebClient.get()
                .uri("https://resource.example.invalid/items")
                .attributes(oauth2AuthorizedClient(authorizedClient))
                .retrieve()
                .bodyToMono(String.class);
    }
}
```

**Import syntax:** A Java `import static` statement must sit on **a single line in a source file**; when copying the snippet above, join the two `import static ...` lines into:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;
```

These are two application code snippets placed in Java files named after their classes; the `/catalog` endpoint in this example needs a fake downstream (MockWebServer, WireMock, or ExchangeFunction) during tests to avoid hitting `.invalid` URLs. The following sections test each boundary separately.

## 4. Testing WebFlux with `mockOAuth2Client()`

### 4.1. Basic syntax and meaning

When `WebTestClient` is configured with Spring Security Test (e.g., `@SpringBootTest` + `@AutoConfigureWebTestClient` or `bindToApplicationContext(...).apply(springSecurity())`):

```java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Client;

// Inside a @Test, with a WebTestClient client variable:
client.mutateWith(mockOAuth2Client("catalog"))
      .get().uri("/client-info")
      .exchange()
      .expectStatus().isOk();
```

Also join the `import static` statement onto one line in a Java file:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Client;
```

`"catalog"` is the **registration ID**, not the client ID, username, or provider name. By default Spring Security Test creates a simple `ClientRegistration` (client ID `test-client`, client secret `test-secret`), principal name `user`, and an access token with scope `read`. The fake token does not need to be signed or recognized by an authorization server.

### 4.2. Verifying `@RegisteredOAuth2AuthorizedClient` resolution

To clearly see the mock reaching the controller, add a small test endpoint in your test config or sample app:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ClientInfoController {
    @GetMapping("/client-info")
    Mono<String> info(
            @RegisteredOAuth2AuthorizedClient("catalog")
            OAuth2AuthorizedClient client) {
        return Mono.just(client.getClientRegistration().getRegistrationId()
                + "|" + client.getPrincipalName()
                + "|" + client.getAccessToken().getTokenValue());
    }
}
```

Example JUnit 5 test inside a **Spring Boot WebFlux test context** that has loaded the controller, OAuth2 Client, and `WebTestClient`:

```java
import java.time.Instant;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Client;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class ClientInfoTest {
    @Autowired
    WebTestClient client;

    @Test
    void injectedAuthorizedClientHasExpectedIdentityAndToken() {
        Instant now = Instant.now();
        var token = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "fake-access-token",
                now.minusSeconds(10),
                now.plusSeconds(3600),
                Set.of("item.read"));

        client.mutateWith(mockOAuth2Client("catalog")
                    .principalName("alice")
                    .accessToken(token))
                .get().uri("/client-info")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("catalog|alice|fake-access-token");
    }
}
```

Run command (for a Gradle project with wrapper): `./gradlew test --tests '*ClientInfoTest'`; on Windows you can use `gradlew.bat test --tests "*ClientInfoTest"`. JUnit asserts the body and status without printing stdout. These snippets assume the project has `@SpringBootApplication`, component-scanned endpoints, matching registration `catalog`, and WebFlux test auto-configuration; pasting a single class alone does not form a standalone app.

If `/client-info` is protected by `authenticated()`, combine authentication, e.g. `client.mutateWith(mockUser("alice")).mutateWith(mockOAuth2Client("catalog").principalName("alice"))`. Add a mock user only when testing route protection behavior; it does not create an access token for `WebClient`.

### 4.3. Customizing mocks for business branches

```java
Instant now = Instant.now();
OAuth2AccessToken token = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "scoped-token",
        now.minusSeconds(5),
        now.plusSeconds(600),
        Set.of("message:read", "item.read"));

client.mutateWith(mockOAuth2Client("catalog")
        .principalName("alice")
        .accessToken(token))
      .get().uri("/client-info")
      .exchange()
      .expectStatus().isOk();
```

Common `OAuth2ClientMutator` methods: `accessToken(OAuth2AccessToken)`, `principalName(String)`, `clientRegistration(ClientRegistration)`, and `clientRegistration(Consumer<ClientRegistration.Builder>)`. If using the real registration config from the app, you can fetch it via `ReactiveClientRegistrationRepository.findByRegistrationId("catalog")` during test setup and pass it to `clientRegistration(...)`; only `block()` in the *synchronous test setup*, never inside a reactive request handler.

**Scopes are data inside the access token**, not automatically equivalent to inbound endpoint access permissions. For instance, `client.getAccessToken().getScopes().contains("message:read")` checks the outgoing client's scope set, while `hasAuthority("SCOPE_message:read")` checks authorities on the inbound authentication. The two sides may require two separate mock datasets.

## 5. Proving WebClient sends the right `Authorization: Bearer` header

A test checking only `/client-info` body merely proves the controller received the authorized client. To confirm outbound Bearer headers, intercept requests at **`WebClient`'s `ExchangeFunction` layer** or a mock HTTP server and assert the header. Below is a JUnit 5 class **that runs standalone inside a project with the dependencies from Section 3**; it opens no sockets and calls no IdP.

Create `src/test/java/example/OAuth2WebClientFilterTest.java`:

```java
package example;

import java.time.Instant;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

class OAuth2WebClientFilterTest {
    @Test
    void sendsBearerHeaderOfExplicitAuthorizedClient() {
        ClientRegistration registration = ClientRegistration
                .withRegistrationId("catalog")
                .clientId("test-client")
                .clientSecret("test-secret")
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://auth.example.invalid/token")
                .build();

        Instant now = Instant.now();
        OAuth2AccessToken token = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "fake-token-123",
                now.minusSeconds(10),
                now.plusSeconds(3600),
                Set.of("item.read"));
        OAuth2AuthorizedClient authorizedClient =
                new OAuth2AuthorizedClient(registration, "alice", token);

        // When the filter requests re-authorization, the fake manager returns the still-valid client.
        ReactiveOAuth2AuthorizedClientManager manager =
                request -> Mono.just(authorizedClient);

        AtomicReference<String> sentAuthorization = new AtomicReference<>();
        ExchangeFunction fakeDownstream = request -> {
            sentAuthorization.set(
                    request.headers().getFirst(HttpHeaders.AUTHORIZATION));
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                    .header(HttpHeaders.CONTENT_TYPE, "text/plain")
                    .body("items-ok")
                    .build());
        };

        WebClient webClient = WebClient.builder()
                .filter(new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager))
                .exchangeFunction(fakeDownstream)
                .build();

        String body = webClient.get()
                .uri("https://resource.example.invalid/items")
                .attributes(oauth2AuthorizedClient(authorizedClient))
                .retrieve()
                .bodyToMono(String.class)
                .block(); // Block only in tests, never in a WebFlux handler.

        assertEquals("items-ok", body);
        assertEquals("Bearer fake-token-123", sentAuthorization.get());
    }
}
```

Run: `./gradlew test --tests example.OAuth2WebClientFilterTest` (Windows: `gradlew.bat test --tests example.OAuth2WebClientFilterTest`). **Expected result:** JUnit test passes; no application stdout. Removing `.filter(...)` leaves the request without a Bearer header from the OAuth2 filter; removing `.attributes(oauth2AuthorizedClient(...))` without a default registration leaves the filter unable to pick an authorized client. The fake manager in this example intentionally avoids testing token issuance/refresh: the sole goal is confirming the chosen token gets attached to the request.

Note: several Spring Security versions still call `ReactiveOAuth2AuthorizedClientManager.authorize(...)` even when an explicit authorized client is supplied, to handle tokens needing re-authorization. That is why the test stubs the manager to return the still-valid client; assuming "passing an explicit client guarantees the manager is never called" can break tests.

### Alternative integration testing

When you need to prove the full `WebTestClient → controller → WebClient → downstream HTTP` chain, use **MockWebServer/WireMock**: point the downstream URL to the mock server's localhost port, enqueue a `200` response, send `WebTestClient.mutateWith(mockOAuth2Client(...))`, and assert that the HTTP request received by the mock server carries `Authorization: Bearer fake-token-123`. You may still need `mockUser` if the route requires `authenticated()`. Never call real internet endpoints or spin up a real authorization server in simulated tests.

## 6. Selecting the client per request: explicit vs registration ID

Two common ways to invoke `WebClient`:

```java
// 1) Already have OAuth2AuthorizedClient (e.g., from a controller argument):
webClient.get()
        .uri(resourceUri)
        .attributes(oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class);

// 2) Only have registrationId; manager/repository needs to resolve the client:
webClient.get()
        .uri(resourceUri)
        .attributes(clientRegistrationId("catalog"))
        .retrieve()
        .bodyToMono(String.class);
```

These are **statement fragments inside a method**, requiring `webClient`, `resourceUri`, and static imports:
```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;
```

Approach 1 passes the concrete object produced by `mockOAuth2Client()`. Approach 2 requests lookup/authorization by registration ID; to avoid unintended calls to a token endpoint during tests, configure a mock manager or matching repository/registration. `setDefaultOAuth2AuthorizedClient(true)` or `setDefaultClientRegistrationId("catalog")` lets you omit the attribute, but use caution: defaults can attach tokens to **every request** sent by that `WebClient`, including unintended hosts. With multiple downstreams, prefer explicit per-request client selection.

`ReactiveOAuth2AuthorizedClientManager` handles the token lifecycle: if no client exists, it can execute the grant; if expired, it can refresh/re-issue when supported by the provider. Those branches are **not proven** by tests returning a prebuilt fake token and manager.

## 7. Key test matrix

| Scenario | Setup | Primary assertion |
| --- | --- | --- |
| Basic authorized client | `mockOAuth2Client("catalog")` | Controller receives the right registration ID/client |
| Custom token | `.accessToken(token)` | Exact Bearer value sent outbound |
| Custom principal | `.principalName("alice")` | Controller receives `alice`; if route is `authenticated()`, mock auth separately |
| Scope branching | Fake token with/without `item.read` | App takes the right business branch without inferring from authorities |
| Wrong client selected | Two different registrations, explicit selection | Client A's token is never sent to Client B's downstream |
| No default client | Omit attribute, no default configured | Verify behavior when client cannot be resolved; do not expect an automatic Bearer |
| Downstream returns 401/403 | Mock HTTP server returns matching status | Verify app error mapping and configured authorization failure handling |
| Expired token | Fake manager/provider returns new token or error | Test refresh/re-authorization separately; do not expect `mockOAuth2Client()` to auto-refresh |
| Endpoint requires login | Add `mockUser`/`mockOAuth2Login` per flow | Distinguish inbound 401/redirect errors from outbound Bearer errors |

HTTP tests should assert the **actual header value** at the downstream point. Checking only a `200` status from the controller is insufficient: the controller might return a stub body while `WebClient` never attached a token or picked the wrong registration.

## 8. Common mistakes and how to verify

1. **Confusing `mockOAuth2Client` with `mockOAuth2Login`.** An authorized client is present without an authenticated user; a protected route still returns `401` or redirects. Check security rules and add the appropriate mock authentication.
2. **Using `mockJwt()` to fake an outbound OAuth2 Client.** JWT mocks create an inbound Resource Server principal, not an `OAuth2AuthorizedClient` for `@RegisteredOAuth2AuthorizedClient`.
3. **Wrong `registrationId`.** `@RegisteredOAuth2AuthorizedClient("catalog")` must match the mocked/configured ID; `clientId` is not `registrationId`.
4. **Mock client present, but WebClient lacks the OAuth2 filter.** Nothing generates the Bearer header automatically. Check the injected `WebClient` bean, filter type, and request attributes.
5. **Filter present, but no authorized client specified.** Without a default, the filter may forward the request without a Bearer header. Use `oauth2AuthorizedClient(client)` or `clientRegistrationId("catalog")` as intended.
6. **Confusing token scopes with Spring authorities.** `Set.of("item.read")` belongs to `OAuth2AccessToken.getScopes()`; authorities for `@PreAuthorize` or `authorizeExchange` come from `Authentication` and usually require separate mocking.
7. **Fake access token already expired.** The manager may attempt to refresh/re-issue over the network. Use a valid token when testing headers; test expiration separately with a fake provider.
8. **Accidentally calling a real authorization server.** Mismatched repository/manager or registration config triggers a real grant. In outbound tests, use a stub manager/HTTP server; never put real client secrets in tests.
9. **Using Servlet APIs in a reactive project.** Servlet-style `MockMvc`/`oauth2Client()` and `ServletOAuth2AuthorizedClientExchangeFilterFunction` differ from `WebTestClient`/`mockOAuth2Client()`/`ServerOAuth2AuthorizedClientExchangeFilterFunction`.
10. **Calling `block()` in a reactive controller/service.** It can block the event loop. Return `Mono`/`Flux` from `WebClient`; only `block()` in synchronous unit-test examples.
11. **Leaking tokens in logs.** Use fake values only for assertions; with real tokens, check presence or a safe fingerprint without printing tokens or client secrets.
12. **Over-extrapolating from mocks.** `mockOAuth2Client()` does not prove authorization code redirects, PKCE, refresh flows, real session persistence, TLS, or IdP behavior; write matching integration/end-to-end tests.

## 9. Post-lesson self-check

- Explain why `mockOAuth2Client("catalog")` does not automatically grant `authenticated()` on an endpoint.
- Point out exactly where `OAuth2AuthorizedClient` flows from the controller into `ClientRequest.attributes()`.
- Write a test asserting `Authorization: Bearer fake-token-123` at an `ExchangeFunction` or mock HTTP server.
- State the differences among testing **token forwarding**, **client selection**, **token refresh**, and **OAuth2 login**.
- When a test returns `401`, determine whether the error belongs to inbound security or outbound downstream.

## Reference documentation

- Spring Security – Testing OAuth 2.0 (Reactive): https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security – Authorized Client Features (Reactive): https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html
- Javadoc – SecurityMockServerConfigurers: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html
- Javadoc – ServerOAuth2AuthorizedClientExchangeFilterFunction: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
