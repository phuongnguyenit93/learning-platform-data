# Renewing Access Tokens and Handling Expired Refresh Tokens in Spring Security Reactive OAuth2 Client

## 1. Objectives and Concepts

A Spring WebFlux application acts as an **OAuth2 Client**: the browser logs in through an Authorization Server, and the application then uses `WebClient` to send access tokens to a Resource Server. Access tokens have a limited lifetime. Sending an expired token causes the Resource Server to typically return HTTP 401. If the Authorization Server has issued a **valid refresh token**, the client can obtain a new access token without forcing the user to log in again.

**Only the Authorization Server issues tokens.** An OAuth2 Client cannot modify a JWT's `exp`, re-sign tokens, or send a refresh token as a Bearer token to a Resource Server.

Objectives:

1. Distinguish access token, refresh token, authorization code, ID token, and session cookie.
2. Understand `authorization_code` and `refresh_token` grants, the token endpoint, and refresh rotation.
3. Understand `expires_in`, `issuedAt`, `expiresAt`, and the 60-second clock-skew refresh threshold.
4. Use `ReactiveOAuth2AuthorizedClientManager`, `RefreshTokenReactiveOAuth2AuthorizedClientProvider`, `ServerOAuth2AuthorizedClientExchangeFilterFunction`, and authorized-client stores.
5. Understand why services/background tasks must choose a different manager than HTTP requests.
6. Properly handle `invalid_grant`, revoked tokens, missing refresh tokens, 401/403, and network errors.
7. Run a Java 17+ Spring Boot WebFlux example with OAuth2 Client and WebClient.
8. Test the provider, rotation, expiration, and persistence using `StepVerifier` and a fake Token Endpoint without a real IdP.
9. Prevent refresh token leaks, cross-user token misuse, concurrent refresh races, and retry loops.

### 1.1. Roles

~~~text
User browser
   | login/consent
   v
OAuth2 Client (Spring WebFlux)
   | authorization_code
   v
Authorization Server / IdP
   | access_token + optional refresh_token
   v
OAuth2AuthorizedClient stored at backend
   | Authorization: Bearer access_token
   v
Resource Server (API accepting Bearer)
   | authorized data
   v
WebFlux application
~~~

| Component | Role | Where Used |
| --- | --- | --- |
| Authorization code | Short-lived, one-time code used at the Token Endpoint | Exchanged by client for tokens |
| Access token | Credential to call resources with specific scopes/audience | Resource Server |
| Refresh token | Credential to request a new access token | Authorization Server Token Endpoint |
| OIDC ID token | Proof of end-user login event intended for the OIDC client | Does not replace access token |
| WebSession cookie | Maintains the WebFlux application session | Browser to application |
| Client secret | Authenticates a confidential client with the Authorization Server | Backend only, never frontend |

An access token can be a JWT or an opaque string. **The OAuth2 Client does not need to assume it is always a JWT**. Expiration is represented by `OAuth2AccessToken.getExpiresAt()`. A refresh token may have a longer lifetime, yet can still be revoked, expire, or be rotated.

### 1.2. Different Lifecycles

- The app's `WebSession` may still be active after the IdP access token expires.
- A new access token can be refreshed while the user remains logged in.
- An expired or revoked refresh token may require the user to re-authorize.
- A logged-out `WebSession` **is never resurrected** just because the backend still holds a refresh token.
- Holding a refresh token does not allow a WebFlux API user to bypass `authorizeExchange`.

## 2. Authorization Code and the refresh_token Grant

A login usually starts at the Spring Security endpoint:

~~~http
GET /oauth2/authorization/training HTTP/1.1
Host: app.example.org
~~~

Spring Security redirects the browser to the provider's Authorization Endpoint. After authentication/consent and state verification, the default callback may look like:

~~~http
GET /login/oauth2/code/training?code=<authorization-code>&state=<state> HTTP/1.1
~~~

Spring Security exchanges the code for an access token and optional refresh token, then saves `OAuth2AuthorizedClient` keyed by `ClientRegistration` and principal. OIDC may also include an ID token, but an ID token never replaces an access token when calling a Resource Server.

### 2.1. Refresh Request

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.org
Authorization: Basic <encoded-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<refresh-token-value>
~~~

Client authentication depends on the provider: `client_secret_basic`, `private_key_jwt`, mTLS, or another method. All must use HTTPS. Never assume secrets always sit in the form body or that a Token Endpoint accepts every grant.

Example success response:

~~~json
{
  "access_token": "access-next",
  "token_type": "Bearer",
  "expires_in": 900,
  "refresh_token": "refresh-next",
  "scope": "profile api.read"
}
~~~

`expires_in` is **seconds**, not an epoch timestamp. Granted scopes may be narrowed. If the provider rotates the refresh token from R1 to R2, the client **must save R2**; R1 may be invalidated immediately. A refresh response does not always contain a new `refresh_token`, depending on the provider and policy. Never overwrite the existing refresh token with null without understanding the implementation.

### 2.2. When No Refresh Token Exists

**`RefreshTokenReactiveOAuth2AuthorizedClientProvider`** cannot refresh if the authorized client has no refresh token. That is not necessarily a bug: the Authorization Server may decline to issue refresh tokens or require `offline_access`/consent. For user `authorization_code`, re-authorization or re-login is needed; for a machine account's `client_credentials`, request a new access token via `client_credentials` **without needing a user refresh token**.

### 2.3. Refresh Grants Do Not Automatically Elevate Permissions

A refresh token does not turn a user into an admin or expand access token scopes on its own. The Resource Server still validates audience, scopes, and object/tenant permissions. If the API returns `403 insufficient_scope`, refreshing under the same grant usually will not resolve the missing permission.

## 3. Expiry, Skew, and Preemptive Refresh

Spring Security's `OAuth2AccessToken` stores `issuedAt` and `expiresAt`. `RefreshTokenReactiveOAuth2AuthorizedClientProvider` uses `Clock`/`clockSkew` to decide whether the access token has reached the renewal window. Spring Security 6.5 Javadoc states a **default `clockSkew` of 60 seconds**.

Roughly, renewal triggers once the current time passes:

~~~text
expiresAt - clockSkew
~~~

Example for a token expiring at 10:05:00:

| Request | Time Remaining | Action with 60-Second Skew |
| --- | --- | --- |
| 10:02:00 | 180 seconds | Do not refresh |
| 10:03:59 | 61 seconds | Do not refresh |
| 10:04:01 | 59 seconds | Refresh if refresh token exists |
| 10:05:01 | Token already expired | Refresh if refresh token exists |

Clock skew reduces clock-drift and network-latency risks, though it is not magic. Setting a skew too large relative to token TTL causes every request to hit the Token Endpoint repeatedly. Synchronize clocks with NTP and test using `Clock.fixed` rather than sleeping near expiry boundaries.

~~~java
RefreshTokenReactiveOAuth2AuthorizedClientProvider provider =
        new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
provider.setClock(Clock.systemUTC());
provider.setClockSkew(Duration.ofSeconds(60));
~~~

This is only an API snippet; complete Java tests appear in section 7.

## 4. Reactive Abstractions

### 4.1. ClientRegistration

Configuration of the OAuth2 client's identity with the provider: `registrationId`, `clientId`, client authentication method, grant, `redirectUri`, `authorizationUri`, `tokenUri`, scopes, and issuer/JWK/userinfo metadata. `ClientRegistration` is not a token.

### 4.2. OAuth2AuthorizedClient

Represents an authorized client **for a specific principal**:

~~~text
OAuth2AuthorizedClient
  ClientRegistration: training
  principalName: alice
  OAuth2AccessToken: access-current
  OAuth2RefreshToken: refresh-current or null
~~~

There is no shared static access token for Alice and Bob. Accurate `(registrationId, principalName)` binding is the boundary preventing cross-user data leaks.

### 4.3. ReactiveOAuth2AuthorizedClientManager

The manager coordinates:

1. Loading the authorized client from the repository/service.
2. Using the appropriate `ReactiveOAuth2AuthorizedClientProvider` to authorize/re-authorize.
3. On a successful refresh, invoking the success handler to save the new authorized client.
4. On certain OAuth2 errors like `invalid_grant`, invoking the failure handler to remove the invalid record.
5. Returning `Mono<OAuth2AuthorizedClient>` without blocking the event loop.

| Manager | Used For | Storage |
| --- | --- | --- |
| DefaultReactiveOAuth2AuthorizedClientManager | WebFlux HTTP with `ServerWebExchange` | ServerOAuth2AuthorizedClientRepository |
| AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager | Services, scheduled/background tasks without HTTP requests | ReactiveOAuth2AuthorizedClientService |

Do not confuse these with Servlet classes `DefaultOAuth2AuthorizedClientManager`/`HttpServletRequest`/`HttpSession`.

### 4.4. ReactiveOAuth2AuthorizedClientProvider

~~~java
ReactiveOAuth2AuthorizedClientProvider providers =
        ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();
~~~

The refresh token provider only applies when an authorized client, a refresh token, and an access token needing renewal are all present. Otherwise, the provider returns `Mono.empty` without calling the Token Endpoint. `clientCredentials` can be added separately when the app needs machine-to-machine calls.

### 4.5. ServerOAuth2AuthorizedClientExchangeFilterFunction

The WebClient OAuth2 filter can resolve the authorized client, refresh prior to the request, and attach **`Authorization: Bearer`** on outbound requests. Never enable default `OAuth2AuthorizedClient` across all outbound hosts if `WebClient` can call arbitrary URLs, as that can send Bearer tokens to untrusted hosts.

**Two different 401/error cases:** the Token Endpoint returns `invalid_grant` when refresh fails; the Resource Server can return `401 invalid_token` when an access token is revoked even though local `expiresAt` has not passed. Pre-request refresh and post-request 401 handling are two distinct flows.

## 5. Persistence and Rotation Concurrency

`ReactiveOAuth2AuthorizedClientService` provides these methods:

~~~java
Mono<Void> saveAuthorizedClient(
        OAuth2AuthorizedClient client, Authentication principal);

Mono<OAuth2AuthorizedClient> loadAuthorizedClient(
        String registrationId, String principalName);

Mono<Void> removeAuthorizedClient(
        String registrationId, String principalName);
~~~

These illustrate the signatures, not a standalone Java class. `Mono` publishers must be composed and subscribed within the proper lifecycle; calling `save` and discarding the `Mono` may persist nothing. The manager typically coordinates saving automatically.

### 5.1. Refresh Token Rotation Race

~~~text
T0: Store holds access A1 + refresh R1 for alice
T1: Request A reads R1
T2: Request B also reads R1
T3: A refreshes successfully, AS returns A2/R2
T4: A saves A2/R2
T5: B uses R1 and is rejected with invalid_grant (R1 already rotated)
T6: B deletes record by key without checking version
    => A's A2/R2 risks being wiped out
~~~

With some IdPs, reusing R1 can even trigger token family revocation. Spring Security does not automatically create distributed locks across all stores and topologies.

**Mitigations:**

- Single-flight refresh keyed by `registrationId`/`principal` within a process.
- Across multiple nodes, optimistic locking/CAS/versioning or distributed coordination.
- Persisting new access/refresh tokens atomically and consistently.
- Ensuring `invalid_grant` cleanup does not delete a newer token version saved by another request.
- Bounded retries/backoff while respecting token reuse policies; never retry R1 endlessly after a timeout.
- Securing storage, logs, and backups that contain secrets.

### 5.2. Safe Token Storage

- Keep refresh tokens server-side when the app has a backend/BFF; never emit them in frontend JSON.
- Restrict DB/Redis permissions, encrypt at rest, and manage TTLs, backups, and secret rotation.
- Never log `access_token`, `refresh_token`, `Authorization` headers, cookies, authorization codes, code verifiers, or `client_secret`.
- Never share the same token across different principals or tenants.
- Delete/revoke authorized clients properly upon logout per IdP policy.
- Avoid sending Bearer tokens to user-supplied URLs; enforce an outbound allowlist to mitigate SSRF/exfiltration.

## 6. Java 17+ / Spring Boot WebFlux Project

This example uses Spring Boot 3.5.16, Java 17+, compatible Gradle 8.x, and Spring Security OAuth2 Client Reactive.

**Two separate verification levels:** the application includes OAuth2 login and WebClient configuration, yet needs a real IdP/Resource Server for end-to-end login; `example.org` hosts are documentation names only. The test suite in section 7 exercises Spring Security's real refresh/manager classes against a fake Token Endpoint **with no network calls**, so `gradle test` runs without an IdP.

### 6.1. Project Structure

~~~text
webflux-refresh/
├── settings.gradle
├── build.gradle
├── src/main/resources/application.yml
├── src/main/java/example/refresh/TokensApplication.java
├── src/main/java/example/refresh/SecurityConfig.java
├── src/main/java/example/refresh/DownstreamClient.java
├── src/main/java/example/refresh/ApiController.java
└── src/test/java/example/refresh/RefreshFlowTest.java
~~~

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-refresh'
~~~

### 6.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Never use Servlet OAuth2 client APIs in WebFlux. The Spring Boot BOM keeps dependencies aligned; team projects should pin a Gradle Wrapper.

### 6.4. application.yml

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          training:
            provider: training-idp
            client-id: lesson-webflux-client
            client-secret: local-demo-not-production-secret
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - offline_access
        provider:
          training-idp:
            authorization-uri: https://login.example.org/oauth2/authorize
            token-uri: https://login.example.org/oauth2/token
            jwk-set-uri: https://login.example.org/oauth2/jwks
            user-info-uri: https://login.example.org/oauth2/userinfo
            user-name-attribute: sub

app:
  downstream:
    profile-url: https://resource.example.org/api/profile
~~~

**Note:** `example.org` is an illustrative host; end-to-end login cannot run against it. With a real IdP, configure the actual `ClientRegistration`, client auth, redirect URI, scopes, and URLs; secrets must come from a vault/environment, never using demo values in production. The `offline_access` scope does not guarantee the IdP issues a refresh token—that still depends on consent and policy.

### 6.5. TokensApplication.java

~~~java
package example.refresh;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TokensApplication {
    public static void main(String[] args) {
        SpringApplication.run(TokensApplication.class, args);
    }
}
~~~

### 6.6. SecurityConfig.java

~~~java
package example.refresh;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.client.DefaultReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers("/public/ping").permitAll()
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                .oauth2Login(Customizer.withDefaults())
                .oauth2Client(Customizer.withDefaults())
                .build();
    }

    @Bean
    ReactiveOAuth2AuthorizedClientManager authorizedClientManager(
            ReactiveClientRegistrationRepository registrations,
            ServerOAuth2AuthorizedClientRepository repository) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .authorizationCode()
                        .refreshToken()
                        .build();

        DefaultReactiveOAuth2AuthorizedClientManager manager =
                new DefaultReactiveOAuth2AuthorizedClientManager(
                        registrations, repository);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

OAuth2 login handles interactive users; `ReactiveOAuth2AuthorizedClientManager` looks up the authorized client by principal and repository, invoking the refresh provider when the access token approaches expiry. The default success handler saves the refreshed authorized client. Never disable CSRF globally merely because APIs are used; this example only exposes GET routes.

### 6.7. DownstreamClient.java

~~~java
package example.refresh;

import java.util.Objects;

import org.springframework.core.env.Environment;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Component
public class DownstreamClient {

    private final WebClient webClient;
    private final String profileUrl;

    public DownstreamClient(
            ReactiveOAuth2AuthorizedClientManager manager,
            Environment env) {

        ServerOAuth2AuthorizedClientExchangeFilterFunction oauth =
                new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                        manager);
        this.webClient = WebClient.builder()
                .filter(oauth)
                .build();
        this.profileUrl = Objects.requireNonNull(
                env.getProperty("app.downstream.profile-url"),
                "app.downstream.profile-url is required");
    }

    public Mono<String> profile(ServerWebExchange exchange) {
        return webClient.get()
                .uri(profileUrl)
                .attributes(
                        ServerOAuth2AuthorizedClientExchangeFilterFunction
                                .clientRegistrationId("training"))
                .attributes(
                        ServerOAuth2AuthorizedClientExchangeFilterFunction
                                .serverWebExchange(exchange))
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

`WebClient` receives an explicit `clientRegistrationId` and the request's `ServerWebExchange`. It retrieves/refreshes the token and sends Bearer to the **trusted downstream host**. Never let clients pass arbitrary URLs, and never return token values to the frontend. The filter constructor taking a manager does not automatically install a failure handler for Resource Server 401/403 responses; that handling is separate from expiry refresh—see section 8.

### 6.8. ApiController.java

~~~java
package example.refresh;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    private final DownstreamClient downstream;

    public ApiController(DownstreamClient downstream) {
        this.downstream = downstream;
    }

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/profile")
    public Mono<String> profile(ServerWebExchange exchange) {
        return downstream.profile(exchange);
    }
}
~~~

### 6.9. Running Locally

~~~bash
gradle bootRun
curl -i http://localhost:8080/public/ping
~~~

Expected body:

~~~json
{"status":"ok"}
~~~

Public ping requires no IdP. Real OAuth2 login at `/oauth2/authorization/training` and `/api/profile` only work after replacing the demo endpoints with a real IdP/Resource Server and configuring valid callbacks and client secrets.

## 7. Testing the Provider and Manager Without a Real IdP

Build a fake Token Endpoint by replacing **`ReactiveOAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>`** on `RefreshTokenReactiveOAuth2AuthorizedClientProvider`. This does not mock the provider itself: tests run Spring Security's real provider, `OAuth2AuthorizedClient`, and manager. `StepVerifier` subscribes and verifies the publisher.

File **src/test/java/example/refresh/RefreshFlowTest.java**:

~~~java
package example.refresh;

import static org.junit.jupiter.api.Assertions.*;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.RefreshTokenReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2AuthorizationException;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;
import org.springframework.security.oauth2.core.endpoint.OAuth2AccessTokenResponse;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class RefreshFlowTest {

    private static ClientRegistration registration() {
        return ClientRegistration.withRegistrationId("training")
                .clientId("test-client")
                .clientSecret("test-secret")
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationUri(
                        "https://idp.example.org/oauth2/authorize")
                .tokenUri("https://idp.example.org/oauth2/token")
                .redirectUri(
                        "{baseUrl}/login/oauth2/code/{registrationId}")
                .scope("profile", "offline_access")
                .build();
    }

    private static Authentication principal() {
        return UsernamePasswordAuthenticationToken.authenticated(
                "alice", "unused-mock-password",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    private static OAuth2AuthorizedClient expiredClient() {
        Instant now = Instant.now();
        OAuth2AccessToken old = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "access-old",
                now.minusSeconds(600),
                now.minusSeconds(120),
                Set.of("profile"));
        return new OAuth2AuthorizedClient(
                registration(), "alice", old,
                new OAuth2RefreshToken(
                        "refresh-old", now.minusSeconds(600)));
    }

    private static OAuth2AccessTokenResponse rotated() {
        return OAuth2AccessTokenResponse
                .withToken("access-new")
                .tokenType(OAuth2AccessToken.TokenType.BEARER)
                .expiresIn(900)
                .refreshToken("refresh-new")
                .scopes(Set.of("profile"))
                .build();
    }

    @Test
    void expiredTokenRefreshesAndRotates() {
        AtomicInteger calls = new AtomicInteger();
        var provider =
                new RefreshTokenReactiveOAuth2AuthorizedClientProvider();

        provider.setAccessTokenResponseClient(request -> {
            calls.incrementAndGet();
            assertEquals("refresh-old",
                    request.getRefreshToken().getTokenValue());
            return Mono.just(rotated());
        });

        StepVerifier.create(provider.authorize(
                OAuth2AuthorizationContext
                        .withAuthorizedClient(expiredClient())
                        .principal(principal()).build()))
                .assertNext(updated -> {
                    assertEquals("access-new",
                            updated.getAccessToken().getTokenValue());
                    assertNotNull(updated.getRefreshToken());
                    assertEquals("refresh-new",
                            updated.getRefreshToken().getTokenValue());
                })
                .verifyComplete();

        assertEquals(1, calls.get());
    }

    @Test
    void validAccessTokenDoesNotRefresh() {
        Instant now = Instant.now();
        OAuth2AccessToken access = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "access-still-valid",
                now.minusSeconds(10),
                now.plusSeconds(1200));
        OAuth2AuthorizedClient current = new OAuth2AuthorizedClient(
                registration(), "alice", access,
                new OAuth2RefreshToken(
                        "refresh-old", now.minusSeconds(10)));

        AtomicInteger calls = new AtomicInteger();
        var provider =
                new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        provider.setAccessTokenResponseClient(request -> {
            calls.incrementAndGet();
            return Mono.just(rotated());
        });

        StepVerifier.create(provider.authorize(
                OAuth2AuthorizationContext
                        .withAuthorizedClient(current)
                        .principal(principal()).build()))
                .verifyComplete();

        assertEquals(0, calls.get());
    }

    @Test
    void clockSkewRefreshesBeforeActualExpiry() {
        Instant fixed = Instant.parse("2026-11-07T00:00:00Z");
        OAuth2AccessToken access = new OAuth2AccessToken(
                OAuth2AccessToken.TokenType.BEARER,
                "access-near",
                fixed.minusSeconds(600),
                fixed.plusSeconds(30));
        OAuth2AuthorizedClient current = new OAuth2AuthorizedClient(
                registration(), "alice", access,
                new OAuth2RefreshToken(
                        "refresh-old", fixed.minusSeconds(600)));

        AtomicInteger calls = new AtomicInteger();
        var provider =
                new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        provider.setClock(Clock.fixed(fixed, ZoneOffset.UTC));
        provider.setClockSkew(Duration.ofSeconds(60));
        provider.setAccessTokenResponseClient(request -> {
            calls.incrementAndGet();
            return Mono.just(rotated());
        });

        StepVerifier.create(provider.authorize(
                OAuth2AuthorizationContext
                        .withAuthorizedClient(current)
                        .principal(principal()).build()))
                .assertNext(updated -> assertEquals("access-new",
                        updated.getAccessToken().getTokenValue()))
                .verifyComplete();
        assertEquals(1, calls.get());
    }

    @Test
    void missingRefreshTokenCannotRunRefreshGrant() {
        OAuth2AuthorizedClient old = expiredClient();
        OAuth2AuthorizedClient noRefresh = new OAuth2AuthorizedClient(
                old.getClientRegistration(),
                old.getPrincipalName(),
                old.getAccessToken());

        AtomicInteger calls = new AtomicInteger();
        var provider =
                new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        provider.setAccessTokenResponseClient(request -> {
            calls.incrementAndGet();
            return Mono.just(rotated());
        });

        StepVerifier.create(provider.authorize(
                OAuth2AuthorizationContext
                        .withAuthorizedClient(noRefresh)
                        .principal(principal()).build()))
                .verifyComplete();
        assertEquals(0, calls.get());
    }

    @Test
    void managerPersistsNewAccessAndRotatedRefreshToken() {
        var registrations =
                new InMemoryReactiveClientRegistrationRepository(
                        registration());
        var store =
                new InMemoryReactiveOAuth2AuthorizedClientService(
                        registrations);

        AtomicInteger calls = new AtomicInteger();
        var provider =
                new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        provider.setAccessTokenResponseClient(request -> {
            calls.incrementAndGet();
            return Mono.just(rotated());
        });

        var manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, store);
        manager.setAuthorizedClientProvider(provider);

        Authentication alice = principal();
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
                .withClientRegistrationId("training")
                .principal(alice).build();

        Mono<OAuth2AuthorizedClient> flow =
                store.saveAuthorizedClient(expiredClient(), alice)
                        .then(manager.authorize(request))
                        .flatMap(updated -> store.loadAuthorizedClient(
                                "training", "alice")
                                .map(saved -> {
                                    assertEquals("access-new",
                                            saved.getAccessToken()
                                                    .getTokenValue());
                                    assertNotNull(saved.getRefreshToken());
                                    assertEquals("refresh-new",
                                            saved.getRefreshToken()
                                                    .getTokenValue());
                                    return updated;
                                }));

        StepVerifier.create(flow)
                .assertNext(updated -> assertEquals("access-new",
                        updated.getAccessToken().getTokenValue()))
                .verifyComplete();

        assertEquals(1, calls.get());
    }

    @Test
    void invalidGrantRemovesSavedAuthorizedClient() {
        var registrations =
                new InMemoryReactiveClientRegistrationRepository(
                        registration());
        var store =
                new InMemoryReactiveOAuth2AuthorizedClientService(
                        registrations);

        var provider =
                new RefreshTokenReactiveOAuth2AuthorizedClientProvider();
        provider.setAccessTokenResponseClient(request ->
                Mono.error(new OAuth2AuthorizationException(
                        new OAuth2Error("invalid_grant"))));

        var manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, store);
        manager.setAuthorizedClientProvider(provider);

        Authentication alice = principal();
        OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
                .withClientRegistrationId("training")
                .principal(alice).build();

        Mono<String> flow =
                store.saveAuthorizedClient(expiredClient(), alice)
                        .then(manager.authorize(request)
                                .onErrorResume(
                                        OAuth2AuthorizationException.class,
                                        error -> Mono.empty()))
                        .then(store.loadAuthorizedClient(
                                "training", "alice")
                                .map(ignored -> "STILL_SAVED")
                                .defaultIfEmpty("REMOVED"));

        StepVerifier.create(flow)
                .expectNext("REMOVED")
                .verifyComplete();
    }
}
~~~

### 7.1. Running and Evaluating Tests

~~~bash
gradle test
~~~

**Expected:** 6 passing tests and `BUILD SUCCESSFUL` when dependencies/JDK are compatible. This is an expectation from the code, not a claim that a live build was executed.

The test suite proves:

- Expired token + valid refresh -> fake Token Endpoint is called once and returns a new access token and rotated refresh token.
- Token far from expiry -> provider returns `Mono.empty`, avoiding unnecessary refreshes.
- `Clock.fixed` + 60-second skew -> token with 30 seconds left triggers refresh.
- Missing refresh token -> refresh grant does not run.
- Service-level manager persists the new tokens under the right `registrationId`/`principal` and reads them back.
- `invalid_grant` triggers the default failure handler to remove the stale authorized client in the test.

**Limitations:** tests do not hit HTTPS or a real IdP, nor do they verify redirects/`state`/PKCE, client secrets/issuers, real revocation, or Resource Servers. End-to-end tests in staging are still required.

### 7.2. Why Not Block?

Never do this in a WebFlux handler:

~~~java
// Do not use on the reactive event loop:
OAuth2AuthorizedClient client = manager.authorize(request).block();
~~~

Use the WebClient filter or compose `Mono` via `flatMap`/`then` so the framework manages subscriptions. In unit tests, use `StepVerifier`.

## 8. Resource Server 401/403, Refresh Errors, and How to Handle Them

### 8.1. Two WebClient Filter Constructors

If you construct:

~~~java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager)
~~~

Spring Security 6.5 Javadoc states clearly that the filter **does not automatically install a failure handler** for Resource Server 401/403 responses. When you want invalid cached authorized clients deleted upon a downstream Bearer `invalid_token`, configure `RemoveAuthorizedClientReactiveOAuth2AuthorizationFailureHandler` matching your repository/service and test it.

If you construct:

~~~java
new ServerOAuth2AuthorizedClientExchangeFilterFunction(
        clientRegistrations, authorizedClientRepository)
~~~

this constructor includes a default failure handler for certain OAuth2 error codes, though it uses its own management strategy and will not automatically apply other custom manager settings unless integrated. Never assume a request receiving 401 is automatically replayed.

### 8.2. Classifying Failures

| Scenario | What to Do |
| --- | --- |
| Access token valid | Use the current token |
| Token near expiry and refresh token exists | Refresh with AS, persist the new pair |
| No refresh token | Reauthorize/re-login user or use an alternate grant |
| `invalid_grant` due to revoked refresh token | Delete invalid token per policy, require re-authorization |
| `invalid_client` | Inspect client secret/certificate/config, alert operations |
| Token Endpoint timeout or 5xx | Fail closed, bounded retry/backoff; do not treat as bad user password |
| 429 from AS | Respect `Retry-After`, add jitter, limit thundering herd |
| Resource Server 401 `invalid_token` | Review token revocation/failure handler, controlled reauthorization |
| Resource Server 403 `insufficient_scope` | Needs permissions/consent; do not refresh hoping to become admin |
| Concurrent requests rotating same refresh token | Lock/CAS/versioning to avoid losing the new token |
| Logout, consent revoked | Clean up authorized clients and sessions properly |

Never retry the same old refresh token endlessly on `invalid_grant` or timeout, because token rotation may already have occurred on the AS side. Never automatically replay a state-changing POST after a 401 without an idempotency policy; the request may already have produced side effects.

### 8.3. Safe Observability

Measure `registrationId`, grant type, token seconds-to-expiry, result category, latency, error code, and `correlationId`. Never log raw `Authorization` headers, token endpoint form/JSON responses, code verifiers, client secrets, or refresh tokens. Metric labels should not contain raw principals or emails.

## 9. Production and Multi-Node Checklist

1. Load client secrets from a vault/secrets store; never commit real secrets.
2. Register exact redirect URIs, `state`, and PKCE per client type.
3. Use HTTPS/TLS with certificate verification across the browser, AS, and Resource Server.
4. Store refresh tokens server-side in an encrypted store with restricted access.
5. Use a shared store and sensible TTLs across multiple replicas; in-memory stores are for demos only.
6. Synchronize clocks and tune `clockSkew` to real TTLs and network latency.
7. Distinguish user HTTP requests from background jobs and pick the matching manager.
8. Never attach Bearer tokens to user-chosen hosts, preventing SSRF/exfiltration.
9. Isolate tokens by principal/tenant; never use a static global token.
10. With one-time rotation, use single-flight and CAS/versioning so an R1 failure cannot delete R2.
11. Logout/revocation must clean up corresponding authorized clients and coordinate with the IdP.
12. Handle `invalid_grant` differently from `invalid_client`/429/5xx; bound retries.
13. Test expired, near-expiry, no-refresh-token, rotation, persistence, and revoked-token cases.
14. Test downstream 401/403 separately from pre-expiry refresh.
15. Never disable CSRF on browser cookies just because an OAuth2 Client is used.
16. Test HTTPS, issuer, redirect, consent, token scopes, and the Resource Server against a real IdP.

### 9.1. End-to-End Verification Steps with a Staging IdP

1. Register the client and exact callback with the real provider; use a test account.
2. Visit `/oauth2/authorization/training` and complete login/consent.
3. Call `/api/profile` with the same browser session and verify the downstream identity.
4. Configure a short access token TTL to easily hit the refresh window.
5. Call the API again once inside the skew window and confirm the AS receives the `refresh_token` grant.
6. Confirm the new access/refresh pair is saved and, if rotated, subsequent calls use R2.
7. Revoke the token at the test IdP and verify there is no refresh or login loop.
8. Send concurrent requests across multiple nodes to check consistency.
9. Audit logs/token redaction and HTTPS/public proxy behavior.
10. Review for replay vulnerabilities, refresh token reuse detection, and unsafe request retries.

## 10. Exercises and Self-Assessment

1. Can an OAuth2 Client mint a new access token on its own?
2. Which endpoints are access tokens and refresh tokens each sent to?
3. Does `expires_in = 900` represent seconds or a timestamp?
4. A token expires at 10:05 with 60s skew; should a request at 10:04:20 refresh?
5. Without a refresh token, what should an `authorization_code` user do?
6. Which grant does `client_credentials` usually use to get a new token?
7. Why must a new refresh token be saved after rotation?
8. Why must a single static token never be shared across all users?
9. Should a downstream `403 insufficient_scope` trigger an infinite refresh loop?
10. Why are `Clock.fixed` tests better than `Thread.sleep`?
11. When request B receives `invalid_grant` because A rotated R1 to R2, what bug must be avoided?
12. Why is a Resource Server 401 different from a Token Endpoint `invalid_grant`?
13. If the Token Endpoint returns 503, how should handling differ from `invalid_grant`?
14. When a user logs out, what needs to happen to the authorized client?
15. Why do fake-response tests not replace testing against a real IdP?

**Answers:** (1) No, only the AS; (2) access goes to the Resource Server, refresh goes to the Token Endpoint; (3) seconds; (4) yes, because 40 seconds remain, which is less than the skew; (5) re-authorize/re-login; (6) `client_credentials`; (7) R1 may already be revoked; (8) to avoid mixing A/B tokens; (9) no, missing scopes require permissions/consent; (10) deterministic; (11) avoid deleting the newer R2 due to the old R1 error; (12) access rejected at a resource differs from an invalid refresh grant; (13) transient outage requires backoff/503, do not delete indiscriminately; (14) clean up/revoke per policy; (15) they do not test TLS, issuer, redirects, scopes, or real protocol behavior.

## 11. References

- Spring Security 6.5 — Reactive OAuth2 Client Core: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html
- Spring Security 6.5 — Reactive Authorized Clients: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html
- Spring Security 6.5 — OAuth2 Authorization Grants: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html
- Spring Security 6.5 Javadoc — RefreshTokenReactiveOAuth2AuthorizedClientProvider: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/RefreshTokenReactiveOAuth2AuthorizedClientProvider.html
- Spring Security 6.5 Javadoc — DefaultReactiveOAuth2AuthorizedClientManager: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/DefaultReactiveOAuth2AuthorizedClientManager.html
- Spring Security 6.5 Javadoc — ServerOAuth2AuthorizedClientExchangeFilterFunction: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/function/client/ServerOAuth2AuthorizedClientExchangeFilterFunction.html
- RFC 6749 §6 — Refresh Access Token: https://www.rfc-editor.org/rfc/rfc6749.html#section-6
- RFC 6750 — Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750.html
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700.html
- OWASP OAuth2 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html

**Conclusion:** `ReactiveOAuth2AuthorizedClientManager` coordinates with `RefreshTokenReactiveOAuth2AuthorizedClientProvider` to request a new access token from the Authorization Server when the token is near expiration and a valid refresh token exists. Persist rotated `OAuth2AuthorizedClient` records, attach Bearer tokens via the WebClient filter, never leak refresh tokens, handle `invalid_grant` cleanly, and protect concurrent refreshes in multi-node systems.