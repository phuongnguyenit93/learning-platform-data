# Injecting OAuth2AuthorizedClient with @RegisteredOAuth2AuthorizedClient

**Module:** Spring Security – reactive (WebFlux)  
**Section:** OAuth2 Client  
**Objective:** Understand how WebFlux resolves a `@RegisteredOAuth2AuthorizedClient` parameter into an `OAuth2AuthorizedClient`, how to select the right registration/principal/token, how to combine it with `WebClient` to call external APIs, how to test the annotation without running a real Authorization Server, and how to prevent credential leakage.

## 1. Core Takeaway

`@RegisteredOAuth2AuthorizedClient("demo-client")` can be placed on a **parameter of an annotated WebFlux controller** of type `OAuth2AuthorizedClient`. Spring Security automatically resolves the parameter using the OAuth2 Client infrastructure, `ClientRegistration`, principal/request context, repository, and the corresponding `ReactiveOAuth2AuthorizedClientManager`.

```java
@GetMapping("/inventory")
public Mono<String> inventory(
        @RegisteredOAuth2AuthorizedClient("inventory-client")
        OAuth2AuthorizedClient authorizedClient) {

    return webClient.get()
        .uri("https://trusted-inventory.example.invalid/items")
        .attributes(
            ServerOAuth2AuthorizedClientExchangeFilterFunction
                .oauth2AuthorizedClient(authorizedClient))
        .retrieve()
        .bodyToMono(String.class);
}
```

This is a **fragment**, not a standalone Java file: `webClient` must be configured with the OAuth2 filter, the `inventory-client` registration must exist, a token must be issued according to an appropriate grant, and the illustrative host is non-functional. This snippet shows two distinct actions:

1. **Injection:** the framework resolves `OAuth2AuthorizedClient` as a controller parameter.
2. **Outbound authorization:** the caller passes that client to `WebClient`, so the filter adds `Authorization: Bearer ...` to requests sent to a trusted API.

**Never** return `getAccessToken().getTokenValue()` or `getRefreshToken().getTokenValue()` in JSON, logs, tracing, or the browser just to see whether injection works. It is a Bearer credential; if exposed, it can be used within its granted scope and validity period.

## 2. Objects You Must Distinguish

| Concept | Function | Example |
| --- | --- | --- |
| `ClientRegistration` | Application configuration registered with the Authorization Server: registration ID, client ID, scopes, grant type, token URI, redirect URI if used | `inventory-client` |
| `ReactiveClientRegistrationRepository` | Looks up a registration by ID; Boot can auto-configure it from properties | `findByRegistrationId("inventory-client")` |
| `OAuth2AuthorizedClient` | Binds a registration, principal name, access token, and optional refresh token | Grant for Alice or a service account |
| `OAuth2AccessToken` | Token used by the Client to call a Resource Server, carrying scopes and issued/expires timestamps | Bearer access token |
| `OAuth2RefreshToken` | Token used to request a new access token at the Authorization Server when issued | Absent in many `client_credentials` grants |
| `OAuth2AuthenticationToken` | User authentication when logging into a website via OAuth2/OIDC | Principal in WebSession |
| `ReactiveOAuth2AuthorizedClientManager` | Authorizes, re-authorizes, refreshes/renews, and coordinates persistence | Used by argument resolver/WebClient |
| `ServerOAuth2AuthorizedClientRepository` | Stores/loads authorized clients in a web request/session context | WebFlux-aware repository |
| `ReactiveOAuth2AuthorizedClientService` | Service loading/saving authorized clients by registration/principal at application scope | In-memory, R2DBC/custom |
| `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Adds the Bearer token to outbound `WebClient` requests per authorized client | `.attributes(oauth2AuthorizedClient(client))` |

**ClientRegistration is not an Authorized Client.** A registration can exist before any user or service receives a token. An authorized client only meaningfully exists once authorization/grant has occurred or has been simulated in tests.

**Authentication is not an Authorized Client.** A website can have a logged-in browser session while still not having been granted an access token for a separate API. Conversely, a scheduled job can acquire a `client_credentials` token unrelated to any browser session.

**ID Token is not an Access Token.** In OIDC, the `id_token` lets the Relying Party verify the login event; a Resource Server API needs an access token with the right audience and scopes. Do not use `OidcUser.getIdToken()` in place of `OAuth2AuthorizedClient.getAccessToken()`.

### 2.1. Two Keys Identifying an Authorized Client

An authorized client is typically associated with a **registrationId** and a **principalName**:

```text
Registration: inventory-client
          |
          +-- principalName: alice
          |     access_token: token-user-A
          |
          +-- principalName: bob
          |     access_token: token-user-B
          |
          +-- principalName: service-principal
                access_token: token-service (when policy permits)
```

With the authorization code grant, an access token can represent a user's delegated access. With client credentials, the token typically represents the **application**. The principal name used in storage/authorization requests may differ from the business identity of an end user. Never share user tokens across requests via a `static currentToken` variable, and never select a token from an unverified username supplied by an HTTP client.

For multi-tenant/multi-provider setups, isolate by issuer, tenant, and registration, not just username. Tenant A's token must never be used to call Tenant B's API.

## 3. Where Exactly Does the Annotation Inject?

Imports:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
```

In a controller:

```java
@GetMapping("/client/details")
public Mono<String> details(
    @RegisteredOAuth2AuthorizedClient("demo-client")
    OAuth2AuthorizedClient client) {

    String id = client.getClientRegistration().getRegistrationId();
    String principal = client.getPrincipalName();
    return Mono.just(id + ":" + principal);
}
```

Spring Security WebFlux provides `OAuth2AuthorizedClientArgumentResolver` in package `org.springframework.security.oauth2.client.web.reactive.result.method.annotation`, a `HandlerMethodArgumentResolver` for reactive annotated endpoints. It interacts with `ServerWebExchange`, the OAuth2 authorized client manager/repository, and the request's `Authentication`. The resolver runs reactively under the hood, while the parameter received by the controller is **`OAuth2AuthorizedClient`**, with no need to wrap it in `Mono<OAuth2AuthorizedClient>` in the signature.

**The annotation value is the internal registration ID**, not the OAuth `client-id` issued by the IdP:

```java
@RegisteredOAuth2AuthorizedClient("demo-client")
OAuth2AuthorizedClient a

@RegisteredOAuth2AuthorizedClient(registrationId = "demo-client")
OAuth2AuthorizedClient b
```

Both forms are equivalent thanks to the `value` and `registrationId` alias attributes. If properties define `registration.reporting` while the annotation asks for `demo-client`, the resolver will not guess the other registration. Never accept an arbitrary registration ID from a public query/header and authorize against any provider without an allowlist.

### 3.1. The Annotation Is Not @Autowired

`@RegisteredOAuth2AuthorizedClient` only resolves a **method parameter** on a framework-handled handler. Do not place it on a singleton field expecting Spring to inject a token. Do not put it on an arbitrary `@Service` expecting AOP-style authorization. For services or background jobs, inject `ReactiveOAuth2AuthorizedClientManager`/`ReactiveOAuth2AuthorizedClientService` and call their APIs directly.

If a test instantiates the controller via `new ClientController()` and calls the Java method directly, no WebFlux argument resolver runs; testing the annotation requires going through `WebTestClient` with a Spring context and security configuration.

### 3.2. Pipeline When a Request Arrives

```text
Browser / client -> GET /client/details
       |
       v
SecurityWebFilterChain: authentication, .authenticated()
       |
       v
Handler mapping -> annotated controller method
       |
       v
OAuth2AuthorizedClientArgumentResolver:
  registrationId = "demo-client"
  principalName = authenticated context / chosen service principal
       |
       +--> existing authorized client? -> load
       |
       +--> missing/expired? -> manager + provider per grant
       |     authorization_code -> may require redirect/consent
       |     client_credentials -> may POST token endpoint
       |     refresh_token -> may refresh if present and supported
       |
       +--> failure / config missing -> no usable token
       |
       v
Controller receives OAuth2AuthorizedClient
       |
       +--> return safe metadata DTO; or
       |
       +--> send via WebClient with OAuth2 filter
               |
               v
             Resource Server checks Bearer, audience, scope, timestamps
```

There is no guarantee that the annotation **always calls** the AS for a new token on every request. When an unexpired token is already stored, the manager typically loads and reuses it. Without a matching registration, authorization, and provider, no valid token can be injected by magic.

## 4. Configuring OAuth2 Client in Spring WebFlux

Required dependency: `spring-boot-starter-oauth2-client` (in addition to WebFlux/Security). Basic configuration:

```java
@Configuration
@EnableWebFluxSecurity
class SecurityConfiguration {
    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers("/public").permitAll()
                .anyExchange().authenticated())
            .formLogin(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
```

This is a **fragment**; the complete project is in section 8. `oauth2Client()` enables OAuth2 Client support; it does not make the app a Resource Server accepting inbound Bearer tokens. `oauth2Login()` is only needed when logging users in via an OAuth2/OIDC provider; local form login combined with an outbound `client_credentials` token is another valid use case.

In Spring Boot, registrations can be configured via properties; `ReactiveClientRegistrationRepository` is built from them. Example:

```properties
spring.security.oauth2.client.registration.demo-client.provider=demo-provider
spring.security.oauth2.client.registration.demo-client.client-id=demo-client-id
spring.security.oauth2.client.registration.demo-client.client-secret=training-invalid
spring.security.oauth2.client.registration.demo-client.authorization-grant-type=client_credentials
spring.security.oauth2.client.registration.demo-client.scope=inventory.read
spring.security.oauth2.client.provider.demo-provider.token-uri=https://idp.example.invalid/oauth2/token
```

These are **illustrative placeholders and do not work with a real IdP**. Never put `training-invalid` into production; obtain legitimately issued credentials/URIs and use a secrets manager, HTTPS, and approved scopes.

### 4.1. Grant Types Change Token Meaning

| Grant | Who Issues the Token? | Who Does the Token Represent? | Notes |
| --- | --- | --- | --- |
| `authorization_code` | AS after browser authorization/login/consent | Permissions delegated by the user to the client | Code + state + PKCE/nonce per profile, exact callback URI |
| `client_credentials` | AS issued directly to a confidential client | **The application/client** | Does not inherently represent an end user; typically no refresh token |
| `refresh_token` | AS issues a new access token under the refresh grant | Follows the existing authorized grant | Only if refresh token is valid and provider supports it |
| Extension grants | Provider-dependent, e.g., token exchange per policy | Depends on grant and issuer | Not enabled automatically; requires explicit config |

In a controller using `@RegisteredOAuth2AuthorizedClient("demo-client")` for `client_credentials`, the token may be keyed to the request's principal in storage, yet the **token's authority remains application authority**, not the caller's admin privileges. Enforce business authorization at the route/service layer.

### 4.2. ReactiveOAuth2AuthorizedClientManager Has Two Contexts

- `DefaultReactiveOAuth2AuthorizedClientManager` fits **web request contexts**; it coordinates with the repository to store clients and refresh/renew via providers.
- `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` fits **outside a WebExchange**, such as cron/queue/batch jobs, using the service store and an explicit service principal.

Do not use the annotated controller argument resolver from a background job, as there is no handler method or `ServerWebExchange` to resolve parameters.

## 5. Using the Authorized Client for Outbound WebClient Calls

Configure `ServerOAuth2AuthorizedClientExchangeFilterFunction`:

```java
@Bean
WebClient protectedWebClient(
        ReactiveOAuth2AuthorizedClientManager manager) {

    var oauth =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder()
        .filter(oauth)
        .build();
}
```

Fragment requiring imports: `WebClient`, `ReactiveOAuth2AuthorizedClientManager`, `ServerOAuth2AuthorizedClientExchangeFilterFunction`, `@Bean`. If you use a bare `WebClient.create()` without the OAuth2 filter, setting a request attribute alone will not add the header.

### 5.1. Selecting the Client Explicitly on the Request

```java
return webClient.get()
    .uri("https://trusted-api.example.invalid/v1/items")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class);
```

`oauth2AuthorizedClient(...)` is a static helper that writes an attribute onto the request for the OAuth2 filter to consume. Never turn the token into a string in the controller to insert it manually if you can keep the credential inside a controlled filter.

### 5.2. Selecting by Registration ID When No Object Is Present Yet

```java
return webClient.get()
    .uri("https://trusted-api.example.invalid/v1/items")
    .attributes(
        ServerOAuth2AuthorizedClientExchangeFilterFunction
            .clientRegistrationId("inventory-client"))
    .retrieve()
    .bodyToMono(String.class);
```

Here, the filter/manager resolves the authorized client from the registration, principal/context, and grant. This does not completely replace the annotation case: when a controller already holds the exact client, passing the object explicitly is easier to audit.

### 5.3. Risks of Default Authorized Client

`ServerOAuth2AuthorizedClientExchangeFilterFunction.setDefaultOAuth2AuthorizedClient(true)` can select the default authorized client of an OAuth2-logged-in user for outbound requests. Spring Security documentation warns that every request sent through a shared WebClient could receive the token. Likewise, `setDefaultClientRegistrationId("...")` can attach tokens unintentionally.

**Recommendation:** Use a dedicated `WebClient` per trusted upstream; select the authorized client per request, allowlist destinations, guard against redirects/SSRF, and never log the `Authorization` header. A token issued for API A is not implicitly accepted by API B; the Resource Server must verify `aud`, issuer, `exp`, and scopes/permissions.

## 6. Managing Token Lifecycle and Repositories

`OAuth2AuthorizedClient` typically provides:

```java
OAuth2AccessToken access = client.getAccessToken();
String registrationId =
    client.getClientRegistration().getRegistrationId();
String principalName = client.getPrincipalName();

boolean hasRefreshToken = client.getRefreshToken() != null;
```

This is a fragment. Never read `getRefreshToken().getTokenValue()` when the refresh token is null. `OAuth2AccessToken` has `getIssuedAt()`, `getExpiresAt()`, and `getScopes()`; safe metadata can be used to monitor expiration **without putting `tokenValue` into logs**.

- `ServerOAuth2AuthorizedClientRepository` is used inside web requests and can retain state across requests.
- `ReactiveOAuth2AuthorizedClientService` is the application-level storage abstraction; Spring provides in-memory and R2DBC/custom persistence options.
- `ReactiveOAuth2AuthorizedClientManager` coordinates `ReactiveOAuth2AuthorizedClientProvider` and can refresh/renew when the grant and provider match.
- Token expiration or revocation at the AS does not automatically log out a WebFlux browser session. Local logout also does not guarantee all issued access tokens have been revoked.
- If a refresh attempt returns `invalid_grant`, the application must remove the stale authorized client per policy and notify or re-authorize appropriately, avoiding infinite retries.
- In multi-instance deployments, shared storage, a token renewal concurrency plan, token security at rest, TTLs, rotation, auditing, and incident response are required.

**Distinguish reading the repository from authorizing via the manager:** `loadAuthorizedClient(registrationId, principalName)` only reads a saved client; manager authorization evaluates expiry and can invoke the provider for a new token. Merely loading and sending a stale token can cause the API to return 401.

## 7. Standalone Java 17 CLI: One Registration, Multiple Principals

To see why an "authorized client" is not simply a "client configuration", run the pure Java example below. It does **not** create real OAuth2 tokens and performs no authentication.

Save `ClientAssociationDemo.java`:

```java
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class ClientAssociationDemo {
    record BoundClient(String registration, String principal,
                       Set<String> scopes) {}

    public static void main(String[] args) {
        var items = List.of(
            new BoundClient("inventory", "alice",
                Set.of("inventory.read")),
            new BoundClient("inventory", "bob",
                Set.of("inventory.write", "inventory.read")),
            new BoundClient("reports", "alice",
                Set.of("report.read"))
        );

        for (BoundClient item : items) {
            String scopes = String.join(",",
                new TreeSet<>(item.scopes()));
            System.out.println(item.registration() + "|"
                + item.principal() + "|" + scopes);
        }
    }
}
```

Run:

```bash
javac ClientAssociationDemo.java
java ClientAssociationDemo
```

**Exact stdout:**

```text
inventory|alice|inventory.read
inventory|bob|inventory.read,inventory.write
reports|alice|report.read
```

Takeaway: registration, principal, and scopes all matter. In a real application, `OAuth2AuthorizedClient` also holds secret access/refresh tokens, and persistence/lookups must isolate users and tenants cleanly.

## 8. Sample Java 17+ Spring Boot WebFlux App Verifying Injection

We build an app with browser **form login** to authenticate users with `WebSession` and an OAuth2 Client registration `demo-client` using `client_credentials` to demonstrate the annotation. Real token data requires an AS, yet **integration tests use `mockOAuth2Client` so no running IdP is needed**.

Note the two modes:

- **`mvn test`**: uses `spring-security-test` to place a fake authorized client and `SecurityContext` into the WebFlux test. Requests pass through the real handler/controller and annotation resolver, without calling an AS or token endpoint.
- **Running with a real AS**: replace the client credentials and token URI in properties with valid values. After form login, the manager can request a real access token for the registration. With the placeholder `idp.example.invalid`, endpoints requiring a token **cannot succeed outside tests**; this is an intentional boundary, not a fake OAuth server.

### 8.1. File Structure

```text
webflux-registered-client/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/registered/
    │   │   ├── RegisteredClientApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── ClientController.java
    │   └── resources/application.properties
    └── test/java/demo/registered/
        └── RegisteredClientTests.java
```

Java 17+, Maven 3.9+, and Spring Boot **3.5.7** serve as the example baseline. For production, use a patched and supported version. Do not add `spring-boot-starter-web`, because **Reactive WebFlux** is required rather than Servlet MVC.

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.7</version>
    <relativePath/>
  </parent>
  <groupId>demo</groupId>
  <artifactId>webflux-registered-client</artifactId>
  <version>1.0.0</version>
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
```

`src/main/resources/application.properties`:

```properties
spring.application.name=webflux-registered-client
server.port=8080

# Replace with the real provider's ID, secret, and token endpoint instead of the demo values.
spring.security.oauth2.client.registration.demo-client.provider=demo-provider
spring.security.oauth2.client.registration.demo-client.client-id=training-id
spring.security.oauth2.client.registration.demo-client.client-secret=training-invalid
spring.security.oauth2.client.registration.demo-client.authorization-grant-type=client_credentials
spring.security.oauth2.client.registration.demo-client.scope=inventory.read
spring.security.oauth2.client.provider.demo-provider.token-uri=https://idp.example.invalid/token
```

The values `training-id`/`training-invalid` and `idp.example.invalid` **are not valid against any Authorization Server**; tests supply a fake authorized client instead of calling this endpoint. Production must use a secrets manager and an endpoint from a trusted IdP.

`src/main/java/demo/registered/RegisteredClientApplication.java`:

```java
package demo.registered;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegisteredClientApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegisteredClientApplication.class, args);
    }
}
```

### 8.2. SecurityConfig.java

`src/main/java/demo/registered/SecurityConfig.java`:

```java
package demo.registered;

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

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails viewer = User.withUsername("viewer")
            .password(encoder.encode("viewer123"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(viewer);
    }

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(ex -> ex
                .pathMatchers(HttpMethod.GET, "/public").permitAll()
                .pathMatchers("/login").permitAll()
                .pathMatchers("/client/**").authenticated()
                .anyExchange().denyAll())
            .formLogin(Customizer.withDefaults())
            .httpBasic(basic -> basic.disable())
            .oauth2Client(Customizer.withDefaults())
            // Default CSRF remains enabled for browser POST requests.
            .build();
    }
}
```

`formLogin` enables browser login with the demo user, and `oauth2Client` provides OAuth2 Client integration. The two are independent: a browser session **does not automatically prove** an AS token has been issued; the authorized client manager must look up/authorize according to the registration. `anyExchange().denyAll()` blocks undeclared routes. Never disable CSRF simply because OAuth2 tokens are used downstream.

### 8.3. ClientController.java: Injected Parameter

`src/main/java/demo/registered/ClientController.java`:

```java
package demo.registered;

import java.util.List;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ClientController {

    public record ClientView(
        String registrationId, String principalName,
        List<String> scopes, boolean refreshTokenPresent
    ) {}

    @GetMapping(value = "/public",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> home() {
        return Mono.just("public");
    }

    @GetMapping(value = "/client/metadata",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ClientView> metadata(
            @RegisteredOAuth2AuthorizedClient("demo-client")
            OAuth2AuthorizedClient client) {
        return Mono.just(safeView(client));
    }

    @GetMapping(value = "/client/alias",
                produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<ClientView> alias(
            @RegisteredOAuth2AuthorizedClient(
                registrationId = "demo-client")
            OAuth2AuthorizedClient client) {
        return Mono.just(safeView(client));
    }

    @PostMapping(value = "/client/check",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> check(
            @RegisteredOAuth2AuthorizedClient("demo-client")
            OAuth2AuthorizedClient client) {
        return Mono.just("accepted:" +
            client.getClientRegistration().getRegistrationId());
    }

    private static ClientView safeView(OAuth2AuthorizedClient client) {
        List<String> scopes = client.getAccessToken().getScopes()
            .stream().sorted().toList();

        return new ClientView(
            client.getClientRegistration().getRegistrationId(),
            client.getPrincipalName(), scopes,
            client.getRefreshToken() != null);
    }
}
```

This code returns only **selectively chosen metadata**. Never `return Mono.just(client)` and let Spring serialize the entire authorized client, as that could expose access/refresh tokens. Even `scopes`/`principalName` must undergo privacy and authorization evaluation before being exposed to browsers outside a demo context.

### 8.4. Testing with WebTestClient and mockOAuth2Client

`spring-security-test` provides `SecurityMockServerConfigurers.mockOAuth2Client("demo-client")`, which supplies a fake `OAuth2AuthorizedClient` in the test `ServerWebExchange`. `mockUser("alice")` sets the `Authentication` independently. Thus, tests prove the **argument resolver and controller** work, without testing real IdP token exchange, signing, or refresh.

`src/test/java/demo/registered/RegisteredClientTests.java`:

```java
package demo.registered;

import java.time.Instant;
import java.util.Set;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import reactor.core.publisher.Mono;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Client;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class RegisteredClientTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    private static OAuth2AccessToken token(Set<String> scopes) {
        Instant now = Instant.now();
        return new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "test-token-never-use-in-production",
            now.minusSeconds(60),
            now.plusSeconds(600), scopes);
    }

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicRouteWorks() {
        client.get().uri("/public")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void anonymousCannotReadClientMetadata() {
        client.get().uri("/client/metadata")
            .exchange().expectStatus().is3xxRedirection()
            .expectHeader().value(HttpHeaders.LOCATION,
                loc -> assertTrue(loc.contains("/login")));
    }

    @Test
    void injectionResolvesRegistrationAndPrincipal() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .get().uri("/client/metadata")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.registrationId").isEqualTo("demo-client")
            .jsonPath("$.principalName").isEqualTo("alice");
    }

    @Test
    void aliasRegistrationIdIsEquivalent() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .get().uri("/client/alias")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.registrationId").isEqualTo("demo-client");
    }

    @Test
    void scopesAreSortedInSafeDto() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of(
                    "inventory.write", "inventory.read"))))
            .get().uri("/client/metadata")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.scopes[0]").isEqualTo("inventory.read")
            .jsonPath("$.scopes[1]").isEqualTo("inventory.write");
    }

    @Test
    void refreshTokenIsOptional() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .get().uri("/client/metadata")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.refreshTokenPresent").isEqualTo(false);
    }

    @Test
    void differentPrincipalDoesNotBecomeAlice() {
        client.mutateWith(mockUser("bob"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("bob")
                .accessToken(token(Set.of("inventory.read"))))
            .get().uri("/client/metadata")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.principalName").isEqualTo("bob");
    }

    @Test
    void queryCannotOverrideExplicitRegistrationId() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .get().uri("/client/metadata?registrationId=other")
            .exchange().expectStatus().isOk()
            .expectBody()
            .jsonPath("$.registrationId").isEqualTo("demo-client");
    }

    @Test
    void jsonResponseDoesNotExposeRawToken() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .get().uri("/client/metadata")
            .exchange().expectStatus().isOk()
            .expectBody(String.class)
            .value(body -> assertFalse(body.contains(
                "test-token-never-use-in-production")));
    }

    @Test
    void browserPostWithoutCsrfIsForbidden() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .post().uri("/client/check")
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void browserPostWithCsrfSucceeds() {
        client.mutateWith(mockUser("alice"))
            .mutateWith(mockOAuth2Client("demo-client")
                .principalName("alice")
                .accessToken(token(Set.of("inventory.read"))))
            .mutateWith(csrf())
            .post().uri("/client/check")
            .exchange().expectStatus().isOk()
            .expectBody(String.class).isEqualTo(
                "accepted:demo-client");
    }

    @Test
    void explicitClientAttributeAttachesBearerOnlyOnOutbound() {
        ClientRegistration reg =
            ClientRegistration.withRegistrationId("demo-client")
                .clientId("demo-id")
                .clientSecret("dummy")
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri("https://idp.example.invalid/token")
                .build();

        OAuth2AuthorizedClient authorized =
            new OAuth2AuthorizedClient(
                reg, token(Set.of("inventory.read")), "alice");

        ReactiveOAuth2AuthorizedClientManager manager =
            request -> Mono.just(authorized);

        ExchangeFunction fake = request -> {
            String authorization = request.headers()
                .getFirst(HttpHeaders.AUTHORIZATION);
            return Mono.just(ClientResponse.create(HttpStatus.OK)
                .body(authorization == null
                    ? "NO_AUTH" : authorization)
                .build());
        };

        var filter =
            new ServerOAuth2AuthorizedClientExchangeFilterFunction(
                manager);
        WebClient web = WebClient.builder()
            .exchangeFunction(fake)
            .filter(filter)
            .build();

        String result = web.get()
            .uri("https://trusted-api.example.invalid/data")
            .attributes(
                ServerOAuth2AuthorizedClientExchangeFilterFunction
                    .oauth2AuthorizedClient(authorized))
            .retrieve()
            .bodyToMono(String.class)
            .block();

        assertEquals("Bearer test-token-never-use-in-production",
            result);
    }
}
```

Run:

```bash
mvn test
```

The goal is **12 passing tests** when files, packages, JDK, and dependencies match. This is a self-run curriculum; **it does not claim tests have already been executed on your machine**. Tests using `mockOAuth2Client` do **not** call an AS, validate real access token signatures, or test PKCE/OIDC callbacks; the final WebClient test uses a fake `ExchangeFunction` without connecting to the illustrative host. Therefore, separate sandbox AS integration testing is needed before production.

### 8.5. Reading Test Results Properly

- Public 200 and anonymous redirect confirm that the web app's HTTP security is active.
- `mockUser` and `mockOAuth2Client` simulate **two independent objects**: `Authentication` and the authorized client. When invoked via `WebTestClient`, the WebFlux argument resolver injects the client into the handler parameter.
- The alias test proves `@RegisteredOAuth2AuthorizedClient("demo-client")` and `registrationId="demo-client"` are equivalent.
- The scopes/refresh tests verify safe metadata without relying on raw tokens.
- The Bob and query-alias tests confirm the route neither uses a global username nor accepts a client-chosen registration ID.
- The POST without CSRF 403 and POST with CSRF 200 tests confirm that browser sessions still need CSRF even when outbound APIs use OAuth2.
- The outbound test needs no network, yet verifies the exact `Authorization: Bearer ...` added by the OAuth2 filter for the **selected request**.

## 9. Manual Practice with a Real AS

Run:

```bash
java -version
mvn -version
mvn spring-boot:run
```

Visit `http://localhost:8080/public` -> returns `public`. Open `http://localhost:8080/client/metadata` while unauthenticated -> redirects to `/login`. Log in with demo user `viewer` and password `viewer123`.

At the moment the controller needs `@RegisteredOAuth2AuthorizedClient("demo-client")`, the manager must find an authorized client in storage or execute the `client_credentials` grant with the AS. Because `token-uri=https://idp.example.invalid/token` is only a placeholder, **do not expect success with the unreplaced demo AS**. That is not a bug in the annotation.

To run against an AS authorized by your organization:

- Replace `client-id` and `client-secret` with real client credentials from a secrets manager.
- Replace `token-uri` with a verified HTTPS token endpoint.
- Request an appropriate scope such as `inventory.read` per provider.
- Determine whether the AS issues access tokens for the application or the user; ensure downstream APIs accept the proper audience and scope.
- When the browser logs in and calls the endpoint, return only the metadata DTO. If the token request fails, do not expose a full OAuth2 error description containing secrets.

Testing with `curl` without cookies only shows the redirect:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/client/metadata
```

`curl` does not persist session cookies between two commands. Simulating browser login requires a cookie jar, form CSRF token, and redirect flow; it is simpler to use a browser for login and `mvn test` for injection. Never leave real tokens in shell history or logs.

### 9.1. Using OIDC Login Instead of Form Login

A real application can configure:

```java
return http
    .authorizeExchange(ex -> ex
        .pathMatchers("/", "/login",
            "/oauth2/authorization/**",
            "/login/oauth2/code/**").permitAll()
        .anyExchange().authenticated())
    .oauth2Login(Customizer.withDefaults())
    .oauth2Client(Customizer.withDefaults())
    .build();
```

This is an **alternative configuration**, not a second filter chain bean with the same matcher. With `authorization_code`, provider/registration/redirect URI/`openid` properly configured, users log in via OIDC and Spring creates an `OAuth2AuthenticationToken` along with the associated authorized client. A controller using `@RegisteredOAuth2AuthorizedClient("enterprise-oidc")` can resolve the token authorized for that provider. If the user logged in via registration `google` and you need a token for `inventory-service`, a separate authorization or `client_credentials` grant is required; you cannot turn a Google ID Token into an inventory access token.

## 10. When Not to Use the Annotation

### 10.1. Service Methods or Scheduled Jobs

Instead of:

```java
// WRONG CONTEXT: no WebFlux handler argument resolver is available.
public Mono<String> scheduled(
    @RegisteredOAuth2AuthorizedClient("demo-client")
    OAuth2AuthorizedClient client) {
    return Mono.just("wrong pattern");
}
```

Inject `ReactiveOAuth2AuthorizedClientManager` and call `authorize(...)` with an `OAuth2AuthorizeRequest`:

```java
@Service
class ClientGateway {
    private final ReactiveOAuth2AuthorizedClientManager manager;

    ClientGateway(ReactiveOAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    Mono<OAuth2AuthorizedClient> authorize(
            String registrationId, Authentication principal) {

        OAuth2AuthorizeRequest req =
            OAuth2AuthorizeRequest
                .withClientRegistrationId(registrationId)
                .principal(principal)
                .build();

        return manager.authorize(req);
    }
}
```

This snippet requires imports and an appropriate manager. If using the web-oriented `DefaultReactiveOAuth2AuthorizedClientManager`, it may require a `ServerWebExchange` in context. Background work requires `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager`, `ReactiveOAuth2AuthorizedClientService`, and a managed service principal rather than borrowing admin authority from a fake request.

### 10.2. Merely Loading a Stored Token

`ReactiveOAuth2AuthorizedClientService.loadAuthorizedClient(registrationId, principalName)` can read a saved client. It is **not equivalent** to authorizing or refreshing. If the goal is a valid token to call an API, use the manager/provider with proper lifecycle handling rather than fetching and sending a stale token.

### 10.3. Complex Tenant/User-Specific Authorization Needed

The annotation makes registration selection convenient, yet tenant/resource ownership policies remain the responsibility of the service and API. Never read a registration ID from a public `X-Client` header and let callers pick any of the organization's client secrets. Never use `@Registered...` to bypass `@PreAuthorize` or `authorizeExchange`.

## 11. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Annotation not resolved | Missing OAuth2 client dependency/registration, or not invoked via WebFlux handler | Check starter, `oauth2Client()`, controller/`WebTestClient` |
| Client registration does not exist | Wrong `demo-client`/`provider`/`client-id` key | Cross-check properties and annotation |
| Client has no access token yet | Grant has not run or manager lacks support | Verify `authorization_code`/`client_credentials` and token endpoint |
| App fails calling fake token URI | Demo AS placeholder | Replace with real AS; mock tests only test injection |
| Logged in but authorized client missing | Authentication and authorization grant are distinct | Check authorized client store/grant |
| Upstream API returns 401 | Missing Bearer header, invalid/expired token, wrong audience | Inspect WebClient filter, token metadata, Resource Server |
| API returns 403 | Missing scope/role/object-level permission | Check API policy; do not bypass permissions |
| Refresh token is null | AS/grant does not issue one | Check for null; do not assume refresh always exists |
| Another user's token is used | Shared singleton cache or unpartitioned principal | Key store by principal/tenant, add multi-user tests |
| Token appears in JSON/logs | Serializing entire authorized client or printing Authorization header | Use safe DTOs, redaction, and incident response |
| Browser POST returns 403 despite login | Missing/invalid CSRF token | Keep CSRF for sessions, send a valid token |
| WebClient does not send Bearer | Missing `ServerOAuth2AuthorizedClientExchangeFilterFunction` | Install filter and attach attribute |
| WebClient sends token to unexpected host | Overly broad default authorized client enabled | Explicit client/request selection, allowlist destinations |
| Mock tests pass but production fails | Mock does not verify AS/tokens/PKCE/network | Add real sandbox e2e integration tests |
| Blocking on Netty | Calling `block()` inside controller | Return `Mono`/`Flux` and let WebFlux subscribe |

### 11.1. Do Not Treat the Annotation as Authentication

Spring Security still needs to authenticate requests via `WebSession`, OAuth2 Login, Basic, or your chosen mechanism. An authorized client holding a token does **not** automatically grant the user every role in the application. `hasRole("ADMIN")`/`@PreAuthorize`/tenant checks are still required by the domain.

### 11.2. Do Not Send an ID Token by Mistake

OIDC ID Tokens serve Relying Party login; Resource Servers require an access token issued for the right audience/scope. Having a signed JWT is no excuse to send an ID Token to an arbitrary API.

### 11.3. Do Not Leak Tokens via Debug or Exceptions

Avoid `log.info("client={}", authorizedClient)`, full HTTP headers, unrestricted JSON serialization, and URL query tokens. Token values can be captured by filters or tracing; configure redaction and log only safe metadata with a correlation ID.

## 12. Pre-Production Checklist

1. Confirm the app acts as an **OAuth2 Client**, not confused with an AS/Resource Server.
2. Use a trusted client registration/provider with exact grant type, scopes, token URI, and redirect URI.
3. Place the annotation on an **annotated WebFlux controller method parameter** with an explicit registration ID.
4. Ensure request `Authentication` and authorized client principal/tenant match, using no global token.
5. Manage refresh, renewal, expiry, revocation, and persistence properly across multiple app instances.
6. Install the OAuth2 filter on `WebClient`, attaching tokens only on requests to allowed hosts without broad defaults.
7. Never send access/refresh/ID tokens or client secrets to browsers or logs; use safe DTOs.
8. Keep CSRF enabled for state-changing browser session routes; outbound OAuth2 Client does not eliminate CSRF.
9. Validate Resource Server audience, issuer, expiration, scopes, and domain permissions.
10. Test annotation resolution using `mockOAuth2Client` with `WebTestClient`, and test grants/refresh against a real sandbox AS.
11. For scheduled/background jobs, use the service manager and avoid fabricating nonexistent web exchanges.
12. Monitor token endpoint authorization errors using correlation IDs without exposing credentials, with policy-based timeouts/retries.
13. Keep Spring Security/Boot on supported versions and re-run regression tests after upgrades.

## 13. Self-Assessment

**1.** What does `@RegisteredOAuth2AuthorizedClient("demo-client")` look up?  
The authorized client keyed by registration and principal/context managed by reactive OAuth2 Client infrastructure, not a bare client ID.

**2.** Why is `ClientRegistration` different from `OAuth2AuthorizedClient`?  
One is the configuration registered with the AS; the other binds that configuration to a principal and issued tokens.

**3.** Should the method parameter be `OAuth2AuthorizedClient` or `Mono<OAuth2AuthorizedClient>`?  
The standard official type is **`OAuth2AuthorizedClient`**; the reactive resolver handles asynchronous resolution before passing the argument.

**4.** Can the same registration be used for both Alice and Bob?  
Yes, provided records are stored and looked up per principal/tenant and user tokens are never mixed.

**5.** If the browser user has logged in, does a `client_credentials` token already exist?  
Not necessarily. Browser `Authentication` and OAuth2 authorization grants are separate states.

**6.** Is a `client_credentials` token necessarily a user token?  
No. It typically represents the permissions of the **client application**.

**7.** Why is `ServerOAuth2AuthorizedClientExchangeFilterFunction` needed?  
So `WebClient` reads the authorized client attribute and attaches the Bearer token to outbound requests as configured.

**8.** Can `OAuth2AuthorizedClient` be returned directly in JSON?  
Never: it contains the access token and possibly a refresh token. Use a selectively chosen metadata DTO.

**9.** Does `mockOAuth2Client` verify real tokens from an AS?  
No. It supplies a fake authorized client in the test context and does not check the token endpoint, refresh, or PKCE.

**10.** Can a local WebFlux controller annotation be used inside a scheduled job?  
Not via standard handler argument resolution. Background code uses the service-based reactive manager.

**11.** Why can a session POST return 403 even when the client has an access token?  
Because CSRF protects browser cookie/session mutations independently from outbound OAuth2 client tokens.

**12.** Should `setDefaultOAuth2AuthorizedClient(true)` be enabled on a shared WebClient?  
It risks leaking tokens to unintended hosts; prefer explicit per-request client selection and a trusted host allowlist.

### Official Documentation

- Spring Security 6.5, *Reactive Authorized Client Features*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html
- Spring Security 6.5, *OAuth2 Client Core Interfaces*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html
- Spring Security 6.5, *OAuth2 Client Authorization Grants*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorization-grants.html
- Spring Security 6.5, *OAuth2 WebFlux Overview*: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security 6.5 API, `RegisteredOAuth2AuthorizedClient`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/annotation/RegisteredOAuth2AuthorizedClient.html
- Spring Security 6.5 API, `OAuth2AuthorizedClientArgumentResolver` (reactive): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/reactive/result/method/annotation/OAuth2AuthorizedClientArgumentResolver.html
- Spring Security, *Testing OAuth2 Clients in WebFlux*: https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html
- Spring Security, *Testing WebFlux Authentication*: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/authentication.html

**Summary:** `@RegisteredOAuth2AuthorizedClient` allows a WebFlux controller to receive an authorized client for the proper registration and principal via Spring Security Reactive infrastructure. Distinguish registration configuration from tokens and grants, use the `WebClient` OAuth2 filter to send access tokens **to the intended API**, never leak credentials, and never treat the annotation as a replacement for authentication or authorization. Testing with `mockOAuth2Client` works well for the resolver, but real grant, refresh, and security integration tests are mandatory before production.