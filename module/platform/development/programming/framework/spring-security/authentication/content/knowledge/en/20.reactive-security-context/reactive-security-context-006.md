# Saving Context After Login and Verifying with a Follow-Up Request in Spring Security WebFlux

## 1. Problem and Observable Outcome

Build a Spring Boot application using **Spring WebFlux + Spring Security**: a user logs in successfully via a form, then sends **a new HTTP request** to a protected resource. The second request still recognizes the right user without resending username/password. This verifies saving and restoring the authentication context across two requests, rather than only checking identity within the login request itself.

Expected outcome:

1. Unauthenticated: accessing `GET /api/me` is blocked and directed to the login page (with form login).
2. Successful login via `POST /login` with a valid CSRF token: Spring Security stores `SecurityContext` in `WebSession` and returns a session cookie to the client.
3. Sending a brand-new request to `GET /api/me` with **the session cookie from the login just performed**, without Basic Auth or a password: response `200 OK`, body `alice`.
4. Sending the exact same request **without a valid cookie**: reverts to unauthenticated state. Thus the result does not come from a global variable or a mocked authentication applied to all requests.

The scope here is **stateful (session-based) login in a reactive application**. For REST APIs using stateless Bearer JWTs, each request must send its own token and the `Authentication` restoration mechanism differs.

## 2. Distinguishing Reactor Context from Cross-Request Data

In Spring Security WebFlux:

| Component | Role | Lifetime to understand |
| --- | --- | --- |
| `Authentication` | Principal, authorities, authentication status | Identity data; does not decide persistence on its own |
| `SecurityContext` | Wraps `Authentication` | May be persisted or exist only in the current processing sequence |
| `ReactiveSecurityContextHolder` | Reads/sets `Mono<SecurityContext>` in **Reactor Context** | Serves a subscribed reactive stream, not HTTP session memory |
| `ServerSecurityContextRepository` | Contract `save(exchange, context)` and `load(exchange)` | Connects context to a storage source usable in other requests |
| `WebSessionServerSecurityContextRepository` | Saves `SecurityContext` in `WebSession` | Persists across multiple requests if the client sends a valid session ID |
| `ReactorContextWebFilter` | Loads context from repository into Reactor Context | Allows handlers and filters to read identity on each request |

**Core point:** `ReactiveSecurityContextHolder.withAuthentication(authentication)` only adds authentication to the **Reactor Context of a single publisher sequence**. It does not automatically write to an HTTP session; a new HTTP request initializes a new Reactor Context chain. Maintaining session-style login requires both **saving** on successful authentication and **loading** on the next request.

Do not apply Servlet reasoning such as calling `SecurityContextHolder.getContext()` and expecting a `ThreadLocal` to survive when WebFlux switches threads. In reactive code, read via `ReactiveSecurityContextHolder.getContext()` or use the principal provided by WebFlux.

### Processing Sequence

1. Client sends `POST /login` containing credentials and a CSRF token.
2. Spring Security's authentication filter verifies credentials via the configured authentication mechanism.
3. On success, the form-login `AuthenticationWebFilter` writes `SecurityContext` using the **form login** repository.
4. With `WebSessionServerSecurityContextRepository`, data resides in server-side `WebSession`; the client keeps only the session ID, typically via the `SESSION` cookie. This repository rotates the session ID when saving context to mitigate session fixation.
5. Client stores the received cookie and sends it on a new `GET /api/me`.
6. `ReactorContextWebFilter` uses the repository configured on `ServerHttpSecurity` to reload the context into the Reactor Context. The `authenticated()` rule permits the request and the controller reads `alice`.
7. If the cookie is omitted, expired, or the session has been invalidated, the prior context is not restored.

Note that **the repository used for writing and the repository used for reading must be compatible**. Calling only `http.securityContextRepository(repo)` configures the context loading side for `ReactorContextWebFilter`; the save side during form login must use a corresponding repository. The example below configures both explicitly so behavior is easy to verify. With standard form login configuration, Spring Security already defaults to `WebSessionServerSecurityContextRepository` for the save step.

## 3. Runnable Spring Boot WebFlux Example

Environment: **Java 17+**, a Spring Boot 3.x project created with Spring Initializr, using **Spring Reactive Web** and **Spring Security**. Do not also add `spring-boot-starter-web` to avoid accidentally running a Servlet application. Add test dependencies if you want to run the automated verification in section 5.

In `build.gradle` of a Spring Boot/Gradle project already configured with plugins and dependency management, declare:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

### 3.1. Configuring Authentication and the Same Repository for Save/Load

Create `src/main/java/com/example/demo/SecurityConfig.java`:

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    ServerSecurityContextRepository securityContextRepository() {
        return new WebSessionServerSecurityContextRepository();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerSecurityContextRepository repository) {

        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/me").authenticated()
                        .anyExchange().permitAll())
                // Repository used by ReactorContextWebFilter to load.
                .securityContextRepository(repository)
                // Repository used by form-login to save on successful login.
                .formLogin(form -> form.securityContextRepository(repository))
                // Disable Basic Auth so the test proves session cookie persistence only.
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                // Keep CSRF enabled: do not disable it just to make POST /login easier.
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }
}
```

In this learning example, the user is held in memory and the password `demo-pass` is sample data. BCrypt only protects the stored password string; production requires a real user store, secret management, and an appropriate login policy.

The configuration above uses WebFlux's `SecurityWebFilterChain` and `ServerHttpSecurity`, not Servlet's `SecurityFilterChain` / `HttpSecurity`. `.formLogin(...)` provides the built-in login page at `GET /login` and handles `POST /login`. Our code does not reimplement username/password verification or manage HTTP sessions manually. Configuring `.httpBasic(...disable)` ensures that succeeding on `/api/me` on the second request demonstrates **session persistence**, rather than the browser silently sending Basic credentials.

### 3.2. Reading Context in a Reactive Handler

Create `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
class MeController {

    @GetMapping("/api/me")
    Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(Authentication::isAuthenticated)
                .map(Authentication::getName);
    }
}
```

`ReactiveSecurityContextHolder.getContext()` retrieves the context for the request being processed. Before the controller runs, the `authenticated()` rule requires authentication; when a valid session exists, the response body is the username `alice`. `Mono<String>` is subscribed to by WebFlux when producing the HTTP response; do not call `block()` and do not spawn separate threads to obtain the principal.

## 4. Manual Verification Using **Two Distinct HTTP Requests**

Start from the project directory: `./gradlew bootRun` (on Windows use `gradlew.bat bootRun`). Once the app is running at `http://localhost:8080`, perform the following in a browser:

1. In a new private window, open `http://localhost:8080/api/me`. Without a logged-in session, you are redirected to the login page (expect an HTTP 3xx redirect to form login). There is no `alice` body.
2. Log in on the default form with `alice` / `demo-pass`. The framework-generated form includes the required CSRF token. Inspect in Developer Tools -> Network: there is a `POST /login` request, and a successful response is typically a redirect carrying a valid session cookie.
3. **After the login page completes, type directly** `http://localhost:8080/api/me` again (or refresh at the endpoint). This is a fresh GET request with no username/password in the URL, body, or Authorization header. Expectation: `HTTP 200` and response content is exact `alice`.
4. Open another private window **not sharing cookies**, and visit the same URL. Expect to be prompted to log in again. Deleting the `SESSION` cookie in the first window and calling again yields the same result.
5. Log out properly (using the `POST /logout` form with CSRF token) or wait for the session to expire; then try a new request to confirm the old context is no longer accepted.

An illustrative HTTP trace (actual headers/cookies/tokens will have different values):

```http
POST /login HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: SESSION=<pre-login-id-if-any>

username=alice&password=demo-pass&_csrf=<valid-token>

HTTP/1.1 302 Found
Set-Cookie: SESSION=<post-login-session-id>; Path=/; HttpOnly

GET /api/me HTTP/1.1
Cookie: SESSION=<post-login-session-id>

HTTP/1.1 200 OK
Content-Type: text/plain;charset=UTF-8

alice
```

This is an **exchange illustration**, not a command to copy verbatim: you must obtain the CSRF token and cookie issued by the server. The `Set-Cookie` header may carry additional attributes; do not hard-code session ID values, redirect statuses, or cookie attributes in application code.

## 5. Automated Testing: Real Login, Carrying Cookie to the Second Request

The following approach tests the behavior of form login and the repository. It **does not** use `mockUser()` or `@WithMockUser` to inject an identity into the second request, because doing so would not prove the context was saved. Use mock-server `WebTestClient`, configure Spring Security test support, and supply a valid CSRF token for the login request.

Create `src/test/java/com/example/demo/SessionPersistenceTest.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SessionPersistenceTest {

    @Autowired
    ApplicationContext context;

    WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void authenticatedSessionIsRestoredOnNextRequest() {
        // Request 1: submit a real form login without setting a fake principal.
        EntityExchangeResult<byte[]> login = client.mutateWith(csrf())
                .post()
                .uri("/login")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("username", "alice")
                        .with("password", "demo-pass"))
                .exchange()
                .expectStatus().is3xxRedirection()
                .expectBody()
                .returnResult();

        ResponseCookie cookie = login.getResponseCookies().getFirst("SESSION");
        assertNotNull(cookie, "Login must create a session cookie");

        // Request 2: client sends only the session cookie, without credentials.
        client.get()
                .uri("/api/me")
                .cookie("SESSION", cookie.getValue())
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .isEqualTo("alice");

        // Request 3: without the cookie, access is denied.
        client.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().is3xxRedirection();
    }
}
```

Run `./gradlew test --tests com.example.demo.SessionPersistenceTest` (Windows: `gradlew.bat test --tests com.example.demo.SessionPersistenceTest`). When the test passes, the two most important observations are: **the second GET request receives 200 + `alice`** and **the GET request without a cookie is blocked**. `csrf()` is a helper for mock-server `WebTestClient`; the real application still requires a valid CSRF token. If your project uses a different build layout or package name, adjust paths/packages/test tasks accordingly.

If you want to test closer to production conditions, run an HTTP client with a cookie jar (or a browser) against a real server, log in, and **send a follow-up request** with that same received session cookie. A test that merely calls `ReactiveSecurityContextHolder.withAuthentication(...)` or `mockUser()` on each request cannot replace this verification step.

## 6. How Do You Save Context If You Write a Custom Login Endpoint?

The example above uses `formLogin`, where Spring Security saves automatically after successful authentication. If you replace it with a JSON controller or a custom `AuthenticationWebFilter`, you must check **which path is actually calling save**. Merely creating an `Authentication`, setting `SecurityContext` in a publisher, or returning `200 OK` is not enough.

In a controller that already has `ReactiveAuthenticationManager manager`, `ServerSecurityContextRepository repository` (shared with the chain configuration), and `ServerWebExchange exchange`, the save idea is:

```java
Authentication request =
        UsernamePasswordAuthenticationToken.unauthenticated(username, password);

return manager.authenticate(request)
        .switchIfEmpty(Mono.error(new BadCredentialsException("Invalid credentials")))
        .flatMap(authenticated -> {
            SecurityContext context = new SecurityContextImpl(authenticated);
            return repository.save(exchange, context)
                    .thenReturn(authenticated.getName());
        });
```

**This is an illustrative logic snippet inside a controller that already has its dependencies**, not a standalone program or complete login API. Corresponding imports: `Authentication`, `UsernamePasswordAuthenticationToken`, `BadCredentialsException`, `SecurityContext`, `SecurityContextImpl`, and `Mono`. In a real implementation, you still must enforce CSRF protection, map authentication failures to appropriate HTTP statuses, and define the response contract.

`save(...)` returns `Mono<Void>`: it must be **chained into the returned sequence** such as `.flatMap(...).thenReturn(...)` so the write actually completes. Calling `repository.save(...)` without subscribing, or calling `subscribe()` yourself and returning a response before saving finishes, easily leaves the next request anonymous. If you instantiate `AuthenticationWebFilter` yourself, `setSecurityContextRepository(repository)` configures where to save; per the API, a manually constructed filter defaults to `NoOpServerSecurityContextRepository`, so it must be configured explicitly when session persistence is needed.

Conversely, if the design is intentionally stateless (Bearer token), choosing a non-persisting repository makes sense; the client must send the token on **every** request. Never turn a stateless API into a session-based one just to make a second test pass.

## 7. Common Errors, Diagnostics, and Security Boundaries

| Symptom | Common cause | How to check or fix |
| --- | --- | --- |
| Login reports success yet the next GET prompts for login again | Context lived only in the current Reactor Context without saving, or saved to a different repository than the one used to load | Inspect form login/filter save configuration and `ServerHttpSecurity.securityContextRepository(...)` |
| GET after login does not see the session | Cookie was not stored/sent by client, wrong domain/path, SameSite/Secure policy, or cross-origin request missing credentials | Check `Set-Cookie` on login response and `Cookie` on the next GET request |
| POST /login returns 403 | Missing/invalid CSRF token, or the session holding the CSRF token changed/expired | Fetch token from the login page and send the matching token; do not disable CSRF reflexively |
| GET still returns 200 without a cookie | Request still carries Basic/Bearer credentials, test injects a mock principal, or endpoint is accidentally `permitAll()` | Inspect Authorization header, remove `mockUser()`, and keep `/api/me` under authenticated |
| Context exists in `map()` but is lost after creating a separate publisher/thread | Reactor Context is not propagated across that execution boundary | Maintain a single reactive chain and use `ReactiveSecurityContextHolder`; avoid relying on ThreadLocal |
| One instance recognizes the session, another instance does not | Session store is local to each instance only | Use a shared reactive session store (e.g., Spring Session + Redis) matching the deployment architecture |
| Works before logout, still works after logout | Old cookie/session was not invalidated or GET is actually authenticated by another mechanism | Check logout handler, session invalidation, and any other attached credentials |

**Directly relevant security notes:**

- The session cookie is sensitive access material: enable HTTPS, use `Secure`/`HttpOnly`, and configure `SameSite` appropriate for your web flow; never log cookie values or session IDs.
- Never store plaintext passwords, arbitrary access tokens, or entire request bodies inside `SecurityContext`; keep only the necessary authentication information.
- Keep CSRF protection for login and state-changing operations when relying on cookies automatically sent by browsers.
- Design TTL, logout/invalidation, session fixation protection, and cross-instance session sharing strategies. `WebSessionServerSecurityContextRepository` supports changing the session ID when saving context.
- When triaging bugs, distinguish **succeeding login within a single request** from **context being restored on a new request**: only the second case proves the requirement of this lesson.

## 8. Completion Criteria

The practice exercise meets requirements when you have evidence for the full sequence **valid login -> session cookie issued -> fresh GET carrying only the cookie -> 200/`alice` -> GET without cookie blocked**. You should be able to explain clearly why `ReactiveSecurityContextHolder` serves the current reactive sequence, while `WebSessionServerSecurityContextRepository` and `ReactorContextWebFilter` form the write/read pair that preserves authentication across multiple HTTP requests.

### Official Documentation for Reference

- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/6.5/reactive/configuration/webflux.html)
- [Spring Security API — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security API — FormLoginSpec and securityContextRepository](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html)
- [Spring Security API — WebSessionServerSecurityContextRepository](https://docs.spring.io/spring-security/site/docs/6.3.7/api/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
- [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html)
- [Spring Security — WebFlux CSRF testing](https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html)
