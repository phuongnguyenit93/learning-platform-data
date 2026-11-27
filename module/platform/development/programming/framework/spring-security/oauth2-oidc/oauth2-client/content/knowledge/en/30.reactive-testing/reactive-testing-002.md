# 30.2. mockOAuth2Login() for Endpoints Requiring an OAuth 2.0 User

## 1. Context: Testing WebFlux Endpoints Without a Real IdP Login

Suppose an **Employee Portal** is written with **Spring Boot 3, Spring WebFlux, and Spring Security OAuth 2.0 Client**. Users sign in at an Authorization Server (AS), then access:

~~~http
GET /api/me HTTP/1.1
Host: portal.example.test
~~~

The controller needs to retrieve the current OAuth 2.0 user information:

~~~java
@GetMapping("/api/me")
public Mono<UserView> me(@AuthenticationPrincipal OAuth2User user) {
    return Mono.just(new UserView(
        user.getName(),
        user.getAttribute("name")));
}
~~~

In production, the application may go through:

~~~text
Browser
  -> GET /oauth2/authorization/employee
  -> Authorization Server login/consent
  -> GET /login/oauth2/code/employee?code=...&state=...
  -> Spring Security exchanges the code for a token
  -> creates Authentication in SecurityContext
  -> GET /api/me
~~~

However, to test the WebFlux controller logic, we **do not need** every test to:

- Open a browser to the IdP.
- Enter a password.
- Execute the Authorization Code Flow.
- Call real token/UserInfo/JWK endpoints.
- Store cookies/tokens from a production login.

Spring Security Test provides **`mockOAuth2Login()`**, a dedicated `WebTestClientConfigurer` that places a **mock OAuth2 `Authentication`** onto the exchange under test.

~~~java
webTestClient
    .mutateWith(mockOAuth2Login())
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
~~~

Important point: **the test above gives the endpoint a mock authenticated OAuth2 principal**, and **does not prove** that a real IdP, callback, token endpoint, or signature validation works.

> Lesson scope: Spring Security 6, Spring WebFlux, JUnit 5, `WebTestClient`, and `SecurityMockServerConfigurers.mockOAuth2Login()`. Do not use Servlet's `SecurityMockMvcRequestPostProcessors.oauth2Login()`: the two test stacks have separate APIs. All identities/tokens/hosts below are fake data.

## 2. Learning Objectives

After completing this lesson, you should be able to:

1. Understand what `mockOAuth2Login()` simulates and what it does not simulate.
2. Recognize `OAuth2User`, `OAuth2AuthenticationToken`, and `ReactiveSecurityContextHolder` types.
3. Configure `WebTestClient` with Spring Security for WebFlux.
4. Test endpoints requiring login and compare against requests without `Authentication`.
5. Create a principal with `sub`, `name`, `email`, or custom claims.
6. Verify roles/authorities separately from OAuth user attributes.
7. Verify the OAuth2 login registration ID.
8. Distinguish `mockOAuth2Login()` from `mockOidcLogin()`, `mockJwt()`, and `mockUser()`.
9. Test reactive method security and CSRF for session-based APIs.
10. Separate login principal tests from `OAuth2AuthorizedClient`, `WebClient` token forwarding, and real OAuth2 protocol tests.
11. Write negative tests for principal, registration, tenant, and access permissions.
12. Diagnose 302/401/403 errors, missing `SecurityWebFilterChain`, or incorrect `WebTestClient` setup.

## 3. Architecture and Role of `mockOAuth2Login()`

~~~mermaid
flowchart TD
    T["JUnit 5 test"] --> W["WebTestClient"]
    M["mockOAuth2Login()"] --> W
    W --> S["Spring Security WebFilterChain"]
    S --> C["WebFlux Controller"]
    C --> P["OAuth2User / OAuth2AuthenticationToken"]
    C --> B["Reactive Business Service"]
    AS["Real Authorization Server / IdP"] -. "Not called in mock-login tests" .-> M
~~~

There is no real token exchange step in this type of test. Instead of supplying credentials in a browser, the test attaches a test-valid `SecurityContext` to the WebFlux exchange.

### 3.1. What Is Mocked

`mockOAuth2Login()` can create:

- An `OAuth2AuthenticationToken`.
- An `OAuth2User` as the principal.
- OAuth2 user attributes/authorities for the controller and authorization layer to read.
- Registration context for the `Authentication`.

### 3.2. What Is Not Automatically Verified

It does not automatically verify:

- That a real user entered the correct password at the IdP.
- That the Authorization Server signed an ID Token or issued a valid access token.
- That `state`, `nonce`, and PKCE were validated across the callback.
- That the OIDC discovery/JWKS response is actually valid.
- Whether browser cookies have proper `SameSite` or `Secure` attributes.
- That a downstream Resource Server accepted a Bearer token.
- That refresh token rotation works.

**Mocked `Authentication` is an input that the test deliberately trusts**, used to isolate and verify code that runs after authentication.

## 4. From OAuth2 Login to `SecurityContext` in WebFlux

An `OAuth2AuthenticationToken` contains:

~~~text
principal: OAuth2User
authorities: Collection<GrantedAuthority>
authorizedClientRegistrationId: String
authenticated: true
~~~

A controller can accept:

~~~java
@AuthenticationPrincipal OAuth2User user
~~~

or:

~~~java
Authentication authentication
~~~

or in reactive style:

~~~java
Mono<Principal> principal
~~~

Depending on WebFlux method argument resolvers, `Authentication` is usually a `Principal` subtype. Inside a Reactor pipeline, Spring Security also provides:

~~~java
ReactiveSecurityContextHolder.getContext()
~~~

to read the `SecurityContext` from the Reactor context.

### 4.1. `OAuth2User` Is Not `OAuth2AuthorizedClient`

Distinguish between:

| Type | Role |
|---|---|
| `OAuth2User` | Attributes, name, and authorities of the logged-in user |
| `OAuth2AuthenticationToken` | Current `Authentication` and registration ID |
| `ClientRegistration` | Configuration of an OAuth client |
| `OAuth2AuthorizedClient` | Access/refresh tokens issued for a registration/principal |
| `ReactiveOAuth2AuthorizedClientService` | Stores authorized clients in the Reactive stack |

**Having an `OAuth2User` does not mean you already have a usable access token for every API**. This is a very important boundary when writing tests.

## 5. Sample Dependencies for Spring Boot WebFlux

With Gradle Kotlin DSL:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.x.x"
    id("io.spring.dependency-management") version "1.x.x"
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

`3.x.x` and `1.x.x` are placeholders: in a real project, use compatible versions rather than copying placeholders verbatim to run Gradle. The Spring Boot BOM normally manages versions of Spring Security, Reactor, and Spring Framework.

### 5.1. Do Not Confuse with the Servlet Starter

If the application only needs the WebFlux Reactive stack, do not add `spring-boot-starter-web` (Spring MVC) to the test classpath without a reason. If both MVC and WebFlux are on the classpath, Spring Boot auto-configuration may select the Servlet web application type.

### 5.2. Import `mockOAuth2Login()` Correctly

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;
~~~

**Do not use the Servlet import:**

~~~java
// Do not use in WebTestClient:
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oauth2Login;
~~~

This is a common mistake when copying code from a Servlet testing chapter into a Reactive one.

## 6. Sample Controller Requiring `OAuth2User`

Create a controller that returns only safe data:

~~~java
package com.example.portal.web;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ProfileController {

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
        @AuthenticationPrincipal OAuth2User user
    ) {
        String displayName = user.getAttribute("name");

        return Mono.just(Map.of(
            "subject", user.getName(),
            "displayName",
            displayName != null ? displayName : user.getName()
        ));
    }
}
~~~

When the browser has completed a valid OAuth2 login, Spring WebFlux injects `user` from the current `Authentication`. Tests will provide a mock `OAuth2User`.

### 6.1. Why Not Return All Attributes?

`OAuth2User.getAttributes()` may contain email, avatar URL, or other personal information. In a production API, do not return all attributes by default; select only allowed fields.

### 6.2. Why Does the Controller Return `Mono`?

WebFlux favors Reactive types when an asynchronous pipeline is needed. When simply mapping an already-available principal, `Mono.just(...)` is just a simple example and performs no HTTP network or blocking I/O.

## 7. `SecurityWebFilterChain` for the Sample Endpoints

~~~java
package com.example.portal.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication
    .HttpStatusServerEntryPoint;

@Configuration
@EnableWebFluxSecurity
public class PortalSecurityConfig {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
        ServerHttpSecurity http
    ) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/admin/report")
                    .hasAuthority("ROLE_ADMIN")
                .pathMatchers("/api/**").authenticated()
                .anyExchange().permitAll()
            )
            .oauth2Login(Customizer.withDefaults())
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusServerEntryPoint(HttpStatus.UNAUTHORIZED))
            )
            .build();
    }
}
~~~

This configuration has the following characteristics:

- `/api/public`: public.
- `/api/admin/report`: requires `ROLE_ADMIN`.
- Remaining `/api/**` routes: require authentication.
- For unauthenticated API calls, returns **401** instead of automatically redirecting to a login page.
- `oauth2Login()` enables OAuth2 login support in the Reactive filter chain.

**The 401 entry point is a choice for this illustrative API**, not the default for every application. If your application serves browser pages, you may want a login redirect; tests must assert the actual contract.

### 7.1. Tests Still Need the Real Chain to Verify 401/403

If you only call the controller directly:

~~~java
controller.me(fakeUser)
~~~

you only test method logic, without verifying `SecurityWebFilterChain`. `WebTestClient` attaches the appropriate security filter chain to test authenticated/denied paths.

### 7.2. `oauth2Login()` May Require `ClientRegistrationRepository`

In a test context enabling OAuth2 login, Spring Security may need a `ReactiveClientRegistrationRepository` to build the filters. Use a fake registration in the test profile; avoid issuer discovery calling a production IdP just to stand up the test application context.

## 8. Controller for Both Registration and `Authentication`

To inspect which registration context the mock creates, add an endpoint:

~~~java
package com.example.portal.web;

import java.security.Principal;
import java.util.Map;
import org.springframework.security.oauth2.client.authentication
    .OAuth2AuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class LoginContextController {

    @GetMapping("/api/login-context")
    public Mono<Map<String, String>> context(
        Mono<Principal> principal
    ) {
        return principal
            .cast(OAuth2AuthenticationToken.class)
            .map(auth -> Map.of(
                "registrationId",
                auth.getAuthorizedClientRegistrationId(),
                "principalName",
                auth.getName()
            ));
    }
}
~~~

The `/api/login-context` path is a probe for this lesson. In a real app, expose only necessary data; never return a client secret, refresh token, or raw access token.

### 8.1. Current Login Registration Differs from API Token

`OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()` reports the registration of the **current `Authentication`**. It does not prove the application already holds an authorized client of another registration to call a Resource Server.

## 9. Fake `ClientRegistration` for Testing Without an IdP

Create a fixture:

~~~java
package com.example.portal.test;

import org.springframework.security.oauth2.client.registration
    .ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

public final class TestClientRegistrations {
    private TestClientRegistrations() {}

    public static ClientRegistration employee() {
        return ClientRegistration
            .withRegistrationId("employee")
            .clientId("employee-test-client")
            .clientSecret("test-secret-not-production")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                "{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("profile", "orders.read")
            .authorizationUri(
                "https://idp.example.test/oauth2/authorize")
            .tokenUri(
                "https://idp.example.test/oauth2/token")
            .userInfoUri(
                "https://idp.example.test/userinfo")
            .userNameAttributeName("sub")
            .clientName("Employee OAuth2 Test Client")
            .build();
    }

    public static ClientRegistration admin() {
        return ClientRegistration
            .withRegistrationId("admin")
            .clientId("admin-test-client")
            .clientSecret("admin-test-only-secret")
            .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri(
                "{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("profile", "audit.read")
            .authorizationUri(
                "https://idp.example.test/oauth2/authorize")
            .tokenUri(
                "https://idp.example.test/oauth2/token")
            .userInfoUri(
                "https://idp.example.test/userinfo")
            .userNameAttributeName("sub")
            .clientName("Admin OAuth2 Test Client")
            .build();
    }
}
~~~

Both registrations share the same Authorization Server URI but differ in:

- Registration ID.
- Client ID.
- Test secret.
- Requested scopes.

There is no need to use real client credentials or call the token endpoint in mock-login tests.

### 9.1. Why Not Use the OIDC `openid` Scope Here?

This example tests **`OAuth2User`** with `mockOAuth2Login()`. With OIDC, the application typically receives `OidcUser` and an ID Token; when you want to test those structures, use `mockOidcLogin()` as shown in the comparison section.

### 9.2. A Registration Fixture Is Not an Authorized Client/Token Fixture

`ClientRegistration` only describes an OAuth client. Creating this fixture does not automatically provide a real access token; `mockOAuth2Login()` is used to construct the test's authentication state.

## 10. Fake `OAuth2User` with Explicit Identity and Authorities

Do not let tests depend on the mock's default name/attributes if assertions need specific values. Create users:

~~~java
package com.example.portal.test;

import java.util.List;
import java.util.Map;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;

public final class TestOAuth2Users {
    private TestOAuth2Users() {}

    public static OAuth2User aliceEmployee() {
        return new DefaultOAuth2User(
            List.of(new SimpleGrantedAuthority("ROLE_EMPLOYEE")),
            Map.of(
                "sub", "employee-001",
                "name", "Alice Nguyen",
                "email", "alice@example.test",
                "department", "orders"
            ),
            "sub"
        );
    }

    public static OAuth2User aliceAdmin() {
        return new DefaultOAuth2User(
            List.of(
                new SimpleGrantedAuthority("ROLE_EMPLOYEE"),
                new SimpleGrantedAuthority("ROLE_ADMIN")
            ),
            Map.of(
                "sub", "employee-001",
                "name", "Alice Nguyen",
                "email", "alice@example.test"
            ),
            "sub"
        );
    }
}
~~~

`DefaultOAuth2User(..., "sub")` selects `sub` as the name attribute, so:

~~~java
user.getName(); // "employee-001"
~~~

Authorities are placed into `Authentication`, used for `hasAuthority()` or `hasRole()`.

### 10.1. Email Is Not a Mandatory Name Attribute

A provider might use `id`, `sub`, or another configured attribute as the principal name. Tests must match the actual contract; do not assume email is an immutable identifier.

### 10.2. Authorities Are Not Automatically Derived from Arbitrary Attributes

A fake user having:

~~~json
{"roles": ["ADMIN"]}
~~~

does not mean Spring Security will automatically generate `ROLE_ADMIN`. You need an authority mapper in the application or configure the appropriate test `GrantedAuthority`.

## 11. Writing Your First Test with `WebTestClient`

Import:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;
~~~

A test can be written as:

~~~java
@Test
void meRequiresAnOauth2User() {
    webTestClient
        .mutateWith(
            mockOAuth2Login()
                .oauth2User(TestOAuth2Users.aliceEmployee())
        )
        .get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.subject").isEqualTo("employee-001")
        .jsonPath("$.displayName").isEqualTo("Alice Nguyen");
}
~~~

This is the core test pattern of this lesson:

1. `mockOAuth2Login()` builds an OAuth2 `Authentication` for the exchange.
2. `.oauth2User(...)` supplies a principal with explicit attributes/authorities.
3. `mutateWith(...)` applies the configuration to the test client/exchange.
4. `WebFilterChain` evaluates authentication.
5. MVC-style method argument? **No**: this is a WebFlux controller, where the reactive argument resolver injects `OAuth2User`.
6. Assertions verify the response generated from the principal.

### 11.1. Writing a Failing Test When Unauthenticated

~~~java
@Test
void meWithoutAuthenticationReturns401() {
    webTestClient
        .get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

The `401` assertion matches the **sample `SecurityWebFilterChain` configured with a 401 entry point**. If the application defaults to redirecting browsers to `/login`, adjust the assertion accordingly; do not hard-code 401 for every OAuth2 login app.

### 11.2. Use Explicit Fixtures Instead of the Default User

A test with just:

~~~java
mockOAuth2Login()
~~~

may suffice to pass `.authenticated()`, but when you need to distinguish principals/roles/tenants, provide a concrete fake user.

## 12. Setting Up `@WebFluxTest` with `WebTestClient`

For a controller slice:

~~~java
package com.example.portal.web;

import com.example.portal.test.TestOAuth2Users;
import com.example.portal.test.TestClientRegistrations;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;

@WebFluxTest(
    controllers = {ProfileController.class, LoginContextController.class}
)
@Import(ReactiveOAuth2TestConfig.class)
class ProfileControllerWebFluxTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void authenticatedEmployeeCanReadOwnProfile() {
        webTestClient
            .mutateWith(mockOAuth2Login()
                .oauth2User(TestOAuth2Users.aliceEmployee())
                .clientRegistration(TestClientRegistrations.employee()))
            .get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.subject").isEqualTo("employee-001");
    }
}
~~~

`ReactiveOAuth2TestConfig` is the test configuration in the next section; import additional service mocks if controllers have dependencies.

### 12.1. Fake `ReactiveClientRegistrationRepository` in Tests

~~~java
package com.example.portal.web;

import com.example.portal.test.TestClientRegistrations;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.registration
    .ReactiveClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration
    .InMemoryReactiveClientRegistrationRepository;

@TestConfiguration
public class ReactiveOAuth2TestConfig {

    @Bean
    ReactiveClientRegistrationRepository testRegistrations() {
        return new InMemoryReactiveClientRegistrationRepository(
            TestClientRegistrations.employee(),
            TestClientRegistrations.admin()
        );
    }
}
~~~

With this configuration, WebFlux/Spring Security has registrations for `employee` and `admin` without real discovery.

### 12.2. Is the Security Chain Loaded in `@WebFluxTest`?

A slice test loads only part of the application context. If `PortalSecurityConfig` is not included in the `@WebFluxTest` context, you need to import it:

~~~java
@Import({
    ReactiveOAuth2TestConfig.class,
    PortalSecurityConfig.class
})
~~~

In a real project, avoid creating **two** unintended `SecurityWebFilterChain` beans; if Boot auto-configuration provides a default chain, tests must know which chain is actually in effect.

### 12.3. Slice or Full Context?

`@WebFluxTest` is suitable for testing WebFlux controllers and limited security integration. If you want to verify wiring of the entire reactive OAuth2 Client, database/token store, custom success handlers, or `WebClient` manager, consider `@SpringBootTest` with fake dependencies.

## 13. `@SpringBootTest` + `@AutoConfigureWebTestClient`

When you need to boot the full context:

~~~java
package com.example.portal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive
    .AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOAuth2Login;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class OAuth2LoginReactiveIntegrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void meIsVisibleForMockOauth2Principal() {
        webTestClient
            .mutateWith(mockOAuth2Login())
            .get()
            .uri("/api/me")
            .exchange()
            .expectStatus().isOk();
    }
}
~~~

**Note:** `mockOAuth2Login()` works best when `WebTestClient` is bound **in-process** to the Spring WebFlux application context or `WebHandler` via Spring Security test hooks.

If you use `RANDOM_PORT` / `bindToServer()` to send HTTP over TCP to another app process, a mock test configurer in the test JVM is **not** a browser authentication credential transmitted over the network. Do not assume `mutateWith(mockOAuth2Login())` automatically authenticates the server on the other end. For network E2E tests, use a fake IdP, a session/login flow, or a controlled test-only server mechanism.

### 13.1. Why Pay Attention to `WebApplicationType`?

If the application starts as Spring MVC Servlet instead of Reactive, `@AutoConfigureWebTestClient` may not apply as expected. Ensure the classpath and Boot web application type match WebFlux; do not use `WebTestClient` mutators to replace `MockMvc` in Servlet tests.

## 14. Manually Binding `WebTestClient` with Spring Security

You can also set up the client without Boot auto-configuration:

~~~java
@Autowired
ApplicationContext applicationContext;

WebTestClient client;

@BeforeEach
void setUp() {
    client = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(springSecurity())
        .configureClient()
        .build();
}
~~~

Static import:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
~~~

Then:

~~~java
client
    .mutateWith(mockOAuth2Login())
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
~~~

### 14.1. `.apply(springSecurity())` and `.mutateWith(mockOAuth2Login())` Are Different

`springSecurity()` integrates the security `WebFilterChain`/filters into a `WebTestClient` bound to the application.

`mockOAuth2Login()` prepares the `Authentication` principal for the test request.

**Mutating login without security filters in a custom `WebTestClient` setup** can cause requests to bypass authorization logic compared to production.

### 14.2. No Need to Manually Populate `SecurityContextHolder` `ThreadLocal`

The reactive `SecurityContext` lives in the Reactor context attached to the publisher/exchange. Do not do:

~~~java
SecurityContextHolder.getContext().setAuthentication(authentication);
~~~

and assume it will propagate correctly through every reactive chain. Use `mockOAuth2Login()` or Spring Security's reactive test mechanisms.

## 15. Quickly Customizing OAuth2 User Attributes

Besides passing an entire `OAuth2User`:

~~~java
.oauth2User(TestOAuth2Users.aliceEmployee())
~~~

you can customize attributes on the mock:

~~~java
webTestClient
    .mutateWith(mockOAuth2Login()
        .attributes(attributes -> {
            attributes.put("sub", "employee-002");
            attributes.put("name", "Bob Tran");
            attributes.put("department", "finance");
        }))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.subject").isEqualTo("employee-002")
    .jsonPath("$.displayName").isEqualTo("Bob Tran");
~~~

This is a useful shortcut when a controller only needs a few attributes.

### 15.1. Distinguish Attribute Name from Principal Name

Not every attribute is used as `OAuth2User.getName()`. The user name is determined by `userNameAttributeName` on `DefaultOAuth2User`/provider configuration or the fake mutator.

If a test requires an exact `principalName`, use `.oauth2User(new DefaultOAuth2User(...))` with an explicit name attribute.

### 15.2. Missing Attributes Are an Important Case

If a provider does not return `name`, the controller needs a fallback or intentional handling:

~~~java
String name = user.getAttribute("name");
String display = name != null ? name : user.getName();
~~~

Write a test with a fake user missing `name` and expect `displayName = subject`, avoiding `NullPointerException` or leaking internal errors.

### 15.3. Untrusted Input When Rendering Output

A provider may return a `name` containing special HTML/Unicode characters. JSON serialization normally encodes per the JSON contract, but the frontend must escape output appropriately for its context. A mock user can include special characters in `name` to test UI/frontend handling separately.

## 16. Customizing OAuth2 User Authorities

An endpoint:

~~~java
@GetMapping("/api/admin/report")
public Mono<Map<String, String>> adminReport() {
    return Mono.just(Map.of("result", "report-ready"));
}
~~~

protected by:

~~~java
.pathMatchers(HttpMethod.GET, "/api/admin/report")
    .hasAuthority("ROLE_ADMIN")
~~~

Test user without permission:

~~~java
@Test
void employeeCannotReadAdminReport() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .get()
        .uri("/api/admin/report")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Test user with permission:

~~~java
@Test
void adminCanReadAdminReport() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(TestOAuth2Users.aliceAdmin()))
        .get()
        .uri("/api/admin/report")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.result").isEqualTo("report-ready");
}
~~~

### 16.1. Customizing Directly via `authorities()`

Spring Security Test also provides a way to set authorities on the mock:

~~~java
.mutateWith(mockOAuth2Login()
    .authorities(
        new SimpleGrantedAuthority("ROLE_ADMIN")
    ))
~~~

In complex tests, creating a `DefaultOAuth2User` with a defined list of authorities is an easy way to keep identity and permission fixtures consistent.

### 16.2. `hasRole` vs `hasAuthority`

~~~java
.hasRole("ADMIN")
~~~

usually expects the authority `ROLE_ADMIN`, whereas:

~~~java
.hasAuthority("ADMIN")
~~~

expects the literal `ADMIN`.

If a test returns 403 even though the mock has `ADMIN`, check the prefix/authority mapping instead of arbitrarily adding scopes.

### 16.3. `GrantedAuthority` Is Not OAuth Scopes Issued by the AS

Mock authorities help test application authorization logic. However, they do not prove that a real Authorization Server granted `admin.read` or that a Resource Server accepts that token. You must test bearer access tokens/claims separately when business logic calls APIs.

## 17. Checking the `registrationId` of a Mock Login

Suppose the `/api/login-context` endpoint returns the current registration ID.

~~~java
@Test
void loginContextUsesEmployeeRegistration() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .clientRegistration(TestClientRegistrations.employee())
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .get()
        .uri("/api/login-context")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.registrationId").isEqualTo("employee")
        .jsonPath("$.principalName").isEqualTo("employee-001");
}
~~~

If the test uses the ADMIN registration:

~~~java
@Test
void loginContextUsesAdminRegistration() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .clientRegistration(TestClientRegistrations.admin())
            .oauth2User(TestOAuth2Users.aliceAdmin()))
        .get()
        .uri("/api/login-context")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.registrationId").isEqualTo("admin");
}
~~~

### 17.1. Registration ID Is Login Context, Not a Role

Someone who logs in via a registration named `admin` **does not automatically have `ROLE_ADMIN`**. Business policy must check authorities, membership, scopes, and resource ownership separately.

### 17.2. Same OP Does Not Mean Same Registration

~~~text
employee -> https://idp.example.test
admin    -> https://idp.example.test
~~~

Two registrations can share the same issuer/token endpoint while using different client IDs and scopes. Tests should verify the selected registration, not merely the matching issuer.

### 17.3. Do Not Hard-Code the Default Registration

If `.clientRegistration(...)` is not called, the test mutator may use a default test registration. Do not assert that the default always equals a production registration name. When you need to verify the ID, supply an explicit fixture.

## 18. Testing When `OAuth2User` Lacks a Required Attribute

An endpoint may require `department` for business logic:

~~~java
@GetMapping("/api/department")
public Mono<Map<String, String>> department(
    @AuthenticationPrincipal OAuth2User user
) {
    String value = user.getAttribute("department");
    if (value == null || value.isBlank()) {
        return Mono.just(Map.of("status", "missing-department"));
    }
    return Mono.just(Map.of("department", value));
}
~~~

Test:

~~~java
@Test
void missingDepartmentGetsControlledResponse() {
    OAuth2User withoutDepartment = new DefaultOAuth2User(
        List.of(new SimpleGrantedAuthority("ROLE_EMPLOYEE")),
        Map.of("sub", "employee-001"),
        "sub"
    );

    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(withoutDepartment))
        .get()
        .uri("/api/department")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.status").isEqualTo("missing-department");
}
~~~

This is an example of testing **application logic with potentially missing attributes**, not validating the OIDC protocol.

### 18.1. Do Not Assume Every Provider Supplies Email

OAuth2 UserInfo attributes can vary greatly across providers. Email may not be provided or may be unverified; do not use email to identify users when a stable key is needed.

### 18.2. When the App Requires Profile Completeness

If a required attribute is missing and app policy rejects the request, test HTTP 422/403 per contract rather than forcing every mock user to contain all fields. The goal is to cover real business branches.

## 19. Testing `@AuthenticationPrincipal` and the Reactor `SecurityContext`

An endpoint can read `Authentication` directly from the Reactive context:

~~~java
package com.example.portal.web;

import java.util.Map;
import org.springframework.security.core.context
    .ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ReactiveContextController {

    @GetMapping("/api/reactive-auth")
    public Mono<Map<String, String>> authContext() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication())
            .map(auth -> Map.of(
                "principal", auth.getName(),
                "authenticated",
                Boolean.toString(auth.isAuthenticated())
            ));
    }
}
~~~

Test:

~~~java
@Test
void reactiveContextCarriesOauth2Login() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .get()
        .uri("/api/reactive-auth")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.principal").isEqualTo("employee-001")
        .jsonPath("$.authenticated").isEqualTo("true");
}
~~~

### 19.1. Why Not Use `SecurityContextHolder` in a Reactive Pipeline?

`SecurityContextHolder` is tied to a thread-based context in Servlet. Reactor can switch schedulers/threads. If reactive code reads `ThreadLocal` as its sole source, it may fail to find the `Authentication`.

**`ReactiveSecurityContextHolder` or method argument injection** is the better approach in WebFlux.

### 19.2. Testing Reactor Context Propagation

If a business service uses `publishOn`/`subscribeOn`, tests should ensure the security context propagates through the framework-supported Reactor context. Do not build tests by mutating global static authentication between tests.

## 20. Testing Reactive Method Security with `mockOAuth2Login()`

If the application uses:

~~~java
@EnableReactiveMethodSecurity
~~~

then the method:

~~~java
@PreAuthorize("hasAuthority('ROLE_ADMIN')")
public Mono<String> generateReport() {
    return Mono.just("report-ready");
}
~~~

is checked when the publisher method is invoked under Reactive method security configuration.

### 20.1. Testing via `WebTestClient`

If a controller calls the service:

~~~java
@GetMapping("/api/admin/report-from-service")
public Mono<String> report() {
    return reportService.generateReport();
}
~~~

Test with insufficient permissions:

~~~java
webTestClient
    .mutateWith(mockOAuth2Login()
        .oauth2User(TestOAuth2Users.aliceEmployee()))
    .get()
    .uri("/api/admin/report-from-service")
    .exchange()
    .expectStatus().isForbidden();
~~~

Test with sufficient permissions:

~~~java
webTestClient
    .mutateWith(mockOAuth2Login()
        .oauth2User(TestOAuth2Users.aliceAdmin()))
    .get()
    .uri("/api/admin/report-from-service")
    .exchange()
    .expectStatus().isOk();
~~~

Precondition: the test context must enable `@EnableReactiveMethodSecurity`, the service bean must be Spring-proxied, and the method must be called through the proxy. If the service is completely mocked, annotations on the real service will not execute.

### 20.2. Note on `Publisher` Return Types

Reactive method security typically applies to `Mono`/`Flux` and supported reactive signatures. Do not assume `@PreAuthorize` on a blocking method running outside the Reactor context always has equivalent semantics.

### 20.3. Test Roles Do Not Prove a Real User Has That Role

`mockOAuth2Login()` supplies test-defined authorities. It tests authorization logic, not that production mapping from IdP claims to `ROLE_ADMIN` is correct. Mapping needs separate tests.

## 21. CSRF with POST Endpoints Using Browser Sessions

With WebFlux OAuth2 Login, browsers typically use a session cookie. State-changing requests require CSRF protection per policy.

Example:

~~~java
@PostMapping("/api/settings")
public Mono<Map<String, String>> save(
    @AuthenticationPrincipal OAuth2User user
) {
    return Mono.just(Map.of("savedFor", user.getName()));
}
~~~

If Spring Security CSRF is enabled, a POST even with a mock login can still return 403:

~~~java
@Test
void postWithoutCsrfFails() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .post()
        .uri("/api/settings")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

To test the happy path, use the Reactive CSRF test mutator:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
~~~

~~~java
@Test
void postWithCsrfAndOauthLoginSucceeds() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .mutateWith(csrf())
        .post()
        .uri("/api/settings")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.savedFor").isEqualTo("employee-001");
}
~~~

### 21.1. 403 Does Not Automatically Mean Missing OAuth2 Authorization

`WebFilterChain` may return 403 due to:

- Missing CSRF token.
- Authenticated user lacking a role/authority.
- Tenant/resource policy denial.
- Custom authorization manager denial.

Check the request method, CSRF setup, and authorization rules before concluding the fake `OAuth2User` is wrong.

### 21.2. Do Not Disable CSRF Just to Make Tests Pass

`csrf.disable()` may make sense in certain stateless bearer-token APIs with their own threat model, but it should not be disabled indiscriminately just because browser session/CSRF tests take effort to write.

## 22. Testing Anonymous Requests and Mock `OAuth2Login` on the Same Endpoint

A pair of tests:

~~~java
@Test
void anonymousCannotReadProfile() {
    webTestClient
        .get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isUnauthorized();
}

@Test
void oauth2PrincipalCanReadProfile() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .get()
        .uri("/api/me")
        .exchange()
        .expectStatus().isOk();
}
~~~

This tests the `.authenticated()` rule on the `WebFilterChain` with the sample 401 API entry point.

### 22.1. You May See 302 Instead of 401

If `SecurityWebFilterChain` routes unauthenticated browsers to the OAuth login entry point, anonymous tests may receive `302` to `/login` or the login URL. The assertion is not "always 401", but **according to the actual `SecurityWebFilterChain` contract**.

### 22.2. Do Not Omit the Security Chain in Tests

If anonymous requests also receive 200, check:

~~~text
Does WebTestClient have .apply(springSecurity())?
Is SecurityWebFilterChain loaded?
Is the endpoint outside securityMatcher/path matchers?
Is the controller test bound directly without filters?
~~~

A controller test without filters does not prove the endpoint is protected.

## 23. Comparing `mockOAuth2Login()` and `mockOidcLogin()`

This is a central distinction:

| Feature | `mockOAuth2Login()` | `mockOidcLogin()` |
|---|---|---|
| Test stack | WebFlux `WebTestClient` | WebFlux `WebTestClient` |
| Principal | `OAuth2User` | `OidcUser` |
| Authentication | `OAuth2AuthenticationToken` | `OAuth2AuthenticationToken` |
| ID Token object | Does not target OIDC ID Token creation | Can customize `OidcIdToken` |
| UserInfo claims | `OAuth2User` attributes | OIDC claims/UserInfo |
| Used for | Generic OAuth2 Login | OpenID Connect login |
| Actually calls AS | No | No |
| Right when controller requires `OidcUser` | Should not be used | Yes |

### 23.1. Do Not Use `mockOAuth2Login()` When the Controller Requires `OidcUser`

Controller:

~~~java
@GetMapping("/api/oidc-sub")
public Mono<String> subject(
    @AuthenticationPrincipal OidcUser user
) {
    return Mono.just(user.getSubject());
}
~~~

The test should use:

~~~java
.mutateWith(mockOidcLogin()
    .idToken(token -> token.claim("sub", "oidc-user-001")))
~~~

with import:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;
~~~

### 23.2. Neither Mock Verifies Signatures

`mockOidcLogin()` creates a test `OidcUser`/claims without exchanging codes or validating an ID Token signature over the network. To test real OIDC validation, use a fake OIDC Provider/JWKS/token endpoint integration.

### 23.3. `OAuth2User` and `OidcUser` Do Not Equal an `AccessToken`

An OIDC ID Token is a token for client authentication, whereas an access token is used to call Resource Servers. Do not send a raw ID Token as a Bearer token to an API just because a mock OIDC login succeeded.

## 24. Comparing with `mockJwt()` and `mockOpaqueToken()`

An application can act as both:

~~~text
OAuth2 Login Client:
  Browser -> WebFlux app -> IdP

Resource Server:
  API consumer -> WebFlux app with Bearer token
~~~

The two request models are different:

| Test mutator | Primary `Authentication` | Suitable for |
|---|---|---|
| `mockOAuth2Login()` | `OAuth2AuthenticationToken` | Browser OAuth2 login |
| `mockOidcLogin()` | `OAuth2AuthenticationToken` + `OidcUser` | Browser OIDC login |
| `mockJwt()` | `JwtAuthenticationToken` | Resource Server accepting JWT Bearer |
| `mockOpaqueToken()` | `BearerTokenAuthentication` | Resource Server accepting opaque tokens |
| `mockUser()` | `UsernamePasswordAuthenticationToken` | Username/password style authentication |

### 24.1. Can `mockJwt()` Be Used for an Endpoint Requiring `OAuth2User`?

`JwtAuthenticationToken.getPrincipal()` is usually not an `OAuth2User`, so `@AuthenticationPrincipal OAuth2User` may receive `null` or a mismatched type. Always use the mutator matching the **`Authentication` type** the endpoint expects.

### 24.2. Two Different Security Chains

A WebFlux app may:

- Use session + OAuth2 Login for `/ui/**`.
- Use stateless JWT bearer auth for `/api/external/**`.

Tests must use the right mutator and match the chain's matcher/entry point. Do not use `mockOAuth2Login()` as a substitute for a Resource Server JWT validation test.

## 25. How Does `@WithMockUser` Differ from `mockOAuth2Login()`?

`@WithMockUser` or its reactive test setup equivalent provides an `Authentication` with a username and authorities, but **does not create `OAuth2User` attributes**.

If the controller accepts:

~~~java
@AuthenticationPrincipal OAuth2User user
~~~

then `mockOAuth2Login()` is a better fit.

If the controller only requires:

~~~java
Principal principal
~~~

or a `.authenticated()` rule, several `Authentication` types may pass; however, tests should reflect real OAuth2 login.

### 25.1. Tests That Look Right but Have a Different Principal from Production

An endpoint doing:

~~~java
OAuth2AuthenticationToken token =
    (OAuth2AuthenticationToken) authentication;
~~~

will fail if the test only builds a `UsernamePasswordAuthenticationToken`. This helps catch tests that are "too fake" and miss OAuth2-specific conditions.

## 26. `mockOAuth2Login()` Does Not Replace `mockOAuth2Client()`

In a Reactive OAuth2 Client, the application also has:

~~~java
ReactiveOAuth2AuthorizedClientService
ServerOAuth2AuthorizedClientRepository
ReactiveOAuth2AuthorizedClientManager
OAuth2AuthorizedClient
~~~

Many tests need an **access token for downstream APIs**, not just the logged-in principal.

### 26.1. Two Distinct Test Goals

**Test A — endpoint requiring an OAuth2 user:**

~~~text
Input: OAuth2User / OAuth2AuthenticationToken
Target: @AuthenticationPrincipal, RBAC, reactive SecurityContext
Tool: mockOAuth2Login()
~~~

**Test B — endpoint using an authorized client to call an API:**

~~~text
Input: registrationId + authorized client + access token
Target: reactive authorized-client repository/manager, WebClient Bearer
Tool: mockOAuth2Client() if supported by version,
      or seed/mock the right repository/service/manager
~~~

Reactive OAuth2 Client hooks/tests depend on the Spring Security version and authorized-client integration. Whether using a mutator or a fake manager, tests must verify the right registration, principal, and token.

### 26.2. Mock Login Is Not Proof That `OAuth2AuthorizedClient` Exists

`mockOAuth2Login()` primarily sets `Authentication` on the reactive exchange; you must not infer that a production `ServerOAuth2AuthorizedClientRepository` or JDBC/Redis authorized-client store already contains a real token just because a `mockOAuth2Login()` test passed.

### 26.3. When Testing `@RegisteredOAuth2AuthorizedClient` in WebFlux

Reactive WebFlux has its own integration for authorized-client resolution, distinct from Servlet MVC. When a method needs an authorized client:

~~~text
Controller authorized-client argument
  -> resolver / manager / repository
  -> registration/principal matching
  -> token
~~~

tests need to configure the actual authorized-client store/manager used by the resolver; not just fake an `OAuth2User`.

## 27. Testing Outbound `WebClient` Tokens Separately from Mock Login

Suppose a controller calls the Orders API using a token from the authorized-client manager:

~~~text
Browser authenticated via employee registration
  -> WebFlux controller
  -> ReactiveOAuth2AuthorizedClientManager
  -> WebClient Bearer access token
  -> Orders API
~~~

`mockOAuth2Login()` only handles the **Browser authenticated** part. To test the `Authorization` header:

1. Use a fake `ReactiveOAuth2AuthorizedClientManager` or seed the repository/service.
2. Create a dedicated fake access token for `employee`.
3. Use a fake downstream HTTP server or `ExchangeFunction`.
4. Assert the exact `Authorization: Bearer <test-token>`.
5. Assert no token from `ADMIN` or another tenant is present.

### 27.1. Fake Token Example

~~~java
Instant now = Instant.now();
OAuth2AccessToken token = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "fake-employee-access-token",
    now.minusSeconds(5),
    now.plusSeconds(600),
    Set.of("orders.read")
);
~~~

This is a fake token and does not need a JWT signature because the test is examining outbound HTTP behavior.

### 27.2. Fake Manager with Mockito

~~~java
ReactiveOAuth2AuthorizedClientManager manager =
    mock(ReactiveOAuth2AuthorizedClientManager.class);

OAuth2AuthorizedClient client = new OAuth2AuthorizedClient(
    TestClientRegistrations.employee(),
    "employee-001",
    token
);

when(manager.authorize(any(OAuth2AuthorizeRequest.class)))
    .thenReturn(Mono.just(client));
~~~

**Mocking only the return value is not enough** if the test's goal is registration selection. The test must capture `OAuth2AuthorizeRequest` to assert the requested registration ID and principal. Moreover, `ReactiveOAuth2AuthorizedClientManager.authorize(...)` accepts `OAuth2AuthorizeRequest` and returns `Mono<OAuth2AuthorizedClient>`; do not use the synchronous Servlet manager.

### 27.3. Do Not Reuse the Current Login's Token in Place of the API Registration

A user may sign in with `employee` yet need a different authorized client for an Admin API. Business code must select the registration per policy; do not assume from the current `Authentication` that every API uses the same token.

## 28. Multiple Registrations: Testing `employee` and `admin` Separately

The `/api/login-context` controller returns the login registration.

Test:

~~~java
@Test
void employeeLoginHasEmployeeRegistration() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .clientRegistration(TestClientRegistrations.employee())
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .get()
        .uri("/api/login-context")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.registrationId").isEqualTo("employee");
}

@Test
void adminLoginHasAdminRegistration() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .clientRegistration(TestClientRegistrations.admin())
            .oauth2User(TestOAuth2Users.aliceAdmin()))
        .get()
        .uri("/api/login-context")
        .exchange()
        .expectStatus().isOk()
        .expectBody()
        .jsonPath("$.registrationId").isEqualTo("admin");
}
~~~

### 28.1. Do Not Assume the `admin` Registration Means `ROLE_ADMIN`

A very useful negative test:

~~~java
@Test
void adminRegistrationWithoutAdminAuthorityStillGets403() {
    webTestClient
        .mutateWith(mockOAuth2Login()
            .clientRegistration(TestClientRegistrations.admin())
            .oauth2User(TestOAuth2Users.aliceEmployee()))
        .get()
        .uri("/api/admin/report")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

Selecting the registration named `admin` does not prove the user has admin permissions. Authorization is based on verified roles/permissions.

### 28.2. Same Issuer Does Not Allow Merging Identities

If two registrations share an OpenID Provider, `OAuth2User` attributes can still differ due to scopes/UserInfo permissions. Tests should not assume all attributes or roles are identical.

### 28.3. Pairwise Subject in OIDC

When switching to OIDC, `sub` can be pairwise per sector/client. Never auto-link accounts solely by email. A mock OAuth2 principal does not verify these properties; identity mapping tests require fixtures matching the IdP's contract.

## 29. Multi-Tenant Testing with Mock Login

In a SaaS app:

~~~text
tenant acme:
  registrationId = portal-acme
  user sub = acme-user-42

tenant globex:
  registrationId = portal-globex
  user sub = globex-user-42
~~~

Tests can create two `OAuth2User` and `ClientRegistration` fixtures. However, a **tenant supplied by the browser** must still be verified server-side.

### 29.1. Do Not Trust an Unmapped Tenant Claim

If a fake test user contains:

~~~json
{"tenant": "globex"}
~~~

that is merely test input. Business authorization must map the identity to an active membership. Test case:

~~~text
Authenticated ACME user
Request candidate tenant = globex
Expect denied unless active GLOBEX membership and proper login grant
~~~

### 29.2. Isolation Testing per Principal

Two users with the same display name or email:

~~~text
ACME Alice: sub=A-42
GLOBEX Alice: sub=G-42
~~~

must not automatically share a session/authorized client. Tests should assert denied cross-tenant access, not just `200` responses for the two tenants individually.

### 29.3. A Registration Is Not a Tenant Policy

A registration ID may map to a tenant, but the application still needs membership/resource authorization. Do not use `getAuthorizedClientRegistrationId()` as sole proof that a user is permitted to read every tenant record.

## 30. Testing Across Scheduler Switches: Reactive Context Is Preserved

Suppose a business service does:

~~~java
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .publishOn(Schedulers.boundedElastic());
}
~~~

A `WebTestClient + mockOAuth2Login` test should still observe the correct user if context is propagated by Reactor:

~~~java
webTestClient
    .mutateWith(mockOAuth2Login()
        .oauth2User(TestOAuth2Users.aliceEmployee()))
    .get()
    .uri("/api/reactive-auth")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.principal").isEqualTo("employee-001");
~~~

### 30.1. Do Not Access `ThreadLocal` After `subscribeOn()`

Bad pattern:

~~~java
String username =
    SecurityContextHolder.getContext()
        .getAuthentication()
        .getName();
~~~

in a Reactive pipeline may find no `Authentication` or pick up another thread's context. Use `ReactiveSecurityContextHolder` or method arguments instead.

### 30.2. Do Not Use `block()` on the Event Loop

Test code can use `StepVerifier` or `WebTestClient` assertions to drive reactive publishers. In WebFlux runtime, `block()` on an event loop is an anti-pattern. Mock login does not make blocking code non-blocking.

## 31. `StepVerifier` Unit Testing Services with Reactive `SecurityContext`

When HTTP/`WebFilterChain` is not needed, you can unit test a service reading the context:

~~~java
Authentication authentication = new OAuth2AuthenticationToken(
    TestOAuth2Users.aliceEmployee(),
    TestOAuth2Users.aliceEmployee().getAuthorities(),
    "employee"
);

Mono<String> result = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication)
    );

StepVerifier.create(result)
    .expectNext("employee-001")
    .verifyComplete();
~~~

`StepVerifier` comes from Reactor Test, usually included in the Spring Boot starter test dependency set. When you need to test HTTP endpoints, still use `WebTestClient.mutateWith(mockOAuth2Login())` for full wiring.

### 31.1. Why Not Use `mockOAuth2Login()` in Plain `StepVerifier`?

`mockOAuth2Login()` is a **`WebTestClient`** configurer, not a direct Reactor `Context` for arbitrary publishers. Service unit tests can populate `SecurityContext` directly using `ReactiveSecurityContextHolder.withAuthentication()`.

### 31.2. Two Complementary Testing Levels

~~~text
StepVerifier:
  Unit test reactive service + explicit Authentication Context.

WebTestClient:
  HTTP routing + SecurityWebFilterChain + controller argument resolution.
~~~

Do not completely replace one with the other.

## 32. Handling Wrong `Authentication` Types

Controller:

~~~java
@GetMapping("/api/oauth2-only")
public Mono<String> oauth2Only(Mono<Principal> principal) {
    return principal
        .cast(OAuth2AuthenticationToken.class)
        .map(OAuth2AuthenticationToken::getAuthorizedClientRegistrationId);
}
~~~

With `mockOAuth2Login()`, the cast succeeds.

With `mockJwt()`, the cast can fail because the `Authentication` principal is `JwtAuthenticationToken`, not `OAuth2AuthenticationToken`.

### 32.1. Should Production Code Cast Blindly?

If the endpoint is truly only for the OAuth2 login flow, configure the chain so only compatible `Authentication` types enter. If the route is used by both OAuth2 login and Bearer clients, use:

~~~java
if (authentication instanceof OAuth2AuthenticationToken oauth) {
    // OAuth2 login case.
} else {
    // Explicit fallback/error for different auth type.
}
~~~

to avoid unexpected `ClassCastException`s.

### 32.2. Negative Test for Auth Type

Verify the endpoint returns a controlled 4xx/5xx per API contract rather than a stack trace. Do not confuse a type-casting programming bug with an invalid token.

## 33. Mock Login Does Not Prove `SecurityContext` Survives Across Two HTTP Requests

Each call to:

~~~java
webTestClient.mutateWith(mockOAuth2Login())
~~~

gives the test exchange a fake `Authentication`.

This **does not automatically prove** a session cookie is created, persisted, and sent back on the next request as in a production browser.

### 33.1. Test Session Persistence Separately

If the app uses `WebSessionServerSecurityContextRepository` or Spring Session, you need an integration test covering:

- Login callback/session creation (with a fake AS if needed).
- Session ID cookie.
- Second request sending the cookie.
- Session expiry/invalidation.
- Multi-node/shared session store behavior.

Mock mutators bypass those network/protocol steps.

### 33.2. `SameSite`/`Secure`/`HttpOnly` Must Be Tested at the Browser/Cookie Layer

`WebTestClient` can inspect `Set-Cookie` headers, but it does not fully simulate cross-site browser cookie enforcement. OIDC callback `SameSite` testing should use browser E2E with the corresponding origins/proxy.

### 33.3. Do Not Store Mock Credentials in Production Storage

Test mocks and authorized-client fixtures use fake tokens; never put real client secrets or reuse production session cookies in CI logs.

## 34. Mock Login and the OAuth2 Callback: Testing Boundaries

A real E2E login may follow:

~~~mermaid
sequenceDiagram
    actor Browser as Browser
    participant App as Reactive Spring Security Client
    participant OP as OpenID Provider

    Browser->>App: GET /oauth2/authorization/employee
    App-->>Browser: 302 to OP, state/nonce/PKCE request
    Browser->>OP: Authenticate and authorize
    OP-->>Browser: Redirect code + state
    Browser->>App: GET /login/oauth2/code/employee?code=...&state=...
    App->>OP: POST /token with code
    OP-->>App: Access token/ID token or OAuth error
    App-->>Browser: Create session and redirect
    Browser->>App: GET /api/me with session cookie
~~~

A `mockOAuth2Login()` test starts right at the final step:

~~~text
Assume OAuth2AuthenticationToken exists.
Test GET /api/me authorization and controller behavior.
~~~

### 34.1. What Should You Do to Test the Callback?

Use a fake Authorization Server/OP to test:

- Authorization request URI/client ID/scopes.
- `state` correlation.
- PKCE, nonce, and redirect URI.
- Token response parsing and ID Token validation.
- Session/cookie persistence.
- Provider error callbacks.

Do not treat `mockOAuth2Login` success as proof that production callback handling works.

### 34.2. JWKS/Issuer Testing Still Requires an Integration Layer

`mockOAuth2Login()` does not verify JWT signatures. For OIDC, validate JWK Set/issuer/audience/nonce in integration tests with a fake OP/JWKS rather than disabling validation to make tests pass easily.

## 35. Testing Logic Based on `OAuth2User.getAttributes()`

Business rule:

~~~java
public Mono<Boolean> isOrdersDepartment(OAuth2User user) {
    String department = user.getAttribute("department");
    return Mono.just("orders".equals(department));
}
~~~

Tests can cover:

~~~text
user A: department = orders -> true
user B: department = finance -> false
user C: missing department -> false
~~~

### 35.1. Do Not Treat Unverified User Attributes as Roles

If the business layer treats `department` as authorization evidence, verify that the attribute comes from a trusted provider/mapping and is permitted by policy. A mock user can hold anything; test input alone does not prove production data is trusted.

### 35.2. Distinguish Identity Data from Permissions

`preferred_username`, `name`, or `email` are identity/profile data, not necessarily access permissions. Authorities/roles are produced by mapping/authorization policy and may depend on the tenant.

## 36. Testing Error Handling and 401/403

States to distinguish:

| Scenario | Category | Expected behavior per sample chain |
|---|---|---|
| Anonymous `GET /api/me` | Unauthenticated | 401 |
| Mock `OAuth2User` `GET /api/me` | Authenticated | 200 |
| Employee `GET /api/admin/report` | Missing `ROLE_ADMIN` | 403 |
| Admin `GET /api/admin/report` | Has `ROLE_ADMIN` | 200 |
| Employee `POST /api/settings` without CSRF | CSRF denied | 403 |
| Employee `POST /api/settings` with CSRF | Authenticated + valid CSRF | 200 |
| Mock JWT hitting endpoint casting `OAuth2AuthenticationToken` | Authentication type mismatch | Controlled error per API policy |
| Mock `OAuth2User` missing attribute required by business logic | Business validation | Controlled response/error |

### 36.1. Do Not Attribute Every 403 to "Missing Scope"

403 can result from CSRF, missing role/authority, tenant authorization, or resource ownership. In tests, inspect the security config and method authorization instead of arbitrarily changing token scopes.

### 36.2. Avoid Login Redirect Loops on 401

If a WebFlux app serves browser pages, `AuthenticationEntryPoint` may redirect; a JSON API may return 401. Tests should reflect route-specific policy so the frontend does not repeatedly follow unexpected login redirects.

## 37. Testing Wrong Provider / Mismatched Registration

With two `ClientRegistration`s:

~~~text
employee: client ID employee-test-client
admin:    client ID admin-test-client
~~~

A test verifying the login context:

~~~java
webTestClient
    .mutateWith(mockOAuth2Login()
        .clientRegistration(TestClientRegistrations.employee())
        .oauth2User(TestOAuth2Users.aliceEmployee()))
    .get()
    .uri("/api/login-context")
    .exchange()
    .expectBody()
    .jsonPath("$.registrationId").isEqualTo("employee");
~~~

Still **does not guarantee** that the downstream `OAuth2AuthorizedClientManager` will select the `employee` registration when calling the Orders API.

### 37.1. Selecting the Authorized Client Separately

If the application uses the Reactive `WebClient` OAuth2 filter, test business service selection with a fake manager/repository and assert `OAuth2AuthorizeRequest.clientRegistrationId`, rather than only looking at `OAuth2AuthenticationToken.registrationId`.

### 37.2. Multiple Distinct Providers

If `employee` and `admin` use two different issuers, `mockOAuth2Login` can still construct both `Authentication`s because it performs no issuer verification. Testing the issuer trust boundary requires integration tests of the callback/ID Token, not just mock registrations.

## 38. Best Practices to Avoid Flaky Tests

1. Create **immutable fake users** or independent fixture objects; do not mutate shared maps across tests.
2. Use **explicit registration IDs** instead of relying on default mock values.
3. Construct test `ClientRegistration`s directly so tests never reach out to the Internet.
4. For controllers needing `OAuth2User`, use `mockOAuth2Login()`, not `mockJwt()` out of habit.
5. For controllers needing `OidcUser`/ID Token claims, use `mockOidcLogin()`.
6. For CSRF-protected POSTs, use `csrf()` instead of disabling CSRF.
7. For role tests, authority fixtures should explicitly specify `ROLE_*`.
8. Assert both **anonymous denied** and **authenticated success**.
9. Avoid calling a real IdP/token endpoint in unit/slice tests.
10. Test storage/manager separately if an endpoint uses downstream authorized clients.
11. Never store mock `Authentication` in a `ThreadLocal` static shared across tests.
12. Never put real production access tokens/secrets into fixtures.
13. If multiple test classes share an application context, do not mutate global state recklessly.
14. When testing 401/403, know which `SecurityWebFilterChain` is matching.
15. Separate unit business assertions from Spring Security wiring assertions for faster diagnosis.

## 39. Troubleshooting When `mockOAuth2Login` Does Not Work

| Symptom | Likely cause | How to fix |
|---|---|---|
| Method `mockOAuth2Login` not found | Missing `spring-security-test` or wrong import | Use `SecurityMockServerConfigurers` |
| Compile error using `.with(...)` | Copied from Servlet `MockMvc` | `WebTestClient` uses `.mutateWith(...)` |
| Mock login still gets 401 | Security configurer/filter chain not integrated | Check `springSecurity()` and reactive chain |
| Anonymous still gets 200 | Missing or mismatched security chain | Check `WebFilterChain`/path matchers |
| `OAuth2User` not injected | Wrong `Authentication` type | Use `mockOAuth2Login()`, matching controller signature |
| `OidcUser` is null | Used `mockOAuth2Login` instead of OIDC mock | Use `mockOidcLogin()` |
| Principal name differs from expected | Default name/name attribute | Use `DefaultOAuth2User(..., "sub")` |
| 403 even though login succeeded | Missing authority or CSRF | Check `ROLE_*` and `csrf()` |
| Test requires admin but fake user is employee | Authority mapping mismatch | Set authorities per policy |
| Different registration ID | Forgot `.clientRegistration(...)` | Use explicit fixture |
| OIDC issuer metadata load error | `issuer-uri` triggers discovery | Use fake `ClientRegistration`/IdP |
| Test passes but JWT Resource Server fails | Mock login does not test bearer validation | Use `mockJwt`/fake JWT validation integration |
| Authorized client missing | Mock login only handles `Authentication` | Seed the Reactive authorized-client repository/service |
| `WebClient` sends wrong Bearer token | Wrong registration selection/manager | Capture outgoing request and manager input |
| Test loses `SecurityContext` across schedulers | Wrong `ThreadLocal` usage | Use `ReactiveSecurityContextHolder`/context propagation |
| Port-based HTTP test ignores mock login | Mock mutator does not send auth over TCP | Bind in-process or run a fake real login flow |
| POST test skips CSRF policy | Security chain not applied or CSRF disabled | Check filter chain & CSRF config |
| Test shows HTML login instead of JSON 401 | Browser login `AuthenticationEntryPoint` | Configure API entry point, assert actual behavior |

### 39.1. Debugging Decision Tree

~~~text
WebFlux test with mockOAuth2Login failed
    |
    v
WebTestClient is bound in-process with springSecurity()?
    |-- No -> fix client binding.
    |
    v
SecurityWebFilterChain active and matching endpoint?
    |-- No -> import/configure reactive security.
    |
    v
mockOAuth2Login() mutator applied?
    |-- No -> use mutateWith().
    |
    v
Endpoint expects OAuth2User or OidcUser?
    |-- OidcUser -> mockOidcLogin().
    |
    v
OAuth2User name/attributes correct?
    |-- No -> use explicit DefaultOAuth2User.
    |
    v
Authorities satisfy rules?
    |-- No -> configure ROLE_* authority.
    |
    v
POST/PUT/DELETE requires CSRF?
    |-- Yes -> mutateWith(csrf()).
    |
    v
Registration context correct?
    |-- No -> clientRegistration(fixture).
    |
    v
Does endpoint also need OAuth2AuthorizedClient/token?
    |-- Yes -> seed/mock reactive manager/repository separately.
    |
    v
Review controller assertion and relevant HTTP security policy.
~~~

## 40. Anti-Patterns to Avoid

**1. Using OAuth2 Login mocks instead of verifying the callback.** Mocks do not send real code/token requests.

**2. Importing `SecurityMockMvcRequestPostProcessors.oauth2Login()` into WebFlux.** Wrong test stack.

**3. Assuming `mockOAuth2Login()` automatically creates an OIDC ID Token.** Use `mockOidcLogin()` for `OidcUser`/ID Token claims.

**4. Assuming you already have an authorized client access token for every API.** `Authentication` and authorized-client state are separate.

**5. Asserting only 200 in tests.** Assert principal name, safe attributes, and registration/role when relevant.

**6. Using default authorities/names without knowing their values.** Create explicit fixtures.

**7. Using `mockJwt()` to test `@AuthenticationPrincipal OAuth2User`.** Resource Server authentication differs from OAuth2 Login.

**8. Disabling CSRF to make POST tests pass.** Hides a protection layer for browser sessions.

**9. Using a global `ThreadLocal` for `Authentication` in Reactor.** Can lose context or leak into other tests.

**10. Using a live IdP/client secret in unit tests.** Non-deterministic and risks leaking secrets.

**11. Believing a `WebTestClient` mutator is sent over TCP to another server.** Mocks only affect the test-bound exchange.

**12. Conflating registration ID with role.** Logging in via the `admin` registration does not grant admin permissions.

**13. Conflating name/email with stable user identity.** They can change or collide.

**14. Assuming mock success means signature/JWKS validation passed.** Protocol integration tests are required.

**15. Not testing anonymous/denied cases.** The happy path alone does not prove security policy.

## 41. Hands-On Exercises

### Exercise 1 — Testing an Authenticated User

A controller requires `@AuthenticationPrincipal OAuth2User`.

**Question:** Which mutator should you use in `WebTestClient`?

**Answer hint:** `mockOAuth2Login()` from `SecurityMockServerConfigurers`. Apply `.mutateWith(mockOAuth2Login())` before the request.

### Exercise 2 — Testing Unauthenticated Requests

Endpoint `/api/me` is protected with `.authenticated()` and an HTTP 401 entry point.

**Question:** What does a request without mock login return?

**Answer:** `401 Unauthorized` per the chosen chain. With a different browser login redirect chain, it may be `302`; do not apply one status blindly across all configurations.

### Exercise 3 — Changing the Principal Name

You want to test `user.getName() == "employee-42"`.

**Answer:** Supply a `DefaultOAuth2User` with attribute `sub=employee-42` and `userNameAttributeName="sub"`, then call `.oauth2User(user)`.

### Exercise 4 — Testing 403

The user has `ROLE_EMPLOYEE`, and the endpoint requires `ROLE_ADMIN`.

**Question:** Do you need to change token scopes to test this?

**Answer:** No. The security rule checks `GrantedAuthority` in this example; give the fake `OAuth2User` the corresponding role authority. Verify `403` for employee and `200` for admin.

### Exercise 5 — Choosing Registration

The app has registrations `employee` and `admin`.

**Question:** How do you verify the current login registration?

**Answer:** `mockOAuth2Login().clientRegistration(TestClientRegistrations.employee())`, call the endpoint reading `OAuth2AuthenticationToken.getAuthorizedClientRegistrationId()`, and assert `employee`.

### Exercise 6 — API Requiring `OidcUser`

The controller accepts `@AuthenticationPrincipal OidcUser` and calls `getIdToken()`.

**Question:** Should you use `mockOAuth2Login()`?

**Answer:** Use `mockOidcLogin()`, not the generic `OAuth2User` mock.

### Exercise 7 — CSRF

`POST /api/settings` with mock login returns 403.

**Question:** What should you check first?

**Answer:** CSRF protection and authorization rules. With browser session CSRF enabled, use `.mutateWith(csrf())` for the happy-path test.

### Exercise 8 — Resource Server JWT Endpoint

The endpoint requires a bearer JWT via `oauth2ResourceServer().jwt()`.

**Question:** Does `mockOAuth2Login()` test this properly?

**Answer:** It does not reflect `JwtAuthenticationToken`/Resource Server behavior. Use `mockJwt()` or a fake JWT decoder validation integration test.

### Exercise 9 — `WebClient` Calling the Orders API

Mock login passes, but `WebClient` has no access token.

**Question:** Why?

**Answer:** Authentication mocking and `OAuth2AuthorizedClient` token storage are two separate layers. You must mock/seed the `ReactiveOAuth2AuthorizedClientManager` or repository/service and assert the outgoing `Authorization` header.

### Exercise 10 — Browser E2E

Mock tests passed `/api/me`, but the production OAuth callback fails with `invalid_state`.

**Question:** Could the mock test have caught this?

**Answer:** No. `mockOAuth2Login()` bypasses the authorization request/callback/`state`. You need fake IdP protocol integration/browser E2E tests to verify it.

### Exercise 11 — Multi-Tenant

ACME and GLOBEX share an issuer, with different registration IDs and memberships.

**Question:** Does a mock user claim `tenant=globex` automatically grant GLOBEX access?

**Answer:** No. The application must verify active membership and registration/token context per tenant; test cross-tenant denial separately.

### Exercise 12 — `WebTestClient` Connecting to a Real Server

A test uses `bindToServer()` to a remote app process.

**Question:** Does `mutateWith(mockOAuth2Login())` make the remote server authenticated?

**Answer:** Not by default. The mutator is an in-process test hook, not an OAuth credential over TCP; you need a real login/fake OP or an appropriate test server mechanism.

## 42. Checklist Before Completing Reactive Mock-Login Tests

| Question | Requirement |
|---|---|
| Correct WebFlux stack? | Yes |
| Correct `mockOAuth2Login` import? | `SecurityMockServerConfigurers` |
| `spring-security-test` declared? | Yes |
| `WebTestClient` integrated with Spring Security? | Yes |
| `SecurityWebFilterChain` active? | Yes |
| Test `ClientRegistration` needs no live IdP? | Yes |
| `OAuth2User` has the right name attribute? | Yes |
| Attributes needed by the controller are provided? | Yes |
| Authorities are explicit per RBAC? | Yes |
| Anonymous denied is tested? | Yes |
| Authenticated allowed is tested? | Yes |
| Employee lacking admin role gets 403 is tested? | Yes |
| Admin with role is allowed is tested? | Yes |
| Explicit registration ID is tested? | Yes when multiple clients exist |
| `OAuth2User` and `OidcUser` are distinguished? | Yes |
| ID Token claims tests use `mockOidcLogin`? | Yes if OIDC is involved |
| JWT Resource Server tests use `mockJwt`? | Yes if Bearer JWT is involved |
| POST requests are tested for CSRF? | Yes |
| `ReactiveSecurityContextHolder` is used properly? | Yes if services need context |
| No global `ThreadLocal` used in Reactor? | Correct |
| Production AS is not called in tests? | Correct |
| Mock login is not treated as token exchange? | Correct |
| Authorized-client manager/store tested separately? | Yes when calling APIs |
| Outgoing Bearer token is verified? | Yes if app sends tokens |
| Negative tests for principal/registration/tenant exist? | Yes when needed |
| Separate tests exist for callbacks/real cookies? | Yes if production requires them |
| Tests do not leak tokens/secrets? | Correct |

## 43. Summary

`mockOAuth2Login()` is the core tool of **Spring Security Test for Reactive WebFlux** to test endpoints requiring an **OAuth 2.0 logged-in user**. When combining:

~~~java
webTestClient
    .mutateWith(mockOAuth2Login()
        .oauth2User(fakeOAuth2User)
        .clientRegistration(testRegistration))
    .get()
    .uri("/api/me")
    .exchange()
    .expectStatus().isOk();
~~~

we can verify `WebFilterChain`, `@AuthenticationPrincipal OAuth2User`, `OAuth2AuthenticationToken`, registration ID, reactive security context, roles/authorities, and response behavior **without a real IdP**.

For reliable tests, maintain **dedicated fixtures** for principals, attributes, authorities, and `ClientRegistration`; use `@WebFluxTest` or an in-process `WebTestClient` with `springSecurity()`; test `401` anonymous, `403` missing permissions, CSRF for POSTs, and wrong registration/tenant cases.

Most importantly, keep the scope clear: **`mockOAuth2Login` tests post-login `Authentication`, not authorization-code callbacks, ID Token signatures, token endpoints, or refresh-token behavior**. When an endpoint actually uses an access token to call an API, test `ReactiveOAuth2AuthorizedClientManager`/repository and outbound Bearer tokens separately; when an endpoint requires `OidcUser`, use `mockOidcLogin()`; and when an endpoint acts as a Resource Server accepting JWTs, use `mockJwt()`.

By cleanly separating these test layers, your application gains fast, deterministic WebFlux tests without conflating **OAuth2 login, user authorization, authorized-client selection, and real token verification**.
