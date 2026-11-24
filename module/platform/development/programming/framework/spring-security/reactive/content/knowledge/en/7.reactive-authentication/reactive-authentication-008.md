# Anonymous Authentication with AnonymousAuthenticationWebFilter

> **Scope:** Spring Boot 3.3.x, Spring Security 6.x, Spring WebFlux (reactive), and Java 17+. This lesson explains **anonymous authentication** in reactive flows, the role of `AnonymousAuthenticationWebFilter`, how to configure `ServerHttpSecurity.anonymous(...)`, how to read anonymous identity from the Reactor Context, and how to distinguish public visitors from logged-in users.

## 1. Does "Anonymous" Mean "Authenticated"?

An API commonly serves two kinds of callers at the same time:

- **Unauthenticated visitors:** have not provided valid credentials; may be allowed to view public pages, product catalogs, or documentation.
- **Logged-in users:** identity has been verified via HTTP Basic, form login, JWT, or another mechanism; may access protected data or authorized operations.

Spring Security offers a mechanism called **anonymous authentication**: when no real `Authentication` exists in the security context yet, the framework *may* create an `AnonymousAuthenticationToken` representing the guest. The purpose is so different parts of the system consistently see an `Authentication` with a uniform identity/authority rather than each place inventing a string like `"guest"`.

**Important warning:** having an `AnonymousAuthenticationToken` in the context does **not** mean the visitor has proven an identity. It creates no account, verifies no password, assigns no personal identity, and grants no access to protected areas.

### Specifics of WebFlux

In WebFlux, the component responsible for this is:

```java
org.springframework.security.web.server.authentication.AnonymousAuthenticationWebFilter
```

This is an `org.springframework.web.server.WebFilter`, distinct from Servlet/MVC's `AnonymousAuthenticationFilter`. It checks whether `ReactiveSecurityContextHolder` already holds an `Authentication`; if not, it can provide an `AnonymousAuthenticationToken` for downstream processing.

**Do not assume WebFlux always enables anonymous authentication.** The Spring Security 6.x Javadoc for `ServerHttpSecurity.anonymous(Customizer)` states that anonymous authentication is **disabled by default** in the reactive DSL; to use it, declare `.anonymous(Customizer.withDefaults())` or a specific `anonymous(...)` configuration explicitly. A `permitAll()` endpoint returning 200 **does not imply** that the context holds an anonymous token.

## 2. How Does AnonymousAuthenticationWebFilter Operate?

The filter belongs to the security web chain and operates inside the reactive context:

```text
HTTP request
   |
   v
SecurityWebFilterChain
   |
   +--> Authentication Filter (Basic/form/JWT, if configured)
   |         |
   |         +--> valid credentials: real user Authentication
   |         +--> no credentials: may have no Authentication yet
   |
   +--> AnonymousAuthenticationWebFilter (when ENABLED)
   |         |
   |         +--> Authentication already present: keep as-is
   |         +--> no Authentication yet: create AnonymousAuthenticationToken
   |                  principal = "anonymousUser" (default)
   |                  authorities = ["ROLE_ANONYMOUS"] (default)
   |
   +--> Authorization / authorizeExchange(...)
   |         |
   |         +--> permitAll()       : does not require login
   |         +--> authenticated()   : requires real verified identity
   |         +--> hasAuthority(...) : compares authority per policy
   v
Controller -> Mono / Flux -> HTTP response
```

The diagram above depicts **when anonymous is enabled** in the chain. If disabled, a request lacking credentials may continue with an empty security context on a public endpoint.

Default properties of the anonymous token when using the `AnonymousAuthenticationWebFilter(String key)` constructor:

| Property | Value / meaning |
|---|---|
| Token type | `AnonymousAuthenticationToken` |
| Principal | String `"anonymousUser"` |
| Authority | Single authority `"ROLE_ANONYMOUS"` |
| Key | Internal key used to create/identify the anonymous token, not a user password |
| Credentials | Does not represent login credentials supplied by a user |
| Trust level | Anonymous visitor; not an authenticated user identity |

You can customize the principal, authority, key, or replace the filter via `ServerHttpSecurity.AnonymousSpec`. If a verified `Authentication` from successful authentication already exists, the filter must not replace it with an anonymous guest.

### Where Does SecurityContext Live?

In WebFlux, Spring Security uses the **Reactor Context** to carry the security context into the reactive chain. Because a request can switch threads, you should not rely on ThreadLocal-based `SecurityContextHolder` as the default way to read the user in a reactive service. When needed, use:

```java
ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
```

This snippet is **a code fragment** that must sit inside a method returning `Mono` with appropriate imports. If the security context is empty, it can return `Mono.empty()`. When `AnonymousAuthenticationWebFilter` is configured and active in the matching chain, downstream handlers can receive the anonymous authentication.

## 3. Is "Token Has isAuthenticated() = true" a Vulnerability?

`AnonymousAuthenticationToken` inherits Spring Security's token machinery and usually has `Authentication.isAuthenticated() == true`. This technical flag causes many readers to mistakenly think an anonymous visitor is "logged in".

**Do not write this yourself:**

```java
// Wrong if used as a logged-in check:
boolean isRealUser = authentication != null
    && authentication.isAuthenticated();
```

Because an anonymous token also makes the expression above evaluate to `true`.

In Spring Security 6.x, `AuthenticationTrustResolver` distinguishes anonymous from real authentication. Illustrative usage:

```java
AuthenticationTrustResolver trust =
    new AuthenticationTrustResolverImpl();

boolean anonymous = trust.isAnonymous(authentication);
boolean authenticatedUser = trust.isAuthenticated(authentication);
```

This is illustrative code requiring imports and a concrete `Authentication`. The trust resolver's `isAuthenticated` checks non-null, the authenticated flag, and **not anonymous**. Spring Security uses similar trust-level awareness in standard authorization rules; therefore you should never conclude `authenticated()` grants access to anonymous callers merely from the token's raw boolean flag.

**Rule:** use `.authenticated()`, `.hasRole(...)`, `.hasAuthority(...)`, and Spring Security's authorization mechanisms when protecting routes. Never compare the string `"anonymousUser"` manually or rely solely on raw `isAuthenticated()` to make security decisions.

## 4. Four Concepts Very Easily Confused

| Concept | What it does | What it does NOT guarantee |
|---|---|---|
| `permitAll()` | Allows matching requests to proceed without logging in | Does not create an `AnonymousAuthenticationToken` on its own |
| `anonymous(Customizer.withDefaults())` | Enables creating anonymous authentication when no real auth exists | Does not open routes on its own or replace `authorizeExchange` |
| `authenticated()` | Requires the caller to be genuinely authenticated per policy | Does not treat an anonymous token as a real login |
| `hasAuthority("ROLE_ANONYMOUS")` | Requires the Authentication object to hold that exact authority | Does not strictly prove the caller is *not* logged in if a misconfigured system assigns it to real users |

Note the last point: `ROLE_ANONYMOUS` is an **authority**, not an absolute "guest-only" check. For example, if a real user were erroneously granted that authority, `hasAuthority("ROLE_ANONYMOUS")` would match too. When business rules require *only unauthenticated guests* to access something, design a `ReactiveAuthorizationManager` checking trust level via `AuthenticationTrustResolver` instead of relying on role names.

**No auth** and **anonymous auth** are two distinct technical states; neither is sufficient to enter an `authenticated()` route.

## 5. Enabling Anonymous Authentication in ServerHttpSecurity

Core configuration snippet:

```java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public").permitAll()
            .anyExchange().authenticated())
        .anonymous(Customizer.withDefaults())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

The snippet above belongs inside a WebFlux `@Configuration` class with the required imports. `.anonymous(Customizer.withDefaults())` is the step that enables the filter for the chain. `.httpBasic(...)` enables a real authentication mechanism; `.authorizeExchange(...)` defines path policies.

Using Spring Boot's security starter does not mean you always need an anonymous token. Enable it only when you have a concrete need such as standardizing guest context or testing identity states; unnecessary configuration can confuse readers about principal types and permission checks.

### Customizing the Anonymous Identity

You can change the principal and authority to match technical requirements:

```java
.anonymous(anonymous -> anonymous
    .principal("guest")
    .authorities("ROLE_GUEST"))
```

This DSL fragment **replaces** `anonymous(Customizer.withDefaults())`. When changing it as above, do not continue expecting `principalName = "anonymousUser"` or `ROLE_ANONYMOUS` to appear. Never configure `ROLE_ADMIN`/`ROLE_USER` for anonymous guests; otherwise authority-based rules would grant guests unintended permissions.

`AnonymousSpec` also supports `key(String)` and `authenticationFilter(AnonymousAuthenticationWebFilter)`. In typical configurations, a default key is generated internally; **never share this key with browsers as a credential**, and do not manually add a second filter when the builder already registers the anonymous filter. If replacing the filter, understand the scope and responsibilities of the custom filter clearly.

## 6. Complete Demo: Comparing Anonymous and Logged-in Users

The application below uses **Spring Boot 3.3.13, Java 17+, Spring WebFlux, and HTTP Basic**. The goal is inspecting the security context via JSON without logging tokens/cookies/passwords. Only run development credentials on localhost or over HTTPS.

Project structure:

```text
anonymous-webflux-demo/
  settings.gradle
  build.gradle
  src/main/java/demo/anonymous/AnonymousDemoApplication.java
  src/main/java/demo/anonymous/SecurityConfiguration.java
  src/test/java/demo/anonymous/AnonymousDemoTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'anonymous-webflux-demo'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.anonymous'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**src/main/java/demo/anonymous/SecurityConfiguration.java**

```java
package demo.anonymous;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET,
                    "/api/public", "/api/whoami").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/api/guest-role").hasAuthority("ROLE_ANONYMOUS")
                .pathMatchers(HttpMethod.GET,
                    "/api/member").authenticated()
                .anyExchange().denyAll())
            .anonymous(Customizer.withDefaults())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Explanation: `/api/public` and `/api/whoami` allow guests, `/api/guest-role` demonstrates a rule based on the `ROLE_ANONYMOUS` authority, and `/api/member` requires real login. Any undeclared HTTP methods are blocked by `denyAll()`. `formLogin` is disabled so HTTP Basic challenges can be observed directly with curl; this is a demo API configuration, not a template for every web app.

**src/main/java/demo/anonymous/AnonymousDemoApplication.java**

```java
package demo.anonymous;

import java.security.Principal;
import java.util.List;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.authentication.AuthenticationTrustResolver;
import org.springframework.security.authentication.AuthenticationTrustResolverImpl;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class AnonymousDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(AnonymousDemoApplication.class, args);
    }

    public record IdentityView(
            String principalName,
            String tokenType,
            boolean tokenAuthenticatedFlag,
            boolean anonymous,
            boolean authenticatedUser,
            List<String> authorities) {
    }

    @RestController
    static class Api {

        private static final AuthenticationTrustResolver TRUST =
            new AuthenticationTrustResolverImpl();

        @GetMapping("/api/public")
        Mono<String> publicMessage() {
            return Mono.just("public");
        }

        @GetMapping("/api/guest-role")
        Mono<String> guestRole() {
            return Mono.just("anonymous role");
        }

        @GetMapping("/api/member")
        Mono<String> member(Principal principal) {
            return Mono.just("member: " + principal.getName());
        }

        @GetMapping("/api/whoami")
        Mono<IdentityView> whoami() {
            return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Api::asView)
                .switchIfEmpty(Mono.just(
                    new IdentityView("none", "none",
                        false, false, false, List.of())));
        }

        private static IdentityView asView(Authentication auth) {
            List<String> authorities = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .sorted()
                .toList();
            return new IdentityView(
                auth.getName(),
                auth.getClass().getSimpleName(),
                auth.isAuthenticated(),
                TRUST.isAnonymous(auth),
                TRUST.isAuthenticated(auth),
                authorities);
        }
    }
}
```

**Why does the example use `AuthenticationTrustResolver`?** An anonymous token can return `true` from `auth.isAuthenticated()`, yet `TRUST.isAnonymous(auth)` is `true` and `TRUST.isAuthenticated(auth)` is `false`. These fields let you see the difference directly in JSON; the application does not use that response for authentication or authorization.

### 6.1 Running the Application

Requires JDK 17+ and Gradle compatible with Boot 3.3. From the project directory:

```bash
gradle bootRun
```

If the project already has a compatible Gradle Wrapper, use `./gradlew bootRun` (Windows: `gradlew.bat bootRun`). Because the demo provides no custom `ReactiveUserDetailsService` or `ReactiveAuthenticationManager`, Spring Boot may generate a test account `user` with a random password. Read the `Using generated security password: ...` line in the startup log; this is the password for the current run, for local use only.

### 6.2 Trying Requests Without Credentials

```bash
curl -i http://localhost:8080/api/public
curl -i http://localhost:8080/api/whoami
curl -i http://localhost:8080/api/guest-role
curl -i -H "Accept: application/json" http://localhost:8080/api/member
```

Expected results:

| Endpoint | Expected HTTP | Meaning |
|---|---|---|
| `GET /api/public` | 200, body `public` | `permitAll()` |
| `GET /api/whoami` | 200, JSON reporting anonymous | Anonymous filter present, context populated for guest |
| `GET /api/guest-role` | 200, body `anonymous role` | Guest carries `ROLE_ANONYMOUS` authority |
| `GET /api/member` | 401 | Guest does not satisfy `authenticated()`, Basic challenge |

Key JSON from `/api/whoami` when no credentials are sent:

```json
{
  "principalName": "anonymousUser",
  "tokenType": "AnonymousAuthenticationToken",
  "tokenAuthenticatedFlag": true,
  "anonymous": true,
  "authenticatedUser": false,
  "authorities": ["ROLE_ANONYMOUS"]
}
```

Depending on the server and HTTP headers, response headers may vary; the JSON illustrates the values produced by the demo code itself.

### 6.3 Trying Requests With Valid Credentials

Use the curl CLI with `-u user` so the tool prompts for the password instead of recording it in shell history:

```bash
curl -i -u user http://localhost:8080/api/whoami
curl -i -u user http://localhost:8080/api/member
curl -i -u user http://localhost:8080/api/guest-role
```

In PowerShell you can use `curl.exe` instead of the `curl` alias.

Expectations:

- `/api/whoami` returns HTTP 200 with `principalName = "user"`, `anonymous = false`, and `authenticatedUser = true`.
- `/api/member` returns HTTP 200 with body `member: user`.
- `/api/guest-role` returns HTTP 403 because the default dev user has `ROLE_USER`, **not** `ROLE_ANONYMOUS`.

Here `/api/guest-role` is a **demo of authority matching**, not a "guest-only" guard guaranteed in every system with customized authorities. If a business rule truly requires unauthenticated guests, check via the trust resolver with an appropriate policy.

**Note when sending wrong credentials:** A request with an invalid HTTP Basic header can be rejected by the authentication mechanism with HTTP 401 **even when the path is marked `permitAll()`**. `permitAll()` governs authorization; it does not turn a failed authentication attempt into a successful anonymous login.

## 7. Automated Testing with WebTestClient

When running tests, use fixed test accounts from Boot properties instead of relying on random passwords in logs. Never use these passwords in production.

**src/test/java/demo/anonymous/AnonymousDemoTest.java**

```java
package demo.anonymous;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {
        "spring.security.user.name=alice",
        "spring.security.user.password=test-only-secret",
        "spring.security.user.roles=USER"
    }
)
@AutoConfigureWebTestClient
class AnonymousDemoTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicEndpointAllowsGuest() {
        client.get().uri("/api/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void guestHasAnonymousAuthenticationToken() {
        client.get().uri("/api/whoami")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.principalName").isEqualTo("anonymousUser")
            .jsonPath("$.tokenType").isEqualTo("AnonymousAuthenticationToken")
            .jsonPath("$.tokenAuthenticatedFlag").isEqualTo(true)
            .jsonPath("$.anonymous").isEqualTo(true)
            .jsonPath("$.authenticatedUser").isEqualTo(false)
            .jsonPath("$.authorities[0]").isEqualTo("ROLE_ANONYMOUS");
    }

    @Test
    void guestRoleMatchesAnonymousAuthority() {
        client.get().uri("/api/guest-role")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("anonymous role");
    }

    @Test
    void memberEndpointRequiresRealAuthentication() {
        client.get().uri("/api/member")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedUserReplacesAnonymousPrincipal() {
        client.get().uri("/api/whoami")
            .headers(h -> h.setBasicAuth("alice", "test-only-secret"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.principalName").isEqualTo("alice")
            .jsonPath("$.anonymous").isEqualTo(false)
            .jsonPath("$.authenticatedUser").isEqualTo(true);
    }

    @Test
    void memberCanEnterButLacksAnonymousAuthority() {
        client.get().uri("/api/member")
            .headers(h -> h.setBasicAuth("alice", "test-only-secret"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("member: alice");

        client.get().uri("/api/guest-role")
            .headers(h -> h.setBasicAuth("alice", "test-only-secret"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

Run:

```bash
gradle test
```

Once dependencies are downloaded, Gradle/JDK are compatible, and the project keeps the demo configuration, all **6 test methods** are expected to pass. The tests do not depend on an external database or token server. Do not claim the build ran solely from reading this lesson; if a build fails, inspect the concrete logs and fix versions/dependencies or errors in actual source files.

### 7.1 Disabling Anonymous to Observe the Difference

To compare, in `SecurityConfiguration`, **replace only**:

```java
.anonymous(Customizer.withDefaults())
```

with:

```java
.anonymous(anonymous -> anonymous.disable())
```

Then run a targeted test: `/api/public` can still return 200 because of `permitAll()`; `/api/whoami` is no longer guaranteed to hold an anonymous token to return JSON as when enabled; the `hasAuthority("ROLE_ANONYMOUS")` rule can no longer rely on a filter-created token. **Do not keep all 6 tests unchanged with the old expectations assuming they should all still pass**; the goal is proving that enabling/disabling the anonymous token is independent from allowing public URLs.

### 7.2 Changing Principal and Authority

Replace the anonymous-enabling line with:

```java
.anonymous(anonymous -> anonymous
    .principal("guest")
    .authorities("ROLE_GUEST"))
```

Expected: `/api/whoami` for guests shows `principalName = "guest"` and authority `ROLE_GUEST`. If you keep the `hasAuthority("ROLE_ANONYMOUS")` matcher, `/api/guest-role` **no longer matches**; update the matcher if changing the policy intentionally. This experiment clarifies how filter constructor/config affects context values while `permitAll` stays independent.

## 8. Reading Anonymous in a Controller or Service

### 8.1 ReactiveSecurityContextHolder Is the Direct Way

Inside a controller/service invoked from a reactive request with a matching security chain:

```java
Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("no-security-context");
}
```

This is an **illustrative method** and does not compile without imports/class. When anonymous is enabled and the request has no real auth, the result is usually `anonymousUser` by default. When anonymous is disabled, the publisher can be empty; handle that intentionally.

### 8.2 Why Can `Principal` and `@AuthenticationPrincipal` Differ?

In Spring Security, `Authentication` also implements `Principal` and has `getPrincipal()`. When the anonymous filter creates its default token:

- `Authentication` can be `AnonymousAuthenticationToken`.
- `Authentication.getPrincipal()` defaults to the string `"anonymousUser"`.
- A handler using `@AuthenticationPrincipal UserDetails` should not assume it will always receive `UserDetails`: for guests the principal is only a `String`, so the types do not match.
- `ServerWebExchange.getPrincipal()` and `ReactiveSecurityContextHolder.getContext()` can reflect the request identity reactively once the chain populates the context.

For example, `@AuthenticationPrincipal Object user` can receive a `String` principal or another type depending on configured authentication, yet business code should not cast arbitrarily. When you only need to display "guest" or "user", it is better to map from verified `Authentication` to an internal DTO and consult `AuthenticationTrustResolver`.

### 8.3 Reactor Context Is Not ThreadLocal

`publishOn` or `subscribeOn` can switch threads without automatically clearing the Reactor Context; bugs usually happen when code calls `subscribe()` manually, creates an unlinked subscription, or hands off work to a system that does not propagate Context. Never call `block()` on the event loop just to fetch the user. Pass publishers or verified identities through APIs/services, and re-verify permissions when dispatching async messages/jobs.

## 9. Comparing WebFlux and Servlet

| Aspect | Spring WebFlux / reactive | Spring MVC / Servlet |
|---|---|---|
| Anonymous filter | `AnonymousAuthenticationWebFilter` | `AnonymousAuthenticationFilter` |
| Security builder | `ServerHttpSecurity` | `HttpSecurity` |
| Chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Security context in flow | `ReactiveSecurityContextHolder` / Reactor Context | Typically `SecurityContextHolder` / ThreadLocal |
| Illustrative config | `.anonymous(Customizer.withDefaults())` | `.anonymous(Customizer.withDefaults())` on the corresponding Servlet builder |
| HTTP filter type | `WebFilter` | Servlet `Filter` |

Do not copy `HttpSecurity` or `OncePerRequestFilter` examples directly into WebFlux. The types, request lifecycles, and context propagation differ. Above all, **do not infer WebFlux's anonymous enabled state from Servlet's default behavior**.

## 10. Common Risks and Misconceptions

| Misconception | Consequence | Correct understanding |
|---|---|---|
| "Having an `AnonymousAuthenticationToken` means the user is logged in" | Can grant access wrongly if checking only `isAuthenticated()` | Use `AuthenticationTrustResolver` or framework authorization |
| "`permitAll()` always creates an anonymous principal" | Controller code relies on a fake principal that does not exist | `permitAll` and `anonymous` are two independent settings |
| "Reactive anonymous is enabled by default like MVC" | Tests expecting `anonymousUser` find none | Enable explicitly on chains needing anonymous |
| "`ROLE_ANONYMOUS` is equivalent to identity authentication" | Private data exposed to guests | This role only denotes nominal guest status |
| "Using `hasAuthority("ROLE_ANONYMOUS")` is an absolute guest-only check" | Real users granted the same authority also match | For guest-only policies, check trust level |
| "Without a Basic header, every route is public" | Getting 401/403 on protected routes | Needs explicit `permitAll` rules by design |
| "Sending wrong Basic to a public route must still return 200" | Confusing authentication failure with authorization failure | Authentication failure can block requests before authorization |
| "Disabling `anonymous()` removes `permitAll()`" | Editing the wrong policy target | Two independent settings; test each condition |
| "Guests must have `UserDetails`" | Null/ClassCastException in handlers | Anonymous principal is usually just a String |
| "Anonymous context persists inside background jobs" | Wrong audit/authorization context | Reactor Context is not automatically carried into queues/background jobs |
| "Enabling anonymous replaces JWT/Basic" | Confusing a placeholder identity with verified identity | Anonymous only fills the gap when no real authentication exists |
| "Can serialize full Authentication to JSON" | Risks exposing credentials/internal details | Return only minimal DTO fields, never log tokens |
| "One custom chain protects all other requests" | URLs outside `securityMatcher` may bypass the chain | Include a fallback chain and test routes outside the matcher |

**Security note:** using `ROLE_ANONYMOUS` to authorize reading public docs can be useful, yet `permitAll()` is simpler when *everyone* may view them. Never grant anonymous authorities equivalent to writing data, admin actions, viewing profiles, or accessing tenants. Never send the anonymous filter's internal key to clients.

## 11. Checklist for Reviewing a WebFlux Application

1. Confirm the app uses WebFlux `ServerHttpSecurity`/`SecurityWebFilterChain`, not mixed with MVC config.
2. Check whether **`anonymous(...)` was called** on the needed chain. Do not rely on default assumptions.
3. Explicitly define `permitAll`, `authenticated`, and required authorities; place specific matchers before fallbacks.
4. On `permitAll`, do not assume Reactor Context holds a real user or even an anonymous token if the filter is not enabled.
5. If you actually want "logged in", use framework authorization/`AuthenticationTrustResolver`; never check raw `isAuthenticated()` alone.
6. Test guests, wrong credentials, and authenticated users, covering appropriate 200/401/403 HTTP statuses.
7. Verify the filter does not overwrite valid `Authentication`s and does not accidentally grant sensitive roles to guests.
8. Never return full `SecurityContext`/`Authentication` or log credentials.
9. With multiple security chains, configure anonymous and rules per chain's exact scope, plus a fallback.
10. When calling async messages/queues, do not assume a request's anonymous identity persists in an independent subscription/job.

## 12. Self-Practice Exercises

1. Run the demo and call `/api/whoami` without Basic and with valid Basic. Compare `tokenType`, `principalName`, `tokenAuthenticatedFlag`, `anonymous`, and `authenticatedUser`.
2. Why can `AnonymousAuthenticationToken.isAuthenticated()` be `true` while `.authenticated()` still denies guests from `/api/member`?
3. Disable anonymous with `.anonymous(anonymous -> anonymous.disable())` and retry `/api/public` and `/api/whoami`. Distinguish public access from anonymous context.
4. Change principal to `guest` and authority to `ROLE_GUEST`; update the `/api/guest-role` test accordingly.
5. Create a policy that truly allows only *unauthenticated* guests using the trust resolver rather than relying solely on authority; write a test where a real user also has `ROLE_ANONYMOUS`.
6. Try sending a wrong Basic header to a `permitAll` route to understand the difference between authentication failure and authorization.
7. Explain why `anonymousUser` must never be treated as a database user ID or used as a cache key for private data.

## Takeaways

`AnonymousAuthenticationWebFilter` is a **Spring Security reactive WebFilter** that can provide an `AnonymousAuthenticationToken` in `ReactiveSecurityContextHolder` when no other authentication exists. On `ServerHttpSecurity`, **enable anonymous explicitly** when truly needed and manage route policies separately via `authorizeExchange`. An anonymous token carries a principal/authority solely to represent guests; it is **not proof of login**. Enforce real permissions with Spring Security authorization and determine trust levels via `AuthenticationTrustResolver`.

## Technical Documentation

- Javadoc `AnonymousAuthenticationWebFilter` — package, constructors, and behavior: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/AnonymousAuthenticationWebFilter.html
- Javadoc `ServerHttpSecurity.anonymous(Customizer)` — how to enable and default policy: https://docs.spring.io/spring-security/site/docs/6.2.8/api/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Javadoc `ServerHttpSecurity.AnonymousSpec` — principal, authorities, key, disable: https://docs.spring.io/spring-security/site/docs/6.3.0-M3/api/org/springframework/security/config/web/server/ServerHttpSecurity.AnonymousSpec.html
- Javadoc `AuthenticationTrustResolver` — distinguishing anonymous and authenticated users: https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authentication/AuthenticationTrustResolver.html
- Spring Security WebFlux configuration: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
