# Integrating ServerOAuth2AuthorizedClientExchangeFilterFunction with WebClient in Spring Security Reactive

> **Module:** Spring Security - reactive  
> **Topic:** OAuth2 Client  
> **Objective:** Use `ServerOAuth2AuthorizedClientExchangeFilterFunction` so `WebClient` attaches the appropriate Bearer access token per `OAuth2AuthorizedClient`; distinguish `authorization_code`, `client_credentials`, `ReactiveOAuth2AuthorizedClientManager`, refresh/renewal, and handling invalid tokens; implement Java 17+ with Spring WebFlux, Spring Security, and tests without calling a real IdP.

## 1. The Problem: WebFlux App A Calls API B After OAuth2 Authorization

A WebFlux application A needs to call a protected REST API B via `WebClient`. B requires an access token in the header:

~~~http
GET /v1/reports HTTP/1.1
Host: api.partner.example
Authorization: Bearer eyJhbGciOi...
Accept: application/json
~~~

In practice, never hardcode a token or copy tokens from incoming requests onto every outbound request. Tokens must be issued **for the right OAuth2 client, right subject, and right API audience/scope**, and managed properly before use.

Two common models:

- **User logs into A via OIDC/OAuth2 Login:** A holds an `OAuth2AuthorizedClient` bound to the user with an access token issued by the Identity Provider; A calls a provider endpoint or API B **permitted to accept that token**.
- **A runs a job/background/service-to-service call:** A uses the `client_credentials` grant to obtain an access token under **the application's identity**, never impersonating an end-user. This requires a manager and store suited for running outside an HTTP request.

Spring Security provides `ServerOAuth2AuthorizedClientExchangeFilterFunction`, an `ExchangeFilterFunction` for **WebFlux**, to apply OAuth2 Client-managed tokens to `WebClient` requests that explicitly specify an authorized client or registration.

**Scope limits:** The filter only attaches tokens and coordinates OAuth2 Client authorization. It does **not** prove the user is authorized to read arbitrary records in B, convert an ID Token into an access token, perform token exchange by itself, or guarantee A's token is accepted by every API B.

## 2. Five Easily Confused Components

| Component | Typical Package/API | Function |
| --- | --- | --- |
| `ClientRegistration` | `org.springframework.security.oauth2.client.registration` | Client metadata: registrationId, clientId, secret, grant, endpoints, scopes |
| `OAuth2AuthorizedClient` | `org.springframework.security.oauth2.client` | Combines ClientRegistration + principal name + access token (+ refresh token if present) |
| `ReactiveOAuth2AuthorizedClientManager` | OAuth2 Client | Requests tokens, re-authorizes/refreshes via grant providers, coordinates persistence |
| `ServerOAuth2AuthorizedClientRepository` / `ReactiveOAuth2AuthorizedClientService` | OAuth2 Client | Saves and loads authorized clients for web requests or at application level |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | OAuth2 Client WebClient | Selects client and adds `Authorization: Bearer ...` on outbound calls |

A `ClientRegistration` **holds no token yet**; only an `OAuth2AuthorizedClient` represents a client with active authorization. A regular `WebClient` **does not automatically carry an access token** simply because user A logged in; you need the filter and explicit client selection.

`ServerOAuth2AuthorizedClientExchangeFilterFunction` resides in package:

~~~java
org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction
~~~

**Never use `ServletOAuth2AuthorizedClientExchangeFilterFunction` in WebFlux**: that name belongs to the Servlet runtime and imperative `OAuth2AuthorizedClientManager`. Reactive stacks use `ReactiveOAuth2AuthorizedClientManager` and `SecurityWebFilterChain`/`ServerHttpSecurity`.

## 3. When Does the Filter Execute?

A `WebClient` chain:

~~~java
webClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("partner"))
    .retrieve()
    .bodyToMono(String.class);
~~~

When creating the publisher, the application is only **describing** the HTTP request. Upon subscription, `WebClient` runs its filter chain, the filter inspects `ClientRequest.attributes()`, selects the OAuth2 client, invokes the authorized client manager if needed, and attaches the token:

~~~mermaid
flowchart TD
    A["Subscriber"] --> B["WebClient ExchangeFilterFunction"]
    B --> C{"Explicit OAuth2AuthorizedClient present?"}
    C -->|"Yes"| D["Use explicit client; may re-authorize"]
    C -->|"No"| E{"clientRegistrationId present?"}
    E -->|"Yes"| F["Manager looks up/requests authorized client"]
    E -->|"No"| G{"Default client enabled?"}
    G -->|"No"| H["Send request without auto-attaching OAuth2 token"]
    G -->|"Yes"| F
    D --> I{"Token still usable?"}
    F --> I
    I -->|"Needs refresh/renewal"| J["AuthorizedClientProvider executes grant"]
    J --> K["Save authorized client when appropriate"]
    I -->|"Yes"| L["Add Authorization Bearer"]
    K --> L
    L --> M["HTTP request to Resource Server"]
    M --> N["Resource Server validates issuer/audience/scope"]
~~~

The filter can request a new token when the client is not yet authorized, or re-authorize when the token is expired or near expiry **if an appropriate grant provider is configured**. Access tokens can be refreshed when a refresh token exists; `client_credentials` usually requests a **new** token without assuming a refresh token exists.

**Reactive pipelines are lazy:** never call `subscribe()` arbitrarily inside a service, and never call `block()` on the WebFlux event loop. Return `Mono`/`Flux` to the layer owning the subscription (WebFlux runtime, a properly designed scheduler, or tests).

## 4. Authorization Code vs. Client Credentials

| Criterion | `authorization_code` + OIDC | `client_credentials` |
| --- | --- | --- |
| Subject | Logged-in/authorizing user | The application/service itself |
| Browser redirect? | Yes, for login/consent | No |
| Callback? | Yes, commonly `/login/oauth2/code/{registrationId}` | No |
| Refresh token? | Depends on provider/scopes/policy | Usually absent; requests a new token |
| Authorized client key | User/registration | Stable service principal/registration |
| When used | A calls UserInfo or audience-matched API on user's behalf | Job or backend A calls API B under A's authority |
| Risk | Forwarding user token to wrong API/tenant | Treating a machine token as an end-user's authority |

When the requirement is **"A calls B on behalf of the user"**, the user access token may only be sent to B if **B is a valid audience with matching scopes**. If the token is only for A or Google UserInfo, never forward it to B. Consider OAuth2 Token Exchange / On-Behalf-Of if supported by your IdP rather than forwarding the same token everywhere.

If A uses `oauth2ResourceServer().jwt()` to validate inbound tokens, that **does not automatically create an authorized client** for outbound `WebClient` calls. To acquire outbound tokens separately, configure OAuth2 Client and an Authorized Client Manager independently.

## 5. Ways to Select an Authorized Client

For each `WebClient` request, select the client **explicitly** in one of two ways:

### 5.1. Pass an Existing Authorized Client

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client
    .ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

return webClient.get()
    .uri("/v1/userinfo")
    .attributes(oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class);
~~~

This is an **illustrative Java method body snippet** (the multi-line static import here only shows the API name; write it on one line when copying). `authorizedClient` is an `OAuth2AuthorizedClient` provided by Spring or returned by the manager, **not** a raw token string parsed from a request body.

### 5.2. Pass a registrationId

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

return webClient.get()
    .uri("/v1/reports")
    .attributes(clientRegistrationId("reports-service"))
    .retrieve()
    .bodyToMono(String.class);
~~~

The manager uses the ID to look up the registration/client and obtain a token per the grant. For `client_credentials` invoked from a background job, a **stable service principal** is still required for cache management; never use an arbitrary HTTP request username as a machine identity.

### 5.3. Avoid Enabling Global Defaults

The filter also provides:
- `setDefaultOAuth2AuthorizedClient(true)`: can select the default token from the `Authentication` of an OAuth2-logged-in user.
- `setDefaultClientRegistrationId("reports-service")`: can select a default registration.

**Caution:** when these options are enabled, any request flowing through the configured `WebClient` may receive a token. If URLs are client-controlled, WebClient calls another host, redirects are followed unsafely, or the same bean serves multiple purposes, **credentials can leak to untrusted services**. This lesson **leaves both defaults disabled**; callers must explicitly choose the authorized client/registration and use a `WebClient` with a fixed base URL.

## 6. Two Constructors with Different Failure Handling

Spring Security 6.x offers two key constructors:

~~~java
// Option A: pass the manager explicitly.
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveAuthorizedClientManager);

// Option B: pass registration repo + authorized-client repo for web.
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    reactiveClientRegistrationRepository,
    serverOAuth2AuthorizedClientRepository);
~~~

**Important difference documented in the API reference:** the constructor taking `ReactiveClientRegistrationRepository` + `ServerOAuth2AuthorizedClientRepository` automatically configures `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` to handle certain downstream authorization/authentication errors. The constructor taking a **manager** does **not automatically set this handler**, so if you want invalid clients/tokens evicted, call `setAuthorizationFailureHandler(...)` wired to the matching repository/service.

The handler only removes authorized clients for supported conditions and error codes; it does **not** turn every 403 into "fetch a new token and it will work". `insufficient_scope` may require different permission policies rather than a refresh. Never retry endlessly on 401/403, especially for non-idempotent HTTP POST requests.

## 7. Complete Project: OIDC Login Then Calling Google UserInfo with WebClient

To give the lab realistic end-to-end audience behavior, we choose **Google OpenID UserInfo API** as the downstream target instead of sending a Google token to an unrelated corporate API.

- The user logs into Google via Spring WebFlux's `oauth2Login()`.
- After login, the `OAuth2AuthorizedClient` for registration `google` holds an access token issued for Google APIs/UserInfo.
- `WebClient` uses the filter to attach the Bearer access token when calling `https://openidconnect.googleapis.com/v1/userinfo`.
- The controller returns only `sub` from UserInfo, never exposing tokens, email, or full claims.
- Tests use a mock OIDC principal, fake manager, and fake downstream, **requiring no real Google login**.

Requires **Java 17+, Maven**. The example uses Spring Boot `3.3.13` compatible with Spring Security 6.x as a learning baseline; the 3.3 branch has reached end of OSS support. For new production deployments, upgrade to a supported branch and verify APIs and tests against your target version.

~~~text
reactive-oauth2-webclient/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/client/
    │   │   ├── ClientApplication.java
    │   │   ├── SecurityConfig.java
    │   │   ├── WebClientConfig.java
    │   │   └── UserInfoController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/client/
        ├── OidcWebFlowTest.java
        └── OAuth2FilterTest.java
~~~

### 7.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactive-oauth2-webclient</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <properties>
        <java.version>17</java.version>
    </properties>

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
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Do not add Servlet `spring-boot-starter-web`**. Java/Reactive code in this lab uses `ServerHttpSecurity`/`SecurityWebFilterChain` and `ServerOAuth2AuthorizedClientExchangeFilterFunction`, not their Servlet namesakes.

### 7.2. ClientApplication.java

~~~java
package demo.client;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(ClientApplication.class, args);
    }
}
~~~

### 7.3. application.yml

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          google:
            client-id: ${GOOGLE_CLIENT_ID:demo-client-id}
            client-secret: ${GOOGLE_CLIENT_SECRET:demo-client-secret}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
~~~

Spring Boot includes built-in provider defaults for `google`, so authorization/token/userinfo URIs do not need to be written manually in the lab. `demo-client-id` / `demo-client-secret` only allow **initializing the test context** without exposing real credentials; Google will reject them for real logins.

For end-to-end login, create an OAuth2 Web Application client in Google and register the redirect URL `http://localhost:8080/login/oauth2/code/google`. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to your app's own credentials; never commit secrets or send them to browsers.

## 8. SecurityConfig.java: Protecting Inbound Requests and Enabling OAuth2 Login

~~~java
package demo.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/", "/login").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/api/me", "/api/userinfo").authenticated()
                .anyExchange().denyAll()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

This configuration handles **inbound authentication** for the browser. When unauthenticated, the app redirects to OAuth2 login; afterward, `WebSession` remembers the user. It does **not** automatically attach tokens to outbound HTTP calls—that is handled by the `WebClient` filter in the next section.

`anyExchange().denyAll()` locks down undefined routes. WebFlux CSRF remains enabled by default, which is crucial if you later add POST routes using browser session cookies. Never disable CSRF app-wide simply because OAuth2 Login is enabled.

## 9. WebClientConfig.java: Attaching ServerOAuth2AuthorizedClientExchangeFilterFunction

~~~java
package demo.client;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfig {

    @Bean
    WebClient googleUserInfoWebClient(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository authorizedClients) {

        var oauth = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            registrations, authorizedClients);

        // Do not call setDefaultOAuth2AuthorizedClient(true).
        // Do not call setDefaultClientRegistrationId("google").
        // Only send Bearer when caller selects an authorized client explicitly.
        return WebClient.builder()
            .baseUrl("https://openidconnect.googleapis.com")
            .filter(oauth)
            .build();
    }
}
~~~

**Why this constructor?** This lab is a **web flow after `oauth2Login`**, with a `ServerOAuth2AuthorizedClientRepository`. Passing the registration repo + authorized client repo builds the matching web manager and automatically configures the failure handler that can evict invalid authorized clients when downstream returns corresponding OAuth2 errors.

**Why a fixed base URL?** Because the filter attaches Bearer tokens; never let users control the destination URI or send tokens to addresses from query parameters or untrusted redirects. When calling multiple APIs, define **separate `WebClient` beans**, attaching filters/token policies only on beans targeting trusted hosts.

Never share a global `WebClient.Builder` carrying the OAuth filter for arbitrary outbound calls (telemetry, image fetchers, webhooks, external search, download URLs...). Doing so can deliver credentials to unauthorized parties.

## 10. UserInfoController.java: Resolving OAuth2AuthorizedClient and Calling WebClient

~~~java
package demo.client;

import java.util.Map;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

@RestController
public class UserInfoController {

    private final WebClient googleClient;

    public UserInfoController(WebClient googleUserInfoWebClient) {
        this.googleClient = googleUserInfoWebClient;
    }

    @GetMapping("/")
    public Mono<Map<String, String>> index() {
        return Mono.just(Map.of(
            "message", "Login at /oauth2/authorization/google"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal OidcUser user) {
        return Mono.just(Map.of("subject", user.getSubject()));
    }

    @GetMapping("/api/userinfo")
    public Mono<Map<String, String>> userInfo(
            @RegisteredOAuth2AuthorizedClient("google")
            OAuth2AuthorizedClient authorizedClient) {

        return googleClient.get()
            .uri("/v1/userinfo")
            .attributes(oauth2AuthorizedClient(authorizedClient))
            .retrieve()
            .bodyToMono(JsonNode.class)
            .map(json -> {
                String subject = json.path("sub").asText("");
                if (subject.isBlank()) {
                    throw new IllegalStateException(
                        "Provider UserInfo response has no subject");
                }
                return Map.of("subject", subject);
            });
    }
}
~~~

**Key integration points:**

1. `@RegisteredOAuth2AuthorizedClient("google")` lets Spring resolve the authorized client via the OAuth2 Client infrastructure and current user.
2. `.attributes(oauth2AuthorizedClient(authorizedClient))` explicitly assigns the tokenized client for **this specific request**.
3. The filter checks/re-authorizes if applicable, attaches `Authorization: Bearer <access-token>`, and calls Google UserInfo.
4. The controller extracts only `subject` from Google's JSON, never exposing raw tokens or other PII.
5. `retrieve()` errors by default on HTTP 4xx/5xx (`WebClientResponseException`). Never convert downstream errors into valid data.

Why Google UserInfo? An access token with OIDC scopes `openid/profile/email` from Google is **intended for Google UserInfo**. An arbitrary partner API must not receive this token merely because it also accepts Bearer headers. To integrate a corporate API B, configure the proper registration/IdP and verify B is the intended audience of the issued token.

`/api/me` reads claims directly from `OidcUser` **without an outbound WebClient call**; `/api/userinfo` deliberately exercises the OAuth2 Client filter. This clearly shows that login and WebClient token relay are two distinct steps.

## 11. Testing the Filter Without Real Google: The Strategy

Tests should never depend on real secrets or call a live IdP on every build. Instead:

- Construct a fake `ClientRegistration` and `OAuth2AuthorizedClient` with a **test-only** access token.
- Mock `ReactiveOAuth2AuthorizedClientManager` to return the authorized client. **Make no** token endpoint requests.
- Use a fake `ExchangeFunction` as downstream, recording `ClientRequest` while **making no outbound HTTP calls**.
- Build a real `WebClient` with the OAuth2 filter and assert the Bearer header; this tests token attachment behavior.
- Send a request without client attributes: with defaults disabled, verify the filter attaches no Bearer header.
- Test one request selecting `clientRegistrationId("reports-service")` and one selecting `oauth2AuthorizedClient(...)`.
- Test that errors from the manager are never masked as success responses.

**Never use fake tokens in production.** These tests do not prove JWT signatures, issuer/audience validation, refresh token servers, HTTP TLS, or the existence of a live API.

## 12. OAuth2FilterTest.java: Verifying the Actual Bearer Header

~~~java
package demo.client;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

import java.time.Instant;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.ClientRequest;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class OAuth2FilterTest {

    private OAuth2AuthorizedClient fakeClient() {
        ClientRegistration registration =
            ClientRegistration.withRegistrationId("reports-service")
                .clientId("not-a-real-client")
                .clientSecret("not-a-real-secret")
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://idp.example.invalid/oauth2/token")
                .scope("reports.read")
                .build();

        OAuth2AccessToken token = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "fake-test-access-token",
            Instant.now().minusSeconds(5),
            Instant.now().plusSeconds(3600),
            Set.of("reports.read"));

        return new OAuth2AuthorizedClient(
            registration, "reports-job", token);
    }

    private ExchangeFunction fakeDownstream(
            AtomicReference<ClientRequest> observed) {
        return request -> {
            observed.set(request);
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                .body("ok")
                .build());
        };
    }

    @Test
    void addingRegistrationIdAddsBearerHeader() {
        var manager = mock(ReactiveOAuth2AuthorizedClientManager.class);
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
            .thenReturn(Mono.just(fakeClient()));

        var captured = new AtomicReference<ClientRequest>();
        WebClient client = WebClient.builder()
            .exchangeFunction(fakeDownstream(captured))
            .filter(new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager))
            .build();

        Mono<String> reply = client.get()
            .uri("https://api.example.invalid/v1/reports")
            .attributes(clientRegistrationId("reports-service"))
            .retrieve()
            .bodyToMono(String.class);

        StepVerifier.create(reply)
            .expectNext("ok")
            .verifyComplete();

        assertNotNull(captured.get());
        assertEquals("Bearer fake-test-access-token",
            captured.get().headers().getFirst(HttpHeaders.AUTHORIZATION));

        verify(manager).authorize(
            org.mockito.ArgumentMatchers.argThat(request ->
                "reports-service".equals(
                    request.getClientRegistrationId())));
    }

    @Test
    void explicitAuthorizedClientAddsBearerHeader() {
        OAuth2AuthorizedClient fake = fakeClient();
        var manager = mock(ReactiveOAuth2AuthorizedClientManager.class);
        when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
            .thenReturn(Mono.just(fake));

        var captured = new AtomicReference<ClientRequest>();
        WebClient client = WebClient.builder()
            .exchangeFunction(fakeDownstream(captured))
            .filter(new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager))
            .build();

        StepVerifier.create(client.get()
                .uri("https://api.example.invalid/v1/reports")
                .attributes(oauth2AuthorizedClient(fake))
                .retrieve()
                .bodyToMono(String.class))
            .expectNext("ok")
            .verifyComplete();

        assertEquals("Bearer fake-test-access-token",
            captured.get().headers().getFirst(HttpHeaders.AUTHORIZATION));
    }

    @Test
    void noSelectionAndNoDefaultMeansNoBearer() {
        var manager = mock(ReactiveOAuth2AuthorizedClientManager.class);
        var captured = new AtomicReference<ClientRequest>();

        WebClient client = WebClient.builder()
            .exchangeFunction(fakeDownstream(captured))
            .filter(new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager))
            .build();

        StepVerifier.create(client.get()
                .uri("https://api.example.invalid/public")
                .retrieve()
                .bodyToMono(String.class))
            .expectNext("ok")
            .verifyComplete();

        assertNotNull(captured.get());
        assertNull(captured.get().headers()
            .getFirst(HttpHeaders.AUTHORIZATION));
        org.mockito.Mockito.verifyNoInteractions(manager);
    }
}
~~~

The first assertions prove the filter selects the right client and attaches the expected Bearer header. The third test proves that when no OAuth2 client is selected and defaults are disabled, no token is added automatically.

**This is a network-free test**: `ExchangeFunction` returns a fake response. It does not prove a server accepts the token, test provider refresh/revocation, or prove the bearer token carries the right audience. Add integration tests with a fake IdP/JWKS or sandbox provider before deployment.

### Why Not Hardcode Tokens via .defaultHeader?

Flawed design:

~~~java
WebClient webClient = WebClient.builder()
    .defaultHeader("Authorization", "Bearer " + token)
    .build();
~~~

Tokens expire, get revoked, or belong to different principals; every request receives a static header even when calling unrelated hosts. Filter + `AuthorizedClientManager` attaches tokens per client/grant/expiry policy. Still, **the filter cannot prevent token leaks if you pick the wrong client or URI yourself**.

## 13. OidcWebFlowTest.java: Verifying HTTP App Security Independently of Downstream

~~~java
package demo.client;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class OidcWebFlowTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicPageIsReadable() {
        client.get().uri("/")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.message").exists();
    }

    @Test
    void anonymousUserMustLoginBeforeViewingProfile() {
        client.get().uri("/api/me")
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void mockOidcLoginMakesProfileReadable() {
        client.mutateWith(
                mockOidcLogin().idToken(token ->
                    token.claim("sub", "subject-123")))
            .get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("subject-123");
    }

    @Test
    void unknownRouteIsNotAccidentallyPublic() {
        client.mutateWith(mockOidcLogin())
            .get()
            .uri("/api/unknown")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

These tests exercise the WebFlux security chain and controller without performing a real Google login and without calling `/api/userinfo` to avoid network traffic. `mockOidcLogin()` is a test mutator for the security context; it does not sign JWTs or test issuer/audience validation. Full login testing requires a fake IdP or sandbox IdP environment executing a real code flow.

## 14. Running Tests and End-to-End Login with Google

In the `pom.xml` directory:

~~~bash
mvn clean test
~~~

The test methods above are expected to run with Java 17+ and compatible dependencies. Exact Maven output depends on the toolchain. `OAuth2FilterTest` uses a fake token and fake `ExchangeFunction`, requiring no Google credentials.

For real login, create an OAuth2 Web Application client in Google and allow the callback:

~~~text
http://localhost:8080/login/oauth2/code/google
~~~

Bash/zsh:

~~~bash
export GOOGLE_CLIENT_ID="id-from-google-console"
export GOOGLE_CLIENT_SECRET="secret-from-google-console"
mvn spring-boot:run
~~~

PowerShell:

~~~powershell
$env:GOOGLE_CLIENT_ID = "id-from-google-console"
$env:GOOGLE_CLIENT_SECRET = "secret-from-google-console"
mvn spring-boot:run
~~~

Once running, open a browser:
- `http://localhost:8080/oauth2/authorization/google` — starts Authorization Code login.
- `http://localhost:8080/api/me` — returns subject from `OidcUser` in the local session.
- `http://localhost:8080/api/userinfo` — Spring resolves `OAuth2AuthorizedClient`, the WebClient filter sends Bearer to Google UserInfo, and returns the trimmed subject.

**There is no fixed stdout subject.** The `sub` value depends on the real Google user. If the client ID/secret or redirect URI is wrong, login fails at the provider and the full WebClient path cannot be verified. Never put real secrets in READMEs, Git, or terminal screenshots.

## 15. The client_credentials Model for Background Jobs

Unlike browser logins, a scheduled/backend job needs an **application-identity** token rather than a logged-in user's access token. Replace `oauth2Login` with a registration using the `client_credentials` grant:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-service:
            provider: reporting-idp
            client-id: ${REPORT_CLIENT_ID}
            client-secret: ${REPORT_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: reports.read
        provider:
          reporting-idp:
            token-uri: ${REPORT_TOKEN_URI}
~~~

This is an **alternative configuration variant**; do not paste it into the Google project unless you intentionally need two clients. `REPORT_TOKEN_URI` must be provided by the IdP and use HTTPS. Never accept an arbitrary caller-supplied issuer URI or ship client secrets to a frontend.

In non-web environments, use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` paired with `ReactiveOAuth2AuthorizedClientService`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Bean
ReactiveOAuth2AuthorizedClientManager serviceManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService authorizedClients) {

    ReactiveOAuth2AuthorizedClientProvider provider =
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

    var manager = new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
        registrations, authorizedClients);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
~~~

**The code above is an optional bean for service-to-service work**, not to be pasted straight into the Google lab's `WebClientConfig` while using `authorization_code`. With `client_credentials`, there is no browser, `state`, or login callback; the token endpoint issues an access token for the application. The manager stores tokens keyed by registration and a **principal key** bound to the authorized client.

### Stable Principal in Jobs

A job can call the manager explicitly, avoiding reliance on an HTTP request's `Authentication`:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import reactor.core.publisher.Mono;

public Mono<OAuth2AuthorizedClient> authorizeMachine(
        ReactiveOAuth2AuthorizedClientManager manager) {

    var authorizeRequest = OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-service")
        .principal("machine-reports")
        .build();

    return manager.authorize(authorizeRequest)
        .switchIfEmpty(Mono.error(new IllegalStateException(
            "No machine authorized client available")));
}
~~~

From this authorized client, send `WebClient` requests using `.attributes(oauth2AuthorizedClient(authorizedClient))`. In a job **without a user Reactor SecurityContext**, the filter can use the explicit authorized client's principal name for authorization/refresh. Never use a report-viewing user's principal to key a `client_credentials` cache entry when the token is truly a machine token, avoiding cache fragmentation and confused permissions.

If an inbound HTTP `Authentication` exists yet downstream requires a machine token, keep the **machine credential boundary** separate from user tokens and test principal selection/context; never force `setDefaultOAuth2AuthorizedClient(true)` or user tokens could be sent instead of service tokens.

## 16. Manager Constructor: Wiring a Failure Handler for the Token Cache

When creating the filter with a manager:

~~~java
var oauth = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    authorizedClientManager);
~~~

**Consider adding a handler to remove invalid authorized clients**, because this constructor does not automatically install a handler for downstream 401/403 responses:

~~~java
import org.springframework.security.oauth2.client.RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;

// Snippet inside a @Bean WebClient in service-to-service configuration.
var oauth = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
    authorizedClientManager);

var handler =
    new RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler(
        (registrationId, principal, attributes) ->
            authorizedClientService.removeAuthorizedClient(
                registrationId, principal.getName()));

oauth.setAuthorizationFailureHandler(handler);

WebClient webClient = WebClient.builder()
    .baseUrl("https://reports.partner.example")
    .filter(oauth)
    .build();
~~~

This is a **standalone configuration snippet** assuming `authorizedClientManager` and `authorizedClientService` are injected by Spring. `removeAuthorizedClient(registrationId, principalName)` must target the **exact same store** where the manager persists authorized clients. If a web flow uses `ServerOAuth2AuthorizedClientRepository` instead of the service store, the remover must target that repository so the wrong cache is not deleted.

**401 vs 403:** If the Resource Server returns `WWW-Authenticate: Bearer error="invalid_token"`, removing the cached token so the next request obtains a fresh one makes sense. If it returns `insufficient_scope`, the caller usually **lacks permissions**, rather than holding an expired token. Never create an infinite retry loop or grant extra scopes beyond what the IdP allows.

The filter docs specify: the **registration repo + server repo constructor** installs `RemoveAuthorizedClient` failure handling automatically; the **manager constructor** does not. Check this API difference whenever refactoring between the two constructors.

## 17. Refresh Tokens, Re-Authorization, and Expiration

An `OAuth2AuthorizedClient` holds an access token with `issuedAt`/`expiresAt` and optionally a refresh token. The manager works with `ReactiveOAuth2AuthorizedClientProvider` configured for grants:

- `authorization_code`: the user completes browser login; later, tokens can be refreshed if a refresh token was issued and the provider supports it.
- `refresh_token`: exchanges an expired/near-expiry access token for a new one; refresh tokens may be rotated, revoked, or rejected.
- `client_credentials`: when the token expires, the service requests a new access token from the token endpoint, usually without receiving a refresh token.
- Extension grants such as token exchange: require dedicated provider/registration support; they do not work automatically just because the OAuth2 filter is attached.

**Never fake a "refresh" by resending the same access token after a 401.** A 401 can stem from wrong audience, wrong issuer, revoked credentials, clock skew, or a locked account; getting a new token will not fix routing or permission mistakes. `403 insufficient_scope` usually requires adjusting scopes or authorization policies rather than retrying.

For WebFlux OAuth2 Login, `@RegisteredOAuth2AuthorizedClient`/manager can re-authorize properly, provided the session and authorized client repository exist and can persist updated tokens. Across multiple nodes, consistent persistence is required if token caches span requests.

**Safe retries:** if a `WebClient` POST producing side effects times out, do not automatically retry thinking the token failed to reach the server. Use idempotency keys, conditional updates, or an appropriate API contract; token renewal and HTTP retries are **two separate decisions**.

## 18. User Token, Machine Token, and Relay: Never Pick the Wrong Identity

| Inbound Request | What Does Outbound Need? | Proper Design |
| --- | --- | --- |
| Browser login at A | A calls Google UserInfo | OAuth2 Login authorized client + explicit `oauth2AuthorizedClient` |
| Browser login at A | A calls API B on user's behalf | Access token with B's audience + scopes; possibly token exchange/OBO |
| HTTP request to A carrying Bearer JWT | A calls B | Never assume direct relay; require permitted token relay or token exchange |
| Background job without user | A calls B with app permissions | `client_credentials` + service manager + stable principal |
| A calls public HTTP endpoint | No token | Separate WebClient without OAuth2 filter or without client attribute |

**Never send an ID Token to call B as an access token.** An ID Token targets the OAuth2 Client as its audience, whereas an access token targets the Resource Server. Never forward a Google access token to a corporate API simply because both use Bearer headers.

**Never take a user's tenant/owner from HTTP input and inject it into a machine principal.** Machine tokens and user delegation are two separate trust boundaries; if B needs end-user auditing, propagate actor identity via a trusted mechanism—never trust an arbitrary header like `X-User: alice`.

If users span multiple tenants or registrations, each `WebClient` request must explicitly specify the **right client/tenant and resource**. Never accept an unallowlisted `registrationId` from callers; a service holding multiple client secrets could be tricked into calling out-of-scope APIs.

## 19. WebClient Security Issues and Token Leakage

**1. Default token on every request:** avoid `setDefaultOAuth2AuthorizedClient(true)` on a `WebClient` shared across multiple destinations.

**2. Client-chosen URLs:** if an API accepts `?url=https://...` and passes it to a `WebClient` with an OAuth2 filter, an attacker can force tokens to be sent to a malicious host (SSRF + credential exfiltration). Restrict to fixed hosts/paths and control redirect behavior.

**3. Downstream redirects:** never assume `WebClient`/the connector will refuse redirects or strip `Authorization` on cross-origin redirects. Test HTTP client settings, redirect policy, allowed hosts, and TLS; never forward tokens across redirects to unlisted hosts.

**4. Never log Bearer tokens or secrets:** scrub `Authorization`, `Cookie`, `Set-Cookie`, token JSON responses, client secrets, refresh tokens, and authorization codes from application logs, HTTP wiretaps, APM, and screenshots.

**5. TLS:** token endpoints and APIs must use HTTPS with valid certificates. Never disable TLS verification to "fix" an `SSLHandshakeException`.

**6. Right token audience:** B must verify the token is intended for B; A must also ensure the IdP issued the token for B. The filter does not perform B's audience validation.

**7. Least privilege:** grant minimal scopes, constrain client credentials, rotate client secrets, keep access token TTLs short, and protect refresh tokens server-side.

**8. Cache isolation:** authorized clients are stored per registration/principal; prevent Alice's token from being served to Bob via shared principal keys or misconfigured repositories.

**9. Data-level authorization:** even with a valid token, B must still check tenant/owner/action on each object; a valid token signature does not grant blanket access.

**10. Timeouts and pressure:** configure reasonable timeouts for the IdP/token endpoint, downstream `WebClient`, and circuit breakers; avoid refresh storms when concurrent requests hit near-expired tokens simultaneously.

## 20. Reactor Context and the WebClient Filter

In WebFlux, `ReactiveSecurityContextHolder` holds authentication inside the subscription's Reactor Context. The OAuth2 filter can read it to determine the current principal during manager authorization/refresh.

~~~java
public Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

Notes:

- Never use Servlet `SecurityContextHolder` `ThreadLocal` expecting values to follow reactive schedulers.
- `publishOn` within the same Reactor chain normally preserves Reactor Context; **subscribing to a detached branch** or spawning separate threads/callbacks does not inherit the context automatically.
- If a user holds multiple OAuth2 clients, select via `clientRegistrationId` or explicit authorized client; never assume the current `OAuth2AuthenticationToken` is always the right token for B.
- In background jobs, context usually lacks a user login: use the service-based authorized client manager and a stable principal.
- Never call `block()` in a service to "fetch the token and build the request"; compose with `flatMap` or let the filter run inside the reactive pipeline.
- If calling an external REST API inside a DB transaction, remember that DB transactions **do not roll back HTTP side effects**. Consider outbox/idempotency rather than assuming external calls and DB transactions are atomic.

## 21. Where Do CORS and CSRF Fit?

**Outbound `WebClient` is a server-side HTTP client** not subject to browser Same-Origin Policy or CORS. You do not need to add `Access-Control-Allow-Origin` to `WebClient` requests to Google or an IdP to "make tokens work".

**Inbound browser sessions** from `oauth2Login` typically rely on a `WebSession` cookie; browser-initiated POST/PUT/PATCH/DELETE calls need CSRF tokens. Spring Security WebFlux enables CSRF by default. Disabling CSRF because "downstream WebClient uses Bearer" is wrong: browser–A cookies and A–B access tokens are **two separate HTTP boundaries**.

If a cross-origin frontend calls A using credentialed `fetch`, configure CORS with allowlisted origins and proper credentials settings, noting that CORS does not replace CSRF. Backend-to-B calls over `WebClient` **require no browser preflight**.

If an SPA calls the Resource Server directly with a Bearer header, an outbound OAuth2 Client inside A may not even be needed; that is a different architecture. Identify where access tokens are issued, stored, and consumed before choosing DSLs.

## 22. HTTP 401/403/5xx and Debugging Guide

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Downstream receives request without Authorization | WebClient lacks filter or request lacks client attribute | Check bean, `clientRegistrationId`/`oauth2AuthorizedClient` |
| `invalid_client` when requesting token | Wrong client ID/secret, auth method, or token-uri | Verify ClientRegistration and IdP config |
| `invalid_grant` on refresh | Refresh token revoked/rotated/expired | Remove authorized client and re-authenticate per flow |
| 401 `invalid_token` at B | Token expired/revoked/wrong issuer/audience | Check B validation, failure handler, fetch token with right audience |
| 403 `insufficient_scope` at B | Token lacks scopes or business permissions | Fix grant/scopes or policy; **never retry infinitely** |
| Getting 302 login redirect instead of JSON | Authorization Code flow requires browser/login session | Never use `authorization_code` in background jobs |
| User token sent to external webhook | Default client on shared WebClient, unallowlisted URL | Disable defaults, isolate WebClient per trusted API |
| Repeated 401s | Manager constructor missing failure handler, stale cache | Attach remover matching store or fix token policy |
| `no client registration` | Wrong `registrationId` or Boot properties not loaded | Verify exact registration ID |
| 401 after logout and new login | Stale authorized client/token cache, changed session | Synchronize token store and SecurityContext |
| Offline tests fail calling IdP | Tests hit real HTTP instead of fake manager | Use fake `ExchangeFunction`/mock authorized client |
| `BlockingOperationError` / stalled event loop | `block()` called inside WebFlux | Return `Mono`, configure non-blocking auth/token client |
| Valid JWT rejected by B | Wrong audience or resource-level policy | Inspect resource server logs safely (redact tokens) |
| Token valid yet API returns another tenant's data | B lacks object-level auth | Enforce authorization near DB, test for IDOR/BOLA |

**Trace layer by layer:** is the WebClient bean right -> is the filter on the builder -> does the request carry the client attribute -> did the manager find/authorize successfully -> is the token valid with the right audience -> is the outgoing Authorization header present (in tests/fakes only) -> what status and `WWW-Authenticate` error code did B return -> did the failure handler update/remove from the right store?

Never enable full wiretap logging containing access tokens in production. In tests, use only fake tokens; in production, log registration IDs, trace IDs, status codes, and sanitized error codes.

## 23. Extended Production Test Matrix

| Test Case | Goal | Tooling |
| --- | --- | --- |
| Explicit registration | Only requests selecting a client carry Bearer | Fake manager + fake `ExchangeFunction` |
| No selection | No token attached when defaults are false | WebClient unit test |
| Explicit authorized client | Correct token/client attached | WebClient unit test |
| Expired access token | Manager re-authorizes via valid provider | Fake token endpoint or sandbox IdP |
| Missing refresh token | App triggers re-login or uses appropriate grant | Integration test |
| 401 `invalid_token` | Handler evicts unusable token on matching error code | Fake Resource Server challenge |
| 403 `insufficient_scope` | Does not retry endlessly, fails with proper permission error | Fake Resource Server |
| Multiple users | Alice's token never leaks to Bob | Session/store isolation integration test |
| Multiple tenants | B token carries right audience and tenant claim | Authorization tests at B |
| Redirect to untrusted host | Authorization never leaks to unknown host | HTTP client / SSRF test |
| Service job without user | Client credentials with stable machine principal | Service manager integration test |
| Concurrent expiry | Avoids token endpoint refresh storm | Load/caching test |
| Token endpoint outage | Fails closed, times out, never uses expired tokens | Failure-injection test |
| Unauthorized browser route | `oauth2Login` redirect, private API protection | `WebTestClient` security test |
| POST with session cookie | CSRF remains enforced | `WebTestClient` `csrf()` |

**Fake header injection tests** do not prove cryptographic token validity. **Resource Server tests** do not prove authorization code login works. Test each trust boundary independently and run end-to-end tests against a staging IdP and live API before release.

## 24. Practice Exercises

### A. Add Another Safe WebClient
Create a `publicWebClient` bean without an OAuth2 filter to call `https://public.example`. Verify that `Authorization` is never sent on those requests, even when the HTTP user has an active OIDC login.

### B. From Authorized Client to registrationId
Switch the Google UserInfo call from `.attributes(oauth2AuthorizedClient(authorizedClient))` to `.attributes(clientRegistrationId("google"))`. Compare how the manager resolves the principal, pulls the authorized client from session, and errors when unauthenticated.

### C. Two Registrations
Create one client for Google UserInfo and one client issuing access tokens for a corporate API. Prove Google's token is **never** sent to API B and B's token is never sent to Google; separate `WebClient` beans and host allowlists.

### D. Lost Access Token
Create an expired fake authorized client and a fake token endpoint returning a new token, and observe manager/provider reauthorization. Add a test for a revoked refresh token ensuring expired tokens are not reused endlessly.

### E. Failure Handler
Stand up a fake downstream returning HTTP 401 with `WWW-Authenticate: Bearer error="invalid_token"`. Using the manager constructor and an appropriate remover, verify the authorized client is deleted on matching error codes. Contrast with `403 insufficient_scope` and avoid baseless "refresh gives new scopes" assumptions.

### F. Background Job
Use `client_credentials`, `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`, and principal `machine-reports`. Verify zero dependency on browser sessions and no accidental selection of a user's OAuth2 token.

### G. Safe Token Handling
Write a log sanitizer for headers, token responses, and cookies; ensure no real Bearer token appears in Logback output, tracing, or exception messages.

### H. SSRF and Redirects
Attempt to change the API host via a query parameter and prove the service rejects it. Check behavior when downstream redirects to another domain, disable unsafe redirects, and verify `Authorization` does not leak.

### I. Object-Level Authorization
Even when B receives a valid token, attempt to access another tenant's report. Prove B enforces owner/tenant/action checks independently; the WebClient filter does not replace BOLA policies.

### J. CSRF Boundary
Add a POST endpoint to the OIDC browser app and verify requests missing a CSRF token return 403. Explain why A calling B with Bearer does not justify disabling CSRF on browser–A session endpoints.

## 25. Completion Checklist

- [ ] Distinguish `ClientRegistration`, `OAuth2AuthorizedClient`, `AuthorizedClientManager`, repository/service, and the WebClient filter.
- [ ] Use the reactive class `ServerOAuth2AuthorizedClientExchangeFilterFunction`, never the Servlet variant.
- [ ] Configure `WebClient` with `.filter(oauth)` and a trusted base URL.
- [ ] Select the client per request via `oauth2AuthorizedClient(...)` or `clientRegistrationId(...)`.
- [ ] Keep default OAuth2 tokens disabled on a `WebClient` shared across destinations.
- [ ] Understand that the two filter constructors differ in failure handler behavior.
- [ ] Distinguish `401 invalid_token` from `403 insufficient_scope`.
- [ ] Include tests using a fake `ExchangeFunction` verifying exact `Authorization` headers.
- [ ] Never substitute ID Tokens for access tokens or send tokens to the wrong audience.
- [ ] Distinguish user-delegated `authorization_code` from machine `client_credentials`.
- [ ] Ensure the manager has proper grant providers and persistence/refresh policies.
- [ ] Avoid nested `subscribe()`, blocking the event loop, or non-idempotent HTTP retries.
- [ ] Keep CSRF enabled on browser session endpoints and distinguish it from CORS.
- [ ] Enforce token redaction, TLS, SSRF prevention, tenant authorization, and secret rotation.
- [ ] Confirm inbound/frontend auth never creates outbound tokens without explicit OAuth2 Client config.

## 26. Self-Check Questions

1. Does a plain `WebClient` automatically attach tokens simply because a user logged in via OIDC in Spring Security?
2. What data does `OAuth2AuthorizedClient` contain beyond `ClientRegistration`?
3. When should you use `@RegisteredOAuth2AuthorizedClient` and `oauth2AuthorizedClient(...)`?
4. What are the pros and cons of `clientRegistrationId(...)` compared to an explicit authorized client?
5. Why is the filter named `ServerOAuth2AuthorizedClientExchangeFilterFunction` even though it is used on outbound `WebClient` calls?
6. Which constructor auto-configures `RemoveAuthorizedClient` failure handling, and which requires manual configuration?
7. Why is `setDefaultOAuth2AuthorizedClient(true)` dangerous on a shared `WebClient`?
8. When an access token expires with no refresh token, how does `client_credentials` differ from `authorization_code`?
9. Why must a Google UserInfo access token never be sent to an internal corporate reports API?
10. If A acts purely as a Resource Server validating inbound Bearer tokens, does it automatically possess an outbound authorized client?
11. When B returns `403 insufficient_scope`, why is clearing the cache and requesting a new token insufficient?
12. In a browserless job, which manager and principal are appropriate?
13. Why use a `WebClient` fake `ExchangeFunction` to test outbound tokens without calling a real IdP?
14. Why does CORS not apply to server-side outbound `WebClient` calls the way it does to browser `fetch`?
15. If a POST succeeds on the server yet times out waiting for the response, why should it not be retried unconditionally?

## 27. Official Documentation

- [Spring Security — OAuth2 Client in Reactive Environments](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/index.html): OAuth2 Client configuration, grant providers, and WebClient.
- [Spring Security — Authorized Client Features for WebClient](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html): filter, explicit authorized client, registration ID, and default-token warnings.
- [Spring Security — Core Interfaces / Classes](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html): ClientRegistration, authorized client managers, repositories, token persistence.
- [Spring Security — ServerOAuth2AuthorizedClientExchangeFilterFunction API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html): constructor behavior, failure handling, request attributes.
- [Spring Security — OAuth2 Login WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/core.html): Authorization Code login, OIDC ClientRegistration, and WebSession.
- [Spring Security — OAuth2 Client Authorization Grants](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html): client_credentials, refresh tokens, and grant providers.
- [Spring Security — Testing OAuth2 WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html): `mockOidcLogin` for HTTP auth tests.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): ExchangeFilterFunction, reactive response handling, and filters.
- [OAuth 2.0 — RFC 6749](https://www.rfc-editor.org/rfc/rfc6749): Authorization Code, client credentials, and OAuth2 Access Tokens.
- [RFC 8707 — Resource Indicators](https://www.rfc-editor.org/rfc/rfc8707): selecting resource/audience for tokens.
- [OWASP — OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): client authentication, redirect/token risks, and secure architecture.

**Conclusion:** `ServerOAuth2AuthorizedClientExchangeFilterFunction` lets `WebClient` use `OAuth2AuthorizedClient` to send **Bearer access tokens** without hardcoding secrets. Still, who tokens are issued to, which grant is used, where they are stored, how they refresh, how 401/403 are handled, and ensuring tokens reach **only the intended audience** remain architectural responsibilities. Select authorized clients **explicitly per outbound request**, separate `WebClient` instances per trusted API, match the manager/service to user vs. machine flows, and test both the **present** and **absent** `Authorization` header paths before deploying with a live provider.