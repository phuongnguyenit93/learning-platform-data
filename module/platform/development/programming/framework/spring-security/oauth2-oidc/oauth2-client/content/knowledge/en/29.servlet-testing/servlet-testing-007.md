# 29.7. Testing `@RegisteredOAuth2AuthorizedClient` and Registration Selection

## 1. Context: The Controller Receives a Token, but from Which OAuth Client?

An **Employee Portal** application uses **Spring Security OAuth 2.0/OIDC Client** with two client registrations:

~~~text
portal-web
  -> Access token with scope orders.read
  -> Calls Orders API

portal-admin
  -> Access token with scope audit.read
  -> Calls Audit API
~~~

Both may share an OpenID Provider, yet **client IDs, scopes, authorizations, and tokens must stay distinct**. A REST controller declares:

~~~java
@RegisteredOAuth2AuthorizedClient("portal-web")
OAuth2AuthorizedClient authorizedClient
~~~

to obtain the token granted for registration `portal-web`.

If a test merely calls:

~~~java
mvc.perform(get("/api/orders").with(oidcLogin()));
~~~

and asserts HTTP 200, it can miss the critical question: **was the controller injected with the authorized client for the right registration and principal?** In addition, the test may fail because the mock login only carries a default registration, whereas the controller demands `portal-web`.

A meaningful test suite must verify:

- The HTTP request is authenticated in the proper context.
- `OAuth2AuthorizedClient` is resolved from the right repository/manager.
- The `registrationId` matches.
- The principal owns the right authorized client.
- The access token/scopes match the expected test values.
- A token for registration A is never sent to registration B's API.
- When authorization is missing, failure follows policy and **never falls back to another token**.

> This hands-on guide focuses on **Spring MVC/Servlet**, Spring Boot 3, Spring Security 6, JUnit 5, and MockMvc. You do not need a real Authorization Server to test method argument resolution. Adapt imports, packages, and security policies to your application. All tokens used in tests are dummy values.

## 2. Learning Objectives

After this lesson, learners will be able to:

1. Explain the role of `@RegisteredOAuth2AuthorizedClient` in Spring MVC.
2. Distinguish **OAuth2 Authentication**, **`ClientRegistration`**, and **`OAuth2AuthorizedClient`**.
3. Pick the right test tool: `oauth2Login()`, `oidcLogin()`, and `oauth2Client()`.
4. Build fixtures containing multiple registrations with different issuers, client IDs, and scopes.
5. Use MockMvc to test a controller whose annotation specifies an explicit registration.
6. Test cases where the annotation omits the registration and relies on the current OAuth2 login context.
7. Test `principalName`, scopes, token expiry, and authorized-client repositories.
8. Avoid confusing `@WithMockUser` with a stored authorized client.
9. Test missing/wrong registration, 401/403, CSRF, multi-tenancy, and session scenarios.
10. Recognize MockMvc's limits and when to use a fake HTTP server or browser E2E.

## 3. Four Easily Confused Components

| Component | Example | Responsibility |
|---|---|---|
| `Authentication` | `OAuth2AuthenticationToken` | Identifies the currently authenticated principal |
| `ClientRegistration` | `portal-web` | Metadata of an OAuth client (client ID, secret, grant, scopes, endpoints) |
| `OAuth2AuthorizedClient` | `portal-web + alice + AT-W` | Authorization/token granted for a client and principal |
| `OAuth2AuthorizedClientManager` | Servlet manager | Loads, authorizes, refreshes, and saves authorized clients via provider chain |

A user logged in via OIDC does not imply the user has authorized every OAuth client in the application:

~~~text
Current browser Authentication:
  registrationId = portal-web
  principal = alice

Authorized Client store:
  (portal-web, alice)  -> AT-W
  (portal-admin, alice) -> AT-A [may or may not exist]
~~~

If a controller requires `portal-admin`, it must never substitute `portal-web` simply because the principal has the same name.

### 3.1. Distinguishing `registrationId` and Provider Key

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal-web:
            provider: company-oidc
          portal-admin:
            provider: company-oidc
        provider:
          company-oidc:
            issuer-uri: https://login.example.test
~~~

Here:

~~~text
Registration IDs: portal-web, portal-admin
Provider alias:   company-oidc
~~~

The annotation uses the **registration ID**, not the provider alias.

### 3.2. An Authorized Client Is Not an ID Token

`OAuth2AuthorizedClient.getAccessToken()` returns an access token for calling a Resource Server. OIDC `OidcUser.getIdToken()` is an ID Token for client authentication; tests must never treat them as the same thing.

## 4. At Which Layer Does the Annotation Operate?

Controller:

~~~java
@GetMapping("/api/orders")
public String orders(
    @RegisteredOAuth2AuthorizedClient("portal-web")
    OAuth2AuthorizedClient authorizedClient
) {
    return authorizedClient.getClientRegistration().getRegistrationId();
}
~~~

Spring Security provides:

~~~java
org.springframework.security.oauth2.client.web.method.annotation
    .OAuth2AuthorizedClientArgumentResolver
~~~

This is a `HandlerMethodArgumentResolver` for parameters carrying the annotation. The resolver delegates to `OAuth2AuthorizedClientManager`, inheriting the manager's capabilities (loading authorized clients, refreshing/authorizing via the provider chain).

~~~mermaid
sequenceDiagram
    actor Test as MockMvc Test
    participant MVC as Spring MVC
    participant Resolver as OAuth2AuthorizedClientArgumentResolver
    participant Manager as OAuth2AuthorizedClientManager
    participant Repo as AuthorizedClientRepository
    participant Controller as OrdersController

    Test->>MVC: GET /api/orders with test SecurityContext + authorized client
    MVC->>Resolver: Resolve annotation("portal-web")
    Resolver->>Manager: authorize with registrationId + principal
    Manager->>Repo: Load authorized client
    Repo-->>Manager: portal-web / alice / AT-W
    Manager-->>Resolver: Authorized client
    Resolver-->>Controller: OAuth2AuthorizedClient parameter
    Controller-->>Test: Safe response (not token value)
~~~

**MockMvc tests must supply both the right `SecurityContext` and authorized-client state when the controller expects them.** Setting a mock `Authentication` without the repository knowing about a token may not be enough.

## 5. Two Ways to Use the Annotation

### 5.1. Specifying the Registration Explicitly

~~~java
@RegisteredOAuth2AuthorizedClient("portal-web")
OAuth2AuthorizedClient webClient
~~~

is equivalent to:

~~~java
@RegisteredOAuth2AuthorizedClient(registrationId = "portal-web")
OAuth2AuthorizedClient webClient
~~~

`value` and `registrationId` are annotation aliases. Prefer this form whenever an endpoint always calls an API using a fixed registration.

### 5.2. Omitting the Registration

~~~java
@RegisteredOAuth2AuthorizedClient
OAuth2AuthorizedClient currentClient
~~~

When the ID is omitted, the resolver can rely on the current `OAuth2AuthenticationToken` to determine the registration (depending on the request/authentication context and configuration).

This behavior should be **tested explicitly**, especially in applications with multiple registrations or multiple `Authentication` types.

### 5.3. Registration Is Never Chosen from the Method Name

A controller method name like:

~~~java
public String adminOrders(...)
~~~

does not make Spring automatically choose `portal-admin`. Explicit annotation configuration or selection logic is required.

## 6. Dependencies for the Project and Tests

With Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

If using `WebClient` to call downstream APIs:

~~~kotlin
implementation("org.springframework.boot:spring-boot-starter-webflux")
~~~

only when the application needs `WebClient`/WebFlux components. Spring MVC's `MockMvc` does not require switching the application to the Reactive stack.

Keep versions managed by a compatible Spring Boot dependency management/BOM; never mix `spring-security-test` from an incompatible version with core.

## 7. Two `ClientRegistration` Fixtures with Distinct Metadata

We construct test registrations directly so we **never trigger production OIDC discovery**:

~~~java
package com.example.portal.test;

import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

public final class TestRegistrations {

    private TestRegistrations() {}

    public static ClientRegistration web() {
        return ClientRegistration.withRegistrationId("portal-web")
            .clientId("portal-web-test-client")
            .clientSecret("web-test-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "orders.read")
            .authorizationUri("https://idp.example.test/oauth2/authorize")
            .tokenUri("https://idp.example.test/oauth2/token")
            .jwkSetUri("https://idp.example.test/oauth2/jwks")
            .issuerUri("https://idp.example.test")
            .clientName("Portal Web")
            .build();
    }

    public static ClientRegistration admin() {
        return ClientRegistration.withRegistrationId("portal-admin")
            .clientId("portal-admin-test-client")
            .clientSecret("admin-test-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile", "audit.read")
            .authorizationUri("https://idp.example.test/oauth2/authorize")
            .tokenUri("https://idp.example.test/oauth2/token")
            .jwkSetUri("https://idp.example.test/oauth2/jwks")
            .issuerUri("https://idp.example.test")
            .clientName("Portal Admin")
            .build();
    }
}
~~~

Both registrations share **the same issuer** while differing in:

~~~text
registration ID
client ID
dummy client secret
scope
clientName
~~~

This setup is well suited for catching wrong-authorized-client selection bugs. If both fixtures shared the same token and scopes, tests would struggle to detect selection mistakes.

### 7.1. Why Not Use Real Client Secrets?

MockMvc does not perform real token exchanges with the IdP in these tests. Fixed dummy test secrets avoid exposing production credentials and keep tests deterministic.

### 7.2. Why Use Fake Issuer/JWK URIs?

This is purely metadata for constructing `ClientRegistration`; controller tests do not actually download JWKS or verify ID Tokens over the network. Real IdP integration tests need separate fake discovery/JWK/token endpoints.

## 8. Creating Fake `OAuth2AccessToken` Fixtures for Tests

Never use real production access tokens. Use:

~~~java
package com.example.portal.test;

import java.time.Instant;
import java.util.Set;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

public final class TestAccessTokens {
    private TestAccessTokens() {}

    public static OAuth2AccessToken webToken() {
        Instant now = Instant.now();
        return new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "fake-access-token-for-web",
            now.minusSeconds(10),
            now.plusSeconds(600),
            Set.of("orders.read")
        );
    }

    public static OAuth2AccessToken adminToken() {
        Instant now = Instant.now();
        return new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "fake-access-token-for-admin",
            now.minusSeconds(10),
            now.plusSeconds(600),
            Set.of("audit.read")
        );
    }
}
~~~

**Access tokens must be non-expired** in tests focused strictly on argument resolution. If a fixture is expired, the manager may try to refresh/reauthorize and make the test inadvertently depend on token endpoint/provider configuration.

### 8.1. Why Is `expiresAt` in the Future?

~~~text
now = 09:00
expiresAt = 09:10
~~~

lets the manager reuse the stored authorized client. With an expired or nearly expired token and clock skew, it may invoke refresh provider behavior, which is outside the scope of happy-path unit tests.

### 8.2. When You Need to Test Expired Tokens

Create a separate token with `expiresAt` in the past and **mock the token refresh provider/manager or use a fake token endpoint**; do not put expired tokens into default fixtures.

## 9. Creating `OAuth2AuthorizedClient` with a Specific Principal

~~~java
package com.example.portal.test;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;

public final class TestAuthorizedClients {
    private TestAuthorizedClients() {}

    public static OAuth2AuthorizedClient webFor(String principalName) {
        return new OAuth2AuthorizedClient(
            TestRegistrations.web(),
            principalName,
            TestAccessTokens.webToken()
        );
    }

    public static OAuth2AuthorizedClient adminFor(String principalName) {
        return new OAuth2AuthorizedClient(
            TestRegistrations.admin(),
            principalName,
            TestAccessTokens.adminToken()
        );
    }
}
~~~

In production, `OAuth2AuthorizedClient` may also hold a refresh token; here it is omitted because we are only testing resolution of a valid client.

### 9.1. Principal Key Is a Security Boundary

~~~text
portal-web + alice -> AT-W-Alice
portal-web + bob   -> AT-W-Bob
portal-admin + alice -> AT-A-Alice
~~~

Never retrieve `bob`'s authorized client when the current `Authentication` is `alice`.

### 9.2. Tokens Do Not Have to Be JWTs

`OAuth2AccessToken` in Spring Security can hold an opaque token or a JWT string. For resolver tests, we only need a fake token value with appropriate expiry and scopes; no cryptographic signature is needed.

## 10. Sample Controller: Returning Safe Metadata Instead of Tokens

Controller for observing which registration is injected:

~~~java
package com.example.portal.web;

import java.util.Map;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation
    .RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/test/clients")
public class AuthorizedClientProbeController {

    @GetMapping("/web")
    public Map<String, String> web(
        @RegisteredOAuth2AuthorizedClient("portal-web")
        OAuth2AuthorizedClient client
    ) {
        return safeView(client);
    }

    @GetMapping("/admin")
    public Map<String, String> admin(
        @RegisteredOAuth2AuthorizedClient("portal-admin")
        OAuth2AuthorizedClient client
    ) {
        return safeView(client);
    }

    @GetMapping("/current")
    public Map<String, String> current(
        @RegisteredOAuth2AuthorizedClient
        OAuth2AuthorizedClient client
    ) {
        return safeView(client);
    }

    private Map<String, String> safeView(OAuth2AuthorizedClient client) {
        return Map.of(
            "registrationId",
            client.getClientRegistration().getRegistrationId(),
            "principalName",
            client.getPrincipalName(),
            "clientId",
            client.getClientRegistration().getClientId()
        );
    }
}
~~~

The `/test/clients/**` paths are strictly for illustration/testing. In production, **never expose access tokens, refresh tokens, or client secrets**, and reveal only necessary metadata per authorization policy.

### 10.1. What Does This Controller Verify?

When `/test/clients/web` returns:

~~~json
{
  "registrationId": "portal-web",
  "principalName": "alice",
  "clientId": "portal-web-test-client"
}
~~~

we know which registration and owner the controller's `OAuth2AuthorizedClient` parameter belongs to. **It does not prove the Resource Server accepts the access token**, because this is a mock.

### 10.2. Why Not Return `tokenValue`?

Dummy test tokens are not sensitive, yet a pattern where controllers return raw tokens easily gets copied into production. Inspect tokens in **test fixtures/spies** or a fake downstream server instead of turning responses into Bearer credential-leaking APIs.

## 11. Setting Up Spring Security and `HttpSessionOAuth2AuthorizedClientRepository` for MockMvc

A Servlet test configuration:

~~~java
package com.example.portal.test;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.client.registration
    .ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration
    .InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client.web
    .HttpSessionOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web
    .OAuth2AuthorizedClientRepository;
import org.springframework.security.web.SecurityFilterChain;

@TestConfiguration
public class OAuth2MvcTestConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository() {
        return new InMemoryClientRegistrationRepository(
            TestRegistrations.web(),
            TestRegistrations.admin()
        );
    }

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository() {
        return new HttpSessionOAuth2AuthorizedClientRepository();
    }

    @Bean
    SecurityFilterChain testSecurityChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Key points:

- The registration repository contains both `portal-web` and `portal-admin`.
- The authorized-client repository uses **`HttpSessionOAuth2AuthorizedClientRepository`** in the test.
- Spring Security filters run inside MockMvc.
- The controller has the argument resolver registered through Spring MVC/Security configuration.

**No real Authorization Server is started**; fake registrations hold metadata only.

### 11.1. Why Does the Repository Bean Matter?

Test request post-processors such as `oauth2Client()`, `oauth2Login()`, and `oidcLogin()` place simulated authorized clients into the session via **`HttpSessionOAuth2AuthorizedClientRepository`**. If the application uses a custom repository or a service-based manager reading elsewhere, the argument resolver may not find the token.

To test a production repository/custom manager, configure the **same implementation and storage contract** used by the resolver, rather than assuming post-processors populate every backend.

### 11.2. Why Is the Spring Security Filter Chain Required?

The `oauth2Login()` and `oidcLogin()` post-processors put `Authentication` on the mock request context; Spring Security filters make that `Authentication` active in `SecurityContextHolder` when MVC/controllers execute.

With `MockMvcBuilders.standaloneSetup(...)`, you must attach `.apply(springSecurity())` or a proper security filter chain while also registering the appropriate argument resolver.

## 12. `@WebMvcTest`: A Controller-Focused Test Class

~~~java
package com.example.portal.web;

import com.example.portal.test.OAuth2MvcTestConfig;
import com.example.portal.test.TestRegistrations;
import com.example.portal.test.TestAccessTokens;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Client;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@WebMvcTest(controllers = AuthorizedClientProbeController.class)
@Import(OAuth2MvcTestConfig.class)
class AuthorizedClientProbeControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void webEndpointUsesWebRegistrationForAlice() throws Exception {
        mvc.perform(get("/test/clients/web")
                .with(user("alice"))
                .with(oauth2Client("portal-web")
                    .clientRegistration(TestRegistrations.web())
                    .principalName("alice")
                    .accessToken(TestAccessTokens.webToken())))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.registrationId")
                .value("portal-web"))
            .andExpect(jsonPath("$.principalName")
                .value("alice"))
            .andExpect(jsonPath("$.clientId")
                .value("portal-web-test-client"));
    }

    @Test
    void adminEndpointUsesAdminRegistrationForAlice() throws Exception {
        mvc.perform(get("/test/clients/admin")
                .with(user("alice"))
                .with(oauth2Client("portal-admin")
                    .clientRegistration(TestRegistrations.admin())
                    .principalName("alice")
                    .accessToken(TestAccessTokens.adminToken())))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.registrationId")
                .value("portal-admin"))
            .andExpect(jsonPath("$.principalName")
                .value("alice"))
            .andExpect(jsonPath("$.clientId")
                .value("portal-admin-test-client"));
    }
}
~~~

**Key point:** the MockMvc request has both `user("alice")` to pass the authentication layer and `oauth2Client("portal-web")` or `oauth2Client("portal-admin")` so the repository holds the authorized-client entry for the right registration and principal.

### 12.1. In a SecurityMockMvc Test, Can `@WithMockUser` Replace `user("alice")`?

You can use:

~~~java
@WithMockUser(username = "alice")
@Test
void webEndpointUsesWebRegistration() throws Exception {
    mvc.perform(get("/test/clients/web")
            .with(oauth2Client("portal-web")
                .principalName("alice")
                .clientRegistration(TestRegistrations.web())
                .accessToken(TestAccessTokens.webToken())))
        .andExpect(status().isOk());
}
~~~

However, `@WithMockUser` only sets up a mock `Authentication`; it **does not create an `OAuth2AuthorizedClient`**. Therefore `oauth2Client()` is still needed in this scenario.

### 12.2. When `@WebMvcTest` Uses the Real Security Configuration

You may need to `@Import` the slice's filter-chain/manager/repository beans. Avoid accidentally registering two beans of the same type or triggering auto-configuration that performs Internet issuer discovery.

Tests should have explicit, completely local configuration.

## 13. `oauth2Client()` — The Primary Tool for Testing the Annotation

Spring Security Test provides:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Client;
~~~

Minimal usage:

~~~java
mvc.perform(get("/test/clients/web")
        .with(user("user"))
        .with(oauth2Client("portal-web")))
    .andExpect(status().isOk());
~~~

However, the default post-processor creates a **mock** authorized client with default metadata, token, and principal; if the app checks `clientId`/`scopes` against fixtures, configure:

~~~java
.with(oauth2Client("portal-web")
    .principalName("alice")
    .clientRegistration(TestRegistrations.web())
    .accessToken(TestAccessTokens.webToken()))
~~~

### 13.1. Key Customizations

| Method | Purpose |
|---|---|
| `oauth2Client("portal-web")` | Selects the registration ID of the mock authorized client |
| `.principalName("alice")` | Sets the owner of the authorized client |
| `.clientRegistration(clientRegistration)` | Attaches full client metadata |
| `.clientRegistration(builder -> ...)` | Customizes the client registration builder in the test |
| `.accessToken(accessToken)` | Attaches a mock access token/scopes/expiry |

### 13.2. `oauth2Client()` Is Not Equivalent to `oauth2Login()`

`oauth2Client()` focuses on placing **authorized-client state into the repository/session**. It does not ensure the user has an `OAuth2AuthenticationToken`/`OidcUser`; when an endpoint requires authentication, add `user()`, `oauth2Login()`, or `oidcLogin()` per test.

### 13.3. Do Not Rely on the Default Token Fixture for Security Policies

The default post-processor has simple scopes (such as `read`). If a controller checks `orders.read`, construct an access token with that exact scope.

## 14. `oidcLogin()` — Simulating OIDC Authentication and Authorized Client

For OIDC applications:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
~~~

Testing the current registration:

~~~java
@Test
void currentRegistrationUsesOidcLoginRegistration() throws Exception {
    mvc.perform(get("/test/clients/current")
            .with(oidcLogin()
                .clientRegistration(TestRegistrations.web())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId")
            .value("portal-web"));
}
~~~

`oidcLogin()` creates a mock `OidcUser` and `OAuth2AuthenticationToken`, while also associating a mock authorized client in the session. Thus it fits controllers that declare:

~~~java
@AuthenticationPrincipal OidcUser user
~~~

or inspect OIDC claims.

### 14.1. Customizing ID Token Claims

~~~java
mvc.perform(get("/api/profile")
    .with(oidcLogin()
        .clientRegistration(TestRegistrations.web())
        .idToken(token -> token.claim("tenant", "acme"))));
~~~

Claims are **synthesized** for the test; no real signature/issuer is verified over the network during the mock request.

### 14.2. When Should You Still Pair `oauth2Client()` with `oidcLogin()`?

For example, when the browser logged in via `portal-web`, yet the controller also needs a token for `portal-admin`:

~~~java
mvc.perform(get("/test/clients/admin")
    .with(oidcLogin()
        .clientRegistration(TestRegistrations.web()))
    .with(oauth2Client("portal-admin")
        .principalName("user")
        .clientRegistration(TestRegistrations.admin())
        .accessToken(TestAccessTokens.adminToken())))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.registrationId")
        .value("portal-admin"));
~~~

In this example, `oidcLogin()`'s default principal is `user`. Thus the mock ADMIN authorized client also needs `principalName("user")`. If a test uses a custom `OidcUser`, ensure `principalName` matches `Authentication.getName()`.

**Note:** if the application's custom repository/manager does not read authorized clients from `HttpSession`, seed that store directly; do not assume the post-processor populates every backend.

## 15. `oauth2Login()` — When `OidcUser` Is Not Needed

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Login;
~~~

Example:

~~~java
@Test
void currentRegistrationWithOauth2Login() throws Exception {
    mvc.perform(get("/test/clients/current")
            .with(oauth2Login()
                .clientRegistration(TestRegistrations.admin())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId")
            .value("portal-admin"));
}
~~~

`oauth2Login()` creates a mock `OAuth2User`, whereas `oidcLogin()` creates a mock `OidcUser`. Both establish an `OAuth2AuthenticationToken` and populate authorized-client state for the mock request.

### 15.1. Choosing from the Controller's Perspective

| Controller needs | Appropriate test post-processor |
|---|---|
| Standard username/authorities | `user()` or `@WithMockUser` |
| `OAuth2User` / OAuth2 login | `oauth2Login()` |
| `OidcUser` / ID Token claims | `oidcLogin()` |
| Only a specific authorized client | `oauth2Client("id")` plus an appropriate `Authentication` |
| Browser logged in via web, yet calling admin authorized client | `oidcLogin(web)` + `oauth2Client(admin)` |

### 15.2. Never Use `jwt()` Instead of `oauth2Client()`

`jwt()` builds a `JwtAuthenticationToken` for **Resource Server authentication tests**, rather than creating an authorized client in the **OAuth2 Client repository**.

These are two distinct features of Spring Security.

## 16. Testing an Explicit Registration ID Differing from Current Login Registration

Sending a request where they differ:

~~~java
@Test
void explicitWebIgnoresCurrentAdminLoginRegistration()
        throws Exception {
    mvc.perform(get("/test/clients/web")
        .with(oidcLogin()
            .clientRegistration(TestRegistrations.admin()))
        .with(oauth2Client("portal-web")
            .principalName("user")
            .clientRegistration(TestRegistrations.web())
            .accessToken(TestAccessTokens.webToken())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId").value("portal-web"));
}
~~~

The current `Authentication` belongs to ADMIN, while the explicit annotation requests WEB; if a WEB authorized client exists for that principal, the resolver picks WEB. Such tests catch code that accidentally runs:

~~~java
((OAuth2AuthenticationToken) authentication)
    .getAuthorizedClientRegistrationId();
~~~

and defaults to the currently logged-in registration for every downstream API.

### 16.1. Authorization Must Be Verified at the Business Layer

Because a user can hold both WEB and ADMIN tokens in the store, the fact that a method receives the ADMIN authorized client **does not mean the user holds `ROLE_ADMIN` in the domain app**.

MockMvc tests should verify separately:

- Whether the user is allowed/denied on the endpoint.
- Which registration is selected if the endpoint is invoked.
- Downstream Resource Server audience/scopes/permissions.

Never conflate these three assertions.

## 17. Testing the Annotation Without a Registration When Multiple Clients Exist

Controller:

~~~java
@GetMapping("/test/clients/current")
public Map<String, String> current(
    @RegisteredOAuth2AuthorizedClient OAuth2AuthorizedClient client
) {
    return safeView(client);
}
~~~

Tests:

~~~java
@Test
void currentFollowsWebLogin() throws Exception {
    mvc.perform(get("/test/clients/current")
        .with(oidcLogin()
            .clientRegistration(TestRegistrations.web())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId").value("portal-web"));
}

@Test
void currentFollowsAdminLogin() throws Exception {
    mvc.perform(get("/test/clients/current")
        .with(oidcLogin()
            .clientRegistration(TestRegistrations.admin())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.registrationId").value("portal-admin"));
}
~~~

When no `OAuth2AuthenticationToken` exists or the resolver lacks enough context to select, exact behavior depends on the manager/config. Tests **must not assume** Spring picks the first registration listed in YAML.

### 17.1. Sharing a Provider Does Not Distinguish Registrations

~~~text
portal-web.provider=company-oidc
portal-admin.provider=company-oidc
~~~

In reality, there are still two independent `ClientRegistration` instances. A provider alias cannot answer "which authorized client?".

### 17.2. Prefer Explicit Selection for Fixed Endpoints

If the Orders endpoint always needs the WEB token:

~~~java
@RegisteredOAuth2AuthorizedClient("portal-web")
~~~

is far less ambiguous than an empty annotation, especially after a user re-authenticates via the ADMIN registration.

## 18. Principal Name: Verifying the Right Owner of the Authorized Client

Suppose a test runs:

~~~java
mvc.perform(get("/test/clients/web")
    .with(user("alice"))
    .with(oauth2Client("portal-web")
        .principalName("bob")
        .clientRegistration(TestRegistrations.web())));
~~~

The application sees `Authentication` as `alice`, while the authorized-client fixture belongs to `bob`. The controller must not receive Bob's token.

**Expected result depends on repository/manager:** it may fail to find an authorized client and trigger an authorization flow or error. What must be tested is:

~~~text
Mismatched owner must not silently return Bob's token to Alice.
~~~

### 18.1. Matching Properly with `principalName`

~~~java
.with(user("alice"))
.with(oauth2Client("portal-web")
    .principalName("alice")
    .clientRegistration(TestRegistrations.web()))
~~~

Depending on the app's custom principal, `Authentication.getName()` may be `sub` or an internal ID. Never assume email is a stable principal key.

### 18.2. OIDC Pairwise Subjects and Account Linking

The same user at the same OP can receive different pairwise `sub` values across registrations/sectors. In tests, principals must reflect verified identity mapping; never merge tokens solely because emails match.

## 19. Testing Token Scopes — Scopes Belong to the Token, Not the Annotation

Controller:

~~~java
@GetMapping("/test/clients/web/scopes")
public Set<String> scopes(
    @RegisteredOAuth2AuthorizedClient("portal-web")
    OAuth2AuthorizedClient authorizedClient
) {
    return authorizedClient.getAccessToken().getScopes();
}
~~~

Test:

~~~java
@Test
void webAccessTokenCarriesOrdersRead() throws Exception {
    mvc.perform(get("/test/clients/web/scopes")
        .with(user("alice"))
        .with(oauth2Client("portal-web")
            .principalName("alice")
            .clientRegistration(TestRegistrations.web())
            .accessToken(TestAccessTokens.webToken())))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$[0]").value("orders.read"));
}
~~~

In the demo, `TestAccessTokens.webToken()` returns `Set.of("orders.read")`, so there is one element. When a set holds multiple scopes, do not rely on index ordering since `Set` does not guarantee iteration order.

### 19.1. `ClientRegistration` Scopes Differ from Granted Token Scopes

~~~text
Configured scopes:
  openid profile orders.read

Granted access token scopes:
  orders.read
~~~

The two sets do not have to match because the Authorization Server can apply grant/consent/scope policies. A controller reading `authorizedClient.getAccessToken().getScopes()` inspects **granted token scopes**, not merely configured scopes.

### 19.2. A Token Carrying a Scope Is Not Enough to Prove Resource Server Acceptance

A mocked JWT payload with `scope=orders.read` does not prove the Orders API will permit the call. The API also validates issuer, signature, audience, tenant, ownership, and policy. Write separate integration tests for Bearer requests.

## 20. Testing Token Expiry and Refresh by Separating Layers

If you need to test how the manager handles an expired token:

~~~java
Instant now = Instant.now();
OAuth2AccessToken expired = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "fake-expired-token",
    now.minusSeconds(3600),
    now.minusSeconds(60),
    Set.of("orders.read")
);
~~~

Do not let controller annotation tests accidentally call a real token endpoint. There are three options:

1. Unit-test the provider/manager separately with a fake token-response client.
2. Mock the `OAuth2AuthorizedClientManager` used by the argument resolver.
3. Stand up a fake HTTP token endpoint in an integration test.

### 20.1. Do Not Equate "Resolver Injected" with "Refresh Succeeded"

The resolver can return a valid non-expired authorized client without calling the AS. Argument resolution tests prove the right registration/principal is picked, whereas refresh tests must prove:

~~~text
Input:
  expired AT, valid RT, correct registration

Expected:
  refresh grant invoked with correct client credentials/RT
  new authorized client persisted
  original principal/registration preserved
~~~

That is a **different test goal**—do not cram everything into one MockMvc method.

### 20.2. Refresh Token Rotation and Concurrent Tests

When multiple requests share an authorized client, a refresh token may be rotated. Negative tests must verify that failure cleanup never deletes a newer token or a token belonging to another registration.

## 21. Testing Repository/Service with Two Registrations

In Servlet:

~~~java
OAuth2AuthorizedClientRepository
OAuth2AuthorizedClientService
~~~

differ in persistence scope:

- **Repository**: normally serves web requests, often session-based.
- **Service**: application-level authorized clients, such as in-memory or JDBC.

### 21.1. Testing Web/Admin Loads Independently

~~~text
Given:
  (portal-web, alice) -> AT-W
  (portal-admin, alice) -> AT-A

When:
  load portal-web for alice
Then:
  return AT-W

When:
  load portal-admin for alice
Then:
  return AT-A
~~~

### 21.2. Testing Narrowly Scoped Cleanup

~~~text
Remove (portal-web, alice).

Expected:
  (portal-admin, alice) still exists.
  (portal-web, bob) still exists.
~~~

Never delete all tokens for an issuer merely because the WEB token became invalid.

### 21.3. Testing with Spring Session/JDBC Custom Storage

If production stores authorized clients in Redis/JDBC, `oauth2Client()` putting a dummy token in `HttpSession` **may hit the wrong store** relative to the app. To test custom persistence, seed the actual `OAuth2AuthorizedClientService` or matching repository with exact principal and registration IDs.

## 22. Testing Registration Selection by Business Use Case

An application has:

~~~text
OrdersController:
  always portal-web

AuditController:
  always portal-admin

ReportsJob:
  reports-service with client_credentials
~~~

With an explicit controller annotation:

~~~java
@RegisteredOAuth2AuthorizedClient("portal-web")
~~~

MockMvc can prove the controller receives the WEB token.

However, if business logic picks a registration based on tenant or endpoint:

~~~java
String registrationId =
    trustedTenantRegistry.registrationFor(authorizedTenant);
~~~

selection lives in the service/manager, **no longer as a dynamic annotation value**. Test with a fake manager/registry and verify `OAuth2AuthorizeRequest` carries an allowlisted registration.

### 22.1. Never Turn the Annotation Value into an HTTP Parameter

Using:

~~~text
/api/orders?registrationId=portal-admin
~~~

does not replace the fixed `@RegisteredOAuth2AuthorizedClient("portal-web")` annotation. If dynamic selection is needed, implement dedicated logic and test authorization thoroughly.

### 22.2. Never Use `client_credentials` to Bypass User Authorization

If the `portal-web` token lacks permissions, never switch to a higher-privileged `reports-service` client to bypass policy. Unit tests should reject unauthorized registration switching.

## 23. Testing That the HTTP Client Attaches the Right Bearer Token

A controller receiving an `OAuth2AuthorizedClient` may pass it to `WebClient`/`RestClient`. We need to test the **outgoing request**:

~~~text
GET /api/orders
Authorization: Bearer fake-access-token-for-web
~~~

and confirm the admin token is not used.

### 23.1. `WebClient` Servlet Integration

Spring Security provides:

~~~java
ServletOAuth2AuthorizedClientExchangeFilterFunction
~~~

for Servlet + `WebClient`. Once you have an `OAuth2AuthorizedClient`:

~~~java
import static org.springframework.security.oauth2.client.web
    .reactive.function.client
    .ServletOAuth2AuthorizedClientExchangeFilterFunction
    .oauth2AuthorizedClient;

String response = webClient.get()
    .uri("https://orders.example.test/api/orders")
    .attributes(oauth2AuthorizedClient(authorizedClient))
    .retrieve()
    .bodyToMono(String.class)
    .block();
~~~

Testing with a fake HTTP server or `ExchangeFunction` captures `Authorization` and asserts the right Bearer token.

### 23.2. Fake `ExchangeFunction` Pattern

~~~java
AtomicReference<String> authorization = new AtomicReference<>();

ExchangeFunction fakeExchange = request -> {
    authorization.set(
        request.headers().getFirst("Authorization"));
    return Mono.just(ClientResponse.create(HttpStatus.OK)
        .body("ok")
        .build());
};

WebClient webClient = WebClient.builder()
    .exchangeFunction(fakeExchange)
    .build();
~~~

This is a **test fragment**; attach the configured OAuth filter and mock authorized client to the request, or test a service that sets the header explicitly to isolate transport. After the request:

~~~java
assertThat(authorization.get())
    .isEqualTo("Bearer fake-access-token-for-web");
~~~

Never send requests to the real Internet in unit tests, and never use production tokens.

### 23.3. `RestClient` (Spring Security 6.4+)

`OAuth2ClientHttpRequestInterceptor` uses the manager; testing registration selection typically uses:

~~~java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver
    .clientRegistrationId;

restClient.get()
    .uri("/api/orders")
    .attributes(clientRegistrationId("portal-web"))
    .retrieve()
    .body(String.class);
~~~

This is a **different selection mechanism** from the controller annotation; test both when the application mixes them. You can use `MockRestServiceServer` or a custom `ClientHttpRequestFactory` to assert Bearer requests.

## 24. When to Use `@SpringBootTest` Instead of `@WebMvcTest`?

| Test approach | Best suited for |
|---|---|
 `@WebMvcTest` + fake registrations/repository | Testing MVC annotations, security filters, and responses |
 `@SpringBootTest` + `@AutoConfigureMockMvc` | Testing wiring of full application beans/managers/repositories |
 Unit-testing service + mock manager | Testing dynamic registration selection and permission checks |
 Fake IdP + fake downstream server | Testing token exchange/refresh/end-to-end HTTP integration |
 Browser E2E | Testing cookies, SameSite, redirects, and sessions across real browsers |

### 24.1. Full-Context Integration Test

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OAuth2ClientWiringIntegrationTest {
    @Autowired MockMvc mvc;
    @Autowired ClientRegistrationRepository registrations;
    @Autowired OAuth2AuthorizedClientRepository authorizedClients;
    // Test methods using test profile/fake IdP fixtures.
}
~~~

**Never use live production OIDC issuer discovery** in default tests. When `issuer-uri` is present in config, the framework fetches metadata while building `ClientRegistration`; use fake issuer/discovery or explicit endpoint fixtures in the test profile.

### 24.2. Test Slices May Omit Beans

`@WebMvcTest` loads only part of the context; if `OAuth2AuthorizedClientArgumentResolver`, `ClientRegistrationRepository`, or the manager is missing, tests fail before running business logic.

This is a **test wiring** issue, not proof that the production annotation is wrong.

## 25. MockMvc `standaloneSetup`: Requires the Resolver and Spring Security

If not using Boot's web test slice:

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new AuthorizedClientProbeController())
    .setCustomArgumentResolvers(
        new OAuth2AuthorizedClientArgumentResolver(manager))
    .apply(springSecurity(securityFilterChain))
    .build();
~~~

This is a **conceptual pattern**; `manager` and `securityFilterChain` must be wired compatibly with Spring Security Test APIs and your app. In standalone setup, the filter chain/security context/authorized-client repository may require manual registration. Never assume a bare `MockMvcBuilders.standaloneSetup(controller)` understands Spring Security annotations.

### 25.1. Why Is Full MVC Config Simpler?

With `@WebMvcTest` and `@Import(OAuth2MvcTestConfig.class)`, Spring MVC and security infrastructure are wired together consistently. Standalone setup suits very small tests, yet makes it easy to forget an argument resolver or filter chain.

### 25.2. `@WithMockUser` Does Not Register the Argument Resolver

`@WithMockUser` only prepares `Authentication` for the test; the resolver must still be registered by MVC configuration. If you see `IllegalStateException`, `No suitable resolver`, or parameter injection failures, inspect the wiring rather than just swapping mock users.

## 26. Negative Test: Missing Authorized Client

Suppose the browser is authenticated yet has not authorized `portal-admin`.

~~~text
Authentication: alice
Repository:
  (portal-web, alice) -> AT-W
  (portal-admin, alice) -> [missing]
~~~

When calling the controller:

~~~java
@RegisteredOAuth2AuthorizedClient("portal-admin")
OAuth2AuthorizedClient client
~~~

the manager may:

- Initiate an authorization code flow and redirect if a suitable web context/provider is present.
- Return `null` or throw an exception depending on grant/config.
- Use another provider chain if the registration is `client_credentials`.

**Do not hardcode "missing client always returns 404/401"** across every system. Write tests matching the **application's expected policy**, for example:

~~~text
No authorized client for portal-admin
  => Must not return portal-web's token
  => Must not call Admin API with WEB token
  => Can initiate authorization or return controlled error
~~~

### 26.1. Avoid False Successes

If a test merely asserts the controller returns a non-null string, it could accidentally accept a fallback token. Assert the exact registration ID and downstream Bearer token.

### 26.2. Invalid Registration ID

If an annotation uses:

~~~java
@RegisteredOAuth2AuthorizedClient("does-not-exist")
~~~

the resolver/manager cannot find the registration. Exact behavior depends on exception handling; tests must prove **no authorization succeeds and no other registration's token endpoint is called**.

## 27. Unauthenticated Requests: 401 or Redirect?

With `SecurityFilterChain`:

~~~java
.authorizeHttpRequests(auth -> auth
    .anyRequest().authenticated())
.oauth2Login(Customizer.withDefaults())
~~~

an unauthenticated request goes through `AuthenticationEntryPoint`; with browser login flow this may redirect to the login page. With a JSON API chain, it may return 401 per policy.

~~~java
@Test
void anonymousRequestIsNotAllowed() throws Exception {
    mvc.perform(get("/test/clients/web"))
        .andExpect(status().is3xxRedirection());
}
~~~

This test **matches only the sample chain above**; if the app configures an API entry point returning 401, the assertion must be `isUnauthorized()`.

### 27.1. Authentication and Authorized Client Are Two Layers

If a request is anonymous while carrying a fake `oauth2Client()` session token, the security chain can still block the endpoint for lacking authentication. Never treat an authorized client's presence as proof the browser is authenticated.

### 27.2. When Using `@WithMockUser`

`@WithMockUser` may pass the authentication gate, yet does not supply an OIDC principal, ID Token claims, or authorized-client state. Pick the fixture matching what the controller actually consumes.

## 28. 403 and CSRF: Avoid Confusing Them with Registration Errors

Example POST controller:

~~~java
@PostMapping("/api/orders")
public ResponseEntity<Void> submitOrder(
    @RegisteredOAuth2AuthorizedClient("portal-web")
    OAuth2AuthorizedClient client
) {
    // Business operation...
    return ResponseEntity.accepted().build();
}
~~~

With Spring Security CSRF protection for browser sessions:

~~~java
@Test
void postRequiresCsrf() throws Exception {
    mvc.perform(post("/api/orders")
        .with(oidcLogin()
            .clientRegistration(TestRegistrations.web())))
        .andExpect(status().isForbidden());
}
~~~

This can be a **403 caused by CSRF**, not a missing OAuth2 token.

Happy-path test:

~~~java
mvc.perform(post("/api/orders")
    .with(csrf())
    .with(oidcLogin()
        .clientRegistration(TestRegistrations.web())))
    .andExpect(status().isAccepted());
~~~

### 28.1. Should You Call `csrf.disable()` Just to Make Tests Pass?

No. If production uses sessions/cookies, CSRF is an independent defense. Tests must mirror production policy. Never disable CSRF app-wide to mask a missing CSRF request post-processor.

### 28.2. Roles and Scopes

A 403 may stem from `@PreAuthorize` or `hasAuthority(...)`, even when an authorized client exists. Tests must supply matching authorities on `Authentication` and keep them distinct from access token scopes when needed.

## 29. Testing Registration Selection with Multiple Principals and Tenants

A SaaS system:

~~~text
tenant acme:
  registration = portal-acme
  principal = acme-alice

tenant globex:
  registration = portal-globex
  principal = globex-alice
~~~

Even users with the same email must never cross-use authorized clients.

### 29.1. Testing the Identity Key

~~~text
Given:
  (portal-acme, acme-alice) -> AT-A
  (portal-globex, globex-alice) -> AT-G

When:
  ACME request needs portal-acme
Then:
  AT-A used

When:
  GLOBEX request needs portal-globex
Then:
  AT-G used
~~~

### 29.2. Never Trust a Query `registrationId`

If a controller reads `?registrationId=portal-globex` and picks GLOBEX's token without checking tenant membership, it risks cross-tenant credential usage.

Dynamic selection must rely on a trusted tenant registry and authorization before invoking the manager. Unit tests must verify an ACME user cannot pick the GLOBEX registration simply by changing a URL parameter.

### 29.3. Same Issuer Does Not Mean Shared Token

Two registrations can share a provider alias and issuer while having different client IDs and scopes. Assert both registration ID **and client ID**, not just the issuer URL.

## 30. Testing When the Logged-In Registration Differs from the API's Authorized Client

Scenario:

~~~text
Browser Authentication:
  OAuth2AuthenticationToken.registrationId = portal-web

AuthorizedClientRepository:
  (portal-web, alice) -> AT-W
  (portal-admin, alice) -> AT-A

Controller /api/audit:
  @RegisteredOAuth2AuthorizedClient("portal-admin")
~~~

Tests should verify the controller receives the ADMIN authorized client, while separate authorization ensures Alice is allowed to call audit.

### 30.1. Do Not Use `getAuthorizedClientRegistrationId()` Everywhere

`OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` identifies the **current login's** registration, not necessarily the right client for every downstream API.

With multiple registrations, you may need explicit selection:

~~~java
@RegisteredOAuth2AuthorizedClient("portal-admin")
~~~

or a service manager selecting the registration per trusted business policy.

### 30.2. Keep Default Selection and Explicit Selection Tests Independent

Never merge them into one ambiguous assertion. Write separate tests:

- Current registration follows the OIDC login context.
- Explicit registration remains WEB/ADMIN per the annotation.
- A missing explicit registration never falls back to the current login token.

## 31. What Can MockMvc NOT Verify?

MockMvc runs in a mock HTTP Servlet environment; things **not automatically verified** by `oauth2Client()` or `oidcLogin()`:

- Whether the OP actually accepts the client ID/secret and redirect URI.
- Whether an authorization code is genuinely exchanged for tokens.
- Whether ID Token signature/issuer/audience/nonce are verified against a real JWKS.
- Whether the browser enforces `SameSite`/`Secure`/`HttpOnly` cookie policies.
- Whether refresh tokens actually rotate/revoke.
- Whether the Resource Server actually trusts the access token.
- Whether token scopes/audience are issued by the AS per production policy.

**Mock fixtures isolate the code under test**; they do not prove the full Authorization Code/OIDC protocol.

### 31.1. Recommended Test Layers

~~~text
Unit:
  Dynamic selection, tenant/RBAC, manager invocation.

MockMvc:
  MVC argument resolver, login/authenticated context, session repository.

HTTP integration:
  Fake AS token endpoint, fake Resource Server, Authorization header.

Browser E2E:
  Redirect/callback cookies/state/CSRF across actual origins.
~~~

## 32. Troubleshooting: Controller Receives `null` or Cannot Find Client

| Symptom | Common cause | Investigation |
|---|---|---|
| Resolver ignores annotation | MVC/security argument resolver not registered | Check OAuth2 Client MVC config |
| `No bean of type ClientRegistrationRepository` | Test slice lacks OAuth2 client bean | Import fixture repository |
| Missing authorized client | `oauth2Login()` mocked yet registration mismatches | Configure `.clientRegistration(...)` |
| Missing authorized client despite calling `oauth2Client` | Test repo differs from app repo | Register `HttpSession` repo bean or seed the right store |
| Client returned with `principal=user` instead of `alice` | Default mock `principalName` | Call `.principalName("alice")` |
| Manager calls token endpoint in test | Token expired or no authorized client | Use future `expiresAt`, mock provider/endpoint |
| Test passes yet production uses wrong token | Client ID/Bearer header not asserted | Assert outbound requests |
| 302 instead of expected 200 | Login entry point or authorization redirect | Distinguish missing browser `Authentication` vs. client |
| 401 instead of 302 | API `AuthenticationEntryPoint` | Assert per real policy |
| 403 POST | Missing CSRF token or role | Add `.with(csrf())` and authorities |
| 404 wrong path | Controller/filter matcher mismatch | Check endpoint mappings |
| `registrationId=company-oidc` not found | Used provider alias instead of registration ID | Fix to `portal-web` |
| Tests depend on Internet/IdP | `issuer-uri` discovery | Use fake metadata/`ClientRegistration` |
| Client tests are flaky | Shared mutable sessions/stores across tests | Isolate data and reset state |
| Failed refresh deletes ADMIN token | Cleanup keyed by issuer alone | Key by registration + principal |
| Different principal under OIDC | Pairwise `sub`/custom name attribute | Align trusted `principalName` |

### 32.1. Debug Decision Tree

~~~text
@RegisteredOAuth2AuthorizedClient test failed
    |
    v
Does the endpoint hit the right SecurityFilterChain?
    |-- No -> check matchers / MockMvc springSecurity().
    |
    v
Is Authentication present?
    |-- No -> user()/oauth2Login()/oidcLogin().
    |
    v
Is the requested registration ID accurate?
    |-- No -> check annotation or trusted selector.
    |
    v
Does ClientRegistrationRepository contain that ID?
    |-- No -> check test fixture/profile.
    |
    v
Do the authorized-client repository and manager use the same store?
    |-- No -> seed the right HttpSession/service/custom store.
    |
    v
Does the client's principalName match Authentication?
    |-- No -> align fixture, never use raw user input.
    |
    v
Is the access token still valid (non-expired)?
    |-- No -> test refresh separately.
    |
    v
Does the controller receive the right registration/token?
    |-- No -> inspect resolver/manager selection.
    |
    v
Are downstream API authorization and Bearer header correct?
~~~

## 33. Anti-Patterns When Testing the Annotation

**1. Using `@WithMockUser` alone and expecting `OAuth2AuthorizedClient` to exist.** Mock authentication does not store tokens automatically.

**2. Testing with only a single registration.** Fails to catch client selection bugs when the app has multiple registrations.

**3. Giving two fixture clients the same `clientId`/scopes/token.** Tests cannot distinguish wrong-registration selection.

**4. Using a provider alias in the annotation.** `company-oidc` is not `portal-web`.

**5. Testing `tokenValue` via a production-style HTTP response.** Easily creates endpoints that leak Bearer credentials.

**6. Using expired tokens for every resolver test.** The manager may attempt refreshes outside the test's scope.

**7. Using MockMvc without Spring Security filters.** Tests lack a production-like `Authentication` context.

**8. Testing a different repository than production unknowingly.** A fake session repository can mask Redis/JDBC bugs.

**9. Asserting only HTTP 200.** Fails to prove registration, client ID, or principal correctness.

**10. Conflating current login registration with explicit API registration.** Makes it easy to send the wrong token to an API.

**11. Removing CSRF/security filters to make POST tests pass.** Does not reflect real policy.

**12. Using `jwt()` instead of an OAuth2 Client fixture.** Resource Server authentication differs from an authorized client.

**13. Accepting another user's/tenant's token in fixtures.** Creates false confidence in isolation.

**14. Calling a production IdP or using real client secrets in tests.** Non-deterministic and creates security risks.

**15. Letting a mock manager return any authorized client without asserting the requested `registrationId`.** Can hide dynamic selection bugs.

## 34. Practice Exercises

### Exercise 1 — Selecting the Right Registration

Controller has:

~~~java
@RegisteredOAuth2AuthorizedClient("portal-web")
OAuth2AuthorizedClient client
~~~

**Question:** If the fake repository only contains `portal-admin`, may the controller use the ADMIN token?

**Solution:** Never fall back implicitly. It must require WEB authorization per manager policy or fail with a controlled error/redirect; tests must reject using the ADMIN token.

### Exercise 2 — Is `@WithMockUser` Enough?

~~~java
@WithMockUser(username = "alice")
@Test
void test() { ... }
~~~

**Question:** Does an `OAuth2AuthorizedClient` for `portal-web` exist yet?

**Solution:** Not necessarily. `@WithMockUser` only creates `Authentication`; add `oauth2Client("portal-web")` or seed the repository properly.

### Exercise 3 — Using `oidcLogin()`

~~~java
.with(oidcLogin().clientRegistration(TestRegistrations.admin()))
~~~

**Question:** What is the current `OAuth2AuthenticationToken`'s registration?

**Solution:** `portal-admin`. If the annotation omits the ID and the resolver uses the current login context, tests expect the current authorized client to be ADMIN.

### Exercise 4 — Explicit Differs from Current

Browser logged in via ADMIN, while the controller annotation requests WEB.

**Question:** Which token should be selected?

**Solution:** The WEB authorized client granted to that principal per the annotation. Never pick the ADMIN token simply because the current `Authentication` is ADMIN.

### Exercise 5 — Principal Mismatch

~~~text
Authentication.name = alice
AuthorizedClient.principalName = bob
~~~

**Question:** May Bob's token be returned to Alice?

**Solution:** No. Test the expected fail-safe behavior per repository/manager policy; never take `principalName` from query parameters.

### Exercise 6 — Token Scopes

WEB configured scopes are `openid profile orders.read`; the mock access token only has `orders.read`.

**Question:** What does the controller see from `getAccessToken().getScopes()`?

**Solution:** Granted access token scopes, which do not necessarily equal configured scopes.

### Exercise 7 — Missing `HttpSession` Repo Bean

MockMvc uses `oauth2Client()`, while the MVC resolver uses a custom JDBC repository.

**Question:** Why is the client not found?

**Solution:** The post-processor seeds the token into the test session repo, whereas the app resolver queries JDBC. Either seed the production store or wire a compatible `HttpSession` repo bean in the test.

### Exercise 8 — CSRF and 403

A POST endpoint returns 403 even with `oidcLogin()` and the right token.

**Question:** What should you check first?

**Solution:** Security rules, CSRF token (`.with(csrf())`), and roles/authorities. Never blame all 403s on a missing OAuth token.

### Exercise 9 — Multi-Tenancy

ACME and GLOBEX share an issuer, have different registration IDs, and both have username `alice`.

**Question:** What is the minimal isolation test?

**Solution:** Distinct token/key fixtures, membership authorization, exact registration checks, and verifying no cross-use of access tokens or resource data.

### Exercise 10 — What Does MockMvc Prove?

An `oidcLogin()` test passes and the controller receives the expected registration ID.

**Question:** Does that prove the production OP issues valid tokens?

**Solution:** No. MockMvc does not exchange codes, verify ID Token/AS signatures, or test browser cookies; separate fake-AS integration or staging E2E tests are required.

## 35. Checklist Before Finalizing the Servlet Test Suite

| Question | What to confirm |
|---|---|
| Correct annotation/argument type? | `@RegisteredOAuth2AuthorizedClient OAuth2AuthorizedClient` |
| Explicit or implicit annotation? | Test both behaviors accordingly |
| Are registration IDs unique? | Distinct WEB/ADMIN IDs |
| Is the provider alias confused? | No |
| Do test `ClientRegistration`s have distinct client IDs? | Yes |
| Are fixture tokens distinct and non-expired? | Yes on happy paths |
| Does `principalName` match `Authentication`? | Yes |
| Does MockMvc include Spring Security filters? | Yes |
| Is the MVC argument resolver registered? | Yes |
| Does the test authorized-client repo match the manager? | Yes |
| Is `oauth2Client()` used for authorized-client state? | Yes |
| Are `oauth2Login()`/`oidcLogin()` used for proper `Authentication`? | Yes |
| Is `@WithMockUser` never treated as an authorized-client fixture? | Confirmed |
| Does web endpoint test pick WEB? | Assert registration ID/client ID |
| Does admin endpoint test pick ADMIN? | Assert registration ID/client ID |
| Does current-registration test follow login? | Yes |
| Is explicit selection differing from current login tested? | Yes |
| Is missing client verified not to fall back wrongly? | Yes |
| Is user principal isolation tested? | Yes |
| Is tenant registration isolation tested? | Yes if multi-tenant |
| Are granted scopes tested? | Yes |
| Are expired tokens/refresh tested separately? | Yes if app uses refresh |
| Is the outgoing Bearer header tested? | Yes when controller calls APIs |
| Are 401/403/CSRF tested per security chain? | Yes |
| Does test setup avoid calling production IdP? | Yes |
| Are real secrets/tokens kept out of CI? | Yes |
| Are test data/sessions isolated? | Yes |
| Are browser cookie/E2E tests separate? | Yes if callbacks need coverage |

## 36. References

- **Testing OAuth 2.0 (Servlet MockMvc)**: `https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html`
- **Authorized Client Features** and annotation resolver: `https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorized-clients.html`
- **Core OAuth2 Client classes**: `https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/core.html`

When upgrading Spring Security versions, check the exact API of `SecurityMockMvcRequestPostProcessors`, the argument resolver, and manager wiring in your project's version.

## 37. Summary

`@RegisteredOAuth2AuthorizedClient` lets Spring MVC inject an `OAuth2AuthorizedClient` by **registration ID**. Because the resolver uses `OAuth2AuthorizedClientManager`, testing requires more than creating `Authentication`: you must ensure the **authorized-client repository, registration, principal, and token context** all align.

In MockMvc, `oauth2Client("portal-web")` is the most focused way to put a fake authorized client into the session; `oauth2Login()` and `oidcLogin()` simulate `Authentication` and can link a corresponding authorized client. `@WithMockUser` only simulates basic `Authentication` and does not create an OAuth2 authorized client. If the manager uses a custom repository or JDBC, tests must seed **the exact store the resolver reads from**.

For applications with multiple registrations, the highest-value tests prove **the WEB token is never picked in place of the ADMIN token, principal Alice cannot read Bob's token, and tenant A never uses tenant B's token**. Assert registration ID, client ID, principal, scopes, and outgoing Bearer headers where appropriate; keep refresh, consent, and IdP protocol testing separate from MVC argument resolution tests. That keeps registration selection tests crystal clear while preserving OAuth2/OIDC and authorization boundaries.
