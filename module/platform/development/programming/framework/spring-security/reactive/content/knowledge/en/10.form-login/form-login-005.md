# Customizing Redirect Destinations After Successful or Failed Login

> **Lesson:** Form login in **Spring Security reactive / Spring WebFlux**. The content uses Spring Boot 3.x, Spring Security 6.x, and Java 17+. We configure `SecurityWebFilterChain` so that after a user submits the login form, a **valid login** redirects to `/app/home` and an **invalid login** redirects to `/auth/failed`. The lesson also explains the *saved request* mechanism, CSRF, WebSession, authorization, and *open redirect* pitfalls.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **unauthenticated destination**, **post-login success destination**, and **post-login failure destination**.
2. Configure `ServerHttpSecurity.formLogin(...)` with `ServerAuthenticationSuccessHandler` and `ServerAuthenticationFailureHandler`.
3. Use `RedirectServerAuthenticationSuccessHandler` and `RedirectServerAuthenticationFailureHandler` instead of writing redirect logic inside a password-handling controller.
4. Understand why `RedirectServerAuthenticationSuccessHandler("/app/home")` can **prioritize a saved request over `/app/home`**, and know how to enforce a fixed destination when needed.
5. Build a runnable WebFlux application with Spring Security's generated login page, a reactive user store, and a public failure notice page.
6. Properly test HTTP `302` and `Location` using `WebTestClient` with a CSRF token, without accidentally disabling CSRF just to make tests pass.
7. Avoid redirect loops, leaking authentication details, unintended external redirects, and confusing authentication with authorization.

## 2. Three Redirect Scenarios That Are Not the Same

In a web application using form login, these events occur at different times:

| Event | Primary Handler Component | Typical Destination |
| --- | --- | --- |
| Unauthenticated user opens a protected page | `ServerAuthenticationEntryPoint` / exception handling | `/login` |
| User submits `POST /login` with right password | `ServerAuthenticationSuccessHandler` | Saved request or default page, e.g., `/` |
| User submits `POST /login` with wrong password | `ServerAuthenticationFailureHandler` | `/login?error` |
| Authenticated user lacks permissions | Authorization / access-denied handling | Usually **403 Forbidden**, not "login failed" |
| Form POST missing CSRF token | CSRF WebFilter | Usually **403 Forbidden**; password failure handler is not invoked |

**Common misconception:** `.formLogin(form -> form.loginPage("/login"))` **does not set the post-login success destination**. `loginPage(...)` declares the entry page for the login flow (and the default form processing path per `FormLoginSpec`). To change success/failure destinations, configure **`authenticationSuccessHandler(...)`** and **`authenticationFailureHandler(...)`**.

### 2.1 Request Flow in WebFlux

```text
Browser: GET /app/home (not logged in)
   |
   v
WebFlux SecurityWebFilterChain: unauthenticated
   |
   +--> entry point redirects to GET /login
                     |
                     v
              Spring Security renders form
              with username, password, CSRF token
                     |
                     v
              Browser: POST /login
                     |
                     v
              AuthenticationWebFilter
                     |
             ReactiveAuthenticationManager
                 /             \
           valid auth      invalid auth
              |                  |
              v                  v
   ServerAuthentication  ServerAuthentication
      SuccessHandler        FailureHandler
              |                  |
              v                  v
   HTTP 302 Location:   HTTP 302 Location:
       /app/home             /auth/failed
```

This is a **logical** diagram. Real WebFilters have their own ordering; CSRF can halt a POST before processing credentials, while authorization for the target URL is checked when the browser sends the **next GET**. A redirect handler cannot by itself guarantee the newly logged-in user has permission to access the target page.

## 3. APIs to Remember in Spring Security Reactive

| API / Class | Role |
| --- | --- |
| `ServerHttpSecurity` | WebFlux HTTP security configuration DSL |
| `SecurityWebFilterChain` | WebFlux security WebFilter chain |
| `ServerHttpSecurity.FormLoginSpec` | Configures form authentication inside `.formLogin(form -> ...)` |
| `ServerAuthenticationSuccessHandler` | Reactive contract `onAuthenticationSuccess(WebFilterExchange, Authentication)` returning `Mono<Void>` |
| `ServerAuthenticationFailureHandler` | Reactive contract `onAuthenticationFailure(WebFilterExchange, AuthenticationException)` returning `Mono<Void>` |
| `RedirectServerAuthenticationSuccessHandler` | Post-success redirect handler; checks saved request before fallback location by default |
| `RedirectServerAuthenticationFailureHandler` | Fixed redirect handler after authentication failure |
| `ServerRequestCache` | Saves an interrupted request requiring login so the user can return after logging in |
| `NoOpServerRequestCache` | Cache that does not save/restore requests; used when intentionally enforcing a fixed target |
| `DefaultServerRedirectStrategy` | Performs an HTTP redirect to a `URI` in WebFlux |
| `ReactiveUserDetailsService` / `ReactiveAuthenticationManager` | Validates username/password and produces the authentication result |

**Pick the right stack:** Spring MVC Servlet uses Servlet `HttpSecurity`, `SecurityFilterChain`, `AuthenticationSuccessHandler`, and `HttpServletResponse.sendRedirect(...)`. **Do not use those Servlet APIs** inside WebFlux `ServerHttpSecurity`. When both `spring-boot-starter-web` and `spring-boot-starter-webflux` are present, Spring Boot typically defaults to MVC; confirm the app actually runs WebFlux before applying reactive examples.

## 4. Default Rules and Why Saved Requests Matter

Suppose a user initially opens `/reports/monthly` while not logged in. Security redirects them to `/login`, and the request cache may store `/reports/monthly`. After successful authentication:

1. `RedirectServerAuthenticationSuccessHandler` checks whether there is a URL/request to resume in the request cache.
2. **If a saved request exists**, it can redirect to the stored URL.
3. **If none exists**, it redirects to the fallback location, defaulting to `/` or the path you passed to the constructor.

Therefore:

```java
new RedirectServerAuthenticationSuccessHandler("/app/home");
```

**does not necessarily force every login session to `/app/home`**. This constructor sets the **fallback location**; the handler's Javadoc confirms saved requests take precedence. This often causes tests that "log in directly from `/login`" to pass while a browser that visited a protected link first ends up at a different page.

### 4.1 Three Policy Options

| Product Requirement | Appropriate Solution |
| --- | --- |
| Let users resume the page they wanted before logging in | Keep `ServerRequestCache` and a success handler that handles saved requests |
| **Always** go to `/app/home` upon successful login | Configure `NoOpServerRequestCache` on both the chain and the success handler, or a custom success handler redirecting directly to a fixed URL |
| Destination depends on role, tenant, or business rules | Custom `ServerAuthenticationSuccessHandler` or verified routing; redirect only to **server-allowed** targets |

Never pick a "return URL" directly from a query parameter without validation. If redirecting based on user-supplied data, allowlist internal paths, block absolute URLs to foreign domains or paths like `//attacker.example`, and never let users inject different access permissions into redirect logic.

## 5. Preparing the Practice Project

Create a Spring Boot **3.x**, Java **17+**, Gradle Groovy application, selecting:

- **Spring Reactive Web** — `spring-boot-starter-webflux`;
- **Spring Security** — `spring-boot-starter-security`;
- **Spring Boot Test** — `spring-boot-starter-test`;
- **Spring Security Test** — `spring-security-test`, used for CSRF testing.

The dependencies section of `build.gradle` in a project already configured with the Spring Boot plugin and dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Do not add `spring-boot-starter-web` for this example.** The project uses the WebFlux server and WebFilter chain, not Spring MVC.

File structure:

```text
src/main/java/com/example/redirectlogin/
  RedirectLoginApplication.java
  LoginSecurityConfig.java
  PageController.java
src/test/java/com/example/redirectlogin/
  FormRedirectTest.java
```

Each class is a **separate Java file** in the same `com.example.redirectlogin` package. Do not combine multiple `public class` declarations in one file. With Gradle, run `./gradlew bootRun` or `./gradlew test`. On Windows PowerShell, use `.\gradlew.bat` instead of `./gradlew`.

### 5.1 Startup Class

`src/main/java/com/example/redirectlogin/RedirectLoginApplication.java`:

```java
package com.example.redirectlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RedirectLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(RedirectLoginApplication.class, args);
    }
}
```

`@SpringBootApplication` scans `LoginSecurityConfig` and `PageController` in the same package. The example does not need a template engine because **Spring Security generates a default login page** when you configure form login without changing `loginPage(...)`.

## 6. Configuring Success and Failure Redirects in SecurityWebFilterChain

`src/main/java/com/example/redirectlogin/LoginSecurityConfig.java`:

```java
package com.example.redirectlogin;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.savedrequest.NoOpServerRequestCache;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class LoginSecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        var reader = User.withUsername("reader")
            .password(encoder.encode("reader-demo-password"))
            .roles("READER")
            .build();

        var admin = User.withUsername("admin")
            .password(encoder.encode("admin-demo-password"))
            .roles("READER", "ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    ReactiveAuthenticationManager passwordAuthenticationManager(
            MapReactiveUserDetailsService users,
            PasswordEncoder encoder) {

        var manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain webSecurity(
            ServerHttpSecurity http,
            ReactiveAuthenticationManager passwordAuthenticationManager) {

        // FIXED destination on successful login.
        var success = new RedirectServerAuthenticationSuccessHandler(
            "/app/home"
        );

        // Do not let saved request override "/app/home".
        var noSavedRequest = NoOpServerRequestCache.getInstance();
        success.setRequestCache(noSavedRequest);

        // FIXED destination when username/password authentication fails.
        var failure = new RedirectServerAuthenticationFailureHandler(
            "/auth/failed"
        );

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/login", "/auth/failed", "/public/**")
                    .permitAll()
                .pathMatchers("/admin/**").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .requestCache(cache -> cache.requestCache(noSavedRequest))
            .formLogin(form -> form
                .authenticationManager(passwordAuthenticationManager)
                .authenticationSuccessHandler(success)
                .authenticationFailureHandler(failure)
            )
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .build();
    }
}
```

**Important points in the configuration above:**

1. `.formLogin(form -> ...)` enables form authentication in WebFlux. Without calling `form.loginPage(...)`, Spring Security can generate a default login page at **`GET /login`** and process credentials at **`POST /login`**. The login form uses `username` and `password` fields; a CSRF token must be sent on POST.
2. `.authenticationSuccessHandler(success)` decides the response **after credentials have been verified**. Here `RedirectServerAuthenticationSuccessHandler` sends the client to `/app/home`.
3. `.authenticationFailureHandler(failure)` applies when form authentication **was attempted and failed**, such as a wrong password. The response redirects to `/auth/failed` — this route must exist and be accessible without logging in.
4. `NoOpServerRequestCache` is configured on both the success handler **and** the chain's `requestCache`. As a result, visiting a protected URL before logging in does not cause a successful redirect to prioritize the stored URL; this is a **fixed-destination policy**, not the only way to design form login.
5. `.httpBasic(...disable)` disables HTTP Basic in the **demo chain** to eliminate competing authentication mechanisms. It **does not remove** form login or authorization.
6. `passwordAuthenticationManager` is a `UserDetailsRepositoryReactiveAuthenticationManager` using `MapReactiveUserDetailsService` and `PasswordEncoder`. We configure it explicitly to avoid mistaking the redirect handler for being responsible for checking passwords: **no**, the manager performs authentication.
7. `.pathMatchers("/admin/**").hasRole("ADMIN")` is a post-login authorization policy. `reader` can log in successfully yet still receive **403** when opening the admin page. Success redirects do not replace permission checks on the target URL.
8. `.pathMatchers("/login", "/auth/failed", "/public/**").permitAll()` avoids redirect loops for the login page and failure notice page. `POST /login` must also be allowed to reach the appropriate authentication filter; do not add a rule blocking login POSTs.
9. **CSRF protection is kept intact**, with no `csrf(...disable)`. This is crucial for browser form login. Removing CSRF would shorten the demo, but it is **not** a safe way to teach form login.

**Example limitations:** Demo passwords are written directly in code for learners to run locally. Production should use a trusted user store/IdP, proper password hashing, and secret management; never hardcode real accounts. Form login must use HTTPS/TLS and secure session cookies.

### 6.1 Why Configure the Manager Explicitly?

`MapReactiveUserDetailsService` satisfies the `ReactiveUserDetailsService` contract, whereas a concrete manager processes credentials, checks `PasswordEncoder.matches(...)` and account status, and builds an authenticated `Authentication`. `UserDetailsRepositoryReactiveAuthenticationManager` is Spring Security's built-in manager for reactive user details.

We declare a `ReactiveAuthenticationManager` bean and pass it to `form.authenticationManager(...)` so the example is independent of other auto-configuration defaults that might appear in real projects. With OAuth2 login or JWT Resource Server, the authentication mechanism differs; do not use form redirect handlers as a way to verify tokens yourself.

## 7. Illustrative Endpoints

`src/main/java/com/example/redirectlogin/PageController.java`:

```java
package com.example.redirectlogin;

import org.springframework.http.MediaType;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PageController {

    @GetMapping(
        value = "/public/ping",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> ping() {
        return Mono.just("pong");
    }

    @GetMapping(
        value = "/app/home",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> home() {
        return username().map(name -> "Welcome " + name);
    }

    @GetMapping(
        value = "/admin/home",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> adminHome() {
        return username().map(name -> "Admin area: " + name);
    }

    @GetMapping(
        value = "/auth/failed",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> loginFailed() {
        return Mono.just("Login failed. Return to /login and try again.");
    }

    private Mono<String> username() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
```

**Why is `/auth/failed` a public endpoint?** If a user just entered a wrong password, they **do not yet have a valid authenticated session**. If `/auth/failed` were protected, the post-redirect request would be bounced back to `/login` or an access error, preventing the user from seeing the failure message. Therefore this route is `permitAll` and shows a generic message without revealing whether the username exists.

**Why does `/app/home` still need protection?** Without `anyExchange().authenticated()`, someone who has not logged in could simply type that URL directly. Post-login redirects are only **UX navigation**, not an access policy.

## 8. Running and Observing Redirects with a Browser or curl

From the project directory:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

With the default configuration, the app typically listens at `http://localhost:8080`. Use local HTTP only for practice with fake passwords; production mandates HTTPS/TLS.

### 8.1 Accessing a Protected Endpoint Before Login

```bash
curl -i http://localhost:8080/app/home
```

Expectation matching the form entry point:

```text
HTTP 302 Found
Location: /login
```

The snippet above only illustrates the key **status and Location**; framework versions may include other headers/cookies. HTTP 3xx here is **not a success redirect**, but an **entry point redirect** because the request is unauthenticated.

### 8.2 Opening the Login Page

```bash
curl -i http://localhost:8080/login
```

Without changing `loginPage`, Spring Security generates the default HTML page with a username/password form. This page includes the mechanism to inject the required CSRF token into POSTs in the standard configuration. Instead of manually copying a token from one response and posting from another session, open **`/login` in a browser** and enter:

- Username `reader`; password `reader-demo-password` → login succeeds.
- Enter a wrong password → redirects to `/auth/failed`.

To test manually with curl while keeping CSRF, you must **save the session cookie** from GETting the login page, extract the right `_csrf` hidden field, and send POST with that same cookie:

```text
1. GET /login
   <- Set-Cookie: SESSION=... (if session is created)
   <- HTML form: hidden input name="_csrf", value="..."
2. POST /login
   Cookie: SESSION=...
   Content-Type: application/x-www-form-urlencoded

   username=reader&password=reader-demo-password&_csrf=<token>
3. <- HTTP 302 Location: /app/home
4. GET /app/home with updated session cookie
   <- HTTP 200 body "Welcome reader"
```

This is an **interaction outline**, not raw observed HTTP or a complete shell recipe. Tokens and cookies are generated per session, so substitute real values from the same client. After login, the server may rotate the session identifier for session fixation protection; the client must accept the new cookie if issued.

### 8.3 Failure Flow

If you send POST `/login` with a wrong password but **valid CSRF**:

```text
POST /login (username=reader, password=wrong, valid CSRF)
      -> authentication manager rejects
      -> RedirectServerAuthenticationFailureHandler
      -> HTTP 302 Location: /auth/failed
GET /auth/failed
      -> HTTP 200
      -> Login failed. Return to /login and try again.
```

Because the failure handler redirected, **the POST response may be 302 rather than 401**. Statuses 401/403 usually appear in APIs, Basic/Bearer, or other authentication/authorization policies; **do not try to force form login to return 401 on wrong passwords**.

Invalid CSRF is a different story: the request can receive **403** right at the CSRF WebFilter, before the password manager is called. That case is **not** a "failure redirect to /auth/failed", because it is not a wrong password inside form authentication.

## 9. Testing with WebTestClient and the CSRF Mutator

With `spring-security-test`, you can test form login via a **mock WebFlux application context** without opening a network port. `SecurityMockServerConfigurers.springSecurity()` attaches Spring Security support to `WebTestClient`. `SecurityMockServerConfigurers.csrf()` provides a valid CSRF token for testing a POST that must pass CSRF protection.

Create `src/test/java/com/example/redirectlogin/FormRedirectTest.java`:

```java
package com.example.redirectlogin;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
class FormRedirectTest {

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

    @Test
    void anonymousProtectedPageRedirectsToLogin() {
        client.get()
            .uri("/app/home")
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/login");
    }

    @Test
    void generatedLoginPageIsPublic() {
        client.get()
            .uri("/login")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void validCredentialsRedirectToFixedHome() {
        client.mutateWith(csrf())
            .post()
            .uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "reader"
            ).with(
                "password", "reader-demo-password"
            ))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/app/home");
    }

    @Test
    void invalidCredentialsRedirectToFailurePage() {
        client.mutateWith(csrf())
            .post()
            .uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "reader"
            ).with(
                "password", "wrong-password"
            ))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueEquals(
                HttpHeaders.LOCATION, "/auth/failed");
    }

    @Test
    void missingCsrfIsForbiddenNotPasswordRedirect() {
        client.post()
            .uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "reader"
            ).with(
                "password", "reader-demo-password"
            ))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void failurePageIsPublic() {
        client.get()
            .uri("/auth/failed")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo(
                "Login failed. Return to /login and try again.");
    }

    @Test
    void publicPingDoesNotRequireLogin() {
        client.get()
            .uri("/public/ping")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("pong");
    }
}
```

**Detailed test explanation:**

- `@SpringBootTest(webEnvironment = MOCK)` builds a real application context with beans/configs without needing a real HTTP socket. `WebTestClient.bindToApplicationContext(...).apply(springSecurity())` applies the context's security in tests.
- `mutateWith(csrf())` from `spring-security-test` prepares a request with a valid CSRF token for the **mock exchange**. It **does not replace** browser or live HTTP server tests of cookies/sessions/CSRF when end-to-end verification is needed.
- Form POST uses `Content-Type: application/x-www-form-urlencoded` and `username` and `password` fields. If you send a JSON body without changing the converter, default form login will not read the data as you expect.
- `expectStatus().is3xxRedirection()` does not assume a single exact status like 302/303/307 across all custom strategies; `expectHeader().valueEquals(Location, ...)` verifies the **redirect destination**, the focus of this lesson.
- The invalid-credentials test has **valid CSRF** so it reaches the authentication failure handler. The missing-CSRF test checks the **403** response, which must not be conflated with a wrong password.
- These tests **do not prove that sessions are persisted and reused across real requests**. To prove that, add a live server test retaining cookies/sessions after POST, or test in a browser.
- If using multiple `SecurityWebFilterChain`s in a real app, the mock context must include the right chain and matcher; a test slice importing only the Controller can bypass security config.

Run with Gradle:

```bash
./gradlew test --tests '*FormRedirectTest'
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests '*FormRedirectTest'
```

The 3xx/403/200 results in the tests are **expectations from the example configuration**. If a project has replaced the login page, request matcher, csrf repository, session management, or success handler, use the corresponding values; never copy tests and strip out security features just to make tests green.

## 10. Keep Saved Request or Fixed Redirect?

Both policies provide different experiences and each has suitable use cases.

### 10.1 Policy A: Return to the URL the User Wanted Before Login

If you want users opening `/reports/monthly`, getting prompted to log in, and then returning to that exact page, keep `WebSessionServerRequestCache` and a success handler supporting saved requests.

Example **replacement configuration snippet**:

```java
var success = new RedirectServerAuthenticationSuccessHandler(
    "/app/home"
);

// DO NOT call success.setRequestCache(NoOpServerRequestCache.getInstance()).
// Keep request cache and compatible request-cache filter.
return http
    .authorizeExchange(ex -> ex
        .pathMatchers("/login", "/auth/failed").permitAll()
        .anyExchange().authenticated())
    .formLogin(form -> form
        .authenticationSuccessHandler(success)
        .authenticationFailureHandler(
            new RedirectServerAuthenticationFailureHandler(
                "/auth/failed")))
    .build();
```

This snippet only **illustrates the return portion of the security bean**, and needs imports and the manager/user store as in the main example. When a saved request exists, the saved URL may take precedence over `/app/home`; on direct login, the fallback remains `/app/home`. Decide how to handle the original GET URL, sensitive query params, missing role permissions, and multiple tabs sharing the same session.

**Recommendation:** Only restore URLs within the trusted application scope; never blindly accept external URLs from clients. If the app sits behind a proxy, control forwarded headers and hosts to prevent redirects to spoofed hosts.

### 10.2 Policy B: Always Redirect to the Dashboard

The main example in section 6 implements this policy in two places:

```java
var cache = NoOpServerRequestCache.getInstance();
var success = new RedirectServerAuthenticationSuccessHandler(
    "/app/home"
);
success.setRequestCache(cache);

http.requestCache(requestCache -> requestCache.requestCache(cache));
```

This is a **snippet** inside the configuration method. Effect:

- Security does not store the target request in this flow's request cache.
- The success handler does not pick a saved request to override `/app/home`.
- Users entering valid credentials receive a redirect to the fixed target.
- Access to `/app/home` must still be controlled by `authorizeExchange`.

**Important:** "Not saving a saved request" **does not mean "not using WebSession"**. Form login can still save `SecurityContext` in `WebSessionServerSecurityContextRepository` so users do not have to re-send passwords on every request. Do not replace `ServerSecurityContextRepository` with NoOp just because you want a fixed redirect target: doing so can make login succeed while the very next request loses identity.

## 11. Role-Based Redirect Destination: Advanced Example

When users with `ROLE_ADMIN` should go to `/admin/home` while regular users go to `/app/home`, you can write a `ServerAuthenticationSuccessHandler` that picks a **server-controlled internal path**.

The code below is a **success handler replacement snippet** for `LoginSecurityConfig`, not a complete standalone class:

```java
import java.net.URI;

import org.springframework.security.web.server.DefaultServerRedirectStrategy;
import org.springframework.security.web.server.ServerRedirectStrategy;
import org.springframework.security.web.server.authentication.ServerAuthenticationSuccessHandler;

ServerRedirectStrategy redirects = new DefaultServerRedirectStrategy();

ServerAuthenticationSuccessHandler successByRole =
    (webFilterExchange, authentication) -> {
        boolean admin = authentication.getAuthorities().stream()
            .anyMatch(authority ->
                "ROLE_ADMIN".equals(authority.getAuthority()));

        URI destination = URI.create(
            admin ? "/admin/home" : "/app/home"
        );

        return redirects.sendRedirect(
            webFilterExchange.getExchange(), destination
        );
    };

// Inside formLogin(...) of the SecurityWebFilterChain bean:
.formLogin(form -> form
    .authenticationManager(passwordAuthenticationManager)
    .authenticationSuccessHandler(successByRole)
    .authenticationFailureHandler(
        new RedirectServerAuthenticationFailureHandler(
            "/auth/failed")))
```

**Do not paste the entire snippet above after `http.build()`.** To compile, move the imports to the top of the Java file, place `redirects` and `successByRole` **inside the configuration method**, and replace the `formLogin(...)` section of the main example. This pattern uses the proper reactive API `ServerRedirectStrategy.sendRedirect(ServerWebExchange, URI)`, **not** Servlet's `RedirectStrategy.sendRedirect(HttpServletRequest, HttpServletResponse, String)`.

Notes:

1. The `Authentication` entering the success handler must be the **authenticated result from the authentication manager**; never take roles from a query parameter `role=admin`.
2. Use only server-defined path lists. Never concatenate strings like `"/" + request.getQueryParams().getFirst("next")` to redirect, as that risks open redirects, path traversal, or routing to unintended areas.
3. `/admin/home` must still have a `hasRole("ADMIN")` rule. Choosing an admin redirect page **is not** a role-granting mechanism. Even if the server picks the wrong path, authorization must still block it.
4. A custom success handler like the one above **does not automatically handle saved requests**. It redirects directly; if returning to saved requests is needed, explicitly design precedence and use `ServerRequestCache` properly.
5. Never write blocking I/O logic inside a reactive handler; if you need to look up roles/tenants from a reactive repository, compose `Mono.flatMap(...)` and return `Mono<Void>`, never `block()`.
6. In Spring Security 6.3+, `FormLoginSpec.authenticationSuccessHandler(Consumer<List<ServerAuthenticationSuccessHandler>>)` can compose a list of handlers; when using it, understand ordering and semantics. This simple lesson uses the **single-handler** overload to avoid overlapping behaviors.

## 12. Changing the Login Page and Changing Redirect Targets Are Independent Operations

If you need a custom UI at `GET /sign-in`, you can write:

```java
.formLogin(form -> form
    .loginPage("/sign-in")
    .authenticationSuccessHandler(
        new RedirectServerAuthenticationSuccessHandler("/app/home"))
    .authenticationFailureHandler(
        new RedirectServerAuthenticationFailureHandler(
            "/sign-in?error")))
```

This is a **configuration snippet to explain the API**, not yet a complete application. After calling `.loginPage("/sign-in")`:

- Spring Security **no longer auto-generates the default login page** for the new path.
- The application must actually provide `GET /sign-in` and an appropriate HTML page/response.
- Per `FormLoginSpec` in Spring Security 6.x, credential-handling POSTs default to **`/sign-in`** with such a custom login page.
- The form must send `username`, `password`, and a valid CSRF token; show an error message when the `error` query parameter is present.
- Add `/sign-in` and related pages to the public routes list; otherwise a redirect loop can occur.
- If you still want a fixed success path, mind the saved request as in section 10. Changing `loginPage` alone does not change saved-request policy.

If using Thymeleaf templates, the library offers convenient CSRF integration. If building plain HTML/SPA, retrieve the valid CSRF token from WebFlux `ServerWebExchange` or the configured repository and add a hidden input or valid header; never copy a static token into HTML. Spring Security 6.x uses BREACH-protected CSRF request handling, so how raw/masked tokens are exposed must match the active handler.

## 13. Distinguishing Failures Beyond Wrong Passwords

Not every 3xx/401/403 status invokes `ServerAuthenticationFailureHandler`:

| Scenario | Responsible Component | Typical Result in Lesson |
| --- | --- | --- |
| GET protected while unauthenticated | Authentication entry point | 302 to `/login` |
| POST `/login` missing CSRF | CSRF protection | 403, **does not** redirect to `/auth/failed` |
| POST `/login` wrong password | Authentication manager → failure handler | 302 to `/auth/failed` |
| POST `/login` right password | Authentication manager → success handler | 302 to `/app/home` |
| Reader accesses `/admin/home` after login | Authorization | 403 |
| GET `/auth/failed` while unauthenticated | `permitAll` rule | 200 |
| Accessing `/app/home` after session expiration | Authentication entry point | Typically redirects to `/login` |
| GET URL with no handler, not blocked by security | WebFlux routing | 404 |

If the target is a **REST API** called by `fetch`/`WebClient` expecting JSON errors, browser-style redirects may be inappropriate: clients might auto-follow 302 and receive HTML instead of a 401/403 JSON response. For APIs, use a `ServerAuthenticationEntryPoint`/failure handler suited to the request type, or a dedicated security chain for APIs; for browsers, use form login and redirects.

### 13.1 CSRF Is Not a Password Failure

When CSRF is missing, the POST request is blocked at the CSRF layer, so there is no basis for invoking `RedirectServerAuthenticationFailureHandler`, which handles authentication failures. Never add `csrf(csrf -> csrf.disable())` just to make a test POST return 302. In mock tests, use `mutateWith(csrf())`; in browsers, use the token supplied by the framework.

### 13.2 Access Denied Is Not a Login Failure

When already authenticated but lacking admin permissions, the server should return 403 (or a response from the access denied handler), rather than sending the user back to "wrong password", which both confuses users and complicates security investigations. Customize 403 via exception handling/access-denied configuration, not by modifying `authenticationFailureHandler`.

### 13.3 Error URLs Should Hide Sensitive Causes

Never put `?username=alice&reason=user-not-found`, `?password=...`, or exception messages in `Location`. URLs are saved in browser history, proxy logs, referrers, analytics, and screenshots. The error page should only show a generic message: "Unable to sign in. Please check your details or try again." Meanwhile, write structured security logs on the backend **without passwords/tokens**; distinguish account locks, rate limits, and bad credentials per policy.

## 14. Securing Redirects and WebSession in Production

### 14.1 Preventing Open Redirects

An **unsafe** example:

```java
String next = exchange.getRequest().getQueryParams().getFirst("next");
return redirects.sendRedirect(exchange, URI.create(next));
```

This is a **warning snippet** and must not be put into an application. If `next` comes from the user, its value could be `https://attacker.example` or `//attacker.example`. A freshly logged-in client could be sent to a spoofed site mimicking the real app. If a `returnUrl` is required, enforce a **structured allowlist**:

- Accept only allowed internal paths (e.g., a set like `/app/home`, `/reports`, `/settings`); reject arbitrary URL schemes/hosts.
- Normalize paths, reject backslashes/double-slashes/control characters, and handle percent-encoding consistently with the actual router.
- Never use role/tenant from a query param as the source of permission decisions.
- Check authorization at the **destination URL**, not just when picking the redirect.
- Account for trusted proxy headers, HTTPS, and host validation.
- Never put tokens/passwords/PII into the Location URL.

### 14.2 Distinguishing Session from Request Cache

`WebSessionServerSecurityContextRepository` can save `SecurityContext` after login so subsequent requests recognize the user via the session cookie. `WebSessionServerRequestCache` is a **different** mechanism used to remember a previously requested URL for post-login redirects. Choosing `NoOpServerRequestCache` **does not delete the login session**.

If customizing `.securityContextRepository(...)` on form login, ensure the component loading context on subsequent requests uses a compatible repository. Switching to a NoOp repository in a browser session flow can cause POST login to succeed and redirect properly, yet GET on the destination page bounces right back to login.

### 14.3 Session Fixation, Cookies, and Logout

Production applications must verify session fixation protection, lifetimes, `Secure`/`HttpOnly`/`SameSite` cookies, TLS termination at reverse proxies, and logout. A 302 redirect **does not prove** that session cookies are secure or that login remains active after a reload. Real browser/cookie-retaining tests are essential when integrating with real proxies and domains.

If using OAuth2/OIDC login, success/failure handlers for the OAuth2 flow can be configured on `oauth2Login(...)` or corresponding classes; modifying `formLogin(...)` **does not automatically** alter OAuth2 callbacks/redirects. Distinguish username/password forms from logging in via an external Identity Provider.

## 15. Real-World Troubleshooting

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| Login succeeds but redirects to old page instead of `/app/home` | Saved request took precedence | Check `RedirectServerAuthenticationSuccessHandler.setRequestCache` and `http.requestCache(...)` |
| Login succeeds but GET `/app/home` goes back to `/login` | Session/security context not saved or cookie dropped | Check `ServerSecurityContextRepository`, cookies, session, proxy, multiple instances |
| Wrong password returns 403 instead of redirecting to `/auth/failed` | Missing CSRF token or POST blocked before authentication | Check `_csrf` field, same session, and CSRF config |
| GET `/auth/failed` redirects to login | Failure route is not `permitAll` | Add public rule for failure route and test separately |
| 404 after 302 to destination | Target controller/route does not exist | Create `GET` handler at the right URL, check mappings |
| After changing `loginPage("/sign-in")` form cannot log in | App does not render page or form action is still `/login` | Check GET + POST paths, CSRF, and form field names |
| Browser enters a redirect loop | `/login` or error page is protected, or session broken | Check authorization rules, session cookie, matchers |
| JavaScript API receives unexpected HTML | Form login redirects suit browsers, not APIs | Split security chain for APIs with JSON 401/403 |
| Reader can enter admin page | `anyExchange().authenticated()` shadows admin rule | Admin rule must come before broad matchers |
| Sensitive failure reason appears in URL | Failure handler injects exception message | Fixed redirect URL, generic message |
| Login works in mock tests but browser still fails | Mock CSRF/session differs from real HTTP flow | Check cookies, HTTPS, reverse proxy, real browser flow |
| Redirect handler does not run even on POST with password | Form login filter does not match path, or auth failed before filter | Check `requiresAuthenticationMatcher`, form action, CSRF, active security chain |

**Concise diagnostic workflow:** Identify which request produced 302/403 → inspect `Location`/response headers → check the active security matcher → distinguish entry point, authentication success/failure, and access denied → check CSRF/session → only then inspect controllers. Never start by randomly changing URLs and disabling security.

## 16. Extended Practice Exercises

### Exercise A: Remove the No-Op Request Cache

Remove both `NoOpServerRequestCache` configurations and keep `new RedirectServerAuthenticationSuccessHandler("/app/home")`. Open `/admin/home` while unauthenticated, then log in as `reader`. Think: if the saved request returns to `/admin/home`, the user will get **403** because they lack the ADMIN role. That is the right outcome: **redirects do not grant permissions**. Logging in as `admin` afterwards will allow entering the admin page.

When doing this exercise, standalone mock tests do not fully simulate saved requests across multiple browser requests. Run with a real browser or cookie/session-preserving tests and compare the two policies.

### Exercise B: Change the Failure Page

Switch the failure redirect from `/auth/failed` to `/login?error`:

```java
new RedirectServerAuthenticationFailureHandler("/login?error");
```

With the default login page, the `error` query parameter usually triggers the failure notice. Ensure the failure route stays accessible and re-test `Location`. If changing to `/sign-in?error`, you must render the custom login page yourself as in section 12.

### Exercise C: Role-Based Destination

Replace the fixed success handler with `successByRole` from section 11. Log in separately as reader and admin and verify the respective redirect destinations. Add a test confirming `GET /admin/home` only returns 200 when the session has `ROLE_ADMIN`; users lacking permission must be denied even if they type the URL manually.

### Exercise D: Handling an App Behind a Reverse Proxy

Suppose the app is exposed externally at `https://example.invalid/portal` while the internal server sees a different path. Check context path/base path, trusted forwarded headers, and how the strategy handles relative redirects. Never read `Host`/`X-Forwarded-Host` from a client without a trusted proxy to build absolute redirects. If cross-domain redirects are needed for SSO integration, use standard OAuth2/OIDC flows and registered redirect URI allowlists.

## 17. Self-Check Questions

**Q1.** Why is `.formLogin(form -> form.loginPage("/sign-in"))` not enough to send users to the dashboard after successful authentication?

**A:** `loginPage` specifies the login page. Success is handled by `ServerAuthenticationSuccessHandler`, not the login page setting. Use `authenticationSuccessHandler(...)`.

**Q2.** If you created `new RedirectServerAuthenticationSuccessHandler("/app/home")`, will every login always go to `/app/home`?

**A:** Not necessarily. The handler can prioritize a URL in `ServerRequestCache`. If a fixed destination is required, configure an appropriate no-op cache or a custom handler that ignores saved requests.

**Q3.** Does a wrong password necessarily return 401?

**A:** No. With browser-style form login, `ServerAuthenticationFailureHandler` usually returns a 3xx redirect to an error page. HTTP Basic/Bearer APIs have different challenge/status mechanisms.

**Q4.** Sending POST `/login` with the right password but missing `_csrf` returns 403. Is the failure handler broken?

**A:** You cannot conclude that yet. The CSRF filter may reject before authentication. Supply a valid CSRF token from the same session before testing the success/failure handlers.

**Q5.** Why should `/auth/failed` be `permitAll`?

**A:** Someone who just failed authentication does not have a trusted principal yet. If the error URL requires login, the system may redirect back to the login page or create a loop.

**Q6.** Does a success handler sending a user to `/admin/home` mean the user was granted the ADMIN role?

**A:** No. Authorization on the target URL decides permissions. The redirect handler only creates an HTTP response; it does not modify authorities.

**Q7.** Does `NoOpServerRequestCache` mean "deleting the login session"?

**A:** No. The request cache serves the return URL; `ServerSecurityContextRepository` serves SecurityContext/sessions. Those are two separate responsibilities.

**Q8.** Can you redirect to an arbitrary `next` query parameter?

**A:** That is unsafe due to **open redirect** risk. Only accept URLs/paths validated by a server allowlist, checking host/path and permissions on the target endpoint.

**Q9.** If a POST success test lacks CSRF, what is the right fix?

**A:** Supply a valid CSRF token (`mutateWith(csrf())` when using mock WebTestClient with Spring Security test support); do not disable CSRF globally.

**Q10.** How do you verify the destination page truly works after login?

**A:** Beyond asserting that POST returns 3xx and Location, send a follow-up GET with preserved cookies/session in a browser or live HTTP test, and confirm 200 along with the corresponding permission policy.

## 18. Project Adoption Checklist

- [ ] Server runs **Spring WebFlux reactive**; uses `ServerHttpSecurity` and `SecurityWebFilterChain` instead of the Servlet DSL.
- [ ] **Entry point redirect**, **authentication success redirect**, **authentication failure redirect**, and **access denied** are clearly separated.
- [ ] `.formLogin(...)` properly declares `authenticationSuccessHandler` / `authenticationFailureHandler`.
- [ ] Decided between keeping saved requests or a fixed dashboard; saved URLs do not accidentally override the desired target.
- [ ] Login and failure page URLs are public; actual URLs exist with matching GET controllers/handlers.
- [ ] User/password are verified via `ReactiveAuthenticationManager` and a valid encoder; authenticated principals are never forged from client input.
- [ ] CSRF is enabled and form POSTs include a valid CSRF token.
- [ ] Protected destination URLs still enforce authorization; redirects are never used to grant permissions.
- [ ] Never construct arbitrary Location URLs from `next`, `returnUrl`, `Host`, or unverified claims.
- [ ] Failure messages do not expose account existence, passwords, tokens, or exception details.
- [ ] Tests cover 3xx status, `Location`, CSRF 403, public failure page, and success path.
- [ ] Login sessions are tested separately via browser/cookies, proxies, TLS, and logout during deployment.
- [ ] If serving both APIs and browsers in the same system, HTML redirect responses are cleanly separated from JSON 401/403 when needed.

**Conclusion:** In Spring Security WebFlux, changing where form login goes afterwards must be configured on `ServerAuthenticationSuccessHandler` and `ServerAuthenticationFailureHandler` of `ServerHttpSecurity.formLogin(...)`. `RedirectServerAuthenticationSuccessHandler` can prioritize a **saved request** before its fallback URL; if you need a fixed destination, handle the request cache deliberately. Never disable CSRF, drop the session security context, or open external redirects just to achieve a 302 result. Verify **`Location`**, **session**, and **permissions on the target URL**.

### Official References

- [Spring Security 6.5 — ServerHttpSecurity.FormLoginSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html)
- [Spring Security 6.5 — RedirectServerAuthenticationSuccessHandler](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html)
- [Spring Security 6.5 — RedirectServerAuthenticationFailureHandler](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/authentication/RedirectServerAuthenticationFailureHandler.html)
- [Spring Security 6.5 — RequestCacheSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.RequestCacheSpec.html)
- [Spring Security 6.5 — NoOpServerRequestCache](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/savedrequest/NoOpServerRequestCache.html)
- [Spring Security 6.5 — CSRF in WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security 6.5 — Setting Up WebTestClient with Spring Security](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/setup.html)
- [Spring Security — Testing Reactive CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html)
- [Spring Security 6.5 — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
