# Testing `mockOAuth2Login()`, `mockOidcLogin()`, and Post-Login Principals in Spring Security WebFlux

## Learning objectives

After this lesson, you will be able to: (1) create a request authenticated via OAuth 2.0 Login or OpenID Connect (OIDC) Login in `WebTestClient` without a real Identity Provider (IdP); (2) inspect `OAuth2User`, `OidcUser`, `Authentication`, and the post-login principal name; (3) configure custom attributes, ID Token claims, authorities, and principal names; (4) write allowed, denied, and unauthenticated scenarios; (5) distinguish the limits of mock testing from testing the full login flow.

## 1. What is actually being simulated

In a WebFlux application, Spring Security filters store authentication information in the reactive security context so controllers and business layers can access it in a Reactor stream. Two helpers from `spring-security-test` establish an authentication context for **test requests**, bypassing IdP redirects, receiving an authorization code, exchanging the code for tokens, or verifying token signatures:

- `mockOAuth2Login()`: creates an `OAuth2AuthenticationToken` whose principal is an `OAuth2User`. Suitable for apps using OAuth 2.0 Login and user attributes.
- `mockOidcLogin()`: also creates an `OAuth2AuthenticationToken`, but with an `OidcUser` principal carrying `OidcIdToken` and `OidcUserInfo`. Suitable for apps needing OIDC identity/claims.

Test flow diagram:

~~~text
WebTestClient.mutateWith(mockOAuth2Login() or mockOidcLogin())
    -> simulated request has Authentication in SecurityContext
    -> SecurityWebFilterChain (authentication/authorization rules)
    -> Handler/Controller (@AuthenticationPrincipal, Principal)
    -> response asserted with WebTestClient
~~~

Both helpers can also supply a fake `OAuth2AuthorizedClient` via the test repository, useful with `@RegisteredOAuth2AuthorizedClient`. They **do not verify** that authorization endpoint configuration, redirect URIs, client secrets, PKCE, token exchange, or an external IdP actually work.

### Defaults to remember

| Characteristic | `mockOAuth2Login()` | `mockOidcLogin()` |
| --- | --- | --- |
| Authentication | `OAuth2AuthenticationToken` | `OAuth2AuthenticationToken` |
| Principal | `OAuth2User` | `OidcUser` (which is also an `OAuth2User`) |
| Default identity | attribute `sub = "user"` | ID Token claim `sub = "user"` |
| Default authority | `SCOPE_read` | `SCOPE_read` |
| Direct data customization | `attributes(...)` | `idToken(...)`, `userInfo(...)` |
| Fully custom principal | `oauth2User(...)` | `oidcUser(...)` |

`getName()` on the default principal returns `user`. In custom setups, `getName()` may come from another attribute such as `user_name` or `preferred_username`; it does not necessarily equal the `sub` claim. `Authentication.getPrincipal()` is the user object, whereas `Authentication.getName()` is the name determined by that object.

## 2. Setting up the reactive test environment

Examples use Java 17+, Spring Boot 3.x / Spring Security 6.x, and JUnit Jupiter. On a Spring Boot Gradle project **that already has plugins and version management**, add these dependencies to `build.gradle` (omit explicit versions to use Boot's BOM):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Use WebFlux, `WebTestClient`, and import helpers from `org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers`. Spring MVC APIs such as `SecurityMockMvcRequestPostProcessors.oauth2Login()` or `MockMvc` are **not** the helpers used here. The tests below bind to a mock application context (`MOCK`) without starting a real server.

To have a runnable example and actively observe the principal, create three files in package `com.example.securitydemo`.

### File 1: `src/main/java/com/example/securitydemo/ReactiveLoginDemoApplication.java`

~~~java
package com.example.securitydemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveLoginDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveLoginDemoApplication.class, args);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/admin").hasAuthority("ROLE_ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

The filter chain requires authentication for every endpoint, with `/admin` additionally requiring `ROLE_ADMIN`. `httpBasic` is only present so the example has a clear 401 response for anonymous access; OAuth2/OIDC test helpers still attach the simulated authentication context directly to the request. **This is a minimal configuration for inspecting principals**, not a production OAuth2/OIDC login setup. A real app must configure `oauth2Login`, client registrations, and the corresponding provider.

### File 2: `src/main/java/com/example/securitydemo/ProfileController.java`

~~~java
package com.example.securitydemo;

import java.security.Principal;
import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ProfileController {

    @GetMapping("/me/oauth2")
    public Mono<Map<String, String>> oauth2(
            @AuthenticationPrincipal OAuth2User user) {
        return Mono.just(Map.of(
                "name", user.getName(),
                "userId", user.getAttribute("user_id")));
    }

    @GetMapping("/me/oidc")
    public Mono<Map<String, String>> oidc(
            @AuthenticationPrincipal OidcUser user) {
        return Mono.just(Map.of(
                "name", user.getName(),
                "subject", user.getIdToken().getSubject(),
                "userId", user.getIdToken().getClaimAsString("user_id")));
    }

    @GetMapping("/me/principal")
    public Mono<String> principal(Mono<Principal> principal) {
        return principal.map(Principal::getName);
    }

    @GetMapping("/me/context")
    public Mono<String> contextName() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());
    }

    @GetMapping("/admin")
    public Mono<String> admin() {
        return Mono.just("admin-ok");
    }
}
~~~

`@AuthenticationPrincipal` extracts `Authentication.getPrincipal()` and binds it to the declared parameter type. When an endpoint needs an OIDC-specific ID Token, use `OidcUser` and `getIdToken()`. If only the authenticated name is needed, you can accept `Mono<Principal>` or read `ReactiveSecurityContextHolder`. Do not retrieve a WebFlux request's Authentication from ThreadLocal `SecurityContextHolder` as in synchronous servlet code. Both `/me/oauth2` and `/me/oidc` intentionally require `user_id`; tests must supply that attribute because only `sub` is present by default, avoiding constructing `Map.of(...)` with a null value.

### File 3: `src/test/java/com/example/securitydemo/ProfileControllerTest.java`

~~~java
package com.example.securitydemo;

import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.oidc.OidcIdToken;
import org.springframework.security.oauth2.core.oidc.user.DefaultOidcUser;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.security.oauth2.core.user.DefaultOAuth2User;
import org.springframework.security.oauth2.core.user.OAuth2User;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOAuth2Login;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockOidcLogin;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class ProfileControllerTest {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void oauth2AttributesAndDefaultPrincipalName() {
        client.mutateWith(mockOAuth2Login()
                        .attributes(attrs -> attrs.put("user_id", "u-42")))
                .get().uri("/me/oauth2")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("user")
                .jsonPath("$.userId").isEqualTo("u-42");
    }

    @Test
    void oidcIdTokenClaimAndDefaultPrincipalName() {
        client.mutateWith(mockOidcLogin()
                        .idToken(token -> token.claim("user_id", "u-77")))
                .get().uri("/me/oidc")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("user")
                .jsonPath("$.subject").isEqualTo("user")
                .jsonPath("$.userId").isEqualTo("u-77");
    }

    @Test
    void principalAfterOAuth2Login() {
        client.mutateWith(mockOAuth2Login())
                .get().uri("/me/principal")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user");
    }

    @Test
    void authenticationFlowsThroughReactiveContext() {
        client.mutateWith(mockOidcLogin())
                .get().uri("/me/context")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("user");
    }

    @Test
    void anonymousRequestIsRejected() {
        client.get().uri("/me/principal")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedWithoutAdminAuthorityIsForbidden() {
        client.mutateWith(mockOidcLogin())
                .get().uri("/admin")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminAuthorityAllowsRequest() {
        client.mutateWith(mockOidcLogin()
                        .authorities(new SimpleGrantedAuthority("ROLE_ADMIN")))
                .get().uri("/admin")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-ok");
    }

    @Test
    void customOAuth2UserControlsPrincipalName() {
        OAuth2User user = new DefaultOAuth2User(
                AuthorityUtils.createAuthorityList("SCOPE_read"),
                Map.of("user_name", "linh", "user_id", "u-42"),
                "user_name");

        client.mutateWith(mockOAuth2Login().oauth2User(user))
                .get().uri("/me/oauth2")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("linh")
                .jsonPath("$.userId").isEqualTo("u-42");
    }

    @Test
    void customOidcUserCanUsePreferredUsername() {
        OidcIdToken idToken = OidcIdToken.withTokenValue("fake-id-token")
                .claim("sub", "subject-101")
                .claim("preferred_username", "minh")
                .claim("user_id", "u-99")
                .build();

        OidcUser user = new DefaultOidcUser(
                AuthorityUtils.createAuthorityList("SCOPE_read"),
                idToken,
                "preferred_username");

        client.mutateWith(mockOidcLogin().oidcUser(user))
                .get().uri("/me/oidc")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("minh")
                .jsonPath("$.subject").isEqualTo("subject-101")
                .jsonPath("$.userId").isEqualTo("u-99");
    }
}
~~~

Run a single test class in a Gradle project configured with Spring Boot (no IdP or real server needed):

~~~bash
./gradlew test --tests 'com.example.securitydemo.ProfileControllerTest'
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.securitydemo.ProfileControllerTest
~~~

The expected result is **9 passing tests**. These tests assert HTTP status, JSON responses, or plain text; they do not depend on controller stdout.

## 3. Reading the principal after mock login

Three perspectives to distinguish:

1. `@AuthenticationPrincipal OAuth2User`: receives an object holding attributes (e.g. `user.getAttribute("user_id")`) and `getName()`; used for OAuth2 profiles.
2. `@AuthenticationPrincipal OidcUser`: receives an object with `getIdToken()`, `getUserInfo()`, and `getClaims()`; reads `sub` from the ID Token when an IdP identifier is needed. `OidcUser` extends `OAuth2User`.
3. `Principal` / `Authentication`: represents identity at the security layer; `OAuth2AuthenticationToken.getPrincipal()` is an `OAuth2User` or `OidcUser` depending on the request. `getName()` uses the configured name attribute, so **never assume it is an immutable ID**.

In asynchronous/reactive flows, `ReactiveSecurityContextHolder.getContext()` retrieves the `SecurityContext` attached to the Reactor context. This matters when switching threads, invoking reactive services, or running work on a different thread from where the request began. `Mono<Principal>` in a controller also reflects the current request's identity.

Examples from the test suite:

| Simulated request | How it is read | Expected value |
| --- | --- | --- |
| `mockOAuth2Login()` | `Principal.getName()` | `user` |
| `mockOAuth2Login().attributes(...)` | `OAuth2User.getAttribute("user_id")` | `u-42` |
| `mockOidcLogin().idToken(...)` | `OidcUser.getIdToken().getSubject()` | `user` |
| `mockOidcLogin().idToken(...)` | `OidcUser.getIdToken().getClaimAsString("user_id")` | `u-77` |
| `mockOAuth2Login().oauth2User(...)` | `OAuth2User.getName()` | `linh` |
| `mockOidcLogin().oidcUser(...)` | `OidcUser.getName()` vs `getIdToken().getSubject()` | `minh` vs `subject-101` |

In business logic, the pair `issuer + sub` is commonly used as a stable OIDC identifier within an issuer's scope; `preferred_username`, `name`, and `email` can change, be missing, or lack uniqueness. Tests should assert the exact field that real business logic uses.

## 4. Customizing for advanced test scenarios

**Authorities / authorization.** The helpers grant `SCOPE_read` by default. To test `hasAuthority("ROLE_ADMIN")`, use `authorities(new SimpleGrantedAuthority("ROLE_ADMIN"))` as shown. `SCOPE_read` differs from `ROLE_ADMIN`; if a policy uses `hasRole("ADMIN")`, Spring Security looks for `ROLE_ADMIN` by prefix convention. Test both 403 when logged in without permission and 200 when authorized.

**OAuth2 attributes.** `mockOAuth2Login().attributes(attrs -> attrs.put("user_id", "u-42"))` modifies `OAuth2User` attributes. To change the principal name from `sub` to `user_name` or supply a custom principal, construct `DefaultOAuth2User` with `nameAttributeKey` and pass it to `oauth2User(...)`.

**OIDC claims.** `mockOidcLogin().idToken(token -> token.claim("user_id", "u-77"))` customizes the ID Token; `userInfo(...)` customizes UserInfo. Read claims from the exact source your business code reads from. When using a custom principal or non-default name attribute, construct `DefaultOidcUser` and pass it to `oidcUser(...)`.

**Client registration / authorized client.** If a controller uses `@RegisteredOAuth2AuthorizedClient`, login helpers provide a mock authorized client; you can override `clientRegistration(ClientRegistration)` to match the registration ID and metadata your code expects. When testing an OAuth2 client running independently of user login (such as client credentials), use `mockOAuth2Client("registration-id")` rather than treating `mockOAuth2Login()` as equivalent.

**Per-request isolation.** Apply `mutateWith(...)` directly to each `WebTestClient` request and assert both the response and 401/403 statuses. This keeps each test case's authentication data explicit and prevents subsequent tests from accidentally inheriting a prior test's principal.

## 5. Common mistakes and diagnostics

| Symptom | Likely cause | How to fix |
| --- | --- | --- |
| `@AuthenticationPrincipal OidcUser` is null or wrong type | Used `mockOAuth2Login()` while endpoint expects OIDC | Use `mockOidcLogin()` or align principal type with real logic |
| `user_id` is null when reading attribute | Default helper only sets `sub` | Add `attributes(...)` or `idToken(...)` on the right helper |
| Test returns 401 despite calling helper | `WebTestClient` lacks security filter support or wrong request setup | When binding manually: `.apply(springSecurity())`; ensure reactive APIs are used |
| Test returns 403 | Principal is authenticated but lacks policy authority | Supply matching `SCOPE_*` / `ROLE_*` and also assert the denied case |
| `getName()` differs from `sub` | Principal has a custom `nameAttributeKey` | Assert `name` and `subject` separately; never equate the two fields |
| `@WithMockUser` does not provide `OidcUser` | `@WithMockUser` builds a different Authentication/principal type | For OAuth2/OIDC controllers, use the OAuth2/OIDC helpers |
| Reading context via ThreadLocal in Reactor | WebFlux SecurityContext travels in Reactor context | Use `ReactiveSecurityContextHolder` or reactive principal parameter |
| Tests pass but real login fails | Helpers do not perform redirects, token exchange, or IdP validation | Add dedicated integration tests with a test IdP / mock HTTP provider |

Never infer that `mockOidcLogin()` validates ID Token signatures, audience, issuer, nonce, or expiration. Claims and authorities here are **test-defined fixtures**, not the outcome of real token verification. For Resource Server APIs accepting Bearer JWTs, use `mockJwt()` or `mockOpaqueToken()`: that is the access-token endpoint protection model, distinct from users logging in via OAuth2/OIDC Login.

## 6. Test design checklist

- Test endpoints reading only `Principal.getName()` if only a simple name is needed; test `OAuth2User`/`OidcUser` when business code relies on specific attributes/claims.
- Build fixtures matching real data: `sub`, `user_id`, authorities, registration, and name attribute; include missing claim, missing authority, and anonymous cases where needed.
- Verify the exact claim location: `OAuth2User.getAttributes()`, OIDC ID Token, or UserInfo, and distinguish `name` from `subject`.
- Verify both authorization (401/403/200) and response payloads; explicitly assert the principal seen by the request in Reactor context.
- Run additional authorization-flow integration tests with a mock IdP/HTTP component when your goal is verifying redirect configuration, token exchange, ID Token validation, or provider behavior.

## Official documentation

- [Spring Security — Testing OAuth 2.0 in Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockOAuth2Login()`, `mockOidcLogin()`, claims, authorities, and custom principals.
- [SecurityMockServerConfigurers API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/reactive/server/SecurityMockServerConfigurers.html): `WebTestClient` mutators and `SecurityContext` contracts.

Core takeaway: choose the helper matching **the principal type your code actually needs**, construct accurate fixtures for testing authorities and attributes, and verify that identity flows cleanly through WebFlux/Reactor from request to controller.