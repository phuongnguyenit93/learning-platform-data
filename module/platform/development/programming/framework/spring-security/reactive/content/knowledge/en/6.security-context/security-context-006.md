# ServerSecurityContextRepository and the context save/load lifecycle in Spring Security WebFlux

## Lesson objectives

In a **Spring Security - reactive** application, a user logs in successfully on one request yet still needs to be recognized on subsequent requests. `ServerSecurityContextRepository` solves **saving and loading SecurityContext across HTTP requests**. This lesson belongs to the **Security context** group and focuses on WebFlux, Reactor, and the authentication lifecycle.

After this lesson, you will be able to:

1. Accurately explain `ServerSecurityContextRepository.load(exchange)` and `save(exchange, context)`.
2. Distinguish **Reactor Context within a single subscription** from **SecurityContext persisted across multiple requests**.
3. Trace the flow: unauthenticated → form login → save to WebSession → send cookie → load → authorization → logout.
4. Evaluate `WebSessionServerSecurityContextRepository` and `NoOpServerSecurityContextRepository` by application type.
5. Consistently configure the repository for both the **load path** and the **save path** of authentication filters.
6. Build a Java 17+ example with Spring Boot 3.3.13, test requests with/without sessions, and diagnose persistence bugs.

> This guide uses APIs from `org.springframework.security.web.server.*` (WebFlux). Do not confuse them with Servlet's `SecurityContextRepository`, `HttpSessionSecurityContextRepository`, or `SecurityContextPersistenceFilter`.

## 1. What data does SecurityContext hold?

`SecurityContext` is an object containing an `Authentication`. `Authentication` describes the principal, authorities, authentication status, and related metadata.

```text
SecurityContext
  |
  +-- Authentication
        |
        +-- Principal (user, token subject, UserDetails...)
        +-- Authorities (ROLE_USER, SCOPE_read...)
        +-- authenticated (authentication status)
        +-- details / credentials depending on implementation
```

Concepts to keep separate:

| Component | Responsibility |
| --- | --- |
| `SecurityContext` | Security state, containing `Authentication` |
| `ReactiveSecurityContextHolder` | API to read/set context in **the pipeline's Reactor Context** |
| `ServerSecurityContextRepository` | Strategy to **save and retrieve** SecurityContext bound to `ServerWebExchange` |
| `WebSession` | WebFlux session, which can store SecurityContext and other attributes |
| Session cookie | Carries the **session identifier**, helping the server look up the session; does not itself contain the whole Authentication |
| `ReactiveAuthenticationManager` | Verifies credentials/tokens and emits an authenticated `Authentication` on success |
| `ReactiveAuthorizationManager` | Makes access decisions on resources; does not replace context saving/loading |

**Two distinct lifecycle levels:** Reactor Context follows the publisher/subscriber chain of **a single request**; a repository enables **subsequent** requests to reconstruct context from saved data. Calling `ReactiveSecurityContextHolder.withAuthentication(auth)` does not automatically persist `auth` into `WebSession`.

Unlike Servlet, which usually relies on `SecurityContextHolder`'s `ThreadLocal`, WebFlux can switch execution across multiple threads. When reading security context in reactive code, prefer `ReactiveSecurityContextHolder.getContext()` or principal APIs passed through the pipeline rather than assuming ThreadLocal always holds identity.

## 2. Contract of ServerSecurityContextRepository

API definition:

```java
// Signature representing the main contract; nullable annotations
// may vary by Spring Security version.
public interface ServerSecurityContextRepository {

    Mono<Void> save(
            ServerWebExchange exchange,
            SecurityContext context);

    Mono<SecurityContext> load(ServerWebExchange exchange);
}
```

`ServerWebExchange` holds the request, response, attributes, and access to `WebSession`, allowing the repository to associate a context with an HTTP exchange.

### 2.1. Meaning of load

| Result of `load(exchange)` | Proper interpretation |
| --- | --- |
| `Mono.just(securityContext)` | Repository found a context for the exchange |
| `Mono.empty()` | No saved context to restore; never emits `null` |
| `Mono.error(error)` | Error retrieving/restoring context; may indicate a session backend issue |

`Mono.empty()` is **not** a `deny` decision and certainly not `allow`. Subsequent authentication filters can still verify credentials in the request; if no authentication exists, authorization or entry points then decide whether to redirect, challenge, or reject.

A loaded context also **does not grant permissions on its own**: authorization still evaluates authentication state and authorities according to policy.

### 2.2. Meaning of save

`save(exchange, context)` returns `Mono<Void>`: normal completion signals that saving succeeded per the repository contract, while errors use `onError`. `Mono<Void>` does not emit `onNext`.

Because Reactor is normally lazy, the line below **does not guarantee saving occurs**:

```java
repository.save(exchange, context); // Not subscribed/composed.
```

It must be composed into the pipeline:

```java
// Illustrative snippet inside a custom authentication flow;
// repository, exchange, and authenticated are already available.
SecurityContext context = new SecurityContextImpl(authenticated);

return repository.save(exchange, context)
        .thenReturn(authenticated);
```

`thenReturn` emits the result after `save` completes. If saving fails, the error is not swallowed. Do not create an independent `subscribe()` inside a WebFilter or call `block()` on the event loop just to save context. With standard Spring Security, use `AuthenticationWebFilter` and built-in configuration mechanisms.

## 3. How does load occur during a request?

```text
Browser sends GET /me + session cookie
        |
        v
Spring WebFlux WebFilter pipeline
        |
        v
WebFilterChainProxy -> matched SecurityWebFilterChain
        |
        v
ReactorContextWebFilter
        |
        +-- ServerSecurityContextRepository.load(exchange)
        |        |
        |        +-- context present -> populate Reactor Context
        |        +-- empty           -> no authentication restored from repo
        |        +-- error           -> retrieval error must be handled
        |
        v
Authentication/Authorization WebFilter
        |
        v
Handler reads ReactiveSecurityContextHolder when allowed
        |
        v
Response
```

`ReactorContextWebFilter` uses the repository to initialize `ReactiveSecurityContextHolder` for downstream. This flow is **reactive**: loading is evaluated upon subscription and as downstream consumes the context; do not assume it is a synchronous query executed unconditionally at the very start of a request.

`SecurityContextServerWebExchangeWebFilter` is a related filter: it adapts `ServerWebExchange.getPrincipal()` to look up the principal via `ReactiveSecurityContextHolder`. As a result, WebFlux handlers can accept `Principal` or retrieve authentication via reactive APIs once the chain has established context.

If load is empty, the user can still be authenticated via HTTP Basic or a Bearer token in that same request. **Load is not the entire authentication process.**

## 4. How does save occur upon login?

```text
POST /login + username/password + valid CSRF token
       |
       v
AuthenticationWebFilter (form login)
       |
       +-- convert request into unauthenticated Authentication
       +-- ReactiveAuthenticationManager authenticates
       |
       +-- on success:
       |       SecurityContextImpl(authenticated Authentication)
       |                 |
       |                 v
       |       repository.save(exchange, securityContext)
       |                 |
       |                 +-- WebSession: store in session
       |                 +-- NoOp: do not retain across requests
       |                 |
       |                 v
       |       authentication success handler/redirect
       |
       +-- on failure:
               failure handler, no successful login created
```

After form login saves to `WebSession`, the response can update the cookie with the current session ID. The browser must send that cookie back on the next request. On the subsequent request, loading from `WebSession` restores the context, and the handler receives the principal.

**An easily overlooked API detail:** `ServerHttpSecurity.securityContextRepository(repository)` primarily selects the repository that `ReactorContextWebFilter` uses **for loading**. The Javadoc clearly states that **saving is configured per AuthenticationWebFilter**. For form login, use `FormLoginSpec.securityContextRepository(...)` or verify your version's default; for HTTP Basic and custom filters, check their individual save behavior as well.

```java
// Configuration snippet inside SecurityWebFilterChain, using the same repo:
return http
        .securityContextRepository(repository)           // LOAD
        .formLogin(login ->
            login.securityContextRepository(repository)) // SAVE
        .build();
```

If form login saves to `WebSession` while loading uses `NoOp`, the POST request may succeed yet the following GET request appears unauthenticated. Conversely, if loading uses `WebSession` while the form filter saves with `NoOp`, there is no saved context to restore either.

## 5. Built-in repositories

| Repository | On load | On save | Typical use |
| --- | --- | --- | --- |
| `WebSessionServerSecurityContextRepository` | Reads SecurityContext from WebSession; empty if absent | Stores context as a WebSession attribute | Web UI/form login needing persistent login |
| `NoOpServerSecurityContextRepository` | Does not load saved context | Does not save context | APIs authenticating every request with tokens/credentials |
| Custom repository | Implementation-dependent, may use distributed store | Must guarantee atomicity/lifecycle/error semantics | Specialized persistence contracts; build only when truly necessary |

### 5.1. WebSessionServerSecurityContextRepository

Class `org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository` uses an attribute inside `WebSession`. It provides `DEFAULT_SPRING_SECURITY_CONTEXT_ATTR_NAME` and `setSpringSecurityContextAttrName(...)`; `setCacheSecurityContext(boolean)` can cache load results to avoid repeated lookups when needed.

Per the official API, **each time SecurityContext is saved, the session ID is rotated to defend against session fixation**. Hence the ID before authentication and after authentication can differ. When writing integration tests, capture and send the **new cookie** returned by the login response.

WebSession is not permanent storage: timeouts, invalidation, backend storage, restarts, or load balancing can all affect it. In multi-node systems, design an appropriate shared session store (such as Spring Session with Redis) and test logout/expiration. Cookies must be protected with HTTPS, Secure, HttpOnly, and appropriate SameSite settings, and session IDs must never be logged.

### 5.2. NoOpServerSecurityContextRepository

`NoOpServerSecurityContextRepository.getInstance()` always represents the **no save/load SecurityContext** strategy. A request carrying a valid Bearer token can still be authenticated and authorized **within that request**, because the token is processed by the authentication filter. However, the next request without credentials cannot "inherit" context from NoOp.

```text
Request #1: Authorization: Bearer <valid-token>
   -> verify token -> Authentication for request #1
   -> NoOp.save: nothing persisted across requests

Request #2: no token sent
   -> NoOp.load: empty
   -> no Authentication from request #1
   -> protected endpoint requires fresh authentication
```

NoOp **does not disable all WebSessions by itself**: other components, such as a CSRF token repository or request cache, may still use sessions. It controls only persistence of **SecurityContext**, not JWT configuration, refresh tokens, CSRF, or cookies.

### 5.3. Do not equate similar interfaces

- Servlet's `SecurityContextRepository` works with Servlet request/response and has a different contract.
- `ServerCsrfTokenRepository` stores **CSRF tokens**, not SecurityContext.
- `ServerSecurityContextRepository` does not replace `ReactiveAuthenticationManager` and does not decide 401/403 itself.
- `WebSession` is session infrastructure that can hold more data than just the security context.
- `ReactiveSecurityContextHolder` propagates context through a subscription's Reactor Context, not a long-lived data store.

## 6. Complete example: Spring Boot 3.3.13, Java 17+, and form login

This example uses **a single SecurityWebFilterChain** to focus on the lifecycle. User `alice` accesses `/me` after logging in with a form. The browser sends the session cookie back on a new request, and the repository reloads `Authentication`.

### 6.1. Create the Gradle project

Structure:

```text
security-context-demo/
  settings.gradle
  build.gradle
  src/main/java/example/SecurityContextDemoApplication.java
  src/test/java/example/SecurityContextDemoApplicationTests.java
```

`settings.gradle`:

```groovy
rootProject.name = 'security-context-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Boot's BOM manages compatible versions of Spring Security, Spring Framework, and Reactor. Never mix Servlet `HttpSecurity` configuration with WebFlux `ServerHttpSecurity`.

### 6.2. SecurityContextDemoApplication.java

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@RestController
public class SecurityContextDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityContextDemoApplication.class, args);
    }

    @GetMapping("/")
    public String index() {
        return "Visit /login, then /me";
    }

    @GetMapping("/public/ping")
    public String ping() {
        return "PONG";
    }

    @GetMapping(value = "/me", produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .map(name -> "AUTHENTICATED:" + name);
    }

    @Bean
    WebSessionServerSecurityContextRepository contextRepository() {
        return new WebSessionServerSecurityContextRepository();
    }

    @Bean
    SecurityWebFilterChain securityChain(
            ServerHttpSecurity http,
            WebSessionServerSecurityContextRepository contextRepository) {

        return http
                // Load context for the current request:
                .securityContextRepository(contextRepository)
                .authorizeExchange(ex -> ex
                        .pathMatchers("/", "/login", "/public/**")
                        .permitAll()
                        .anyExchange().authenticated())
                // Save context after successful form authentication:
                .formLogin(form -> form
                        .securityContextRepository(contextRepository))
                .httpBasic(basic -> basic.disable())
                // CSRF remains enabled by default.
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails alice = User.withUsername("alice")
                .password("{noop}learn")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(alice);
    }
}
```

**Explanation:**

1. `contextRepository()` creates the repository instance storing SecurityContext in `WebSession`. Both loading and saving in form login use **the same instance**.
2. `.securityContextRepository(contextRepository)` configures loading; `formLogin(...securityContextRepository(...))` configures saving for the login filter.
3. `/me` is accessible only when authenticated and reads the username from **ReactiveSecurityContextHolder** on the active request.
4. `GET /login` uses the default form page provided by Spring Security with proper CSRF flow. `POST /login` is handled by the security filter; no custom controller is needed.
5. `{noop}learn` is only suitable for **local demos**; production must encode passwords, secure cookies/sessions, and use HTTPS.
6. HTTP Basic is disabled so requests without a context use the login UI instead of an HTTP Basic challenge.

### 6.3. Running and verifying

Requires JDK 17+ and Gradle compatible with the plugin:

```bash
gradle bootRun
```

If using Gradle Wrapper: `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

Observe in the browser:

1. Open `http://localhost:8080/public/ping` → HTTP 200, body exact **`PONG`**.
2. Open `http://localhost:8080/me` while unauthenticated → redirected to form login (`/login`).
3. Log in with username **`alice`**, password **`learn`**. The browser sends the session cookie and corresponding CSRF token.
4. Open `http://localhost:8080/me` again → HTTP 200, body:

```text
AUTHENTICATED:alice
```

5. Refresh `/me` → still shows `AUTHENTICATED:alice` while the session remains valid.
6. Open a private/incognito window without the same cookie and visit `/me` → prompted to log in again. That request cannot find a saved context for its session.

Refreshing matters: it issues **a new HTTP request**; seeing `alice` in the handler proves the client sent the current cookie and `load` restored the context. Checking only that POST login succeeded **does not prove** cross-request persistence.

### 6.4. CSRF note when testing with curl

With CSRF enabled by default, the command below can return **403**:

```bash
curl -i -X POST -d "username=alice&password=learn" \
  http://localhost:8080/login
```

The reason is that the request lacks a matching CSRF token/session, not necessarily a wrong username or repository failing to save. To log in via HTTP script, GET the login page to extract the CSRF token, keep the cookie, and send **both token and cookie** in the POST. Browsers handle this in the default form flow. Do not disable CSRF just to shorten a POST example.

## 7. Request timeline: where data is created, saved, and loaded

| Time | Request | What happens |
| --- | --- | --- |
| T0 | `GET /me` without cookie | Repo cannot restore context; entry point redirects to login |
| T1 | `GET /login` | Form page and CSRF token are prepared per configuration |
| T2 | `POST /login` valid credentials + CSRF | Authentication succeeds, context created, saved to WebSession; session ID may rotate |
| T3 | Redirect or `GET /me` with new cookie | `load` restores context, authorization permits, handler sees principal `alice` |
| T4 | `GET /me` with expired/missing cookie | No context found in session; re-login required |
| T5 | Logout handled with proper CSRF | Framework removes/invalidates context via logout handlers and repository |
| T6 | `GET /me` after logout | Old context is no longer restored, endpoint requires authentication |

Parts such as request cache, redirect URL, session creation, and cookies can vary by configuration. **Not every public request creates a WebSession**, though a CSRF component or request cache might trigger session creation.

### When save fails

The repository can emit `Mono.error(...)` due to storage issues. In a custom flow, never report success and ignore errors; compose `save` and handle failures before confirming persistence. In the framework, the exact HTTP outcome depends on authentication/error handlers.

### When load fails

`load` failing due to storage does not mean the user was business-denied. Never use `onErrorReturn(true)` or turn errors into an authenticated context. Clearly distinguish **infrastructure errors**, **absent context**, and **authorization DENY** in observability and tests.

## 8. Reactor Context is not session storage

Look at the two mechanisms side by side:

```text
Within a single subscription:
  Authentication
    -> SecurityContext
    -> ReactiveSecurityContextHolder
    -> downstream operators/handler
    -> request ends

Across requests:
  POST /login
    -> repository.save(exchange, context)
    -> WebSession storage / session cookie
    -> new GET /me request
    -> repository.load(exchange)
    -> ReactiveSecurityContextHolder
    -> authorization/handler
```

You can supply context to **one publisher**:

```java
// Illustrative snippet; authentication is an existing value.
Mono<String> currentName =
        ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName);

Mono<String> scopedPublisher = currentName.contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authentication));
```

When `scopedPublisher` is subscribed to, it has context within the appropriate subscriber scope. However, **no save operation** occurs merely from calling `contextWrite`. The next request does not inherit it automatically.

Conversely, merely calling `repository.save(...)` does not necessarily put the context into the current Reactor Context if you miswrite a custom filter. The **persistence** path and the **in-pipeline context propagation** path are separate responsibilities; Spring Security's standard authentication filter connects them in a valid flow.

## 9. Choosing a strategy for APIs and UIs

Suppose a system has both a form-login UI and a REST API called with Bearer tokens:

| Group | Typically suitable repository | Explanation |
| --- | --- | --- |
| Form-login UI and session cookie | `WebSessionServerSecurityContextRepository` | Log in once, reload context on subsequent requests |
| REST Bearer token in header per request | `NoOpServerSecurityContextRepository` | Token is sent and re-verified on every request; no need to persist context from prior requests |
| REST API using browser session cookies | May need WebSession and CSRF | JSON/REST does not automatically make cookie-based auth stateless |
| Multiple instances needing shared sessions | WebSession + suitable backing store | Ensure cross-node persistence per operational policy |

NoOp configuration snippet for the load path:

```java
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

ServerSecurityContextRepository noOp =
        NoOpServerSecurityContextRepository.getInstance();

http.securityContextRepository(noOp);
```

**This is only a configuration snippet**, not a runnable application: `ServerSecurityContextRepository` must be imported and `http` prepared. For a custom `AuthenticationWebFilter`, the repository used when saving is set via:

```java
AuthenticationWebFilter authenticationFilter =
        new AuthenticationWebFilter(authenticationManager);

authenticationFilter.setSecurityContextRepository(
        NoOpServerSecurityContextRepository.getInstance());
```

These snippets require a `ReactiveAuthenticationManager`, converter, and appropriate matcher. When using `oauth2ResourceServer(...)`, Spring Security configures the corresponding filters itself; verify the save behavior of the Resource Server mechanism itself. **Do not assume `http.securityContextRepository(noOp)` alone ensures every authentication filter uses NoOp when saving.**

With multiple `SecurityWebFilterChain` beans, each chain can have different matchers, mechanisms, and repositories. For example, `/api/**` uses Bearer/NoOp while the default UI chain uses WebSession/form login. Without careful configuration, the API might unexpectedly accept UI session cookie authentication, or the UI might lose login after redirect. Test chain, session, and credential boundaries.

## 10. Logout, session invalidation, and token revocation

Logging out must clean up **saved context**, not merely return a redirect or clear UI state. Spring Security WebFlux provides a logout filter and `SecurityContextServerLogoutHandler` to clear the security context using the configured repository. Clearing may invoke `save(exchange, null)` on APIs supporting null and remove session attributes; do not pass null yourself without verifying the version/implementation.

Expected result:

```text
POST /logout + CSRF + valid cookie
       |
       v
LogoutWebFilter + logout handlers
       |
       v
remove SecurityContext from repository
       |
       v
New request cannot load the old Authentication
```

Clearing SecurityContext can differ from invalidating all `WebSession` attributes. If writing a custom repository, support **clear/invalidate** consistently with logout and prevent sessions from continuing to hold authentication after logout. Test with a new request after logout.

Also do not confuse session logout with **Bearer JWT revocation**. A self-contained token can remain valid until expiration unless proper revocation/denylist/rotation mechanisms exist. A NoOp repository does not revoke tokens automatically.

## 11. Which tests truly prove save/load?

Behavior must be tested across **two real HTTP requests**:

| Test | Condition | Expected outcome |
| --- | --- | --- |
| Not logged in | `GET /me` without cookie | Redirect/challenge; `AUTHENTICATED:alice` is absent |
| Successful login | `POST /login` with valid CSRF + credentials | Authentication succeeds, appropriate response/session cookie |
| New request same session | `GET /me` sending post-login cookie | 200, `AUTHENTICATED:alice` |
| New request no cookie | `GET /me` in another session | Authentication required |
| Wrong password login | `POST /login` bad credentials | No authenticated context saved |
| Expired or invalidated session | `GET /me` with old cookie | Context not restored |
| Logout | Logout per policy, then `GET /me` | Old context is gone |
| NoOp | Request 1 with token, request 2 missing token | Request 2 does not inherit authentication |
| Backend failure | `load` or `save` emits error | Error handled, never treated as ALLOW |
| Multiple chains | UI cookie sent to Bearer-only API | API does not unintentionally accept UI login |

### Minimal JUnit test

Create `src/test/java/example/SecurityContextDemoApplicationTests.java`:

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class SecurityContextDemoApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteIsAccessible() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PONG");
    }

    @Test
    void protectedRouteRequiresLogin() {
        client.get().uri("/me")
                .exchange()
                .expectStatus().is3xxRedirection();
    }

    @Test
    void loginPageIsAvailable() {
        client.get().uri("/login")
                .exchange()
                .expectStatus().isOk();
    }
}
```

Run:

```bash
gradle test
```

These three tests verify the **start of the flow**, without proving persistence by themselves. When expanding integration tests with `WebTestClient`, GET login → keep cookie/CSRF → POST login → keep the **new** cookie from the response → GET `/me` with the new cookie; never use `mockUser` as proof of save/load because mocks attach a principal only for the current test and can bypass the repository.

### StepVerifier when building a custom repository

```java
// Test snippet: repository, exchange, and securityContext prepared by the test.
StepVerifier.create(repository.save(exchange, securityContext))
        .verifyComplete();

StepVerifier.create(repository.load(exchange))
        .assertNext(saved -> {
            // Compare Authentication and authorities per contract.
        })
        .verifyComplete();
```

`StepVerifier` belongs to `io.projectreactor:reactor-test` (managed by Spring Boot starter test if on classpath; add `testImplementation 'io.projectreactor:reactor-test'` when needed). Do not merely create the `save` publisher and ignore it while concluding saving was tested.

## 12. Diagnosing failures in practice

The symptom **"login succeeded, yet visiting another page prompts for login again"** can originate from multiple layers:

1. Did the login filter actually receive credentials and authenticate successfully?
2. Which repository did the filter use for `save`? Did it complete or error?
3. Did the client receive and send back the new session ID cookie after the repository rotated the ID?
4. Which repository did `ReactorContextWebFilter` use for `load`?
5. Does the session backend still hold the data, with matching session ID, timeout, cookie path/domain, and node/instance?
6. Does the handler read `ReactiveSecurityContextHolder` in the same subscription, or did it lose context by manually subscribing a separate flow?
7. Did authorization deny access for a missing authority even though context loaded successfully?

Temporarily enable DEBUG in development:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
```

When deep inspection is needed, TRACE can provide more detail. **Never log raw passwords, access tokens, SESSION cookies, or the entire SecurityContext**; use correlation IDs and minimal metadata (request path, load status present/empty/error, error type, authorization result).

**Distinguish HTTP responses:** form-login UIs typically redirect 302 when login is required; Basic/Bearer APIs typically challenge 401; authenticated without permission can be 403; storage errors can produce 5xx responses. These codes depend on the security chain's entry points and handlers, not directly inferred from a repository's `Mono.empty()`.

## 13. Common mistakes

- **Confusing load with save:** `http.securityContextRepository(...)` configures the load path; saving is also configured per authentication filter.
- **Using NoOp for a UI that must stay logged in:** POST login succeeds, yet the next GET request does not restore the user.
- **Assuming `contextWrite` is `save`:** Reactor Context does not persist into `WebSession`.
- **Assuming `save` automatically puts context into the active publisher:** persistence and context propagation must both be wired properly.
- **Not subscribing/composing `Mono<Void>`:** the save call may never execute; having no `onNext` does not mean an error.
- **Calling `block()` in WebFlux:** stalls processing threads; use Reactor operators and framework filters.
- **Interpreting `Mono.empty()` from load as DENY or ALLOW:** it simply means no context was loaded.
- **Assuming NoOp means no WebSession at all:** CSRF, request cache, or other code can still create sessions.
- **Using Servlet ThreadLocal `SecurityContextHolder`:** incompatible with reactive thread switching.
- **Testing only with mockUser:** skips real persistence/cookies/CSRF.
- **Logout only redirects without clearing the repository:** subsequent requests may still see the old principal.
- **Assuming the session ID is fixed:** WebSession repo rotates the ID on save to prevent session fixation; do not assume the cookie stays unchanged after login.
- **Confusing Servlet and WebFlux repositories:** use the `org.springframework.security.web.server.context` package.
- **Treating a 403 CSRF error as a repository bug:** check CSRF token, session, and HTTP method first.

## 14. Self-check questions

**1. Does `load(exchange)` returning `Mono.empty()` mean the account is locked?**  
No. The repo simply found no context. Downstream authentication/authorization policies decide next.

**2. Why does a form-login UI need both save and load to use the same strategy?**  
Login saves context on the POST request; the subsequent GET request uses the repository to reload it. If the two sides disagree, authentication cannot be restored.

**3. Does `ReactiveSecurityContextHolder.withAuthentication(auth)` automatically give subsequent requests auth?**  
No. It attaches context within the current Reactor pipeline without saving to a repository.

**4. Does NoOp prevent a request carrying a valid JWT from being authorized?**  
No. The token is authenticated in the current request; NoOp only avoids remembering context for future requests.

**5. `save` returns a `Mono<Void>` that completes without a value; is that an error?**  
No. `onComplete` is normal completion. Errors use `onError`. The publisher must be properly composed/subscribed.

**6. After login, why can the session cookie change?**  
`WebSessionServerSecurityContextRepository` rotates the session ID when saving context to mitigate session fixation. The client must use the updated cookie.

**7. Does clearing server-side SecurityContext automatically invalidate a JWT?**  
No. Token revocation is a separate concern.

**8. How do you prove a repository actually persists login state?**  
Perform login with valid CSRF/cookies, then send a **new request** with the server-issued cookie and verify the principal, then test again without the cookie or after logout.

**Remember:** `ServerSecurityContextRepository` manages **the save/load lifecycle across HTTP requests**; `ReactiveSecurityContextHolder` manages **context within a pipeline**. Accounts, session cookies, repo load/save, authentication filters, and authorization are distinct steps that must work in unison.

## References

- [Spring Security API — ServerSecurityContextRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html) — the `save` and `load` methods, empty result.
- [Spring Security API — WebSessionServerSecurityContextRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html) — stores context in WebSession and rotates session ID.
- [Spring Security API — NoOpServerSecurityContextRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html) — neither saves nor restores context.
- [Spring Security API — ReactorContextWebFilter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ReactorContextWebFilter.html) — populates ReactiveSecurityContextHolder from the repository's SecurityContext.
- [Spring Security API — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html) — distinguishes the repository for loading from per-authentication-filter save configuration.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html) — configuring form login and SecurityWebFilterChain.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html) — propagation of Reactor Context.
