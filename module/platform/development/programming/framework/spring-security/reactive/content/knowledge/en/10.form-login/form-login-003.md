# Creating a Custom Login Page and Configuring the Login Processing URL in Spring Security WebFlux

## Lesson Objectives

In a **Spring Security - reactive** application, Spring Security can generate a default login page. However, when building a product, we often need our own UI at a memorable URL and sometimes want the **login page display URL to differ from the URL that receives login credentials**.

This lesson belongs to the **Form Login** group. After studying it, you will:

1. Distinguish **GET login page**, **POST login processing**, **error URL**, and **post-login URL**.
2. Understand `ServerHttpSecurity.formLogin(...)`, `FormLoginSpec.loginPage(...)`, and `requiresAuthenticationMatcher(...)` in WebFlux.
3. Know exactly why `loginPage("/signin")` also configures **POST /signin** by default, and how to move it separately to **POST /auth/session**.
4. Create a custom HTML/Thymeleaf page with `username`, `password`, and **CSRF token** fields.
5. Configure public routes, authentication success/failure outcomes, and login persistence via WebSession.
6. Build a complete example with **Java 17+, Spring Boot 3.3.13, Spring WebFlux**, run it with Gradle, and test it with `WebTestClient`.
7. Recognize redirect loops, POSTing to the wrong URL, missing CSRF, Servlet API confusion, security chains not covering login, and 401/403/302 statuses.

**Scope:** **Spring Security WebFlux** form login with `SecurityWebFilterChain` and `ServerHttpSecurity`. `HttpSecurity`, `SecurityFilterChain`, `UsernamePasswordAuthenticationFilter`, and `loginProcessingUrl(...)` belong to **Servlet**; do not copy them into reactive configuration.

## 1. Four URLs with Distinct Roles

Suppose the application home needs login. We choose:

| Function | Illustrative URL | Who Handles It? | Expected Result |
| --- | --- | --- | --- |
| Custom login page | `GET /signin` | WebFlux controller returning HTML/template | 200 and form |
| Login data receiver | `POST /auth/session` | Spring Security's `AuthenticationWebFilter` | Authenticates credentials, redirects on success/failure |
| Login page on wrong password | `GET /signin?error` | Same controller at `GET /signin` | 200 and generic error message |
| Post-login page | `GET /dashboard` | Application handler, requires authenticated | 200 when a valid session exists |

Note: **`GET /signin` and `POST /auth/session` are two distinct requests**. The controller only needs to render HTML for GET; normally **do not declare `@PostMapping("/auth/session")` yourself to compare passwords**, because the form authentication filter intercepts the POST request and delegates to `ReactiveAuthenticationManager`. Adding a duplicate POST controller at the same path easily leads to incorrect behavior or never being invoked.

**Three states of a request requiring login:**

```text
GET /dashboard (unauthenticated)
    |
    +--> security entry point: 302 Location: /signin
    |
    v
GET /signin
    |
    +--> WebFlux Controller renders HTML form + CSRF token
    |
    v
POST /auth/session (username, password, _csrf)
    |
    +--> Spring Security Form AuthenticationWebFilter
            |
            +--> valid credentials: SecurityContext + session, redirect
            |
            +--> invalid credentials: redirect /signin?error
```

The exact HTTP status depends on the entry point/handlers and specific configuration. This example uses redirects because it is a browser-based web app with a form; REST APIs using Basic or Bearer typically have a different 401 challenge mechanism.

## 2. Distinguishing Default vs. Custom Configuration

### 2.1. Spring Security WebFlux Defaults

When enabling form login without choosing custom URLs:

```java
http.formLogin(Customizer.withDefaults());
```

Per the `ServerHttpSecurity.FormLoginSpec` contract, Spring Security WebFlux can provide a default page at **`GET /login`** and accept credentials at **`POST /login`**. Failure defaults to redirecting to **`/login?error`**. If you do not need to change the UI, this is a quick way to start.

### 2.2. Changing Only the Login Page

```java
http.formLogin(form -> form.loginPage("/signin"));
```

In **WebFlux**, `loginPage("/signin")` applies **simultaneously** to:

- The URL the entry point sends unauthenticated users to.
- The page the **application must render itself** at `GET /signin`.
- The default error URL `/signin?error`.
- By default, **the authentication processing URL is POST /signin**.

This is a notable difference from the Servlet DSL: in WebFlux, you do not need `loginProcessingUrl("/signin")`. Reactive `FormLoginSpec` does not provide that method. The Javadoc states clearly that setting the login page also sets the POST URL to the same path, unless you override the authentication matcher.

When customizing `loginPage`, **the auto-generated login/logout pages will no longer be provided by Spring Security under that default configuration**. You must build the login page, the `?error` state, and—if your app needs a logout confirmation page—provide that UI yourself. The logout POST filter remains a separate configuration concern.

### 2.3. Changing the POST URL Separately

If you want to keep **`GET /signin`** while submitting the form to **`POST /auth/session`**:

```java
http.formLogin(form -> form
    .loginPage("/signin")
    .requiresAuthenticationMatcher(
        new PathPatternParserServerWebExchangeMatcher(
            "/auth/session", HttpMethod.POST)));
```

- `loginPage` controls the page path and the redirect target to the login page.
- `requiresAuthenticationMatcher(...)` specifies **which request triggers the form authentication filter**. In the example, both **path** and **HTTP method POST** must match.
- The HTML form must set `action="/auth/session"` and `method="post"` accordingly.
- By default, the form converter reads `username` and `password` fields from the `application/x-www-form-urlencoded` body.
- The `/auth/session` URL itself **does not need a custom POST controller**.
- `GET /auth/session` is not a POST authentication request. If there is no GET handler and it is protected, it may result in a redirect/challenge/404 depending on the chain; it must not be treated as authenticated.

**Configuration order should be clear:** place `loginPage(...)` then `requiresAuthenticationMatcher(...)`. This is easy to follow because the POST matcher overrides the defaults applied by `loginPage`.

### 2.4. Do Not Mix Servlet and Reactive APIs

| Need | Spring Security WebFlux | Spring Security Servlet |
| --- | --- | --- |
| Configuration | `ServerHttpSecurity` | `HttpSecurity` |
| Security chain | `SecurityWebFilterChain` | `SecurityFilterChain` |
| Form login | `ServerHttpSecurity.FormLoginSpec` | `FormLoginConfigurer` |
| Login page | `loginPage("/signin")` | `loginPage("/signin")` |
| Separate POST URL | `requiresAuthenticationMatcher(ServerWebExchangeMatcher)` | `loginProcessingUrl("/auth/session")` |
| Authentication filter | `AuthenticationWebFilter` | `UsernamePasswordAuthenticationFilter` |
| Request/context | `ServerWebExchange`, Reactor Context | `HttpServletRequest`, ThreadLocal/Servlet |
| Session | `WebSession` | `HttpSession` |

If you see a guide calling `.loginProcessingUrl(...)` on `HttpSecurity`, check whether it is a **Servlet** or **WebFlux** example before copying.

## 3. Separating Application Responsibilities from Framework Responsibilities

Full flow at the filter level:

```text
Browser
  |
  | GET /signin
  v
WebFlux WebFilter chain
  |
  v
Spring Security WebFilterChainProxy
  |
  +-- selects SecurityWebFilterChain with formLogin
  +-- CSRF filter generates/attaches token to request
  +-- authorization permits GET /signin
  |
  v
@Controller GET /signin -> template signin.html
  |
  v
Browser receives HTML form

Browser
  |
  | POST /auth/session, Content-Type: application/x-www-form-urlencoded
  | username=...&password=...&_csrf=...
  v
Spring Security WebFilterChainProxy
  |
  +-- CSRF filter checks token on POST
  +-- AuthenticationWebFilter:
          |
          +-- requiresAuthenticationMatcher matches POST /auth/session
          +-- converter -> UsernamePasswordAuthenticationToken
          +-- ReactiveAuthenticationManager authenticates
          +-- if valid: save SecurityContext, success handler redirects
          +-- if invalid: failure handler redirects to /signin?error
  |
  v
Browser receives redirect -> sends new request with session cookie
```

There are three independent responsibilities:

1. **HTML page:** layout, error messages that do not leak sensitive info, form fields, CSRF token.
2. **Security configuration:** choosing which routes need authentication, which URL runs form auth, entry point/success/failure handlers, and where `SecurityContext` is stored.
3. **Identity service:** validating username/password, hashing passwords per standards, and providing roles/authorities.

Do not put password verification into Thymeleaf templates or render controllers. Never pass passwords via query parameter `GET /signin?password=...`. Never write raw passwords, Authorization headers, or session cookies to logs.

## 4. Complete Example: Java 17+, Spring Boot 3.3.13, and Thymeleaf

This example deliberately creates a **custom GET page** and a **separate POST URL**, keeps CSRF enabled, and supports login via WebSession.

The URLs:

- `GET /`: public, returns `PUBLIC_HOME`.
- `GET /signin`: HTML template with username/password/CSRF inputs.
- `POST /auth/session`: handled by Spring Security; no POST controller.
- `GET /signin?error`: template displays a generic error.
- `GET /dashboard`: requires login, returns `DASHBOARD:alice` after valid login.
- `GET /public/ping`: public endpoint used as a smoke test.

### 4.1. Project Structure

```text
webflux-custom-login/
  settings.gradle
  build.gradle
  src/
    main/
      java/example/CustomLoginApplication.java
      resources/templates/signin.html
    test/
      java/example/CustomLoginApplicationTests.java
```

Create `settings.gradle`:

```groovy
rootProject.name = 'webflux-custom-login'
```

Create `build.gradle`:

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
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-webflux` provides WebFlux/Netty; `spring-boot-starter-security` provides Spring Security; `spring-boot-starter-thymeleaf` renders HTML views. The example uses Boot BOM to manage compatible versions. Do not add `spring-boot-starter-web` (MVC/Servlet) because we want to keep the reactive runtime.

### 4.2. Application Class and Security Configuration

Create `src/main/java/example/CustomLoginApplication.java`:

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationFailureHandler;
import org.springframework.security.web.server.authentication.RedirectServerAuthenticationSuccessHandler;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.stereotype.Controller;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
@Controller
public class CustomLoginApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomLoginApplication.class, args);
    }

    @GetMapping("/")
    @ResponseBody
    public String index() {
        return "PUBLIC_HOME";
    }

    @GetMapping("/public/ping")
    @ResponseBody
    public String ping() {
        return "PONG";
    }

    @GetMapping("/dashboard")
    @ResponseBody
    public Mono<String> dashboard() {
        return ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
                .map(name -> "DASHBOARD:" + name);
    }

    @GetMapping("/signin")
    public Mono<Rendering> signin(
            ServerWebExchange exchange,
            @RequestParam(name = "error", required = false) String error) {

        Mono<CsrfToken> tokenPublisher =
                exchange.getAttribute(CsrfToken.class.getName());

        if (tokenPublisher == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF token is unavailable"));
        }

        return tokenPublisher.map(token -> Rendering.view("signin")
                .modelAttribute("csrf", token)
                .modelAttribute("loginError", error != null)
                .build());
    }

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(
                                "/", "/signin", "/public/**", "/css/**")
                        .permitAll()
                        .pathMatchers(HttpMethod.POST, "/auth/session")
                        .permitAll()
                        .anyExchange().authenticated())
                .formLogin(form -> form
                        .loginPage("/signin")
                        .requiresAuthenticationMatcher(
                                new PathPatternParserServerWebExchangeMatcher(
                                        "/auth/session", HttpMethod.POST))
                        .authenticationSuccessHandler(
                                new RedirectServerAuthenticationSuccessHandler(
                                        "/dashboard"))
                        .authenticationFailureHandler(
                                new RedirectServerAuthenticationFailureHandler(
                                        "/signin?error")))
                .httpBasic(basic -> basic.disable())
                // Keep default CSRF: POST login must send token.
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

**Section-by-section explanation:**

- `@EnableWebFluxSecurity` enables Spring Security for WebFlux. The `SecurityWebFilterChain` bean uses `ServerHttpSecurity`, not `HttpSecurity`.
- `GET /signin` is a **UI-rendering-only** controller. It retrieves the `Mono<CsrfToken>` publisher from `ServerWebExchange` under attribute name `CsrfToken.class.getName()`, then maps it to template model attribute `csrf`.
- If misconfiguration leaves the CSRF token absent, the demo throws an explicit error rather than silently rendering a form without CSRF. This helps catch security chain mistakes immediately while learning.
- `.pathMatchers("/signin").permitAll()` lets unauthenticated users access the page; omitting it can trap browsers in a redirect loop to a page that itself requires login.
- `.pathMatchers(HttpMethod.POST, "/auth/session").permitAll()` explicitly places the form processing URL in the public policy. It **does not bypass** `AuthenticationWebFilter` and does not disable CSRF. The authentication filter intercepts the request at the filter layer before application handlers.
- `.loginPage("/signin")` controls the page and login entry point. `requiresAuthenticationMatcher("/auth/session", POST)` moves the credential-receiving endpoint separately.
- `authenticationSuccessHandler` sends users to `/dashboard` when no higher-priority saved request exists; a protected request stored in the request cache may be restored first. `authenticationFailureHandler` redirects back to `/signin?error`.
- `httpBasic(...disable())` keeps browsers on the form login flow. If the application also exposes REST APIs, consider splitting `SecurityWebFilterChain`s and corresponding authentication mechanisms.
- `MapReactiveUserDetailsService` is only an in-memory user store for the demo. `{noop}learn` **must not be used in production**; store password hashes with an appropriate encoder and use HTTPS.

### 4.3. Thymeleaf Page

Create `src/main/resources/templates/signin.html`:

```html
<!doctype html>
<html lang="en" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="utf-8">
    <meta name="viewport"
          content="width=device-width, initial-scale=1">
    <title>Sign in</title>
</head>
<body>
<main>
    <h1>Sign in</h1>

    <p th:if="${loginError}" role="alert">
        Unable to sign in. Please check your credentials.
    </p>

    <form action="/auth/session" method="post">
        <label for="username">Username</label>
        <input id="username" name="username"
               type="text" autocomplete="username" required>

        <label for="password">Password</label>
        <input id="password" name="password"
               type="password" autocomplete="current-password"
               required>

        <input type="hidden"
               th:name="${csrf.parameterName}"
               th:value="${csrf.token}">

        <button type="submit">Sign in</button>
    </form>
</main>
</body>
</html>
```

Note that `<form action="/auth/session" method="post">` uses a fixed action matching the demo running at root context. When deploying under a context path or a reverse proxy with a prefix, update the URL accordingly. If using `th:action`, Thymeleaf integrates automatic CSRF hidden field insertion for POST forms; avoid configuring both auto-insertion and an unnecessary second CSRF field. In this example, we keep the plain HTML action and **provide an explicit hidden field** from the model.

**Important CSRF detail:** In Spring Security WebFlux, `CsrfWebFilter` places a `Mono<CsrfToken>` in exchange attributes. Spring Security 6.x versions use a request handler mechanism that protects against BREACH using a token processed for page rendering. This lesson uses `csrf.token` **from the request attribute intended for rendering**, rather than reading the raw token stored in the session and guessing its encoding. Never hardcode tokens, never put tokens in URLs, and never put passwords in query strings.

### 4.4. Running the Application

Requires Java 17+ and a Gradle version compatible with the Spring Boot plugin.

```bash
gradle bootRun
```

If the project has a Gradle Wrapper, use `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows.

Open a browser:

1. Visit `http://localhost:8080/signin`. The custom page should show username/password fields along with the rendered hidden CSRF token.
2. Enter **`alice` / `learn`**. The form submits **POST `/auth/session`**, Spring Security processes it, and redirects after successful authentication.
3. Visit `http://localhost:8080/dashboard`. While the browser keeps the session cookie, the response body is:

```text
DASHBOARD:alice
```

4. Log in again with a wrong password in an unauthenticated session: redirects to `/signin?error`, displaying the generic error message; no authentication succeeds.
5. Open a private window not sharing session cookies and visit `/dashboard`: the request redirects to the login page.

**You can check public GET endpoints with curl:**

```bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/signin
```

The bodies of the first two commands are `PUBLIC_HOME` and `PONG` respectively on HTTP 200. The third returns HTML containing `action="/auth/session"` and a hidden CSRF field; the token value changes per session/request and cannot be written as a constant stdout string.

**Do not assume the following command can log in:**

```bash
curl -i -X POST http://localhost:8080/auth/session \
  -d "username=alice&password=learn"
```

It typically returns **403** because it lacks a CSRF token, not because a POST controller is missing. To test the form with an HTTP client, extract the HTML/CSRF token and session cookie from GET `/signin`, then send the form POST with that exact session's token and cookie. Browsers do this automatically.

## 5. CSRF Model for a Custom Login Page

A login form must defend against **login CSRF**: an attacker may try to make a victim's browser log into an attacker-controlled account, altering session state and causing business impact.

Per Spring Security WebFlux documentation, CSRF **is enabled by default** and **POST login is protected**. The form POST should carry a token issued for the valid session/request:

```http
POST /auth/session HTTP/1.1
Content-Type: application/x-www-form-urlencoded
Cookie: SESSION=...

username=alice&password=learn&_csrf=<session-token>
```

**Proper interpretation of the fields:**

| Field | Role |
| --- | --- |
| `username` | Username read by the form authentication converter |
| `password` | Raw password just entered by the user, sent over TLS; do not log |
| `_csrf` | Anti-CSRF proof, issued and verified by the server |
| `SESSION` | Cookie helping the server locate WebSession; distinct from the CSRF token |

Do not force the token into a static string, and do not guess the `_csrf` field name if the app customized the CSRF repository/handler. The template uses `csrf.parameterName` and `csrf.token` to preserve the contract.

**Do not disable `csrf` just because you see 403 on POST login.** Check whether the token was rendered, whether the session cookie was sent back, whether the CSRF request handler is compatible, whether the POST method is right, and whether the form body has the expected media type. For browser UIs using cookies, disabling CSRF for testing convenience is a major security policy change.

In Spring Security 6.x, `XorServerCsrfTokenRequestAttributeHandler` masks the rendered token by default to reduce BREACH risk. Therefore the token string placed into HTML may differ from the value stored directly. To obtain the token expected by the verifier, use the attribute provided on the request by `CsrfWebFilter`.

### Distinguishing GET and POST Regarding CSRF

- `GET /signin` is a read operation used to display the form and token. GET is not typically protected by CSRF in the sense of requiring a token to invoke.
- `POST /auth/session` mutates authentication session state and must send the token.
- `POST /logout` also requires CSRF under default configuration. Do not use GET logout merely to make links easier to create.
- `GET /signin?error` is simply a GET page with a status parameter; it is not where passwords are received.

Never put CSRF tokens or passwords in `GET` query parameters, as URLs can appear in browser history, referrers, and proxy logs.

## 6. Authentication Success, Failure, and Session

### 6.1. On Success

The form authentication filter reads form data, builds an unauthenticated `Authentication`, and calls `ReactiveAuthenticationManager` to verify it. If valid, it sets the request's security context and can save `SecurityContext` via the default `ServerSecurityContextRepository`, which uses WebSession for form login. The success handler decides the redirect.

```text
POST /auth/session
  -> authentication succeeds
  -> save SecurityContext into WebSession
  -> response redirect (Location /dashboard or saved request)
  -> browser retains/updates SESSION cookie
  -> GET /dashboard
  -> load SecurityContext from WebSession
  -> ReactiveSecurityContextHolder has principal
  -> handler returns DASHBOARD:alice
```

**Saved request:** `RedirectServerAuthenticationSuccessHandler` typically prioritizes a login-protected request stored in `ServerRequestCache`, falling back to its constructor URL only afterwards. Thus `new RedirectServerAuthenticationSuccessHandler("/dashboard")` is not a promise that every success always goes strictly to `/dashboard` when the user started from another protected endpoint.

**Session ID:** the repository storing context in `WebSession` may rotate the session ID to prevent session fixation. When testing with an HTTP client, read the new cookie from the POST login response instead of assuming the pre-login and post-login cookies are identical.

### 6.2. On Wrong Username/Password

`RedirectServerAuthenticationFailureHandler("/signin?error")` sends the browser back to the login page and shows a generic error. Avoid overly detailed reasons like "username does not exist" or "wrong password"; keep messages non-enumerating.

`GET /signin?error` must be rendered by the same controller as `GET /signin`; the `error` query string is not a separate controller URL. In the Java snippet above, `error != null` makes the template enable `loginError`.

A redirect after invalid credentials **does not mean authentication succeeded**. To verify, send a new request to `/dashboard` in the same session: if there was never a valid login, it must still demand authentication.

### 6.3. When Session Saving or Backend Fails

Errors in the authentication manager, session store, memory exhaustion, or misconfiguration are not necessarily "wrong password". Do not use `onErrorReturn(true)`, fake a success redirect, or write sensitive data to logs. Separate the user-facing HTTP response from metrics/logs categorizing the error so operations know whether the fault lies in storage, CSRF, or credentials.

## 7. Customizing Field Names and Request Format

Under the standard form login contract, requests need **`application/x-www-form-urlencoded`** with field names **`username`** and **`password`**. Incorrect HTML example:

```html
<form action="/auth/session" method="post">
    <input name="email">
    <input name="secret" type="password">
    <button>Sign in</button>
</form>
```

Without changing the authentication converter, the filter looks for `username` and `password` and will fail to read the two fields above. Changing UI labels is separate from **submitted parameter names**. You can display the label "Email" while keeping `name="username"` if user lookup accepts email as the username.

If the domain truly requires `email`/`secret`, Spring Security WebFlux provides `ServerFormLoginAuthenticationConverter` supporting custom parameter names and `FormLoginSpec.authenticationConverter(...)`. **Illustrative** configuration snippet (not a standalone app):

```java
ServerFormLoginAuthenticationConverter converter =
        new ServerFormLoginAuthenticationConverter();

converter.setUsernameParameter("email");
converter.setPasswordParameter("secret");

http.formLogin(form -> form
        .loginPage("/signin")
        .requiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/auth/session", HttpMethod.POST))
        .authenticationConverter(converter));
```

Import `org.springframework.security.web.server.authentication.ServerFormLoginAuthenticationConverter`. Check the Javadoc for your exact version because the older class with the same name in `org.springframework.security.web.server` was deprecated. When changing the converter, the HTML form, test requests, and user lookup service must align. Do not equate "changing the POST path" with "changing field names": they are two independent configurations.

**If a client sends JSON** with `Content-Type: application/json`, the default form converter will not automatically treat it as a username/password form. Supporting JSON login requires designing an appropriate authentication converter/endpoint, handling CSRF if browsers send cookies, and configuring the matching session/token mechanism; you cannot get JSON authentication merely by changing `method="post"` or `action` in HTML.

## 8. Integrating with Multiple SecurityWebFilterChains

In Spring Security reactive, `WebFilterChainProxy` picks the **first `SecurityWebFilterChain` matching the request** in order. Each chain can have different matchers, authentication, and authorization.

Suppose an app has:

```text
Order 1: /api/**       -> Bearer token, no form
Order 2: /admin/**     -> dedicated admin mechanism
Order 3: fallback      -> form login UI
```

When a user sends **GET /signin** or **POST /auth/session**, both requests must reach the **fallback chain configured with form login**. If the UI chain only matches `/app/**`, both the GET page and POST processing fall outside its scope; the form login filter may not run even if HTML is still returned by a controller elsewhere.

### 8.1. Common Misconfiguration

```java
// INCORRECT configuration snippet if no chain covers /signin and /auth/session.
http
    .securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/app/**"))
    .formLogin(form -> form
        .loginPage("/signin")
        .requiresAuthenticationMatcher(
            new PathPatternParserServerWebExchangeMatcher(
                "/auth/session", HttpMethod.POST)));
```

Because the **chain** matcher only matches `/app/**`, `POST /auth/session` requests never reach the login filter in this chain. `requiresAuthenticationMatcher` only takes effect **inside an already-selected chain**; it cannot get the filter called if the chain was skipped at the proxy layer.

The right approach is usually simpler: place the form login chain last **covering the remainder**, or expand the UI chain's `securityMatcher` to include `/app/**`, `/signin`, `/auth/session`, and error/logout URLs together.

### 8.2. Distinguishing the Three Matchers

| Configuration | What Does It Decide? |
| --- | --- |
| `http.securityMatcher(...)` | Does this chain apply to the request? |
| `form.requiresAuthenticationMatcher(...)` | Within the selected chain, which request triggers the authentication filter? |
| `authorizeExchange(...pathMatchers(...))` | Within the selected chain, which requests are permitted/denied? |

They **do not replace one another**. A POST request can match the security chain yet miss the form filter's matcher, eventually reaching authorization or another handler. A request can match the form filter yet be blocked by CSRF before passwords are checked.

### 8.3. Separating UI Security from API Security

Form login/cookie sessions fit browser applications. APIs using Bearer tokens usually expect 401 JSON/`WWW-Authenticate` instead of HTML redirects. If APIs and UI share an undifferentiated chain, API callers may unexpectedly encounter `302 /signin`; consider a dedicated API chain.

In apps behind multiple reverse proxies, do not use unmapped external URLs as WebFlux matchers: determine the URL that `ServerWebExchange` actually sees and configure forwarded headers/context paths properly. Pay special attention to testing `/signin` and `/auth/session` when deployed under a prefix.

## 9. Testing the Configuration with WebTestClient

Tests should prove not only that "HTML renders", but also the **POST matcher**, **CSRF**, **authentication success/failure**, **session persistence**, and **re-accessing on a new request**.

### 9.1. Minimal Java Tests

Create `src/test/java/example/CustomLoginApplicationTests.java`:

```java
package example;

import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.boot.test.context.SpringBootTest.WebEnvironment.RANDOM_PORT;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(webEnvironment = RANDOM_PORT)
@AutoConfigureWebTestClient
class CustomLoginApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void publicPingIsAccessible() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("PONG");
    }

    @Test
    void customPageRendersConfiguredPostAction() {
        client.get().uri("/signin")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .value(html -> assertTrue(
                        html.contains("action=\"/auth/session\"")));
    }

    @Test
    void dashboardRequiresAuthentication() {
        client.get().uri("/dashboard")
                .exchange()
                .expectStatus().is3xxRedirection();
    }

    @Test
    void loginPostWithoutCsrfIsRejected() {
        client.post().uri("/auth/session")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData(
                        "username", "alice")
                        .with("password", "learn"))
                .exchange()
                .expectStatus().isForbidden();
    }
}
```

Run:

```bash
gradle test
```

The tests above verify the public page, form action, `/dashboard` protection, and POST CSRF. Verifying that **a successful login stays logged in on subsequent requests** requires an integration test with **real cookies and real CSRF**, or manual browser verification.

### 9.2. Multi-Request Test More Meaningful Than mockUser

To properly verify the configuration, run in sequence:

1. Send **GET /signin**, store the `SESSION` cookie, and extract the token from the hidden field named `_csrf` in HTML.
2. Send **POST /auth/session** with `Content-Type: application/x-www-form-urlencoded`, payload `username=alice&password=learn&_csrf=TOKEN`, and **the captured cookie**.
3. Observe the **3xx** response on successful authentication, capturing the **new session cookie** if the server sends one after rotating the session ID.
4. Send **GET /dashboard** with the current cookie, confirming **200 + `DASHBOARD:alice`**.
5. Send the same GET **without a cookie**, confirming it redirects to login.
6. Try POST with a wrong password but valid CSRF, confirming it redirects to **`/signin?error`** and creates no authenticated context.
7. Try POST with valid credentials but **no CSRF**, verifying it is rejected and never reaches the success handler.
8. Send GET to `/auth/session` or POST to another path, ensuring it **does not accidentally authenticate** merely due to a similar path.

**Do not use `mockUser` as proof of persistence**, because a mocked security context bypasses the very login flow and session repository you need to test. `mockUser` is useful for testing authorization in isolation, but here you must prove credentials, POST matcher, CSRF, and real cookies.

### 9.3. Result Matrix

| Scenario | Expected HTTP in Demo | Meaning |
| --- | --- | --- |
| `GET /signin` unauthenticated | 200 | Custom page renders properly |
| `GET /signin?error` | 200 | Invalid-credentials message displays |
| `GET /dashboard` no session | 302 to `/signin` | Entry point protects page |
| `POST /auth/session` no CSRF | 403 | `CsrfWebFilter` blocks |
| `POST /auth/session` valid CSRF, wrong password | 302 to `/signin?error` | Failure handler |
| `POST /auth/session` valid CSRF and password | 3xx success | Success handler, context stored |
| `GET /dashboard` after login with cookie | 200, `DASHBOARD:alice` | Session loaded |
| `GET /dashboard` without cookie | 302 to `/signin` | Does not inherit context |
| `POST /signin` when matcher only accepts `/auth/session` | Does not hit expected login filter | Proves POST URL was separated |
| `GET /auth/session` | Does not trigger form authentication | Matcher requires POST |

In a different configuration, HTTP codes from the entry point/exception handler may vary. Do not treat a 403 from missing CSRF as the same error category as a 403 from missing permissions.

## 10. Troubleshooting Common Errors

### 10.1. Redirect Loop to the Login Page

**Symptom:** Browser is sent to `/signin` and repeatedly redirects to `/signin`.

**Common cause:** `GET /signin` is not `permitAll()`, or the page lies outside the chain configuring the entry point. Inspect authorization and matchers on the security chain, not just controller routes.

### 10.2. Login Page Appears but Submitting Has No Effect

**Symptom:** Clicking submit returns 404, redirects back to login, or hits a different handler.

**Check:**

- Does `action="/auth/session"` match the actual URL seen by the server?
- Is `method="post"` right? Did JavaScript change it to GET?
- Is `requiresAuthenticationMatcher("/auth/session", POST)` attached to **the chain actually selected**?
- Is `Content-Type` set to `application/x-www-form-urlencoded`?
- Do inputs have exact names `username` and `password`?
- Is a duplicate POST controller or another security chain swallowing the request?

### 10.3. POST Always Returns 403 Despite Right Password

**Common cause:** Missing or invalid CSRF token, token from a different session, or browser did not send the session cookie. Do not conclude the authentication manager is wrong when the POST has not passed `CsrfWebFilter`.

**Check:** Rendered HTML has the hidden token; the token belongs to the current request; the form sends the right `csrf.parameterName` and keeps the cookie; reverse proxies do not alter the URL or cookie scope.

### 10.4. POST Redirects Successfully but Next Request Requires Login Again

**Cause:** Session cookie is not retained/sent, WebSession persistence failed, SecurityContext repository save/load is inconsistent, or the session was invalidated/rotated.

**Check:** Browser DevTools Network/Storage, `SESSION` cookie, redirect responses, `ServerSecurityContextRepository` for form login and context loading; HTTPS/SameSite/Cookie Path/Domain. Do not inspect only the POST response.

### 10.5. Called loginPage but GET Returns 404

When setting `loginPage("/signin")`, Spring Security **does not auto-generate your UI**. You need a controller/view or static HTML served by a router. If using Thymeleaf, check `src/main/resources/templates/signin.html`, the Thymeleaf dependency, and that the controller returns the exact view name.

### 10.6. Error Page Does Not Display

The Javadoc for `loginPage` defaults to routing errors to `/signin?error`. Your template needs to read that parameter to display a generic message, or you must configure a failure handler with the right URL. If it redirects to `/login?error` while your controller only serves `/signin`, the error notice hits the wrong page.

### 10.7. Confusing Servlet's loginProcessingUrl

Do not call `loginProcessingUrl` on `ServerHttpSecurity.FormLoginSpec`. Use `requiresAuthenticationMatcher(...)` with `PathPatternParserServerWebExchangeMatcher` (HTTP POST) in WebFlux. Do not switch to `HttpSecurity` just to use a familiar method name.

### 10.8. Manually Checking Passwords in a Controller

Do not write `@PostMapping("/auth/session")` to compare passwords manually, issue ad-hoc cookies, or use `NoOpPasswordEncoder`. Spring Security already provides converters, managers, password encoders, sessions, CSRF, and handlers. If you have special requirements, extend at the proper abstraction.

### 10.9. Login Page Affected by an API Chain

If an API or catch-all chain has higher precedence (`@Order`) and a matcher covering `/signin` or `/auth/session`, requests may hit Basic/Bearer instead of form login. Check security chain ordering and both URLs; **you cannot tell just by counting beans**.

### 10.10. CSS, Cookie, and Sub-Prefix Deployment Issues

A custom page may load HTML while `/css/**` CSS is blocked, or the form action uses the wrong path when running behind a reverse proxy. Allow access to **only the required login assets**, normalize context path/forwarded headers, and test the real paths. Never open `anyExchange().permitAll()` to "fix" CSS 403s.

### 10.11. Wrong Language/Encoding Displayed in HTML

Include `<meta charset="utf-8">`, check UTF-8 template encoding, and response Content-Type. Error messages must be escaped by Thymeleaf when containing dynamic data; avoid rendering raw HTML from the `error` query string.

## 11. Securing the Login Form for Production

This lesson focuses on **routing and form handling**, yet login design also requires many operational safeguards:

- **HTTPS** for all form actions, redirects, and session cookies. Never transmit passwords over plain HTTP.
- **Appropriate password hashing** (BCrypt/Argon2/PBKDF2/scrypt) with a work factor benchmarked on real infrastructure; `{noop}` is demo-only.
- **CSRF** enabled for cookie/session-based form login; never disable it just because of a 403 in tests.
- **Rate limiting**, credential-stuffing and enumeration defenses, and auditing login success/failure without logging passwords or session IDs.
- **Session fixation protection**, session timeouts, appropriate `Secure`/`HttpOnly`/`SameSite` cookies, and complete logout handling.
- **Prevent open redirects:** never trust user-supplied `next`/`redirect` parameters; if customizing the success handler, redirect only to allowlisted URLs or validated internal paths.
- **CORS/cookie policy:** cross-origin requests and SameSite can affect the login flow; never open wildcard CORS with credentials or disable cookie policies recklessly.
- **Accessibility:** labels bound to inputs, error notices using `role="alert"`, appropriate autocomplete attributes, and keyboard navigation support.
- **Never leak credentials:** never put usernames/passwords or tokens in URLs, analytics, crash reports, or debugging output.
- **Do not rely on secret URLs:** renaming `/login` to `/secret-login` does not substitute for strong authentication or attack mitigation.

These concerns are not automatically solved by `.loginPage(...)` or changing the POST URL. Proper routing is a prerequisite for form login to work; securing the login operation also requires sound policy and operations.

## 12. Self-Check Questions

**Q1.** In WebFlux configured only with `formLogin(form -> form.loginPage("/signin"))`, where must the form POST by default?  
**A:** `POST /signin`. WebFlux's `loginPage` sets the login page, error URL, and default authentication endpoint to the same path; to POST elsewhere you must override the matcher.

**Q2.** To get `GET /signin` and `POST /auth/session`, which APIs are used?  
**A:** `loginPage("/signin")` combined with `requiresAuthenticationMatcher(new PathPatternParserServerWebExchangeMatcher("/auth/session", HttpMethod.POST))`.

**Q3.** Do you need to write `@PostMapping("/auth/session")` yourself in a controller?  
**A:** No, when Spring Security's form authentication filter is configured and matches the request. The controller renders the GET page, while the filter handles POST credentials.

**Q4.** Why must `GET /signin` be accessible while unauthenticated?  
**A:** If the login page itself required being logged in, browsers could enter a redirect loop when visiting protected endpoints.

**Q5.** A form submits the right `username` and `password`, but has no CSRF token; can it log in?  
**A:** With CSRF enabled by default in WebFlux, the POST is usually rejected with 403 before checking the password.

**Q6.** Does `GET /signin?error` require a separate controller?  
**A:** Not required. A single GET handler for `/signin` reading the `error` query parameter and enabling a generic message in the template is sufficient.

**Q7.** Why is changing `action="/auth/session"` in HTML alone insufficient?  
**A:** `AuthenticationWebFilter` must have `requiresAuthenticationMatcher` matching the exact POST URL; otherwise the request will not trigger authentication as intended.

**Q8.** When multiple `SecurityWebFilterChain`s exist, does the form filter's matcher pull requests into the UI chain?  
**A:** No. The proxy selects the security chain first, and internal filters check their matchers afterwards. Both the GET page and POST processing must belong to the chain with form login.

**Q9.** Does a successful redirect already prove session persistence?  
**A:** No. You must send a new request with the current cookie and confirm the principal is loaded and protected endpoints allow access.

**Q10.** Is `loginProcessingUrl(...)` a method on reactive `ServerHttpSecurity.FormLoginSpec`?  
**A:** No. That is part of the Servlet DSL. Reactive uses `requiresAuthenticationMatcher(...)` to change the POST processing condition.

**Remember:** In WebFlux, **`loginPage` determines the display page and default POST target**, while **`requiresAuthenticationMatcher` determines the exact request processed by the form authentication filter**. To separate **GET /signin** and **POST /auth/session** safely, ensure the route/chain is right, input names match, CSRF is complete, success/failure redirects are sound, and session persistence is verified with a new request.

## References

- [Spring Security 6.5 — ServerHttpSecurity.FormLoginSpec API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.FormLoginSpec.html): `loginPage`, `requiresAuthenticationMatcher`, `authenticationFailureHandler`, and `authenticationSuccessHandler`.
- [Spring Security 6.5 — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html): configuring WebFlux form login, security chains, and authorization.
- [Spring Security — CSRF Protection in WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): `Mono<CsrfToken>` in ServerWebExchange, rendered tokens, and login/logout CSRF.
- [Spring Security — PathPatternParserServerWebExchangeMatcher API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/util/matcher/PathPatternParserServerWebExchangeMatcher.html): path + HTTP method matcher.
- [Spring Security — RedirectServerAuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationSuccessHandler.html): post-login redirect and saved request.
- [Spring Security — RedirectServerAuthenticationFailureHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/authentication/RedirectServerAuthenticationFailureHandler.html): redirect on invalid credentials.
- [Spring Security — ServerFormLoginAuthenticationConverter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/authentication/ServerFormLoginAuthenticationConverter.html): converting form fields into Authentication.
- [Spring Security — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `SecurityWebFilterChain` and WebFlux setup.
