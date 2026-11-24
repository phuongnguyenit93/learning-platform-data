# Reading Mono<CsrfToken> and Ensuring Tokens Are Generated on Demand

> **Topic:** Spring Security – reactive  
> **Knowledge group:** CSRF Protection  
> **Focus:** Reading `Mono<CsrfToken>` properly from `ServerWebExchange`, triggering loading/generating/saving of CSRF tokens **via intentional subscription** in the WebFlux pipeline, exposing tokens to HTML forms or same-origin clients, and testing requests reusing tokens with the same session.

## 1. Practical problem: why does a GET page lack a token?

A Spring WebFlux application uses Spring Security to protect a form:

```html
<form action="/api/form" method="post">
    <input type="text" name="message">
    <button type="submit">Submit</button>
</form>
```

If the form contains only these two fields without sending a CSRF token, `POST /api/form` will typically receive **403 Forbidden** from Spring Security. This is not necessarily a login, role, or controller bug. `CsrfWebFilter` requires a valid CSRF token by default for HTTP methods that can mutate state, such as POST.

In Spring Security **reactive**, an easily overlooked detail is that the CSRF token **is not always already created** when a GET request enters the application. The framework puts a **publisher** into `ServerWebExchange`:

```java
Mono<CsrfToken>
```

When this publisher is **subscribed to**, the expected token is loaded from the repository or generated/saved if absent. Merely fetching the attribute or calling `doOnNext` while discarding the publisher will not guarantee token creation happens.

Core example:

```java
@GetMapping("/csrf")
Mono<CsrfView> csrf(ServerWebExchange exchange) {
    Mono<CsrfToken> tokenMono =
        exchange.getAttribute(CsrfToken.class.getName());

    if (tokenMono == null) {
        return Mono.error(
            new IllegalStateException("CSRF publisher unavailable"));
    }

    return tokenMono.map(token -> new CsrfView(
        token.getHeaderName(),
        token.getParameterName(),
        token.getToken()));
}
```

This is a **snippet**, requiring `CsrfView`/imports and security configuration. Because the controller **returns a publisher built on `tokenMono`**, WebFlux subscribes to produce the HTTP response, triggering the token load/generation path. The complete project in Section 8 demonstrates both keeping the session cookie and sending the token on POST.

### Learning Objectives

After this lesson, you will be able to:

1. Explain CSRF risk and why tokens must accompany browser sessions/credentials.
2. Identify the exact attribute key **`CsrfToken.class.getName()`** holding `Mono<CsrfToken>` in `ServerWebExchange`.
3. Distinguish an **unsubscribed publisher** from an emitted `CsrfToken`; use `map`/`flatMap`/`then` instead of `block()` or manual `subscribe()`.
4. Understand the roles of `CsrfWebFilter`, `ServerCsrfTokenRepository`, `ServerCsrfTokenRequestHandler`, the `WebSession`-based repository, and the BREACH-mitigating XOR handler.
5. Proactively trigger token creation when rendering forms or serving token endpoints, while **avoiding unnecessary token creation on useless GETs**.
6. Place tokens into hidden `_csrf` fields or `X-CSRF-TOKEN` HTTP headers and submit them back with the **same session cookie**.
7. Test GET token retrieval, valid/invalid/missing token POSTs, cross-session POSTs, and lazy semantics using `WebTestClient` + `StepVerifier`.

## 2. Why protect against CSRF?

CSRF (Cross-Site Request Forgery) exploits the browser's tendency to auto-send credentials tied to a website, such as session cookies or cached HTTP authentication credentials. A malicious website can cause a user's browser to submit a POST to a target site without the user's intent.

```text
User is logged into shop.example
          |
          v
Browser holds shop.example session cookie
          |
          v
User opens unfamiliar website attacker.example
          |
          v
Unfamiliar page tries to make browser POST shop.example/api/change
          |
          v
Browser may auto-send eligible cookies for shop.example
          |
          v
If server relies solely on cookies => risk of forged request
If server requires session-bound secret token => blocked
```

A CSRF token under the **synchronizer-token pattern** is an unpredictable value that the server stores and verifies against a valid context. The client must submit the token in a place the browser **does not auto-attach to requests from external pages** — typically a hidden form parameter or an HTTP header set by same-origin JavaScript.

**Distinguishing from other mechanisms:**

| Mechanism | What problem does it solve? | What it does NOT replace |
| --- | --- | --- |
| Session cookie | Maintains identity/session | CSRF token when browser auto-sends cookies |
| HTTP Basic | Authenticates username/password | CSRF if browser can auto-send credentials |
| CSRF token | Verifies unsafe request originated from a server-issued token flow | Authentication, authorization, business validation |
| CORS | Restricts browsers reading responses/sending certain cross-origin requests | CSRF tokens; cross-site form POSTs can still occur |
| SameSite cookie | Curbs many cross-site cookie transmissions | Defense-in-depth; not guaranteed to replace all CSRF policies |
| XSS protection | Stops malicious scripts running inside a trusted origin | CSRF tokens cannot stop same-origin XSS |

HTTP methods **GET, HEAD, OPTIONS, TRACE** are treated as safe by the default CSRF matcher; applications must ensure they **do not mutate state**. Never design `GET /delete-account` and expect the default CSRF filter to block it.

Spring Security WebFlux enables CSRF protection by default unless disabled in configuration. Never casually add `.csrf(csrf -> csrf.disable())` just because you hit 403; determine whether clients use auto-sent browser credentials and assess the specific threat model.

## 3. Exactly which objects are involved?

These components are easily mixed up:

| Name | Type | Responsibility |
| --- | --- | --- |
| `CsrfToken` | Interface, synchronous | Provides `getToken()`, `getHeaderName()`, `getParameterName()` |
| `Mono<CsrfToken>` | Reactor Publisher | Describes loading/generating the token; executes only upon subscription |
| `CsrfWebFilter` | `org.springframework.web.server.WebFilter` | Exposes publisher on exchange; validates tokens for CSRF-protected requests |
| `ServerWebExchange` | WebFlux request/response context | Holds attributes, `WebSession`, request/response |
| `ServerCsrfTokenRepository` | Reactive interface | `loadToken`, `generateToken`, `saveToken` |
| `WebSessionServerCsrfTokenRepository` | Default repository | Stores expected token in `WebSession` |
| `CookieServerCsrfTokenRepository` | Alternative repository | Stores token in a cookie; requires security/SPA evaluation |
| `ServerCsrfTokenRequestHandler` | Request handler/resolver | Exposes token on exchange and resolves client-submitted token |
| `XorServerCsrfTokenRequestAttributeHandler` | Default handler since Spring Security 6 | Masks token per request to help mitigate BREACH |

**Correct WebFlux packages:**

```java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.CsrfWebFilter;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.XorServerCsrfTokenRequestAttributeHandler;
```

This is an **illustrative import list**; not all are needed in one file. Do not confuse them with `org.springframework.security.web.csrf.CsrfToken` (Servlet) or `HttpSessionCsrfTokenRepository`. For WebFlux, classes live under packages containing **`.web.server.csrf`**, and repositories return `Mono`.

### 3.1. The crucial attribute key

In Spring Security WebFlux 6.5, `CsrfWebFilter` exposes the publisher under key:

```java
CsrfToken.class.getName()
```

Corresponding string value:

```text
org.springframework.security.web.server.csrf.CsrfToken
```

Correct lookup code:

```java
Mono<CsrfToken> csrfToken =
    exchange.getAttribute(CsrfToken.class.getName());
```

`exchange.getAttribute(...)` retrieves the value from the attribute map without executing the publisher itself. If the publisher is null, there is usually a configuration/chain issue (`CsrfWebFilter` not running, CSRF disabled, request matching a different chain); never fake a token or silently allow POSTs. The example project returns an explicit server error rather than rendering a form missing its hidden field.

Things that are **not the same**:

```text
CsrfToken.class.getName()  -> key holding Mono<CsrfToken> from framework
"_csrf"                    -> common form parameter/view attribute name
"X-CSRF-TOKEN"             -> common request header name
"XSRF-TOKEN"               -> common cookie name for cookie repository
```

Do not call `exchange.getAttribute("_csrf")` assuming it is `Mono<CsrfToken>`. A view integration or `@ControllerAdvice` may expose the **resolved `CsrfToken`** under `_csrf` for templates; those are different layers.

### 3.2. Three getters on CsrfToken

```java
// Snippet inside .map(token -> ...):
String headerName = token.getHeaderName();
String parameterName = token.getParameterName();
String renderedToken = token.getToken();
```

- `getToken()`: value **issued to the client per the active handler**. With the default XOR handler, the exposed value may be a masked token; **do not pull a raw token from the repository as a substitute**.
- `getHeaderName()`: header name the client must send, usually `X-CSRF-TOKEN` with the default WebSession repository.
- `getParameterName()`: form field name, usually `_csrf`.

HTML/JS code should use names obtained from the token or agreed configuration instead of hardcoding across many files; if the app changes `setHeaderName`/`setParameterName` while the frontend keeps old names, POSTs will receive 403.

## 4. Lazy mechanics: why must we subscribe?

In Reactor, a `Mono<T>` describes a pipeline. Creating a `Mono` variable or chaining an intermediate operator **does not mean the pipeline has executed**.

```text
GET /csrf
   |
   v
CsrfWebFilter fetches/creates Mono<CsrfToken> publisher
   |
   v
ServerCsrfTokenRequestHandler places publisher in exchange attributes
   |
   v
Controller reads Mono<CsrfToken> attribute
   |
   +-- Controller ignores Mono, returns static text
   |       |
   |       +--> no guarantee a new token is created/saved
   |
   +-- Controller returns tokenMono.map(CsrfView::new)
           |
           v
      WebFlux subscribes to build response
           |
           v
      Repository: load existing token / generate new / save
           |
           v
      Response contains field/header names + exposed token
```

The `CsrfWebFilter` API docs explicitly state: if no token exists yet, the new token is **saved automatically when the publisher is subscribed to**. Thus the goal is not "manually call `generateToken()` on every request", but rather **wire the publisher into a pipeline actually subscribed to when the UI needs a token**.

### 4.1. Wrong: only retrieving the attribute

```java
@GetMapping("/bad")
Mono<String> bad(ServerWebExchange exchange) {
    Mono<CsrfToken> csrf =
        exchange.getAttribute(CsrfToken.class.getName());
    // Publisher not used in the response.
    return Mono.just("HTML without token");
}
```

This snippet illustrates an anti-pattern. `csrf` is just a reference; token generation/saving was never triggered by the controller. Never treat the mere presence of an attribute as proof that a token was persisted in the session.

### 4.2. Wrong: doOnNext while discarding the new publisher

```java
Mono<CsrfToken> csrf =
    exchange.getAttribute(CsrfToken.class.getName());

// Wrong if the returned Mono is discarded:
csrf.doOnNext(token -> exchange.getAttributes().put("_csrf", token));

return Mono.just("view");
```

`doOnNext` returns a new publisher carrying that side effect on subscription; here nobody subscribes to that new publisher, so the side effect never runs in the controller path. You must **return/compose** the transformed publisher.

### 4.3. Right: compose and let the framework subscribe

```java
Mono<CsrfToken> csrf =
    exchange.getAttribute(CsrfToken.class.getName());

return csrf.map(token -> token.getToken());
```

When a WebFlux method returns `Mono<String>`, the response writer subscribes to the publisher. Consequently the token is loaded/generated/saved if needed, with no `block()` or stray subscription.

### 4.4. Right: chaining other work with flatMap/then

```java
// Illustrative: auditService is a reactive dependency supplied by the app.
return csrfMono.flatMap(token ->
    auditService.record("csrf-view-generated")
        .thenReturn(token.getToken()));
```

`auditService.record` must return a reactive publisher. This is a conceptual snippet, not a standalone runnable Java file. Never log the token value itself in audits; log only the necessary event.

### 4.5. Never use block()/subscribe() in controllers

```java
// Wrong on a WebFlux request path:
CsrfToken token = csrfMono.block();

// Also wrong: detached subscription, does not wait for token save to finish.
csrfMono.subscribe(token -> exchange.getAttributes().put("_csrf", token));
return Mono.just("render immediately");
```

`.block()` can block the event loop and throw errors on non-blocking schedulers. Manual `.subscribe()` detaches token creation/saving from the response lifecycle, breaking ordering, error handling, and cancellation. Replace them with `map`/`flatMap` and **return the `Mono`** to WebFlux.

## 5. BREACH/XOR: tokens exposed to views can differ from tokens stored in session

Since Spring Security **6.0**, WebFlux's default handler is `XorServerCsrfTokenRequestAttributeHandler`, helping counter BREACH information-leakage channels by **masking the CSRF token** when emitted in responses. The record stored in the repository and the value placed in a form can look different even when backed by the same expected token.

```text
WebSessionServerCsrfTokenRepository
      |
      v
Expected raw token (stored in WebSession)
      |
      v
XorServerCsrfTokenRequestAttributeHandler
      |
      v
CsrfToken exposed to view
      |
      v
form input / header carries masked token
      |
      v
Client submits token
      |
      v
Request handler unmasks / resolves
      |
      v
CsrfWebFilter matches against expected token in repository
```

**Important consequences:**

1. Never expect `token.getToken()` to always equal the raw value stored in the session.
2. Never assert "two consecutive GET pages must display the same token string". With XOR masking, the exposed value can vary per request while the server's raw expected token stays usable.
3. Clients should submit **the exact token received from the response/form**, without inventing or decoding/masking it on the frontend.
4. Switching `csrfTokenRequestHandler` back to `ServerCsrfTokenRequestAttributeHandler` alters BREACH protection — **never do it just to make a test pass**.
5. With cookie-based CSRF in SPAs, the cookie typically holds the raw value while the default XOR handler expects masked request tokens. Never assume copying the `XSRF-TOKEN` cookie straight into `X-XSRF-TOKEN` works across all setups; use a compatible request handler/SPA integration and integration tests.

### 5.1. A request token is not a password

A CSRF token is a session-sensitive security value, not a login credential. Yet exposing the token to the legitimate browser/user is **required** by the synchronizer token pattern. Prevent leakage via URLs, analytics, logging, cross-origin responses, HTTP caches, referrers, and XSS.

In the example, `GET /csrf` returns **uncached** JSON. For apps with sensitive authentication state, restrict token retrieval by policy and CORS controls. Cross-site scripts cannot read the token due to the same-origin policy when CORS is tight, yet **same-origin XSS** can read it; CSRF does not replace XSS protection.

## 6. Rendering forms: ensuring the Mono is consumed

### 6.1. Rendering directly from Mono

Preferred pattern when rendering HTML manually:

```java
@GetMapping(value = "/form", produces = MediaType.TEXT_HTML_VALUE)
Mono<String> form(ServerWebExchange exchange) {
    Mono<CsrfToken> csrf =
        exchange.getAttribute(CsrfToken.class.getName());

    if (csrf == null) {
        return Mono.error(new IllegalStateException("CSRF unavailable"));
    }

    return csrf.map(token -> {
        String field = HtmlUtils.htmlEscape(token.getParameterName());
        String value = HtmlUtils.htmlEscape(token.getToken());
        return "<form action='/api/form' method='post'>"
            + "<input type='hidden' name='" + field
            + "' value='" + value + "'>"
            + "<button type='submit'>Submit</button></form>";
    });
}
```

This snippet needs imports and a wired class. The complete project in Section 8 includes an equivalent implementation plus a text input for testing POSTs. The decisive point is **`return csrf.map(...)`**, not a synchronous `String` built before the CSRF publisher is subscribed to.

`HtmlUtils.htmlEscape` prevents unsafe interpolation into HTML attributes. Even though default tokens use Base64/UUID characters, HTML rendering **still requires escaping** when concatenating strings.

### 6.2. @ControllerAdvice + @ModelAttribute for template engines

When using view technologies integrated with `RequestDataValueProcessor`, Spring Security recommends exposing the token under the `_csrf` attribute. Example:

```java
// Illustrative snippet (placed in @ControllerAdvice class with imports).
@ModelAttribute
Mono<CsrfToken> csrfToken(ServerWebExchange exchange) {
    Mono<CsrfToken> publisher =
        exchange.getAttribute(CsrfToken.class.getName());
    if (publisher == null) {
        return Mono.error(new IllegalStateException("CSRF unavailable"));
    }
    return publisher.doOnSuccess(token ->
        exchange.getAttributes().put(
            CsrfRequestDataValueProcessor.DEFAULT_CSRF_ATTR_NAME,
            token));
}
```

Import `CsrfRequestDataValueProcessor` from Spring Security WebFlux. The goal is **when the model publisher is subscribed to**, placing the resolved token into attribute `_csrf` for `CsrfRequestDataValueProcessor`/views. Never create a new `Mono` and discard it. Thymeleaf with Spring Security integration can handle much of this boilerplate automatically; for other rendering engines, verify subscription happens.

The rendered form may contain:

```html
<form action="/api/form" method="post">
    <input type="hidden" name="_csrf" value="TOKEN_PROVIDED_BY_SERVER">
    <input name="message" value="hello">
    <button type="submit">Save</button>
</form>
```

`TOKEN_PROVIDED_BY_SERVER` here is solely an **explanatory placeholder**, not a value you should submit. In runnable code, the hidden input is populated from `token.getToken()`; the token is masked per the active handler. In templates, avoid hardcoding field names if the repository may be configured differently.

### 6.3. JSON/API endpoints for same-origin clients

If the frontend sends JSON, it cannot rely on a `_csrf` form parameter inside a JSON body. Instead, fetch a valid token and send it in an **HTTP header**:

```http
GET /csrf
Cookie: SESSION=<active-session-cookie>
```

Illustrative response:

```json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "<server-issued-token-value>"
}
```

Client sends an unsafe request:

```http
POST /api/change
Cookie: SESSION=<same-session-cookie>
Authorization: Basic <demo-credentials>
X-CSRF-TOKEN: <server-issued-token-value>
Content-Type: application/json

{"message":"hello"}
```

Both requests must belong to the **same session** if the server uses `WebSessionServerCsrfTokenRepository`. A token obtained for session A cannot be used with session B, even if request B carries a valid username/password.

## 7. Not every GET needs to force token creation

Generating/saving CSRF tokens can cause the app to create sessions on requests meant purely for reading data. On high-traffic cacheable sites, **forcing subscriptions on every GET** can bloat `WebSession` count, hurt cacheability, and complicate operations.

| GET request | Truly needs a token? | How to handle |
| --- | --- | --- |
| `GET /public` showing public content only | Usually no | Do not subscribe solely to force CSRF creation |
| `GET /form` rendering a POST form | **Yes** | Consume `Mono<CsrfToken>` when rendering hidden input |
| `GET /csrf` issuing tokens to same-origin JS | **Yes** | Return `Mono<CsrfView>` publisher; no-store |
| `GET /health` | Usually no | Keep lightweight; avoid auto-creating sessions |
| `GET /dashboard` with no forms/actions | Depends on UX | If no unsafe actions exist, avoid useless token creation |
| JSON-only stateless API with Bearer headers | Depends on threat model | Evaluate CSRF separately; never disable blindly |

**Ensuring tokens are created on demand** means letting routes/paths that need tokens **consume the publisher** so the framework saves the token, rather than calling `generateToken` manually on every GET.

### 7.1. Repository flow: load, generate, save

`ServerCsrfTokenRepository` has three methods:

```java
Mono<CsrfToken> loadToken(ServerWebExchange exchange);
Mono<CsrfToken> generateToken(ServerWebExchange exchange);
Mono<Void> saveToken(ServerWebExchange exchange, CsrfToken token);
```

**These are illustrative API signatures**, not a custom interface to define. `CsrfWebFilter` uses the repository to obtain expected tokens and saves new tokens when the `Mono` is subscribed to. You normally **do not need** to call generate/save directly in controllers just to render a form. Conceptual algorithm:

```text
If repo.loadToken(exchange) finds an expected token:
    use existing token
Otherwise, when CSRF Mono is subscribed to:
    repo.generateToken(exchange)
    repo.saveToken(exchange, generated)
    provide token to handler/view
```

If you implement a custom repository, ensure `loadToken`/`saveToken` return proper non-blocking publishers and do not endlessly generate new tokens on every attempt. `saveToken(exchange, null)` deletes the token per interface contract; across login/logout or session invalidation lifecycles, tokens may need to be reissued.

## 8. Runnable Java 17+ WebFlux project

The project uses **Spring Boot 3.5.16** for a concrete learning baseline with Spring Security 6.5.x and Java 17. The 3.5 line has reached end of OSS support; new production projects in 2026 should use a supported Spring Boot branch and review migration notes rather than treating this version as a new production pick.

Structure:

```text
reactive-csrf-on-demand/
├── pom.xml
└── src/
    ├── main/java/demo/csrf/
    │   ├── Application.java
    │   ├── SecurityConfiguration.java
    │   └── CsrfController.java
    └── test/java/demo/csrf/
        ├── CsrfFlowTests.java
        └── CsrfMonoSemanticsTests.java
```

**Design:**

- `GET /public`: public, **does not subscribe to CSRF tokens**.
- `GET /csrf`: returns `CsrfView` with `headerName`/`parameterName`/`token`, triggering load or generate/save as needed.
- `GET /form`: returns an HTML form with a hidden CSRF field, triggering the same publisher.
- `GET /api/profile`: requires Basic authentication, but no CSRF since it is a GET.
- `POST /api/change`: requires Basic auth and CSRF header, accepts JSON.
- `POST /api/form`: requires Basic auth and CSRF form parameter.
- CSRF stays enabled, explicitly using `WebSessionServerCsrfTokenRepository` and the default XOR request handler.
- Account `alice` with password `demo123` is strictly for local testing; stored with BCrypt hash, never deployed with real hardcoded credentials.

### 8.1. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>reactive-csrf-on-demand</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Because `spring-boot-starter-webflux` includes Spring WebFlux and Jackson, JSON responses for Java records encode automatically. `spring-boot-starter-security` configures WebFlux security. `spring-boot-starter-test` and `spring-security-test` support tests.

### 8.2. src/main/java/demo/csrf/Application.java

```java
package demo.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 8.3. src/main/java/demo/csrf/SecurityConfiguration.java

```java
package demo.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.UserDetailsRepositoryReactiveAuthenticationManager;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();
        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    ReactiveAuthenticationManager authenticationManager(
            MapReactiveUserDetailsService users, PasswordEncoder encoder) {
        UserDetailsRepositoryReactiveAuthenticationManager manager =
            new UserDetailsRepositoryReactiveAuthenticationManager(users);
        manager.setPasswordEncoder(encoder);
        return manager;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http, ReactiveAuthenticationManager manager) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public", "/csrf", "/form").permitAll()
                .pathMatchers("/api/**").authenticated()
                .anyExchange().denyAll()
            )
            .httpBasic(basic -> basic.authenticationManager(manager))
            .formLogin(form -> form.disable())
            // Do not disable CSRF. Keep default XOR request handler.
            .csrf(csrf -> csrf.csrfTokenRepository(
                new WebSessionServerCsrfTokenRepository()))
            .build();
    }
}
```

**Annotations:**

1. `.csrf(...)` only declares the repository; CSRF remains **enabled**. The default 6.x handler remains `XorServerCsrfTokenRequestAttributeHandler`.
2. `WebSessionServerCsrfTokenRepository` stores the expected token in `WebSession`. Masked tokens emitted by the handler must not be compared directly against raw session strings.
3. `permitAll()` on `GET /csrf` **does not disable CSRF** for subsequent POSTs; GET is a safe method while POST needs a token.
4. `httpBasic(...)` lets us test authentication independently; valid Basic auth **does not bypass** CSRF.
5. `.formLogin(...disable())` only disables default form-login authentication, **not the application's sample HTML form**.
6. The demo is localhost-only; deployments must use HTTPS and proper secret management instead of hardcoded passwords.

### 8.4. src/main/java/demo/csrf/CsrfController.java

```java
package demo.csrf;

import org.springframework.http.MediaType;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.util.HtmlUtils;
import reactor.core.publisher.Mono;

@RestController
public class CsrfController {

    public record CsrfView(
            String headerName, String parameterName, String token) {}

    public record ChangeRequest(String message) {}

    // Retrieve publisher placed on exchange by CsrfWebFilter.
    private Mono<CsrfToken> tokenPublisher(ServerWebExchange exchange) {
        Mono<CsrfToken> publisher =
            exchange.getAttribute(CsrfToken.class.getName());

        if (publisher == null) {
            return Mono.error(
                new IllegalStateException("CSRF filter did not expose token"));
        }

        return publisher;
    }

    @GetMapping("/public")
    public Mono<String> publicInfo() {
        return Mono.just("public OK");
    }

    // Same-origin endpoint: consume publisher; new token saved on demand.
    @GetMapping(value = "/csrf",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<CsrfView> csrf(ServerWebExchange exchange) {
        exchange.getResponse().getHeaders().setCacheControl("no-store");

        return tokenPublisher(exchange)
            .map(token -> new CsrfView(
                token.getHeaderName(),
                token.getParameterName(),
                token.getToken()));
    }

    // Render a small HTML form, escaping all values inserted into attributes.
    @GetMapping(value = "/form",
            produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> form(ServerWebExchange exchange) {
        exchange.getResponse().getHeaders().setCacheControl("no-store");

        return tokenPublisher(exchange).map(token -> {
            String parameterName =
                HtmlUtils.htmlEscape(token.getParameterName());
            String value = HtmlUtils.htmlEscape(token.getToken());

            return """
                <!doctype html>
                <html lang="en">
                <head><meta charset="utf-8"><title>CSRF demo</title></head>
                <body>
                  <form method="post" action="/api/form">
                    <input type="hidden" name="%s" value="%s">
                    <input type="text" name="message" value="hello">
                    <button type="submit">Save</button>
                  </form>
                </body>
                </html>
                """.formatted(parameterName, value);
        });
    }

    // Safe GET requires no CSRF token.
    @GetMapping("/api/profile")
    public Mono<String> profile() {
        return Mono.just("profile OK");
    }

    @PostMapping(value = "/api/change",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<String> change(@RequestBody Mono<ChangeRequest> body) {
        return body.map(request -> "saved:" + request.message());
    }

    @PostMapping(value = "/api/form",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public Mono<String> submitForm(ServerWebExchange exchange) {
        return exchange.getFormData()
            .map(data -> "form:" + data.getFirst("message"));
    }
}
```

**The single most important point in this file:** `GET /csrf` and `GET /form` both **return a publisher composed from `tokenPublisher(exchange)`**. The subscription performed by WebFlux when writing the response gives `CsrfWebFilter`/the repository its chance to generate and save a new token. By contrast, `GET /public` neither reads nor forces token creation.

`GET /csrf` returns the token in JSON, and the response sets `Cache-Control: no-store` to reduce accidental token caching. In production, also enforce CORS/Cache policies, same-origin checks, and restrict public proxy caching. Clients use `CsrfView.headerName` and `CsrfView.token` for unsafe requests, **never generating tokens on the client**.

## 9. Integration tests: fetch real token, keep same WebSession, then valid POST

The test suite runs **Spring Boot with Netty on a random port**, rather than invoking controllers in isolation, to exercise the real HTTP, CSRF filter, session cookie, and Basic authentication pipeline. `@SpringBootTest(webEnvironment=RANDOM_PORT)` paired with `@AutoConfigureWebTestClient` configures a `WebTestClient` against the live server.

### 9.1. src/test/java/demo/csrf/CsrfFlowTests.java

```java
package demo.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CsrfFlowTests {

    @Autowired
    WebTestClient client;

    private record Issued(
        CsrfController.CsrfView csrf, String sessionId) {}

    // This GET subscribes to Mono<CsrfToken>, creating/saving a token on demand.
    private Issued issue() {
        EntityExchangeResult<CsrfController.CsrfView> result =
            client.get().uri("/csrf")
                .exchange()
                .expectStatus().isOk()
                .expectBody(CsrfController.CsrfView.class)
                .returnResult();

        CsrfController.CsrfView csrf = result.getResponseBody();
        assertNotNull(csrf);
        assertNotNull(csrf.token());
        assertNotNull(csrf.headerName());
        assertNotNull(csrf.parameterName());

        ResponseCookie cookie =
            result.getResponseCookies().getFirst("SESSION");
        assertNotNull(cookie, "new WebSession must have a cookie");

        return new Issued(csrf, cookie.getValue());
    }

    private WebTestClient.ResponseSpec postJson(
            Issued issued, String submittedCsrfToken) {

        return client.post().uri("/api/change")
            .cookie("SESSION", issued.sessionId())
            .headers(headers -> {
                headers.setBasicAuth("alice", "demo123");
                if (submittedCsrfToken != null) {
                    headers.set(
                        issued.csrf().headerName(), submittedCsrfToken);
                }
            })
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CsrfController.ChangeRequest("hello"))
            .exchange();
    }

    @Test
    void publicGetDoesNotNeedCsrfToken() {
        client.get().uri("/public")
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("public OK");
    }

    @Test
    void csrfGetCreatesTokenAndWebSessionCookieWhenNeeded() {
        Issued issued = issue();
        assertEquals("X-CSRF-TOKEN", issued.csrf().headerName());
        assertEquals("_csrf", issued.csrf().parameterName());
        assertTrue(!issued.csrf().token().isBlank());
        assertTrue(!issued.sessionId().isBlank());
    }

    @Test
    void csrfResponseIsNotCacheable() {
        client.get().uri("/csrf")
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .valueMatches(HttpHeaders.CACHE_CONTROL, ".*no-store.*");
    }

    @Test
    void safeGetWorksWithoutCsrfButRequiresAuthentication() {
        client.get().uri("/api/profile")
            .headers(h -> h.setBasicAuth("alice", "demo123"))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("profile OK");
    }

    @Test
    void postWithoutCsrfIsRejectedEvenWithValidBasicCredentials() {
        Issued issued = issue();
        postJson(issued, null)
            .expectStatus().isForbidden();
    }

    @Test
    void postWithWrongCsrfIsRejected() {
        Issued issued = issue();
        postJson(issued, "invalid-csrf-token")
            .expectStatus().isForbidden();
    }

    @Test
    void validCsrfFromSameSessionAllowsJsonPost() {
        Issued issued = issue();
        postJson(issued, issued.csrf().token())
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("saved:hello");
    }

    @Test
    void validCsrfCanBeUsedWithSubsequentPostInSameSession() {
        Issued issued = issue();
        postJson(issued, issued.csrf().token())
            .expectStatus().isOk();
        postJson(issued, issued.csrf().token())
            .expectStatus().isOk();
    }

    @Test
    void tokenWithoutItsSessionCookieIsRejected() {
        Issued issued = issue();

        client.post().uri("/api/change")
            .headers(h -> h.setBasicAuth("alice", "demo123"))
            .header(issued.csrf().headerName(), issued.csrf().token())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CsrfController.ChangeRequest("hello"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void tokenFromDifferentSessionIsRejected() {
        Issued a = issue();
        Issued b = issue();
        assertNotEquals(a.sessionId(), b.sessionId());

        postJson(b, a.csrf().token())
            .expectStatus().isForbidden();
    }

    @Test
    void validCsrfDoesNotReplaceAuthentication() {
        Issued issued = issue();

        client.post().uri("/api/change")
            .cookie("SESSION", issued.sessionId())
            .header(issued.csrf().headerName(), issued.csrf().token())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CsrfController.ChangeRequest("hello"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void wrongBasicPasswordStillReturns401WithValidCsrf() {
        Issued issued = issue();

        client.post().uri("/api/change")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> h.setBasicAuth("alice", "wrong"))
            .header(issued.csrf().headerName(), issued.csrf().token())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CsrfController.ChangeRequest("hello"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void formPageIncludesHiddenCsrfInput() {
        EntityExchangeResult<String> result =
            client.get().uri("/form")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).returnResult();

        String html = result.getResponseBody();
        assertNotNull(html);
        assertTrue(html.contains("name=\"_csrf\""));
        assertTrue(html.contains("type=\"hidden\""));
        assertNotNull(result.getResponseCookies().getFirst("SESSION"));
    }

    @Test
    void validCsrfFormParameterAllowsPost() {
        Issued issued = issue();

        client.post().uri("/api/form")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> h.setBasicAuth("alice", "demo123"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("message", "hello")
                .with(issued.csrf().parameterName(), issued.csrf().token()))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("form:hello");
    }

    @Test
    void formPostWithoutCsrfIsRejected() {
        Issued issued = issue();

        client.post().uri("/api/form")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> h.setBasicAuth("alice", "demo123"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("message", "hello"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void formPostWithInvalidCsrfIsRejected() {
        Issued issued = issue();

        client.post().uri("/api/form")
            .cookie("SESSION", issued.sessionId())
            .headers(h -> h.setBasicAuth("alice", "demo123"))
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData("message", "hello")
                .with(issued.csrf().parameterName(), "invalid"))
            .exchange()
            .expectStatus().isForbidden();
    }
}
```

The integration suite contains **16 `@Test` methods**. It verifies that a fresh token is issued on GET, the session cookie appears, POST succeeds when **same session**, missing/wrong CSRF yields 403, missing/wrong Basic yields 401 when CSRF is valid, and both JSON headers and form parameters are accepted by the framework.

**Why pass the cookie manually?** `WebTestClient` in this example is not configured as a cookie-persisting browser, so `issue()` extracts the `SESSION` cookie and resends it in POSTs. This proves the newly generated token was **saved in `WebSession`** and cannot be used across different sessions. In real browsers, cookies are managed by the browser under SameSite/Secure/HttpOnly policies and must never be copied between users.

### 9.2. Interpreting results properly

| Scenario | Expected result | Meaning |
| --- | --- | --- |
| GET `/csrf` | 200 + CSRF view + session cookie | Mono consumed; new token can be created/saved |
| GET `/public` | 200 | Does not force token creation on public page |
| GET `/api/profile` with valid Basic | 200 | Safe GET needs no CSRF token |
| POST JSON without CSRF, valid Basic | **403** | `CsrfWebFilter` rejects before controller |
| POST JSON wrong CSRF, valid Basic | **403** | Value mismatches expected token |
| POST JSON valid CSRF + same SESSION + valid Basic | **200** | Both CSRF and authentication succeed |
| POST JSON valid token but **missing** matching SESSION | **403** | Token does not match a new session |
| POST JSON token A, session B cookie | **403** | Tokens cannot be borrowed across sessions |
| POST JSON valid CSRF but missing Basic | **401** | CSRF does not replace authentication |
| POST JSON valid CSRF but wrong Basic password | **401** | Authentication fails |
| GET `/form` | 200 + hidden input + session cookie | Template subscribed to token publisher |
| POST form valid hidden token/cookie/Basic | **200** | Framework reads `_csrf` form parameter |
| POST form missing/invalid token | **403** | Form fails CSRF validation |

Never use `@WithMockUser` alone to conclude session-cookie/token round trips work. `mutateWith(csrf())` is handy for **controller tests unconcerned with token lifecycle**, whereas here we want to test **creating/saving/reading `Mono<CsrfToken>`**, so tests fetch real tokens from the endpoint and resend them.

## 10. Testing lazy Publisher semantics with StepVerifier

These tests illustrate a **Reactor rule**: `Mono.defer(...)` does not execute its callback until subscribed to. They **do not replace** the integration tests in Section 9, because a hand-built `Mono` does not prove `CsrfWebFilter` saved cookies/sessions.

### src/test/java/demo/csrf/CsrfMonoSemanticsTests.java

```java
package demo.csrf;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.DefaultCsrfToken;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CsrfMonoSemanticsTests {

    private static Mono<CsrfToken> deferredToken(AtomicInteger counter) {
        return Mono.defer(() -> {
            counter.incrementAndGet();
            return Mono.just(new DefaultCsrfToken(
                "X-CSRF-TOKEN", "_csrf", "example-token"));
        });
    }

    @Test
    void creatingMonoDoesNotGenerateTokenYet() {
        AtomicInteger counter = new AtomicInteger();
        Mono<CsrfToken> csrf = deferredToken(counter);

        assertEquals(0, counter.get());

        StepVerifier.create(csrf)
            .expectNextMatches(token ->
                "example-token".equals(token.getToken()))
            .verifyComplete();

        assertEquals(1, counter.get());
    }

    @Test
    void operatorChainIsAlsoLazyUntilSubscribed() {
        AtomicInteger counter = new AtomicInteger();

        Mono<String> rendered = deferredToken(counter)
            .map(token -> "value=" + token.getToken());

        assertEquals(0, counter.get());

        StepVerifier.create(rendered)
            .expectNext("value=example-token")
            .verifyComplete();

        assertEquals(1, counter.get());
    }

    @Test
    void ignoringTheReturnedMonoDoesNotExecuteSideEffect() {
        AtomicInteger generated = new AtomicInteger();
        AtomicInteger observed = new AtomicInteger();

        Mono<CsrfToken> original = deferredToken(generated);
        original.doOnNext(token -> observed.incrementAndGet());

        assertEquals(0, generated.get());
        assertEquals(0, observed.get());

        StepVerifier.create(original)
            .expectNextCount(1)
            .verifyComplete();

        assertEquals(1, generated.get());
        // doOnNext was discarded and is not part of the subscription.
        assertEquals(0, observed.get());
    }
}
```

The three tests prove:

1. Merely **declaring a `Mono`** does not execute the work inside `defer`.
2. **`map`** is also lazy; rendering occurs when the subscriber executes.
3. `doOnNext` returns a new publisher: if the returned publisher is discarded, the side effect attached to that branch never runs.

In real apps, `CsrfWebFilter` uses Spring Security's token creation/storage logic; `DefaultCsrfToken("...")` in the test is solely a **test value**, never to be sent to Spring Security as a verifiable token.

## 11. Running Maven, trying a browser, and verifying stdout/results

### 11.1. Requirements

- JDK 17+, Maven compatible with Spring Boot 3.5;
- Files placed in package `demo.csrf`;
- Localhost port free of conflicting apps if running Boot via CLI.

In the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn clean test
```

Per the example code, there are **19 tests**: 16 HTTP `WebTestClient` and 3 Reactor `StepVerifier`. With compatible dependencies installed, Maven Surefire is expected to report `Tests run: 19, Failures: 0, Errors: 0` and `BUILD SUCCESS`. This is an **expected outcome**, not a claim that the suite was executed in this environment. If errors occur, inspect `target/surefire-reports` and verify exact Spring Boot/JDK/test dependencies.

Start the app:

```bash
mvn spring-boot:run
```

Open in a browser:

```text
http://localhost:8080/form
```

The browser receives HTML containing `<input type="hidden" name="_csrf" value="...">`. At this point `Mono<CsrfToken>` was subscribed to when the HTML response was generated. On form submission to `/api/form`, the browser may prompt for HTTP Basic credentials; use demo user `alice`/`demo123` within the same tab's session cookie.

Try with curl (localhost; never use real secrets in shell history):

```bash
# Fetch JSON token along with Set-Cookie: SESSION=...
curl -i http://localhost:8080/csrf

# HTML form containing hidden CSRF input
curl -i http://localhost:8080/form

# Public GET needing no CSRF
curl -i http://localhost:8080/public

# Authenticated GET needing no CSRF
curl -i -u alice:demo123 http://localhost:8080/api/profile

# POST missing CSRF => 403 (even with valid credentials)
curl -i -u alice:demo123 -H "Content-Type: application/json" \
  -d '{"message":"hello"}' http://localhost:8080/api/change
```

In PowerShell, use `curl.exe` if `curl` is an alias. On Windows shells, JSON quoting syntax may need adjustment. To send a **valid** POST via curl, save **both** the `SESSION` cookie from GET into a cookie jar and extract the `token` field from JSON, then send the matching `headerName` + `token` on POST. A `curl -X POST` with valid Basic auth that **omits `WebSession`** will not prove CSRF works properly; the most reliable automated verification is the test suite in Section 9.

### 11.2. Why not hardcode tokens in the README?

Tokens are randomly generated and typically masked per request; there is no single "exact token stdout" across runs. The lesson shows only the response shape:

```json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "<generated-masked-token>"
}
```

The real token value is fetched by tests from `/csrf` at runtime. Do not expect two `GET /csrf` calls to return **the exact same masked token string**. Never submit the placeholder `<generated-masked-token>` in a POST; it is purely explanatory notation.

## 12. When CookieServerCsrfTokenRepository is needed for an SPA

You can configure a repository storing tokens in cookies:

```java
// Snippet inside SecurityWebFilterChain configuration:
.csrf(csrf -> csrf.csrfTokenRepository(
    CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
```

**This snippet is not part of the runnable project in Section 8.** It requires importing `org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository`. The default cookie is `XSRF-TOKEN`, and clients conventionally send `X-XSRF-TOKEN` or parameter `_csrf`. `withHttpOnlyFalse()` lets JavaScript read the cookie, increasing XSS exposure; use it only when the frontend genuinely needs direct cookie reads, otherwise keep `HttpOnly` cookies or the `WebSession` repository.

**Do not treat this as a one-line switch for SPAs:** the default XOR request handler uses masking/BREACH behavior, whereas the cookie token is normally a raw token. An SPA copying the cookie into a header may not be decoded by the default XOR resolver as a masked token. Configure a **compatible request handler** for your SPA model, test GET cookie creation, POST header submission, and token refresh after login/logout, and verify SameSite/Secure/HttpOnly/CORS. Never disable BREACH protection solely because an integration test isn't working yet.

To stay focused on "reading `Mono<CsrfToken>` and ensuring on-demand creation", the main example uses **WebSessionServerCsrfTokenRepository + handler-exposed tokens**, avoiding raw-cookie vs. masked-token confusion.

## 13. When tokens must be created or refreshed

| Scenario | What to do | What NOT to do |
| --- | --- | --- |
| First time opening a POST form | Consume `Mono<CsrfToken>` during rendering | Render empty form expecting frontend to guess token |
| SPA client preparing an unsafe request | Fetch token from same-origin endpoint / proper integration mechanism | Borrow token from another session |
| Read-only public GET page | Do not force token creation if unused | Create unnecessary sessions |
| Session just expired | Load fresh page/token and resend new cookie | Reuse old token with expired cookie |
| Login/logout changes or clears security state/token | Confirm token lifecycle, reissue when needed | Keep old token without testing |
| Cookie/session deleted | Establish new session/token | Send old header expecting to pass CSRF |
| CORS/cross-origin frontend | Design specific CORS/credentials/trusted origins | Grant wildcard access to token endpoint |
| Multi-instance WebFlux | Use a shared session store or tested sticky/session strategy | Let each node keep unsynchronized in-memory state |
| Browser keeps form open too long | Handle session timeout, guide reload/token refresh | Disable CSRF to avoid form expiry |

### 13.1. Tokens after session timeout

With the `WebSession` repository, once a session expires its expected token is gone too. POSTs using the stale page's token return 403. Good UX informs the user the session expired and reloads the page/form for a new token, rather than opening a "skip CSRF" loophole for failing requests.

### 13.2. Multiple SecurityWebFilterChain configurations

If `GET /csrf` matches chain A with CSRF enabled while `POST /api/change` matches chain B with a different repository or cookie policy, tokens can mismatch. Ensure filter chains, request matchers, repositories, and handlers **align across both token-issuing routes and token-validating routes**. Do not diagnose "Mono didn't run" when the two URLs actually hit two different security chains.

### 13.3. HTTP forms, AJAX, and multipart

- `application/x-www-form-urlencoded` forms: hidden parameter matching `CsrfToken.getParameterName()`.
- AJAX/JSON: use the header matching `CsrfToken.getHeaderName()`, rather than putting the token inside JSON and expecting the framework to find it.
- Multipart uploads: reading tokens from multipart bodies can force the server to parse/buffer uploads before validating CSRF; Spring Security WebFlux offers `tokenFromMultipartDataEnabled(true)` when genuinely needed, yet sending tokens in headers reduces processing cost and DoS risk.
- Never put CSRF tokens in URLs/query strings when avoidable, as URLs leak into browser history, referrers, and logs.

## 14. Debugging: why is the token null or why is POST still 403?

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| `exchange.getAttribute(CsrfToken.class.getName())` returns null | CSRF filter not applied, disabled, or request hit another chain | Verify chain, enable CSRF, use WebFlux packages |
| `Mono<CsrfToken>` exists, yet session has no new token | Publisher was never subscribed to | Return/compose `Mono` in response/render |
| Called `doOnNext` yet `_csrf` attribute is missing | Discarded the newly returned `Mono` | Return the transformed publisher or use `@ModelAttribute` subscribed by view |
| `block()` throws exception/hangs | Blocking on event loop | Use `map`/`flatMap` and let WebFlux subscribe |
| Form token is empty | Template failed to resolve CSRF publisher | Enable view integration or render directly from `Mono` |
| Form has token yet POST returns 403 | Wrong token, expired session, missing cookie, handler/repo mismatch | Verify same `SESSION`, matching field/header, method |
| Token fetched in session A, POST sent in session B | Expected token belongs to different session | Keep matching session cookie; don't mix users |
| Subsequent GETs return different-looking tokens | XOR masking changes exposed value | Do not compare masked strings across GETs; test round-trip |
| SPA copies `XSRF-TOKEN` cookie to header and gets 403 | Raw cookie token vs. XOR-masked resolver | Design a compatible SPA request handler and test |
| Client sends `X-XSRF-TOKEN` while default repo expects `X-CSRF-TOKEN` | Header name mismatch | Use `getHeaderName()` or align config |
| Client puts token in JSON body | Default resolver does not parse JSON fields | Send via header or form parameter |
| 403 on `POST /login` | Login CSRF is protected | Render login form with token; use `csrf()` in relevant tests |
| POST after session expiry returns 403 | Expected token is gone | Fetch new token/session |
| GET mutates data | Safe-method matcher skips CSRF | Switch to POST/PUT/DELETE and require tokens |
| Valid HTTP Basic yet POST missing token returns 403 | Authentication does not replace CSRF | Send valid token + session |
| Token logged in logs/APM | Secrets/anti-CSRF leakage | Redact `X-CSRF-TOKEN`, `_csrf`, cookies |
| Token API cached publicly | Token leaked to other clients | `Cache-Control: no-store`, CORS/cache policies |
| Test with `mockUser` and `csrf()` passes yet GET token fails | Mocks bypass generation/saving lifecycle | Round-trip `GET /csrf` + same session + POST |
| Session replaced on login/logout | Token rotated or cleared per flow | Refresh token after security state changes when needed |

### 14.1. Troubleshooting workflow in real projects

1. Distinguish 401 authentication from 403 CSRF/authorization. Never assume every 403 means missing role.
2. Check whether the token-issuing GET URL and CSRF-protected POST match the same security configuration.
3. Inspect attribute **`CsrfToken.class.getName()`** of type **`Mono<CsrfToken>`**.
4. Verify a publisher is **actually subscribed to** in the view/response.
5. Confirm the session cookie from GET appears and POST resends the same valid session.
6. Set the token matching `getHeaderName()` or `getParameterName()`; never convert masked/raw manually.
7. Check form encoding, `Content-Type`, CORS preflight, and cookie `SameSite`.
8. If the SPA uses the Cookie repo, verify XOR/raw-cookie request handler compatibility.
9. Check browser caches, session timeouts, token rotation, and multiple application instances.
10. Remove debug logs containing tokens/secrets after investigation; never leave tokens in tickets/screenshots.

## 15. Self-check questions

**Q1.** Does `CsrfWebFilter` place a `CsrfToken` object or a `Mono<CsrfToken>` on `ServerWebExchange`?  
**Answer:** Publisher `Mono<CsrfToken>`, under key `CsrfToken.class.getName()`.

**Q2.** Does merely writing `Mono<CsrfToken> t = exchange.getAttribute(...)` guarantee a new token is generated and saved?  
**Answer:** No. You must **consume/subscribe to the publisher** in the flow that needs the token.

**Q3.** In a WebFlux controller, should you use `t.block()`, `t.subscribe()`, or `return t.map(...)`?  
**Answer:** `return t.map(...)` or compose publishers; never block or manually subscribe on the request path.

**Q4.** Where is the expected CSRF token stored by default in Spring Security WebFlux?  
**Answer:** `WebSession`, via `WebSessionServerCsrfTokenRepository`.

**Q5.** Why can two tokens exposed by two GETs differ?  
**Answer:** The default XOR request handler masks the token per request to mitigate BREACH; the expected raw token in the repository may still be one stable value.

**Q6.** Can a token from session A be used with session B's cookie?  
**Answer:** No. Expected tokens are bound to sessions by the repository.

**Q7.** A user authenticated via Basic gets 403 on a POST missing a CSRF token. Is that expected?  
**Answer:** Yes. Basic verifies identity, while CSRF verifies the unsafe request carries a valid token. They are two separate checks.

**Q8.** If a view technology does not subscribe to `Mono<CsrfToken>`, what can you do?  
**Answer:** Render directly from the publisher or use `@ControllerAdvice` + `@ModelAttribute` per Spring Security, ensuring the model token is subscribed to before rendering.

**Q9.** Should CSRF tokens be forcibly created on every `GET /public`?  
**Answer:** Not necessarily; if the page needs no forms/unsafe requests, unnecessary token/session creation increases resource usage.

**Q10.** Why does copying the `XSRF-TOKEN` cookie into `X-XSRF-TOKEN` sometimes fail with the default XOR handler?  
**Answer:** Cookies normally hold raw tokens, whereas the XOR handler may expect masked request tokens. Use an SPA-compatible request handler and test compatibility.

**Q11.** Does `mutateWith(csrf())` prove a GET endpoint creates and saves tokens properly?  
**Answer:** No. It injects a valid token into mock test requests without exercising the GET token-creation + session-cookie lifecycle. Round-trip integration tests like Section 9 are needed.

**Q12.** Can a CSRF token stop XSS?  
**Answer:** No. Same-origin XSS can read/use tokens; prevent XSS, use CSP where suitable, and limit secret exposure.

**Q13.** Is CORS alone enough to stop CSRF?  
**Answer:** No. Browsers can submit some cross-origin form requests even when scripts cannot read responses. CORS and CSRF are two different mechanisms.

**Q14.** When a token expires because `WebSession` timed out, what is the right handling?  
**Answer:** Obtain a new token/session and let the user retry; never disable CSRF to suppress the error.

## 16. Production checklist and references

- [ ] Use proper **WebFlux** `CsrfToken`, `CsrfWebFilter`, `ServerWebExchange`.
- [ ] Read `Mono<CsrfToken>` via `CsrfToken.class.getName()`, never confusing it with `_csrf`.
- [ ] Form/token endpoints **compose and return the publisher** so subscription generates/saves tokens on demand.
- [ ] Never call `block()` or manual `subscribe()` on request paths.
- [ ] Do not wastefully create tokens on every public GET.
- [ ] Know which repository is active (WebSession/cookie/custom).
- [ ] Handle **masked tokens** properly with the XOR handler; never compare raw storage strings with rendered tokens.
- [ ] Form/JSON clients send the matching parameter/header and the same session cookie.
- [ ] All unsafe endpoints are protected; safe HTTP methods have zero side effects.
- [ ] Apply `Cache-Control: no-store` and CORS/origin/caching policies wherever tokens are exposed.
- [ ] Cookies/sessions use `Secure`, `HttpOnly`, and `SameSite` as appropriate; HTTPS/TLS in production.
- [ ] Never log tokens, session cookies, or credentials; defend against XSS.
- [ ] Multi-instance deployments use a consistent session store and test rotation/timeout/login/logout.
- [ ] Unit test lazy publishers and integration test **GET token -> POST same session**.
- [ ] Never disable CSRF just because tests or forms return 403.

**Summary:** Reading `Mono<CsrfToken>` from `ServerWebExchange` **is not enough**; in Spring Security WebFlux, the decisive condition for generating and saving a new token is that **the publisher must be subscribed to in the response flow needing the token**. Return the `Mono` from the controller/template so WebFlux manages subscription; clients then send the exposed token value with the right session, header/form field, and request handler mechanics.

**Official References:**

- Spring Security 6.5 – CSRF for WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security 6.5 – `CsrfWebFilter` API (new token saved on subscription): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html
- Spring Security 6.5 – `ServerCsrfTokenRepository` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRepository.html
- Spring Security 6.5 – `WebSessionServerCsrfTokenRepository`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html
- Spring Security 6.5 – `XorServerCsrfTokenRequestAttributeHandler`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html
- Spring Security 6.5 – Testing with CSRF in WebTestClient: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/csrf.html
- Spring Boot 3.5 – Testing a running server with WebTestClient: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- OWASP – Cross-Site Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
