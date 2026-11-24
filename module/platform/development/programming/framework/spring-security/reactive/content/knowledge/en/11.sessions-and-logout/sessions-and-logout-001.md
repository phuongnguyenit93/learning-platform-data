# WebSession, Session Cookies, and Differences from HttpSession

> **Context:** Spring Boot 3.3.x, Spring Framework 6.1.x, Spring Security 6.x, Java 17+, HTTP applications using **Spring WebFlux**. The focus is on the session lifecycle, the cookie holding the session ID, differences from `jakarta.servlet.http.HttpSession`, and how Spring Security stores/reads `SecurityContext` when using sessions. The versions in the examples are for learning purposes only; production deployments must choose a Spring Boot/Spring Framework version that has received security patches and is still supported.

## 1. What is a session, and what does a session cookie hold?

A **server-side session** is a set of stateful data that the server associates with requests from the same client. Examples include a temporary shopping cart, the current step in a wizard, or a security context after form login. Typically, the browser holds a **session ID** in a cookie and sends that ID back to the server:

```text
Request 1: Browser                     WebFlux server
           POST /lab/cart  ------------------>
                             create WebSession; save cart
           <------------------  Set-Cookie: SESSION=<opaque-id>; ...
           browser stores cookie

Request 2: Browser
           GET /lab/state
           Cookie: SESSION=<opaque-id>  ----->
                             look up WebSession by ID
           <------------------  JSON containing saved cart
```

- The cookie usually contains a **reference ID**, **not the entire Java data in the session**. Session data resides on the server side or in a configured store.
- A session ID is a **bearer-like secret**: anyone holding a valid ID can impersonate the session if the system lacks other layers of protection. Do not log it, attach it to URLs, send it to third parties, or include it in JSON responses for debugging.
- Having a cookie does not imply being logged in. An **unauthenticated** guest can still have a `WebSession` holding a shopping cart; a user authenticated via Basic/JWT does not necessarily use a session cookie.
- The lifetime of the cookie in the browser and the session expiration time on the server side can **differ**. A cookie that still exists while the session has expired does not bring old data back to life.

In Spring WebFlux, the Java type used for sessions is:

```java
import org.springframework.web.server.WebSession;
```

Whereas in Spring MVC/Servlet:

```java
import jakarta.servlet.http.HttpSession;
```

Both APIs serve the same cross-request state requirement, but **cannot be used interchangeably** in controllers, filters, or repositories across the two web stacks.

## 2. How does WebSession work?

`org.springframework.web.server.WebSession` is Spring Framework's interface for sessions in WebFlux. It is a component of **Spring WebFlux**, not exclusive to Spring Security. Key APIs:

| API | Meaning |
|---|---|
| `getId()` | Reads the current session ID; do not output this ID to logs or JSON outside protected administrative needs |
| `getAttributes()` | `Map<String,Object>` containing session data |
| `getAttribute("key")` | Reads an attribute by name, may return `null` |
| `getRequiredAttribute("key")` | Reads a required attribute; throws an error if absent |
| `start()` | Explicitly marks the session as started; `void` |
| `isStarted()` | Indicates whether the session was started explicitly or implicitly by adding an attribute |
| `save()` | Returns `Mono<Void>`, saves the session; the framework usually calls this automatically when the response is about to commit |
| `changeSessionId()` | Returns `Mono<Void>`, generates a new ID and updates the backing store |
| `invalidate()` | Returns `Mono<Void>`, invalidates the session and deletes stored state |
| `getMaxIdleTime()` / `setMaxIdleTime(Duration)` | Gets/sets the maximum idle time of the session |
| `getCreationTime()` / `getLastAccessTime()` / `isExpired()` | Lifecycle and expiration information |

### 2.1 Obtaining a session does not necessarily start a session

In WebFlux, a controller parameter `WebSession session` **does not automatically force creating a persisted session**. When calling `ServerWebExchange.getSession()`, you receive `Mono<WebSession>`; a request without a valid session can be given a `WebSession` object that is **not yet started**.

```java
@GetMapping("/peek")
Mono<Boolean> peek(WebSession session) {
    return Mono.just(session.isStarted());
}
```

This method snippet is a standalone example without full class/imports. When only reading `isStarted()` or `getAttribute(...)`, a new `Set-Cookie` is not required. However, **other filters** (for example authentication, CSRF, or application filters) may concurrently modify the session; do not treat "GET will definitely never emit a cookie" as a system contract.

A session starts when:

1. Calling `session.start()` explicitly.
2. Adding an attribute to `session.getAttributes()`, e.g., `put("cart", ...)`; the session is started implicitly.

Afterward, `WebSessionManager`/`WebSessionStore` handles persisting the session during the request processing lifecycle. You typically **do not need to call `save()` manually in a controller**, because saving happens before the response is committed. If the response has started writing too early or a custom flow does not match the lifecycle, review the specific API rather than inserting `block()`.

### 2.2 Truly asynchronous APIs must be composed into the pipeline

`changeSessionId()` and `invalidate()` return `Mono<Void>`. Do not write:

```java
session.invalidate(); // Only creates a Publisher, not guaranteed to execute
return Mono.just("logged out");
```

In Reactor, a publisher needs a subscription. The handler must **return a publisher with the operation chained into the flow**:

```java
return session.invalidate()
    .thenReturn("session invalidated");
```

This is a code snippet inside a method returning `Mono<String>`. Spring WebFlux subscribes to the publisher returned by the handler. **Do not call `subscribe()` manually and do not call `block()`** in a WebFlux controller to wait for session invalidation.

### 2.3 Sessions and requests have different lifecycles

- `ServerWebExchange.getAttributes()` holds attributes for **a single request/exchange**, not preserved across the next request.
- `WebSession.getAttributes()` holds attributes for **the session**, surviving across multiple requests when there is a session ID and an appropriate store.
- `ReactiveSecurityContextHolder` provides `SecurityContext` for the **current Reactor chain**. Persisting it across multiple requests is the responsibility of `ServerSecurityContextRepository`, not something that happens automatically just because Reactor Context is present.
- `@SessionAttributes` on a WebFlux controller relates to model attributes and `SessionStatus`; it is not the same as interacting directly with `WebSession.getAttributes()`. Clearing model attributes with `SessionStatus.setComplete()` **does not automatically substitute for invalidating the entire session**.

## 3. CookieWebSessionIdResolver and WebSessionManager

Related classes in Spring WebFlux:

```text
HTTP request
    |
    v
DefaultWebSessionManager
    |
    +--> WebSessionIdResolver
    |       +--> CookieWebSessionIdResolver
    |               reads Cookie: SESSION=<id>
    |
    +--> WebSessionStore
    |       +--> InMemoryWebSessionStore (basic default)
    |       +--> integrated Spring Session/Redis/... store (if configured)
    |
    v
WebSession
    |
    v
handler / WebFilter / Spring Security
    |
    v
save session when response is committed
    |
    +--> Set-Cookie: SESSION=<id> when needed
```

`CookieWebSessionIdResolver` defaults to using a cookie named **`SESSION`**. This is a **WebFlux default**, not a mandatory standard; applications can change the name via the resolver or Spring Boot configuration. In many Servlet applications, the container cookie is typically named **`JSESSIONID`**. Therefore, using `JSESSIONID` to assume whether any WebFlux application has a session is wrong.

`WebSessionIdResolver` is only responsible for reading, writing, or expiring the **client-side session ID**. `WebSessionStore` is responsible for storing/looking up server-side data. Changing the cookie name does not mean moving session data to Redis.

### 3.1 HTTP Sample: Set-Cookie and Cookie

Illustrative header example (ID values have been replaced with placeholders):

```http
HTTP/1.1 200 OK
Set-Cookie: SESSION=<opaque-id>; Path=/; HttpOnly; SameSite=Lax

GET /lab/state HTTP/1.1
Host: localhost:8080
Cookie: SESSION=<opaque-id>
```

Important attributes:

| Attribute | Role | What it cannot do |
|---|---|---|
| `HttpOnly` | Restricts JavaScript from accessing the cookie via `document.cookie` | Does not by itself prevent CSRF or all types of XSS/session hijacking |
| `Secure` | Only sends the cookie over secure connections per browser rules | Does not replace proper TLS termination and proxy configuration |
| `SameSite=Lax/Strict/None` | Restricts certain cookie-sending patterns in cross-site contexts | Does not replace CSRF tokens/Origin checks for all applications |
| `Path` | Limits the URL path for which the browser sends the cookie | Does not create a server-side security boundary between endpoints |
| `Domain` | Limits the domain/subdomain scope of the cookie | An overly broad Domain can increase exposure or session fixation risks via subdomains |
| `Max-Age` | How long the browser keeps the cookie | Does not guarantee the backend session has not expired or been revoked |

If using `SameSite=None` per modern browsers, `Secure` is normally required. For real HTTPS deployments, enable `Secure`; when running `http://localhost` for lab exercises, headers will differ. Do not copy the session cookie into localStorage just for debugging.

### 3.2 Customizing cookies with Spring Boot 3.3

For reactive applications using Spring Boot 3.3, common properties:

**src/main/resources/application.yml**

```yaml
server:
  reactive:
    session:
      timeout: 20m
      cookie:
        name: SESSION
        http-only: true
        same-site: lax
```

`server.reactive.session.timeout` is the idle timeout of `WebSession`; cookie settings use the `server.reactive.session.cookie.*` namespace. **Do not use `server.servlet.session.*` expecting to change WebFlux configuration.**

In production using HTTPS, consider adding:

```yaml
server:
  reactive:
    session:
      cookie:
        secure: true
```

This is an **additional configuration**, not necessarily suitable for localhost HTTP. If TLS terminates at a reverse proxy/load balancer, you must verify forwarding headers, scheme, and where cookies are issued to ensure `Secure`/Domain/Path match the real domain.

### 3.3 Customizing directly with WebSessionIdResolver

When you need explicit control over how cookies are created (for example, a different name), you can provide a bean:

```java
@Bean
WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver =
        new CookieWebSessionIdResolver();
    resolver.setCookieName("APPSESSION");
    resolver.addCookieInitializer(builder ->
        builder.path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax"));
    return resolver;
}
```

This is an **illustrative configuration snippet** that must be placed in a `@Configuration` class with imports for `@Bean`, `WebSessionIdResolver`, and `CookieWebSessionIdResolver`. When using this bean, the cookie name is no longer `SESSION` and `secure(true)` is only appropriate when clients connect over HTTPS. Do not simultaneously declare custom mechanisms without understanding precedence and assume every Boot property still overrides your bean.

## 4. Where does WebSession differ from HttpSession?

| Aspect | WebFlux: `WebSession` | Servlet/MVC: `HttpSession` |
|---|---|---|
| Package | `org.springframework.web.server.WebSession` | `jakarta.servlet.http.HttpSession` |
| Environment | Reactor/WebFlux; can run on Netty | Servlet API and containers such as Tomcat/Jetty |
| Obtaining session from request | `ServerWebExchange.getSession()` returns `Mono<WebSession>`; controllers can also inject `WebSession` | `HttpServletRequest.getSession()` returns `HttpSession` synchronously |
| On first session access | Obtaining the object does not force start/persist; adding an attribute or calling `start()` starts it | `getSession()` typically creates one if absent; `getSession(false)` does not create |
| Attributes | `getAttributes().put(...)`, `getAttribute(...)` | `setAttribute(...)`, `getAttribute(...)` |
| Save/change ID/invalidate | `save()`, `changeSessionId()`, `invalidate()` return `Mono<Void>` (except `start`) | `invalidate()` returns `void`; changing ID typically via `HttpServletRequest.changeSessionId()` |
| Typical default cookie | `SESSION` from `CookieWebSessionIdResolver` | `JSESSIONID` in many Servlet containers |
| Store | `WebSessionStore`; defaults to `InMemoryWebSessionStore`, can integrate Spring Session | Sessions managed by Servlet container or Spring Session/`SessionRepository` |
| Security context | `ReactiveSecurityContextHolder` and `ServerSecurityContextRepository` | `SecurityContextHolder` and Servlet `SecurityContextRepository` |
| Transaction/thread | Does not imply a request is pinned to a single thread for its entire lifecycle | Traditional Servlet code often relies on a thread-per-request model |

**Traditional Servlet example** (not used in WebFlux):

```java
// MVC/Servlet snippet, not part of the WebFlux demo:
@GetMapping("/cart")
String cart(HttpServletRequest request) {
    HttpSession session = request.getSession();
    session.setAttribute("cart", "book");
    return (String) session.getAttribute("cart");
}
```

**Corresponding WebFlux example** (illustrative method only):

```java
@GetMapping("/cart")
Mono<String> cart(WebSession session) {
    session.getAttributes().put("cart", "book");
    return Mono.just(session.getAttribute("cart"));
}
```

The WebFlux code may look shorter, but not because reading a `Map` is itself non-blocking I/O: retrieving the session from `ServerWebExchange` and saving it to a reactive repository is the part that can interact asynchronously. **Do not replace `HttpSession` with `WebSession` and then call synchronous JDBC/JPA repositories on the event loop**; proper blocking boundaries must be established.

## 5. Complete Java 17+ Demo: creating, reading, rotating ID, and invalidating WebSession

The example below is a **lab for session mechanics**, not a production session management system. The application uses Spring Security but allows access to `/lab/**` endpoints without logging in to demonstrate that **session != authenticated user**.

In this sample, **default CSRF protection is kept enabled**. Therefore, every `POST`/`DELETE` through a browser/client must include a valid CSRF token. Tests use Spring Security Test to send the token; a curl command without a token is used to verify the rejected response.

### 5.1 Structure and dependencies

```text
websession-lab/
  settings.gradle
  build.gradle
  src/main/resources/application.yml
  src/main/java/demo/session/WebSessionApplication.java
  src/main/java/demo/session/SecurityConfiguration.java
  src/main/java/demo/session/SessionController.java
  src/test/java/demo/session/SessionFlowTest.java
```

**settings.gradle**

```groovy
rootProject.name = 'websession-lab'
```

**build.gradle**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo.session'
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
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Do not add `spring-boot-starter-web`; the target is the **reactive** web stack. `spring-security-test` helps safely simulate CSRF in `WebTestClient`. Spring Boot 3.3.13 is chosen for API consistency in the example; do not treat it as a recommended production deployment version at the current time.

**src/main/resources/application.yml**

```yaml
server:
  reactive:
    session:
      timeout: 20m
      cookie:
        name: SESSION
        http-only: true
        same-site: lax
```

On localhost HTTP, the example does not enforce `secure: true` on the cookie for ease of testing; **Secure must be enabled in HTTPS production**. In other deployments, the cookie name may not be `SESSION`.

### 5.2 Spring Boot application

**src/main/java/demo/session/WebSessionApplication.java**

```java
package demo.session;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSessionApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSessionApplication.class, args);
    }
}
```

### 5.3 SecurityWebFilterChain

**src/main/java/demo/session/SecurityConfiguration.java**

```java
package demo.session;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/lab/**").permitAll()
                .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }
}
```

Reading the configuration:

- `/lab/**` is public so anonymous session operations can be exercised; this is an **exception meant only for a learning environment**. In real applications, do not let guests freely write sensitive state.
- `.anyExchange().authenticated()` protects other routes, such as `/secure/me`.
- `httpBasic(...)` supports APIs requiring a real identity; Basic and the `SESSION` cookie **are two different mechanisms** and do not replace each other.
- `formLogin` is disabled solely so curl receives a Basic challenge instead of a login page redirect.
- **Do not call `csrf(csrf -> csrf.disable())`**: CSRF still protects state-changing HTTP methods. Do not assume `permitAll()` removes the CSRF requirement.

### 5.4 Controller: using WebSession instead of HttpSession

**src/main/java/demo/session/SessionController.java**

```java
package demo.session;

import java.security.Principal;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.server.WebSession;

import reactor.core.publisher.Mono;

@RestController
public class SessionController {

    public record CartChange(String item) {}
    public record SessionState(boolean started, String cart) {}
    public record Ack(String status) {}

    private SessionState view(WebSession session) {
        String item = session.getAttribute("lab.cart");
        return new SessionState(session.isStarted(), item);
    }

    @GetMapping("/lab/state")
    public Mono<SessionState> state(WebSession session) {
        // Read-only: do not auto-create cart and do not call start().
        return Mono.just(view(session));
    }

    @PostMapping("/lab/cart")
    public Mono<SessionState> addCart(
            WebSession session, @RequestBody CartChange change) {
        if (change.item() == null || change.item().isBlank()) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "item must not be blank"));
        }

        // Writing an attribute -> WebSession is started implicitly.
        session.getAttributes().put("lab.cart", change.item());
        return Mono.just(view(session));
    }

    @PostMapping("/lab/rotate")
    public Mono<SessionState> rotate(WebSession session) {
        if (!session.isStarted()) {
            return Mono.error(new ResponseStatusException(
                HttpStatus.CONFLICT, "no started session"));
        }

        // Must include Mono<Void> in the returned chain.
        return session.changeSessionId()
            .then(Mono.fromSupplier(() -> view(session)));
    }

    @DeleteMapping("/lab/state")
    public Mono<Ack> invalidate(WebSession session) {
        return session.invalidate()
            .thenReturn(new Ack("invalidated"));
    }

    @GetMapping("/secure/me")
    public Mono<String> me(Principal principal) {
        return Mono.just("user: " + principal.getName());
    }
}
```

**Why does the example not return `session.getId()` in JSON?** The session ID is a bearer credential, not status information to expose to every client. To test that the ID changed, compare cookie values in a controlled HTTP client/test; do not create an endpoint that publicly exposes the ID.

**Why is `view(session)` read-only?** `GET /lab/state` is kept free of business side effects. `POST /lab/cart` creates/updates the cart; `POST /lab/rotate` rotates the ID; `DELETE /lab/state` invalidates the session. Even though all of them are `permitAll` in the lab, unsafe HTTP methods still require a valid CSRF token.

### 5.5 Running and observing HTTP

In the project directory, use JDK 17+ and a Gradle version compatible with Spring Boot 3.3:

```bash
gradle bootRun
```

If the project has a compatible Gradle Wrapper, use `./gradlew bootRun`; Windows PowerShell/cmd can use `gradlew.bat bootRun`.

**Reading a session with no attributes created yet**:

```bash
curl -i http://localhost:8080/lab/state
```

Expected key output:

```json
{
  "started": false,
  "cart": null
}
```

Do not rely on the absence of `Set-Cookie` across all environments: other `WebFilter`s may touch the session. What is guaranteed by the API is that **merely obtaining `WebSession` and reading attributes does not force starting it**.

**Trying a POST operation without a CSRF token**:

```bash
curl -i -X POST http://localhost:8080/lab/cart \
  -H "Content-Type: application/json" \
  --data '{"item":"book"}'
```

Because the configuration kept default CSRF enabled, a request without a valid token is expected to return **403 Forbidden** even though `/lab/**` has `permitAll()`. This illustrates that **authorization does not replace CSRF protection**. To actually write the cart, use the `WebTestClient` test in the next section or implement a proper CSRF token issuance/submission flow for the browser.

**Protected endpoint without credentials**:

```bash
curl -i -H "Accept: application/json" \
  http://localhost:8080/secure/me
```

Expected **401 Unauthorized**, distinct from the `403` caused by missing CSRF on POST. If you want to test Basic when logged in, use the development user/password provided by Spring Boot (if auto-configuration creates a user); do not assume the shopping cart cookie automatically grants access to `/secure/me`.

### 5.6 Automated testing with WebTestClient

**src/test/java/demo/session/SessionFlowTest.java**

```java
package demo.session;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureWebTestClient
class SessionFlowTest {

    @Autowired
    WebTestClient client;

    @Test
    void readingDoesNotRequireStartingASession() {
        client.get().uri("/lab/state")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.started").isEqualTo(false);
    }

    @Test
    void missingCsrfTokenIsRejected() {
        client.post().uri("/lab/cart")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new SessionController.CartChange("book"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void cartPersistsThroughCookieThenSessionIsInvalidated() {
        var stored = client.mutateWith(csrf())
            .post().uri("/lab/cart")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new SessionController.CartChange("book"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(SessionController.SessionState.class)
            .returnResult();

        ResponseCookie cookie =
            stored.getResponseCookies().getFirst("SESSION");
        assertNotNull(cookie);

        // Second request sends the cookie explicitly, not relying on
        // whether the client stores cookies automatically.
        client.get().uri("/lab/state")
            .cookie("SESSION", cookie.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.started").isEqualTo(true)
            .jsonPath("$.cart").isEqualTo("book");

        client.mutateWith(csrf())
            .delete().uri("/lab/state")
            .cookie("SESSION", cookie.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.status").isEqualTo("invalidated");

        // The old ID can no longer access the invalidated cart.
        client.get().uri("/lab/state")
            .cookie("SESSION", cookie.getValue())
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.started").isEqualTo(false);
    }

    @Test
    void cookieDoesNotCountAsAuthentication() {
        client.get().uri("/secure/me")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

In the test file above, the static import is wrapped across lines between package name tokens for readability; this is **valid Java syntax** (whitespace is permitted between tokens of a qualified name). If applying a single-line import formatting convention, it can be written as:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;
```

Using the single-line import is easiest to copy. `client.mutateWith(csrf())` belongs to Spring Security Test, not how a production browser obtains a token on its own; production clients must obtain a real server-issued CSRF token and send it back via the policy-compliant header/field.

Run:

```bash
gradle test
```

With proper configuration and dependencies, **4 test methods** are expected to verify: reading does not force start, POST without CSRF is rejected, cart persists across requests via cookie and is then invalidated, and protected routes reject unauthenticated clients. This is an **expectation reviewed from code**, not an actual build report. Using a `WebTestClient` mock server differs from end-to-end testing through a browser/reverse proxy; real environments still require testing cookie flags, SameSite, TLS, and logout.

### 5.7 Extension: testing session ID rotation

After creating a session via `POST /lab/cart` with valid CSRF, send:

```http
POST /lab/rotate HTTP/1.1
Cookie: SESSION=<old-id>
X-CSRF-TOKEN: <valid-csrf-token>
```

`session.changeSessionId()` creates a new ID in the store; `WebSessionManager`/resolver will reflect the corresponding ID to the client according to the response lifecycle. Use a test client allowed to inspect cookies to compare the old and new IDs; **do not log real IDs** into documentation or telemetry. If using a CSRF token stored in the session, keep/update the cookie and token according to the proper flow before the next request.

## 6. What does Spring Security use WebSession for?

`WebSession` is HTTP infrastructure; Spring Security has a separate layer to preserve `SecurityContext`:

- `ServerSecurityContextRepository` is the reactive interface with `load(ServerWebExchange)` and `save(ServerWebExchange, SecurityContext)`.
- `WebSessionServerSecurityContextRepository` stores `SecurityContext` in `WebSession`, and when saving the context also has a mechanism to **rotate the session ID** to mitigate session fixation.
- `NoOpServerSecurityContextRepository` does not persist security context across requests. Suitable for certain truly stateless APIs authenticated per request with properly validated bearer tokens.
- `ReactiveSecurityContextHolder` places/accesses the security context in the **Reactor Context of a subscription**. It is a mechanism for propagating identity within a request, not synonymous with persisting user info to the next HTTP request.

**Two contents that may reside together in a single WebSession must be distinguished:**

```text
WebSession (server-side store)
  ├── "lab.cart"              -> "book"                    (application state)
  ├── Spring Security context -> Authentication/User...   (if saved by repo)
  └── other attributes added by the system

Cookie SESSION=<id>           -> only identifies the session in the store
Reactor Context               -> supplies SecurityContext to the running pipeline
```

A shopping cart session can be created by an unauthenticated guest. The existence of a cookie **does not guarantee** a valid `SecurityContext` in the session; only the configured authentication mechanisms and repository determine whether login is remembered across requests.

### 6.1 Form login, Basic, and bearer tokens do not operate identically

| Authentication type | What role does the cookie/session usually play? | What to verify |
|---|---|---|
| Form login + browser | Can persist `SecurityContext` in `WebSession` so subsequent requests do not need to resend the password | Repository configuration, CSRF, session fixation, logout |
| HTTP Basic | Client usually sends username/password on every request | Do not assume a cart cookie equals credentials; persistence depends on the chain |
| Bearer JWT | Client sends token; resource server checks signature, issuer, audience, and permissions per policy | Do not auto-create login sessions; avoid unnecessary cookie mixing |
| OAuth2 Login/OIDC | May need a session for the login process, state/nonce, and saving authentication | Configure authorized client, context, and CSRF according to the model |
| Guest/anonymous | May have session state like a cart but no verified identity | Check public resources, do not grant permissions based on cookie presence |

Do not "fix" a 401 error by creating a new `WebSession`. A session is where *state is stored*, not a credential verifier.

### 6.2 Storing security context with a reactive repository

**Illustrative configuration snippet (replaces, rather than runs alongside, the demo bean in section 5):**

```java
@Bean
SecurityWebFilterChain securityWithSession(ServerHttpSecurity http) {
    var repository = new WebSessionServerSecurityContextRepository();

    return http
        .securityContextRepository(repository)
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/public/**").permitAll()
            .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

This snippet requires `@Configuration` and imports for `ServerHttpSecurity`, `SecurityWebFilterChain`, `Customizer`, `WebSessionServerSecurityContextRepository`, and `@Bean`; it is not standalone Java. It configures a repository that saves `SecurityContext` into `WebSession` to suit stateful flows. A user source and login/logout route design are still needed. Declaring a chain alone does not create a production account system.

For a genuinely **stateless resource server**, `NoOpServerSecurityContextRepository` can be used; however, only do so when token authentication actually occurs on every request and other components do not rely on server-side sessions. Do not enable `NoOp` merely to reduce the number of cookies and end up breaking form/OAuth2 login flows.

## 7. Logout, invalidation, and session fixation

### 7.1 Three easily confused operations

1. **Clearing/not persisting SecurityContext:** returns the user to an unauthenticated state going forward, depending on the authentication scheme and repository.
2. **`WebSession.invalidate()`:** invalidates the entire session in the store, including the cart and other attributes.
3. **Deleting the cookie in the browser:** the browser stops sending the old ID; **does not by itself guarantee server-side state was destroyed** if the server has not invalidated it.

A logout implementation that intends to terminate the user's entire session typically must address **both the security context and the WebSession**, especially when the application stores other shared data in the session.

Spring Security reactive provides `SecurityContextServerLogoutHandler` to remove the security context and `WebSessionServerLogoutHandler` to invalidate the `WebSession`. They can be combined:

```java
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

// Configuration snippet inside a SecurityWebFilterChain bean:
var logoutHandler = new DelegatingServerLogoutHandler(
    new SecurityContextServerLogoutHandler(),
    new WebSessionServerLogoutHandler());

http.logout(logout -> logout.logoutHandler(logoutHandler));
```

This snippet is **not yet a complete bean**: it still needs authorization, a login mechanism, and `build()`. In a web app using CSRF, logout via POST requires a valid CSRF token per configuration. Additionally, local logout does not automatically revoke issued access tokens or sign out at an external Identity Provider.

### 7.2 Preventing session fixation

**Session fixation** occurs if an attacker tricks a victim into using a session ID known to the attacker, and then the victim logs in without the ID changing. The known ID can then become the key to access the authenticated session.

- After successful login and when the security context is saved, `WebSessionServerSecurityContextRepository` has behavior to rotate the session ID per Spring Security's API to mitigate this risk.
- `WebSession.changeSessionId()` is WebFlux's primitive for proactively generating a new ID. It **does not change the user or clear attributes by itself**.
- Do not put session IDs in URLs/query strings, do not use an overly broad cookie `Domain`, and do not allow untrusted subdomains to overwrite cookies.
- Upgrade to a patched Spring Framework release. Older versions may contain session fixation vulnerabilities; do not treat "already called `changeSessionId()`" as a reason not to update the framework.

**Timing note:** documentation and security advisories change across versions. For example, Spring Framework advisory **CVE-2026-41839** published on 08/06/2026 describes a session fixation/escalation case in WebFlux on certain 6.1/6.2/7.0 releases; before going to production, verify affected versions and patched releases at https://spring.io/security/cve-2026-41839/. The Spring Boot 3.3.13 example in this article is for learning syntax, **not a recommended security baseline for 2026**.

## 8. Cookie security, CSRF, and session boundaries

### 8.1 CSRF still matters when browsers send cookies automatically

If the browser automatically sends `Cookie: SESSION=...` on a POST request, a malicious site can attempt to trigger state changes on behalf of the user. `HttpOnly` and `Secure` **do not fully solve** this attack vector. CSRF protection tailored to cookie/session flows (or an alternative authentication architecture not relying on automatically sent credentials) is required.

In the demo, `POST /lab/cart` without a CSRF token returns 403 despite `permitAll()`; this demonstrates a two-layer policy. For SPAs, a suitable CSRF token issuance mechanism is needed, sending the token via a header and managing rotation/renewal after login/logout.

Do not disable CSRF globally to "fix 403" in an application using session cookies for authentication. For pure bearer-token APIs with no cookie/session credentials, the CSRF assessment may differ, but it must be grounded in the actual threat model.

### 8.2 Browser-side vs. server-side expiration

- `WebSession.maxIdleTime` is the duration a session is allowed to remain inactive before expiring.
- Cookie `Max-Age` is how long the browser retains the cookie. An expired cookie may cause the client to lose access to the session even though data has not been cleaned up; a cookie that still exists does not extend an already expired server-side session.
- `CookieWebSessionIdResolver` by default can use a browser-session cookie (no fixed `Max-Age`). Applications may opt for persistent cookies, but must evaluate the risks.
- When a server-side session expires or is invalidated, requests carrying an old cookie must be treated as having no valid session; never recreate privileges simply from seeing a cookie named `SESSION`.

Do not equate `maxIdleTime` with absolute time since login. For high-security requirements, an **absolute session lifetime** or separate reauthentication limits may be needed, not just an idle timeout.

### 8.3 Conditions at reverse proxies and domains

- Configure HTTPS and `Secure` consistently from the browser to the TLS termination point.
- Be cautious with `Domain=.example.com` in ecosystems with less-trusted subdomains; prefer host-only cookies when there is no reason to share sessions.
- Restrict cookie `Path` and avoid name collisions between applications on the same host. Renaming the cookie does not automatically isolate data if Domain/Path and the backend store are misconfigured.
- Verify SameSite, CORS, CSRF, forwarding headers, and cookie clearing in real browser testing.
- Do not dump session cookies into access logs, error logs, tracing spans, screenshots, or analytics tools.

## 9. In-memory WebSession vs. distributed Spring Session

### 9.1 Easy default, not suited for every architecture

`InMemoryWebSessionStore` stores sessions in process memory. This works for demos or simple applications, but when deploying across multiple pods/nodes:

```text
Client has SESSION=id
      |
      +--> Pod A: has session id in memory -> cart has data
      |
      +--> Pod B: does not have id in memory -> cart not found
```

Load balancers can configure sticky sessions, but this is not a complete replacement for a durable session store during pod restarts, scaling, or failover. Evaluate TTL, capacity, session count, and expiration handling.

### 9.2 Spring Session replaces the persistence layer

**Spring Session** supports integration with `WebSession` via `WebSessionManager` and `ReactiveSessionRepository`, for example a store backed by Redis. When properly configured, multiple instances can read the same session data and reduce dependence on individual node memory.

An **orientational configuration snippet**, not a standalone runnable project:

```groovy
dependencies {
    implementation 'org.springframework.session:spring-session-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis-reactive'
}
```

Use dependency versions compatible with the Spring Boot and Spring Session versions chosen by the project; a Redis server, secure connection configuration, timeouts, serialization, key namespaces, and operational policies are required. With Spring Session reactive, `@EnableRedisWebSession` can be used to enable Redis-backed WebSession when explicitly managing configuration. Avoid placing this annotation alongside auto-configuration without understanding back-off behavior.

**Important note:** Traditional Spring Session JDBC designed for `HttpSession`/Servlet does not automatically turn a JDBC repository into WebFlux's **ReactiveSessionRepository**. For reactive sessions, choose an integration supporting a reactive store per the corresponding documentation; do not wrap a blocking repository yourself and assume it suffices under heavy load.

### 9.3 Trade-offs of distribution

- The Redis store/network can become slow or unavailable, leading to session read/write errors; configure timeouts, bounded retries, and fail-closed behavior when authentication is involved.
- Session attributes must have a serialization/versioning strategy; do not casually put JPA entities, `HttpServletRequest`, objects holding connections, secrets, or overly large payloads into Redis.
- Session invalidation/logout must take effect across all instances; test consistency and behavior when a client has multiple concurrent requests in flight.
- Monitor active sessions, expired sessions, error rates, store latency, and data volume; protect Redis with network controls, authentication, TLS, and backups aligned with your risk model.

## 10. Common mistakes

| Misconception / Misconfiguration | Consequence | Fix |
|---|---|---|
| "A WebFlux app must use `HttpSession` because it has cookies" | Mixing Servlet and reactive APIs | Use `WebSession` and `ServerWebExchange` |
| "Calling `getSession()` always creates a cookie" | False assumptions about no-op requests | Check `isStarted`, attribute-writing logic, and other filters |
| "`Mono.just(session.invalidate())` is enough" | Publisher is not properly composed and may not run | `return session.invalidate().thenReturn(...)` |
| "The `SESSION` cookie contains the user/cart itself" | Mistakenly believing data lives in the browser | The cookie holds the session ID; data is managed by the server-side store |
| "`JSESSIONID` is WebFlux's default cookie" | Session not found | Check `CookieWebSessionIdResolver` and Boot properties |
| "Having a cookie means logged in" | Unauthorized access granted to guest carts | Check `Authentication` and Security chain policies |
| "`permitAll` disables CSRF" | POST/DELETE gets 403, or CSRF is blindly disabled | Implement proper CSRF token flow |
| "Having `HttpOnly` blocks all CSRF" | Cross-site requests still carry cookies | Use CSRF, SameSite, and a matching threat model |
| "`secure=true` on localhost HTTP works identically" | Cookie is not sent as expected | Distinguish HTTP test environments from HTTPS production |
| "Deleting the cookie completes logout" | Backend session/token remains valid | Invalidate server-side; clear SecurityContext; handle tokens/IdP when needed |
| "`invalidate()` and `changeSessionId()` are the same" | Data needing removal stays intact | ID rotation keeps the session; invalidate destroys it |
| "Cookie Max-Age equals server timeout" | Session expires unexpectedly or cookie lingers too long | Configure both browser retention and backend idle timeout |
| "In-memory store across multiple pods syncs automatically" | Users lose state when switching pods or restarting | Use a distributed store supporting reactive |
| "`ThreadLocal SecurityContextHolder` works like MVC" | Lost/wrong context when switching threads | Use Reactor Context or controller parameters |
| "Store entire entities/credentials in session for convenience" | Data leaks, serialization errors, and memory bloat | Store minimal IDs/values, map DTOs server-side |
| "Already rotated session ID so no framework patch needed" | May miss fixation/cookie handling vulnerabilities | Track advisories and upgrade versions |

## 11. Checklist for WebSession design in Spring Security reactive

1. Identify whether the app uses WebFlux or Servlet before choosing `WebSession` or `HttpSession`.
2. Map the request flow: receive cookie ID -> resolve session -> load state -> authorization -> response saves session.
3. Document where sessions are started: `start()`, adding an attribute, CSRF/login filter, or application logic.
4. Never send session IDs in URLs, response DTOs, or logs; restrict access to request headers.
5. Use `server.reactive.session.timeout` and cookie properties when configuring Spring Boot reactive; test on real browsers/proxies.
6. Distinguish a cart session (which can be guest) from `SecurityContext` (which only exists when authenticated and properly saved).
7. Keep CSRF protection if the browser sends cookie credentials automatically; test that POST without a token is rejected and valid POST succeeds.
8. Design logout: clear context, invalidate `WebSession`, expire cookie, revoke tokens/IdP if required by the model.
9. Rotate session ID upon privilege escalation via framework-supported flows; monitor security patches.
10. On multiple nodes, use an appropriate distributed `WebSession` store, testing failover, race conditions, serialization, and TTL.
11. Avoid calling `block()` or manual `subscribe()` in request flows; compose `Mono`s from `invalidate`/`changeSessionId`.
12. Write tests for guests, real users, stale cookies, expired sessions, logout, and per-resource/tenant access control.

## 12. Practice exercises

1. Run the demo and call `GET /lab/state` before adding any attributes. Explain the difference between a `WebSession` object and a started session.
2. Run the four `WebTestClient` tests, then write a cart item using a valid CSRF token and carry the cookie to a new request. Explain why the same cookie retrieves the cart again.
3. Change `server.reactive.session.cookie.name` from `SESSION` to `APPSESSION`; update the client/test accordingly and explain why the name cannot be changed arbitrarily on only one side.
4. Once a session exists, call `POST /lab/rotate`. Inspect the new cookie ID and session attribute; why does a new ID not mean the cart was cleared?
5. Call `DELETE /lab/state` and retry with the old ID. Explain the difference between invalidating in the store and deleting the cookie in the browser.
6. Add `Secure` in an HTTPS environment and test `SameSite=Lax/Strict/None` under a cross-site scenario. Do not confuse browser behavior with server permissions.
7. Compare an MVC method using `request.getSession(false)` with `ServerWebExchange.getSession()` and `WebSession.isStarted()`. Do they follow the same session creation rules?
8. Design form login for WebFlux, describe how `SecurityContext` is saved/loaded via `WebSessionServerSecurityContextRepository`, and verify whether logout invalidates the session.
9. Propose how to migrate a multi-pod application from `InMemoryWebSessionStore` to Spring Session Redis, including bounded retries, TTL, and serialization.
10. Explain why a browser with a session cookie is not automatically admitted to `/secure/me` when the application only grants cart state to guests.

## Key takeaways

**`WebSession` is Spring WebFlux's server-side session; `HttpSession` is the Servlet API session.** WebFlux accesses `WebSession` through reactive APIs and does not start a session merely by reading the object; adding attributes or calling `start()` starts it. The **`SESSION`** cookie typically only holds an ID to look up data in `WebSessionStore`, not proof of authentication. In Spring Security reactive, `WebSessionServerSecurityContextRepository` can persist `SecurityContext` in the session, while authentication, authorization, CSRF, ID rotation, logout, and session expiry remain separate responsibilities to design, configure, and test.

## Official documentation

- Spring Framework 6.1 — `WebSession` API, `start`/`isStarted`/`changeSessionId`/`invalidate`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/WebSession.html
- Spring Framework 6.1 — `CookieWebSessionIdResolver` default `SESSION` and cookie initializers: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html
- Spring Framework — WebFlux controller arguments (`WebSession`): https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/arguments.html
- Spring Boot 3.3 — Common application properties, `server.reactive.session.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring Security 6.3 — `WebSessionServerSecurityContextRepository`: https://docs.spring.io/spring-security/site/docs/6.3.7/api/org/springframework/security/web/server/context/WebSessionServerSecurityContextRepository.html
- Spring Security — Reactive logout and WebSessionServerLogoutHandler: https://docs.spring.io/spring-security/reference/6.5/reactive/authentication/logout.html
- Spring Security — Reactive CSRF and WebTestClient CSRF testing: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Session — WebSession integration/Redis: https://docs.spring.io/spring-session/reference/web-session.html
- Spring Framework security advisory on WebFlux session fixation: https://spring.io/security/cve-2026-41839/
