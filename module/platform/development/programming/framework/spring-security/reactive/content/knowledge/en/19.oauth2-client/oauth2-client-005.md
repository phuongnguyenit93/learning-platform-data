# Configuring Authorization Code and Client Credentials by Application Type — Spring Security Reactive

## 1. Lesson Objectives

When using **Spring WebFlux** as an **OAuth2 Client**, you must answer one question first: **"Is the application requesting authority on behalf of a user, or on behalf of itself?"** Those two goals lead to two very different grants:

- **Authorization Code**: involves an interactive user. The application redirects the browser to the Authorization Server, receives an authorization code via callback, verifies `state` and required conditions, and exchanges the code for tokens. Login flows are often combined with **OpenID Connect (OIDC)** when user identity is needed. **PKCE** protects the authorization code and is architecturally mandatory for public clients.
- **Client Credentials**: a trusted service/backend authenticates itself directly at the token endpoint and obtains an access token **for the workload/application**, with no user, no browser, and no OAuth2 login callback. This grant is meant for machine-to-machine API calls, batch jobs, or queue workers.

This lesson compares grants across **server-rendered web apps, BFFs, SPAs, mobile apps, background jobs, and microservices**, walks through configuring two client registrations in Spring Boot 3.x, using `ServerHttpSecurity.oauth2Login()` for users and `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` for service tokens, and covers Java 17+, `WebClient`, testing, and common security pitfalls.

> **Scope:** Spring Security 6.x **Reactive**, not Servlet `HttpSecurity`/`ServletOAuth2AuthorizedClientExchangeFilterFunction`. The OAuth2 Client is the **token requester**, not the Authorization Server issuing tokens or the Resource Server validating Bearer tokens. One application can play multiple roles, but boundaries and configurations must stay separate.

## 2. Choosing a Grant by Application Type

| Application or Workload | User Present? | Recommended Grant | What to Avoid |
| --- | --- | --- | --- |
| Server-side web app with session/cookie | Yes | **Authorization Code**; OIDC if login is needed | Exposing client secrets or access tokens to HTML/JS |
| **BFF** serving an SPA | Yes | BFF executes Authorization Code, keeps tokens on server | Letting the browser hold the BFF's secret |
| Browser-only SPA | Yes | **Authorization Code + PKCE**, public client; consider BFF | **Client Credentials in JavaScript** |
| Native mobile/desktop | Yes | Authorization Code + PKCE via system browser | Hardcoding a secret and treating it as confidential |
| Backend calling API under logged-in user's authority | Yes | Delegated token from Authorization Code; proper scope/audience | Using an overprivileged machine token instead of the user |
| Microservice A calling B for A's own business logic | No | **Client Credentials** | Creating a "robot" user with username/password |
| Batch, cron, queue consumer | No | **Client Credentials**, manager independent of HTTP requests | Requiring `ServerWebExchange` or a browser callback |
| Public client unable to hold a secret | Yes/No | Authorization Code + PKCE if a user is involved | Issuing application tokens using a public client secret |

**Decision rules:**

1. Need user consent or user login -> **Authorization Code**.
2. Need the application itself to call an API with no user -> **Client Credentials**.
3. Need user identity -> **OIDC** with `openid`, validating the ID token/nonce/issuer/audience per provider config.
4. Need both users and machines to call the same API -> the Resource Server must **distinguish which token type is accepted on which endpoint**; the two grants are not interchangeable.

`Client Credentials` is not a "simplified user login". Inside that token, `sub` (if present) may represent a client/service identity; never treat it as an end-user account holder.

## 3. Comparing the Core Nature of the OAuth2 Grants

| Aspect | Authorization Code | Client Credentials |
| --- | --- | --- |
| Primary actor | Resource owner/user + client | Confidential client/service |
| `/authorize` step | **Yes**, browser redirect | **No** |
| Token endpoint | `grant_type=authorization_code`, with `code`; PKCE verifier if used | `grant_type=client_credentials` with client authentication |
| Callback/redirect URI | **Yes**, must be allowlisted | **No** |
| `state` | Binds callback to the initial authorization request | No equivalent browser callback |
| PKCE | Recommended; essential for public clients | Not part of this grant's mechanism |
| Client secret | Used by confidential clients; public clients hold no secret | Confidential client must authenticate via an AS-supported method |
| Access token represents | User-delegated authorization | Application/workload authorization |
| Refresh token | May be issued, depending on provider | Usually absent; request a new access token on expiry |
| Token storage | Keyed by user/authorized client and session strategy | Keyed by registration + workload principal/service |
| Common failure modes | Missing `state`, missing PKCE, wrong redirect URI, token leak | Exposed client secret, overprivileged tokens, confused deputy |

### OAuth2 and OIDC

OAuth 2.0 focuses on **delegated resource access**; OIDC adds an **ID token** and identity verification rules. An app implementing "Sign in with IdP" typically selects Authorization Code with the `openid` scope and a real OIDC provider configuration. **An ID token does not replace an access token** when calling a Resource Server unless an API has a verified special contract; nor does a JWT automatically mean an ID token.

## 4. Authorization Code Flow in Spring WebFlux

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant C as Spring WebFlux OAuth2 Client
    participant A as Authorization Server
    participant R as Resource Server
    B->>C: GET /oauth2/authorization/browser
    C->>C: Create authorization request, state, PKCE
    C-->>B: 302 to authorization endpoint
    B->>A: GET /authorize?response_type=code&client_id&state...
    A-->>B: Login and consent
    B->>C: GET /login/oauth2/code/browser?code=...&state=...
    C->>C: Restore original request; verify state
    C->>A: POST /token grant_type=authorization_code
    A-->>C: Access token (and other tokens if issued)
    C->>C: OIDC/user validation, save Authentication/authorized client
    C-->>B: Redirect back to application
    C->>R: API request + Bearer user access token
    R-->>C: Response per user permissions
~~~

By default, the endpoint initiating the flow is:

~~~text
GET /oauth2/authorization/{registrationId}
~~~

and the default callback is:

~~~text
GET /login/oauth2/code/{registrationId}?code=...&state=...
~~~

In Spring Security Reactive:

- `DefaultServerOAuth2AuthorizationRequestResolver` builds `OAuth2AuthorizationRequest` from `ClientRegistration`.
- `OAuth2AuthorizationRequestRedirectWebFilter` saves the request and redirects to the Authorization Server.
- `ServerAuthorizationRequestRepository` typically stores the temporary request in `WebSession` so the callback can match `state` and attributes for PKCE/OIDC.
- The OAuth2 login authentication flow handles the callback, token exchange, and user authentication.
- `ServerOAuth2AuthorizedClientRepository` / `ReactiveOAuth2AuthorizedClientService` saves the `OAuth2AuthorizedClient` after tokens are issued.
- `ServerSecurityContextRepository` stores `SecurityContext`/`Authentication` according to the login policy.

**Do not confuse these three stores:** the authorization-request repository holds `state` **before** the callback; the authorized-client store holds tokens **after** authorization; and the security-context repository holds the **authenticated identity** for subsequent requests.

### Role of PKCE

The client generates a random `code_verifier` and sends a `code_challenge` (typically `S256`) on the authorize request. When exchanging the code for tokens, the client sends the original `code_verifier` so the Authorization Server can verify it. Public SPAs and mobile apps cannot hold a meaningful client secret, so they rely on PKCE alongside `state`/redirect URI protection and preserving the verifier in session/authorization-request storage. For confidential server-side clients, a secret and PKCE can complement each other when the provider supports it.

### Redirect URI Warning

The setting:

~~~yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
~~~

must match the redirect URI permitted by the IdP. When the application sits behind a proxy, `{baseUrl}` must resolve to the public HTTPS host/path, not an internal hostname. Trust forwarded headers only from a properly configured trusted proxy; never rely on an arbitrary client-supplied `redirect_uri` parameter.

## 5. Client Credentials Flow for Backends and Jobs

~~~mermaid
sequenceDiagram
    participant S as Service A
    participant A as Authorization Server
    participant R as Resource Server B
    S->>A: POST /token grant_type=client_credentials + client authentication
    A->>A: Verify client_id, method, scopes, audience
    A-->>S: access_token, token_type, expires_in
    S->>R: GET /internal/data + Authorization: Bearer access_token
    R->>R: Verify signature/introspection, iss, aud, scope
    R-->>S: 200 or 401/403 per permission
~~~

**There is no** `/oauth2/authorization/...`, `/login/oauth2/code/...`, or user session. A backend that only performs machine-to-machine communication does not need to configure `oauth2Login()`.

The token endpoint can receive a request shaped like:

~~~http
POST /oauth2/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credentials-encoded>

grant_type=client_credentials&scope=inventory.read
~~~

`client_secret_basic` is a common client-authentication method; other providers may require `client_secret_post`, private-key JWT, or another supported method. **HTTP Basic is only safe over TLS**; Base64 does not encrypt secrets. Never ship client secrets to browsers, mobile apps, or public repositories.

A `client_credentials` token typically includes only an **access token**. When near or past expiration, the client manager requests a new token using the same grant; it does not require a refresh token. The Resource Server must still verify signature/introspection, `iss`, `aud`, expiry, scopes, and workload permissions.

## 6. Roles of Reactive OAuth2 Client Classes

| Class/Interface | What It Is Used For |
| --- | --- |
| `ClientRegistration` | Client ID, authentication method, grant, redirect URI, scopes, endpoints |
| `ReactiveClientRegistrationRepository` | Looks up a registration by `registrationId` |
| `ReactiveOAuth2AuthorizedClientManager` | Requests/renews/manages authorized clients via providers |
| `ReactiveOAuth2AuthorizedClientProvider` | Per-grant strategy such as Authorization Code, refresh token, Client Credentials |
| `DefaultReactiveOAuth2AuthorizedClientManager` | Manages authorized clients within a `ServerWebExchange` context |
| `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | Manages outside web requests, suited for background/service apps |
| `ServerOAuth2AuthorizedClientRepository` | Authorized-client persistence per web request |
| `ReactiveOAuth2AuthorizedClientService` | Authorized-client persistence at application level |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Adds Bearer token to outbound `WebClient` requests per authorized client |
| `OAuth2AuthorizedClient` | Registration + access token and optional refresh token, bound to a principal |
| `ServerHttpSecurity.oauth2Login` | Configures browser user login redirect/callback in WebFlux |
| `ServerHttpSecurity.oauth2Client` | Enables outbound OAuth2 Client features in web flows |
| `SecurityWebFilterChain` | Protects inbound HTTP; distinct from Resource Server token validation |

Key point: **`DefaultReactiveOAuth2AuthorizedClientManager` is designed for use within a `ServerWebExchange`**. Spring Security 6.5 documentation directs using **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`** for services running outside an HTTP request, such as schedulers or queue consumers.

Even with Client Credentials, the `OAuth2AuthorizeRequest` passed to the manager needs a **stable principal as a storage key for the authorized client**. For example, `"workload-inventory"` is an internal cache identity, **not a user like Alice or Bob**.

## 7. Java 17+ Example: Two Registrations in One WebFlux App

This example uses Spring Boot 3.x / Spring Security 6.x. It starts up and runs registration, redirect, and service token propagation tests **without needing a real IdP**. To complete an OAuth2 login or call a resource API via the token endpoint, replace the demo domains with a real provider/Resource Server and officially issued client credentials.

### 7.1. Dependencies

Add to a Gradle project already configured with the Spring Boot plugin, repositories, and Java 17+:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

Do not add `spring-boot-starter-web` if this example should run on WebFlux rather than Servlet. Use the Spring Boot BOM to manage dependencies; never mix Spring Security jars from different versions.

### 7.2. `src/main/resources/application.yml`

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          browser:
            provider: demo
            client-id: demo-browser-client
            client-secret: demo-browser-secret
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: profile

          machine:
            provider: demo
            client-id: demo-machine-client
            client-secret: demo-machine-secret
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: inventory.read

        provider:
          demo:
            authorization-uri: https://idp.example.test/oauth2/authorize
            token-uri: https://idp.example.test/oauth2/token
            user-info-uri: https://idp.example.test/oauth2/userinfo
            user-name-attribute: sub

demo:
  machine-resource-uri: https://api.example.test/internal/inventory
~~~

- The two registrations `browser` and `machine` use **different client IDs and secrets**. Separating client registrations enables least privilege, auditing, and independent rotation.
- `browser` needs an authorize endpoint and redirect URI; `machine` only needs the token endpoint while sharing the `provider.demo` reference. In real systems, register providers accurately reflecting each client's capabilities.
- `scope: profile` illustrates OAuth2 login via the UserInfo endpoint. If **OIDC** is needed, configure a provider supporting OIDC with `openid`, issuer/JWK metadata, and ID token validation; do not simply add a scope against a fake IdP.
- `inventory.read` is an illustrative application scope name; the real IdP must grant that client the corresponding permission, and the Resource Server must verify the matching audience/scope.
- `idp.example.test` and `api.example.test` are addresses with **no real IdP or resource**. The app can start and generate redirects; token exchanges/calls to those hosts will not complete. Do not treat this as production-connected code.
- In production, inject credentials from environment variables or a secrets manager, and **never commit** production values to YAML, logs, or frontends.

### 7.3. `src/main/java/demo/grants/GrantTypesApplication.java`

~~~java
package demo.grants;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GrantTypesApplication {
    public static void main(String[] args) {
        SpringApplication.run(GrantTypesApplication.class, args);
    }
}
~~~

### 7.4. `src/main/java/demo/grants/SecurityConfig.java`

~~~java
package demo.grants;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
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
                .pathMatchers("/", "/public/**").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

- `oauth2Login` enables Authorization Code login for the `browser` registration. The `machine` registration does not become a browser login option because its grant is `client_credentials`.
- `GET /oauth2/authorization/browser` is handled by Spring Security; no custom controller is needed to receive the authorization code.
- Routes other than `/` and `/public/**` require user authentication.
- `oauth2Client` is omitted from the chain here because the machine flow below explicitly uses an out-of-HTTP manager; if you need **user-delegated outbound API calls** with `@RegisteredOAuth2AuthorizedClient`, configure OAuth2 Client and an authorized-client repository on the chain per application needs.
- Never disable CSRF globally; browser sessions still require CSRF for unsafe HTTP methods.

### 7.5. `src/main/java/demo/grants/MachineOAuth2Config.java`

~~~java
package demo.grants;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
public class MachineOAuth2Config {

    @Bean
    ReactiveOAuth2AuthorizedClientService authorizedClientService(
            ReactiveClientRegistrationRepository registrations) {
        return new InMemoryReactiveOAuth2AuthorizedClientService(
            registrations);
    }

    @Bean("machineManager")
    ReactiveOAuth2AuthorizedClientManager machineManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClientService) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClientService);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

**Why this manager type is used:**

1. `ReactiveClientRegistrationRepository` holds both `browser` and `machine`.
2. `ReactiveOAuth2AuthorizedClientService` holds issued `OAuth2AuthorizedClient` instances. `InMemoryReactiveOAuth2AuthorizedClientService` fits single-instance demos; multi-replica production should evaluate persistence, consistency, and token caching.
3. `machineManager` configures a provider with **`clientCredentials()` only**, avoiding mixing the browser Authorization Code path with the service path.
4. `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` needs no `ServerWebExchange`; it suits schedulers, queue consumers, and services with no user present.
5. When an access token nears expiration, the manager/provider applies the appropriate renewal policy. Never assume Client Credentials receives a refresh token.

### 7.6. `src/main/java/demo/grants/MachineResourceClient.java`

~~~java
package demo.grants;

import java.net.URI;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class MachineResourceClient {
    private final ReactiveOAuth2AuthorizedClientManager manager;
    private final WebClient webClient;
    private final URI resourceUri;

    @Autowired
    public MachineResourceClient(
            @Qualifier("machineManager")
            ReactiveOAuth2AuthorizedClientManager manager,
            WebClient.Builder builder,
            @Value("${demo.machine-resource-uri}") String uri) {
        this(manager, builder.build(), URI.create(uri));
    }

    // Package-private constructor for testing without an IdP.
    MachineResourceClient(
            ReactiveOAuth2AuthorizedClientManager manager,
            WebClient webClient,
            URI resourceUri) {
        this.manager = manager;
        this.webClient = webClient;
        this.resourceUri = resourceUri;
    }

    public Mono<String> fetchInventory() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("machine")
                .principal("workload-inventory")
                .build();

        return manager.authorize(request)
            .switchIfEmpty(Mono.error(new IllegalStateException(
                "Machine client was not authorized")))
            .flatMap(client -> webClient.get()
                .uri(resourceUri)
                .headers(headers -> headers.setBearerAuth(
                    client.getAccessToken().getTokenValue()))
                .retrieve()
                .bodyToMono(String.class));
    }
}
~~~

**What this code does:**

- The manager specifies `registrationId=machine` and a fixed principal `workload-inventory`; this is a **cache/persistence key**, not a logged-in user.
- `manager.authorize(request)` returns a reactive publisher without blocking the event loop. If no valid token is stored, it can contact the token endpoint.
- Only when an `OAuth2AuthorizedClient` is returned is `Authorization: Bearer ...` added to the outbound request.
- Never return the access token to the browser, never log it, and never use a machine credential to bypass user object-level authorization.
- `switchIfEmpty` converts an unsupported grant/registration outcome into an explicit error instead of sending an unauthenticated request.
- `@Autowired` identifies the constructor for Spring; the package-private constructor accepts `WebClient` directly for unit tests with a fake HTTP exchange.
- The downstream URI is configured server-side. **Never let users supply arbitrary URIs**, or machine tokens could be sent to malicious hosts (SSRF/token exfiltration).

### 7.7. `src/main/java/demo/grants/DemoController.java`

~~~java
package demo.grants;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class DemoController {
    private final MachineResourceClient machine;

    public DemoController(MachineResourceClient machine) {
        this.machine = machine;
    }

    @GetMapping("/")
    public Mono<String> index() {
        return Mono.just(
            "Start login at /oauth2/authorization/browser");
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

    @GetMapping("/demo/machine-inventory")
    public Mono<String> machineInventory() {
        return machine.fetchInventory();
    }
}
~~~

The `/demo/machine-inventory` route requires an authenticated browser user because of `anyExchange().authenticated()`. **This is purely an experimental endpoint** to observe the service using Client Credentials for a downstream call. In production, do not let any logged-in user trigger a high-privilege machine API call at will; enforce separate role/policy checks or trigger machine calls only from authorized workflows or background jobs. User permissions and service permissions are **two separate checks**.

### 7.8. Running the App

~~~bash
# Linux/macOS
./gradlew bootRun

# Windows
gradlew.bat bootRun

# Public endpoint runs without an IdP:
curl -i http://localhost:8080/public/ping

# Inspect redirect only; do not use -L to follow to the demo IdP:
curl -i http://localhost:8080/oauth2/authorization/browser
~~~

Expected result for `/public/ping` is `200 OK`, body `pong`. The request starting Authorization Code typically returns `302` with a `Location` containing `https://idp.example.test/oauth2/authorize`, `client_id`, `state`, `redirect_uri`, and `response_type=code`. The `state` value is random; parameter order and encoding may vary.

**Login and machine token requests cannot complete against the demo domain.** To test end-to-end, configure a real IdP or test identity server with authorization/token/userinfo endpoints; enable HTTPS and register the exact redirect URI at the IdP.

## 8. `WebClient` and the OAuth2 Authorized-Client Filter

The main example sets the Bearer header explicitly to highlight the mechanics. Spring Security Reactive also provides `ServerOAuth2AuthorizedClientExchangeFilterFunction` to attach `OAuth2AuthorizedClient` tokens to outbound `WebClient` calls.

~~~java
// Integration snippet inside @Configuration; do not use concurrently
// with the main WebClient unless token selection boundaries are clear.
@Bean
WebClient oauthWebClient(
        @Qualifier("machineManager")
        ReactiveOAuth2AuthorizedClientManager manager) {

    var oauthFilter =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder().filter(oauthFilter).build();
}
~~~

Import `WebClient`, `ReactiveOAuth2AuthorizedClientManager`, `Qualifier`, `Bean`, and `org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction`.

On each outbound request, you can use:

~~~java
// Excerpt inside a service owning the configured WebClient:
return oauthWebClient.get()
    .uri("https://api.example.test/internal/inventory")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("machine"))
    .retrieve()
    .bodyToMono(String.class);
~~~

**Note:** if called from a background process, ensure the manager receives a stable principal/workload identity; in some configurations, the filter expects an explicit authentication attribute. That is why `MachineResourceClient` explicitly passes `OAuth2AuthorizeRequest.principal("workload-inventory")` rather than relying on a current HTTP user.

**Never** enable `setDefaultOAuth2AuthorizedClient(true)` or `setDefaultClientRegistrationId("machine")` on a shared `WebClient` calling arbitrary URLs. Misconfigured defaults can cause the client to **accidentally send access tokens to hosts outside the intended audience**. Use dedicated clients or per-request attributes selecting registrations explicitly, paired with a downstream host allowlist.

## 9. Calling a Resource API on Behalf of a User

Once a user has logged in via Authorization Code/OIDC, the backend may need to call a resource API using the **user's access token**. This differs from a machine token.

Spring Security WebFlux offers `@RegisteredOAuth2AuthorizedClient` and `ServerOAuth2AuthorizedClientExchangeFilterFunction` to obtain and apply the appropriate authorized client. Example **excerpt inside a controller/service with a configured WebClient**:

~~~java
@GetMapping("/user/profile-from-api")
public Mono<String> profile(
        @RegisteredOAuth2AuthorizedClient("browser")
        OAuth2AuthorizedClient client) {
    return userWebClient.get()
        .uri("https://api.example.test/user/profile")
        .headers(h -> h.setBearerAuth(
            client.getAccessToken().getTokenValue()))
        .retrieve()
        .bodyToMono(String.class);
}
~~~

This snippet **does not run standalone**: `userWebClient` must be injected, the OAuth2 client argument resolver/repository must be configured in the security chain as required (e.g., via `oauth2Client()`), and the token must carry the **audience and scope** accepted by the API. Import `OAuth2AuthorizedClient`, `RegisteredOAuth2AuthorizedClient`, `GetMapping`, and `Mono`.

Do not use an **ID token** to call an API that requires an **access token**, and never use a `machine` token to read Alice's or Bob's private data if downstream expects user-delegated authorization. If an API must be called on a user's behalf yet the initial token lacks the target audience, use an Authorization Server-supported token exchange/on-behalf-of mechanism rather than substituting Client Credentials.

## 10. Rules for SPAs, Mobile Apps, BFFs, and Services

### Server-Side Web Apps

The backend holds client secrets and tokens; the browser holds a session cookie. Use Authorization Code, plus OIDC when login is needed. Configure `state`, PKCE if supported by the IdP, redirect URI allowlists, CSRF, and proper session/cookie flags. Avoid sending secrets or tokens down to the frontend needlessly.

### BFF for an SPA Frontend

The BFF is a confidential OAuth2 client executing Authorization Code on the backend and keeping authorized clients/tokens on the server. The browser talks to the BFF using session cookies and CSRF tokens for state-changing requests. This architecture limits where access tokens appear compared to a pure token-managing SPA.

### Public Client SPA

An SPA cannot hide a `client-secret` in JavaScript. Use Authorization Code + **PKCE** (client authentication `none` if the IdP treats it as a public client). Still evaluate XSS, token storage, redirect URIs, `state`, Refresh Token Rotation, CORS, and provider policies. **Never** use Client Credentials from a browser.

### Native Mobile/Desktop

Use Authorization Code + PKCE via the system browser, platform-valid redirect URIs, and OS-protected token storage. App binaries can be reverse-engineered; hardcoded client secrets are not trustworthy secrets.

### Backend Services and Schedulers

Use Client Credentials, workload identities, least-privilege scopes, and a manager outside `ServerWebExchange`. Never create a fake password-based user account to simulate machine-to-machine auth. When the token endpoint fails, fail closed instead of reusing invalid tokens or granting temporary access.

## 11. Testing the Client Registrations Configuration

The following test confirms both grants are configured properly without calling an IdP.

File `src/test/java/demo/grants/RegistrationContractTest.java`:

~~~java
package demo.grants;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.client.registration
    .ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class RegistrationContractTest {

    @Autowired
    ReactiveClientRegistrationRepository registrations;

    @Test
    void browserUsesAuthorizationCode() {
        StepVerifier.create(
                registrations.findByRegistrationId("browser"))
            .assertNext(reg -> {
                assertEquals(AuthorizationGrantType.AUTHORIZATION_CODE,
                    reg.getAuthorizationGrantType());
                assertTrue(reg.getRedirectUri().contains(
                    "/login/oauth2/code/"));
            })
            .verifyComplete();
    }

    @Test
    void machineUsesClientCredentials() {
        StepVerifier.create(
                registrations.findByRegistrationId("machine"))
            .assertNext(reg -> {
                assertEquals(AuthorizationGrantType.CLIENT_CREDENTIALS,
                    reg.getAuthorizationGrantType());
                assertTrue(reg.getScopes().contains("inventory.read"));
            })
            .verifyComplete();
    }
}
~~~

Run:

~~~bash
./gradlew test --tests 'demo.grants.RegistrationContractTest'
~~~

This test proves **registration properties** map cleanly to `ClientRegistration`; it does not prove the secret is valid at the IdP.

## 12. Testing Authorization Code Redirects with `WebTestClient`

File `src/test/java/demo/grants/AuthorizationCodeRedirectTest.java`:

~~~java
package demo.grants;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class AuthorizationCodeRedirectTest {

    @Autowired
    WebTestClient client;

    @Test
    void startsBrowserGrantWithState() {
        client.get().uri("/oauth2/authorization/browser")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().value("Location", location -> {
                assertTrue(location.startsWith(
                    "https://idp.example.test/oauth2/authorize"));
                assertTrue(location.contains("response_type=code"));
                assertTrue(location.contains("client_id="));
                assertTrue(location.contains("state="));
                assertTrue(location.contains("redirect_uri="));
            });
    }

    @Test
    void publicEndpointDoesNotNeedLogin() {
        client.get().uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("pong");
    }
}
~~~

This test only verifies **initiation** and client registration. It **does not verify callbacks, state/PKCE validation, code exchange, or OIDC ID tokens**; those require tests with a full mock IdP or test IdP tenant. Do not call `/oauth2/authorization/machine` expecting a redirect: the machine grant is not a browser flow.

## 13. Unit Testing the Machine Client Without an IdP

We can create a fake manager returning an `OAuth2AuthorizedClient` with a test token and a fake WebClient exchange to prove the token is sent **to the right downstream**, without hitting a real token endpoint.

File `src/test/java/demo/grants/MachineResourceClientTest.java`:

~~~java
package demo.grants;

import java.net.URI;
import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MachineResourceClientTest {

    private ClientRegistration registration() {
        return ClientRegistration.withRegistrationId("machine")
            .clientId("unit-client")
            .clientSecret("unit-secret")
            .authorizationGrantType(
                AuthorizationGrantType.CLIENT_CREDENTIALS)
            .tokenUri("https://idp.example.test/oauth2/token")
            .build();
    }

    @Test
    void sendsBearerTokenToConfiguredResourceOnly() {
        var accessToken = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "unit-token",
            Instant.now(),
            Instant.now().plusSeconds(300));

        var authorized = new OAuth2AuthorizedClient(
            registration(), "workload-inventory", accessToken);

        ReactiveOAuth2AuthorizedClientManager manager = request -> {
            assertEquals("machine", request.getClientRegistrationId());
            assertEquals("workload-inventory",
                request.getPrincipal().getName());
            return Mono.just(authorized);
        };

        ExchangeFunction fakeResource = request -> {
            assertEquals(
                "https://api.example.test/internal/inventory",
                request.url().toString());
            assertEquals("Bearer unit-token",
                request.headers().getFirst(HttpHeaders.AUTHORIZATION));
            return Mono.just(
                ClientResponse.create(HttpStatus.OK)
                    .body("inventory-response")
                    .build());
        };

        WebClient webClient =
            WebClient.builder().exchangeFunction(fakeResource).build();

        var service = new MachineResourceClient(
            manager,
            webClient,
            URI.create("https://api.example.test/internal/inventory"));

        StepVerifier.create(service.fetchInventory())
            .expectNext("inventory-response")
            .verifyComplete();
    }

    @Test
    void refusesToCallResourceWithoutAuthorizedClient() {
        ReactiveOAuth2AuthorizedClientManager manager =
            request -> Mono.empty();

        ExchangeFunction forbiddenCall = request ->
            Mono.error(new AssertionError(
                "Resource should not be called without a token"));

        var service = new MachineResourceClient(
            manager,
            WebClient.builder().exchangeFunction(forbiddenCall).build(),
            URI.create("https://api.example.test/internal/inventory"));

        StepVerifier.create(service.fetchInventory())
            .expectError(IllegalStateException.class)
            .verify();
    }
}
~~~

Run:

~~~bash
./gradlew test --tests 'demo.grants.MachineResourceClientTest'
~~~

This test verifies **token consumption** and that the resource is not called when the manager provides no token. It **does not** prove `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` actually POSTed to the token endpoint. To test the grant end-to-end, build a mock AS accepting `grant_type=client_credentials`, checking client authentication/scopes, and returning a synthetic token; then mock a Resource Server validating the bearer token and returning 401/403 when invalid.

## 14. Token Lifecycle: Refresh, Expiration, and Caching

**Authorization Code:** The AS can issue an access token and a refresh token. A manager configured with the `refreshToken()` provider can use the refresh token if present and the access token needs renewal. If the refresh token has been revoked or the IdP did not issue one, a new authorization flow may be required.

Example **composite provider snippet** for a web manager:

~~~java
ReactiveOAuth2AuthorizedClientProvider provider =
    ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();
~~~

**Client Credentials:** normally receives only an access token; when it expires, the manager requests a new token using client authentication rather than "refreshing" with a user refresh token. Multiple cache keys can exist per registration and principal. With the demo `InMemoryReactiveOAuth2AuthorizedClientService`, each JVM keeps its own tokens; multiple replicas may request tokens independently.

**Concurrency and availability notes:**

- Multiple concurrent requests seeing an expired token can cause a token storm. Test rate limits/concurrency, backoff, and appropriate caching.
- Do not call the token endpoint on every HTTP request while a token is still valid; leverage the authorized-client manager.
- Separate `invalid_client` (secret/method) from `invalid_scope` (policy) and network/503 errors.
- Do not retry a POST with downstream side effects just because a token was renewed, unless the operation is idempotent.
- Never log raw Bearer tokens, token JSON responses, client secrets, PKCE verifiers, or authorization codes.
- Set sensible timeouts and track OAuth2/Resource Server error metrics while keeping request secrets confidential.

## 15. Distinct Authorization for User vs. Service Tokens

Suppose an API exposes two endpoints:

~~~text
GET /customers/me
GET /internal/inventory
~~~

`/customers/me` typically requires a user-delegated access token and enforces user subject/ownership checks. `/internal/inventory` may target service clients holding `SCOPE_inventory.read` or an equivalent permission. **A Client Credentials token cannot act as a user token** to read Alice's or Bob's private data unless the Resource Server has an explicit policy allowing the app to perform that operation with additional authorization checks.

Common risks:

- **Confused deputy:** an arbitrary user request causes the backend to invoke a high-privilege machine token without checking whether the user is authorized for the target object.
- **Token exfiltration:** a WebClient with default token behavior sends Bearer tokens to an attacker-controlled URL.
- **Wrong audience:** a token valid for service A is sent to service B when the Resource Server checks `aud` loosely.
- **Client secret reuse:** browser apps, batch jobs, and multiple services share one high-privilege credential, making rotation and attribution hard.
- **ID token as access token:** a Resource Server accidentally accepts an ID token issued for the client instead of an API access token.

Sound design: separate registrations; minimal audiences/scopes; independent authorization at the Resource Server; logs recording client ID/workload ID without tokens; user ownership and tenant boundaries; and standard token exchange/on-behalf-of when delegation is truly needed, never faking it with a machine token.

## 16. Common Incidents and Diagnosis

| Symptom | Suggested Cause | What to Check |
| --- | --- | --- |
| `/oauth2/authorization/browser` does not redirect | Missing `oauth2Login`, wrong registration, or chain mismatch | Security config and `browser` registration |
| Redirect URI mismatch | Host/scheme/path differs from IdP allowlist | `{baseUrl}`, proxy, HTTPS |
| Callback reports invalid state | Lost WebSession/cookie, state mismatch | SameSite, session store, repository |
| Authorization Code `invalid_grant` | Code expired/used, wrong PKCE verifier | Code exchange, verifier, redirect URI |
| OIDC ID token error | Issuer/audience/nonce/JWK mismatch | Provider metadata and validation |
| Client Credentials `invalid_client` | Wrong client ID/secret/method or rotated secret | Credential store, `client_secret_basic` |
| Client Credentials `unsupported_grant_type` | AS/client not permitted to use the grant | IdP client settings |
| Machine `invalid_scope` | `inventory.read` not granted to client | AS app permissions |
| Background job missing `ServerWebExchange` | Using web-bound manager outside HTTP | Use service-based manager |
| Request to machine API triggers browser redirect | Picked `browser` registration or wrong manager | Safely log `registrationId`/grant |
| Outbound request missing Bearer token | Manager returned empty, WebClient filter missing, wrong registration | `OAuth2AuthorizeRequest` and manager result |
| Resource Server returns 401 | Token missing/expired/invalid/wrong audience | Verify token, `iss`, `aud`, expiry |
| Resource Server returns 403 | Valid token lacking scopes/permissions | Resource authorization policy |
| Job keeps requesting new tokens | In-memory store or broken caching | Cache key, expiry, concurrency |
| Browser cannot see access token in JS | BFF/server-side app keeps tokens on backend | May be the intended design |
| App boots, login fails on `.test` domain | Demo domain has no real IdP | Use a test IdP tenant / valid endpoints |

**Debugging sequence:** verify app type -> grant/registration -> endpoint (authorize vs. token) -> client authentication -> manager suited to HTTP vs. background -> token/claims -> Resource Server policy -> lifecycle/cookies/proxy/rotation. Never "fix" issues by disabling `state`, dropping PKCE, opening all scopes, or wrongly switching the grant to Client Credentials.

## 17. Pre-Production Checklist

| Item | Target State |
| --- | --- |
| Right actor chosen | User vs. workload clearly separated |
| Grant | User: Authorization Code; machine: Client Credentials |
| SPA/mobile | Public client + PKCE, no secrets sent to client |
| BFF | Tokens on server, proper session/CSRF |
| OIDC | `openid` and ID token verification when identity is needed |
| Client registration | Grant, scopes, client ID, auth method match IdP |
| Redirect URI | Public HTTPS, allowlisted, trusted reverse proxy headers |
| `state` and PKCE | Correlation/PKCE verifier/nonce never lost |
| Manager | Service-based manager for background work, no exchange dependency |
| Token storage | Isolated by registration + principal/tenant, TTL/expiry |
| Resource Server | Validates signature/introspection, `iss`, `aud`, scopes, ownership |
| Secrets | Secrets manager, rotation, audit, never sent to JS/logs |
| WebClient | Tokens sent only to exact allowed host and registration |
| Privilege escalation prevented | Machine tokens never substitute for user tokens |
| Testing | Contract, redirect, bearer propagation, token endpoint integration |
| Negative cases | Bad secret, invalid scope, state mismatch, expired token, 401/403 |
| Deployment | Token caching/concurrency, IdP outage handling, safe tracing |

## 18. Self-Check Questions

**1. Why should an SPA not use Client Credentials?** Because a browser cannot keep a confidential client secret safe. Use Authorization Code + PKCE or move token management into a BFF.

**2. Does Authorization Code have a callback?** Yes, after user authorization. The client must restore the original request, verify `state`, and exchange the code at the token endpoint.

**3. Does Client Credentials need `/authorize` or `state`?** No; this grant obtains tokens directly from the token endpoint for an application identity.

**4. Why should a job use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`?** Because it works outside `ServerWebExchange`/user requests and stores authorized clients at the service level.

**5. Is `principal("workload-inventory")` an API end-user?** No. It is an internal key associating the authorized-client cache; the token carries the identity/permissions granted by the Authorization Server to the client.

**6. Can a Client Credentials token be used to read personal documents under Alice's permissions?** Not automatically; it is an app token, not a delegated user token. If required, proper downstream authorization/delegation must exist.

**7. An OAuth2 response contains `access_token` and `id_token`; which one calls the Resource Server?** Normally the access token with the right audience; the ID token is for OIDC login/client identity validation.

**8. What does `invalid_client` typically relate to?** Client ID, secret/key, authentication method, rotation, or AS policy.

**9. Why should `WebClient` not attach tokens by default to every URL?** It risks leaking tokens to hosts outside the intended audience or attacker-controlled URLs.

**10. Can grants be tested without a real IdP?** You can test registrations, redirects, and Bearer token attachment using fake managers/HTTP; real token exchange testing requires a mock AS or test IdP tenant.

## Key Takeaways

- **Authorization Code** involves a user, browser redirect, callback, `state`, token exchange, and PKCE; OIDC adds ID tokens and `nonce`.
- **Client Credentials** involves an application identity and token endpoint, with no user or callback.
- WebFlux server-side user login uses **`oauth2Login()`**; background services use **`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`** with `clientCredentials()`.
- **`OAuth2AuthorizedClient`/authorized-client services store tokens**, distinct from the authorization-request repository storing temporary `state` and the security-context repository storing `Authentication`.
- **Machine tokens do not replace user tokens.** Resource Servers check subject, scopes, audience, and ownership.
- **Never hardcode client secrets in SPAs/native apps.** Keep tokens/secrets in trusted boundaries, use TLS, and rotate secrets.
- Test both redirect flows and outbound machine tokens; never treat a login HTTP 302 as proof that token exchange succeeded.

### Official Documentation

- [Spring Security 6.5 — Reactive OAuth2 Client: Authorization Grant Support](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html)
- [Spring Security 6.5 — Reactive OAuth2 Client: Core Interfaces](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html)
- [Spring Security 6.5 — Reactive OAuth2 Client: Authorized Client Features](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — Reactive OAuth2 Login: Core Configuration](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/login/core.html)
- [Spring Security 6.5 — Reactive OAuth2 Client Authentication](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/client-authentication.html)
- [RFC 6749 — OAuth 2.0 Authorization Code / Client Credentials](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636)
