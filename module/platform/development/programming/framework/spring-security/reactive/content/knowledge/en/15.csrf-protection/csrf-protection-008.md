# Passing Tokens via Forms, HTTP Headers, and Async Requests in Spring Security Reactive

## 1. Objectives and Context

A **Spring WebFlux / Spring Security reactive** application has an HTML UI, session-cookie login, POST forms, and `fetch()` calls sending JSON. When browsers can automatically attach login cookies to requests, an external web page may abuse that to submit actions against the user's intent. **Cross-Site Request Forgery (CSRF)** is the attack class CSRF tokens are designed to mitigate.

This lesson focuses on how to **obtain, pass, and validate CSRF tokens** when using:

1. HTML forms with hidden inputs.
2. HTTP headers such as `X-CSRF-TOKEN` in `fetch()`/XMLHttpRequest.
3. A `GET /csrf` endpoint issuing tokens to SPAs or async clients.
4. The default `WebSessionServerCsrfTokenRepository` and the `CookieServerCsrfTokenRepository` option.
5. Default XOR masking/BREACH behavior since Spring Security 6.0, affecting tokens in cookies, forms, and headers.

You will build a **Java 17+** Spring Boot WebFlux example to observe HTTP 200 successes, HTTP 403 CSRF failures, and errors after session expiration. A CSRF token is **not** an access token or proof of login; authorization must still be checked independently.

## 2. Why must tokens travel outside cookies?

Suppose a user is logged into `https://shop.example` and the browser holds a session cookie. Another website creates a form submitting POST to `https://shop.example/account/change-email`. Depending on SameSite/cookie policies and context, the browser may auto-send the cookie. If the server trusts "has a cookie = owner intended the POST", forged requests can slip through.

Under the **synchronizer token pattern**, the server stores an **expected token** bound to the session; a legitimate server-rendered page supplies the client with a **submitted token** in a channel the browser does not auto-send like cookies, such as a hidden field or custom header. On POST, `CsrfWebFilter` verifies the submitted token before letting the handler run.

~~~text
Browser                         Spring WebFlux
   |                                   |
   | GET /demo                         |
   |---------------------------------->|
   |                                   | CsrfWebFilter + repository
   | HTML with token in hidden/meta    |
   |<----------------------------------|
   |                                   |
   | POST form /form/save               |
   | Session cookie + _csrf field      |
   |---------------------------------->|
   |                                   | compare with expected token
   |           200 / 403               |
   |<----------------------------------|
   |                                   |
   | POST fetch /api/notes             |
   | Session cookie + X-CSRF-TOKEN     |
   |---------------------------------->|
   |                                   | compare with expected token
   |         JSON / 403                |
   |<----------------------------------|
~~~

You cannot simply **store a token in a cookie and trust that cookie alone**. In double-submit/cookie-repository patterns, the client must **read** or receive the token via an appropriate channel and **send a copy in a header/parameter**, while the server uses the matching configured request handler and token format.

### 2.1. Which HTTP methods require CSRF?

By default, Spring Security WebFlux checks CSRF on **unsafe** methods. Common table:

| Method | Default CSRF | Proper usage |
| --- | --- | --- |
| `GET` | No | Read-only; may be used to fetch tokens |
| `HEAD`, `OPTIONS`, `TRACE` | No | Must not mutate state |
| `POST` | **Yes** | Login, logout, writing data |
| `PUT`, `PATCH` | **Yes** | Updating data |
| `DELETE` | **Yes** | Deleting data |

Never use GET to delete records, transfer funds, or perform real logouts. If GET has side effects, attackers can abuse the URL because the default CSRF matcher does not block safe methods. **Fix HTTP semantics** instead of expecting `CsrfWebFilter` to guess business actions.

### 2.2. CSRF vs. 401/403 from authentication/authorization

| Request | Typical outcome | Mechanism |
| --- | --- | --- |
| POST with login cookie but **no token** | **403 Forbidden** | `CsrfWebFilter` |
| POST with valid token, unauthenticated user, protected URL | Login redirect or 401 | Authentication/authorization |
| POST with valid token and user, missing role | **403** | Authorization |
| Private GET without credentials | Login redirect or 401 | Entry point |
| POST with valid token, user, and role | Controller executes | Business logic |

A request with a valid CSRF token **can still be denied for lacking permissions**. A 403 response **does not by itself prove CSRF is missing**. Separate logs and tests for CSRF failures vs. role failures.

## 3. WebFlux APIs to remember

| API | Role |
| --- | --- |
| `CsrfWebFilter` | Reactive filter enforcing CSRF |
| `CsrfToken` | `getToken()`, `getHeaderName()`, `getParameterName()` |
| `ServerCsrfTokenRepository` | Generates, saves, and loads expected tokens |
| `WebSessionServerCsrfTokenRepository` | **Default** store, keeps token in `WebSession` |
| `CookieServerCsrfTokenRepository` | Cookie token store; XSRF convention |
| `ServerCsrfTokenRequestHandler` | Exposes/resolves submitted tokens |
| `XorServerCsrfTokenRequestAttributeHandler` | Masks tokens against BREACH, default since 6.0 |
| `ServerCsrfTokenRequestAttributeHandler` | Request handler without XOR |
| `ServerWebExchange` | Request attributes, cookies, headers, response |
| `Mono<CsrfToken>` | Publisher fetching/exposing CSRF token in reactive chain |
| `ServerHttpSecurity.csrf(...)` | Configures CSRF on `SecurityWebFilterChain` |

Per official documentation, Spring Security 7.1 stores expected CSRF tokens in **WebSession** by default, and `CsrfWebFilter` exposes a `Mono<CsrfToken>` via an exchange attribute keyed by `CsrfToken.class.getName()`. Since **Spring Security 6.0**, the default request handler has been `XorServerCsrfTokenRequestAttributeHandler` to mitigate BREACH response-compression risk. In **5.8**, the previous default handler was `ServerCsrfTokenRequestAttributeHandler`.

### 3.1. Reading tokens without blocking the event loop

Inside a reactive controller receiving `ServerWebExchange exchange`:

~~~java
Mono<CsrfToken> csrfToken =
        exchange.getAttribute(CsrfToken.class.getName());

if (csrfToken == null) {
    return Mono.error(new IllegalStateException(
            "CSRF request attribute unavailable"));
}
return csrfToken.map(CsrfToken::getToken);
~~~

This is an **illustrative snippet placed inside a method returning `Mono<String>`**, not a standalone Java class. Never call `csrfToken.block()` or manual `subscribe()` in a controller. Spring WebFlux subscribes when you **return** the publisher; when a new token is needed, the repository generates/saves it via that subscription.

Distinguish carefully:

- `CsrfToken.class.getName()`: **exchange attribute key**, full reactive class name.
- `token.getParameterName()`: HTML field name (usually `_csrf`).
- `token.getHeaderName()`: request header name (usually `X-CSRF-TOKEN` with WebSession repo).
- `token.getToken()`: submitted token value exposed by the handler; **do not assume it equals a raw cookie**.

### 3.2. Lazy tokens are not a bug

CSRF tokens are exposed via `Mono<CsrfToken>` so they are loaded/generated only when genuinely needed. A GET request not rendering a form need not touch the repository. If you obtain the publisher without returning/subscribing to it, the endpoint may never actually issue a new token or save an expected token. Conversely, forcing token subscriptions on **every request** via global advice can increase session churn.

## 4. HTML forms: sending tokens via hidden inputs

For form-urlencoded POSTs, the final form sent to the browser should look like:

~~~html
<form method="post" action="/form/save">
  <label>
    Content
    <input name="message" value="from-form">
  </label>
  <input type="hidden" name="_csrf" value="SERVER_RENDERED_TOKEN">
  <button type="submit">Save</button>
</form>
~~~

`SERVER_RENDERED_TOKEN` is illustrative only; in the app use the actual value from `CsrfToken.getToken()` for the current request/session. If the token parameter name is customized, use `getParameterName()` instead of hardcoding `_csrf`.

In Spring Security 6+/7+ with default XOR, the token in the form **can be a masked value**, differing from the raw expected token stored in `WebSession`; this is intentional. The filter resolves/unmasks it before comparing.

### 4.1. Forms rendered by Thymeleaf

Spring Security integrates with `RequestDataValueProcessor` so Thymeleaf can automatically insert hidden CSRF inputs when rendering POST forms, provided the token/model attribute is exposed properly:

~~~html
<form th:action="@{/form/save}" method="post">
  <input name="message" value="from-thymeleaf">
  <button type="submit">Save</button>
</form>
~~~

This is a **Thymeleaf fragment**, requiring the Spring Boot Thymeleaf starter and view engine. Do not assume arbitrary HTML from `@RestController` or other template engines auto-injects inputs. If a view engine does not automatically handle `Mono<CsrfToken>`, reactive docs recommend `@ControllerAdvice` to expose `CsrfToken` as a model attribute for views.

### 4.2. Forms built with JavaScript

You can use DOM APIs instead of HTML string concatenation:

~~~javascript
const form = document.querySelector("#edit-form");
const csrf = document.querySelector('meta[name="_csrf"]').content;
const hidden = document.createElement("input");
hidden.type = "hidden";
hidden.name = "_csrf";
hidden.value = csrf;
form.appendChild(hidden);
~~~

This snippet assumes the HTML already contains `form#edit-form` and the server-rendered `_csrf` meta tag. When the field name is non-default, pass `parameterName` from the server as well and use that name. Never put tokens in query parameters or URL paths.

## 5. HTTP headers: sending tokens when submitting JSON or AJAX

With `Content-Type: application/json`, Spring Security by default **does not parse a `_csrf` field inside the JSON business body for CSRF checks** like a form parameter. Pass the submitted token in the header given by `getHeaderName()`.

The server can render meta tags:

~~~html
<meta name="_csrf" content="SERVER_RENDERED_TOKEN">
<meta name="_csrf_header" content="X-CSRF-TOKEN">
~~~

JavaScript reads the meta tags and adds the header to `fetch()`:

~~~javascript
const token = document.querySelector('meta[name="_csrf"]').content;
const header = document.querySelector('meta[name="_csrf_header"]').content;

async function createNote(message) {
  const response = await fetch("/api/notes", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [header]: token
    },
    body: JSON.stringify({message})
  });
  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }
  return response.json();
}
~~~

**`credentials: "same-origin"` sends the session cookie for same-origin requests**, yet **does not automatically insert the CSRF header**: the `[header]: token` line does that. The CSRF token does not go into `Authorization` in place of a JWT and is not an authorization key.

Another request from a same-origin tab/page can reuse the same submitted token as long as the expected token in `WebSession` has not been reset. XOR masking **does not mean tokens are single-use per POST**; it masks the rendered value against BREACH while validation still checks against the expected token.

### 5.1. XMLHttpRequest

With the classic API:

~~~javascript
const xhr = new XMLHttpRequest();
xhr.open("POST", "/api/notes");
xhr.setRequestHeader("Content-Type", "application/json");
xhr.setRequestHeader(header, token);
xhr.onload = () => console.log("status", xhr.status);
xhr.send(JSON.stringify({message: "xhr"}));
~~~

This uses `header` and `token` already extracted from the page. For cross-origin requests, `withCredentials` and CORS policies must be designed separately; never assume custom headers are automatically permitted by CORS.

### 5.2. Using Angular, Axios, jQuery

Some libraries support the **`XSRF-TOKEN` cookie -> `X-XSRF-TOKEN` header** convention, yet the server must have a repository and request handler compatible with **raw vs. masked** tokens. Never claim enabling a frontend flag alone suffices; verify where tokens are stored, how they are masked on exposure, and how they are resolved on submission.

For apps using the default `WebSession` repository, **rendering masked tokens into meta tags or returning them from `GET /csrf`** is usually easier to keep aligned with defaults than forcing the frontend to read raw cookies.

## 6. Issuing tokens via GET /csrf for async clients

If the frontend is an SPA, it can fetch tokens via a GET endpoint returning JSON:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "TOKEN_FROM_SERVER"
}
~~~

**`TOKEN_FROM_SERVER` is an illustrative placeholder.** Real values must be server-issued and bound to the appropriate session/request. Responses should carry `Cache-Control: no-store` and never allow external-origin websites to read them via overly permissive CORS.

Workflow:

~~~text
Logged-in client:
GET /csrf + session cookie
  -> receives token, headerName, parameterName
POST /api/notes + session cookie
  + headerName: token + JSON body
  -> CsrfWebFilter validates
  -> controller runs only if CSRF/auth/role match

After logout / new login / session timeout:
GET /csrf or page reload
  -> use fresh token with new session
~~~

A successful `GET /csrf` **does not authenticate the client**. If the endpoint is protected by `authenticated()`, the client must have a login session before fetching the token. If the endpoint is public, evaluate who may read the response and how cookies are issued.

Async clients can do:

~~~javascript
async function loadCsrf() {
  const response = await fetch("/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });
  if (!response.ok) {
    throw new Error("Cannot load CSRF: " + response.status);
  }
  return response.json();
}

async function saveAsync(message) {
  const csrf = await loadCsrf();
  const response = await fetch("/api/notes", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({message})
  });
  if (!response.ok) {
    throw new Error("Cannot save: " + response.status);
  }
  return response.json();
}
~~~

This code fetches a token before each POST for simplicity. Real apps can cache the token **in page memory** and refresh on login/logout or session changes. Never retry infinitely just because of status 403; the user may lack a role or another policy may be denying the request.

## 7. Repositories and the difference between raw and masked tokens

### 7.1. Default WebSessionServerCsrfTokenRepository

Spring Security WebFlux stores the expected CSRF token in `WebSession` by default, while `CsrfWebFilter` exposes `Mono<CsrfToken>` on the request. With session login cookies, the server locates the expected token from the request's `WebSession`.

Pros: expected tokens stay server-side without requiring JavaScript to read raw CSRF cookies. When rendered into forms/meta tags, Spring Security handles masking and verification per configuration.

Limitation: when the session expires or is invalidated, old submitted tokens no longer match. A token matching the active session must be fetched before the next POST.

### 7.2. CookieServerCsrfTokenRepository

An SPA may deliberately use a CSRF cookie named `XSRF-TOKEN` and send a copy in the `X-XSRF-TOKEN` header. This convention is supported by `CookieServerCsrfTokenRepository`:

~~~java
// Snippet inside SecurityWebFilterChain configuration method:
.csrf(csrf -> csrf
        .csrfTokenRepository(
                CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
~~~

`withHttpOnlyFalse()` makes the **CSRF cookie** directly readable by JavaScript. **It does not mean authentication/session cookies lose `HttpOnly`.** If reading the cookie is unnecessary, use the regular constructor with `HttpOnly` or keep the default `WebSession` repository. Exposing tokens to JS reads requires evaluating XSS/CORS/cookie policies.

Default names:

| Location | Value |
| --- | --- |
| Cookie | `XSRF-TOKEN` |
| Request header | `X-XSRF-TOKEN` |
| Form parameter | `_csrf` |

### 7.3. XOR masking: common cause of 403 when "cookie equals header"

Since Spring Security **6.0**, the default `XorServerCsrfTokenRequestAttributeHandler` masks tokens when exposed on requests and unmasks tokens submitted in headers/forms. The `XSRF-TOKEN` cookie typically holds the **raw expected token**; if the client reads the raw token from the cookie and copies it verbatim into the `X-XSRF-TOKEN` header, the default XOR handler may fail to decode it, causing **403**.

In the main example of this lesson, we **keep default XOR** and submit tokens **from exchange attributes/page/GET /csrf**, avoiding raw vs. masked guesswork.

If you must keep the raw-cookie reading pattern, you can configure a non-XOR handler:

~~~java
// Optional approach, not used in the main demo.
.csrf(csrf -> csrf
        .csrfTokenRepository(
                CookieServerCsrfTokenRepository.withHttpOnlyFalse())
        .csrfTokenRequestHandler(
                new ServerCsrfTokenRequestAttributeHandler()))
~~~

**Security trade-off:** replacing XOR with `ServerCsrfTokenRequestAttributeHandler` **disables BREACH masking protection**. Never do this reflexively over a 403; evaluate the threat model or implement a custom request handler combining masked rendering with raw header resolution per API and test thoroughly.

Never mix Servlet's `CookieCsrfTokenRepository` with reactive `CookieServerCsrfTokenRepository`.

### 7.4. Cookies are necessary but not sufficient

The `SESSION` cookie identifies the user in a login session. The `XSRF-TOKEN` cookie stores CSRF state (when using the cookie repo). The `X-XSRF-TOKEN` or `X-CSRF-TOKEN` header is where **the client actively presents the token**. Having both cookies without sending the matching parameter/header still causes unsafe requests to return 403.

## 8. Complete example: forms, fetch, and /csrf on Spring Boot WebFlux

We will build a **Spring Boot 4.1.2**, **Java 17+**, Spring Reactive Web, and Spring Security app:

- `GET /` public.
- `GET /login` provided by Spring Security by default.
- `GET /demo` after login: HTML with a hidden form token and meta tokens for JS.
- `GET /csrf` after login: JSON token for async clients.
- `POST /form/save`: form-urlencoded with CSRF token in hidden field.
- `POST /api/notes`: JSON with CSRF token in HTTP header.

We **do not use the optional cookie CSRF repository**, **do not disable XOR**, and **do not disable CSRF**. Form login is purely a way to establish a browser session for practice, not a production identity service.

### 8.1. Maven configuration

Generate a project from [Spring Initializr](https://start.spring.io/) with Java 17+, Maven, group `com.example`, artifact `reactive-csrf-demo`; select **Spring Reactive Web** and **Spring Security**. `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>reactive-csrf-demo</artifactId>
  <version>0.0.1-SNAPSHOT</version>
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
~~~

Let the Boot BOM manage Spring Security, Framework, Reactor, and Netty versions. Never add `spring-boot-starter-web`/Servlet to a WebFlux project.

### 8.2. Complete Java source

Create `src/main/java/com/example/csrfdemo/ReactiveCsrfDemoApplication.java`:

~~~java
package com.example.csrfdemo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class ReactiveCsrfDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveCsrfDemoApplication.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
                .password("{noop}learn123")
                .roles("USER")
                .build();
        return new MapReactiveUserDetailsService(learner);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        return http
                .authorizeExchange(routes -> routes
                        .pathMatchers("/").permitAll()
                        .anyExchange().authenticated())
                .formLogin(Customizer.withDefaults())
                .httpBasic(basic -> basic.disable())
                // Default WebFlux CSRF remains enabled.
                .build();
    }

    private static Mono<CsrfToken> requireCsrf(
            ServerWebExchange exchange) {
        Mono<CsrfToken> publisher =
                exchange.getAttribute(CsrfToken.class.getName());
        if (publisher == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF attribute unavailable"));
        }
        return publisher;
    }

    public record NoteRequest(String message) { }

    @RestController
    static class DemoController {

        @GetMapping(value = "/", produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> index() {
            return Mono.just("""
                <!doctype html>
                <html lang="en">
                <head><meta charset="UTF-8"><title>CSRF demo</title></head>
                <body>
                  <h1>CSRF in Spring WebFlux</h1>
                  <a href="/demo">Go to test page</a>
                </body></html>
                """);
        }

        @GetMapping(value = "/demo",
                produces = MediaType.TEXT_HTML_VALUE)
        Mono<String> demo(ServerWebExchange exchange) {
            return requireCsrf(exchange).map(token -> {
                exchange.getResponse().getHeaders()
                        .setCacheControl("no-store");
                return """
                    <!doctype html>
                    <html lang="en">
                    <head>
                      <meta charset="UTF-8">
                      <title>CSRF form and fetch</title>
                      <meta name="_csrf" content="%s">
                      <meta name="_csrf_header" content="%s">
                    </head>
                    <body>
                      <h1>Form &amp; async JSON</h1>
                      <form method="post" action="/form/save">
                        <input name="message" value="from-form">
                        <input type="hidden" name="%s" value="%s">
                        <button type="submit">Submit form</button>
                      </form>
                      <button id="send" type="button">
                        Submit fetch()
                      </button>
                      <pre id="result"></pre>

                      <script>
                        const token = document.querySelector(
                          'meta[name="_csrf"]').content;
                        const header = document.querySelector(
                          'meta[name="_csrf_header"]').content;
                        document.getElementById('send')
                          .addEventListener('click', async () => {
                            const output = document.getElementById('result');
                            try {
                              const response = await fetch('/api/notes', {
                                method: 'POST',
                                credentials: 'same-origin',
                                headers: {
                                  'Content-Type': 'application/json',
                                  [header]: token
                                },
                                body: JSON.stringify({
                                  message: 'from-fetch'
                                })
                              });
                              output.textContent = response.status + ' ' +
                                  await response.text();
                            } catch (error) {
                              output.textContent = 'Network/CORS error';
                            }
                          });
                      </script>
                    </body></html>
                    """.formatted(token.getToken(),
                            token.getHeaderName(),
                            token.getParameterName(),
                            token.getToken());
            });
        }

        @GetMapping(value = "/csrf",
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
            exchange.getResponse().getHeaders()
                    .setCacheControl("no-store");
            return requireCsrf(exchange).map(token -> Map.of(
                    "headerName", token.getHeaderName(),
                    "parameterName", token.getParameterName(),
                    "token", token.getToken()));
        }

        @PostMapping(value = "/form/save",
                consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
                produces = MediaType.TEXT_PLAIN_VALUE)
        Mono<String> formSave(ServerWebExchange exchange) {
            return exchange.getFormData()
                    .map(form -> "FORM_OK:" +
                            form.getFirst("message"));
        }

        @PostMapping(value = "/api/notes",
                consumes = MediaType.APPLICATION_JSON_VALUE,
                produces = MediaType.APPLICATION_JSON_VALUE)
        Mono<Map<String, String>> apiNotes(
                @RequestBody NoteRequest input) {
            return Mono.just(Map.of(
                    "status", "API_OK",
                    "message", input.message()));
        }
    }
}
~~~

### 8.3. Code walkthrough

- `@EnableWebFluxSecurity` + `SecurityWebFilterChain` use the reactive API.
- `formLogin(withDefaults())` generates the default login page and accepts login POSTs with valid CSRF; `httpBasic(disable)` keeps browsers from showing a native Basic prompt.
- `/` is public; `/demo`, `/csrf`, and both POSTs are protected by `authenticated()`. CSRF is an **additional** verification layer, not a replacement for authorization.
- `requireCsrf(...)` reads `Mono<CsrfToken>` from the exchange attribute and **returns the publisher**, never blocking.
- `GET /demo` subscribes to the token inside `map` and renders the hidden input via `getParameterName()/getToken()` and meta tags via `getToken()/getHeaderName()`.
- `POST /form/save` uses `ServerWebExchange.getFormData()`. In WebFlux, `@RequestParam` primarily binds query params rather than assuming Spring MVC form-body behavior everywhere.
- `POST /api/notes` uses `@RequestBody NoteRequest` to parse JSON via WebFlux codecs; it does not read CSRF tokens from the JSON business body.
- `GET /csrf` exposes the token as JSON for async clients; responses carry `Cache-Control: no-store`.
- The demo only replies with text/JSON for observation; nothing is saved to a database.
- `{noop}`/plaintext passwords in source are strictly for local use. Production must use strong password encoders, HTTPS, rate limiting, real identity sources, and proper session/cookie mechanisms.
- The code uses Java text blocks, requiring Java 17+. File paths and public class names must match packages.

**Masking note:** even when the token in meta/hidden inputs differs from the expected token string in the server repository, always submit the **exposed** value. Never trim, decode, or swap it with raw cookies.

### 8.4. Running the demo

In the directory containing `pom.xml`:

~~~bash
./mvnw clean package
./mvnw spring-boot:run
~~~

On Windows use `.\mvnw.cmd clean package` and `.\mvnw.cmd spring-boot:run`; if no Maven wrapper is present, use `mvn` with a compatible Maven version.

Visit `http://localhost:8080/`, click the `/demo` link, and you will be redirected to `/login`. Sign in with:

~~~text
Username: learner
Password: learn123
~~~

After logging in, open `http://localhost:8080/demo` if not redirected there automatically. The page shows two submission methods:

1. Click **Submit form**: the browser POSTs form-urlencoded with hidden `_csrf`; expect HTTP 200 and body `FORM_OK:from-form`.
2. Click **Submit fetch()**: JavaScript sends JSON and the header from meta; `<pre>` shows status 200 and JSON with `"status":"API_OK"`.

Right after logging in, **reload the demo page** to ensure the rendered token belongs to the active session. A token fetched from a pre-login session may have been reset.

### 8.5. Testing missing and invalid tokens

Use DevTools Network to inspect `POST /api/notes`, checking **Request Headers** and session cookies. Removing the line that adds `[header]: token` and reloading in a test environment causes the POST to return **403** without executing `apiNotes`. Similarly if the token is replaced with an invalid string.

Checking the HTTP status alone is not enough to prove the controller ran. Good tests also inspect business side effects/test logs and distinguish CSRF 403 from missing-role 403.

## 9. Testing with curl and a cookie jar

`curl` does not maintain browser sessions automatically. Use `-c` and `-b` to retain the right cookies when fetching and submitting tokens. The token commands below require substituting the **actual token returned by the server**, never the placeholder string.

### 9.1. Fetch the login form and its token

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/login
~~~

Inspect the `GET /login` HTML to grab the hidden `_csrf` input of the default login form. Never copy only the session cookie while omitting the token.

### 9.2. Log in with the form token

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  --data-urlencode "username=learner" \
  --data-urlencode "password=learn123" \
  --data-urlencode "_csrf=LOGIN_FORM_TOKEN" \
  http://localhost:8080/login
~~~

`LOGIN_FORM_TOKEN` must be replaced with the hidden field from the same cookie jar. On success, the form-login flow typically returns a **302 redirect**; do not expect POST login to return JSON 200.

### 9.3. Fetch a new token after login

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf
~~~

The response body contains `headerName`, `parameterName`, and `token`. The token may have changed compared to pre-login. Use the **new token** for subsequent requests, and never share it in public chats/logs.

### 9.4. POST JSON + CSRF header

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: TOKEN_FROM_CSRF_RESPONSE" \
  -d '{"message":"from-curl-json"}' \
  http://localhost:8080/api/notes
~~~

Expect HTTP **200** and JSON containing `"status":"API_OK"` and `"message":"from-curl-json"`. JSON key order may vary since `Map.of` does not guarantee serializer order.

### 9.5. POST form-urlencoded + CSRF parameter

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  --data-urlencode "message=from-curl-form" \
  --data-urlencode "_csrf=TOKEN_FROM_CSRF_RESPONSE" \
  http://localhost:8080/form/save
~~~

Expect HTTP **200** with body `FORM_OK:from-curl-form`. This is equivalent to the hidden form input.

### 9.6. POST without a token

~~~bash
curl -i -c cookies.txt -b cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"message":"missing-token"}' \
  http://localhost:8080/api/notes
~~~

Expect HTTP **403 Forbidden** (CSRF failure), even though browser/curl holds an authenticated session. The 403 body depends on handler and version; do not hardcode a default JSON string.

On Windows PowerShell, use `curl.exe` if `curl` is an alias; the commands use Bash `\` line continuations, so in PowerShell you can put them on one line. `cookies.txt` holds session cookies—never upload or commit it to Git.

## 10. Async edge cases, timeouts, and CORS

### 10.1. fetch does not throw on status 403

`fetch()` normally **resolves its Promise even on HTTP 401/403/500**; `catch` mainly catches network/CORS failures. Always check `response.ok` or `response.status`:

~~~javascript
const response = await fetch("/api/notes", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    [csrfHeader]: csrfToken
  },
  body: JSON.stringify({message: "example"})
});

if (response.status === 401) {
  // Login required; trigger login UX.
} else if (response.status === 403) {
  // CSRF or missing authority; do not assume a single cause.
} else if (!response.ok) {
  // Other application errors.
}
~~~

This snippet assumes `csrfHeader` and `csrfToken` were already loaded; it is not a standalone JS program.

### 10.2. Multiple concurrent requests

When multiple `fetch()` calls send POSTs in parallel on the **same `WebSession`**, they can reuse the same submitted token. XOR masking does not restrict tokens to single use. However, if the user logs out or the session is invalidated mid-flight, some requests may get 403; never infinitely retry POSTs since side effects may already have happened.

If the system requires "exactly-once submission", that is a job for **idempotency keys/transactions**, separate from CSRF validation.

### 10.3. Login/logout invalidates old tokens

After login, logout, session timeout, password change, or session rotation, the expected token may be cleared/replaced. An SPA should refetch `/csrf` or reload the page before issuing new unsafe requests; never cache a pre-login token indefinitely.

**403 does not always mean an expired token**: the user might lack a role, another CORS/WAF policy might block it, or the request handler might expect a masked token. Never blindly refresh tokens and retry in a loop.

### 10.4. CORS preflight

A cross-origin request with custom header `X-CSRF-TOKEN` can trigger an `OPTIONS` preflight. The default CSRF matcher does not require a token on OPTIONS, yet **CORS** still needs to allow the origin, method, header, and credentials. Never use `Access-Control-Allow-Origin: *` for cookie credentials, and never "disable CSRF" to fix CORS.

If SPA and backend sit on different origins using cookies, also design `SameSite`, `Secure`, the CSRF token endpoint, credentialed CORS, and trust boundaries. CORS **is not** a replacement for CSRF.

### 10.5. Multipart uploads

Putting tokens in multipart form bodies can force the server to parse bodies before deciding CSRF, risking temp-file creation and resource exhaustion. With JavaScript uploaders, **prefer sending tokens in HTTP headers** to validate before deep body parsing. Never put tokens in query strings to dodge multipart parsers.

### 10.6. Server-to-server WebClient

`WebClient` calling APIs with server-managed Bearer tokens (without auto-sent browser cookies) typically has a different CSRF threat model. If `WebClient` actually holds a **session cookie** and calls a CSRF-protected server, it must fetch the token and send the matching header/form. Never blindly send tokens to stateless APIs just thinking "every POST needs one".

### 10.7. WebSocket/SSE

Read-only SSE GETs are usually safe; WebSockets have dedicated origin/cross-site handshake concerns. Never assume `CsrfWebFilter` protects all WebSocket messages just because it protects POSTs. For upgrade connections or SockJS, read the corresponding documentation to verify origin checks and authenticated sessions.

## 11. Troubleshooting common errors

| Symptom | Possible cause | Check |
| --- | --- | --- |
| Form POST returns 403 | Missing hidden input, wrong token, or missing session cookie | Inspect form DOM, Request Payload, Cookies |
| Fetch POST returns 403 while form succeeds | Forgot CSRF header or wrong header name | DevTools Request Headers |
| GET /csrf returns no token | Did not subscribe to `Mono<CsrfToken>` or route blocked | Return publisher and check authentication |
| Sending raw XSRF cookie in header still gets 403 | XOR handler expects masked submitted token | Inspect repo + `ServerCsrfTokenRequestHandler` |
| POST after login returns 403 | Stale token or session rotated | Fetch fresh `GET /csrf` |
| POST after timeout returns 403 | Token belonged to expired session | Re-authenticate and fetch new token |
| Browser A token + browser B cookie returns 403 | Expected tokens differ per session | Never mix tokens across sessions |
| POST missing token yet controller logs nothing | Filter rejects before controller | Expected behavior; inspect security debug logs |
| OPTIONS preflight fails | CORS does not allow header/origin | Check `Access-Control-Allow-*` |
| fetch does not enter catch on 403 | HTTP error responses don't reject the Promise | Check `response.ok`/`response.status` |
| AJAX gets login HTML instead of JSON | Form-login redirect or session expired | Check 302/Location; separate browser/API |
| Dev/prod behave differently | Cookie path/domain/SameSite, proxy, cluster | Inspect response `Set-Cookie` and session store |
| GET mutates data without CSRF check | GET is safe by default | Fix endpoint per HTTP semantics |

### 11.1. Logging safely without leaking secrets

You can enable in dev:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Application logs should capture request ID, sanitized route template, method, status, and reason codes like `csrf_missing`/`csrf_invalid`, while **never** logging raw `_csrf`, `X-CSRF-TOKEN`, access tokens, passwords, or session cookies. Never put tokens into URLs, Referer headers, or query parameters when form/header options exist.

### 11.2. Never fix 403 with csrf.disable()

If a POST returns 403, check:

1. Is the request method covered by the CSRF matcher?
2. Which repository stores the expected token?
3. Was the token exposed/subscribed to?
4. Which header/parameter name does the server expect?
5. Is the client sending a **masked** or **raw** value?
6. Does the cookie belong to the same browser session?
7. Did login/logout reset the token or session?
8. Did a different security chain match the URL?
9. Is the 403 actually from CSRF or from authorization?
10. Was the cross-origin request rejected by CORS preflight?

Only consider disabling CSRF on a stateless Bearer chain **after** proving zero browser-auto-sent credentials exist and the threat model supports it.

## 12. Automated testing

With WebFlux, use `WebTestClient` and Spring Security test support to assert that POSTs without CSRF fail and POSTs with proper tokens reach the controller.

Test snippet:

~~~java
// Illustrative snippet inside an integration test with WebTestClient.
webTestClient.mutateWith(mockUser("learner"))
        .mutateWith(csrf())
        .post()
        .uri("/api/notes")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new ReactiveCsrfDemoApplication.NoteRequest("test"))
        .exchange()
        .expectStatus().isOk();
~~~

This is not a full test class; it requires `spring-security-test`, `WebTestClient`, `SecurityMockServerConfigurers.mockUser`/`csrf`, a compatible test runner, and loaded app beans. Follow up with the same request **without `csrf()`** to expect 403. Mock users do not by themselves prove real browsers use the right cookie jar; combine with E2E tests across two browser profiles.

### 12.1. Test matrix

| Test | Input | Expected |
| --- | --- | --- |
| Public GET | Anonymous `GET /` | 200 |
| Protected GET | Anonymous `GET /demo` | Redirect to login |
| Login with valid CSRF | POST login + cookie + hidden token | Success/redirect |
| Login missing CSRF | POST login without token | 403 |
| Valid form POST | Cookie + hidden `_csrf` | 200, `FORM_OK:from-form` |
| Invalid form POST | Wrong/missing token | 403 |
| Valid fetch POST | Cookie + `X-CSRF-TOKEN` | 200, JSON `API_OK` |
| Fetch POST missing header | Cookie present, header absent | 403 |
| JSON body has `_csrf` key without header | POST JSON | Usually 403 |
| GET /csrf | Valid session | JSON token/headerName/parameterName |
| Pre-login token used post-login | Stale token | Possibly 403, refresh needed |
| Session A token + session B cookie | Cross-session | 403 |
| Cookie repo raw + default XOR | Raw header | Possibly 403, check handler |
| CORS preflight | OPTIONS with custom header | CORS permits per policy |
| CSRF passes yet role missing | Logged in without authority | 403 authorization |
| Stateless Bearer API | JWT Authorization, no cookies | Separate threat model |

**When asserting JSON responses**, compare fields rather than byte order. With `Map.of`, serializers may vary key ordering in output.

## 13. Production checklist

1. Keep CSRF enabled for cookie/form/session or browser-cached credential flows.
2. Never use GET/HEAD for state-changing operations.
3. Fetch tokens from the active authenticated session; never reuse another user's/session's token.
4. Forms use hidden `token.getParameterName()` and `token.getToken()`.
5. JSON/AJAX use header `token.getHeaderName()` and the server-exposed token value.
6. Never block the Reactor event loop with `block()` when fetching tokens.
7. Distinguish **where** the repository stores tokens from **what format** (raw/masked) the request handler expects.
8. Only disable `HttpOnly` on `XSRF-TOKEN` when JS genuinely must read it; keep auth cookie policies separate.
9. After login/logout/session reset, fetch a fresh token.
10. Set `Cache-Control: no-store` on token-exposing endpoints/pages where appropriate.
11. Never log CSRF tokens or send them in URLs/query strings.
12. Design CORS, `SameSite`, `Secure`, `HttpOnly`, and session stores to match your topology.
13. Never treat CSRF tokens as proof of authentication/authorization.
14. Test browser HTML, async fetch, curl with cookie jars, session expiry, and multipart uploads.
15. Across multiple instances, use shared session storage or a suitable strategy so expected tokens stay consistent.
16. Never disable CSRF system-wide to fix a single 403 error.

## 14. Self-check questions

**Q1.** Why is sending only the session cookie insufficient for a POST to be accepted?

**Answer:** Browsers can auto-attach cookies to forged requests. Tokens must be actively sent in a form field/header supplied by the legitimate website.

**Q2.** Why can a `fetch()` sending JSON with a `_csrf` field in the business body still receive 403?

**Answer:** The default reactive CSRF resolver reads tokens from form parameters or HTTP headers, not arbitrary keys inside JSON bodies. Send the proper header.

**Q3.** Where does `Mono<CsrfToken>` live?

**Answer:** In a `ServerWebExchange` attribute under `CsrfToken.class.getName()`. Controllers compose/return the publisher without calling `block()`.

**Q4.** Where does Spring Security 7.1 store expected tokens by default?

**Answer:** `WebSessionServerCsrfTokenRepository`, inside `WebSession`.

**Q5.** Why might a token read from the `XSRF-TOKEN` cookie not work directly in a header in Spring Security 7?

**Answer:** Cookies hold raw tokens whereas the default XOR request handler may expect masked submitted tokens. Configure a compatible repository and handler.

**Q6.** Does `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` strip `HttpOnly` from the session cookie?

**Answer:** No. It configures the CSRF cookie so JavaScript can read it without altering authentication/session cookie attributes.

**Q7.** Why refresh tokens after login/logout?

**Answer:** Sessions/expected tokens can change or be cleared; old tokens may fail on the next POST.

**Q8.** Does `fetch()` automatically throw on HTTP status 403?

**Answer:** No. Check `response.ok`/`response.status`; Promise rejections typically reflect network/CORS errors.

**Q9.** For JavaScript multipart file uploads, where should the token be sent to avoid parsing the body before CSRF?

**Answer:** Prefer an HTTP header.

**Q10.** Must a Bearer-only stateless API always disable CSRF?

**Answer:** There is no "always" rule. Consider disabling only after verifying browsers never auto-send credentials and no cookie-based paths need protection.

## 15. Official References

- [Spring Security 7.1 — CSRF for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html)
- [Spring Security — CsrfWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html)
- [Spring Security — CsrfToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CsrfToken.html)
- [Spring Security — WebSessionServerCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html)
- [Spring Security — CookieServerCsrfTokenRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/CookieServerCsrfTokenRepository.html)
- [Spring Security — XorServerCsrfTokenRequestAttributeHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html)
- [Spring Security — ServerCsrfTokenRequestAttributeHandler API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestAttributeHandler.html)
- [Spring Security — WebFlux Configuration](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security — Reactive Login](https://docs.spring.io/spring-security/reference/reactive/authentication/passwords/form.html)
- [Spring Security — CSRF Concepts](https://docs.spring.io/spring-security/reference/features/exploits/csrf.html)
- [Spring Boot 4.1.2 release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/)
