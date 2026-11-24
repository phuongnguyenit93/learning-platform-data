# Persisting Security Context in Sessions and Controlling Session Creation Timing

## 1. Goal and Context

In Spring Security Reactive, a WebFlux request can authenticate successfully and then finish. When the browser sends the next request, how does the server know it is still the logged-in user? When does a public request need to create a session? Does calling `exchange.getSession()` already cause the server to send a cookie? And does configuring `NoOpServerSecurityContextRepository` guarantee that the entire application will never use a session?

This lesson directly answers those questions in the **Sessions and Logout** group of the **Spring Security – reactive** module.

After this lesson, you will be able to:

1. Distinguish between the **security context within a Reactor subscription**, the **security context persisted across requests**, and **`WebSession`**.
2. Understand the `ServerSecurityContextRepository.load(exchange)` and `save(exchange, context)` contract; deliberately choose between `WebSessionServerSecurityContextRepository` and `NoOpServerSecurityContextRepository`.
3. Explain why `exchange.getSession()` can return a `WebSession` that is **not yet started**, when `session.start()`/writing attributes starts the session, and when the browser sees a session cookie.
4. Know how to configure **both the read path and the write path** for the security context in WebFlux form login; avoid saving successfully while failing to restore identity on the next request.
5. Recognize other actors that can initialize a session: CSRF token repository, request cache, application code, and login; do not confuse "not saving security context" with "no session exists".
6. Design stateful browser login, distinguish it from APIs that accept credentials/tokens on every request; understand the limits of "stateless" in WebFlux.
7. Run a Java 17+ application with Spring Boot 3.x/Spring Security 6.x, verifying that GET only reads the session, POST starts the session, login creates a security context, and a subsequent request with the cookie remains authenticated.
8. Verify logout, expiry, session fixation, cookie attributes, multi-instance setups, and common pitfalls.

**Scope:** the inbound application is **Spring WebFlux**. Do not copy Servlet APIs such as `HttpSession`, `HttpSecurity`, `HttpSessionSecurityContextRepository`, or `SessionCreationPolicy` verbatim into a reactive security chain.

## 2. Three Layers of State That Must Not Be Equated

### 2.1. Reactor Context: context *within the current request*

Spring Security Reactive places `SecurityContext` into the **Reactor Context** of the subscription handling the request, and the application reads it via `ReactiveSecurityContextHolder`:

```java
// Method snippet inside a reactive service/controller.
public Mono<String> username() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
```

This is a **snippet**, requiring imports for `reactor.core.publisher.Mono` and `org.springframework.security.core.context.ReactiveSecurityContextHolder`; it is not a standalone Java class. It returns the username if a security context exists in the subscriber. This context **does not automatically survive into another HTTP request**. Switching schedulers via `publishOn`/`subscribeOn` does not imply losing context within the same subscription, nor does it create permanent login persistence.

### 2.2. ServerSecurityContextRepository: how to *save and load* across requests

`ServerSecurityContextRepository` is the strategy for loading and saving `SecurityContext` by `ServerWebExchange`:

```java
// Abbreviated API declaration for study; do not redefine this interface.
public interface ServerSecurityContextRepository {
    Mono<Void> save(ServerWebExchange exchange, SecurityContext context);
    Mono<SecurityContext> load(ServerWebExchange exchange);
}
```

`load` returns the context or completes empty when none is found; `save` returns an asynchronous publisher that completes once saving has occurred. **You must compose/return this publisher** when writing a custom authentication flow; calling `save(...)` and discarding the `Mono` does not save anything.

For browser form login, the standard implementation is `WebSessionServerSecurityContextRepository`: it puts the security context into a `WebSession` attribute; on the next request, it identifies the same session and reads it back. For stateless APIs, `NoOpServerSecurityContextRepository` skips saving/loading persistent security context.

### 2.3. WebSession: WebFlux's HTTP session

`org.springframework.web.server.WebSession` stores **server-side attributes** across HTTP requests using a session manager/store and a session ID sent back by the client, usually via a cookie. `WebSession` is not identical to `SecurityContext`:

- `WebSession` present but **not** logged in: the app may store a shopping cart, CSRF token, or saved request.
- Authentication for **a single request** without saving to `WebSession`: for example, a Bearer token or HTTP Basic re-authenticated on every request.
- `WebSession` containing a security context: browser login persists identity across requests via a repository.

Diagram:

```text
Request 1: POST /login
  Credential -> ReactiveAuthenticationManager
                |
                v
          Valid Authentication
                |
                v
       ServerSecurityContextRepository.save(...)
                |
                v
         WebSession (server-side)
           attribute SecurityContext
                |
                v
       HTTP Set-Cookie: SESSION=<opaque-id>

Request 2: GET /private
        Cookie: SESSION=<opaque-id>
                |
                v
        WebSessionManager / store
                |
                v
       ServerSecurityContextRepository.load(...)
                |
                v
       ReactiveSecurityContextHolder in Reactor Context
                |
                v
       AuthorizationWebFilter allows -> controller
```

This is a **conceptual flow** assuming the browser holds the cookie, the session has not expired, and the server has a consistent repository. The cookie **contains the session ID**, not plaintext passwords. Cookie values/attributes and when they are issued may differ when using a custom session resolver or session middleware.

## 3. Obtaining WebSession Differs from Actually Starting a Session

Spring Framework defines `ServerWebExchange.getSession()` returning `Mono<WebSession>`. `DefaultWebSessionManager` can return an existing `WebSession` object or a new one when the client does not yet have a valid session ID.

**Important:** creating a `WebSession` object **does not automatically start a persisted stateful session** and does not force sending a session ID to the client. By the `WebSession` contract, a session starts when **an attribute is added** or when code explicitly calls `start()`.

State model:

```text
New GET request
  -> exchange.getSession()             : receives a WebSession object
  -> session.isStarted() == false      : can be true
  -> reading session.getAttribute(...) : does not force start

  When session.getAttributes().put("cart", ...) or session.start():
    -> session becomes started
    -> when framework commits/saves, state is persisted
    -> session resolver may emit session cookie

Subsequent request with valid cookie:
  -> WebSessionManager retrieves session from store
  -> session.isStarted() == true (if still valid)
```

### 3.1. Reading does not mean starting

Handler snippet example:

```java
@GetMapping("/session/state")
public Mono<String> state(ServerWebExchange exchange) {
    return exchange.getSession()
        .map(session -> "started=" + session.isStarted());
}
```

A clean new request, with no other component initializing the session, usually receives `started=false`. **Do not** infer that merely calling `exchange.getSession()` produces a `SESSION` cookie. Avoid calling `session.getId()` and treating "has an ID" as a sign the session was persisted: a new `WebSession` object can already carry an internal ID before any cookie is sent.

### 3.2. Explicit start

```java
@PostMapping("/session/start")
public Mono<String> start(ServerWebExchange exchange) {
    return exchange.getSession()
        .map(session -> {
            session.start();
            return "started=" + session.isStarted();
        });
}
```

With the default WebFlux session manager, when the request completes, the started session is saved and the ID is sent to the client via the appropriate resolver/cookie. There is no need to call `subscribe()` manually to "force saving". **POST** is used here because it actively creates state, avoiding turning a GET into a state-mutating operation. In an application using form login, POST also requires a **valid CSRF token**; this example will have a `csrf()` test in section 8.

### 3.3. Implicit start when writing an attribute

```java
return exchange.getSession()
    .map(session -> {
        session.getAttributes().put("theme", "dark");
        return "saved";
    });
```

This is a method code snippet, not a standalone program. When an attribute is added, `WebSession` is considered started per the contract. Do not create a session just to store a value that could live in the browser or request scope if unnecessary: server-side state incurs costs in RAM, storage, expiry, and scaling.

### 3.4. Reasons why inferring from status/cookie can be wrong

- **GET /login** can trigger generating/saving a CSRF token and start `WebSession` before the user authenticates.
- Unauthenticated **GET /private** can write a saved request into the session to return to after login.
- App/controller code can write attributes other than the security context.
- `CookieWebSessionIdResolver` or a custom resolver can change the cookie name/attributes; do not hardcode them in production code.
- A request with a session cookie is **not** necessarily logged in; it merely holds a session ID.
- `WebSession.isStarted()` indicates session status; it **does not** replace checking `Authentication.isAuthenticated()` and authorization.

Therefore, concluding that Spring Security is mis-saving login just because `Set-Cookie` is present, or concluding an endpoint has no session just because `Set-Cookie` is absent, lacks foundation. Trace what added the session attribute and which repository persists the security context.

## 4. How Does WebSessionServerSecurityContextRepository Work?

Class `org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository` implements `ServerSecurityContextRepository`:

- `load(exchange)` looks up the security context from the corresponding `WebSession`; when absent, it returns an empty publisher.
- `save(exchange, context)` stores the context in a `WebSession` attribute.
- When saving the context, the repository **changes the session ID** to reduce **session fixation** risk. This is documented API behavior, so you should not manually write `session.changeSessionId()` before every login.
- `setSpringSecurityContextAttrName(...)` allows changing the attribute name used to store the context when there is a specific reason and it is kept consistent across the entire system.
- `setCacheSecurityContext(true)` can cache the `load` result at the publisher level for a request flow to avoid repeated lookups; this does not mean globally caching credentials.

Note that **saving the context** and **saving the cookie/session ID** are operations at different layers: the repository writes the attribute while WebFlux `WebSessionManager`/session store/resolver manage session lifecycle and identification.

### 4.1. Mechanism for loading into Reactor Context

`ReactorContextWebFilter` uses a `ServerSecurityContextRepository` to populate `SecurityContext` into `ReactiveSecurityContextHolder` for the **running request**. Thus:

```text
WebSession attribute SecurityContext (across requests)
           |
           v
ServerSecurityContextRepository.load(exchange)
           |
           v
ReactorContextWebFilter
           |
           v
ReactiveSecurityContextHolder.getContext()
           |
           v
service/controller in the same Reactor subscription
```

If you configure the **form-login filter's repository to save** while `ReactorContextWebFilter` uses a different repository to **load**, POST login may return success yet the subsequent GET request treats the user as anonymous. This is a very subtle configuration bug if you only check the redirect after POST login.

### 4.2. Read and write configuration must be synchronized

`ServerHttpSecurity.securityContextRepository(repository)` chooses the strategy used by `ReactorContextWebFilter` to **load** into Reactor Context. According to the API docs, it **does not automatically control how each `AuthenticationWebFilter` saves the context**, because the save path is configured per authentication mechanism.

For form login:

```java
// Lines inside a @Bean SecurityWebFilterChain method:
ServerSecurityContextRepository repository =
    new WebSessionServerSecurityContextRepository();

return http
    .securityContextRepository(repository) // load across requests
    .formLogin(form -> form
        .securityContextRepository(repository)) // save on login
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().authenticated())
    .build();
```

This is a **configuration snippet** to emphasize that read/write use the **same instance/semantics**; it does not yet include public routes, a user store, and form CSRF details. The runnable demo in section 7 fills in the complete setup.

Do not manually add `.contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` in a controller after authentication and treat that as session persistence. `contextWrite` only affects the scope of **that subscription**, not saving into `WebSession` for the next HTTP request.

### 4.3. Do not call save and discard the publisher

Wrong in a custom flow:

```java
repository.save(exchange, context);
return Mono.just("ok");
```

This is an **incorrect example**: `save(...)` returns `Mono<Void>`; if the publisher is discarded, the save operation may never execute.

Correct composition:

```java
return repository.save(exchange, context)
    .thenReturn("ok");
```

This is an **illustrative code snippet** assuming you already have a trusted `repository`, `exchange`, and `context`. Do not build a custom login by accepting an arbitrary username from the request and saving it into the session. Creating `Authentication` must come from `ReactiveAuthenticationManager` or a trusted authentication mechanism; Spring Security's handler already handles this when using form login.

## 5. Controlling *When* a Session Is Created Requires Looking at the Whole Pipeline

An important metric is the ratio of **stateless** requests to requests that **start/persist a session**. To avoid excessive RAM/session store usage, you must know all places where state originates:

| Activity | Can it start WebSession? | Explanation |
|---|---|---|
| `exchange.getSession()` then read-only | Usually **no** | Creates/looks up session object, no write needed yet |
| `session.start()` | **Yes** | Explicit start request |
| `session.getAttributes().put(...)` | **Yes** | Adding an attribute causes the session to start |
| Successful form login with `WebSessionServerSecurityContextRepository` | **Yes** | Saves authenticated SecurityContext into session |
| GET login page with CSRF token in WebSession | **Possibly** | Needs CSRF token state for subsequent POST |
| Hitting a protected URL while anonymous, request cache uses WebSession | **Possibly** | Saved request to redirect back after login |
| Failed login | Depends on configuration | Prior CSRF/request cache/session may exist; does not mean authenticated |
| API login verifying credentials per request with no-op repo | Not by **security-context repository** | But CSRF/request cache/app may still create a session |
| Logout | May operate on existing session | Must eliminate the ability to restore old authentication |

A public GET might not start a session, but if the response uses a template that accesses a CSRF token or a filter writes request state, the outcome changes. Do not rely on the assumption "GET never creates a session". To prove a specific endpoint **does not** start a session, test state and cookies on a clean request **under the exact real configuration**.

### 5.1. Request cache is an independent source of session creation

`WebSessionServerRequestCache` stores an interrupted protected request to redirect back to it after login. When a user opens `/private` and gets redirected to `/login`, the session may already be started **before logging in** because the cache needs to save the original URI.

`NoOpServerRequestCache` is the choice when you do not want to cache requests, commonly in stateless APIs. Changing the request cache affects browser form-login UX: after login, the browser may not return to the original URL.

### 5.2. CSRF tokens also require state in many configurations

`WebSessionServerCsrfTokenRepository` can store the CSRF token in the session. When the login page renders a form token, the session may be started to hold the token between the form GET and POST. Do not disable CSRF just because you see a session created early: CSRF protects cookie-based browser flows, including login/logout POSTs.

If using an SPA or another token mechanism, you can choose `CookieServerCsrfTokenRepository` and an appropriate security policy, but that is **how the CSRF token is stored**, not something that automatically makes `Authentication` stateless or protects against every form of CSRF.

### 5.3. Distinguish "no security session needed" from "never create a session"

`NoOpServerSecurityContextRepository` only governs **how SecurityContext is saved/loaded**. It does not prevent other code from calling `WebSession.start()`, does not disable `WebSessionManager`, does not automatically swap out the request cache/CSRF repository, and does not delete existing session cookies. An API that genuinely needs to avoid session state must inspect **the entire chain, filters, middleware, controllers, request cache, and login mechanism**.

## 6. Stateful Form Login vs. Stateless API: Two Organizational Patterns

### 6.1. Stateful browser form login

When a browser logs in via an HTML form, the components typically coordinate as follows:

```text
GET /private while not logged in
  -> authorization requires identity
  -> request cache may save URI, WebSession may start
  -> redirect /login

GET /login
  -> form and CSRF token
  -> WebSession may already hold pre-login data

POST /login + credential + CSRF + cookie
  -> ReactiveAuthenticationManager verifies
  -> valid Authentication
  -> WebSessionServerSecurityContextRepository.save(...)
  -> security context saved via WebSession, ID may change
  -> redirect to saved URL or default page

GET /private + current session cookie
  -> WebSessionServerSecurityContextRepository.load(...)
  -> ReactorContextWebFilter puts context into subscriber
  -> authorization allows request to proceed
```

What needs testing is not just that `POST /login` returns 302; there must be a **subsequent GET with the cookie** that receives the right user's data.

### 6.2. Stateless API not using sessions to store authentication

An **illustrative configuration snippet** for an API authenticating per request via HTTP Basic, not a complete standalone configuration:

```java
ServerSecurityContextRepository noOp =
    NoOpServerSecurityContextRepository.getInstance();

return http
    .securityContextRepository(noOp)   // load: do not restore login from session
    .httpBasic(basic -> basic
        .securityContextRepository(noOp)) // save: do not save auth into session
    .formLogin(form -> form.disable())
    .requestCache(cache -> cache
        .requestCache(NoOpServerRequestCache.getInstance()))
    .authorizeExchange(exchanges -> exchanges
        .anyExchange().authenticated())
    .build();
```

Import the WebFlux Security classes in `org.springframework.security.web.server...`; the code requires a suitable `ReactiveAuthenticationManager`/user store. This is an **example of a persistence decision**, not proof that the entire application never creates a `WebSession`. HTTP Basic verifies credentials on every request and is not a replacement for Bearer tokens in every system. If a browser automatically sends Basic credentials, **evaluate CSRF per the threat model**; do not automatically disable CSRF just because the API is called stateless.

For REST APIs protected by a JWT Bearer Resource Server, the typical model is likewise **verifying the token on every request**, with no need to store `Authentication` across requests in `WebSession`. However, JWT signature, issuer, audience, expiry, scope/authorities, and an appropriate revocation policy must be checked. Endpoints accepting cookies or operating through a browser still require separate CSRF evaluation.

### 6.3. Do not copy Servlet's SessionCreationPolicy

A configuration snippet commonly seen in Servlet tutorials:

```java
// Servlet only, do not apply verbatim to ServerHttpSecurity:
http.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS));
```

This is **wrong-stack example code in a WebFlux context**. `SessionCreationPolicy` belongs to HTTP Servlet `HttpSecurity`/`HttpSession`. With reactive, look at `ServerSecurityContextRepository`, `ServerRequestCache`, `WebSession`, and related components. Having `ServerHttpSecurity.sessionManagement(...)` in versions with session/concurrency management APIs does not mean it has the same `sessionCreationPolicy(...)` method as Servlet.

Do not claim a single line of `NoOpServerSecurityContextRepository` is 100% equivalent to `STATELESS` across all framework components.

## 7. Runnable Project: Observing the Session Before and After Login

The demo application has three key endpoints:

- `GET /session/state`: only inspects `WebSession` and reports `isStarted`.
- `POST /session/start`: explicitly calls `start()`; still **has not** authenticated anyone.
- `GET /private`: only allows users logged in via form, reading `ReactiveSecurityContextHolder` to return the username.

From this we separate **an existing session** from **an authenticated SecurityContext**.

### 7.1. Dependencies and file structure

Create a Spring Initializr project with Java 17+, Spring Boot 3.x, Gradle, Spring Reactive Web, Spring Security, Spring Boot Starter Test, and Spring Security Test. In the `build.gradle` generated by Initializr, keep plugins, repositories, dependency management, and the Java toolchain; dependencies block:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

This is a **dependencies block**, not a complete standalone `build.gradle`. Do not add `spring-boot-starter-web` because inbound WebFlux can be replaced by Servlet/MVC when both starters are present.

File structure:

```text
src/main/java/demo/sessionsecurity/
  SessionSecurityApplication.java
  SecurityConfig.java
  SessionController.java
src/test/java/demo/sessionsecurity/
  SessionSecurityTests.java
```

### 7.2. `SessionSecurityApplication.java`

```java
package demo.sessionsecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionSecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(SessionSecurityApplication.class, args);
    }
}
```

### 7.3. `SecurityConfig.java`: one repository for load/save

```java
package demo.sessionsecurity;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.ServerSecurityContextRepository;
import org.springframework.security.web.server.context.WebSessionServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    public ServerSecurityContextRepository securityContextRepository() {
        return new WebSessionServerSecurityContextRepository();
    }

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http,
            ServerSecurityContextRepository repository) {
        return http
            .securityContextRepository(repository)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET,
                    "/", "/session/state").permitAll()
                .pathMatchers(HttpMethod.POST,
                    "/session/start").permitAll()
                .pathMatchers("/login").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/private").authenticated()
                .anyExchange().denyAll()
            )
            .formLogin(form -> form
                .securityContextRepository(repository))
            .httpBasic(basic -> basic.disable())
            .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails student = User.withUsername("student")
            .password(encoder.encode("student-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(student);
    }
}
```

In the demo:

1. `securityContextRepository()` returns an instance of `WebSessionServerSecurityContextRepository`.
2. `http.securityContextRepository(repository)` provides the read source for `ReactorContextWebFilter`.
3. `formLogin(form -> form.securityContextRepository(repository))` specifies where the login filter **saves** `Authentication`.
4. `GET /session/state` is public and read-only. `POST /session/start` is public yet modifies the session, so it requires CSRF; this endpoint is **only for experimentation** and should not be exposed to anonymous users in production.
5. `/login` is public; Spring Security generates the form login page and handles POST login. `/private` requires authentication.
6. Default CSRF **is preserved**; we do not disable it to let POST login/POST start bypass protection unsafely.
7. HTTP Basic is disabled so browsers follow a consistent form-login flow.
8. User/password are demo data, not stored in plaintext in an account store: the password is hashed with `DelegatingPasswordEncoder`; do not reuse sample credentials in production.

**Why not call `new WebSessionServerSecurityContextRepository()` separately in two places?** Two instances with the same default config can usually read the same attribute; however, using one bean clarifies the contract and avoids mismatches in attribute name or caching when customizing. More importantly, **matching type and matching semantics** on load/save ensure the next request can read the context.

### 7.4. `SessionController.java`

```java
package demo.sessionsecurity;

import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@RestController
public class SessionController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping("/session/state")
    public Mono<String> state(ServerWebExchange exchange) {
        return exchange.getSession()
            .map(session -> "started=" + session.isStarted());
    }

    @PostMapping("/session/start")
    public Mono<String> start(ServerWebExchange exchange) {
        return exchange.getSession()
            .map(session -> {
                session.start();
                return "started=" + session.isStarted();
            });
    }

    @GetMapping("/private")
    public Mono<String> privatePage() {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .map(name -> "hello " + name);
    }
}
```

Methods return `Mono`, without calling `block()` or `subscribe()` inside request handlers. In Spring WebFlux, the session manager handles saving at the end of the HTTP exchange lifecycle; the example only needs `session.start()` when wanting to start explicitly.

`/private` does not call `getSession()` directly: it reads `SecurityContext` from the Reactor Context already populated/set by Spring Security for the request. This separates the responsibility of the **security filter** from the business controller.

### 7.5. Expected results with browser and curl

Run the Gradle wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

In another terminal:

```bash
curl -i http://localhost:8080/session/state
curl -i http://localhost:8080/private
```

With a client that has no session and no other component adding attributes on public requests, `GET /session/state` is expected to return body:

```text
started=false
```

It typically **does not** need `Set-Cookie: SESSION=...`. Note that if the app has extra custom filters/session middleware attached or a CSRF token is requested/rendered during the request, the result may change; this is a demo under a specific configuration.

Unauthenticated `GET /private` normally returns `302 Location: /login` because form login is enabled. Request cache or CSRF may initialize a session during this flow; that **does not mean the user is authenticated**.

In the browser:

1. Open `http://localhost:8080/private` in a logged-out profile.
2. The browser redirects to the generated `/login`, carrying any cookie/session if the framework created one.
3. Log in with `student` / `student-pass`. The generated form includes a valid CSRF token for the session.
4. Login succeeds; the browser is redirected to the saved request or default page.
5. Open `/private`: expected `hello student`.
6. Open `/session/state` in the same profile: expected `started=true` because the session now holds the security context.

Do not use GET directly to test `/session/start`: the demo endpoint only accepts POST and requires CSRF by default. An HTTP POST without a token receives `403`; this is normal protection behavior, not a bug.

### 7.6. Changing cookie and timeout configuration

Example Spring Boot 3.x properties for an **HTTPS environment**:

```properties
# application.properties - example configuration, verify against your environment
server.reactive.session.timeout=20m
server.reactive.session.cookie.name=SESSION
server.reactive.session.cookie.http-only=true
server.reactive.session.cookie.secure=true
server.reactive.session.cookie.same-site=lax
```

`secure=true` should only be enabled when the site is served over HTTPS (or a TLS reverse proxy with properly configured forwarded headers); Secure cookies are not sent by browsers over plain HTTP. Because the demo runs at `http://localhost:8080`, **do not copy this entire block into the local demo and conclude login is broken** when the browser refuses to send the Secure cookie.

`timeout=20m` is the **idle expiration timeout** per the session manager/store, not a guarantee that the browser is logged out at the exact millisecond while a tab stays open. With external Spring Session, check the separate session repository timeout configuration and the distributed store's lifecycle. Cookie flags are necessary, but do not replace CSRF, session fixation protection, logout, and authorization.

## 8. Testing with WebTestClient: Unstarted Session, Starting, Then Saving Authentication

To test WebFlux security filters without manually parsing an HTML CSRF token, we use `WebTestClient.bindToApplicationContext(...)` with `SecurityMockServerConfigurers.springSecurity()`. The tests use a mock WebFlux application context and the framework-provided session repository; they exercise multiple requests/cookies via `WebTestClient` methods.

Create `src/test/java/demo/sessionsecurity/SessionSecurityTests.java`:

```java
package demo.sessionsecurity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SessionSecurityTests {

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
    void sessionObjectCanBeReadWithoutStartingIt() {
        client.get().uri("/session/state")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class)
            .isEqualTo("started=false");
    }

    @Test
    void startDoesNotMeanAuthentication() {
        var startResult = client.mutateWith(csrf())
            .post().uri("/session/start")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("started=true")
            .returnResult();

        ResponseCookie sessionCookie =
            startResult.getResponseCookies().getFirst("SESSION");
        assertNotNull(sessionCookie);

        client.get().uri("/session/state")
            .cookie("SESSION", sessionCookie.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("started=true");

        client.get().uri("/private")
            .cookie("SESSION", sessionCookie.getValue())
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void loginSavesAuthenticationForANewHttpRequest() {
        var loginResult = client.mutateWith(csrf())
            .post().uri("/login")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "username", "student").with("password", "student-pass"))
            .exchange()
            .expectStatus().is3xxRedirection()
            .expectBody().isEmpty()
            .returnResult();

        ResponseCookie sessionCookie =
            loginResult.getResponseCookies().getFirst("SESSION");
        assertNotNull(sessionCookie);

        client.get().uri("/private")
            .cookie("SESSION", sessionCookie.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("hello student");
    }

    @Test
    void missingCsrfRejectsStateChangingPost() {
        client.post().uri("/session/start")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void sessionCookieIsNotRequiredForPublicHome() {
        client.get().uri("/")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("home");
    }
}
```

### 8.1. Why are these tests valuable?

- `sessionObjectCanBeReadWithoutStartingIt` separates creating the `WebSession` object from `isStarted`. Under the **exact demo configuration**, the public request only reads the session and no component intentionally writes an attribute.
- `startDoesNotMeanAuthentication` proves a started session can still be **anonymous**. A cookie only represents state, not granted roles.
- `loginSavesAuthenticationForANewHttpRequest` proves that successful POST login and GET `/private` **are two separate HTTP exchanges**: the second request only carries the cookie without resending the password; the user is still recognized via the repository.
- `missingCsrfRejectsStateChangingPost` proves state-creating endpoints do not bypass CSRF.
- `sessionCookieIsNotRequiredForPublicHome` proves the `permitAll()` rule allows access to public resources.

In `loginSavesAuthenticationForANewHttpRequest`, `mutateWith(csrf())` is a **test helper** that generates/attaches a valid token in the mock WebFlux security environment; it is not a valid way for real-world clients to "fabricate" CSRF tokens. Real browsers must obtain the token from the login page/same session.

The tests use the default `SESSION` cookie. If you changed `server.reactive.session.cookie.name` or replaced the resolver, read and use the **actual cookie name** in tests instead of hardcoding `SESSION`. Do not assert a fixed ID: Spring Security may rotate the session ID after saving authentication to prevent session fixation.

### 8.2. Running and interpreting results

From the project root:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

**5 tests are expected to pass** with Spring Boot 3.x/Spring Security 6.x in the presented configuration. This is an **expectation from the code**, not a claim that Gradle was run in the learner's environment. If a test fails on a specific version/test adapter, inspect the actual response cookies, status, session repo, and security filter setup instead of removing assertions.

Full-system testing should add a real browser test or live-server HTTP test to confirm cookie attributes, session rotation, TLS, load balancing, and timeouts. Mock `WebTestClient` does not replace network/reverse-proxy verification.

### 8.3. A test you should have to prevent cross-user session mix-ups

After a successful login as `student`, create another HTTP client that sends no cookie and call `/private`. That client must still be redirected/challenged as anonymous. User A's cookie must never turn into global authentication for user B. Never store `Authentication` in a static field or mutable singleton to "remember" logins.

## 9. When Should Session Creation Be Avoided in Large Systems?

Every started session can consume RAM or distributed store capacity, while generating read/write traffic, TTLs, and cleanup overhead. If the server issues session cookies on every crawler/public-asset request, the number of sessions can grow unnecessarily.

A control approach:

1. Identify which endpoints **must** have a session (browser login, cart, wizard, optional CSRF state).
2. For purely public GET endpoints, avoid calling `session.start()` or `put`ting attributes without reason.
3. Review request cache configuration: do not cache every request unnecessarily, especially machine-to-machine APIs.
4. For an API authenticating a token on every request, prefer `NoOpServerSecurityContextRepository` or an equivalent strategy when session persistence is unnecessary, and review request cache/CSRF/cookies across the entire pipeline.
5. Do not disable CSRF merely to "reduce sessions": if browsers automatically send cookies/credentials, you must evaluate the CSRF threat model.
6. Measure **started sessions**, session creation rate, RAM/Redis storage, invalidation/expiration, session counts per tenant, and anomalous frequencies.
7. When migrating from stateful to stateless, test the authentication/authorization path for every request, not just login redirects.

### 9.1. Session count and session store

In basic WebFlux, `DefaultWebSessionManager` typically uses `InMemoryWebSessionStore`; this data belongs to one application instance and is not automatically shared across nodes. When running multiple instances, if request 1 logs in on pod A but request 2 lands on pod B, pod B may not find the `WebSession`; the user gets redirected to login again.

Production handling can be Spring Session Reactive with Redis or suitable storage, or a token-based architecture independent of server sessions, depending on requirements. **Sticky sessions** may alleviate some symptoms but do not handle failover/pod restarts well, nor do they automatically synchronize revocation/logout across instances.

### 9.2. Timeout, idle expiration, and logout

`WebSession` has an idle timeout; the session store can remove state when expired. When an old cookie is resent after the session has expired, the server may create a new unauthenticated `WebSession` object. Therefore, a protected GET after expiry must require logging in again.

In browser flows, logout must eliminate the ability to restore authentication: use the official logout handler/DSL. When full-session invalidation is required, `WebSession.invalidate()` is the appropriate API to remove state; it is not enough to guarantee the browser no longer holds **independent credentials** such as remember-me, JWT, or cached HTTP Basic credentials. Exact logout depends on the authentication mechanism.

Example snippet for **authorized custom session revocation**:

```java
return exchange.getSession()
    .flatMap(session -> session.invalidate());
```

This is only a **code snippet** within a flow that has proper authn/authz; it does not replace the full Spring Security logout handler. `invalidate()` returns `Mono<Void>` and must be returned/composed, not manually subscribed to with `subscribe()` while ignoring completion.

### 9.3. Session fixation and ID rotation

An attacker may try to trick a user into pre-using a session ID known to the attacker. If the server does not change the session ID when the user logs in, the attacker risks being able to use the same ID to access the authenticated session.

`WebSessionServerSecurityContextRepository` has a mechanism to **rotate the ID when saving SecurityContext** per the API documentation. Test that the client uses the **post-login** cookie ID; do not try to reuse the old ID. When writing a custom context repository/login handler, protect against session fixation with an equivalent design—do not assume a session is "safe because cookies are random" and ignore the ID lifecycle.

### 9.4. Session theft, revocation, and cookie flags

- `Secure`: browsers send the cookie over HTTPS appropriately.
- `HttpOnly`: reduces the ability of JavaScript to access the session cookie.
- `SameSite`: restricts certain cross-site flows; does not fully replace CSRF tokens.
- `Path`/`Domain`: limits the scope where the cookie is sent.
- Expiration/idle timeout, logout, device/session management, and anomaly alerts reduce the exploitation window of stolen cookies.
- Session IDs are sensitive data: never log raw values into logs, URLs, analytics, exceptions, support tickets, or tracing baggage.
- With reverse proxies, only trust forwarded headers from trusted proxies; configure HTTPS/TLS termination properly so redirects and Secure cookies work.

## 10. Comparison Table of Security Context Persistence Strategies

| Configuration | Loads SecurityContext on next request | Saves after authentication | Can a session be created by other components? |
|---|---|---|---|
| `WebSessionServerSecurityContextRepository` for both load and save | Yes, if cookie/session is valid | Yes, saved into WebSession | Yes |
| `NoOpServerSecurityContextRepository` for both load and save | Not from this repository | Not from this repository | **Yes** (CSRF, request cache, app code) |
| Load from WebSession, but form login saves to no-op | No new context to load after login | Does not save new login | Yes |
| Form login saves to WebSession, but load uses no-op | Next request does not restore context from WebSession | Saved, but not loaded properly | Yes |
| Only `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` | Does not persist across requests | No | Depends on other components |
| Per-request Bearer JWT authentication | New token verified each request | Does not necessarily use a session | Depends on other components |

The table describes the **meaning of each persistence strategy**; do not deduce whether a request has or lacks `Set-Cookie` solely from a class name. Other Spring Security components can use sessions independently of the authentication repository.

## 11. Common Mistakes

1. **Thinking `exchange.getSession()` always issues a cookie.** It returns a `WebSession` object, not necessarily started; observe `isStarted()` and actual state.
2. **Relying on `session.getId()` to confirm persistence.** A new session object also has an ID; check whether the session is started/persisted and check actual cookies.
3. **Confusing `WebSession` with `Authentication`.** An anonymous session can still exist due to CSRF/request cache.
4. **Configuring the repo only for loading, forgetting form login save.** POST login succeeds, yet subsequent requests lack the expected security context.
5. **Configuring form login save only, forgetting the load side.** Authentication is stored, but WebFlux does not restore it through the right repository.
6. **Calling `repository.save(...)` and discarding the publisher.** Reactor is lazy; you must compose and return the `Mono`.
7. **Using `contextWrite` to "persist login".** `contextWrite` is subscription-scoped, not server-side session persistence.
8. **Enabling NoOp and declaring the whole system stateless.** CSRF, saved requests, OAuth2 state, and controllers can still create sessions.
9. **Disabling CSRF because POST login got 403.** Send the token with the matching session instead of stripping browser protection.
10. **Confusing Servlet's `SessionCreationPolicy` with `ServerHttpSecurity`.** Do not copy DSLs from another stack verbatim into WebFlux.
11. **Using GET to start a session without reason.** GET should be safe/idempotent; the demo deliberately uses POST.
12. **Exposing a session-start endpoint to anonymous users in production.** It can be abused to flood sessions; the demo is a learning exception.
13. **Assuming `Set-Cookie` = logged in.** A cookie only identifies a session; it says nothing about roles or credentials.
14. **Assuming no `Set-Cookie` on a response means no session exists.** The cookie may have been set earlier and sent back via the `Cookie` header.
15. **Failing to retain cookies after redirects or session ID rotation.** Clients using the stale cookie lose the login.
16. **Lacking a distributed session store across multiple nodes.** State is lost when a load balancer switches nodes or pods restart.
17. **Relying on ThreadLocal `SecurityContextHolder` in a reactive controller.** Use `ReactiveSecurityContextHolder` from the Reactor subscription.
18. **Storing raw passwords/tokens/session IDs in `WebSession` and logs.** Minimize secrets/sensitive data, storing only necessary state with a TTL.
19. **Skipping timeout/revocation/logout tests.** Sessions may remain valid longer than policy intends.
20. **Testing only mock contexts without testing HTTP cookie continuity.** Tests must issue a new request and resend the cookie received after login.

## 12. Exercises with Answers

**Exercise 1 — Does an existing session object mean the session is persisted?**

`exchange.getSession()` returns `WebSession`, `isStarted() == false`, no attributes added. When the request finishes, is the client guaranteed to receive a cookie?

**Answer:** No. Creating/looking up a `WebSession` does not automatically start the session. Cookie/session persistence is only required once the session starts per manager/resolver policy. Do not treat `getId()` as proof.

**Exercise 2 — Session has a cookie but the user is not logged in**

A browser opens `/login` and receives a `SESSION` cookie due to the CSRF token. The browser then calls `/private` without sending credentials. Will it access the page?

**Answer:** No. A started session does not mean there is an authenticated `Authentication`. Authorization still requires login.

**Exercise 3 — Save and load use conflicting strategies**

You configure form login to use `WebSessionServerSecurityContextRepository` for saving, but `ServerHttpSecurity.securityContextRepository(NoOpServerSecurityContextRepository.getInstance())` for loading. POST login returns 302, yet the next GET `/private` redirects to `/login`. Why?

**Answer:** Login saved the context, but `ReactorContextWebFilter` did not read it on the next request. Use compatible load/save strategies and test HTTP cookie continuity.

**Exercise 4 — Is NoOp enough to guarantee no sessions are created?**

Replace both load and save security repos with no-op. However, controller `GET /cart` writes a cart attribute into `WebSession`. Can a session cookie appear?

**Answer:** Yes. NoOp only controls `SecurityContext` persistence. The controller can still start `WebSession`; avoiding sessions requires inspecting the entire pipeline.

**Exercise 5 — Form login needs to redirect back to the previous URL**

An unauthenticated user opens `/private`, the request cache saves the URI into `WebSession`, then redirects to `/login`. If you disable the request cache wanting "no session before login", what changes?

**Answer:** The browser may not return to `/private` after login and instead go to the landing page chosen by the success handler. You must weigh UX against state rather than disabling the request cache arbitrarily.

**Exercise 6 — How to test persisting identity across two HTTP requests**

A test calls `POST /login` with valid credentials, sees 302, and ends. Is that enough to prove session context persistence?

**Answer:** Not yet. You must take the **post-login** session cookie, send a new GET `/private` with only that cookie, and verify 200 and the right username. Also verify a client without a cookie is still prompted to log in.

**Exercise 7 — What happens when a session expires?**

The client still holds the `SESSION` cookie, but the server-side session was evicted due to idle timeout. What happens on a new request to a protected URL?

**Answer:** There is no longer a context to restore; the client typically becomes anonymous and is asked by the entry point to re-authenticate (form login may redirect). Keeping the old cookie does not revive an expired session.

**Exercise 8 — Why rotate the session ID on login?**

**Answer:** To reduce session fixation risk: an attacker knows a session ID before the user logs in and tries to reuse it after login. Spring Security's `WebSession` repository rotates the ID when saving the context; tests/clients must continue with the post-login cookie.

**Exercise 9 — Choosing a design for a machine-to-machine API**

An API accepts a Bearer JWT on every request, with no browser form login. Does it need to store security context in `WebSession` across requests?

**Answer:** Usually no. Verify the JWT properly on each request and use no-op security context persistence when appropriate; also inspect request cache, CSRF, app state, and other filters. Stateless does not mean skipping authorization, expiry, signature validation, or auditing.

## 13. Operational Checklist

- [ ] The actual inbound stack is WebFlux; use `ServerHttpSecurity` and `ServerSecurityContextRepository`, not Servlet equivalents.
- [ ] Security context is persisted according to the authentication mechanism: form login needs consistent read/save.
- [ ] Do not treat a `WebSession` object or session cookie as proof the user is authenticated.
- [ ] Only start a session when there is state worth saving; consider the impact of CSRF/request cache/login.
- [ ] Public endpoints do not accidentally mass-create sessions due to filters or app attributes.
- [ ] For stateless APIs, inspect the **entire** pipeline instead of just adding `NoOpServerSecurityContextRepository`.
- [ ] Browser POST login/logout/state-changing requests have proper CSRF protection.
- [ ] HTTPS/TLS, cookie Secure/HttpOnly/SameSite/Path/Domain/timeout fit the environment.
- [ ] Session fixation protection, ID rotation, and logout invalidation have been tested.
- [ ] Do not store/log passwords/secrets/session IDs in logs, traces, URLs, or unnecessary responses.
- [ ] Multi-instance systems have an appropriate shared session store/failover strategy, or a genuinely stateless architecture.
- [ ] Test pre-login requests, post-login requests with cookie, without cookie, logout, timeout, and missing roles.
- [ ] Measure session creation rate, active sessions, storage footprint, and anomalies by IP/tenant.
- [ ] All reactive repository operations (`save`, `invalidate`) are returned/composed, never manually `subscribe()`d.

## 14. Quick Summary

```text
New public GET
  exchange.getSession() -> WebSession object (may have isStarted=false)
  read-only -> does not force a session cookie

NEED STATE:
  session.start() OR add a session attribute
  -> WebSession started -> session manager saves state/cookie

FORM LOGIN:
  Authentication success
  -> WebSessionServerSecurityContextRepository.save(...)
  -> SecurityContext into WebSession, session ID rotated against fixation

NEXT REQUEST:
  Valid cookie/session -> repository.load(...)
  -> ReactorContextWebFilter -> ReactiveSecurityContextHolder
  -> AuthorizationWebFilter -> handler

STATELESS:
  NoOpServerSecurityContextRepository does not save/load SecurityContext
  BUT does not prevent CSRF/request cache/app from creating WebSession

LOGOUT / EXPIRE:
  session context is gone -> protected requests require re-authentication
```

**Two boundaries to remember:** (1) `Reactor Context` belongs to a **request subscription**, whereas `WebSession` and `ServerSecurityContextRepository` hold state **across HTTP requests**; (2) "having a `WebSession` object" differs from "session is started", and "having a session" differs from "user is authenticated".

## 15. Official Documentation

- [Spring Framework — WebSession API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebSession.html)
- [Spring Framework — DefaultWebSessionManager API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/server/session/DefaultWebSessionManager.html)
- [Spring Security — WebSessionServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html)
- [Spring Security — ServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html)
- [Spring Security — NoOpServerSecurityContextRepository API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/context/NoOpServerSecurityContextRepository.html)
- [Spring Security — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — FormLoginSpec API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html)
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — WebFlux CSRF](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — WebFlux Test](https://docs.spring.io/spring-security/reference/reactive/test/web/)
- [Spring Boot 3.4 — Reactive session/cookie application properties](https://docs.spring.io/spring-boot/3.4/appendix/application-properties/)
- [Spring Boot — Spring Session Reactive](https://docs.spring.io/spring-boot/3.4/reference/web/spring-session.html)
