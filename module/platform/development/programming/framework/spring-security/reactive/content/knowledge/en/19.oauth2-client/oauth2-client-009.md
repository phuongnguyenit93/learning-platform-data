# Distinguishing Application Token Acquisition from User Token Relay in Spring Security WebFlux

> **Topic:** OAuth2 Client in Spring Security Reactive applications. The goal is to clearly understand when a WebFlux service **acquires an access token itself via client credentials to act on behalf of the application**, when it **relays an access token belonging to an authenticated user context**, and when it must use **on-behalf-of delegation / token exchange** rather than merely re-attaching a Bearer string. Examples target Java 17+, Spring Boot 3.3.x, and Spring Security 6.3.x; before production deployment, use supported versions with current patches.

## 1. Scenario: One API Calling Another API

Suppose there are three components:

- **Frontend:** user Alice logs in.
- **WebFlux Gateway/BFF:** receives requests, checks authentication/authorization, and calls the reports API.
- **Reports API:** downstream endpoint enforcing bearer access token validation rules.

There are two distinct tasks:

1. **System job:** nightly, the application aggregates internal reports. No user is interacting. It needs the **service account's** own permissions.
2. **Alice's request:** Alice views her personal reports. Reports API must know and enforce **Alice's** permissions, not merely the intermediary application's broad permissions.

```text
A. APP TOKEN — client_credentials

Background task / internal service
       |
       v
WebFlux app -- client_id + client authentication --> Authorization Server
       |                   grant_type=client_credentials
       |<------------------ access_token (subject: app/client)
       |
       +-- Authorization: Bearer <APP_TOKEN> --> Reports API
                                                   |
                                         checks client scopes/roles

B. USER TOKEN RELAY — user authority

Alice -- Authorization: Bearer <USER_TOKEN> --> WebFlux Resource Server
                                                   |
                                             checks signature/issuer/
                                             audience/exp/scope
                                                   |
                                      controlled forwarding permitted?
                                                   |
             Reports API <-- Authorization: Bearer <USER_TOKEN>
                                                   |
                                         checks token and Alice's permissions
```

**Core difference:** Flow A uses the **client application's authority**; Flow B carries **authority granted for the user**. Both send an `Authorization: Bearer ...` HTTP header, yet their **permissions, subject, token lifecycle, and security consequences differ**. Never conclude they are interchangeable just because the header name matches.

## 2. Comparison Table to Remember

| Criterion | Application Token (App Token) | User Token Relay |
|---|---|---|
| Represented actor | OAuth2 client/service account | End-user or workload represented by the inbound token |
| How token is obtained | Typically `client_credentials` grant | Existing valid token on inbound Bearer request, or user's access token from OAuth2 Login |
| User interaction when acquiring token? | **No** | User context present at initial authorization; forwarding usually requires no re-login |
| Registration | `authorization-grant-type: client_credentials` | Resource Server receiving JWT needs no `ClientRegistration`; OAuth2 Login typically uses an `authorization_code` registration |
| Typical Spring components | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` and `ReactiveOAuth2AuthorizedClientProvider` | `oauth2ResourceServer().jwt()` + `JwtAuthenticationToken`/`@AuthenticationPrincipal Jwt`; or OAuth2 Login's `OAuth2AuthorizedClient` |
| Token acquisition | Client calls token endpoint and gets a new access token | Relay **does not necessarily call the token endpoint**; it can forward the received access token |
| `sub`/principal | May be client ID or service identity; per IdP | Usually user subject; depends on token/issuer |
| Scope/audience | Per permissions granted to service | Per permissions consented/granted to user |
| Token renewal | Requests a new token on expiry; client credentials usually lack refresh tokens | Uses flow/authorized-client manager for OAuth2 Login; inbound Resource Server JWT cannot self-refresh |
| Downstream authorization | Service permissions, not automatically scoped to Alice | Downstream can apply user-level authorization if token has right audience/scopes |
| Audit | "service performed this" | "Alice performed this", if downstream verifies subject |
| Major risk | **Confused deputy:** service uses broad privileges for an under-authorized user | **Token leakage/audience mismatch:** relaying token to wrong target or service rejecting audience |
| Typical usage | Batch, scheduler, cron, sync pipelines, service-to-service | BFF/gateway/API proxy serving user-scoped actions |

**Note on JWT claims:** there is no universal claim layout forcing every IdP to place a username in `sub` for all `client_credentials` tokens. Access tokens may be JWTs or opaque strings. Rely only on verified claims and specific issuer/resource-server contracts.

## 3. Three Important Patterns — Do Not Merge Them Into One

### 3.1 Pattern A: client_credentials — Application Authorized as Itself

```text
Service                  Authorization Server            Reports API
  |                              |                           |
  | POST /token                  |                           |
  | grant_type=client_credentials                            |
  | client authentication ------>|                           |
  |<------ access_token ---------|                           |
  |                              |                           |
  | GET /internal/report         |                           |
  | Authorization: Bearer APP_TOKEN ------------------------->|
  |<---------------------------------------------------------|
```

The client is identified by the IdP via client ID and an appropriate client authentication method (e.g., `client_secret_basic`, private-key JWT, or mTLS depending on IdP support). The IdP issues a token with the **application's scopes**, never granting Alice's roles simply because Alice hit a service endpoint.

**Use when:** a job has no user session and permissions genuinely belong to the service. Avoid using client credentials for "view Alice's orders" if Reports API must authorize by owner/tenant Alice.

### 3.2 Pattern B: Inbound Bearer Relay — Preserving User Context

```text
Alice -> WebFlux BFF -> Reports API
          |
          +-- @AuthenticationPrincipal Jwt
          +-- Security filter verifies inbound JWT
          +-- Checks route + scope/tenant
          +-- WebClient setBearerAuth(jwt.getTokenValue())
          +-- Sends only to trusted downstream host
```

The BFF acts as a **Resource Server** on the inbound side. It must validate the token **before forwarding**, never grabbing an unverified raw `Authorization` header and sending it to arbitrary URLs. Reports API is **another Resource Server** and must independently verify signature, issuer, expiry, audience, scope, and object-level authorization under its own contract.

**Critical condition:** the token must be issued for the **right downstream audience**. If Alice presents a token with only `aud=frontend-bff`, a Reports API expecting `aud=reports-api` should reject it. Forwarding the raw string does not alter its audience. When the token does not match the target audience, consider token exchange/on-behalf-of rather than loosening downstream audience validation.

### 3.3 Pattern C: OAuth2 Login + Outbound Authorized Client

An application using `oauth2Login()` and a `WebSession` cookie normally receives **no** access token on inbound browser requests; the browser only sends a session cookie. After login, Spring Security can hold an `OAuth2AuthorizedClient` containing the access token for that registration.

```text
Browser -- SESSION cookie --> BFF after oauth2Login
                               |
                          OAuth2AuthenticationToken
                               |
                          OAuth2AuthorizedClient
                          (registration + user token)
                               |
                         WebClient -> Reports API
```

In this case, **fetch the token from the authorized-client repository/service** bound to the user and registration—never copy the `SESSION` cookie and pretend it is an OAuth2 token. If the access token expires and the user flow/refresh token supports it, `ReactiveOAuth2AuthorizedClientManager` can renew/refresh via the provider.

**Distinction:** "User token relay" is often used broadly for both forwarding an inbound bearer token and sending an `oauth2Login` access token downstream. Those two token sources are **technically different**; be explicit about where the token originates.

## 4. What Tokens Contain and What Downstream Must Check

Below are **illustrative claims**, not a mandatory format for all OAuth2 access tokens:

**App token** — might look like:

```json
{
  "iss": "https://auth.example.com",
  "sub": "service-report-worker",
  "aud": ["reports-api"],
  "scope": "reports.system.read",
  "client_id": "report-worker"
}
```

**User token** — might look like:

```json
{
  "iss": "https://auth.example.com",
  "sub": "user-12345",
  "aud": ["reports-api"],
  "scope": "reports.read",
  "client_id": "portal-web"
}
```

Keep in mind:

- `iss`: trusted issuer. Never trust an issuer string claimed directly by an HTTP request.
- `aud`: which resource/API is the **target** of the token; **never** skip audience checks just to make relay convenient.
- `scope`/`scp`: granted permissions; structure and mapping to Spring authorities like `SCOPE_reports.read` depend on the provider/converter.
- `sub`: subject defined by the issuer; `client_credentials` may represent a **service**.
- `client_id`/`azp`: client metadata when provided by the issuer, not proof of an end-user.
- `exp`, `nbf`, signature, key ID, algorithm: must be validated by the resource server.
- **Access tokens** differ from **OIDC ID Tokens**. Never forward `id_token` as a Bearer token to Reports API; ID Tokens let the client verify user identity, not authorize API calls.

**Strictly never log full tokens**, even in debug logs, exceptions, or test reports. An exposed Bearer token can usually be replayed for its remaining lifetime.

## 5. Deciding Which Pattern to Use

| Scenario | Approach |
|---|---|
| Nightly internal job sending aggregate statistics | **Client credentials** with minimal service scope |
| Backend BFF receives Alice's JWT to read Alice's report from an API sharing the same audience | **User token relay** after verification, if permitted by resource server |
| BFF uses OAuth2 Login/cookies and calls an API with user-granted scopes | **OAuth2AuthorizedClient** bound to user/registration via WebClient OAuth2 client |
| API requires a different audience than the inbound token | **Token exchange/on-behalf-of** if supported by Authorization Server; never forward directly |
| Service calls a sensitive-data endpoint for Alice while holding only an app token | Redesign authorization/ACL or verified delegation; never spoof user via `X-User-Id` |
| API between two systems with no user | **Client credentials** or appropriate workload identity |
| Frontend sends ID Token to API | **Never use ID Token as access token**; request an API access token with proper audience |
| Request requires combining user authority + service authority | Design explicit **combined authorization**, typically OBO/token exchange; never just pick the broader token |
| App only validates inbound JWTs | `oauth2ResourceServer().jwt()`; no OAuth2 Client needed if not acquiring outbound tokens |
| App only acquires app tokens in a scheduler | `ReactiveOAuth2AuthorizedClientManager` with `client_credentials`; no login UI needed |

**Choose the token type based on who is being authorized**, not which API is easier to wire.

## 6. Corresponding Spring Security Reactive Interfaces

| Component | Responsibility |
|---|---|
| `ReactiveClientRegistrationRepository` | Looks up OAuth2 client metadata (registration, client ID, grant, provider endpoints) |
| `ClientRegistration` | Defines one application client; **not** an access token |
| `ReactiveOAuth2AuthorizedClientManager` | Authorizes/re-requests tokens, manages `OAuth2AuthorizedClient` via providers |
| `ReactiveOAuth2AuthorizedClientProvider` | Handles grants such as `client_credentials`, `authorization_code`, `refresh_token` |
| `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | Manager capable of running **outside `ServerWebExchange`**, suited to jobs/background services |
| `DefaultReactiveOAuth2AuthorizedClientManager` | Manager bound to `ServerWebExchange`, suited to web requests / OAuth2 Login |
| `ReactiveOAuth2AuthorizedClientService` | Saves/retrieves authorized clients and tokens by registration/principal |
| `ServerOAuth2AuthorizedClientRepository` | Authorized clients per `ServerWebExchange`/principal |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | WebClient filter using `OAuth2AuthorizedClient` to attach outbound Bearer tokens |
| `JwtAuthenticationToken`/`Jwt` | Represents a JWT decoded/validated by Spring Resource Server |
| `ReactiveJwtDecoder` | JWT verification component for WebFlux Resource Server |
| `ServerHttpSecurity.oauth2ResourceServer()` | Protects inbound APIs with bearer tokens |
| `ServerHttpSecurity.oauth2Login()` | Browser login via OAuth2/OIDC |
| `ServerHttpSecurity.oauth2Client()` | Integrates OAuth2 Client features in web flows |

**Remember the two managers:**

- `DefaultReactiveOAuth2AuthorizedClientManager` uses `ServerOAuth2AuthorizedClientRepository` and normally runs in a request context; use it for user/web authorization.
- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` uses `ReactiveOAuth2AuthorizedClientService` and works when **no active request exists**, such as schedulers, queue consumers, or the service tier.

Never copy Servlet interfaces `OAuth2AuthorizedClientManager` or `HttpSecurity` in place of reactive `ReactiveOAuth2AuthorizedClientManager` and `ServerHttpSecurity`.

## 7. Configuring an App Token with client_credentials

Spring Boot reads configuration under the `spring.security.oauth2.client.registration.*` prefix. For a job without a browser:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          machine-api:
            provider: corporate-idp
            client-id: ${SYSTEM_CLIENT_ID}
            client-secret: ${SYSTEM_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [reports.system.read]
        provider:
          corporate-idp:
            token-uri: https://auth.example.com/oauth2/token
```

`SYSTEM_CLIENT_ID`/`SYSTEM_CLIENT_SECRET` are real environment variables supplied via a vault/secrets manager. The client secret is sent only according to an IdP-allowed client authentication method, such as `client_secret_basic` over a trusted HTTPS connection. **Never send secrets to resource APIs**, and never place them in the `Authorization` header of downstream API calls.

### 7.1 When Does Token Acquisition Happen?

A `ReactiveOAuth2AuthorizedClientManager` calls the matching `ReactiveOAuth2AuthorizedClientProvider`, typically requesting a token from the token endpoint if no valid authorized client exists, or requesting a new one upon expiration. With `client_credentials`, renewal is normally **requesting a new token**; do not assume a refresh token exists.

```text
ClientRegistration "machine-api"
   |
   +-- grant = client_credentials
   +-- token-uri = https://auth.example.com/oauth2/token
   +-- scopes = reports.system.read
   |
ReactiveOAuth2AuthorizedClientManager
   |
   +-- authorized client cache/service has valid token? -> reuse
   +-- missing/expired? --> token endpoint --> new token --> save
   |
WebClient outbound Authorization: Bearer <APP_ACCESS_TOKEN>
```

Specific refresh/caching behavior depends on the authorized client manager, provider, clock skew, principal key, and store. **Never cache access token strings in long-lived static variables**, and never distribute tokens through logs or event payloads.

### 7.2 Java 17+: Manager Suited for Jobs Without ServerWebExchange

```java
@Bean
ReactiveOAuth2AuthorizedClientManager machineClientManager(
        ReactiveClientRegistrationRepository registrations,
        ReactiveOAuth2AuthorizedClientService authorizedClients) {

    ReactiveOAuth2AuthorizedClientProvider provider =
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build();

    var manager =
        new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
            registrations, authorizedClients);
    manager.setAuthorizedClientProvider(provider);
    return manager;
}
```

This is a **bean snippet**; the full class with imports is in section 12. Spring Boot may auto-register a default manager depending on version/configuration, yet declaring an explicit manager guarantees only your chosen grants are used for this job.

**Never accidentally use Alice's principal as the app-token key**. For `client_credentials`, the token represents the service; pick a **stable service principal key**, such as `"internal-report-job"`, avoiding fragmenting the token cache per user or creating the illusion that each app token is "Alice's token".

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("machine-api")
        .principal("internal-report-job")
        .build();

Mono<OAuth2AuthorizedClient> authorized =
    machineClientManager.authorize(request);
```

`OAuth2AuthorizedClient` contains the valid access token issued for the application client. If the publisher completes empty or errors, **never** send an unauthenticated downstream request or randomly retry using a user token.

## 8. Properly Relaying an Inbound User Bearer Token

In the HTTP API branch accepting Bearer JWTs:

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http.authorizeExchange(exchanges -> exchanges
            .pathMatchers(HttpMethod.GET, "/api/relay/reports")
                .hasAuthority("SCOPE_reports.read")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

When a JWT is valid, `BearerTokenAuthenticationWebFilter`/the JWT authentication stack creates the authentication; the controller receives `Jwt` via `@AuthenticationPrincipal`. Spring Security has already verified the JWT via the decoder and authorization policy **before** the controller executes.

```java
@GetMapping("/api/relay/reports")
Mono<String> relay(@AuthenticationPrincipal Jwt jwt) {
    // Only reaches here after Spring Security accepts the JWT + scope.
    return reportService.userReports(jwt);
}
```

This is a **method snippet**; the complete project is in section 12.

### 8.1 Why Not Copy the Raw Authorization Header?

```java
// WRONG — do not send an unverified raw header to an arbitrary URL.
String raw = exchange.getRequest().getHeaders()
    .getFirst(HttpHeaders.AUTHORIZATION);
// webClient.get().uri(userSuppliedUrl).header("Authorization", raw) ...
```

Risks:

- The header could be Basic, a malformed Bearer, an expired Bearer, or forged by the client.
- `userSuppliedUrl` could point to an attacker's server (SSRF/token exfiltration).
- The token might be valid for the BFF yet have the **wrong downstream audience**.
- Forwarding a token does not itself enforce object-level permissions inside Reports API.
- Tokens easily leak via tracing or HTTP logging.

**Proper approach with JWTs:** Spring Security Resource Server validates the token; the controller/service reads `Jwt.getTokenValue()` from the verified principal and forwards it only to an **allowlisted downstream origin**. Even then, Reports API must validate it again. For opaque inbound tokens, use appropriate introspection/Authentication mechanisms; never assume a raw token is a JWT.

### 8.2 Right Issuer but Wrong Audience Is Still Invalid for Relay

For example, the BFF accepts `aud=portal-bff` while Reports API requires `aud=reports-api`. Configuring Reports API's verifier to accept `portal-bff` just to "make relay work" breaks the authorization boundary between APIs. Valid designs include:

- The client obtains an access token issued directly for the downstream resource/audience upfront (if the AS supports it).
- Use **OAuth 2.0 Token Exchange (RFC 8693)** / on-behalf-of to obtain a new token with the downstream audience and scopes, on the user's behalf per AS policy.
- Use a backend API on the user's behalf only after verified business authorization checks; never pretend an app token is a user token.

## 9. WebClient: Explicitly Specifying Tokens Instead of Global Defaults

Spring Security Reactive provides `ServerOAuth2AuthorizedClientExchangeFilterFunction` for `WebClient`. The filter can acquire tokens via the authorized-client manager and attach Bearer on requests.

```java
@Bean
WebClient oauth2WebClient(
        ReactiveOAuth2AuthorizedClientManager authorizedClientManager) {

    var oauth2 =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            authorizedClientManager);
    return WebClient.builder().filter(oauth2).build();
}
```

When using this filter, **specify the registration/authorized client on each request** so tokens are never accidentally sent to unauthorized HTTP hosts:

```java
// SNIPPET: machine-api ClientRegistration is already configured.
oauth2WebClient.get()
    .uri("https://reports.example.com/api/system")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("machine-api"))
    .retrieve()
    .bodyToMono(String.class);
```

This requires an appropriate manager/provider and valid subject; in schedulers without `ServerWebExchange`, use the manager/service from section 7.2. Never turn this into a global `WebClient` that attaches app tokens to every HTTP request.

### Two Dangerous Configuration Switches If Used Carelessly

```java
oauth2.setDefaultOAuth2AuthorizedClient(true);
oauth2.setDefaultClientRegistrationId("machine-api");
```

Spring Security documentation advises **caution** because any request passing through the configured client can receive a default token, even requests to services you did not intend to authorize. Use dedicated `WebClient` beans, fixed base URLs, and per-request authorized client selection, especially when calling multiple domains or handling redirects.

**Important:** `setDefaultOAuth2AuthorizedClient(true)` primarily targets the token of a user logged in via OAuth2 Login; `setDefaultClientRegistrationId(...)` selects a default registration (possibly an app client). Neither behavior is **equivalent** to "forwarding an inbound Bearer validated by the resource server".

### When to Set Tokens Manually with setBearerAuth?

In the demo in section 12, the service uses:

```java
.headers(headers -> headers.setBearerAuth(
    authorizedClient.getAccessToken().getTokenValue()))
```

and in the user branch:

```java
.headers(headers -> headers.setBearerAuth(jwt.getTokenValue()))
```

This style is **deliberately explicit** to highlight who owns each token. In production, consider Spring Security's WebClient filter to manage lifecycle when tokens come from an authorized client manager, while still constraining every request, host, and registration to prevent leakage.

## 10. Spring Cloud Gateway TokenRelay Is Not client_credentials

Spring Cloud Gateway Server WebFlux offers a filter named **`TokenRelay`** (requiring the corresponding module/dependency and OAuth2 client configuration). Example in Gateway versions supporting this config style:

```yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: report-api
              uri: https://reports.internal.example
              predicates:
                - Path=/reports/**
              filters:
                - TokenRelay=
```

**This is a Gateway-specific configuration snippet**, not to be pasted into the plain Boot WebFlux project in section 12; exact config paths depend on the Spring Cloud Gateway version. `TokenRelay=` without a registration ID typically relays the authenticated user's access token from OAuth2 Login when that flow is configured; Gateway docs also describe passing a `clientRegistrationId` to select a specific authorized client.

```text
TokenRelay=                    -> typically current user's access token
TokenRelay=some-registration   -> resolves authorized client for that registration
```

Do not assume adding `TokenRelay=` makes an arbitrary Resource Server "log in" or automatically forwards raw inbound JWTs across every scenario and version. Verify authentication config, registrations, token sources, lifecycle, and integration tests. The downstream service behind the gateway must still validate `aud`/scopes per API.

**Authorized client storage:** Gateway's default implementation may use an in-memory authorized-client service. Multiple instances or durability/refresh requirements call for an appropriate repository/service. Never write sensitive tokens to logs or unprotected persistent stores.

### An Easily Misread Configuration

```yaml
filters:
  - TokenRelay=machine-api
```

This **does not necessarily** "relay Alice's token": you have explicitly chosen the `machine-api` registration. If that registration uses `client_credentials`, it can acquire an **app token**, not an end-user token. For per-Alice auditing and authorization, choose the proper flow and token.

## 11. OAuth2 Token Exchange / On-Behalf-Of: When Neither Pattern Suffices

`OAuth 2.0 Token Exchange` (RFC 8693) lets a client present a token (subject token) to the Authorization Server and **request a new token** with the appropriate audience/resource/scopes. Depending on the AS and policy, the flow can preserve actor/delegation claims.

```text
Alice -- USER_TOKEN(aud=bff) --> BFF
                                  |
                                  | grant_type=urn:ietf:params:oauth:grant-type:token-exchange
                                  | subject_token=USER_TOKEN
                                  | audience=reports-api (if AS supports it)
                                  v
                           Authorization Server
                                  |
                                  | evaluates delegation policy
                                  v
                           NEW_USER_DELEGATED_TOKEN
                           aud=reports-api
                                  |
                                  v
                              Reports API
```

Key points:

- Token Exchange is **not** forwarding the original token unchanged; a **new token** is issued at the AS's discretion.
- Do not assume every provider supports RFC 8693; many IdPs offer proprietary "on-behalf-of" mechanisms or distinct policies.
- Restrict requested audiences, scopes, subject tokens, actors, client authentication, TTLs, and auditing.
- Never copy a user's `sub` into a self-signed JWT produced by your app and call it a "delegated token"; doing so can introduce spoofing vulnerabilities.
- Spring Security 6.3+ supports configuring extension grants depending on version; verify exact APIs and packages against docs and your IdP. Keep extension grants clearly separated from `client_credentials` and `authorization_code` in advanced designs.

**When Reports API requires its own audience, returning 403/401 on a BFF-only inbound token is correct**; implement proper exchange rather than disabling issuer/audience checks just to get a demo passing.

## 12. Spring Boot 3.3.13 + WebFlux Example: Two Isolated Token Branches

This section provides the files for a WebFlux app with:

1. **App token branch** in service method `applicationReports()`, using `client_credentials` via `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` and a principal key `"internal-report-job"`. Never expose a public endpoint exercising broad service permissions just for users to click.
2. **User token relay branch** in `GET /api/relay/reports`, accepting only JWTs verified by Resource Server with authority `SCOPE_reports.read`.
3. Fixed downstream URL configured server-side. **The demo never accepts client-supplied URLs**.
4. Unit tests substituting the OAuth token manager and downstream HTTP transport to prove the right Bearer headers are used per branch **without needing a live IdP**.
5. An HTTP test verifying requests without a JWT are rejected.

**Intentional limitations:** `auth.example.invalid` and `reports.example.invalid` have no live systems. Therefore, running full outbound HTTP or token-exchange flows outside tests will not succeed; substitute a real IdP and Reports API with TLS and matching `aud`/scope contracts. Never treat mock tokens in unit tests as proof that production JWT security has been validated.

### 12.1 Directory Layout

```text
webflux-token-boundaries/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/demo/tokens/TokenBoundaryApplication.java
  src/main/java/demo/tokens/SecurityConfiguration.java
  src/main/java/demo/tokens/TokenBoundaryService.java
  src/main/java/demo/tokens/RelayController.java
  src/test/java/demo/tokens/TokenBoundaryServiceTest.java
  src/test/java/demo/tokens/InboundSecurityTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'webflux-token-boundaries'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.tokens'
version = '1.0.0'

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
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

We need both OAuth2 Client for **outbound token acquisition** and OAuth2 Resource Server for **inbound user bearer validation**. Do not include Servlet `spring-boot-starter-web`. `reactor-test` provides `StepVerifier` in unit tests.

### 12.2 application.yml

```yaml
app:
  downstream-base-url: https://reports.example.invalid

spring:
  security:
    oauth2:
      client:
        registration:
          machine-api:
            provider: corporate-idp
            client-id: demo-app-client
            client-secret: demo-not-a-real-secret
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [reports.system.read]
        provider:
          corporate-idp:
            token-uri: https://auth.example.invalid/oauth2/token
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.invalid
          jwk-set-uri: https://auth.example.invalid/oauth2/jwks
          audiences:
            - relay-api
```

Although `demo-not-a-real-secret` is syntactically valid, **it is not a real secret**. Production must retrieve client ID/secret from environment variables or a vault, verify TLS, and avoid committing secrets. Declaring both `issuer-uri` and `jwk-set-uri` explicitly reduces startup metadata discovery dependence; when real tokens arrive, the resource server still needs a reachable JWKS to verify signatures.

`audiences: relay-api` is the audience the **BFF** expects on inbound JWTs. It does **not** prove the token will be accepted by Reports API. If downstream expects `aud=reports-api`, obtain a properly scoped access token or use token exchange. Offline tests verify header selection, **not** downstream acceptance.

### 12.3 Main Application

**src/main/java/demo/tokens/TokenBoundaryApplication.java**

```java
package demo.tokens;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TokenBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(TokenBoundaryApplication.class, args);
    }
}
```

### 12.4 SecurityConfiguration.java

```java
package demo.tokens;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http.authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/relay/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    ReactiveOAuth2AuthorizedClientService authorizedClientService(
            ReactiveClientRegistrationRepository registrations) {
        return new InMemoryReactiveOAuth2AuthorizedClientService(
            registrations);
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager machineClientManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }

    @Bean
    WebClient reportsWebClient(
            @Value("${app.downstream-base-url}") String baseUrl) {
        return WebClient.builder()
            .baseUrl(baseUrl)
            .build();
    }
}
```

Explanation:

- `SecurityWebFilterChain` protects inbound endpoints; the policy requires `SCOPE_reports.read` via Spring's default JWT authority mapper when the issuer emits `scope`/`scp`.
- `ReactiveOAuth2AuthorizedClientService` stores authorized client state. The demo uses in-memory; multi-pod production must address shared caching/persistence, TTLs, and token confidentiality.
- `machineClientManager` is the manager suited to background tasks; its provider enables only `clientCredentials()`.
- `reportsWebClient` points exclusively to a trusted base URL, **accepting no arbitrary URLs from HTTP users**. In production, enforce DNS/TLS allowlists, egress policies, and prevent redirects from leaking tokens to other origins.
- There is no HTTP endpoint "fetching an app token for a user", reducing the risk of substituting system privileges for user permissions.

### 12.5 TokenBoundaryService.java

```java
package demo.tokens;

import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class TokenBoundaryService {

    private final ReactiveOAuth2AuthorizedClientManager machineManager;
    private final WebClient reportsWebClient;

    public TokenBoundaryService(
            ReactiveOAuth2AuthorizedClientManager machineManager,
            WebClient reportsWebClient) {
        this.machineManager = machineManager;
        this.reportsWebClient = reportsWebClient;
    }

    // Used in job/service tier. Do not expose this token to callers.
    public Mono<String> applicationReports() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("machine-api")
                .principal("internal-report-job")
                .build();

        return machineManager.authorize(request)
            .switchIfEmpty(Mono.error(new IllegalStateException(
                "Machine client is not authorized")))
            .flatMap(authorized ->
                reportsWebClient.get()
                    .uri("/api/system/reports")
                    .headers(headers -> headers.setBearerAuth(
                        authorized.getAccessToken().getTokenValue()))
                    .retrieve()
                    .bodyToMono(String.class));
    }

    // jwt MUST be a principal already verified by Spring Resource Server.
    // Relay only when downstream audience/scopes permit.
    public Mono<String> userReports(Jwt jwt) {
        if (jwt == null) {
            return Mono.error(new IllegalArgumentException(
                "Validated JWT principal is required"));
        }

        return reportsWebClient.get()
            .uri("/api/user/reports")
            .headers(headers -> headers.setBearerAuth(
                jwt.getTokenValue()))
            .retrieve()
            .bodyToMono(String.class);
    }
}
```

How to read this:

1. `applicationReports()` takes no `Jwt` and uses no user principal. It requests an app token under the `machine-api` registration and stable key `internal-report-job`.
2. If token acquisition fails, it returns an error; **never fall back** to an anonymous request, raw inbound token, or session cookie.
3. `userReports(Jwt jwt)` only accepts a `Jwt` from the verified security context **passed by the controller**, never reading raw headers or manually parsing tokens.
4. Both methods target distinct downstream paths matching server authorization rules. In production, Reports API must still verify claims/scopes/tenant on the token.
5. Both return Reactor `Mono` without calling `block()` on a WebFlux thread.
6. Never share acquired tokens across users via static fields or logs; app tokens may be cached by the manager under the service principal, while user tokens are scoped strictly to the verified user's request.
7. If downstream returns cross-origin redirects, ensure the HTTP client never forwards Bearer tokens to another host; configure egress policies and disable unconditional redirect following.

### 12.6 RelayController.java

```java
package demo.tokens;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
public class RelayController {

    private final TokenBoundaryService service;

    public RelayController(TokenBoundaryService service) {
        this.service = service;
    }

    @GetMapping("/api/relay/reports")
    public Mono<String> relay(@AuthenticationPrincipal Jwt jwt) {
        if (jwt == null) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.UNAUTHORIZED));
        }
        return service.userReports(jwt);
    }
}
```

**Note:** The controller does **not** expose `applicationReports()`. That is a system/service branch invoked by a scheduler or trusted internal workflow as needed. If business requirements genuinely demand an endpoint triggering a job, enforce strict authorization/admin approval, rate limits, auditing, allowlisted actions, and confused-deputy protections—never expose broad service authority to every user just because they logged in.

### 12.7 Unit Tests: Verifying App Tokens Stay Separate from User Tokens Without an IdP

**src/test/java/demo/tokens/TokenBoundaryServiceTest.java**

```java
package demo.tokens;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TokenBoundaryServiceTest {

    private static OAuth2AuthorizedClient machineToken() {
        ClientRegistration registration =
            ClientRegistration.withRegistrationId("machine-api")
                .clientId("demo-machine-client")
                .clientSecret("fake-secret")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://auth.example.invalid/token")
                .build();

        Instant now = Instant.now();
        OAuth2AccessToken access = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "app-token-123",
            now,
            now.plusSeconds(300),
            Set.of("reports.system.read"));

        return new OAuth2AuthorizedClient(
            registration, "internal-report-job", access);
    }

    private static Jwt userJwt(String value, String username) {
        Instant now = Instant.now();
        return Jwt.withTokenValue(value)
            .header("alg", "RS256")
            .claim("sub", username)
            .claim("scope", "reports.read")
            .issuedAt(now)
            .expiresAt(now.plusSeconds(300))
            .build();
    }

    private static TokenBoundaryService service(
            ReactiveOAuth2AuthorizedClientManager manager,
            List<String> sentHeaders) {

        ExchangeFunction downstream = request -> {
            sentHeaders.add(request.headers()
                .getFirst(HttpHeaders.AUTHORIZATION));

            ClientResponse response = ClientResponse
                .create(HttpStatus.OK)
                .header(HttpHeaders.CONTENT_TYPE,
                    MediaType.TEXT_PLAIN_VALUE)
                .body("downstream-ok")
                .build();

            return Mono.just(response);
        };

        WebClient fakeWebClient = WebClient.builder()
            .baseUrl("https://reports.example.invalid")
            .exchangeFunction(downstream)
            .build();

        return new TokenBoundaryService(manager, fakeWebClient);
    }

    @Test
    void appTokenUsesFixedRegistrationAndMachinePrincipal() {
        var captured = new ArrayList<String>();
        AtomicReference<String> registration = new AtomicReference<>();
        AtomicReference<String> principal = new AtomicReference<>();

        ReactiveOAuth2AuthorizedClientManager manager = request -> {
            registration.set(request.getClientRegistrationId());
            principal.set(request.getPrincipal().getName());
            return Mono.just(machineToken());
        };

        var app = service(manager, captured);

        StepVerifier.create(app.applicationReports())
            .expectNext("downstream-ok")
            .verifyComplete();

        assertEquals("machine-api", registration.get());
        assertEquals("internal-report-job", principal.get());
        assertEquals(List.of("Bearer app-token-123"), captured);
    }

    @Test
    void userRelayForwardsUserTokenNotMachineToken() {
        var captured = new ArrayList<String>();
        ReactiveOAuth2AuthorizedClientManager manager = request ->
            Mono.error(new IllegalStateException(
                "Should not acquire machine token"));

        var app = service(manager, captured);

        StepVerifier.create(app.userReports(
                userJwt("user-token-alice", "alice")))
            .expectNext("downstream-ok")
            .verifyComplete();

        assertEquals(
            List.of("Bearer user-token-alice"), captured);
    }

    @Test
    void twoUsersRetainDistinctBearerTokens() {
        var captured = new ArrayList<String>();
        ReactiveOAuth2AuthorizedClientManager manager = request ->
            Mono.empty();

        var app = service(manager, captured);

        StepVerifier.create(app.userReports(
                userJwt("token-alice", "alice")))
            .expectNext("downstream-ok").verifyComplete();

        StepVerifier.create(app.userReports(
                userJwt("token-bob", "bob")))
            .expectNext("downstream-ok").verifyComplete();

        assertEquals(List.of(
            "Bearer token-alice", "Bearer token-bob"), captured);
    }

    @Test
    void cannotAcquireAppTokenStopsBeforeDownstream() {
        var captured = new ArrayList<String>();
        ReactiveOAuth2AuthorizedClientManager manager = request ->
            Mono.empty();

        var app = service(manager, captured);

        StepVerifier.create(app.applicationReports())
            .expectError(IllegalStateException.class)
            .verify();

        assertTrue(captured.isEmpty());
    }

    @Test
    void appTokenProviderErrorDoesNotDowngradeToAnonymous() {
        var captured = new ArrayList<String>();
        ReactiveOAuth2AuthorizedClientManager manager = request ->
            Mono.error(new IllegalStateException("token unavailable"));

        var app = service(manager, captured);

        StepVerifier.create(app.applicationReports())
            .expectErrorMessage("token unavailable")
            .verify();

        assertTrue(captured.isEmpty());
    }

    @Test
    void applicationFlowDoesNotUseUserBearerToken() {
        var captured = new ArrayList<String>();
        ReactiveOAuth2AuthorizedClientManager manager = request ->
            Mono.just(machineToken());

        var app = service(manager, captured);

        StepVerifier.create(app.userReports(
                userJwt("USER-ONLY", "alice")))
            .expectNext("downstream-ok")
            .verifyComplete();

        StepVerifier.create(app.applicationReports())
            .expectNext("downstream-ok")
            .verifyComplete();

        assertEquals(List.of(
            "Bearer USER-ONLY", "Bearer app-token-123"), captured);
    }

    @Test
    void missingValidatedUserPrincipalIsRejected() {
        var captured = new ArrayList<String>();
        ReactiveOAuth2AuthorizedClientManager manager = request ->
            Mono.just(machineToken());

        var app = service(manager, captured);

        StepVerifier.create(app.userReports(null))
            .expectError(IllegalArgumentException.class)
            .verify();

        assertTrue(captured.isEmpty());
    }
}
```

**Seven test methods** verify using a fake `ReactiveOAuth2AuthorizedClientManager` and fake `ExchangeFunction` that the right Bearer headers are chosen, registrations/principals stay stable, tokens are never crossed, and token acquisition failures abort before hitting downstream. Because the fake `ExchangeFunction` sends no network traffic, tests run offline.

**Explicit limitations:** unit tests construct `Jwt` via its builder **without signature verification**; real signature checking is performed by Spring Security Resource Server on real HTTP requests. These tests only prove the service **consumes a `Jwt` already verified by the controller**, not end-to-end authentication protocols. Verifying signatures and audiences requires integration tests with mock JWK/Authorization Servers or a real IdP.

### 12.8 HTTP Test: Missing Bearer Token Is Rejected

**src/test/java/demo/tokens/InboundSecurityTest.java**

```java
package demo.tokens;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class InboundSecurityTest {

    @Autowired
    WebTestClient client;

    @Test
    void relayEndpointRequiresBearerAuthentication() {
        client.get().uri("/api/relay/reports")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**This single HTTP test** verifies anonymous requests never reach controller/relay logic; it does **not** test full JWT validation, token acquisition, or downstream calls. With both `issuer-uri` and `jwk-set-uri` declared, the app can build the decoder from the JWKS URI without fetching IdP metadata at startup, though verifying a real bearer JWT still requires a reachable JWKS.

### 12.9 Running Tests and Startup

```bash
gradle test
gradle bootRun

# Inbound endpoint without bearer JWT -> 401, downstream not called:
curl -i http://localhost:8080/api/relay/reports
```

Use the appropriate Gradle Wrapper when present: `./gradlew test` or Windows `gradlew.bat test`. For requests to succeed on a real system, a **real** access token issued by a valid issuer with `aud=relay-api` and scope `reports.read` is required, and downstream must accept that audience and permission. Never use unit-test fake tokens against production APIs.

**Not claiming Gradle was run here:** the source code was reviewed against Spring Security 6.x; test outcomes are expectations that must be confirmed by running in an environment with real dependencies.

## 13. Production Design: Never Turn Your Service Into a Confused Deputy

**Confused deputy** occurs when a highly privileged component acts on behalf of a less-privileged caller without enforcing the caller's permissions.

```text
Alice (only permitted to view Alice's reports)
    |
    | GET /api/admin/export?tenant=bob
    v
BFF uses app token holding reports.system.read across all tenants
    |
    v
Reports API trusts app token, returns Bob's tenant report
    |
    v
BFF returns Bob's data to Alice       <-- vulnerability without permission check
```

**Do not** do this:

```java
// Anti-pattern: app token used as proof that the user has permission.
return machineClientManager.authorize(request)
    .flatMap(client -> callAdminReport(
        client.getAccessToken().getTokenValue(),
        requestTenantFromUser));
```

An app token may carry access to large datasets. If a user triggers a job via an API, the BFF must enforce *user* permissions and business targets server-side first, audit the requester, allowlist actions, and have downstream verify delegation/ACLs as needed. Even if the app adds an `X-User-Id` header, downstream should not treat that header as proof of authorization without a strict trust boundary/mTLS and explicit policy.

### App Permissions Are Not User Permissions

- `reports.system.read` and `reports.read` are distinct scopes under issuer policies.
- Never collapse all roles/scopes into ADMIN simply because the client holds a secret.
- Service accounts should follow **least privilege**, short lifetimes, rotation, and mTLS/private-key JWT where appropriate.
- User tokens must have audience, scope, and ownership validated downstream—never inferred from a username in the URL.
- When both app and user participate, token exchange/combined delegation must be approved by the AS.

## 14. Protecting Tokens in Reactive WebClient

### 14.1 Sending Tokens Only to the Right Host and Route

Even when `WebClient` specifies a fixed base URL, never take URLs or hosts from query parameters or JSON bodies without allowlisting. Risks include SSRF, DNS rebinding, cross-origin redirects, and leaking Bearer tokens to untrusted endpoints.

Configure egress firewalls, HTTPS with certificate verification, timeouts, bounded retries, and fixed base URLs. If redirect-following is enabled, verify exactly whether the HTTP library keeps or strips `Authorization` on cross-origin redirects; generally **do not follow** cross-origin redirects on Bearer requests.

### 14.2 Reactor Context and Background Tasks

`ReactiveSecurityContextHolder` carries user `Authentication` via Reactor Context in the request pipeline. Schedulers/jobs lack user context; never call `ReactiveSecurityContextHolder.getContext()` and inject a synthetic `"anonymous=user service"` to simulate one. Use a `client_credentials` manager such as `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`.

Never call `block()`/`subscribe()` manually inside WebFlux controllers. `Mono`/`Flux` are subscribed by the framework; jobs/schedulers must manage subscriptions, lifecycle, and error handling properly inside the scheduler/job runner.

### 14.3 Token Expiration, Refresh, and Retries

- With client credentials, expired app tokens are usually **renewed** via a fresh grant per the provider.
- With OAuth2 Login, refresh tokens may be available if issued by the AS and supported by the authorized-client provider.
- With inbound user JWT relay, the BFF **has no refresh token** to renew it; typically return 401 when expired, or perform delegation via a designed flow.
- When downstream returns 401/403, never fall back from a user token to an app token. That can create a privilege-escalation vulnerability.
- Never retry infinitely on 401/`invalid_client`, avoiding token storms and throttling; distinguish 429/5xx and apply backoff.
- Token caches must key strictly by principal/registration/tenant; prevent one user from receiving another user's token.

### 14.4 Header Injection, Logging, and Exceptions

Never print raw tokens in logs or request/response `toString()` output. When tracing:
- Log the registration ID or grant type when useful; never the client secret.
- Record request correlation IDs, status, latency, and **anonymized/sanitized** identities per policy.
- Redact `Authorization`, `Cookie`, query codes/states, `Set-Cookie`, and access/refresh tokens.
- Never send access tokens back to the frontend just for debugging.

## 15. Token Exchange Is Not Manually Editing a JWT

When an inbound JWT has `aud=bff` and downstream requires `aud=reports-api`, strictly never do this:

```java
// Broken security model:
// decode JWT, change aud claim, re-encode Base64, attach to Authorization.
```

The signature becomes invalid; if your application re-signs tokens under its own identity and downstream trusts that loosely, you have invented a custom authorization protocol requiring rigorous design, not RFC 8693.

A **trusted Authorization Server** must decide whether to let the BFF exchange the subject token for one targeting Reports API. Downstream validates the new token and may retain user/actor identity for auditing. Each provider has specific nuances, so consult your IdP's documentation.

## 16. Recommended Test Matrix

| Test | What It Must Prove |
|---|---|
| App token request uses `grant_type=client_credentials` | No user authorization redirect triggered; uses right client credentials |
| Manager uses `machine-api` registration and key `internal-report-job` | No accidental per-user token issuance |
| User relay accepts `Jwt` from authenticated principal | Does not trust raw `Authorization` header |
| Alice and Bob make separate calls | Outbound Bearer headers differ; tokens never mixed |
| App token missing/errors | Never calls downstream anonymously or falls back to user token |
| HTTP without JWT | 401 before controller |
| HTTP JWT with bad signature/issuer/exp/aud | 401, no relay (requires mock IdP/JWKS) |
| Valid JWT lacking `reports.read` | 403, no relay |
| Valid scoped JWT for another tenant's record | Downstream/service denies per owner/tenant |
| Token valid for BFF yet wrong downstream audience | Downstream rejects, or token exchange used |
| OAuth2 Login/cookie mode | Authorized-client token fetched for right registration and principal |
| Outbound client hits fake host or odd redirect | `Authorization` header does not leak |
| 401/403 from downstream | No fallback to app token; clean error handling |
| Concurrent requests on expired app token | Bounded renewal/caching, no request storm |
| Client secret rotation / provider outage | Fails closed, metrics/audit emitted, secrets unexposed |
| Gateway `TokenRelay` (if used) | Verify no-ID vs. registration ID picks the right token kind |
| Token Exchange/OBO (if used) | AS itself issues token with right `aud`/scopes, preserving delegation/audit |
| Multiple pods | Authorized-client service and session/token caching behave consistently |

Unit tests in section 12 only verify **header routing and isolation**. To claim OAuth2/OIDC integration works, you also need a real/mock IdP, verified signed JWTs, token endpoints, callbacks/state or `client_credentials` grants, JWKS/clock/issuer/audience checks, and downstream authorization.

## 17. Common Mistakes

| Mistake | Why It Is Wrong | Fix |
|---|---|---|
| Using `client_credentials` and treating the token as Alice | The grant does not represent a user | Relay user token or use OBO/delegation |
| Forwarding unvalidated inbound `Authorization` | Token may be forged, wrong scheme, or wrong audience | Validate in Resource Server first |
| Using `id_token` to call APIs | ID Token is not an API access token | Obtain a proper API access token |
| Relaying a BFF-only `aud` token | Downstream is not an intended audience | Request a resource-scoped token or Token Exchange |
| Setting `setDefaultOAuth2AuthorizedClient(true)` everywhere | User tokens may attach to wrong hosts | Per-request authorized client/registration; separate WebClients |
| Setting a default machine registration on a multi-domain client | App tokens may be sent to wrong endpoints | Host allowlist and per-request selection |
| Letting users trigger app-token exports unchecked | Confused deputy, privilege escalation | Enforce user permissions first, restrict service scopes |
| Requesting machine tokens using the user's username as principal | Cache fragmentation, misleading context | Use a fixed service principal |
| Calling `DefaultReactiveOAuth2AuthorizedClientManager` in an exchangeless scheduler | Manager targets HTTP requests | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| Using Servlet managers in WebFlux | Wrong API/reactive context | Use `Reactive...` managers/repositories |
| Falling back to user token when app token expires | Weakens security boundaries / privilege confusion | Fail closed, renew via proper grant |
| Parsing JWT claims without validation | Trusts client-forged data | `ReactiveJwtDecoder` / Resource Server |
| Skipping scopes/tenant checks in Reports API | Authentication is not authorization | Resource Server + business ACLs |
| Logging `Authorization`/`clientSecret` | Exposes bearer tokens/secrets | Redact logs, use vault/rotation |
| Omitting `client_credentials` provider in manager | Manager cannot acquire app tokens | Configure `ReactiveOAuth2AuthorizedClientProviderBuilder.clientCredentials()` |
| Assuming `TokenRelay=machine-api` is Alice's token | Registration may use `client_credentials` | Inspect grant type and actual authorized client |
| Taking `targetUrl` from query to forward tokens | SSRF/exfiltration | Fixed/allowlisted HTTPS downstreams |
| Changing audience by editing JWT text | Breaks signature/valid authority | AS Token Exchange or acquire new token |
| Confusing token-endpoint 401 with downstream 401 | Different systems and credentials | Distinguish failure source and telemetry |
| Not testing without a user | Jobs fail when expecting a principal | App manager with service principal |

## 18. Pre-Deployment Checklist

1. Document whether each outbound API **needs app permissions or user permissions**. Never decide based on "whichever token is handy".
2. For app tokens: configure `client_credentials` registration, client auth, minimal scopes, and trusted token URI.
3. For jobs: use `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` with a stable service principal key.
4. For user relay from HTTP Bearer: validate the token at the Resource Server (signature/issuer/audience/exp) plus scope/route before relaying.
5. Relay only **access tokens**, never OIDC ID Tokens or session cookies.
6. Verify **downstream** issuer/audience/scopes; never assume BFF acceptance implies downstream acceptance.
7. For OAuth2 Login: retrieve the `OAuth2AuthorizedClient` bound to the exact user and registration—never treat raw cookies as access tokens.
8. When two resources have distinct audiences, use token exchange/OBO per IdP policy or design a single audience-appropriate grant.
9. Separate `WebClient` instances by token source and target host; restrict `setDefault...` and never send Bearer to arbitrary URLs.
10. Never fall back from a failed user token to a higher-privilege app token.
11. Enforce business/tenant/ownership permissions downstream, not just scopes.
12. Use a secrets manager, TLS, secure storage, and rotation; never log access/refresh tokens or client secrets.
13. Configure bounded connection pools, timeouts, status-aware retries, circuit breakers, and redacted tracing.
14. Test userless app/job flows, distinct users, invalid JWTs, wrong audiences, missing scopes, expired tokens, and downstream errors.
15. For Gateway `TokenRelay`, verify module/config versions and the effect of omitting vs. passing `clientRegistrationId`.
16. Check multi-pod authorized-client caching, refresh lifetimes, clock skew, and token endpoint outages.
17. Review security after upgrading Spring Boot/Spring Security/IdP; never assume "current" docs match 6.x/7.x identically.

## 19. Applied Exercises

1. Diagram the flow for a userless batch job: who calls the token endpoint, who holds the secret, and why is `sub` not Alice?
2. Diagram Alice calling the BFF with a JWT: where are signature, scope, and audience checked? Must Reports API re-verify?
3. Change the YAML from `client_credentials` to `authorization_code` and explain why a scheduler cannot complete user login merely by switching grants.
4. Test the demo with `StepVerifier` when the manager returns `Mono.empty()`, then when the token endpoint errors. Should any outbound request be sent?
5. Add Bob's user token and prove Alice's Bearer token is never mixed with Bob's.
6. Design token claims and resource-server policies when Reports API requires `aud=reports-api` while the BFF's inbound JWT carries `aud=relay-api`.
7. Contrast an `OAuth2AuthorizedClient` from an `oauth2Login` user with a `JwtAuthenticationToken` from an `oauth2ResourceServer` request.
8. Explain why `ServerOAuth2AuthorizedClientExchangeFilterFunction.setDefaultOAuth2AuthorizedClient(true)` risks token leaks if `WebClient` calls multiple hosts.
9. Write a test simulating a redirect URL from Reports API to an unknown domain and verify no `Authorization` header is sent to that domain.
10. Use Spring Cloud Gateway `TokenRelay` with and without `clientRegistrationId`, stating the conditions under which tokens come from the user vs. the registration.
11. Design a policy for Alice triggering a "full tenant export" when only the app holds broad system scopes; how do you prevent confused deputy?
12. Read RFC 8693 and identify the roles of `subject_token`, `audience`/`resource`, and `scope`; why must the AS authorize delegation?
13. Create an integration test with a mock token endpoint for `grant_type=client_credentials`, Basic client authentication, and token expiry/renewal.
14. Write tests for inbound 401 and insufficient-scope 403 using a mock signed JWT/decoder; verify downstream is never called.
15. List everything that must be redacted in logs: cookies, access tokens, refresh tokens, authorization codes, client secrets, and user PII.

## Conclusion

Two outbound requests may both use `Authorization: Bearer ...` yet carry **completely different security semantics**. With `client_credentials`, the app requests a token **on behalf of the service/client**, fitting schedulers or machine-to-machine calls; in Spring Security WebFlux, the job manager is `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`. With **user token relay**, the app must start from a **verified** token bound to a user context (such as a `Jwt` in Resource Server or an `OAuth2AuthorizedClient` from OAuth2 Login) and forward it only to trusted downstreams **when audience and scopes match**. If the downstream API requires a different audience or delegated authority, use **OAuth2 Token Exchange/on-behalf-of** rather than disabling validators or substituting app tokens for user tokens. Safe design rests on isolating **identity, grant, token lifecycle, audience, and business permissions**, backed by negative tests before deployment.

## References

1. Spring Security — Reactive OAuth2 Client, core classes and background service manager: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
2. Spring Security — Authorized Client features and `WebClient` OAuth2 filter: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html
3. Spring Security 6.5 — OAuth2 WebFlux, client credentials, and WebClient integration: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
4. Spring Security — Client Credentials grant and reactive token response client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorization-grants.html
5. Spring Boot 3.3 — OAuth2 Resource Server JWT issuer/JWKS/audiences properties: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
6. Spring Cloud Gateway Server WebFlux — TokenRelay GatewayFilter: https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/tokenrelay-factory.html
7. Spring Security 6.3.8 — InMemoryReactiveOAuth2AuthorizedClientService: https://docs.spring.io/spring-security/site/docs/6.3.8/api/org/springframework/security/oauth2/client/InMemoryReactiveOAuth2AuthorizedClientService.html
8. RFC 6749 — OAuth2 Authorization Framework / Client Credentials: https://www.rfc-editor.org/rfc/rfc6749
9. RFC 6750 — Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
10. RFC 8693 — OAuth2 Token Exchange: https://www.rfc-editor.org/rfc/rfc8693
11. OpenID Connect Core 1.0 — ID Token vs Access Token: https://openid.net/specs/openid-connect-core-1_0.html
