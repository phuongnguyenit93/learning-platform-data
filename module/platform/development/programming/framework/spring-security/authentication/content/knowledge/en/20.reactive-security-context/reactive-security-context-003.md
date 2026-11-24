# ServerSecurityContextRepository and WebSessionServerSecurityContextRepository in Spring Security WebFlux

## 1. Problem: Where Is Identity Kept Across HTTP Requests?

In WebFlux, after successful authentication, Spring Security has an `Authentication` (representing the principal, authorities, and authentication status) placed inside a `SecurityContext`. However, the next HTTP request is a fresh processing flow: if the application needs to remember a user who logged in via a form, it must **save and reload** the `SecurityContext`.

The two components in this lesson address two different levels:

- **`ServerSecurityContextRepository`** is the *strategy interface*: it defines how to load and save a `SecurityContext` associated with a `ServerWebExchange`.
- **`WebSessionServerSecurityContextRepository`** is a *concrete implementation*: it uses Spring WebFlux's `WebSession` to store `SecurityContext` on the server side between requests.

Package name to remember: `org.springframework.security.web.server.context`. This is **WebFlux/reactive**, not Servlet's `SecurityContextRepository` and `HttpSessionSecurityContextRepository`.

### Distinguishing Four Concepts

| Component | Role | Scope |
| --- | --- | --- |
| `Authentication` | Who the user is, what authorities they have, and whether they are authenticated | Identity data |
| `SecurityContext` | Wrapper object holding `Authentication` | Security context |
| `ReactiveSecurityContextHolder` | Accesses context via **Reactor Context** in the current processing flow | The request's reactive sequence |
| `ServerSecurityContextRepository` | Loads/saves context to serve **subsequent requests** | Persistence mechanism determined by the implementation |

Reactor Context is not a long-lived session store. Placing authentication into `ReactiveSecurityContextHolder` only makes it visible to steps within the current reactive sequence; persisting login state to the next request requires an appropriate save/load mechanism.

## 2. The ServerSecurityContextRepository Contract

Core API (annotations simplified):

```java
public interface ServerSecurityContextRepository {
    Mono<Void> save(ServerWebExchange exchange, SecurityContext context);
    Mono<SecurityContext> load(ServerWebExchange exchange);
}
```

- `load(exchange)`: emits a `SecurityContext` if found; **`Mono.empty()`** if absent. Never return `null` instead of a `Mono`.
- `save(exchange, context)`: returns `Mono<Void>`; the save operation occurs when the publisher is **subscribed to** and finishes when the publisher completes. Calling the method and discarding the `Mono` does not guarantee saving.
- `ServerWebExchange` provides the request/response and access to `WebSession`; it is the reactive API, not `HttpServletRequest`.
- Verifying credentials (passwords, tokens, etc.) belongs to `ReactiveAuthenticationManager` or the corresponding authentication mechanism; the repository **does not verify passwords itself**.

In Spring Security 6.x, the `save` signature accepts `SecurityContext`; newer versions may document a nullable parameter to support clearing context. When illustrating custom code, follow the signature of your project's version.

## 3. How Does WebSessionServerSecurityContextRepository Work?

`WebSessionServerSecurityContextRepository` writes `SecurityContext` under a key in `WebSession.getAttributes()`; on `load`, it retrieves the context from the corresponding session. The default key is exposed via the constant `DEFAULT_SPRING_SECURITY_CONTEXT_ATTR_NAME`; it can be changed with `setSpringSecurityContextAttrName(...)` if custom integration is needed.

**Login and subsequent request flow:**

```text
[POST /login with username/password]
  -> AuthenticationWebFilter + ReactiveAuthenticationManager authenticate
  -> create SecurityContext containing Authentication
  -> repository.save(exchange, context)
  -> WebSession holds context; session id is changed on save to mitigate session fixation
  -> browser retains session cookie

[GET /whoami with cookie of the same session]
  -> WebFlux restores WebSession from cookie / session store
  -> ReactorContextWebFilter uses repository.load(exchange)
  -> SecurityContext is placed into Reactor Context
  -> Authorization and handler read Authentication in the reactive flow
```

Mental model: **the cookie carries the session ID**, while the context is stored server-side in `WebSession`; normally the cookie does not carry the full `Authentication`. `WebSession` may be backed by local memory or a shared session store depending on configuration. `WebSessionServerSecurityContextRepository` does not generate a JWT, nor does it store into Redis/a database by default.

Notable characteristics:

1. When saving context, the implementation **changes the session ID** to protect against session fixation attacks.
2. When no context exists, `load` returns an empty publisher; the request does not thereby become a logged-in request.
3. `setCacheSecurityContext(true)` can cache the `load` result with `Mono.cache()` to avoid repeated loads within the same processing path. This is a publisher cache, **not a distributed cache or a replacement for a session store**.
4. When a session is invalidated or expires, the saved context is no longer available on subsequent requests; re-authentication is required.

## 4. Who Calls save, Who Calls load? Two Easily Confused Configurations

In the WebFlux chain:

- `ReactorContextWebFilter` uses the repository configured on `ServerHttpSecurity.securityContextRepository(...)` to **load** context into `ReactiveSecurityContextHolder`.
- Authentication mechanisms based on `AuthenticationWebFilter`, such as `formLogin`, have their own repository configuration for **saving** the authentication result. Under typical form login configuration, `WebSessionServerSecurityContextRepository` is used for saving.
- `SecurityContextServerWebExchangeWebFilter` enables `ServerWebExchange.getPrincipal()` to read the principal from the reactive context.

**Decisive point:** setting `http.securityContextRepository(repo)` **configures only the load path** and does not automatically force every `AuthenticationWebFilter` to use that same repository for saving. When changing strategies, verify both **the save path and the load path**. If login saves into repository A while the next request loads from repository B, login may succeed and immediately appear unauthenticated afterward.

## 5. Runnable Example: Form Login Persisting Context with WebSession

Create a Spring Boot 3.x, Java 17+ application selecting **Spring Reactive Web (WebFlux)** and **Spring Security**. Corresponding Gradle dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
```

Create `src/main/java/demo/SessionSecurityDemoApplication.java`:

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class SessionSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionSecurityDemoApplication.class, args);
    }

    @Bean
    ServerSecurityContextRepository securityContextRepository() {
        return new WebSessionServerSecurityContextRepository();
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerSecurityContextRepository repository) {
        return http
                .securityContextRepository(repository) // Load on new request
                .authorizeExchange(exchanges -> exchanges
                        .anyExchange().authenticated())
                .formLogin(form -> form
                        .securityContextRepository(repository)) // Save after login
                .build();
    }

    @Bean
    MapReactiveUserDetailsService userDetailsService() {
        UserDetails user = User.withUsername("reader")
                .password("{noop}demo123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }

    @GetMapping("/whoami")
    Mono<String> whoami() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(authentication -> authentication.getName());
    }
}
```

**How to observe:**

1. Run `./gradlew bootRun` (Windows: `gradlew.bat bootRun`) from the Spring Boot project you just created, or run `main` in your IDE.
2. Open `http://localhost:8080/whoami` in a browser. Because there is no authentication yet, Spring Security redirects to the login page.
3. Log in with `reader` / `demo123` using the default form; the CSRF token is handled by this form. After logging in, visit `/whoami` again: the response body is exactly `reader`.
4. Reloading the page still returns `reader` while the session cookie remains valid. Deleting the session cookie or opening a new browser session requires logging in again.

The example uses `{noop}` **for learning only**; never use unencrypted passwords or hard-coded users in a real environment. Production needs a secure password encoder (such as bcrypt), a user store, and an appropriate authentication policy. Spring Security's CSRF protection remains enabled for form login.

Why does `whoami()` read from `ReactiveSecurityContextHolder` instead of accessing `WebSession` directly? Because the web filter has restored the request's context into **Reactor Context**; business handlers only need to read identity via the security API, avoiding direct coupling to where the session is stored.

## 6. Properly Testing Save/Load Behavior Across Two Exchanges

The following test does not require running an HTTP server; it explicitly creates **two distinct `ServerWebExchange` instances sharing one `MockWebSession`**. This verifies persistence better than saving and loading on the same exchange.

Add test dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

Create `src/test/java/demo/WebSessionRepositoryTest.java`:

```java
package demo;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.web.server.MockWebSession;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class WebSessionRepositoryTest {

    @Test
    void savesContextAndLoadsItFromAnotherRequest() {
        var repository = new WebSessionServerSecurityContextRepository();
        var sharedSession = new MockWebSession();

        var loginExchange = MockServerWebExchange
                .builder(MockServerHttpRequest.post("/login"))
                .session(sharedSession)
                .build();

        Authentication authentication =
                new UsernamePasswordAuthenticationToken(
                        "reader", "ignored",
                        List.of(new SimpleGrantedAuthority("ROLE_USER")));
        SecurityContext context = new SecurityContextImpl(authentication);

        // StepVerifier subscribes and waits for Mono<Void> save to complete.
        StepVerifier.create(repository.save(loginExchange, context))
                .verifyComplete();

        var nextExchange = MockServerWebExchange
                .builder(MockServerHttpRequest.get("/whoami"))
                .session(sharedSession)
                .build();

        StepVerifier.create(repository.load(nextExchange))
                .assertNext(loaded -> {
                    assertEquals("reader", loaded.getAuthentication().getName());
                    assertEquals(
                            "ROLE_USER",
                            loaded.getAuthentication().getAuthorities()
                                    .iterator().next().getAuthority());
                })
                .verifyComplete();

        var unrelatedExchange = MockServerWebExchange
                .builder(MockServerHttpRequest.get("/whoami"))
                .session(new MockWebSession())
                .build();

        StepVerifier.create(repository.load(unrelatedExchange))
                .verifyComplete(); // No SecurityContext yet: Mono.empty()
    }
}
```

Run `./gradlew test`; the sample test is expected to **PASS**: with the same session, authentication is loaded; with a different session, there is no context. The test only verifies the repository contract and does not replace real HTTP/cookie/CSRF testing. `StepVerifier` subscribes properly in accordance with Reactor's laziness.

## 7. When to Use WebSession and When Not To?

| Scenario | Typical choice | Reason |
| --- | --- | --- |
| WebFlux application with form login keeping login state in a session cookie | `WebSessionServerSecurityContextRepository` | Reloads `SecurityContext` from the session on subsequent requests |
| API requiring Basic/Bearer credentials on **every request**, no need to remember context across requests | `NoOpServerSecurityContextRepository` | `save` persists nothing; `load` is always empty |
| Multi-instance system needing to keep login when requests hit another node | `WebSession`-based repository **with a shared session store** | Requires session infrastructure accessible from multiple nodes, not merely switching repository implementations |
| Custom login with a step that constructs authentication manually | Explicitly save context via repository and place into Reactor Context when needed in the current request | Avoids state existing only for the current request |

Example configuration for a **stateless API with HTTP Basic**, intended for a pure API application (independent of the form login example above):

```java
@Bean
SecurityWebFilterChain statelessApi(ServerHttpSecurity http) {
    var noOp = NoOpServerSecurityContextRepository.getInstance();

    return http
            .securityContextRepository(noOp) // Do not load context from session
            .authorizeExchange(exchanges ->
                    exchanges.anyExchange().authenticated())
            .httpBasic(basic -> basic.securityContextRepository(noOp))
            .formLogin(form -> form.disable())
            .build();
}
```

The imports needed for this snippet are `org.springframework.security.web.server.context.NoOpServerSecurityContextRepository` and the types already present in the main example. This snippet is **an alternative configuration method** in a `@Configuration` class; do not add it alongside the form-login application without defining explicit `SecurityWebFilterChain` scopes. The application/client must send `Authorization` on every request to authenticate. `NoOp` only prevents **saving/loading SecurityContext**; it does not mean every other WebFlux feature stops using `WebSession`; CSRF, request cache, or application code may still use sessions depending on configuration.

## 8. Common Real-World Errors and Diagnostics

**(1) Login succeeds and then the next request returns 401/redirects to login.** Check whether the session cookie is sent back, whether the session store retains the session, whether the session has expired, and especially **whether the repository used to save matches the repository used to load**. When multiple security chains exist, verify which chain actually matches that URL.

**(2) Calling `repository.save(exchange, context);` yet nothing is saved.** `Mono` is lazy; it must be chained into the pipeline or subscribed to in a test. In a WebFlux handler use `flatMap`, `then`, or `contextWrite` as appropriate; do not call `block()` on the event loop to force a side effect.

**(3) Context exists in the current request but is missing in the next request.** `ReactiveSecurityContextHolder.withAuthentication(...)` or `withSecurityContext(...)` only enriches **Reactor Context** for the current subscription; it does not replace `repository.save`. Conversely, saving to the session does not mean operators that already ran earlier immediately gain the new context.

**(4) Using `SecurityContextHolder.getContext()` in WebFlux and seeing null/empty or wrong context.** Traditional `SecurityContextHolder` relies on ThreadLocal; reactive pipelines can switch threads. Use `ReactiveSecurityContextHolder.getContext()` and keep operations inside the pipeline.

**(5) Assuming WebSession means the token lives in the cookie.** The cookie usually contains only the session ID; the security context resides server-side. Never log or serialize raw credentials/secrets into the context, session, or response.

**(6) Login fails with CSRF 403 when POSTing via curl/Postman.** Form login has CSRF protection enabled by default: obtain a valid token and preserve the same session's cookie. Never disable CSRF globally just to make test requests pass.

**(7) Running multiple instances and login works intermittently.** If sessions are stored in each node's local memory, the cookie is valid yet another node cannot load the old session. Configure a shared session store (e.g., Spring Session with a compatible backend), and consider session timeout, rotation, `Secure`/`HttpOnly`/`SameSite` cookies, and HTTPS.

**(8) Confusing Servlet and Reactive APIs.** `HttpSessionSecurityContextRepository`, `SecurityContextHolderFilter`, and `HttpSecurity` belong to the Servlet stack. For WebFlux, use `ServerSecurityContextRepository`, `WebSession`, `ServerHttpSecurity`, and Reactor Context.

## 9. Checklist for Applying to a Real System

1. Determine whether the application genuinely needs **stateful login** or **per-request credentials**.
2. Choose the repository for **loading** and verify that authentication filters use a compatible repository for **saving**.
3. If using WebSession, ensure cookies work, the session store fits the deployment topology, and session expiration and logout handling are tested.
4. Keep authentication in Reactor Context during request processing; do not rely on ThreadLocal.
5. Minimum tests: fresh session is unauthenticated; login followed by next request succeeds; different/expired session is rejected; logout clears identity; switching nodes preserves session if the app requires distribution.
6. When saving context in a custom flow, verify `Mono<Void>` error/completion and do not respond that login succeeded before mandatory persistence completes.

### Official Documentation for API Reference

- Spring Security 6.3 — `ServerSecurityContextRepository`: https://docs.spring.io/spring-security/site/docs/6.3.10/api/org/springframework/security/web/server/context/ServerSecurityContextRepository.html
- Spring Security 6.3 — `WebSessionServerSecurityContextRepository`: https://docs.spring.io/spring-security/site/docs/6.3.7/api/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html
- Spring Security — WebFlux Security configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Framework — `MockServerWebExchange.Builder.session(WebSession)`: https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/mock/web/server/MockServerWebExchange.Builder.html
