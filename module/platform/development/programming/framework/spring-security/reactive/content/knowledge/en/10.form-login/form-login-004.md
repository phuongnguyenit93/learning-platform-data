# Reading Form Data and Authenticating Users in WebFlux

## 1. Problem Statement and Objectives

When a user opens a login page, enters a **username/password**, and clicks "Log in", the browser typically sends an HTTP POST with content type `application/x-www-form-urlencoded`. In Spring WebFlux, reading form data happens **asynchronously**; Spring Security reactive includes a built-in login processing pipeline to turn the form into an authentication request, verify the password, place the authenticated identity into `SecurityContext`, and maintain the login session when needed.

The core point is separating two tasks:

1. **Form decoding:** turning the HTTP body into name-value pairs, such as `username=reader&password=...`.
2. **Authentication:** using a trusted user source and password encoder to verify the username/password, never trusting the client to self-assert its identity.

**Do not write a `POST /login` controller that reads passwords and creates sessions yourself if Spring Security `formLogin` already meets your needs.** The built-in mechanism performs many easily overlooked steps such as error handling, CSRF, context management, and cookies/sessions.

After this lesson, you will:
- Understand `ServerWebExchange.getFormData()`, `Mono<MultiValueMap<String,String>>`, and how they differ from JSON/multipart.
- Explain the reactive login pipeline: `formLogin` → `AuthenticationWebFilter` → converter → `ReactiveAuthenticationManager` → `SecurityContext`.
- Configure `ReactiveUserDetailsService`, `PasswordEncoder`, and `SecurityWebFilterChain` for form login.
- Distinguish unauthenticated requests, wrong passwords, missing CSRF tokens, and authenticated users lacking permissions.
- Run a Java 17+ example with Spring Boot WebFlux, checking browser behavior and `WebTestClient`.
- Know when a custom login form is needed and how to avoid leaking passwords/sessions.

## 2. How Does the Form Login Flow Work?

Suppose the application has `/account` requiring login:

~~~text
Browser                 Spring Security WebFlux                  User store
     │                                │                                  │
     ├── GET /account ───────────────►│                                  │
     │              unauthenticated   │                                  │
     ◄───────── 302 /login ───────────┤                                  │
     │                                │                                  │
     ├── GET /login ─────────────────►│                                  │
     ◄──── HTML form + CSRF token ────┤                                  │
     │                                │                                  │
     ├── POST /login ────────────────►│                                  │
     │   Content-Type: application/   │                                  │
     │     x-www-form-urlencoded      │                                  │
     │   username, password, _csrf    │                                  │
     │                                ├── verify CSRF                    │
     │                                ├── read formData reactively       │
     │                                ├── create unauthenticated Authentication
     │                                ├── manager.authenticate(...) ────►│
     │                                │                 look up user/hash│
     │                                ◄──── authenticated Authentication ┤
     │                                ├── save context to appropriate session
     │                                └── success handler / redirect     │
     ◄──────── 302 + session cookie ──┤                                  │
     │                                │                                  │
     ├── GET /account + cookie ──────►│                                  │
     │                                ├── load saved context             │
     │                                └── check authenticated()          │
     ◄──────── 200 Hello reader ──────┤                                  │
~~~

Some important details:

- **`GET /login` does not require authentication.** It returns an HTML page for the user to fill in the form; Spring Security can generate the default page.
- **`POST /login` is the default authentication attempt** when `formLogin` is enabled. Default fields are `username` and `password`.
- **CSRF is checked before processing login** for POST requests: a missing/invalid token can return HTTP 403 even if the username/password are right.
- The manager uses a password encoder to compare the client-submitted **raw password** against the stored **password hash**; never compare the raw password directly with the hash string.
- Successful authentication does not automatically grant access to every URL; `authorizeExchange` still checks roles/authorities.
- In regular form login, the context can be stored in **WebSession** so subsequent requests retain the identity. Reactor Context is only the context for a single subscription/request and does not automatically replace a session.
- The redirect outcome may return to the previous page or a default URL depending on the saved request/success handler; do not hardcode that every login always goes to `/`.

## 3. Reading Forms in WebFlux with `getFormData()`

### 3.1. Signature and Data Type

`org.springframework.web.server.ServerWebExchange` provides:

~~~java
Mono<MultiValueMap<String, String>> getFormData();
~~~

`MultiValueMap` differs from `Map<String,String>` in that **each key can have multiple values**. Example body:

~~~text
username=reader&password=reader-pass&remember=on&remember=yes
~~~

After parsing:
- `getFirst("username")` returns `"reader"`.
- `getFirst("password")` returns `"reader-pass"`.
- `get("remember")` can return the list `["on","yes"]`.

Using the API:

~~~java
Mono<String> username = exchange.getFormData()
    .map(form -> form.getFirst("username"));
~~~

**This is only an illustrative snippet**, assuming `exchange` is a valid `ServerWebExchange` and `reactor.core.publisher.Mono` is imported. This snippet has not verified any password; form data remains **untrusted**.

`getFormData()`:
- Processes bodies with `Content-Type: application/x-www-form-urlencoded`; for other content types, it typically returns an empty map.
- Uses WebFlux's `HttpMessageReader` to read and parse the body.
- Returns a `Mono`, so you chain with `map` / `flatMap`; never `block()` on the event loop.
- Parses and caches form data per `ServerWebExchange` contract, so calling `getFormData()` multiple times on the same exchange is supported. **Do not use that as a reason to proactively re-read passwords across multiple layers**: limit where secrets are handled.
- Form bodies are typically read/parsed in full; body size and memory must be bounded via appropriate codec/web server configuration.

### 3.2. Example Endpoint Reading Non-Sensitive Form Data

To learn how to read forms without touching login, here is **an illustrative handler snippet**, not included in the runnable project in section 8:

~~~java
@PostMapping(
    path = "/feedback",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
Mono<String> feedback(ServerWebExchange exchange) {
    return exchange.getFormData().map(form -> {
        String title = form.getFirst("title");
        if (title == null || title.isBlank()) {
            return "Missing title";
        }
        return "Received feedback title";
    });
}
~~~

Corresponding imports include `org.springframework.http.MediaType`, `org.springframework.web.bind.annotation.PostMapping`, and `org.springframework.web.server.ServerWebExchange`. The example only receives a form title and contains no password.

**Do not** replace `title` with `password` and then log, echo back, or store the raw password. In regular business endpoints, validate input, CSRF, size limits, and authorization separately.

### 3.3. `@RequestParam`, `@RequestBody`, and `multipart/form-data`

- `@RequestParam` in WebFlux annotated controllers primarily reads query parameters; **do not assume it automatically handles form bodies the same way as Spring MVC Servlet**. To read URL-encoded forms in WebFlux, use `ServerWebExchange.getFormData()` or `ServerRequest.formData()` (functional endpoints).
- `@RequestBody Mono<MyDto>` fits JSON and media types supported by decoders. It is not a direct equivalent to extracting fields from an HTML form in `formLogin`.
- `multipart/form-data` uses `getMultipartData()` or `Part`-handling APIs, **not** `getFormData()`. Do not use multipart by default for receiving ordinary passwords.
- Query string `?password=...` is unsafe: it easily enters URL logs/history/referrers. Standard form login uses a POST body, and all real traffic must use HTTPS.

## 4. Built-in `formLogin` Mechanism: No Need to Write a POST /login Controller

With Spring Security WebFlux:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/", "/about").permitAll()
            .anyExchange().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

This is an **excerpt configuration snippet**, requiring imports/beans in a WebFlux application. Calling `formLogin(...)` enables the form-based login pipeline. When using the default page:
- `GET /login`: Spring Security generates the login page.
- `POST /login`: the form login `AuthenticationWebFilter` receives login credentials.
- The basic fields are `username` and `password`.
- Login failures due to credentials usually redirect to `/login?error`.
- Successful logins usually redirect to the saved URL or a default target.
- CSRF is enabled by default; the generated login page handles the token.
- Form login typically uses `WebSessionServerSecurityContextRepository` to save authentication across requests along with the corresponding context-loading mechanism.

Clear separation of responsibilities:

| Component | Function |
| --- | --- |
| `ServerHttpSecurity.formLogin(...)` | Creates/configures the form login mechanism |
| `AuthenticationWebFilter` | Orchestrates an authentication attempt when a request matches the matcher |
| `ServerFormLoginAuthenticationConverter` | Reads username/password from the form and turns them into an **unauthenticated** authentication |
| `ReactiveAuthenticationManager` | Checks credentials and produces a trusted authentication |
| `ReactiveUserDetailsService` | Looks up account/UserDetails by username from a trusted source |
| `PasswordEncoder` | Compares the client password against the stored password hash |
| `SecurityContext` | Holds the authenticated `Authentication` |
| `WebSessionServerSecurityContextRepository` | Saves/loads context via WebSession when session-based form login is configured |
| `authorizeExchange(...)` | Checks URI access permissions based on state and authorities |

**Version note:** Spring Security 6.x API docs describe `ServerFormLoginAuthenticationConverter`. Do not accidentally copy Servlet's `UsernamePasswordAuthenticationFilter` or `HttpSecurity` into a WebFlux project. WebFlux uses `ServerHttpSecurity`, `SecurityWebFilterChain`, and `WebFilter`.

### 4.1. Unauthenticated → Authenticated Authentication

When the form has `username` and `password`:
1. The converter produces an **unauthenticated** `UsernamePasswordAuthenticationToken`.
2. The manager looks up the user, checks account status, and calls `PasswordEncoder.matches(raw, hash)` per the configured mechanism.
3. Password matches → creates an authenticated `Authentication` with authorities from the backend.
4. Wrong password/missing user → emits `AuthenticationException`; the failure handler handles it.
5. On success, `Authentication` enters `SecurityContext`, and Spring Security applies authorization on the current request and later when loading the appropriate session.

**Do not manually call** `UsernamePasswordAuthenticationToken.authenticated(username, password, clientRoles)` from form data. That factory is for the result **after verification**; using it before verification is an authentication-bypass bug.

### 4.2. Login Matcher Differs from Authorization Rules

- The form login matcher determines **which request triggers the login process**: default POST `/login`.
- `authorizeExchange(...).pathMatchers("/account").authenticated()` determines **which URLs require a logged-in user**.
- `permitAll` for `GET /login` does not verify the user; it only permits access to the login page.

A request to `/account` requiring authentication is **not** the request where the converter reads username/password from the form. Spring Security handles two different requests: the initial request leads to a redirect, and afterwards the browser POSTs the login form.

## 5. CSRF Is Part of Form Login, Not an Ancillary Bug

Cookie/session-based login is exposed to **login CSRF** and unintended state-changing requests. Spring Security WebFlux enables CSRF protection by default and requires a valid token for POST (including POST login), PUT, PATCH, DELETE, etc., unless an intentional exception is configured.

The HTML form submitting a POST must contain a matching CSRF token, usually a hidden input named `_csrf`. The default login page generated by Spring Security normally prepares the token already. With custom templates, you must render the token from the corresponding reactive CSRF mechanism.

In WebFlux:
- `CsrfWebFilter` is responsible for validating the token.
- `ServerCsrfTokenRepository` manages the token per configuration; the default usually uses `WebSessionServerCsrfTokenRepository`.
- Spring Security 6.x includes a request handler mechanism to strengthen BREACH protection for tokens in HTML; **do not guess the token value from a cookie and assume it works in every configuration**.
- `Mono<CsrfToken>` can be placed by the framework into exchange attributes for template renderers to access per contract. Use the official integration when using a template engine.
- `POST /login` with a missing or wrong token can return 403 **even before the password-comparison step**.

### 5.1. Three States to Distinguish

| Request | Expected Outcome in Demo |
| --- | --- |
| `GET /login` | 200, HTML form page |
| `POST /login` with right username/password but missing CSRF token | 403 Forbidden |
| `POST /login` with valid CSRF token, wrong password | Redirect to `/login?error` (usually 302) |
| `POST /login` with valid CSRF token, right password | Success redirect (usually 302) and session established |
| `GET /account` without authenticated session | Redirect to login |
| `GET /account` with valid authenticated session | 200 |

If you encounter HTTP 403 during login, **do not jump to concluding the password is wrong**. Inspect Content-Type, CSRF token, session cookie, POST path, and security filter order.

### 5.2. Form Login and JSON APIs Do Not Share the Same Contract

A JSON API `POST /api/login` with body `{"username":"...", "password":"..."}` is **not automatically understood** by the default form login converter. Likewise, sending JSON to POST `/login` is not equivalent to submitting an HTML form.

If a real product design genuinely needs JSON authentication:
- Define an explicit API spec and CSRF/session/token policy.
- Use an appropriate `ServerAuthenticationConverter` and `ReactiveAuthenticationManager`, or an established standard authentication approach.
- Check validation, origin, brute-force mitigation, success/failure responses, and never manually subscribe/block inside a filter.
- Do not disable CSRF "to make testing easier" if browsers still use cookies/sessions.

## 6. Session, Reactor Context, and Login Lifecycle

There are at least three constructs that must not be equated:

| Construct | Scope | Role |
| --- | --- | --- |
| `SecurityContext` | Within Spring Security | Holds the current `Authentication` |
| **Reactor Context** | Per reactive subscription | Propagates security data in the pipeline without relying on a fixed ThreadLocal |
| **WebSession** | Can persist across multiple HTTP requests | Stores state such as security context via cookie/session ID depending on repository |

With default form login, Spring Security typically configures `WebSessionServerSecurityContextRepository` to **save the security context after login** and reload it on subsequent requests. The browser carries the session cookie on follow-up requests. If the client drops the cookie, or the session expires/is deleted, a request may be treated as unauthenticated even though an earlier login returned 302.

In a reactive handler:

~~~java
Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(context ->
            Mono.justOrEmpty(context.getAuthentication()))
        .map(Authentication::getName);
}
~~~

This is an **illustrative method snippet**: it must run inside a Java class with corresponding imports. `getContext()` returns a publisher, not a synchronous `SecurityContext`.

**Do not use** `SecurityContextHolder.getContext()` assuming Servlet ThreadLocal to read request identity across WebFlux branches. Also do not manually call `block()` or `subscribe()` in a controller to obtain the username; return a `Mono` so Reactor/Spring manages the subscription and context.

Session-based form login differs from stateless Bearer JWT APIs: in a stateless model, the client usually sends a token on every request and the server re-verifies it; with form login, browsers may use cookies/sessions. The two models require different CSRF and logout policies.

## 7. Building a Runnable Application with Java 17+ and Spring Boot WebFlux

The demo uses **Spring Boot 3.3.13**, Java 17+, Gradle 8.x, and Spring Security reactive. Versions are pinned to illustrate consistent APIs, not as a recommendation to use out-of-support versions in production. In new projects, choose a currently supported Spring Boot line and verify compatibility.

We will use the **default login page** to focus on reading forms/authentication rather than hand-rolling UI and forgetting CSRF. All endpoints defined by the application are GETs.

### 7.1. Directory Structure

~~~text
webflux-form-login-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── FormLoginApplication.java
    │   ├── SecurityConfig.java
    │   └── DemoController.java
    └── test/java/demo/
        └── FormLoginTests.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-form-login-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Dependency notes:
- `spring-boot-starter-webflux`: reactive server, Reactor, and WebFlux.
- `spring-boot-starter-security`: Spring Security, WebFlux configuration, form login.
- `spring-security-test`: supports `WebTestClient` with mock CSRF/spring security in integration tests; test scope only.
- Do not add `spring-boot-starter-web` (Servlet/MVC) because Boot may pick the Servlet stack when both starters are present.
- Do not add Thymeleaf in this demo since we use the login page generated by Spring Security.

### 7.2. Startup Class

`src/main/java/demo/FormLoginApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormLoginApplication.class, args);
    }
}
~~~

### 7.3. User Beans, Password Encoder, and Security Chain

`src/main/java/demo/SecurityConfig.java`:

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService(
            PasswordEncoder encoder) {

        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new MapReactiveUserDetailsService(reader, admin);
    }

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchange -> exchange
                .pathMatchers("/", "/about").permitAll()
                .pathMatchers("/admin").hasRole("ADMIN")
                .anyExchange().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            // Disable HTTP Basic to focus on observing form login behavior.
            .httpBasic(spec -> spec.disable())
            .build();
    }
}
~~~

**Part-by-part explanation:**
1. `@EnableWebFluxSecurity` enables WebFlux security configuration. In Spring Boot apps with the appropriate Security starter, auto-configuration usually handles this as well, so the annotation is not mandatory in every Boot project.
2. `MapReactiveUserDetailsService` provides `Mono<UserDetails>` via a reactive implementation; real applications can replace it with a reactive user store backed by R2DBC/an identity provider.
3. `BCryptPasswordEncoder` hashes passwords in the user store; during login, the manager checks raw input against the hash. Never use plaintext passwords in production.
4. `.formLogin(Customizer.withDefaults())` enables the generated login page and `POST /login` processing for username/password.
5. `.httpBasic(...disable())` disables HTTP Basic in the demo so browser requests focus on form login and redirects. This is a demo choice, not a requirement of `formLogin`.
6. `/` and `/about` are public; `/admin` requires `ROLE_ADMIN` via `hasRole("ADMIN")`; remaining URLs require `authenticated()`.
7. CSRF is not disabled. POST `/login` still requires a valid token; the generated login page supports this.
8. There is no need to write `@PostMapping("/login")` because Spring Security's login filter handles the request before controllers. If a controller handles it in parallel, authentication routing confusion and vulnerabilities can easily arise.

Do not hardcode users/passwords or keep BCrypt hashes in memory or an unprotected database for real applications. The purpose of the user set above is **local testing demo**.

### 7.4. Controller Illustrating Authenticated Context

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
class DemoController {

    @GetMapping("/")
    Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping("/about")
    Mono<String> about() {
        return Mono.just("about");
    }

    @GetMapping("/account")
    Mono<String> account() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                Mono.justOrEmpty(context.getAuthentication()))
            .map(Authentication::getName)
            .map(name -> "Hello " + name);
    }

    @GetMapping("/admin")
    Mono<String> adminOnly() {
        return Mono.just("admin-only");
    }
}
~~~

The `/account` handler does not read passwords, does not take the username from a query parameter, and does not call `block()`. `ReactiveSecurityContextHolder` reads the authentication placed into Reactor Context by Spring Security; if unauthenticated, the `anyExchange().authenticated()` rule must block the request **before the handler returns a result**.

## 8. Running Live with a Browser

From the `webflux-form-login-demo` directory, the machine needs JDK 17+, compatible Gradle, and network access to download dependencies on first run:

~~~bash
gradle bootRun
~~~

If using a Gradle Wrapper, run `./gradlew bootRun` (Unix/macOS) or `gradlew.bat bootRun` (Windows). The server runs at `http://localhost:8080` by default unless another port is configured.

Observation steps:

1. Open `http://localhost:8080/`: receives body `home`, no login required.
2. Open `http://localhost:8080/account` when the browser has no session: typically redirected to `/login`.
3. On the Spring Security-generated `/login` page: enter username `reader` and password `reader-pass`. You do not need to enter a CSRF token manually; the generated page prepares the appropriate field.
4. The browser sends `POST /login` with `Content-Type: application/x-www-form-urlencoded`, username/password/CSRF. The security filter verifies and redirects.
5. Returning to `/account` with the session cookie: body is `Hello reader`.
6. Open `/admin` while logged in as reader: receives **403 Forbidden** due to lacking `ROLE_ADMIN`.
7. Log out using the default logout mechanism and log in as `admin` / `admin-pass`. `/admin` now returns `admin-only`.

**Note on post-login redirects:** if the user requested `/account` before logging in, the success handler may navigate to that page. If visiting `/login` directly, the destination may differ. Do not treat a bare HTTP 302 status as proof the user is authenticated; verify the session and access to protected endpoints in the next request.

### 8.1. Why Does a Simple curl Test Easily Hit 403?

Example:

~~~bash
curl -i -X POST http://localhost:8080/login \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'username=reader&password=reader-pass'
~~~

Even with the right password, the sample request **has no CSRF token**, so it can be rejected with **403**. This is intentional protective behavior, not a `PasswordEncoder` bug.

To simulate a full browser with curl, you need to:
- Fetch `GET /login` and the initial session cookie.
- Extract the CSRF token **rendered by the page** (do not guess it), keeping the cookie jar.
- Submit the form with `username`, `password`, matching `_csrf`, and the same session's cookie.
- Follow the redirect, using the post-login cookie for protected requests.

Tokens may be encoded/masked to mitigate BREACH; regexes extracting tokens from HTML are brittle across versions/templates. Therefore, **for this lesson**, using a browser or `WebTestClient.mutateWith(csrf())` is more reliable than providing a shell script tied to specific HTML.

## 9. Integration Testing with `WebTestClient` and Spring Security Test CSRF Support

Spring Security includes reactive test utilities to generate a test CSRF token **valid in the test environment**; there is no need to disable CSRF to POST the login form.

`src/test/java/demo/FormLoginTests.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class FormLoginTests {

    @Autowired
    ApplicationContext applicationContext;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(applicationContext)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void publicHomeCanBeVisitedWithoutAuthentication() {
        client.get().uri("/")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("home");
    }

    @Test
    void defaultLoginPageExists() {
        client.get().uri("/login")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
            .contentTypeCompatibleWith(MediaType.TEXT_HTML);
    }

    @Test
    void protectedBrowserPageRedirectsToLogin() {
        client.get().uri("/account")
            .header(HttpHeaders.ACCEPT, MediaType.TEXT_HTML_VALUE)
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueMatches("Location", ".*/login.*");
    }

    @Test
    void postLoginWithoutCsrfIsRejected() {
        client.post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "reader")
                .with("password", "reader-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void invalidPasswordWithCsrfRedirectsToErrorPage() {
        client.mutateWith(csrf())
            .post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "reader")
                .with("password", "wrong"))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().valueMatches(
                "Location", ".*login\\?error.*");
    }

    @Test
    void correctPasswordWithCsrfStartsAuthenticatedSession() {
        client.mutateWith(csrf())
            .post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("username", "reader")
                .with("password", "reader-pass"))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectHeader().exists(HttpHeaders.LOCATION);
    }
}
~~~

Explanation:
- `WebTestClient.bindToApplicationContext(...)` creates a client for the WebFlux app in tests; `apply(springSecurity())` wires Spring Security WebFilters into the test environment.
- `mutateWith(csrf())` supplies a valid CSRF token in the mock environment; it is **not** a command to disable CSRF protection.
- `BodyInserters.fromFormData(...).with(...)` sends URL-encoded form data matching the login converter.
- The no-CSRF test expects 403.
- The wrong-password-with-CSRF test expects an error redirect.
- The right-password-with-CSRF test expects a success redirect; proving persistence across requests requires a follow-up test with real session cookies (below).
- The tests do not use a mock user to authenticate the login action itself; they go through the demo's real password manager.

**Note on test scope:** The tests above assert statuses and redirects; they do not guarantee every verbatim response header beyond `Location` or cookies across every server/session implementation. Session cookie names and attributes can be changed by configuration in real systems.

### 9.1. Checking the Real Login Session After Redirect

To verify that identity persists on a subsequent request, you can run a **real HTTP integration test** with `@SpringBootTest(webEnvironment = RANDOM_PORT)`, a client keeping a cookie jar, and a way to extract/send the CSRF token from the login page. After successful login, a follow-up request to `/account` carrying that session's cookie must return `Hello reader`.

Alternatively, with mock `WebTestClient` on `ApplicationContext`, you can capture response cookies after POST login and attach them to `GET /account`, if the corresponding WebSession configuration allows. In the default WebFlux demo, the session cookie is typically named `SESSION`; **do not treat that cookie name as universal truth** if the application customized the resolver, path, domain, or SameSite. A complete persistence test should check both cases: with a valid cookie you get 200; omitting the cookie redirects back to 302 login.

### 9.2. Additional Test Matrix Needed for Real Systems

| Scenario | Expectation |
| --- | --- |
| GET `/login` | 200 HTML containing form with username/password fields and token |
| POST login right password, with CSRF | Success redirect + security context stored properly |
| POST login wrong password, with CSRF | Error redirect, no authenticated session |
| POST login missing/wrong CSRF | 403, not authenticated |
| GET `/account` not logged in | Redirect to login |
| GET `/account` after login, same cookie | 200 and right identity |
| GET `/admin` with ROLE_USER | 403 |
| GET `/admin` with ROLE_ADMIN | 200 |
| Logout POST with valid CSRF | Session/logout state processed |
| Logout GET when not intentionally reconfigured | Not automatically treated as a successful logout request |
| Request from another origin, unfamiliar redirect URL | No open redirect, complies with cookies/security headers |

## 10. If You Want to Design Your Own Login Page

Illustrative configuration:

~~~java
.formLogin(form -> form.loginPage("/signin"))
~~~

**This is an additional configuration snippet, not a standalone Java program.** In Spring Security WebFlux, when specifying `loginPage("/signin")`:
- The framework no longer auto-renders the default login page the old way.
- The application must serve **GET `/signin`**.
- The HTML form must submit **POST `/signin`** when using this login page, per the default contract associated with `loginPage`.
- The form must use the exact field names `username`, `password`, and a rendered CSRF token.
- The application should render its own login error page, e.g., `/signin?error`.
- Ensure `GET /signin` is permitted **when anonymous**, avoiding redirect loops.
- Do not build HTML by concatenating user input strings; use a supported view/template engine with output escaping.

In a reactive Thymeleaf app, CSRF integration via Spring Security and the template engine can automatically add the token input to POST forms if model/request attributes and processors are configured properly. With hand-written HTML forms, you must supply the token from `Mono<CsrfToken>` exposed by Spring Security per the contract of your version; never hardcode tokens in source or share one global token across users.

### 10.1. Reading the Form Yourself Then Calling Manager: API Illustration, Not a Replacement for Default Flow

If you genuinely build a custom authentication flow, converter logic might look like:

~~~java
ServerAuthenticationConverter converter = exchange ->
    exchange.getFormData()
        .map(form -> {
            String username = form.getFirst("username");
            String password = form.getFirst("password");
            return UsernamePasswordAuthenticationToken.unauthenticated(
                username == null ? "" : username,
                password == null ? "" : password
            );
        });
~~~

The snippet above **is not a standalone application** and needs imports:
- `org.springframework.security.web.server.authentication.ServerAuthenticationConverter`
- `org.springframework.security.authentication.UsernamePasswordAuthenticationToken`
- `org.springframework.web.server.ServerWebExchange` (lambda parameter type is inferred)
- `reactor.core.publisher.Mono` via the API.

The converter only creates an **unauthenticated** token. Manager, matcher, success/failure handlers, and SecurityContext persistence still require configuration. This snippet does not handle full validation, Content-Type, body limits, CSRF, session fixation, or rate limiting; that is why **preferring built-in `formLogin`** is recommended when there are no special requirements.

If you want to rename fields, login URLs, or failure handling, inspect `ServerHttpSecurity.FormLoginSpec` and the converter API instead of placing a new `@PostMapping("/login")` in a controller. When altering the mechanism, re-test valid, malformed, and CSRF-safe form POSTs.

## 11. Common Bugs and Diagnostics

| Symptom | Possible Cause | How to Check / Fix |
| --- | --- | --- |
| GET `/account` returns 302 even though controller exists | No valid authentication yet, `authenticated()` applies | Log in via browser, keep session cookie; do not drop rule |
| POST `/login` right password returns 403 | Missing/wrong CSRF token, different session, expired token | Check CSRF and cookie; do not disable CSRF to dodge the error |
| POST `/login` returns `/login?error` | Wrong credentials, locked/expired user, or encoder mismatch | Check user store, `PasswordEncoder`, sanitized logs |
| Login 302 succeeds yet `/account` still redirects | Session cookie missing/different domain/different path or incompatible repository | Check response `Set-Cookie`, request Cookie, TTL, context repository |
| Form sends JSON instead of URL-encoded | Default converter does not read JSON as username/password | Send `application/x-www-form-urlencoded` or design a separate API |
| Form uses `user`/`pass` instead of `username`/`password` | Field names do not match converter configuration | Align field names or customize converter with tests |
| Reading form via `@RequestParam` like MVC yields null | Resolver/stack differences in WebFlux | Use `exchange.getFormData()` for the body |
| Using `getFormData()` for multipart uploads | Different media type and decoder | Use `getMultipartData()` / `Part` |
| Comparing plaintext password with BCrypt hash via `equals` | Always fails or leads to insecure workarounds | Use `PasswordEncoder.matches` |
| Writing a POST `/login` controller alongside `formLogin` | Filter may handle first; controller does not run as expected | Let Spring Security manage login POST |
| Calling `block()` inside a WebFlux converter/manager | Blocks event loop, causes errors or drops throughput | Use reactive publishers/repositories per contract |
| Using Servlet `HttpSecurity` and `UsernamePasswordAuthenticationFilter` | Wrong web stack | Use `ServerHttpSecurity`, `SecurityWebFilterChain`, `AuthenticationWebFilter` |
| Custom login page enters a redirect loop | GET login is also blocked by authorization | Permit login page + required CSS/JS assets |
| User logged in yet `/admin` returns 403 | Missing `ROLE_ADMIN` | Inspect authorities; never grant roles from form input |
| Switched form login to stateless without saving session | POST login may succeed, but next request lacks context | Redesign persistence/token flow; do not assume automatic session saving |
| Logging full form body, Authorization, or password | Secret leakage | Never log credentials; log minimal trace IDs and outcome categories |

### 11.1. Distinguishing HTTP 302, 401, 403

- **302 Redirect**: common in form login: unauthenticated users are sent to login, or login success/failure sends them to a target page.
- **401 Unauthorized**: common with API mechanisms (HTTP Basic/Bearer) or custom entry points; default browser form login may return 302 instead of 401.
- **403 Forbidden**: valid authentication but insufficient permissions, **or** rejected by the CSRF filter on a state-changing request.

Do not inspect an HTTP status in isolation and guess the cause; check Location, cookies, client type (browser/API), form body, CSRF, and authorization rules.

### 11.2. Form Data Is Untrusted and Requires Controls

- Enforce limits on request body/form size, field count, and processing time.
- Never log raw passwords or POST login bodies, even in debug mode.
- Use TLS/HTTPS and appropriate cookie flags (`Secure`, `HttpOnly`, `SameSite` suited to the flow).
- Mitigate brute-force/credential stuffing via rate limits, monitoring, and appropriate lockout/challenges; never reveal "username does not exist" or "wrong password" to attackers.
- Never send passwords in query strings, URL paths, or analytics events.
- Never store plaintext passwords; hash with an appropriate algorithm (BCrypt/Argon2 or an evaluated encoder) with a hash upgrade policy.
- Control session fixation, session expiry, logout, concurrency, and revocation according to risk level.
- Protect custom login pages against XSS, open redirects, CSP issues, and client-injected data.
- Test post-login authorization, including tenant/ownership boundaries; successful login does not grant all permissions.

## 12. Knowledge Self-Check

1. **What type does `ServerWebExchange.getFormData()` return?** `Mono<MultiValueMap<String,String>>`; the form body is read/parsed non-blockingly via reactive APIs.
2. **Which path and method does default form login submit to?** `POST /login`, with `username` and `password` by default.
3. **Why shouldn't you process passwords in `@PostMapping("/login")` when using `formLogin`?** Spring Security already places filters in the pipeline to check CSRF, convert data, authenticate, and manage context.
4. **May a converter create an authenticated Authentication before checking the password?** No. It creates an unauthenticated request; the manager performs verification.
5. **Where does the manager obtain users/hashes?** From a trusted user source via `ReactiveUserDetailsService` or corresponding authentication mechanism; verified with `PasswordEncoder`.
6. **With the right password but missing CSRF token, can you log in?** Normally no; the POST is rejected with 403 by the CSRF filter.
7. **What happens with a wrong password and valid CSRF?** Typically redirects to `/login?error` per default form login.
8. **Why does GET /account still need a cookie after a successful POST login?** The session/context is linked via cookie/session ID; Reactor Context does not replace sessions across multiple requests.
9. **Does `@RequestParam` in WebFlux always extract fields from form bodies like Spring MVC?** Do not assume so; to read the body use `getFormData()`/`ServerRequest.formData()`.
10. **When should `getMultipartData()` be used?** When the request is `multipart/form-data` (e.g., file upload), not regular `application/x-www-form-urlencoded`.
11. **Which authority does `hasRole("ADMIN")` compare against by default?** `ROLE_ADMIN`.
12. **Does `WebTestClient.mutateWith(csrf())` disable CSRF in production?** No. It is a test utility that supplies a valid token in the mock environment.
13. **What must be prepared when configuring `form.loginPage("/signin")`?** Render GET `/signin` and error state yourself, POST `/signin` with fields + CSRF, and permit anonymous access to the page.
14. **Why is form login unsuitable for pure JSON APIs?** The default form login converter expects form data and does not parse JSON under the form contract.
15. **Do you need to modify `SecurityWebFilterChain` to read the username in a reactive handler?** No. After authorization, use `ReactiveSecurityContextHolder.getContext()` to obtain authentication within the pipeline.
16. **Is HTTP 403 on `/admin` always caused by CSRF?** No; GET does not require CSRF under default policy, so 403 can result from the user lacking the ADMIN role.

## 13. Implementation Checklist

- [ ] The web stack is genuinely WebFlux, not accidentally running Servlet MVC.
- [ ] The `POST /login` form uses matching field names and the right media type.
- [ ] `ReactiveUserDetailsService` returns users and password hashes from a trusted source.
- [ ] `PasswordEncoder` is configured consistently with stored hashes.
- [ ] CSRF is enabled for session-based form login and tokens are rendered properly.
- [ ] Success/failure redirects are tested; login page/assets are permitted anonymously.
- [ ] Context persistence, session cookies, and logout work properly.
- [ ] Passwords are never stored/logged, and raw credentials are never echoed in responses.
- [ ] WebFlux handlers read Reactor security context non-blockingly.
- [ ] Post-login authorization enforces roles/permissions and object ownership appropriately.
- [ ] Tests cover success, wrong password, missing CSRF, session reuse, and 403 insufficient permissions.
- [ ] HTTPS, cookie flags, rate limiting, and credential-stuffing mitigations are in place.

## 14. Official Documentation

- Spring Security — WebFlux Security Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security API — `ServerHttpSecurity.FormLoginSpec` (loginPage, matcher, repository, failure): https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html
- Spring Security API — `ServerFormLoginAuthenticationConverter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/ServerFormLoginAuthenticationConverter.html
- Spring Framework — `ServerWebExchange.getFormData()`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework — WebFlux form-data parsing: https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html
- Spring Security — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security — Testing with CSRF/WebTestClient: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html

**Remember:** `getFormData()` reads data from the HTTP body; it **does not authenticate the user**. `formLogin` integrates the converter, reactive authentication manager, password encoder, CSRF handling, and session/context to build a controlled login session. In WebFlux, keep these steps on the `Mono`/`Flux` pipeline and test success, wrong password, missing CSRF, and post-login requests.
