# Saving and Restoring Authorization Requests with `ServerAuthorizationRequestRepository` in Spring Security Reactive

## 1. The Problem to Solve

When a **Spring WebFlux** application lets users sign in with **OAuth 2.0 Authorization Code** or **OpenID Connect (OIDC)**, authentication does not happen in a single HTTP request. The application redirects the browser to the Authorization Server (IdP), the user logs in/consents there, and then the IdP redirects the browser back to the application's callback URL.

Between these two requests, the application must remember: **“What did the original redirect request ask for, for which client, with which `state`, and with which PKCE/OIDC metadata?”** Without saving and restoring this properly, the callback cannot be safely correlated with the initial request; users easily run into `authorization_request_not_found`, `invalid_state_parameter`, PKCE errors, OIDC nonce errors, or login loops.

In **Spring Security Reactive**, this storage responsibility belongs to the interface:

```java
org.springframework.security.oauth2.client.web.server
    .ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>
```

The default implementation:

```java
WebSessionOAuth2ServerAuthorizationRequestRepository
```

stores `OAuth2AuthorizationRequest` in **Spring WebFlux `WebSession`** from the moment the redirect is initiated until the authorization response is processed. This lesson covers the principles, API, configuration, testing, multi-tab/multi-instance limits, and safe extension patterns.

**Learning objectives:**

1. Explain the differences between **authorization request**, **authorization response**, **access token**, **authorized client**, and **SecurityContext**.
2. Trace the path `GET /oauth2/authorization/{registrationId}` → IdP → `GET /login/oauth2/code/{registrationId}`.
3. Use `saveAuthorizationRequest`, `loadAuthorizationRequest`, and `removeAuthorizationRequest` reactively.
4. Understand why **`state`, PKCE code verifier, OIDC nonce**, and accompanying attributes must all be preserved intact.
5. Configure `ServerHttpSecurity.oauth2Login().authorizationRequestRepository(...)` with a single consistent repository.
6. Build a **Java 17+ / Spring Boot 3.x / Spring Security 6.x** application that boots and can be tested without a real IdP at the repository/redirect level.
7. Diagnose cookie, WebSession, callback URL, proxy, multi-tab, multi-node, timeout, and replay issues.

> **Scope note:** `ServerAuthorizationRequestRepository` handles only the **temporary state of the authorization-code flow**. It is **not** a store for access/refresh tokens, not `ServerSecurityContextRepository`, and does not replace verifying ID token signatures, nonces, issuers, audiences, or resource permissions.

## 2. Two Requests at Different Times: Why Do We Need a Repository?

Suppose a user clicks “Sign in with Demo IdP” on an application at `https://app.example.com`.

**Step 1 — initiate login:**

```http
GET /oauth2/authorization/demo HTTP/1.1
Host: app.example.com
```

`OAuth2AuthorizationRequestRedirectWebFilter` delegates to `ServerOAuth2AuthorizationRequestResolver` to build an `OAuth2AuthorizationRequest` for the `demo` client registration. Depending on configuration, the request contains:

- The IdP's Authorization URI;
- `client_id`, `response_type=code`, scopes;
- The application's `redirect_uri`;
- An unpredictable **`state`** to match the callback;
- Extra attributes needed for **PKCE/OIDC**.

Before returning the HTTP redirect to the IdP, the application **saves the corresponding authorization request** in the repository. The browser is redirected to the IdP URL and holds the application's **session cookie** for subsequent requests back to the application.

**Step 2 — IdP authenticates and calls back:**

```http
GET /login/oauth2/code/demo?code=...&state=... HTTP/1.1
Host: app.example.com
Cookie: SESSION=...
```

Spring Security retrieves the authorization request saved in the corresponding session, **matches `state` and required parameters**, and then exchanges the authorization code for an access token at the token endpoint. If the client uses OIDC, the framework proceeds to verify the ID token and related conditions. When the flow succeeds, the app can set `Authentication` in `SecurityContext` and redirect to the post-login destination.

**If `WebSession` cannot be restored**, the callback has `code` and `state` but no way to know which initial request it belongs to. This situation must **fail closed**; never synthesize a new authorization request from the query string to continue the token exchange.

### Timeline Diagram

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as WebFlux OAuth2 Client
    participant R as ServerAuthorizationRequestRepository
    participant I as Identity Provider

    B->>A: GET /oauth2/authorization/demo
    A->>A: Resolver builds OAuth2AuthorizationRequest and state
    A->>R: saveAuthorizationRequest(request, exchange)
    R-->>A: Mono<Void> completes
    A-->>B: 302 to IdP + session cookie
    B->>I: GET /authorize?client_id&state&redirect_uri
    I->>B: Login/consent page
    B->>I: User logs in
    I-->>B: 302 to /login/oauth2/code/demo?code&state
    B->>A: GET callback + same WebSession cookie
    A->>R: load/removeAuthorizationRequest(exchange)
    R-->>A: Original OAuth2AuthorizationRequest
    A->>A: Correlate state and client registration
    A->>I: Exchange authorization code + PKCE verifier (if present)
    I-->>A: Token response
    A->>A: OAuth2/OIDC validation, create Authentication
    A-->>B: Success redirect; do not reuse consumed request
```

This diagram shows a conceptual sequence. Depending on the filter/implementation, the callback may invoke **load and/or remove** at slightly different steps; what matters is that a valid callback recovers the original state and does not turn an authorization code into an infinitely replayable operation.

## 3. Distinguishing Easily Confused Concepts

| Component | What Data Does It Store? | How Long Does It Live? | Role |
| --- | --- | --- | --- |
| `OAuth2AuthorizationRequest` | Redirect request, state, client/scope/redirect, PKCE/OIDC attributes | From flow initiation to callback | Correlation, protecting the authorization code flow |
| `ServerAuthorizationRequestRepository` | Pending `OAuth2AuthorizationRequest` | Short-lived, per session/transaction | Save, load, and remove pending records |
| `WebSessionOAuth2ServerAuthorizationRequestRepository` | Request inside `WebSession` | Per session/removal | Default Reactive repository |
| `ReactiveClientRegistrationRepository` | OAuth2 client/IdP configuration parameters | Lifetime of app config | Resolver looks up `client_id`, endpoints, scopes |
| `ServerOAuth2AuthorizationRequestResolver` | **Creates** the authorization request from an HTTP request | At redirect initiation | Builds the URL and request parameters |
| `ServerOAuth2AuthorizedClientRepository` | Authorized client, typically linked to tokens and principal | After token issuance, per policy | Stores/retrieves `OAuth2AuthorizedClient` |
| `ServerSecurityContextRepository` | `SecurityContext` holding `Authentication` | After login per session strategy | Restores identity on subsequent requests |
| `ServerRequestCache` | Original protected request to return to | During redirect/login flow | Saves original URL, **does not store OAuth2AuthorizationRequest** |
| `ReactiveOAuth2AuthorizedClientService` | Authorized client/tokens per service policy | After token issuance | Another form of backend token/client storage |
| `OAuth2AuthorizationResponse` | Callback `code` and `state` or error from IdP | Current callback | Result returned by IdP, matched against saved request |

A common point of confusion is **authorization request** vs. **authorized client**. Before the user visits the IdP, the app has no access token yet; this lesson's repository only stores the **pending request awaiting completion**. Only after a successful token exchange do `OAuth2AuthorizedClient`/tokens exist, belonging to a different component.

`ServerRequestCache` is also not this lesson's repository. It can remember `/orders/42` to redirect back after login, but it does not replace the `state`/PKCE/nonce data required for the OAuth2 callback.

## 4. Exact API of `ServerAuthorizationRequestRepository`

The Reactive interface in package `org.springframework.security.oauth2.client.web.server` has 3 key methods:

```java
public interface ServerAuthorizationRequestRepository<
        T extends OAuth2AuthorizationRequest> {

    Mono<Void> saveAuthorizationRequest(
        T authorizationRequest, ServerWebExchange exchange);

    Mono<T> loadAuthorizationRequest(ServerWebExchange exchange);

    Mono<T> removeAuthorizationRequest(ServerWebExchange exchange);
}
```

This is a **condensed signature for study**; do not recreate the interface in your project. It uses Reactor `Mono`, **not** Servlet's `HttpServletRequest`/`HttpServletResponse`.

### 4.1. `saveAuthorizationRequest`

Called when preparing to redirect to the IdP. It saves the **entire** `OAuth2AuthorizationRequest` object, not just `state`:

```java
Mono<Void> saved = repository
    .saveAuthorizationRequest(authorizationRequest, exchange);
```

**It must be subscribed indirectly by returning the publisher into the pipeline.** Merely creating `saved` and discarding it will not execute the save. In Spring Security's code, the filter composes the save with the redirect response.

### 4.2. `loadAuthorizationRequest`

Used to find the original request matching the current callback/exchange:

```java
Mono<OAuth2AuthorizationRequest> original =
    repository.loadAuthorizationRequest(exchange);
```

If not found, the reactive API returns **`Mono.empty()`**, never `Mono.just(null)` (Reactor does not allow null elements). With the default repository, state in `WebSession` and the callback `state` are tied to the lookup.

**Do not** do this:

```java
return repository.loadAuthorizationRequest(exchange)
    .switchIfEmpty(Mono.just(createNewRequestFromCallback()));
```

This is an **anti-example illustration**; `createNewRequestFromCallback()` is not part of any standard API. Synthesizing a request from the callback when the session is missing destroys correlation and risks accepting a response with no initiating request.

### 4.3. `removeAuthorizationRequest`

Returns and simultaneously removes the corresponding original authorization request:

```java
Mono<OAuth2AuthorizationRequest> consumed =
    repository.removeAuthorizationRequest(exchange);
```

Once a request has been consumed, a subsequent callback/replay **must not find the same pending transaction again**. Never just call `load` and leave the request sitting around forever, especially if replacing the default filter.

**Do not manually call remove in a controller before the OAuth2 login filter**: doing so can leave the filter with no data to validate the callback. In the standard flow, let Spring Security own when consumption occurs; a custom repository simply provides accurate semantics.

## 5. Default Repository: WebSession

`WebSessionOAuth2ServerAuthorizationRequestRepository` is the default implementation, storing the authorization request in Spring WebFlux's `WebSession`.

```java
ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest> repository =
    new WebSessionOAuth2ServerAuthorizationRequestRepository();
```

Imports:

```java
import org.springframework.security.oauth2.client.web.server
    .ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.server
    .WebSessionOAuth2ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint
    .OAuth2AuthorizationRequest;
```

**What does WebSession do?**

- The browser is bound to a `WebSession` via an appropriate cookie/session ID.
- When starting OAuth2 login, the repository stores the authorization request in session attributes.
- When the callback returns **with the corresponding session**, the repository loads or consumes the pending request.
- If the session expired, the cookie wasn't sent, `state` doesn't match, or the session store lost state, the callback cannot restore the request.

**Do not manually create sessions as a “fix”** if the default works; diagnose session persistence/cookies/redirects first. In multi-replica deployments, use a **shared `WebSessionStore`** and test callbacks landing on different nodes.

### Can One Session Hold Multiple Concurrent OAuth2 Login Flows?

**Do not assume yes.** Different implementations and versions have different pending-request storage policies. Under common default configurations, opening two tabs and starting two consecutive logins in the **same session** can overwrite transaction A with B. When callback A arrives later, no matching request/state remains, so login A fails.

To support multiple concurrent transactions:

- You need a custom repository **keyed by state**, holding a bounded number of requests per session.
- Each request needs expiry/TTL, a count limit, cleanup on callback success/failure, atomic consumption, and binding to the session/user-agent.
- Never store an unbounded `Map` in the session; a malicious client could initiate thousands of authorization requests.
- Analyze cookie, session fixation, concurrency, and IdP interactions carefully; do not just flip an old flag that once existed in 5.x Javadocs.

If the product does not require multi-tab login, guiding users to avoid concurrent login tabs and supporting clean session retries is much simpler.

## 6. Preserving `state`, PKCE, and OIDC Nonce

### 6.1. `state`: Matching an Initiated Request

The authorization server returns the `state` sent in the authorization request. The client uses it to correlate the callback with the initiated session/transaction, reducing response-injection and login CSRF risks.

```text
GET /oauth2/authorization/demo
  → state = sRANDOM_A, save pending request in WebSession
  → IdP /authorize?...&state=sRANDOM_A

GET /login/oauth2/code/demo?code=c123&state=sRANDOM_A
  → retrieve matching pending request and process

GET /login/oauth2/code/demo?code=c123&state=WRONG
  → must not be accepted as callback for sRANDOM_A
```

**Never set `state` to `username`, a date, a constant string, or an unverified query string value.** Spring Security's default resolver generates a proper value; when customizing, keep it random, unpredictable, and preserve correlation.

Never log raw `state`/`code` from callback URLs: these parameters can show up in reverse proxy logs, browser history, telemetry, and traces. Log allowlisted event IDs/outcomes/registrationId instead of the full URL.

### 6.2. PKCE: Preserving `code_verifier` Completely

PKCE (**Proof Key for Code Exchange**) adds binding to code authorization:

1. The client generates a random `code_verifier` and keeps it secret.
2. Sends `code_challenge` (typically `S256`) in the authorization request to the IdP.
3. When exchanging the code for tokens, the client sends back the **original `code_verifier`**.
4. The IdP matches the verifier against the challenge.

In Spring Security, the resolver may place `code_verifier` into the **`attributes`** of `OAuth2AuthorizationRequest` for use at token exchange; `code_challenge` is sent on the authorization URI. If a custom repository serializes only `state` and `redirect_uri` while dropping `attributes`, token exchange can fail because **the verifier is gone**.

Never put `code_verifier` in HTML, JavaScript-readable cookies, `state`, or logs. Store it server-side and protect the session/store.

**Note on enabling PKCE:** Spring Security automatically supports PKCE for properly configured public clients (`client-authentication-method: none`, no client secret), or when `ClientRegistration.clientSettings.requireProofKey` is enabled. You can use `OAuth2AuthorizationRequestCustomizers.withPkce()` when the IdP supports it and customization is needed. Not every registration enables PKCE automatically just because the app uses OAuth2.

### 6.3. OIDC: Preserving and Verifying Nonce

When scope includes `openid`, OpenID Connect adds identity mechanisms such as the **ID token** and **nonce**. `nonce` binds the ID token to the login request, mitigating ID token replay/substitution in applicable flows.

Spring Security's resolver and OIDC handler may keep the **original nonce in request attributes**, while sending an appropriate nonce representation to the IdP on the authorization URI. A custom repository must preserve enough data for the ID token verifier to run validation. Never drop `nonce` just to work around a random error.

**State, PKCE, and nonce serve different purposes:**

| Mechanism | What It Binds | Failure When Lost |
| --- | --- | --- |
| `state` | Callback → original authorization request | Request not found; risk of response injection |
| PKCE `code_verifier` | Authorization code → client that initiated flow | Token endpoint rejects or PKCE protection is lost |
| OIDC `nonce` | ID token → original auth request | OIDC nonce validation fails or protection weakens |
| `redirect_uri` | Registered/valid callback URL | Redirect mismatch, callback error |
| `registrationId` | Selected client configuration/IdP | Transaction bound to wrong client/provider |

The framework integrates most of this validation when using `oauth2Login`. **Writing your own repository does not mean you may skip validation** or trust callback parameters blindly.

## 7. Relationship Between Resolver, Redirect Filter, and Callback Filter

| Reactive Component | When Used | Responsibility |
| --- | --- | --- |
| `DefaultServerOAuth2AuthorizationRequestResolver` | Login-initiation request | Looks up `registrationId`, builds authorization request |
| `OAuth2AuthorizationRequestRedirectWebFilter` | `/oauth2/authorization/{registrationId}` | Saves request and redirects to Authorization Server |
| `ServerAuthorizationRequestRepository` | Flow start and callback | Saves/loads/removes pending request |
| `OAuth2LoginAuthenticationWebFilter` | `/login/oauth2/code/{registrationId}` | Restores request, processes authorization response |
| `ReactiveOAuth2AccessTokenResponseClient` | After valid callback code | Exchanges code for tokens at the token endpoint |
| `ReactiveOAuth2UserService` / `OidcReactiveOAuth2UserService` | After token exchange | Loads user info / performs needed OIDC checks |
| `ServerSecurityContextRepository` | After authentication success | Saves logged-in user state |
| `ServerOAuth2AuthorizedClientRepository` | After token exchange | Stores authorized client/tokens per policy |

Default Spring Security 6.x path:

```text
GET /oauth2/authorization/demo
    -> Save OAuth2AuthorizationRequest
    -> Redirect to IdP authorize endpoint
GET /login/oauth2/code/demo?code=...&state=...
    -> Recover/consume matching OAuth2AuthorizationRequest
    -> Exchange authorization code for token
    -> OAuth2/OIDC validation
    -> Authentication success / SecurityContext
```

`/oauth2/authorization/{registrationId}` is the **start path**, not the callback. `/login/oauth2/code/{registrationId}` is the **callback**; the IdP must whitelist the exact redirect URI. Changing one side without updating the other causes errors.

If you build a custom `ServerOAuth2AuthorizationRequestResolver` to add `prompt=consent`, `login_hint`, or PKCE, preserve all mandatory attributes, use a compatible repo, and test state across the redirect.

## 8. Explicitly Configuring the Repository in `oauth2Login`

In a WebFlux app, the simplest choice is the default repository. When you want to declare it explicitly to share one consistent instance:

```java
@Bean
ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>
authorizationRequestRepository() {
    return new WebSessionOAuth2ServerAuthorizationRequestRepository();
}

@Bean
SecurityWebFilterChain securityChain(
        ServerHttpSecurity http,
        ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest> repo) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/", "/public/**").permitAll()
            .anyExchange().authenticated())
        .oauth2Login(oauth2 ->
            oauth2.authorizationRequestRepository(repo))
        .build();
}
```

This is a **configuration excerpt**; complete imports and a runnable app appear in the next section. When there is no reason to customize, you can omit the repo bean and `.authorizationRequestRepository(...)` to let the framework use the default.

**Note distinguishing the DSLs:**

- `oauth2Login(oauth2 -> oauth2.authorizationRequestRepository(repo))` configures state persistence for **OAuth2/OIDC login**.
- `oauth2Client(oauth2 -> oauth2.authorizationRequestRepository(repo))` can be used when the app also enables **OAuth2 client authorization** for outgoing resource access in the corresponding flow.
- Both DSLs can be configured in the same app, provided you understand the path flows and choose consistent repos per use case. Never create two different repositories and expect the callback to guess where the record was saved.
- `authorizationRequestRepository` is distinct from `authorizedClientRepository` (which stores tokens after authorization).

## 9. Java 17+ / Spring Boot 3.x Example: Storing Requests in WebSession

The example below **runs standalone up to the OAuth2 redirect step** and includes repository tests without needing a real IdP. To **complete a real login**, replace the test IdP address/`client-id`/`client-secret` with a valid OAuth2/OIDC registration at a live Authorization Server. This is stated explicitly instead of pretending tokens can be verified from a non-existent provider.

**Project structure:**

```text
src/main/java/demo/oauthstate/OAuthStateApplication.java
src/main/java/demo/oauthstate/SecurityConfig.java
src/main/java/demo/oauthstate/StartPageController.java
src/main/resources/application.yml
src/test/java/demo/oauthstate/AuthorizationRequestRepositoryTest.java
src/test/java/demo/oauthstate/OAuth2RedirectTest.java
```

### 9.1. Dependencies (`build.gradle`)

In a project already configured with the Spring Boot Gradle plugin, repositories, and Java 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Do not add `spring-boot-starter-web` to avoid switching the demo to Servlet. The Spring Boot BOM manages starter versions; do not mix Spring Security 6.x jars with other version APIs without an upgrade plan.

### 9.2. `src/main/java/demo/oauthstate/OAuthStateApplication.java`

```java
package demo.oauthstate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OAuthStateApplication {
    public static void main(String[] args) {
        SpringApplication.run(OAuthStateApplication.class, args);
    }
}
```

### 9.3. `src/main/resources/application.yml`

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          demo:
            provider: demo
            client-id: local-demo-client
            client-secret: local-demo-secret
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: profile
        provider:
          demo:
            authorization-uri: https://idp.example.test/oauth2/authorize
            token-uri: https://idp.example.test/oauth2/token
            user-info-uri: https://idp.example.test/oauth2/userinfo
            user-name-attribute: sub
```

`idp.example.test` is an **illustrative address that does not provide real login**. The app can still start and issue a **redirect** to this URI; token exchange cannot complete without a provider.

**For real login**, replace all URLs and credentials in the provider/client registration with a configured IdP's details, use **environment variables/a secret manager** for the client secret, and whitelist the redirect URI at the IdP. For OIDC, use a real provider supporting OIDC discovery/JWK, the `openid` scope, and issuer/ID token validation; do not just add the word `openid` to a dummy provider and assume you have an OIDC IdP.

### 9.4. `src/main/java/demo/oauthstate/SecurityConfig.java`

```java
package demo.oauthstate;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.web.server
    .ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.server
    .WebSessionOAuth2ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint
    .OAuth2AuthorizationRequest;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>
    authorizationRequestRepository() {
        return new WebSessionOAuth2ServerAuthorizationRequestRepository();
    }

    @Bean
    SecurityWebFilterChain chain(
            ServerHttpSecurity http,
            ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest> repo) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/", "/public/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(oauth2 ->
                oauth2.authorizationRequestRepository(repo))
            .build();
    }
}
```

**Explanation:**

- `@EnableWebFluxSecurity` enables Spring Security configuration for WebFlux.
- The `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` bean uses the default implementation; that exact bean is passed into `.oauth2Login(...)`.
- No need to write a custom `AuthenticationWebFilter` or compare `state` in controller code; Spring Security handles the authorization code flow.
- `authorizeExchange()` protects routes other than `/` and `/public/**`; the OAuth2 initiation filter at `/oauth2/authorization/demo` is installed in the chain by Spring Security. Because the filter owns this path, do not create a controller on the same URL.
- `oauth2Login` adds the OAuth2 login flow using the `ReactiveClientRegistrationRepository` built by Spring Boot from YAML.
- `Customizer` is not used in this class; if your IDE flags an unused `Customizer` import, you may remove that import line when formatting. An unused import does not block Java compilation.

### 9.5. `src/main/java/demo/oauthstate/StartPageController.java`

```java
package demo.oauthstate;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class StartPageController {

    @GetMapping("/")
    public Mono<String> index() {
        return Mono.just(
            "Start OAuth2 login at /oauth2/authorization/demo");
    }

    @GetMapping("/public/ping")
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping("/private/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName());
    }
}
```

`/private/me` requires login per the security policy. It reads the identity from **Reactor Context**, rather than accepting a username from a request parameter. Without a real IdP, this request will prompt login/redirect via the entry point — which is the expected behavior of the demo before OAuth2 login is completed.

### 9.6. Running and Observing the Redirect

```bash
# Linux/macOS
./gradlew bootRun

# Windows
gradlew.bat bootRun
```

Test:

```bash
curl -i http://localhost:8080/public/ping

# Do NOT add -L: only inspect the redirect to the demo IdP, do not call the dummy IdP.
curl -i http://localhost:8080/oauth2/authorization/demo
```

The login-initiation response is normally `302 Found` with a `Location` header containing parameters like:

```text
https://idp.example.test/oauth2/authorize?
  response_type=code&client_id=local-demo-client&
  redirect_uri=...&state=RANDOM_VALUE&scope=profile
```

The lines above are wrapped **for readability**, not a verbatim URL to copy. The random `state` value, parameter order, and URL encoding may vary. The server may also send a session cookie so the returning callback identifies the same `WebSession`.

**Do not** use `curl -L` to follow the redirect to the demo domain and mistake the connection failure for a Spring Security bug. With a real IdP, the browser is redirected to a valid login page; returning to the callback uses the repo to restore the original authorization request.

## 10. Unit Tests That Run Without an IdP: save → load → remove

This is **the most important test suite for the repository itself**. It requires no token endpoint or Authorization Server; Spring Test's `MockServerWebExchange` simulates a callback request holding a test `WebSession`.

File `src/test/java/demo/oauthstate/AuthorizationRequestRepositoryTest.java`:

```java
package demo.oauthstate;

import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.oauth2.client.web.server
    .WebSessionOAuth2ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint
    .OAuth2AuthorizationRequest;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AuthorizationRequestRepositoryTest {

    private OAuth2AuthorizationRequest original(String state) {
        return OAuth2AuthorizationRequest.authorizationCode()
            .authorizationUri(
                "https://idp.example.test/oauth2/authorize")
            .clientId("local-demo-client")
            .redirectUri(
                "http://localhost:8080/login/oauth2/code/demo")
            .scopes(Set.of("profile"))
            .state(state)
            .build();
    }

    @Test
    void savesLoadsAndConsumesOriginalRequest() {
        var repo =
            new WebSessionOAuth2ServerAuthorizationRequestRepository();

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/login/oauth2/code/demo")
                .queryParam("state", "state-for-unit-test")
                .queryParam("code", "unused-test-code"));

        var expected = original("state-for-unit-test");

        StepVerifier.create(
                repo.saveAuthorizationRequest(expected, exchange))
            .verifyComplete();

        StepVerifier.create(repo.loadAuthorizationRequest(exchange))
            .assertNext(saved -> {
                assertEquals(expected.getState(), saved.getState());
                assertEquals(expected.getClientId(), saved.getClientId());
                assertEquals(
                    expected.getRedirectUri(), saved.getRedirectUri());
            })
            .verifyComplete();

        StepVerifier.create(repo.removeAuthorizationRequest(exchange))
            .assertNext(consumed ->
                assertEquals(expected.getState(), consumed.getState()))
            .verifyComplete();

        // Callback already consumed; old request must not be reused.
        StepVerifier.create(repo.loadAuthorizationRequest(exchange))
            .verifyComplete();
    }

    @Test
    void refusesRequestWithUnexpectedState() {
        var repo =
            new WebSessionOAuth2ServerAuthorizationRequestRepository();

        var exchange = MockServerWebExchange.from(
            MockServerHttpRequest.get("/login/oauth2/code/demo")
                .queryParam("state", "wrong-state"));

        StepVerifier.create(repo.saveAuthorizationRequest(
            original("expected-state"), exchange))
            .verifyComplete();

        // The default repository does not return the authorization request
        // when the callback state does not match the stored one.
        StepVerifier.create(repo.loadAuthorizationRequest(exchange))
            .verifyComplete();
    }
}
```

Run:

```bash
# Linux/macOS
./gradlew test --tests 'demo.oauthstate.AuthorizationRequestRepositoryTest'

# Windows
gradlew.bat test --tests "demo.oauthstate.AuthorizationRequestRepositoryTest"
```

**Why is this test trustworthy?**

- Uses the actual default implementation from Spring Security WebFlux rather than a mock repository that always returns results.
- `saveAuthorizationRequest` completes before `load`.
- `load` verifies the original `state`, `clientId`, and `redirectUri`.
- `remove` returns and removes the request; subsequent `load` is empty.
- The second test verifies that a callback carrying a wrong `state` **cannot** retrieve the original request within the same test session.

This is a **repository unit test**. It **does not prove** that a real browser/IdP shares the same cookie, that token exchange succeeds, or that ID tokens are verified. Those steps require integration tests with a full mock IdP or a test-tenant IdP.

## 11. Integration Test: Filter Saves Request Before Redirect

Beyond calling the repository directly, we need to test the application with a client registration and the actual OAuth2 filter redirecting the browser to the IdP.

File `src/test/java/demo/oauthstate/OAuth2RedirectTest.java`:

```java
package demo.oauthstate;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class OAuth2RedirectTest {

    @Autowired
    WebTestClient client;

    @Test
    void startLoginRedirectsToAuthorizationEndpoint() {
        client.get().uri("/oauth2/authorization/demo")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value("Location", location -> {
                assertTrue(location.startsWith(
                    "https://idp.example.test/oauth2/authorize"));
                assertTrue(location.contains("client_id="));
                assertTrue(location.contains("state="));
                assertTrue(location.contains("response_type=code"));
            });
    }

    @Test
    void publicPingDoesNotStartOAuth2Login() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }
}
```

Run:

```bash
./gradlew test --tests 'demo.oauthstate.OAuth2RedirectTest'
```

**This test suite has limited scope:** it confirms Spring Security builds the proper redirect and client registration. It **does not** test a callback completing token exchange, because the IdP in YAML is a dummy domain with no token endpoint. When integrating a real IdP, add browser or OAuth2 test-server tests to verify:

- The callback uses the **same session** as the initiating request.
- Right `state` → valid token exchange.
- Wrong/missing `state` → login fails.
- Reused `code` or repeated callback → rejected.
- PKCE verifier/nonce preserved → token/OIDC validation succeeds.
- After login, `/private/me` has an `Authentication`; before login it does not.

Never inject a mock `Authentication` in this integration test and claim the authorization code flow has been verified.

## 12. Observing the Repository Without Rewriting Security Mechanics

A common requirement is wanting to know **whether save/load/remove actually ran**, for debugging and auditing. The safest approach is keeping the default implementation and wrapping it to log only **non-sensitive** events, rather than reimplementing storage per field.

Optional class example `src/main/java/demo/oauthstate/ObservingAuthorizationRequestRepository.java`:

```java
package demo.oauthstate;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.oauth2.client.web.server
    .ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.client.web.server
    .WebSessionOAuth2ServerAuthorizationRequestRepository;
import org.springframework.security.oauth2.core.endpoint
    .OAuth2AuthorizationRequest;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

public final class ObservingAuthorizationRequestRepository
        implements ServerAuthorizationRequestRepository<
            OAuth2AuthorizationRequest> {

    private static final Logger log = LoggerFactory.getLogger(
        ObservingAuthorizationRequestRepository.class);

    private final ServerAuthorizationRequestRepository<
        OAuth2AuthorizationRequest> delegate =
            new WebSessionOAuth2ServerAuthorizationRequestRepository();

    @Override
    public Mono<Void> saveAuthorizationRequest(
            OAuth2AuthorizationRequest request,
            ServerWebExchange exchange) {
        return delegate.saveAuthorizationRequest(request, exchange)
            .doOnSuccess(ignored ->
                log.debug("OAuth2 authorization request saved"));
    }

    @Override
    public Mono<OAuth2AuthorizationRequest> loadAuthorizationRequest(
            ServerWebExchange exchange) {
        return delegate.loadAuthorizationRequest(exchange)
            .doOnNext(ignored ->
                log.debug("OAuth2 authorization request found"));
    }

    @Override
    public Mono<OAuth2AuthorizationRequest> removeAuthorizationRequest(
            ServerWebExchange exchange) {
        return delegate.removeAuthorizationRequest(exchange)
            .doOnNext(ignored ->
                log.debug("OAuth2 authorization request consumed"));
    }
}
```

**This is an optional alternative**; do not register two beans of the same type at once and expect Spring to pick automatically. To use the wrapper, replace the `authorizationRequestRepository()` method in `SecurityConfig` with:

```java
@Bean
ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>
authorizationRequestRepository() {
    return new ObservingAuthorizationRequestRepository();
}
```

The debug events **do not** print `request.getState()`, `authorizationRequestUri`, session ID, `code_verifier`, nonce, authorization code, cookies, or access tokens. In production, you can attach an independent audit ID, using a correlation mechanism that leaks no secrets.

**Never use `request.toString()` for logging**: the object may contain sensitive attributes used for PKCE/OIDC. The wrapper preserves the delegate's exact behavior; every `Mono` is composed into the pipeline without calling `.subscribe()` or `.block()`.

## 13. When Do You Need a Custom `ServerAuthorizationRequestRepository`?

The default `WebSession` repo is usually the best choice for **server-side OAuth2 login**. Replace it only when there is a verified requirement:

- The system needs to store pending requests in a shared store with TTL rather than `WebSession` attributes.
- Multiple OAuth2 login flows must work concurrently within the same browser session.
- Strict audit/tracing is required without modifying framework source code.
- A distributed app needs atomic consume/invalidation and independent cleanup.
- A specialized multi-domain/multi-instance cookie/session architecture has been threat-modeled.

If writing a custom implementation, design for:

1. **Lookup key:** tied to the **session/browser transaction**, random `state`, and exact registration/client. Never rely solely on `userId` because the user may not be authenticated yet when login starts.
2. **State matching:** callbacks may retrieve only a request matching `state`; missing or mismatched state must fail closed.
3. **Full request persistence:** never drop `attributes` holding the PKCE verifier/OIDC nonce or parameters verified by the resolver.
4. **Atomic consumption:** `removeAuthorizationRequest` removes the record on time so two callbacks cannot reuse the same state.
5. **TTL and cleanup:** pending records have a short lifetime; prevent attackers from creating unlimited requests in memory/Redis.
6. **Encryption/access control:** restrict store access; protect PKCE verifier/nonce and sensitive metadata; use TLS for Redis/databases.
7. **Cookie/session association:** callbacks must re-bind to the initiating browser/session; never rely solely on a client-supplied `state` without an appropriate combined protection mechanism.
8. **Error handling:** store loss/timeouts must fail closed—never authenticate when the request cannot be read; emit operational metrics.
9. **Concurrency:** multiple callbacks or login tabs may race; atomic compare-and-delete/transactions are essential.
10. **Observability:** log category/result, never `state`/`code`/verifier, raw callback URLs, or session IDs.

Never write a repository backed by a global `ConcurrentHashMap<String, OAuth2AuthorizationRequest>` that lets any caller knowing `state` fetch the request without evaluating TTL limits, session binding, scaling, and state-hijacking attacks. An in-memory map can serve an isolated test, but is **not automatically production-ready**.

### Why Must a Custom Repository Never Return Another User's Request?

In an OAuth2 redirect flow, the client does not yet hold the user's `Authentication` at callback time. Thus the repository acts as a **pre-authentication transaction store** and must isolate transactions by browser/session and state. Loading another user's record by mistake can mix up token exchanges and establish a session for the wrong subject, leading to login CSRF/account confusion.

**Multi-node guarantees** must also handle Node A saving and Node B receiving the callback; a repository bound to Node A's RAM returns empty on Node B. Use a distributed `WebSessionStore` or a shared-backing repository rather than relying on sticky sessions as your sole security guarantee.

## 14. Multi-Tab, Refresh, Back Button, and Callback Replay

Real-world scenarios:

| Scenario | Result / What to Check |
| --- | --- |
| User initiates login A, callback A immediately | Restores request A if session/state match |
| User initiates A then B in same session | A may be replaced by B depending on implementation; test multi-tab |
| Callback B arrives before A | One flow may succeed while the other fails if the repo keeps only one pending request |
| User refreshes callback URL containing `code` | Code already consumed or authorization request removed; must not log in again |
| User clicks Back to IdP `/authorize` URL | May start a new authorization request/state; must not reuse old state |
| Session expires while user is at IdP | Callback lacks original request; show safe retry page |
| Browser blocks cookies | Server sees a different or missing session; cannot find request |
| User switches browsers mid-flow | Different session/cookies; default WebSession repo finds no request |
| LB routes callback to another node | Requires shared `WebSessionStore` or compatible repository |
| Callback has `error=access_denied` | Protocol-level OAuth2 failure; clean up and show generic UI |
| Callback lacks `state` or has wrong state | Must not synthesize a new request to “ignore the error” |
| Token endpoint unavailable after callback | Infrastructure/token-exchange error; must not report login success |

A notable behavior of the default session repository is that **the number of pending requests managed** is not a guarantee of multi-tab support. If the product requires parallel flows, test specifically under one session and build a bounded state-keyed repository following the security contract.

Never replace this logic with “if state is not found, automatically log in again using the old code”. Authorization codes are short-lived, single-use, and bound to client/redirect/PKCE; a new flow must **restart from the authorization endpoint** with a fresh state.

## 15. WebSession Cookie, SameSite, Proxy, and Redirect URI

“Cannot restore authorization request” errors often stem not from the repository itself, but from **session continuity**.

### 15.1. Does the Session Cookie Return with the Callback?

The IdP redirects the browser back to the app via a **cross-site redirect**. The browser may omit the cookie if:

- The cookie has `SameSite=Strict`, so cross-site navigations omit it.
- The callback uses a different host/domain than login initiation (`www` vs. non-`www`, different subdomain).
- The cookie `Path` does not cover `/login/oauth2/code/...`.
- The cookie has the `Secure` flag while the callback hits HTTP instead of HTTPS.
- The browser blocks third-party cookies or the app is embedded in an iframe.
- The session expired or was logged out/invalidated while the user was at the IdP.
- The LB/gateway cannot find the session because the backend store is not shared.

For a **top-level GET** OAuth2 authorization-code callback, `SameSite=Lax` is usually more compatible than `Strict` when the browser returns from the IdP. If the IdP is configured with response mode **`form_post`** (cross-site POST), cookie policies differ and may require `SameSite=None; Secure` with an appropriate threat model. **Never blindly downgrade all cookies to `SameSite=None` over an uninvestigated error.**

### 15.2. Proxy Breaking `{baseUrl}`

Spring Security can construct `redirect_uri` from variables such as:

```text
{baseUrl}/login/oauth2/code/{registrationId}
```

If the app runs behind a reverse proxy and sees the internal request as `http://service:8080` instead of public `https://app.example.com`, the `redirect_uri` sent to the IdP can have the wrong scheme/host. Configure forwarded headers/trusted proxies per Spring Boot/Spring WebFlux and whitelist the exact redirect URI at the IdP. **Never trust arbitrary `X-Forwarded-*` headers from the Internet**; accept them only through a trusted proxy.

### 15.3. Changing Callback Without Updating Registration

Default:

```text
Start: /oauth2/authorization/{registrationId}
Callback: /login/oauth2/code/{registrationId}
```

To change the callback to `/login/oauth2/callback/{registrationId}`, keep all four aligned:

1. Matcher in `oauth2Login().authenticationMatcher(...)`;
2. `ClientRegistration.redirectUri`;
3. Redirect URI allowlist at the IdP;
4. Route security matchers, reverse proxy, and tests.

Changing only the URL in the gateway without updating the client registration causes the callback to arrive unhandled or the IdP to reject `redirect_uri`.

## 16. Information Security: Do Not Confuse `state` with Full Authentication

`state` is the correlation variable for the OAuth2 authorization request/response; it does not replace:

- Client authentication at the token endpoint (when applicable);
- PKCE verifier/challenge;
- `redirect_uri` and `client_id` checks;
- OIDC ID token signature, issuer, audience, expiry, and nonce;
- Authorization by scopes/roles after authentication.

**Never** disable state validation to avoid `authorization_request_not_found`. **Never** store the entire OAuth2 authorization request in a plaintext client-modifiable cookie. **Never** stuff PKCE `code_verifier` or client secrets into query strings/browser storage just to make the system “stateless” at any cost.

Authorization codes and `state` appear on the callback URL by protocol; logs can accidentally capture them. Therefore:

- Avoid logging full callback URIs, `Location` headers with code/state, raw cookies, and session IDs.
- Use HTTPS, HSTS/appropriate cookie flags, and centralized secret management.
- Show a generic login error page to the client, while logging sanitized **error category** metrics: session missing, state mismatch, token exchange timeout, provider error, registration mismatch.
- Rate-limit login initiations per session/IP at a balanced threshold to prevent abuse.
- Purge expired pending requests and monitor store errors so memory never grows unbounded.

Spring Security previously issued a security advisory regarding **DoS caused by initiating too many Authorization Requests** in certain older versions (CVE-2021-22119); patches were released years ago. The key takeaway for custom repositories is to **bound temporary data and run security-patched framework versions**.

## 17. Testing Real Callbacks with a Test IdP

The unit tests in section 10 verify that the repository honors its contract, but a system also needs the following end-to-end tests against a **test-tenant IdP** or a mock Authorization Server with a token endpoint:

1. **Happy path:** start `/oauth2/authorization/demo`, receive `state` + cookie, IdP redirects back to the same session, valid `Authentication` is established, `/private/me` returns the principal.
2. **State mismatch:** intentionally alter one character of `state` on the callback; login must fail closed.
3. **No cookie:** callback omits the initiating session cookie; repository cannot restore the request, no authenticated session is created.
4. **Expired session:** `WebSession` expires between steps; user is guided to start a fresh flow, never bypassing validation.
5. **Replay:** reuse `code`/`state` from a successful callback; second attempt must fail.
6. **Wrong registration:** callback hits a different registration/provider; must not use a request saved for another client.
7. **PKCE:** client sends valid `code_verifier`/challenge; omitting verifier in a test must fail token exchange.
8. **OIDC:** ID token with wrong nonce/issuer/audience/signature or expired timestamp must be rejected.
9. **Two tabs:** two authorization requests in the same session; verify documented supported behavior/limits.
10. **Multiple replicas:** initiate on node A, callback hits node B; shared session/store still retrieves the request.
11. **Reverse proxy:** redirect URI uses the external HTTPS host, cookie domain/path match.
12. **Provider error:** callback `error=access_denied` or token endpoint outage never results in an authenticated user.
13. **Observability:** logs/traces contain no authorization codes, `state`, PKCE verifiers, nonces, cookies, or tokens.

**Testing note:** Using `mockOAuth2Login()` or a mock authentication to test a controller tests **post-login** authorization, not `save`/`load`/`remove` of the authorization request or code exchange with the IdP. Distinguish repository tests, redirect filter tests, and full-flow tests.

## 18. Symptom-Based Troubleshooting

| Symptom | Common Cause | Steps to Check |
| --- | --- | --- |
| `authorization_request_not_found` | Cannot load original request | `WebSession` cookie, TTL, session store, `state`, multi-tab |
| `invalid_state_parameter` / state mismatch | Callback `state` differs from stored request | Matching session, never replace `state` with synthetic data |
| Callback loops back to login repeatedly | Lost cookie, OAuth2 callback error, wrong security chain | Network/Set-Cookie/callback, error handler, session |
| Redirect to IdP lacks `state` | Misconfigured resolver/customizer | `OAuth2AuthorizationRequest` before redirect |
| PKCE `invalid_grant` | Missing/wrong verifier, reused code, or different redirect URI | Attributes preserved, code verifier, client & redirect URI |
| OIDC nonce validation fails | Nonce mismatch or lost in repository | Full request attributes preserved and OIDC validation intact |
| Callback goes to internal HTTP host | Reverse proxy forwarded headers misconfigured | `{baseUrl}`, trusted proxy, client registration |
| Node A initiates, Node B callback fails | Unshared sessions | `WebSessionStore` or distributed backing repository |
| Only the second tab's login succeeds | Pending request overwritten by newer flow | Multi-tab test / bounded state-keyed repository |
| Retrying callback with same code fails | Request/code already consumed | Expected behavior; start a fresh authorization flow |
| Backend token endpoint call times out | Provider/network/service outage | Classify infrastructure failure, timeouts, safe retries |
| `GET /oauth2/authorization/demo` does not redirect | Missing registration/filter/right chain | `oauth2-client` starter, client registration, `oauth2Login()` |
| Mock user tests pass but real IdP fails | Mock skips the entire OAuth2 grant flow | Add higher-level integration tests |
| Works in another browser, fails in current one | Cookie policies, stale session, extensions | Try an incognito profile, inspect cookies safely |

**Ordered debugging procedure:**

1. Identify `registrationId`, initiation request, callback URI, and the matching security chain.
2. Check status and `Location` of the initiation request: does it redirect to the right IdP host with `state`?
3. Check whether the browser receives/sends the matching session cookie across both requests. Never paste real cookie values into tickets.
4. Verify `WebSessionStore` still holds the data and the same backend/repository is reading it; with multiple replicas, check shared storage.
5. Check how many pending login flows exist in the same session, or if the user opened multiple tabs/retried.
6. If `state` matches but token exchange fails, inspect client/redirect/PKCE/nonce/IdP rather than blindly swapping repositories.
7. Cross-check APIs, dependency versions, and logging, then re-test negative cases (missing state, replay, no cookie).
8. Never “fix” issues by disabling state/nonce validation, setting infinite TTL, or logging raw tokens/URLs.

## 19. Common Mistakes

**Mistake 1 — Using Servlet's `HttpSessionOAuth2AuthorizationRequestRepository` in WebFlux.**  
Reactive must use `WebSessionOAuth2ServerAuthorizationRequestRepository` or a custom `ServerAuthorizationRequestRepository`; never take `HttpServletRequest` or `HttpSecurity`.

**Mistake 2 — Confusing the repository with an access token store.**  
The authorization request exists **before** token exchange; `ServerOAuth2AuthorizedClientRepository`/service manages `OAuth2AuthorizedClient` after token issuance. Replacing this lesson's repository does not replace token storage.

**Mistake 3 — Saving only a `state` string.**  
PKCE `code_verifier`, OIDC nonce, and other attributes can be lost. Save the full `OAuth2AuthorizationRequest` or a fully verified mapping.

**Mistake 4 — Synthesizing the original request from the callback when session is missing.**  
A callback alone does not prove the user initiated the flow. Fail closed and restart login.

**Mistake 5 — Failing to remove the request after the callback.**  
Stale pending requests risk replay or resource exhaustion. Enforce one-time consumption, cleanup, and TTL.

**Mistake 6 — Keeping an unbounded map for multiple tabs.**  
Without bounds and TTL, this invites DoS. Use bounded state-keyed persistence with atomic consumption.

**Mistake 7 — Two different beans/repositories on the two ends of the flow.**  
If the redirect filter saves to repository A while the callback filter reads repository B, login always fails. Wire the exact same repo to the active flow and test end-to-end.

**Mistake 8 — Disabling cookies/WebSession while expecting default authorization request storage to work.**  
`NoOpServerSecurityContextRepository` and the authorization request repository serve different roles. An OAuth2 browser redirect flow needs **a place to hold transaction state** across two requests; design an alternative before disabling sessions.

**Mistake 9 — `SameSite=Strict` on cross-site OAuth2 callbacks causing missing sessions.**  
Check cross-site navigations, GET/`form_post`, cookie flags, and paths before blaming the IdP.

**Mistake 10 — Accepting arbitrary redirect URIs from query parameters.**  
Creates open redirect/client confusion risks. Redirect URIs must belong to the client registration and IdP allowlist; trust forwarded headers only from valid proxies.

**Mistake 11 — Logging raw authorization URIs, `code`, `state`, and cookies.**  
These values can be sensitive; log minimally and avoid capturing full URLs in tracing spans.

**Mistake 12 — Tests checking only the 302 from `/oauth2/authorization/demo`.**  
A 302 proves initiation; it does not prove the repo restores state on callback or that token validation succeeds. You need repository unit tests and IdP integration tests.

## 20. Implementation Checklist and Self-Assessment

| Item | Expected Outcome |
| --- | --- |
| Right Reactive API | `ServerAuthorizationRequestRepository<OAuth2AuthorizationRequest>` |
| Save | Saves full request before redirect; publisher is executed |
| Load | Looks up by matching session and state; unknown/mismatch fails closed |
| Remove | Consumes request exactly once; no replay |
| PKCE | `code_verifier`/attributes preserved intact |
| OIDC | Nonce and ID token validation preserved |
| Client registration | URIs, clientId, scopes, redirect URI match IdP |
| Cookie | GET initiation and callback share the same session |
| SameSite/TLS | Cross-site callback carries matching cookie; HTTPS in production |
| Proxy | Correct external base URL; trusted forwarded headers |
| Multi-tab | Behavior tested; if supported, must be bounded with TTL |
| Multi-node | Shared `WebSessionStore` or compatible repository |
| Custom repo | Atomic consume, TTL, session binding, fail closed |
| Error handling | Never grants access when store/IdP fails |
| Secrets | Never log `state`, `code`, verifier, nonce, cookies, or tokens |
| Tests | Save/load/remove, wrong state, redirect, end-to-end callback |
| Replay | Second callback cannot reuse the same transaction |
| Authorization | Post-login still enforces roles/scopes/resource ownership |

### Self-Check Questions

**1. Does this repository store access tokens or `OAuth2AuthorizationRequest`?**  
It stores **temporary authorization requests before the callback**. Tokens are stored via separate authorized-client components.

**2. Why is storing only `state` insufficient?**  
PKCE `code_verifier`, OIDC `nonce`, and other attributes may be required for token/ID token validation.

**3. What does `saveAuthorizationRequest()` return in WebFlux?**  
`Mono<Void>`. The publisher must be composed into the processing pipeline for the operation to execute.

**4. If the callback lacks the original WebSession, should you build a new request from `code`/`state`?**  
No. Fail closed and let the user start a fresh authorization flow.

**5. What does `removeAuthorizationRequest()` do?**  
Finds and **consumes/deletes** the pending authorization request so it cannot be reused as an incomplete transaction.

**6. Does `ServerRequestCache` replace this repository?**  
No. It remembers the original resource URL, not the full authorization request/PKCE/OIDC state.

**7. Why does logging in on two tabs in the same browser sometimes let only one tab finish?**  
They share a `WebSession`; the default repository may not hold multiple concurrent pending requests. Test and design a bounded state-keyed repo if concurrent support is mandatory.

**8. What must be checked when running two replicas?**  
The node receiving the callback must be able to access the same `WebSession`/store; consumption operations must be concurrency-safe.

**9. What impact can `SameSite=Strict` have?**  
The browser may withhold the session cookie on the cross-site redirect from the IdP, preventing the callback from finding the original request.

**10. Can `invalid_state_parameter` be “fixed” by disabling the state check?**  
No. It is a critical protection layer; diagnose lost sessions, flow changes, or mismatches instead.

## Remember

- **`ServerAuthorizationRequestRepository` saves and restores `OAuth2AuthorizationRequest` between the IdP redirect and the callback.**
- **Reactive defaults to `WebSessionOAuth2ServerAuthorizationRequestRepository`**, not `HttpSessionOAuth2AuthorizationRequestRepository`.
- Three APIs: `saveAuthorizationRequest(...): Mono<Void>`, `loadAuthorizationRequest(...): Mono<T>`, `removeAuthorizationRequest(...): Mono<T>`.
- **Never lose `state`, PKCE verifier, or OIDC nonce**; never synthesize a new request from the callback when the repository returns empty.
- `ServerOAuth2AuthorizationRequestResolver` **creates** requests; the repository **saves/restores** them; the authorized-client store **saves tokens after grant**; the security-context repo **persists authentication after login**.
- WebSession cookies, SameSite, TTL, proxy hosts, multiple tabs, and multiple replicas all affect the callback's ability to recover the request.
- For custom repos, require **bounded storage + TTL + atomic consume + session binding**; never log secrets or allow callback replay.
- Test across layers: **repository save/load/remove**, **OAuth2 redirect**, and **real callbacks with a test IdP**.

### Official Documentation

- [Spring Security 6.5 — OAuth2 Authorization Grant, Storing the Authorization Request](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html)
- [Spring Security 6.5 — OAuth2 Login Advanced Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/advanced.html)
- [Spring Security 6.5 — OAuth2 WebFlux Overview](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html)
- [Spring Security 6.5 — ServerAuthorizationRequestRepository Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/server/ServerAuthorizationRequestRepository.html)
- [Spring Security — WebSessionOAuth2ServerAuthorizationRequestRepository Javadoc](https://docs.spring.io/spring-security/site/docs/6.5.4-SNAPSHOT/api/org/springframework/security/oauth2/client/web/server/WebSessionOAuth2ServerAuthorizationRequestRepository.html)
- [Spring Security — Historical authorization-request DoS advisory (CVE-2021-22119)](https://spring.io/security/cve-2021-22119/)
