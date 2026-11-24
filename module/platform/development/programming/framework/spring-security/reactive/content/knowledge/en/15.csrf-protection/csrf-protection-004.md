# WebSessionServerCsrfTokenRepository and Storing Tokens in a Session

## 1. Problem: why must a CSRF token be linked to a session?

In a Spring WebFlux application with a browser UI, a user may already be authenticated via a login cookie, HTTP Basic credentials cached by the browser, or another mechanism the browser auto-attaches to requests. When the user visits an unintended page, that page can cause the browser to send a request to the application. If the server only checks the auto-attached credentials, a data-changing operation can be triggered without the user intentionally initiating it. That is **Cross-Site Request Forgery (CSRF)**.

A standard defense is the **Synchronizer Token Pattern**:

1. The server generates an unpredictable token value and retains the **expected value** on the server side, typically bound to the browser's session.
2. The legitimate application supplies the token to the page/form or JavaScript in a trusted origin.
3. When sending POST/PUT/PATCH/DELETE, the client sends the token in a **header or form parameter**, rather than relying solely on cookies auto-sent by the browser.
4. The server loads the expected token and compares it with the token presented by the client. If missing or invalid, the request is rejected before business logic executes.

In Spring Security Reactive, the **`WebSessionServerCsrfTokenRepository`** class is the `ServerCsrfTokenRepository` implementation that uses **`WebSession`** to save/load the expected CSRF token. It is the **default** storage choice for CSRF in standard Spring Security WebFlux configurations.

Key point:

> `WebSessionServerCsrfTokenRepository` stores an **anti-CSRF token**, not a username/password or a "copy of the Authorization header". Nor is it a mechanism to auto-login or auto-authorize requests.

### What you will learn

- Clearly explain how CSRF tokens, token repositories, `WebSession`, and session ID cookies relate to one another.
- Correctly read the `generateToken`, `saveToken`, and `loadToken` contracts and what an empty `Mono` means.
- Understand Spring Security WebFlux defaults, on-demand token generation, and the difference between the stored expected token and the masked token rendered to clients.
- Configure `ServerHttpSecurity.csrf` with `WebSessionServerCsrfTokenRepository`, using `setSessionAttributeName` or customizing header/form field names when needed.
- Run a Java 17+, Spring Boot, Gradle, WebFlux + Basic + WebSession-backed CSRF project and test HTTP 200/401/403.
- Diagnose missing cookies, session timeouts, stale CSRF tokens after logout, reverse proxies, multiple instances, and React/SPA behavior.
- Distinguish `WebSessionServerCsrfTokenRepository` from `CookieServerCsrfTokenRepository` and stateless API considerations.

This lesson belongs to the **CSRF Protection** group of the Spring Security - reactive module; examples use local credentials strictly for illustration. Never use demo passwords or unencrypted HTTP over the Internet.

## 2. Concepts that must be distinguished

| Concept | Nature | Role in CSRF protection |
| --- | --- | --- |
| `CsrfToken` | Data holding `headerName`, `parameterName`, `token` | Describes field names and token value |
| `ServerCsrfTokenRepository` | Reactive interface | Generates, saves, and loads the **expected token** |
| `WebSessionServerCsrfTokenRepository` | Repository backed by `WebSession` | Stores token as a session attribute |
| `WebSession` | Spring WebFlux session object | Holds session data and has ID, timeout, and lifecycle |
| Session ID cookie (usually `SESSION`) | Value stored by browser so server locates `WebSession` | Binds incoming request to the session holding the token |
| `CsrfWebFilter` | Spring Security WebFilter | Coordinates token checking when request requires CSRF protection |
| `ServerCsrfTokenRequestHandler` | Strategy for exposing/resolving request tokens | Exposes `Mono<CsrfToken>` and resolves client-submitted token |
| `XorServerCsrfTokenRequestAttributeHandler` | Default request handler since Spring Security 6 | Masks/unmasks tokens to mitigate BREACH risk |
| `ServerSecurityContextRepository` | Saves/loads `SecurityContext` | **Distinct** from CSRF repository; may use `WebSession` or no-op |
| `ReactiveSecurityContextHolder` | Reactor Context of current subscription | Reads downstream authentication, not a CSRF token store |

An application can configure `NoOpServerSecurityContextRepository` to **avoid persisting authentication across sessions** while still using `WebSessionServerCsrfTokenRepository` to store CSRF tokens in the session. Therefore, "HTTP Basic authenticates every request" does not imply "no `WebSession` is ever created".

Conversely, if the server persists `SecurityContext` in the session and you arbitrarily disable CSRF, browsers using login cookies become exposed to forged requests. Evaluate **authentication persistence** and **CSRF protection** as two separate concerns.

## 3. Synchronizer Token Pattern mechanics with WebSession

Examine the exact flow:

~~~text
Browser                                          Spring WebFlux + Security
   |                                                        |
   | 1. GET /csrf (authenticated or per policy)             |
   |------------------------------------------------------->|
   |                                                        |
   |     CsrfWebFilter + token request handler              |
   |           |                                            |
   |           +--> Repository.loadToken(exchange)          |
   |           |      (if no token yet)                     |
   |           +--> Repository.generateToken(exchange)      |
   |           +--> Repository.saveToken(exchange, token)   |
   |                  |                                     |
   |                  v                                     |
   |           WebSession holds expected token              |
   |                                                        |
   | 2. Response: presented token + Set-Cookie SESSION=...  |
   |<-------------------------------------------------------|
   |                                                        |
   | 3. POST /api/note                                      |
   |    Cookie: SESSION=<id>                                |
   |    X-CSRF-TOKEN: <issued-token>                        |
   |------------------------------------------------------->|
   |                                                        |
   |     WebSessionServerCsrfTokenRepository.loadToken      |
   |       --> expected token of the same session           |
   |     Request handler resolves/unmasks presented token   |
   |     Compare --> valid token?                           |
   |                                                        |
   | 4. Yes --> authentication/authorization, run handler   |
   |    No  --> reject request, typically HTTP 403          |
   |<-------------------------------------------------------|
~~~

This is a conceptual diagram. Exact execution order depends on the WebFilter chain, authentication method, and Spring Security version; **not every GET creates a session/token** because the framework generates/loads tokens on demand.

### 3.1. Both pieces must come from the same context

With this repository, a successful POST normally requires **both**:
- The session ID cookie so the server locates the `WebSession` holding the expected token.
- The CSRF token value issued by the application, sent by the client in a header or form parameter.

If only the token is sent without the session cookie, the repository may find a **different or brand-new session** lacking the expected token. If only the cookie is sent without the token, the server still lacks proof that the request originated from a valid context. Both cases normally yield 403 on protected methods.

**A CSRF token is not a session ID.** Never pass the `SESSION` cookie value in place of `X-CSRF-TOKEN`, and never use a CSRF token as a Bearer token to authenticate identity.

### 3.2. Why is a server-side session needed?

Synchronizer tokens keep the expected value on the server side. The browser only retains a session identifier so the server locates the right data, while the legitimate application passes the token in a way external-origin websites cannot arbitrarily read.

With multiple instances:
- If sessions reside solely in one instance's memory, a subsequent request routed to another instance may fail to find the expected token.
- You can use intentional sticky sessions or Spring Session with Redis/a shared store so all instances read the same `WebSession`.
- Session cookies and datastores must have appropriate timeouts, concurrency controls, logout handling, and consistency.

**Never log full tokens/sessions or place them in URLs.** Logs may record error categories, routes, correlation IDs, and status codes, but never raw tokens.

## 4. Exact API of WebSessionServerCsrfTokenRepository

Package:

~~~text
org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository
~~~

Implementing class:

~~~java
// Abbreviated signatures for explanation; not a standalone Java file.
public class WebSessionServerCsrfTokenRepository
        implements ServerCsrfTokenRepository {

    public Mono<CsrfToken> generateToken(ServerWebExchange exchange);
    public Mono<Void> saveToken(ServerWebExchange exchange,
                                CsrfToken token);
    public Mono<CsrfToken> loadToken(ServerWebExchange exchange);

    public void setParameterName(String parameterName);
    public void setHeaderName(String headerName);
    public void setSessionAttributeName(String sessionAttributeName);
}
~~~

`saveToken` allows passing `null` as the token to **delete** the stored value per the contract; this is a Java API convention, not a value emitted by `Mono.just(null)`. In Reactor, never use `Mono.just(null)` because Publishers forbid null items.

### 4.1. generateToken(exchange)

- Creates a new `CsrfToken` object with an unpredictable value.
- Does not yet mean the token has been durably saved.
- Does not by itself "mark the request as protected".
- In Spring Security, the request handler/repository is coordinated via `CsrfWebFilter`, so controllers do not need to call generate on every GET.

### 4.2. saveToken(exchange, token)

- Saves the supplied token into the `WebSession` of `ServerWebExchange`.
- Per the contract, `saveToken(exchange, null)` means **deleting the token** from the repository.
- Returns `Mono<Void>`: the publisher completes once the reactive operation finishes.
- To actually persist, the framework must subscribe to the publisher as part of the pipeline. Calling the method and discarding the `Mono` does not guarantee any effect occurs.

### 4.3. loadToken(exchange)

- Loads the expected token from the `WebSession` bound to the exchange.
- If the session has no stored token yet, the result is **`Mono.empty()`** rather than a dummy token object.
- Returns the stored token; it is not responsible for reading the client-presented token header.
- Used to compare against the token read from the request by the request handler during CSRF processing.

### 4.4. setParameterName, setHeaderName, setSessionAttributeName

The three setters configure **three distinct parts**:

| API | Controls | Example |
| --- | --- | --- |
| `setParameterName("_csrf")` | Form field name sent by the client | `_csrf=<token>` |
| `setHeaderName("X-CSRF-TOKEN")` | HTTP request header name for the token | `X-CSRF-TOKEN: ...` |
| `setSessionAttributeName("DEMO_CSRF_TOKEN")` | Key inside `WebSession.attributes` holding expected token | Not a cookie name or HTTP header |

Example:

~~~java
// Illustrative snippet inside a @Bean method.
WebSessionServerCsrfTokenRepository repo =
        new WebSessionServerCsrfTokenRepository();

repo.setParameterName("_csrf");
repo.setHeaderName("X-CSRF-TOKEN");
repo.setSessionAttributeName("DEMO_CSRF_TOKEN");
~~~

If changing header/parameter names, synchronize the frontend, HTML forms, and tests; if changing the session attribute key while active users are deployed, new tokens may need to be issued because existing data resides under the old key.

**Do not rename the session attribute solely to "increase security".** Security depends on token entropy, restricting token distribution, proper verification, session protection, and other XSS/CSRF layers; hiding the attribute name is not a reliable security control.

## 5. Default CSRF protection in Spring Security WebFlux

In Spring Security WebFlux, **CSRF protection is enabled by default** in standard `SecurityWebFilterChain` configurations. The default repository is `WebSessionServerCsrfTokenRepository`.

Most applications **do not need** to configure the repository manually if keeping default behavior:

~~~java
@Bean
SecurityWebFilterChain securityFilterChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(ex -> ex.anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

This is a snippet that belongs inside a `@Configuration` class with Spring Security imports; if the app uses form login or Resource Server, authentication must be configured accordingly.

To make the repository explicit, you can write:

~~~java
.csrf(csrf -> csrf
        .csrfTokenRepository(new WebSessionServerCsrfTokenRepository()))
~~~

The snippet above belongs to `ServerHttpSecurity`, which is **reactive** configuration. **Do not** use Servlet's `HttpSessionCsrfTokenRepository` or Spring MVC's `HttpSecurity` to configure WebFlux; the two stacks have different request/filter contracts.

### 5.1. Which methods require CSRF?

Under Spring Security's default matcher:
- Typically **no token needed**: GET, HEAD, OPTIONS, TRACE.
- Typically **token needed**: POST, PUT, PATCH, DELETE, and other unsafe methods.

In practice, a route using POST for **reads** is not automatically exempt from CSRF; conversely, a GET that deletes data is a flawed design because the framework trusts GET as a safe method. Keep GET/HEAD free of side effects.

### 5.2. CSRF and authentication are two independent decisions

A POST request with valid username/password but missing a CSRF token can receive 403.
A POST request missing **both** credentials and a CSRF token can also receive 403 if `CsrfWebFilter` blocks before the authentication layer.
A GET missing credentials on a protected route normally receives 401 from the authentication entry point.
A POST with a valid token and valid credentials but lacking a role can still be rejected 403 by authorization.

Never deduce the error source from HTTP status 403 alone; inspect CSRF policy, roles, and the filter chain.

## 6. Deferred tokens, Reactor Mono, and subscription lifecycle

One reason Spring Security Reactive uses `Mono<CsrfToken>` is that tokens can be generated/loaded **on genuine demand**. When rendering an ordinary GET that needs no token and no code subscribes to the token, do not assume the repository immediately creates a `WebSession` and writes a token.

When a web page needs a form or an SPA needs to fetch a token:
1. A page/template/endpoint reads `Mono<CsrfToken>` from the exchange.
2. WebFlux subscribes to the publisher as part of response processing.
3. The repository either loads an existing token or generates/saves a new one.
4. The client receives the token presented via the request handler.

**Pitfall to avoid:** `ServerWebExchange.getAttribute(CsrfToken.class.getName())` returns **a `Mono`**, not an already-materialized `CsrfToken`. Never cast the attribute directly to `CsrfToken` or call `block()` in a controller.

Correct example:

~~~java
// Inside a @RestController, return Mono for WebFlux to subscribe.
@GetMapping("/csrf")
Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
    Mono<CsrfToken> token =
            exchange.getAttribute(CsrfToken.class.getName());

    if (token == null) {
        return Mono.error(new IllegalStateException(
                "CSRF token attribute unavailable"));
    }

    return token.map(value -> Map.of(
            "headerName", value.getHeaderName(),
            "token", value.getToken()));
}
~~~

This is a controller snippet requiring imports for `CsrfToken`, `ServerWebExchange`, `Mono`, `Map`, and annotations. The demo section below provides all files needed to run.

### 6.1. Why not subscribe manually?

Anti-pattern:

~~~java
// WRONG: subscription detached from the response lifecycle.
tokenMono.subscribe(token -> someSharedHolder.set(token.getToken()));
return Mono.just("done");
~~~

This snippet illustrates an architectural flaw; `someSharedHolder` is not a real class. Manual subscription detaches error handling/cancellation from the request and introduces global-state hazards. Compose `tokenMono.map(...)`/`flatMap(...)` and return the `Publisher`.

**Reactor Context** is different from **WebSession**: one belongs to the reactive subscription, while the other persists session data across requests. Never use Servlet `ThreadLocal` or a static variable to replace `ServerCsrfTokenRepository`.

## 7. Raw tokens in session vs. XOR-masked tokens displayed to clients

Spring Security 6.x normally uses `XorServerCsrfTokenRequestAttributeHandler` by default to reduce **BREACH** risk. This is an important distinction when learners notice the token from `/csrf` does not match the value stored inside the repository.

Distinguish clearly:

- **Expected/raw token:** the `CsrfToken` value the repository holds in `WebSession` for verification.
- **Presented token:** the potentially masked value the request handler emits into client HTML/forms/headers.
- **Resolved token:** the value the handler extracts from the request (potentially unmasked) to compare with the raw expected token.

Overview diagram:

~~~text
WebSessionServerCsrfTokenRepository
          |
          +--> raw expected token in WebSession
                      |
                      v
              XOR request handler
                      |
                      +--> token presented to client
                                 |
                                 v
                       Form/JavaScript sends it back
                                 |
                                 v
              Handler resolves/unmasks token
                                 |
                                 v
             Compare with expected token
~~~

When reading the token from `exchange.getAttribute(CsrfToken.class.getName())` via the default handler, the value returned to the client may be masked; **the client must send back the exact issued value**, never "unmask" it with custom logic, and never read the session attribute directly as a request token.

In many cases, the same expected token in the session can be presented as different masked strings across responses. Do not compare token strings returned to the browser across two GETs and conclude the session token changed just because they differ.

### 7.1. Why not disable XOR to simplify?

The non-masking `ServerCsrfTokenRequestAttributeHandler` exists. However, switching handlers solely to "make strings look clean" can weaken BREACH protection in certain scenarios. If an SPA reads raw cookie CSRF tokens via JS, design a compatible request handler **for the exact version and client model**; never blindly apply Servlet recipes to WebFlux APIs.

### 7.2. CSRF tokens vs. access tokens

A CSRF token does not allow a client to impersonate a user. A request with a valid CSRF token yet wrong credentials or insufficient authority still cannot execute the operation. Conversely, a valid Bearer token does not prove a browser cannot suffer CSRF if the browser auto-sends tokens/cookies by design.

## 8. Which cookies are created when storing CSRF tokens in WebSession?

In default WebFlux, the session ID is usually exchanged via a cookie named `SESSION` (configurable). When a token is saved and the session initialized, the response may contain:

~~~http
Set-Cookie: SESSION=<opaque-session-id>; Path=/; HttpOnly; SameSite=Lax
~~~

Exact `Set-Cookie` attributes/values vary with `CookieWebSessionIdResolver` configuration, Spring Boot settings, profiles, and HTTPS environments. The session ID cookie **does not contain the raw CSRF token** under this repository mechanism.

Several consequences:
- The session ID cookie still needs protection via `Secure` on production HTTPS, `HttpOnly`, and sensible SameSite/Domain/Path settings.
- WebFlux's default cookie **is not necessarily** Servlet's `JSESSIONID`.
- Losing the cookie causes the repository to miss the saved token.
- When `WebSession` expires or is invalidated, the expected token bound to it is gone.
- The browser resending the cookie does not automatically put the token into a header/form. Clients must send **both channels** properly.

### 8.1. Do not confuse with CookieServerCsrfTokenRepository

| Criterion | WebSessionServerCsrfTokenRepository | CookieServerCsrfTokenRepository |
| --- | --- | --- |
| Where expected token is stored | Server-side `WebSession` | Browser-side cookie |
| Needs session ID cookie to find expected token | Usually yes | No, not for this token repository alone |
| Typical use cases | Browser/form login, stateful sessions, apps with `WebSession` | Certain SPA/JavaScript clients needing cookie-token exchange |
| Associated cookie | Usually `SESSION`/resolver config | Usually `XSRF-TOKEN` |
| Typical client-sent header | `X-CSRF-TOKEN` | `X-XSRF-TOKEN` per cookie repo default |
| XSS security | Must protect token endpoint/views and JS | JS-readable token cookie (if enabled) carries trade-offs |
| Timeout | Tied to server session lifecycle | Tied to separate cookie/token policy |

`CookieServerCsrfTokenRepository.withHttpOnlyFalse()` may be needed for JS to read the cookie; **never** disable `HttpOnly` on the **`SESSION` cookie** because of that. Both repositories still require a non-auto-attached request header/form field for CSRF protection; letting the browser merely auto-send a token cookie without an actively submitted application value **does not provide sufficient synchronizer-token protection**.

### 8.2. Should stateless APIs use session tokens?

An API receiving only tokens actively sent by service-to-service/mobile clients, with zero browser ambient credentials, may evaluate whether CSRF is needed based on its threat model. If there is genuinely no risk of browsers auto-sending authentication info, there may be reason not to create a `WebSession` solely for CSRF.

However, **never disable CSRF just because an app says REST or HTTP Basic**. Browsers can remember Basic credentials and auto-send them; form login/session cookies require CSRF review even more. Choose a token repository based on your actual client model.

## 9. Runnable project: Java 17 + Spring Boot WebFlux + WebSession CSRF

We will build a demo featuring:
- HTTP Basic to test authentication per request without storing `SecurityContext` in the session.
- `WebSessionServerCsrfTokenRepository` explicitly configured.
- Session attribute name `DEMO_CSRF_TOKEN` for easy observation in this lesson.
- `GET /csrf` issuing a token and generating/saving the expected token on demand.
- `GET /session/csrf-stored` reporting **whether the current session holds a token**, without returning the raw token.
- `GET /api/note` reading state.
- `POST /api/note` mutating state, requiring a CSRF token.
- `POST /session/end` invalidating the current `WebSession`; while the client still has Basic credentials, the next request can still authenticate, yet the old token loses validity.

**Never use demo passwords in real products.** HTTP Basic is only safe over HTTPS/TLS; Base64 is not encryption. The `WebSession` repository illustrates CSRF and does not replace authentication/authorization.

### 9.1. File structure

~~~text
webflux-session-csrf/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── DemoApplication.java
    │   │   ├── SecurityConfig.java
    │   │   └── DemoController.java
    │   └── resources/
    │       └── application.yml
    └── test/java/demo/
        ├── WebSessionCsrfRepositoryTest.java
        └── WebFluxCsrfSecurityTest.java
~~~

### 9.2. settings.gradle

~~~groovy
rootProject.name = 'webflux-session-csrf'
~~~

### 9.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.7'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
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
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Use JDK 17+, a compatible Gradle version, or the project's Gradle Wrapper. The Spring Boot BOM supplies compatible versions for Spring Security 6.x/Framework/Reactor per the chosen Boot release. For production deployments, apply patches and stay on a supported branch; this version pins a concrete configuration.

### 9.4. application.yml

~~~yaml
server:
  port: 8080
  reactive:
    session:
      timeout: 10m
      cookie:
        name: SESSION
        path: /
        http-only: true
        same-site: lax
        secure: false

spring:
  application:
    name: webflux-session-csrf
~~~

`secure: false` is **only for localhost HTTP demos**. In production, require HTTPS, `secure: true`, CORS controls, and never allow session cookies over unprotected channels.

`server.reactive.session.timeout: 10m` sets `WebSession` inactivity timeout; it **does not guarantee tokens always live exactly 10 minutes from creation** or that browser cookies always expire after 10 minutes. If the session is invalidated or absent from the store, the old CSRF token becomes unusable.

### 9.5. DemoApplication.java

`src/main/java/demo/DemoApplication.java`:

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 9.6. SecurityConfig.java

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
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    static final String CSRF_ATTRIBUTE = "DEMO_CSRF_TOKEN";

    @Bean
    WebSessionServerCsrfTokenRepository csrfTokenRepository() {
        WebSessionServerCsrfTokenRepository repository =
                new WebSessionServerCsrfTokenRepository();
        repository.setSessionAttributeName(CSRF_ATTRIBUTE);
        repository.setHeaderName("X-CSRF-TOKEN");
        repository.setParameterName("_csrf");
        return repository;
    }

    @Bean
    SecurityWebFilterChain securityFilterChain(
            ServerHttpSecurity http,
            WebSessionServerCsrfTokenRepository csrfTokenRepository) {
        return http
                .authorizeExchange(ex -> ex
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .csrf(csrf -> csrf
                        .csrfTokenRepository(csrfTokenRepository))
                .build();
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails user = User.withUsername("learner")
                .password("{noop}localpass")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(user);
    }
}
~~~

**Explanation:**
1. `WebSessionServerCsrfTokenRepository` is a **separate bean** solely to highlight the repository, passed into `ServerHttpSecurity.csrf` without calling generate/save in controllers.
2. `setSessionAttributeName` sets the expected token's key inside `WebSession`; changing this key does not change the cookie name.
3. `anyExchange().authenticated()` requires Basic credentials for all demo endpoints.
4. `NoOpServerSecurityContextRepository` prevents persisting authentication in `WebSession` across requests, even though CSRF tokens are still stored there.
5. `csrfTokenRepository` is the storage strategy for the **expected CSRF token**, while reading masked tokens from headers/forms is managed by the default request handler.
6. `{noop}localpass` is a plaintext password strictly for local testing. Production uses an adaptive `PasswordEncoder` (BCrypt/Argon2 per policy), HTTPS, rate limiting, and secure user management.

**Never disable CSRF to fix a 403** when a client submits a POST missing a token. A 403 in that situation is the intended response.

### 9.7. DemoController.java

`src/main/java/demo/DemoController.java`:

~~~java
package demo;

import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.http.MediaType;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
public class DemoController {

    private final AtomicReference<String> note =
            new AtomicReference<>("initial");

    @GetMapping("/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token attribute is missing"));
        }

        return token.map(t -> Map.of(
                "headerName", t.getHeaderName(),
                "parameterName", t.getParameterName(),
                "token", t.getToken()));
    }

    @GetMapping("/session/csrf-stored")
    public Mono<Map<String, Boolean>> csrfStored(
            ServerWebExchange exchange) {
        return exchange.getSession()
                .map(session -> Map.of(
                        "stored", session.getAttribute(
                                SecurityConfig.CSRF_ATTRIBUTE) != null));
    }

    @GetMapping(path = "/api/note",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> getNote() {
        return Mono.fromSupplier(note::get);
    }

    @PostMapping(path = "/api/note",
            consumes = MediaType.TEXT_PLAIN_VALUE,
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> setNote(@RequestBody Mono<String> text) {
        return text.map(value -> {
            note.set(value);
            return "saved:" + value;
        });
    }

    @PostMapping(path = "/session/end",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public Mono<String> endSession(ServerWebExchange exchange) {
        return exchange.getSession()
                .flatMap(WebSession::invalidate)
                .thenReturn("session-ended");
    }
}
~~~

**Meaning:**
- `/csrf` returns the token emitted by Spring Security via the request handler, without directly reading the raw token attribute in `WebSession`.
- `/session/csrf-stored` returns only a boolean, never exposing the token value stored in the session. It still uses `exchange.getSession()` to inspect the current session.
- `GET /api/note` is read-only; `POST` is an unsafe operation checked by the CSRF filter before mutating `AtomicReference`.
- `/session/end` is a `POST`, **also requiring a CSRF token** before calling `WebSession.invalidate()`.
- All handlers return `Mono` and let WebFlux manage subscriptions; never `block()` or `subscribe()` manually.

`AtomicReference` is only an in-memory single-instance data model, not a persistence solution; real systems require services/databases and object-level authorization.

## 10. Hands-on test: tokens and cookies across multiple requests

In the directory containing `build.gradle`:

~~~bash
gradle bootRun
~~~

With Gradle Wrapper, run `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. By default the app listens on `http://localhost:8080`, for local use only.

### 10.1. First GET requests

~~~bash
# Missing credentials --> HTTP 401 on protected route.
curl -i http://localhost:8080/api/note

# With Basic credentials --> HTTP 200; body initial.
curl -i -u learner:localpass http://localhost:8080/api/note
~~~

GET needs no CSRF token under the default policy; 401 in the example is due to authentication, not CSRF.

### 10.2. Issue token and save WebSession cookie

The commands below use Bash and require `curl` and `jq`:

~~~bash
# Fetch token (possibly masked) and save session cookie.
curl -sS -u learner:localpass \
  -c csrf-cookies.txt \
  http://localhost:8080/csrf > csrf.json

# Inspect JSON has expected fields (NEVER log in production).
jq '{headerName, parameterName}' csrf.json

# Extract server-issued token value.
TOKEN="$(jq -r '.token' csrf.json)"
HEADER="$(jq -r '.headerName' csrf.json)"

# Check whether current session holds expected token.
curl -i -u learner:localpass \
  -b csrf-cookies.txt \
  http://localhost:8080/session/csrf-stored
~~~

Expected `GET /session/csrf-stored` output:

~~~json
{"stored":true}
~~~

**Never hardcode tokens** into files in source control. `csrf.json` and `csrf-cookies.txt` are for demo use only; in real environments, these are sensitive data requiring safe handling and exclusion from git, logs, and shared artifacts.

### 10.3. POST missing token is rejected

~~~bash
curl -i -u learner:localpass \
  -b csrf-cookies.txt \
  -H 'Content-Type: text/plain' \
  --data 'unsafe-change' \
  http://localhost:8080/api/note
~~~

Expected **HTTP 403 Forbidden**. Then GET to check state:

~~~bash
curl -i -u learner:localpass http://localhost:8080/api/note
~~~

Expected body remains `initial`. That proves the POST operation did not reach the controller when the token was missing.

### 10.4. POST with valid token and cookie

~~~bash
curl -i -u learner:localpass \
  -b csrf-cookies.txt \
  -H "$HEADER: $TOKEN" \
  -H 'Content-Type: text/plain' \
  --data 'saved-with-csrf' \
  http://localhost:8080/api/note

curl -i -u learner:localpass http://localhost:8080/api/note
~~~

If the token/session are still valid, expected results:

~~~text
POST /api/note -> HTTP 200; body: saved:saved-with-csrf
GET  /api/note -> HTTP 200; body: saved-with-csrf
~~~

**Two independent conditions:** token + cookie satisfy CSRF verification; `-u learner:localpass` satisfies request authentication. If Basic credentials are omitted while keeping cookie/token, the API must still enforce authentication rules.

### 10.5. Omitting cookie while still sending token

~~~bash
curl -i -u learner:localpass \
  -H "$HEADER: $TOKEN" \
  -H 'Content-Type: text/plain' \
  --data 'token-without-session' \
  http://localhost:8080/api/note
~~~

With `WebSession` repository and no matching session, expect **403**, because the server cannot locate the matching expected token. Do not interpret "invalid token" by grabbing the raw session attribute and comparing manually when using the default XOR handler.

### 10.6. Invalidate WebSession

Call the session-ending POST while the cookie/token are still valid:

~~~bash
curl -i -u learner:localpass \
  -b csrf-cookies.txt -c csrf-cookies.txt \
  -H "$HEADER: $TOKEN" \
  -X POST \
  http://localhost:8080/session/end
~~~

Expect `200` and body `session-ended`. Afterward, the old token no longer has a matching expected token in the session for new POSTs; to continue mutating data, the client must obtain a new CSRF token via `GET /csrf` and keep the new session cookie.

Notably, after `invalidate()`, a GET can still return 200 if HTTP Basic credentials continue to be sent; **not** because the old session is still active, but because Basic re-authenticates on the new request. A system using form-login/session authentication exhibits different logout behavior.

### 10.7. HTTP summary matrix

| Request | Auth | Cookie/session token | CSRF header | Expected result |
| --- | --- | --- | --- | --- |
| GET `/api/note` | None | None | None | **401** |
| GET `/api/note` | Valid Basic | None | None | **200** |
| GET `/csrf` | Valid Basic | Browser receives session | None | **200** + token |
| GET `/session/csrf-stored` | Valid Basic | Same session | None | **200** + stored=true |
| POST `/api/note` | Valid Basic | Same session | Missing | **403** |
| POST `/api/note` | Valid Basic | Same session | Valid | **200** |
| POST `/api/note` | Valid Basic | Missing/wrong session | Token from previous session | **403** |
| POST `/session/end` | Valid Basic | Same session | Valid | **200**, invalidate |

Error bodies may vary by version; statuses are based on the demo configuration. Do not conclude a POST missing both auth and token definitely returns 401, as the CSRF filter can return 403 first.

## 11. Unit testing the repository directly with Reactor StepVerifier

The HTTP tests in the next section show Spring Security using CSRF tokens. You should also verify the repository contract directly:
- No token saved -> `loadToken` emits nothing.
- `generateToken` -> non-blank token value.
- `saveToken` then `loadToken` on the same exchange -> tokens match.
- `saveToken(exchange, null)` -> deletes stored token.

`src/test/java/demo/WebSessionCsrfRepositoryTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;

class WebSessionCsrfRepositoryTest {

    private WebSessionServerCsrfTokenRepository repository() {
        WebSessionServerCsrfTokenRepository repository =
                new WebSessionServerCsrfTokenRepository();
        repository.setSessionAttributeName("TEST_CSRF");
        return repository;
    }

    @Test
    void newSessionHasNoStoredToken() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/csrf"));
        StepVerifier.create(repository().loadToken(exchange))
                .verifyComplete();
    }

    @Test
    void generateSaveAndLoadRoundTrip() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/csrf"));
        var repository = repository();

        StepVerifier.create(
                repository.generateToken(exchange)
                        .flatMap(token -> repository
                                .saveToken(exchange, token)
                                .then(repository.loadToken(exchange))
                                .map(loaded -> {
                                    assertFalse(loaded.getToken().isBlank());
                                    assertEquals(token.getToken(),
                                            loaded.getToken());
                                    return loaded;
                                })))
                .expectNextCount(1)
                .verifyComplete();
    }

    @Test
    void saveNullRemovesExpectedToken() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/csrf"));
        var repository = repository();

        StepVerifier.create(
                repository.generateToken(exchange)
                        .flatMap(token -> repository
                                .saveToken(exchange, token)
                                .then(repository.saveToken(exchange, null))
                                .then(repository.loadToken(exchange))))
                .verifyComplete();
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expected:** all three tests PASS if the project is created as described. This expectation is based on the API; it is not a report that Gradle actually ran. `verifyComplete()` on `Mono<CsrfToken>` means no `onNext` item was emitted, matching when no expected token is found.

**Test boundary:** instantiating the repository directly does not prove a `SecurityWebFilterChain` is wired with that bean. The integration tests below are needed to confirm real requests are checked by the CSRF filter.

## 12. WebFlux integration tests with WebTestClient

Spring Security Test provides `SecurityMockServerConfigurers.csrf()` to attach a valid CSRF token in WebFlux tests; never use this helper to bypass CSRF in production.

`src/test/java/demo/WebFluxCsrfSecurityTest.java`:

~~~java
package demo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class WebFluxCsrfSecurityTest {

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
    void anonymousGetNeedsAuthentication() {
        client.get().uri("/api/note")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void basicAuthenticatedGetNeedsNoCsrf() {
        client.get().uri("/api/note")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void postWithoutCsrfIsForbiddenEvenWithBasic() {
        client.post().uri("/api/note")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("not-allowed")
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void postWithTestCsrfAndBasicIsAllowed() {
        client.mutateWith(csrf())
                .post().uri("/api/note")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("allowed")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("saved:allowed");
    }

    @Test
    void postSessionEndWithoutCsrfIsForbidden() {
        client.post().uri("/session/end")
                .headers(h -> h.setBasicAuth("learner", "localpass"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

**Expected:** 5 integration tests PASS. Allowing POST via `csrf()` in tests does not weaken CSRF protection in the real application. Tests use a mock exchange to verify the security chain, while the `curl` commands in Section 10 verify the actual token + `WebSession` cookie lifecycle.

If a test has a valid token yet still returns 403, verify `springSecurity()` was applied, which repo/CSRF handler is configured, and that test helpers match your dependency version; never disable CSRF just to turn tests green.

## 13. When tokens disappear: session timeout, logout, and token rotation

### 13.1. WebSession expiration

The expected token stored in `WebSession` follows the session lifecycle. When the idle timeout is exceeded:
- The browser may still send the old session ID cookie.
- The server no longer holds the expected token of the old session.
- Unsafe requests with the old token are rejected, typically 403.
- The client must fetch a new token in a new session and send it with the matching cookie.

In Boot Reactive, `server.reactive.session.timeout` usually sets an **idle timeout**, not an absolute deadline. Browser cookie expiration (`Max-Age`) and server session TTL are **two separate clocks**.

### 13.2. Logout

With session login, logout requires proper invalidation of `SecurityContext`/session and the CSRF token. In the demo, `POST /session/end` calls `WebSession.invalidate()` to demonstrate token invalidation, though **it does not make the browser forget HTTP Basic credentials**.

In real applications:
- Perform logout via an appropriate HTTP method, keeping CSRF for state-changing operations with browser clients.
- Invalidate the server-side session and delete cookies with exact Name/Domain/Path if policy requires.
- If remember-me/OAuth2 refresh tokens exist, handle revocation and the identity provider accordingly.
- Never merely delete the client cookie while leaving the old session ID valid in a shared store.

### 13.3. Login/logout invalidates old tokens

Replacing `SecurityContext`/session or CSRF logout handlers can delete/rotate tokens. This is intentional to curb reuse in invalid contexts.

An SPA continuing to POST after login/logout may need to:
1. Re-authenticate (if needed).
2. Call the endpoint to fetch a new CSRF token in the new session context.
3. Retain the new session cookie per browser policy.
4. Attach the new token to unsafe requests.

Never store a CSRF token in `localStorage` "forever" and assume it stays valid across session changes. Never infinitely retry 403 POSTs with an old token.

### 13.4. Should a fresh token be forced on every request?

Not necessarily. The repository keeps the expected token in the session, while the XOR request handler can generate a fresh **masked presentation** each time a token is supplied. That differs from generating/saving a new raw token on every GET.

If the app has a custom rotation policy, design server state, session stores, concurrent tabs, logout, and client synchronization carefully. Arbitrarily rotating raw tokens on every GET can cause other open tabs with forms to fail with 403.

## 14. Troubleshooting: is POST 403 really caused by the repository?

When hitting 403, do not jump to "WebSessionServerCsrfTokenRepository is broken". Check in order:

1. **Method:** is the request POST/PUT/PATCH/DELETE or GET? Does the CSRF matcher apply?
2. **Security chain:** are there multiple `SecurityWebFilterChain` beans? Which chain matches the route?
3. **Authentication:** with Basic, test a protected GET with the same credentials. GET 401 means authentication failed.
4. **Token endpoint:** does `GET /csrf` return a token, or is it rejected by an entry point?
5. **Cookie jar:** does the POST send the exact `SESSION` cookie received during `GET /csrf`?
6. **Token header:** are `headerName` and `token` sent exactly as returned in the response?
7. **XOR handler:** is the client trying to decode/mask/unmask the token with custom logic? If so, stop and send the issued value as-is.
8. **SameSite/CORS:** is the browser blocking cookies cross-site per policy? Is the origin allowed to read the token response?
9. **Session expiry:** did timeout elapse, did session invalidate/logout occur, or was the ID rotated?
10. **Multiple instances:** is a load balancer routing requests to another instance without shared sessions?
11. **Spring Session:** is the Redis store healthy, and are TTL/WebSession configurations compatible?
12. **Proxy:** is a reverse proxy altering scheme, cookie Path/Domain, stripping headers, or rewriting URLs?
13. **Authorization:** if a valid token is present yet 403 persists, did role/scope/owner checks deny it?
14. **CSRF disabled?** If POST without a token still returns 200, check whether the chain's policy/matcher disabled CSRF or the route matched a different chain.
15. **Never log tokens:** log correlation ID, method, route, response status, and error category; never print raw tokens, cookies, or Authorization headers.

### 14.1. Distinguishing symptoms

| Symptom | Likely cause | How to confirm |
| --- | --- | --- |
| Protected GET API returns 401 | Missing/wrong credentials | Check authentication entry point |
| POST missing token returns 403 | CSRF protection is working | Try equivalent POST with valid token |
| POST with token yet missing SESSION returns 403 | Cannot locate session's expected token | Send matching cookie jar |
| GET /csrf returns token yet session state is false | Token not saved yet, deferred token unsubscribed, or wrong session | Inspect pipeline/repository and request cookies |
| Session state true yet POST 403 | Wrong header, masked/raw mismatch, stale token, or lacking permission | Inspect issued token/handler and authorization |
| Second GET /csrf returns different string while session remains valid | Likely XOR masking | Never compare masked strings to assume raw token changed |
| Scaling to 2 instances causes intermittent 403 on POST | Unshared session store or proxy misconfig | Test sticky routing/Redis sessions |
| After logout, old token returns 403 | Old token/session was invalidated | Fetch new token and new session |
| POST has token and cookie yet server returns 404 | Security likely passed; no matching handler | Check route/method |
| POST has valid token, cookie, and Basic yet returns 403 | Likely authorization | Check authorities and error-emitting filter |

### 14.2. Never disable CSRF to fix integration errors

Anti-pattern:

~~~java
// Do not use as a "fix" for browsers with cookies/Basic credentials.
.csrf(ServerHttpSecurity.CsrfSpec::disable)
~~~

Consider disabling only after a threat model proves requests do not rely on browser-originated ambient authentication. Whenever clients are web browsers with login cookies or cached Basic authentication, keep an appropriate anti-CSRF mechanism.

## 15. WebSession repository and alternatives

### 15.1. When to keep WebSessionServerCsrfTokenRepository

Appropriate when:
- The application already uses `WebSession` for browser/form login.
- CSRF tokens should be bound to a server-side session lifecycle.
- Session timeout/invalidation and shared session stores can be managed.
- The frontend has a secure channel to receive and send tokens in forms/headers.
- JavaScript does not need to read a token cookie directly.

**Pros:** the expected token does not need to live in plaintext in a browser CSRF cookie; lifecycle is tightly bound to `WebSession`. **Trade-offs:** must manage session state, cookie IDs, timeouts, Redis/scaling, and clients failing to resend cookies.

### 15.2. When to consider CookieServerCsrfTokenRepository

An SPA may find it more convenient if a token cookie is read by JavaScript and placed in a header. However:
- Using `withHttpOnlyFalse()` makes the CSRF token cookie readable by JS: XSS and exposure must be evaluated.
- Browsers can auto-send cookies, so **sending the token in a separate header** remains the critical anti-CSRF step.
- Spring Security 6.x's default XOR handler and JS reading raw tokens from cookies may require an appropriate custom request handler/flow.
- Not necessarily suitable for every login/SSO/embedded app.

Never swap the `WebSession` repository for cookies solely over a single 403. Diagnose cookie jar/timeout/header/matcher issues first.

### 15.3. When an API truly has no CSRF risk

For service-to-service APIs using Bearer tokens where browsers never auto-attach ambient credentials, you can evaluate disabling CSRF for that namespace without creating server sessions solely for CSRF tokens. Yet this choice must examine the whole system: API gateway, cookie authentication, SPAs, browser Basic, OAuth2 login, CORS, and shared routes.

## 16. Production security considerations

**SESSION cookie:**
- `Secure=true` on production HTTPS.
- `HttpOnly=true` for session ID cookies.
- `SameSite=Lax/Strict/None` matching real navigation/browsers and the CSRF threat model.
- Restrict `Domain` and `Path`; prefer host-only cookies when sharing is unnecessary.
- Never log session IDs; never place them in URLs.
- Protect against session fixation/rotate at privilege-escalation boundaries; test logout and expiry.

**CSRF token:**
- High cryptographic entropy, unpredictable, never carelessly reused across sessions.
- Never expose tokens to unintended origins via CORS/proxies.
- Tokens must travel in properly named headers/form fields, not solely cookies.
- Refresh/rotate tokens when session/auth lifecycle changes.
- Never log tokens, store them in analytics, or place them in shared files.
- Test Spring Security 6.x masked tokens and frontend compatibility.

**Application and infrastructure:**
- Prevent XSS with output encoding, CSP, and template/JS dependency controls. XSS in a legitimate origin can abuse CSRF tokens.
- Enforce proper resource-ownership authorization; a CSRF token does not let users view others' data.
- Restrict CORS origins and methods/headers/credentials.
- Add rate limiting and protect authentication mechanisms.
- Use a shared session store with clear TTLs for multi-instance deployments where needed.
- Avoid forcing tokens into multipart request bodies before size/resource limits are checked; prefer headers in JS apps.

### 16.1. A note on session fixation

If login succeeds after an anonymous session, the session ID may need rotation to mitigate session fixation. Authentication elevation and session fixation protection belong to the security/session lifecycle and **must not** be replaced by arbitrarily generating a new CSRF token.

### 16.2. Never use CSRF tokens to authenticate users

An application must verify identity and privileges via dedicated authentication/authorization. If someone holds only a valid CSRF token without credentials, they gain zero permissions. A CSRF token is an additional guard when requests require protection, not a replacement for account management.

## 17. Common mistakes

| Mistake | Why it is wrong | Correct approach |
| --- | --- | --- |
| Confusing expected token with `SESSION` cookie | The cookie holds the session ID, not the token | Send both session cookie and token in header/form |
| Sending only token, omitting cookie | Repository cannot tell which session holds expected token | Use the same session/cookie jar |
| Sending only `SESSION` cookie, omitting token | Browser auto-sends cookie, offering no CSRF protection | Client actively attaches token |
| Reading raw token from session and comparing with masked response token | XOR handler may transform presented tokens | Use default request handler; do not unmask manually |
| Calling `block()` in a WebFlux controller | Can block the event loop | Return `Mono`/compose publishers |
| Calling `saveToken` without subscribing | Reactive operation may never execute | Compose into framework pipeline |
| Assuming every GET issues a CSRF token | CSRF tokens can be deferred | Request/subscribe to token when needed |
| Thinking `NoOpServerSecurityContextRepository` disables CSRF sessions | They are two separate repositories | Inspect the CSRF token repository independently |
| Deleting `SESSION` cookie without invalidating server session | Stolen session IDs remain usable | Invalidate/revoke on the server side |
| Token expires with `WebSession` yet frontend doesn't refresh | POSTs repeatedly fail with 403 | Obtain a new token and session |
| Using in-memory session store across multiple instances | Requests hitting another instance lose the token | Shared store/controlled sticky routing |
| Allowing every CORS origin to read `/csrf` | Tokens can be leaked | Restrict trusted origins and credentials |
| Disabling CSRF on browser Basic/form login | Increases CSRF exposure | Keep CSRF whenever browsers hold ambient credentials |
| Using `HttpSessionCsrfTokenRepository` in WebFlux | That is a Servlet API | Use `WebSessionServerCsrfTokenRepository` |
| Logging raw tokens and cookies | Leaks secrets | Log only safe statuses and correlation IDs |
| Treating CSRF token as `ROLE_ADMIN` authority | Wrong security layer | Authorization checks roles/ownership separately |
| Using POST for mutations without negative tests | Easy to miss gaps in the security chain | Test with/without token, with/without auth |
| Mutating state in GET | Default CSRF skips GET | Keep GET read-only |
| Copying Servlet SPA cookie configs to WebFlux | Handler APIs differ | Read Reactive docs and test your version |

## 18. QA checklist for a new feature

### Configuration
- [ ] Confirmed whether the app runs WebFlux or Servlet; selected the matching token repository.
- [ ] `SecurityWebFilterChain` actually covers all routes requiring protection.
- [ ] CSRF is enabled for unsafe methods per threat model.
- [ ] `WebSessionServerCsrfTokenRepository` is used by default or configured explicitly.
- [ ] If custom header/parameter/session attribute names are used, frontend and tests are updated.
- [ ] SecurityContext repository is independent; never infer session auth from a CSRF token.
- [ ] No sensitive POST route is unintentionally `permitAll`.

### Browser/front-end
- [ ] View/endpoint emits token from `Mono<CsrfToken>` provided by the request handler.
- [ ] Token is never exposed via CORS, URLs, referrers, logs, or analytics.
- [ ] Browser sends the matching `SESSION` cookie on POST.
- [ ] Token is placed in a form field/header, not solely in a cookie.
- [ ] Frontend handles expired tokens after session timeout/logout.
- [ ] SPA accounts for token masking when using Spring Security 6.x.
- [ ] CSRF tokens and authentication credentials are never conflated.

### Server/operational
- [ ] `WebSession` timeout, cookie `Max-Age`, and Redis TTL are verified as separate policies.
- [ ] After logout/invalidation, old tokens no longer work.
- [ ] Shared session store or proper routing when running multiple instances.
- [ ] GET/HEAD requests produce zero side effects.
- [ ] Session cookies are protected with HTTPS and appropriate Secure/HttpOnly/SameSite flags.
- [ ] Metrics distinguish auth 401, CSRF 403, authorization 403, and 4xx business errors.
- [ ] No tokens/session IDs logged in tracing.

### Tests
- [ ] Protected GET without credentials returns 401.
- [ ] GET with valid credentials reads state.
- [ ] POST with valid credentials but missing CSRF token returns 403.
- [ ] POST with valid token but wrong session is rejected.
- [ ] POST with matching session + token + authentication succeeds.
- [ ] `saveToken` followed by `loadToken` round-trips accurately.
- [ ] `saveToken(exchange, null)` deletes the token.
- [ ] After session invalidation, old tokens are no longer valid.
- [ ] Real browser tests performed when CORS/SameSite/cross-site flows exist.
- [ ] Never infer the exact rejecting layer from a single 403 status without verification.

## 19. Self-check questions and suggested answers

**1. What does `WebSessionServerCsrfTokenRepository` store and where?**

> Stores the **expected `CsrfToken`** as an attribute inside `WebSession`, so the server can compare it against tokens sent by clients.

**2. Why must the client send both the `SESSION` cookie and `X-CSRF-TOKEN`?**

> The cookie lets the server locate the right session holding the expected token; the header/form proves the request carries a token issued by the legitimate app, not just an auto-attached cookie.

**3. Does `generateToken` automatically save into `WebSession`?**

> Do not assume so; there is a separate `saveToken` step coordinated by the filter/repository flow.

**4. What does `loadToken` return when the session has no token yet?**

> `Mono.empty()`: emits no token object.

**5. What does `saveToken(exchange, null)` mean?**

> Per the repository contract, deletes the currently stored expected token.

**6. Why does the masked token in HTML not necessarily equal the raw token in `WebSession`?**

> Spring Security 6.x uses an XOR request handler by default to mask tokens on output, mitigating BREACH risk.

**7. Why might a GET not create a `WebSession` even with CSRF enabled?**

> Tokens can be deferred/lazy; if the request needs no token and nothing subscribes to `Mono<CsrfToken>`, neither token nor session needs to be created.

**8. A browser keeps the token in a header but loses the `SESSION` cookie; will POST succeed?**

> Usually not, because the repository cannot find the old session's expected token to compare against.

**9. Does `NoOpServerSecurityContextRepository` prevent the CSRF repository from saving tokens?**

> No. Authentication persistence and CSRF token repositories are separate mechanisms.

**10. Why does a GET with Basic credentials still return 200 after `WebSession.invalidate()`?**

> Basic credentials can be resent and re-authenticated on the new request; invalidating the session does not clear client-side credentials.

**11. For an SPA, when should `CookieServerCsrfTokenRepository` be considered?**

> When the frontend needs cookie-based token integration under an appropriate threat model, while properly handling XOR/token handlers, `HttpOnly`, and XSS for your version.

**12. Can a CSRF token replace `hasRole("ADMIN")`?**

> No. CSRF protects requests from forgery, whereas authorization grants permissions to users/resources.

## 20. Summary

`WebSessionServerCsrfTokenRepository` is Spring Security Reactive's way of **storing expected CSRF tokens in `WebSession`**. It defines a Reactive `Mono` contract for generating/saving/loading tokens and is used by `CsrfWebFilter` and request handlers to validate requests requiring CSRF protection.

For a POST to pass CSRF properly, clients typically need to:
1. Hold a session cookie enabling the server to locate `WebSession`.
2. Obtain a token through a valid view/endpoint from the request handler.
3. Send the token in a header/form parameter not auto-added by the browser.
4. Still satisfy authentication and authorization independently.

When Spring Security 6.x uses the XOR handler, **the masked token presented to clients can differ from the raw expected token stored in the session**; never alter the token manually. Session timeout/logout, cookie scope, shared session stores, HTTPS, and CSRF/CORS/XSS must all be verified together.

### Official References

- Spring Security Reference — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- Spring Security Javadoc — `WebSessionServerCsrfTokenRepository`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html
- Spring Security Javadoc — `ServerCsrfTokenRepository`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRepository.html
- Spring Security Javadoc — `XorServerCsrfTokenRequestAttributeHandler`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html
- Spring Security Reference — Testing WebFlux with CSRF: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Security Reference — Reactive Configuration: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Framework Javadoc — `WebSession`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/WebSession.html
- Spring Session Reference — WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- OWASP CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html