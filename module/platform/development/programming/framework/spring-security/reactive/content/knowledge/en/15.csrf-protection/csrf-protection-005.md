# CookieServerCsrfTokenRepository and Sending Tokens from JavaScript Applications

## Learning Objectives

This lesson belongs to the **CSRF Protection** topic in **Spring Security reactive / Spring WebFlux**. After studying it, you will be able to:

- Explain how CSRF happens when browsers **auto-send credentials** (especially session cookies) on state-changing requests, and why HTTP Basic, session-cookie authentication, or certain browser token storage choices can be affected.
- Distinguish the default `WebSessionServerCsrfTokenRepository` from `CookieServerCsrfTokenRepository`: where the expected token lives, cookie names, headers, and form parameters.
- Configure `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` when same-origin JavaScript needs to read the `XSRF-TOKEN` cookie to send the token back in `X-XSRF-TOKEN`.
- Understand a common Spring Security 6.x pitfall: the default **XOR-masking/BREACH** request handler may reject **raw** tokens read from cookies by JS; customize raw-header handling while keeping masked tokens for HTML forms.
- Initialize or refresh the token cookie via a **GET /csrf** endpoint by subscribing to the WebFlux-provided `Mono<CsrfToken>`, especially after login/logout.
- Write a **Java 17 + Spring Boot + WebFlux** example and same-origin JavaScript `fetch` for JSON POSTs, including tests verifying 403 on missing/invalid tokens and 200 on valid tokens.
- Choose sensible `HttpOnly`, `Secure`, `SameSite`, `Path`, and CORS policies; never treat CSRF tokens as substitutes for Authentication/Authorization or XSS defenses.

> **Scope:** Spring Security **reactive**. WebFlux uses `CookieServerCsrfTokenRepository` and `ServerHttpSecurity`, not Servlet MVC's `CookieCsrfTokenRepository`/`HttpSecurity`. A conceptually similar cookie setup does not necessarily use the same classes, response handlers, or flows across the two stacks.

## 1. What is CSRF, and how is JavaScript involved?

**Cross-Site Request Forgery (CSRF)** occurs when a malicious website/page causes a victim's browser to send a request to an application where the victim is logged in. If the browser **automatically attaches the session cookie** to the request, the server may mistake that action for the user's real intent.

Example:

~~~text
User is logged into https://shop.example.test
    |
    +-- Browser holds cookie SESSION=...
    |
    v
User visits an untrusted website
    |
    v
That website attempts to trigger POST /api/orders/cancel
    |
    +-- Browser may auto-send session cookie
    |
    v
If server trusts cookie alone -> risk of unintended data mutation
~~~

**CSRF tokens** add a requirement: state-changing requests must contain an unpredictable token in a **location the browser does not add automatically** (such as a custom header explicitly set by JavaScript, or a hidden form field rendered by the legitimate app). The server checks the submitted token against the expected token.

A JavaScript application commonly sends JSON via `fetch`:

~~~javascript
await fetch("/api/orders", {
  method: "POST",
  credentials: "same-origin",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ itemId: 42 })
});
~~~

The snippet above **does not send a CSRF token yet**. If the server enforces CSRF protection and relies on cookies, the POST request may get **403 Forbidden**, even with a valid session. Configuring where tokens are stored and adding the header properly is the core subject of this lesson.

### 1.1. Which methods require CSRF?

Spring Security WebFlux enforces CSRF by default on **unsafe** HTTP methods; `GET`, `HEAD`, `OPTIONS`, and `TRACE` are normally treated as safe methods. `POST`, `PUT`, `PATCH`, and `DELETE` typically require a valid CSRF token when the filter is enabled.

- `GET /csrf`: reads/initializes the token for client use; must not mutate business data.
- `GET /api/me`: reads identity, typically requires no CSRF header.
- `POST /api/notes`: state-changing operation, typically requires a token.
- `POST /login` and `POST /logout`: in cookie/session apps these also require CSRF protection; login CSRF and logout CSRF are real threats.
- If a **GET** endpoint transfers money or deletes data, that is an HTTP design bug; the default CSRF matcher normally **does not protect** GET. Fix the method rather than relying on "hiding the button".

**CSRF does not replace Authentication.** Holding a valid token does not prove a user is authorized to call an API; session/password/token verification and authorization must still be enforced independently.

## 2. What does CookieServerCsrfTokenRepository store?

`CookieServerCsrfTokenRepository` is a WebFlux `ServerCsrfTokenRepository` that stores the **expected token** in a cookie instead of in `WebSession` like the default repository. It fits when same-origin JavaScript needs to access the token via `document.cookie`.

By repository default:

| Component | Default name | How it is used |
|---|---|---|
| Cookie storing expected token | `XSRF-TOKEN` | Sent by server via `Set-Cookie` and read back on subsequent requests. |
| Header carrying JS-sent token | `X-XSRF-TOKEN` | Client reads value from cookie and **copies it into the header** on unsafe requests. |
| Form parameter | `_csrf` | HTML forms can submit the token in a form field; JSON typically uses a header. |
| Session cookie | Usually `SESSION`, configurable | Used for login; **distinct** from the CSRF cookie. |
| Bean/repository | `ServerCsrfTokenRepository` | Generates, saves, and loads CSRF tokens; not an Authentication repository. |

Do not confuse `XSRF-TOKEN` with `SESSION`: the first holds the anti-CSRF token, while the second is typically the login session ID. A site can perfectly well have a CSRF token before the user logs in.

### 2.1. Cookies are auto-sent, headers are not

Browsers **auto-send cookies** per cookie rules (origin/domain/path/SameSite/Secure). Custom headers like `X-XSRF-TOKEN`, however, must be added explicitly by JavaScript or a client.

~~~text
Browser holds cookies:
  SESSION=<session-id>
  XSRF-TOKEN=<raw-csrf-token>

JavaScript:
  token = read XSRF-TOKEN via document.cookie
  fetch("/api/notes", {
    method: "POST",
    headers: { "X-XSRF-TOKEN": token },
    credentials: "same-origin"
  })

Browser actually sends:
  Cookie: SESSION=...; XSRF-TOKEN=...
  X-XSRF-TOKEN: <raw-csrf-token>

Server:
  CookieServerCsrfTokenRepository.loadToken(exchange)
  + ServerCsrfTokenRequestHandler reads token from request
  + CsrfWebFilter compares
  -> allow through or 403
~~~

**Never say "just setting the XSRF-TOKEN cookie gives CSRF protection".** An attacker can cause the browser to auto-send cookies (since cookies attach automatically). What makes the JavaScript pattern work is requiring the token to also be sent in a **custom header**; ordinary cross-origin sites cannot arbitrarily set that header and read the victim origin's token when browser/SOP/CORS are properly configured.

### 2.2. What does withHttpOnlyFalse() do?

~~~java
CookieServerCsrfTokenRepository repository =
    CookieServerCsrfTokenRepository.withHttpOnlyFalse();
~~~

This factory method sets **`HttpOnly=false`** on the cookie, allowing same-origin JavaScript to read it via `document.cookie`. This is necessary **if the client reads the cookie directly**. If the application **does not need JS to read the cookie**, prefer:

~~~java
CookieServerCsrfTokenRepository repository =
    new CookieServerCsrfTokenRepository();
~~~

This configuration keeps `HttpOnly` as a safer default for the CSRF cookie, while tokens can still be passed to forms/meta tags via server-rendered views.

**Security boundary:** a CSRF token **is not a login password**; nevertheless, making cookies JS-readable expands risk exposure to **XSS**. If an attacker executes scripts inside your origin, they can usually issue accepted requests despite CSRF tokens. Always maintain XSS protections (output encoding, CSP, safe dependencies, restricting untrusted scripts) and keep the session cookie **`HttpOnly`**.

## 3. Basic configuration in Spring Security WebFlux

Per official WebFlux documentation:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .csrf(csrf -> csrf.csrfTokenRepository(
            CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
        .authorizeExchange(exchanges -> exchanges
            .anyExchange().authenticated())
        .build();
}
~~~

This is a **configuration fragment** inside a Spring class importing `@Bean`, `ServerHttpSecurity`, `SecurityWebFilterChain`, and `CookieServerCsrfTokenRepository`. It shows how to swap the default `WebSessionServerCsrfTokenRepository` for the cookie-based repository.

**However, this configuration alone does not guarantee every Spring Security 6.x setup will accept a raw token header from `document.cookie`.** The issue lies in the request handler layer and BREACH token masking; the next section addresses this explicitly.

### 3.1. Customizing cookie attributes

In Spring Security 6.1+, the repository offers `setCookieCustomizer(...)` to tune cookie attributes:

~~~java
CookieServerCsrfTokenRepository repository =
    CookieServerCsrfTokenRepository.withHttpOnlyFalse();

repository.setCookieCustomizer(cookie -> cookie
    .path("/")
    .sameSite("Lax"));
~~~

This is a **code fragment** placed before passing the repository to `csrfTokenRepository(...)`. `path("/")` ensures JavaScript across paths on the same host can see the cookie; `SameSite=Lax` fits a same-origin demo. In HTTPS production, consider setting `.secure(true)`; if using `SameSite=None`, `Secure` is mandatory in modern browsers.

Do not set `Domain=.example.com` to share the CSRF cookie across all subdomains just for convenience, as an untrusted subdomain increases **cookie injection** risk. Cookie `Path`, `Domain`, `Secure`, and `SameSite` must match your real domain, proxy, and TLS architecture.

## 4. The Spring Security 6 catch: XOR-masked tokens vs. raw tokens from cookies

Since 6.0, Spring Security WebFlux uses `XorServerCsrfTokenRequestAttributeHandler` by default. It **masks** token values emitted to views to mitigate **BREACH** (compression side-channel secret inference). It also decodes masked tokens when clients submit them back via form fields/headers.

Meanwhile, `CookieServerCsrfTokenRepository` stores the **raw token** in the `XSRF-TOKEN` cookie, and JavaScript can only read the raw value. This creates a mismatch:

~~~text
Expected token in cookie:          T (raw)
View receives token from XOR:      M(T, random) (masked)
HTML form submits masked token:    M(T, random)
JS document.cookie reads:          T (raw)
JS X-XSRF-TOKEN sends:             T (raw)

The XOR resolver is written to decode masked tokens.
Passing raw T to the XOR resolver can FAIL validation (403).
~~~

Therefore, **never set `withHttpOnlyFalse()` alone and assume JavaScript apps will always work**. Two approaches exist:

1. **Simple approach for a raw-header-only JS API:** use `new ServerCsrfTokenRequestAttributeHandler()` to process raw tokens. Spring Security docs note this turns off XOR/BREACH masking; this carries a security trade-off if raw tokens are also rendered into HTML responses.
2. **More balanced approach for SPAs mixed with forms:** keep XOR to generate masked tokens for views/forms; when a request includes the `X-XSRF-TOKEN` header, use a plain handler to resolve the **raw header**. This is used in the main example of this lesson: letting JS read the raw cookie while keeping masked form submission.

### 4.1. Simple option: accept raw tokens only

~~~java
.csrf(csrf -> csrf
    .csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse())
    .csrfTokenRequestHandler(
        new ServerCsrfTokenRequestAttributeHandler()))
~~~

This WebFlux DSL fragment requires importing `org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler`. With this setup, the server does not apply XOR masking by default. Do not apply it blindly when your app renders tokens into HTML, because BREACH protection is designed to avoid echoing the exact same raw secret in compressible responses.

### 4.2. Combined option: raw header + masked form

You can provide a custom `ServerCsrfTokenRequestHandler`:

~~~java
ServerCsrfTokenRequestHandler handler =
    new ServerCsrfTokenRequestHandler() {
        private final XorServerCsrfTokenRequestAttributeHandler xor =
            new XorServerCsrfTokenRequestAttributeHandler();
        private final ServerCsrfTokenRequestAttributeHandler plain =
            new ServerCsrfTokenRequestAttributeHandler();

        @Override
        public void handle(
            ServerWebExchange exchange, Mono<CsrfToken> token) {

            xor.handle(exchange, token);
        }

        @Override
        public Mono<String> resolveCsrfTokenValue(
            ServerWebExchange exchange, CsrfToken token) {

            boolean rawHeaderPresent = exchange.getRequest()
                .getHeaders().containsKey(token.getHeaderName());

            return rawHeaderPresent
                ? plain.resolveCsrfTokenValue(exchange, token)
                : xor.resolveCsrfTokenValue(exchange, token);
        }
    };
~~~

This is a **fragment inside a configuration method**; its complete runnable Java class is in the hands-on section. It captures the two independent duties of the request handler cleanly:

- `handle(...)` uses XOR to **expose tokens to views** with BREACH protection.
- `resolveCsrfTokenValue(...)` reads the **raw header** when JavaScript explicitly sets `X-XSRF-TOKEN`; if the header is absent, it resolves the **masked form value** via XOR.
- Never write your own token `equals` check; `CsrfWebFilter` still compares the expected token against the value returned by the resolver.

**Explicit caveat:** If you send a masked token in the `X-XSRF-TOKEN` header with this handler, it will be treated as raw and may be rejected. In this lesson, JS clients always send the raw cookie value; forms use masked fields. If multiple clients follow different conventions, design dedicated matchers/handlers or rules and test them.

### 4.3. Why shouldn't a gateway copy the cookie into a header?

If a reverse proxy auto-generates `X-XSRF-TOKEN` by copying the cookie on every request, including cross-site requests, you eliminate the requirement for the client to **actively** present the token. The double-submit CSRF defense relies on untrusted sites being unable to supply a valid header (and unable to read the token). Never configure infrastructure to blindly turn cookies into headers.

## 5. Deferred CSRF tokens: why is XSRF-TOKEN missing after GET?

Spring Security uses **deferred token loading**: the token is exposed as `Mono<CsrfToken>` and may only be created/saved when a subscriber actually consumes it. Consequently:

- Any arbitrary public GET **is not guaranteed** to emit `Set-Cookie: XSRF-TOKEN=...`.
- Configuring the cookie repository without ever consuming `Mono<CsrfToken>` can leave the frontend without the cookie.
- After login or logout, old CSRF tokens are often cleared/refreshed; SPAs must obtain a fresh token before the next unsafe request.

In WebFlux, `CsrfWebFilter` exposes an exchange attribute at key `CsrfToken.class.getName()` of type `Mono<CsrfToken>`. A GET endpoint can subscribe to that `Mono` so the token is generated and the cookie saved:

~~~java
@GetMapping("/csrf")
@ResponseStatus(HttpStatus.NO_CONTENT)
Mono<Void> csrf(ServerWebExchange exchange) {
    Mono<CsrfToken> token =
        exchange.getAttribute(CsrfToken.class.getName());

    if (token == null) {
        return Mono.error(new IllegalStateException(
            "CSRF attribute unavailable"));
    }

    return token.then();
}
~~~

This is a **controller method fragment**; the hands-on section shows the complete class. `then()` subscribes to the token `Mono` in the pipeline, discards the token value from the body, and returns HTTP 204. Crucially, **let WebFlux subscribe**, never call `token.subscribe()` manually. The cookie is delivered via the response's `Set-Cookie` header without needing a JSON body.

### 5.1. Why should GET /csrf be same-origin and no-store?

The token has security value within the session/browser scope; the initialization endpoint should be protected from caching and unnecessary cross-origin sharing. On the frontend:

~~~javascript
const response = await fetch("/csrf", {
  method: "GET",
  credentials: "same-origin",
  cache: "no-store"
});
if (!response.ok) {
  throw new Error("Failed to obtain CSRF token");
}
~~~

`credentials: "same-origin"` sends cookies on same-origin requests without leaking tokens to another origin. `cache: "no-store"` avoids reusing cached GET responses when a fresh cookie is needed. The server should emit proper cache headers; Spring Security typically adds default cache-control headers, yet apps behind CDNs/proxies must still verify them.

### 5.2. Login/logout lifecycle

~~~text
GET /csrf (before login)  --> issue XSRF-TOKEN A
POST /login + token A     --> authentication succeeds
                              CSRF token A may be cleared
GET /csrf (after login)   --> issue XSRF-TOKEN B
POST /api/notes + B       --> 200 if user has authority
POST /logout + B          --> logout / CSRF token may be cleared
GET /csrf (after logout)  --> issue new token C if needed
~~~

Never assume a token value remains valid forever across page loads, logins, logouts, session expirations, other tabs, or cookie refreshes. **JS should fetch/refresh the token after login/logout** and handle 403 errors from expired tokens via a safe flow (no infinite retries; never auto-replay dangerous non-idempotent operations).

## 6. Sending X-XSRF-TOKEN from same-origin JavaScript

With an `HttpOnly=false` cookie, JavaScript can read `document.cookie`. The browser auto-sends cookies on requests; JavaScript must actively copy the value into `X-XSRF-TOKEN`.

### 6.1. Reading the cookie

~~~javascript
function getCookie(name) {
  const prefix = encodeURIComponent(name) + "=";
  const entry = document.cookie
    .split(";")
    .map(part => part.trim())
    .find(part => part.startsWith(prefix));

  return entry ? decodeURIComponent(entry.slice(prefix.length)) : null;
}

const csrfToken = getCookie("XSRF-TOKEN");
if (!csrfToken) {
  throw new Error("XSRF-TOKEN cookie not found");
}
~~~

This is a simple JS helper for a **same-origin demo**. It cannot read `HttpOnly=true` cookies, nor can it read cookies belonging to origins outside the page's access. If multiple cookies share the same name across paths/domains, browsers may hold duplicates and simple string matching becomes unreliable; keep cookie path/host definitions unambiguous.

### 6.2. Adding the header on JSON POSTs

~~~javascript
async function createNote(text) {
  await fetch("/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });

  const token = getCookie("XSRF-TOKEN");
  if (!token) {
    throw new Error("Failed to obtain CSRF cookie");
  }

  const response = await fetch("/api/notes", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-XSRF-TOKEN": token
    },
    body: JSON.stringify({ text })
  });

  if (!response.ok) {
    throw new Error("HTTP " + response.status);
  }

  return response.json();
}
~~~

This JavaScript snippet builds on `getCookie` declared above. The hands-on section uses a more thorough version checking 302/login HTML redirects, JSON, and 403s.

**Never** pass tokens in URLs/query strings like `?csrf=...`: URLs easily leak into browser history, reverse-proxy logs, analytics, or referrers. For JSON requests, a custom header is the clean choice. Avoid stuffing `_csrf` into JSON bodies without a dedicated CSRF parser: Spring Security normally reads tokens from **headers or form parameters**, not arbitrary JSON fields.

### 6.3. How does Fetch send cookies?

| `credentials` | Meaning | When to use |
|---|---|---|
| `same-origin` | Sends cookies/credentials for same-origin requests. | **Recommended default** for same-origin SPA examples. |
| `include` | May send credentials cross-origin if browser/CORS/cookie policies permit. | Use only for deliberately controlled cross-origin designs. |
| `omit` | Sends no cookies/credentials. | Stateless APIs or requests needing no session; may render user anonymous. |

Setting a custom header **does not attach the session cookie** if you specified `credentials:"omit"`. Conversely, sending cookies **without the CSRF header** can return 403. Both serve independent roles.

### 6.4. Avoid sending tokens outside your origin

Clients should use relative paths like `"/api/notes"` or verify the destination URL before attaching the header. Never configure a global interceptor to attach `X-XSRF-TOKEN` to every request going to CDNs, analytics, third-party APIs, or external redirects. The token belongs to your origin/session; sending it elsewhere provides zero benefit and increases leakage risk.

## 7. Standalone runnable Java 17 example: Spring Boot WebFlux + cookie CSRF + SPA

This hands-on project uses **Java 17**, **Spring Boot 3.5.16**, Spring Security reactive, and an HTML/JavaScript page **served from the same origin** as the backend. Spring Boot manages the matching Spring Security version via dependency management; real projects should update releases per active security support.

**Observation goals:**

1. `GET /csrf` creates the JavaScript-readable `XSRF-TOKEN` cookie.
2. `POST /api/notes` missing the CSRF header -> **403**.
3. Having both the `XSRF-TOKEN` cookie and `X-XSRF-TOKEN` header with the same raw value -> passes CSRF; requires an authenticated user to enter the controller.
4. Uses `formLogin` for session-cookie website authentication; `httpBasic` is also enabled **solely so HTTP integration tests need no UI interaction**.
5. `GET /app.html` loads the page with the JS form; learners sign in at `/login` before calling the API.
6. `POST /api/notes` merely returns a demo confirmation without **persisting to a database**.

### 7.1. Project structure

~~~text
cookie-csrf-webflux-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/CookieCsrfWebFluxDemo.java
    ├── main/resources/static/app.html
    └── test/java/example/CookieCsrfIntegrationTest.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'cookie-csrf-webflux-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Requires JDK 17+ and Gradle compatible with Spring Boot 3.5. Use a Gradle Wrapper if available. Never add Servlet's `spring-boot-starter-web` dependency because the example targets the WebFlux stack.

### 7.2. Complete application

`src/main/java/example/CookieCsrfWebFluxDemo.java`:

~~~java
package example;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.CookieServerCsrfTokenRepository;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestAttributeHandler;
import org.springframework.security.web.server.csrf.ServerCsrfTokenRequestHandler;
import org.springframework.security.web.server.csrf.XorServerCsrfTokenRequestAttributeHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@SpringBootApplication
@EnableWebFluxSecurity
public class CookieCsrfWebFluxDemo {

    public static void main(String[] args) {
        SpringApplication.run(CookieCsrfWebFluxDemo.class, args);
    }

    @Bean
    MapReactiveUserDetailsService users() {
        // Localhost only; never use {noop} in production.
        UserDetails user = User.withUsername("learner")
            .password("{noop}demo-pass")
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(user);
    }

    @Bean
    SecurityWebFilterChain security(ServerHttpSecurity http) {
        var csrfCookie = CookieServerCsrfTokenRepository.withHttpOnlyFalse();

        // Local demo uses HTTP; in HTTPS production set secure(true).
        csrfCookie.setCookieCustomizer(cookie -> cookie
            .path("/")
            .sameSite("Lax"));

        var xor = new XorServerCsrfTokenRequestAttributeHandler();
        var plain = new ServerCsrfTokenRequestAttributeHandler();

        ServerCsrfTokenRequestHandler spaHandler =
            new ServerCsrfTokenRequestHandler() {

                @Override
                public void handle(
                    ServerWebExchange exchange, Mono<CsrfToken> token) {

                    // Keep masked token when exposing to forms/views.
                    xor.handle(exchange, token);
                }

                @Override
                public Mono<String> resolveCsrfTokenValue(
                    ServerWebExchange exchange, CsrfToken token) {

                    // JS sends raw cookie value in X-XSRF-TOKEN.
                    boolean headerPresent = exchange.getRequest()
                        .getHeaders().containsKey(token.getHeaderName());

                    return headerPresent
                        ? plain.resolveCsrfTokenValue(exchange, token)
                        : xor.resolveCsrfTokenValue(exchange, token);
                }
            };

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/csrf", "/app.html", "/login").permitAll()
                .anyExchange().authenticated())
            .csrf(csrf -> csrf
                .csrfTokenRepository(csrfCookie)
                .csrfTokenRequestHandler(spaHandler))
            .formLogin(Customizer.withDefaults())
            // Allow integration tests to send Basic without a login form.
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    public record NoteRequest(String text) {
    }

    @RestController
    static class Api {

        // Subscribe to token Mono -> XSRF-TOKEN cookie is created on demand.
        @GetMapping("/csrf")
        @ResponseStatus(HttpStatus.NO_CONTENT)
        Mono<Void> csrf(ServerWebExchange exchange) {
            Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

            if (token == null) {
                return Mono.error(new IllegalStateException(
                    "CSRF token attribute unavailable"));
            }

            return token.then();
        }

        @GetMapping("/api/me")
        Mono<Map<String, String>> me(ServerWebExchange exchange) {
            return exchange.getPrincipal()
                .map(principal ->
                    Map.of("username", principal.getName()));
        }

        @PostMapping("/api/notes")
        Mono<Map<String, String>> create(
            @RequestBody Mono<NoteRequest> body,
            ServerWebExchange exchange) {

            // Acknowledge request only; do not write to a database.
            return exchange.getPrincipal()
                .zipWith(body)
                .map(pair -> Map.of(
                    "acceptedBy", pair.getT1().getName(),
                    "text", pair.getT2().text()));
        }
    }
}
~~~

**Key points in the Java code:**

- `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` lets `document.cookie` read the token.
- `setCookieCustomizer` configures path and SameSite; `Secure` is omitted in the local demo because it runs on `http://localhost`. Production must enforce TLS and consider `Secure` mandatory.
- `XorServerCsrfTokenRequestAttributeHandler` still exposes tokens to forms/views; `ServerCsrfTokenRequestAttributeHandler` resolves JS raw headers.
- `.csrf(...)` is not disabled. POSTs with missing/invalid CSRF tokens are rejected by `CsrfWebFilter`.
- `formLogin(...)` provides form/session login for browser users; `httpBasic(...)` adds a convenience path for integration tests. In production, enable only the login mechanisms actually needed.
- `GET /csrf` is public so clients can initialize the token; it **does not prove the user is authenticated** and prepares both the login POST and post-login calls.
- `GET /app.html` publicly serves the JavaScript page; the `POST /api/notes` controller only runs once the user is authenticated and CSRF is valid.
- `NoteRequest` is a Java record (Java 17); Spring Boot's Jackson maps `{"text":"..."}` JSON into the object.
- Never call `block()` or manual `subscribe()`; everything returns `Mono` for WebFlux to execute.

### 7.3. Same-origin JavaScript UI

`src/main/resources/static/app.html`:

~~~html
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>WebFlux CSRF Cookie Demo</title>
</head>
<body>
  <h1>POST JSON with X-XSRF-TOKEN</h1>
  <p>First sign in via <a href="/login">/login</a>
     using learner / demo-pass (local only).</p>

  <form id="noteForm">
    <input id="noteText" value="Hello WebFlux" required>
    <button type="submit">Send POST</button>
  </form>
  <pre id="result" aria-live="polite"></pre>

  <script type="module">
    "use strict";

    function readCookie(name) {
      const prefix = encodeURIComponent(name) + "=";
      const entry = document.cookie
        .split(";")
        .map(part => part.trim())
        .find(part => part.startsWith(prefix));

      return entry
        ? decodeURIComponent(entry.slice(prefix.length))
        : null;
    }

    async function getFreshCsrfToken() {
      const response = await fetch("/csrf", {
        method: "GET",
        credentials: "same-origin",
        cache: "no-store"
      });

      if (!response.ok) {
        throw new Error("Failed to fetch CSRF cookie: HTTP "
          + response.status);
      }

      const token = readCookie("XSRF-TOKEN");
      if (!token) {
        throw new Error("XSRF-TOKEN cookie not found");
      }

      return token;
    }

    async function submitNote(text) {
      // Re-fetch after login since the old token may be cleared/rotated.
      const token = await getFreshCsrfToken();

      const response = await fetch("/api/notes", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-XSRF-TOKEN": token
        },
        body: JSON.stringify({ text })
      });

      // With form login, fetch may follow redirects and receive login HTML.
      const contentType = response.headers.get("Content-Type") || "";

      if (response.redirected || !contentType.includes("application/json")) {
        throw new Error("Please sign in at /login before sending POST");
      }

      const data = await response.json();

      if (!response.ok) {
        throw new Error("POST rejected: HTTP " + response.status);
      }

      return data;
    }

    document.getElementById("noteForm")
      .addEventListener("submit", async event => {
        event.preventDefault();

        const result = document.getElementById("result");
        const text = document.getElementById("noteText").value;

        result.textContent = "Sending...";

        try {
          const data = await submitNote(text);
          result.textContent = JSON.stringify(data, null, 2);
        } catch (error) {
          result.textContent = String(error.message || error);
        }
      });
  </script>
</body>
</html>
~~~

**How to run the page:** visit `http://localhost:8080/login`, sign in with `learner / demo-pass`, then open `http://localhost:8080/app.html` and click **Send POST**. JavaScript will `GET /csrf`, read the raw `XSRF-TOKEN` cookie, and send the `X-XSRF-TOKEN` header and JSON to `/api/notes`. Once the session/CSRF cookies are valid, the server replies with JSON similar to `{"acceptedBy":"learner","text":"Hello WebFlux"}`.

Actual output may have a different JSON field order. This is an **HTTP response**, not Java application stdout. The demo writes nothing to a database; `acceptedBy` merely shows the authenticated principal and `text` echoes the input.

### 7.4. Steps to run

Inside `cookie-csrf-webflux-demo`:

~~~bash
gradle bootRun
~~~

If using Gradle Wrapper: `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Once the app is running, open the browser as instructed above. In Developer Tools you can inspect:

- The `GET /csrf` response may contain `Set-Cookie: XSRF-TOKEN=...; Path=/; SameSite=Lax` (the cookie is refreshed/saved when the token is actually created).
- The `POST /api/notes` request sends the `SESSION` cookie (if the browser logged in), the `XSRF-TOKEN` cookie, and the `X-XSRF-TOKEN` header carrying the same **raw token**.
- In the Network tab, if POST returns 403, inspect the exact token, cookie, handler, and path instead of disabling CSRF.
- Never copy/paste real cookies, session tokens, or credentials into tickets/logs. Use test values and scrub sensitive data from debug screenshots.

### 7.5. Manual verification with curl (demo-only HTTP Basic)

You can bypass the browser login step when testing the CSRF mechanics by using the HTTP Basic auth enabled in the demo. Use a **cookie jar** so POST requests send back the server-issued token:

~~~bash
# 1. Server creates the XSRF-TOKEN cookie.
curl -i -c cookies.txt -b cookies.txt \
  http://localhost:8080/csrf

# 2. POST with valid Basic auth but MISSING X-XSRF-TOKEN: typically 403.
curl -i -b cookies.txt -u learner:demo-pass \
  -H 'Content-Type: application/json' \
  -d '{"text":"missing header"}' \
  http://localhost:8080/api/notes

# 3. POST with forged CSRF header: 403.
curl -i -b cookies.txt -u learner:demo-pass \
  -H 'Content-Type: application/json' \
  -H 'X-XSRF-TOKEN: invalid-token' \
  -d '{"text":"wrong header"}' \
  http://localhost:8080/api/notes
~~~

To test a successful POST, safely read the **`XSRF-TOKEN` cookie value** from the cookie jar and pass that exact value in the header:

~~~bash
# Demo only; never print real tokens into logs/tickets.
TOKEN=$(awk '$6=="XSRF-TOKEN"{print $7}' cookies.txt)

curl -i -b cookies.txt -u learner:demo-pass \
  -H 'Content-Type: application/json' \
  -H "X-XSRF-TOKEN: $TOKEN" \
  -d '{"text":"valid header"}' \
  http://localhost:8080/api/notes
~~~

This uses **Bash/GNU awk** syntax; on Windows PowerShell, use `curl.exe` and a compatible cookie reader. Column order in curl's cookie jar follows Netscape format; cookie presence depends on the `GET /csrf` response actually generating it. If the first command produces no cookie, check deferred tokens and ensure the endpoint subscribed to `Mono<CsrfToken>`.

Never pass real passwords with `-u` in shell history/process listings; this is a local demo account. Never send HTTP Basic over unencrypted networks outside localhost.

## 8. Integration tests with WebTestClient

File `src/test/java/example/CookieCsrfIntegrationTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CookieCsrfIntegrationTest {

    @Autowired
    WebTestClient client;

    private ResponseCookie csrfCookie() {
        var result = client.get().uri("/csrf")
            .exchange()
            .expectStatus().isNoContent()
            .returnResult(Void.class);

        ResponseCookie cookie =
            result.getResponseCookies().getFirst("XSRF-TOKEN");

        assertNotNull(cookie, "GET /csrf must create XSRF-TOKEN");
        assertFalse(cookie.isHttpOnly(),
            "JS must be able to read the cookie in this demo");
        return cookie;
    }

    @Test
    void missingHeaderIsForbiddenEvenWithValidCredential() {
        ResponseCookie cookie = csrfCookie();

        client.post().uri("/api/notes")
            .headers(h -> h.setBasicAuth("learner", "demo-pass"))
            .cookie("XSRF-TOKEN", cookie.getValue())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CookieCsrfWebFluxDemo.NoteRequest("missing"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void wrongHeaderIsForbidden() {
        ResponseCookie cookie = csrfCookie();

        client.post().uri("/api/notes")
            .headers(h -> h.setBasicAuth("learner", "demo-pass"))
            .cookie("XSRF-TOKEN", cookie.getValue())
            .header("X-XSRF-TOKEN", "invalid-token")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CookieCsrfWebFluxDemo.NoteRequest("wrong"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void rawCookieTokenInHeaderAllowsPost() {
        ResponseCookie cookie = csrfCookie();

        client.post().uri("/api/notes")
            .headers(h -> h.setBasicAuth("learner", "demo-pass"))
            .cookie("XSRF-TOKEN", cookie.getValue())
            .header("X-XSRF-TOKEN", cookie.getValue())
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue(new CookieCsrfWebFluxDemo.NoteRequest("allowed"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.acceptedBy").isEqualTo("learner")
            .jsonPath("$.text").isEqualTo("allowed");
    }

    @Test
    void safeGetDoesNotNeedCsrfHeader() {
        client.get().uri("/api/me")
            .headers(h -> h.setBasicAuth("learner", "demo-pass"))
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.username").isEqualTo("learner");
    }
}
~~~

Run:

~~~bash
gradle test
~~~

Or `./gradlew test` / `gradlew.bat test` with the wrapper. Four tests are expected to pass **when** the code/dependencies/config above run properly; actual execution is required to confirm. In these tests, Basic auth only proves authentication works independently of the CSRF cookie; in real browsers, form login + session cookies represent the primary CSRF context.

### 8.1. What else should you test for stronger security?

The test suite above is only a baseline. Before production, add tests verifying:

1. After form login, the old CSRF cookie is cleared/rotated properly and the client obtains a fresh token.
2. After logout, the previous token is not accepted in violation of policy; the token endpoint can issue a new one if needed.
3. A POST with a valid token yet **unauthenticated** is blocked by the authentication policy.
4. A valid token with a user lacking the required role is still rejected by authorization.
5. Cross-origin POSTs lacking the custom header return 403; CORS preflights are not overly permissive.
6. Multiple browser tabs with rotated tokens behave cleanly on retry/refresh.
7. Cookie `Path`/`Domain`/`Secure`/`SameSite` match the real origin behind reverse proxies/TLS termination.
8. CSRF 403s are distinguished in server audit logs from role-denied 403s without exposing token details to callers.

Never treat a single `POST 200` test as proof against all CSRF/XSS; test your threat model, CORS, and cookie injection separately.

## 9. CORS, cross-origin SPAs, and cookie pitfalls

The main example is **same-origin**: the page is served from `localhost:8080` and the API is also at `localhost:8080`. That is the simplest model for reading `XSRF-TOKEN` and sending custom headers.

If the SPA lives at `https://ui.example.test` and the API at `https://api.example.test`:

- The two addresses are **cross-origin** (scheme/host/port), even if same-site under SameSite rules.
- JS at the UI origin cannot by default read the API's host-only cookie via `document.cookie`.
- `fetch(..., {credentials:"include"})` only asks the browser to send credentials per policy; it **does not** grant JavaScript permission to read another origin's cookies.
- The `X-XSRF-TOKEN` header and JSON Content-Type can trigger a **CORS preflight**. The server must allowlist the specific origin, methods, and headers; credentialed CORS must never use `Access-Control-Allow-Origin: *`.
- If genuinely using third-party cookies, modern browser restrictions may block them; `SameSite=None` requires `Secure`, yet does not guarantee third-party cookies always work.
- Consider a BFF/reverse-proxy pattern so UI and API share an origin, or a controlled authenticated-CORS CSRF token endpoint; verify tokens are not leaked via public cross-origin APIs.
- Never share CSRF cookies across all subdomains solely to bypass Same-Origin Policy without assessing subdomain takeover/cookie tossing.

### 9.1. CORS is not complete CSRF protection

CORS mainly restricts **JavaScript on another origin from reading responses and sending non-simple requests**; browsers can still send some cross-origin form/navigation requests. Therefore never say "CORS is enabled so CSRF isn't needed". CSRF tokens/Origin checking/SameSite and server-side boundaries must still be evaluated per auth model.

### 9.2. Cookie injection and double-submit

When the expected token resides in a cookie, systems must consider scenarios where an attacker can **set/overwrite a cookie with the same name** via a compromised subdomain, overly broad `Domain`, or related flaws. Defensive strategies can include:

- Avoid shared `Domain` unless genuinely necessary; prefer **host-only cookies**.
- In HTTPS production, consider the `__Host-` cookie prefix (requiring `Secure`, `Path=/`, and **no `Domain`**) with matching JS naming; configure both the repository and JS code to use the exact same name.
- Check `Origin`/`Referer` and `Sec-Fetch-Site` when appropriate for your threat model, without replacing tokens with an unverified custom header.
- Never let an untrusted proxy copy raw cookies into CSRF request headers on every request.
- For high-risk apps, consider session-bound synchronizer tokens or signed, session-bound double-submit designs if architecture allows.

**A CSRF token cookie is not an XSS defense.** Same-origin XSS can usually read non-HttpOnly cookies and submit arbitrary requests. Both defenses must operate side by side.

## 10. HttpOnly, Secure, SameSite, Path: how to choose?

| Attribute | Recommendation for XSRF-TOKEN in same-origin SPA | Notes |
|---|---|---|
| `HttpOnly` | `false` **if JS genuinely must read the cookie** | If JS does not need to read it, keep `true` via `new CookieServerCsrfTokenRepository()`. |
| `Secure` | `true` on HTTPS production | Local HTTP demos may omit it; production needs proper end-to-end TLS. |
| `SameSite` | Usually `Lax` or `Strict` per UX | Cross-site architectures may require `None; Secure`, with trade-offs. |
| `Path` | `/` if JS/APIs span multiple routes on the same host | Narrow paths can hide the cookie from JS on the current page. |
| `Domain` | Prefer **omitted** (host-only) | Overly broad domains enlarge cookie-injection surface. |
| `Max-Age` | Aligned with token lifecycle; consider session/login/logout | Avoid excessively long-lived tokens if policy requires rotation. |

**Never set `HttpOnly=false` on the session cookie just because the CSRF cookie needs JS access.** `SESSION` holds the login session identifier and should remain `HttpOnly`. The two cookies serve different purposes.

**Never set `Secure=false` in HTTPS production** to work around CORS errors or "missing cookies". Inspect proxy/TLS setup, domain/path, and browser policies instead.

## 11. Common errors and how to resolve them

**Error 1 — `XSRF-TOKEN` cookie missing after GET.**

Possible causes include an unsubscribed deferred CSRF token, a GET endpoint bypassing the CSRF filter, a mismatched cookie path, or `Set-Cookie` blocked by proxy/browser. Fix: add `GET /csrf` subscribing to `Mono<CsrfToken>.then()`, inspect Network response `Set-Cookie`, and check `Path`/`Domain`/`Secure`/`SameSite`.

**Error 2 — Cookie present and matching raw header sent, yet still 403.**

In Spring Security 6.x, default `XorServerCsrfTokenRequestAttributeHandler` expects masked tokens in many scenarios. Use the raw-header + masked-form custom resolver as shown, or choose the plain handler while understanding the BREACH trade-off; test both valid and invalid POSTs.

**Error 3 — Sending only the cookie without `X-XSRF-TOKEN`.**

Cookies are auto-sent by browsers and do not prove active client intent. JS must add the token to the header on unsafe requests. `credentials:"same-origin"` does not create the CSRF header automatically.

**Error 4 — Putting the token inside a JSON field expecting Spring to parse it.**

The default repository reads from header `X-XSRF-TOKEN` or form parameter `_csrf`; JSON `{"_csrf":"..."}` is not parsed by `CsrfWebFilter` by default. Use the header.

**Error 5 — Not refreshing the token after login/logout.**

Authentication success/logout can clear the token, invalidating the old cookie. Before the next POST, `GET /csrf` to obtain a fresh token, and handle expired sessions or re-login cleanly.

**Error 6 — Setting `HttpOnly=true` and then reading `document.cookie`.**

JS cannot read `HttpOnly` cookies; use `withHttpOnlyFalse()` **only when needed**, or deliver tokens via meta tags/forms/API responses with proper security.

**Error 7 — Using Servlet's `CookieCsrfTokenRepository`.**

WebFlux requires `CookieServerCsrfTokenRepository`. The Servlet class takes `HttpServletRequest`/`Response` and is incompatible with reactive stacks.

**Error 8 — Disabling CSRF to fix 403.**

Doing so exposes browser cookie authentication to CSRF. Inspect the token source/header, request handler, cookie attributes, and security matchers first. Never use `csrf.disable()` as a long-term debugging workaround.

**Error 9 — Putting the token in a URL/query string.**

Tokens can leak into logs, history, analytics, and referrers. Use a custom header for JSON requests.

**Error 10 — Sending the token to every origin via an interceptor.**

If requests to untrusted domains also receive `X-XSRF-TOKEN`, the token leaks. Restrict origins explicitly using relative URLs or a host allowlist.

**Error 11 — Using a CORS wildcard with credentials.**

Credentialed CORS cannot use a wildcard origin; allowlist trusted origins and required methods/headers. CORS does not replace CSRF.

**Error 12 — Thinking a CSRF token authorizes any operation.**

CSRF only stops forged requests from other sites; business permissions are still enforced by Authentication + Authorization.

**Error 13 — Same-origin XSS is possible while relying solely on CSRF tokens.**

XSS can read non-HttpOnly cookies and issue requests. Enforce CSP/output encoding/dependency hygiene; never treat CSRF as an XSS defense.

**Error 14 — Calling `token.subscribe()` inside a controller.**

Can emit cookies/write responses at the wrong time, swallow errors, or race response commits. Return the reactive publisher via WebFlux.

**Error 15 — Confusing 401 and 403.**

Authenticated requests failing CSRF normally receive 403; unauthenticated requests hit the authentication entry point, returning 302 (form login) or 401 (Basic). Never handle every 403 by forcing re-login or infinitely retrying POSTs.

**Error 16 — State-changing GET bypassing CSRF.**

GET is a safe method by default; refactor the endpoint to an appropriate POST/PUT/PATCH/DELETE. Never rely on "the frontend only has the right button" for security.

**Error 17 — Duplicate cookie names across multiple paths/domains.**

JS may read the wrong cookie; design consistent host-only + `Path`, and consider the `__Host-` prefix over HTTPS.

**Error 18 — Reusing tokens across multiple accounts/sessions without evaluation.**

CSRF cookies have a lifecycle tied to login sessions and may require rotation; assess risk per threat model and ensure clients fetch new tokens when auth state changes.

## 12. Pre-production review checklist

1. Are cookies/sessions or browser auto-sent credentials actually used? Has the CSRF threat model been documented?
2. Is the cookie repository definitely WebFlux's **`CookieServerCsrfTokenRepository`**?
3. Does the client need to read the cookie? If yes, is `HttpOnly=false` applied only to `XSRF-TOKEN`, never `SESSION`?
4. Does the server emit the cookie after `GET /csrf` genuinely subscribes to the token `Mono`?
5. Does JS send the `X-XSRF-TOKEN` custom header on protected POST/PUT/PATCH/DELETE requests?
6. Do the `XSRF-TOKEN` cookie and header carry the same raw token matching the handler policy?
7. With Spring Security 6, are **raw headers** and **XOR-masked forms** handled distinctly?
8. Are missing/wrong CSRF tokens rejected 403, while valid tokens proceed to authorization?
9. Is a valid token with insufficient user authority still rejected 403 by authorization?
10. Does a valid token with an unauthenticated user still require authentication?
11. After login/logout, does the frontend refresh the token and handle session expiry/403 cleanly?
12. Are tokens kept out of URLs, logs, third-party requests, and cross-origin analytics?
13. Do cookies have `Path`, `Domain`, `SameSite`, and `Secure` suited to the real origin behind HTTPS/proxies?
14. Does CORS use an explicit allowlist, avoid wildcards with credentials, and allow the preflight header?
15. Are overly broad subdomain-shared cookies avoided unless needed, with cookie injection evaluated?
16. Are XSS defenses (CSP, output encoding) maintained without over-relying on CSRF?
17. Are HTTP safe methods free of business side effects?
18. Does all CSRF code compose reactive publishers properly without `block()` or manual `subscribe()`?
19. Do actual tests cover cookie+header happy paths, missing/wrong headers, login/logout refresh, and multi-tab flows?
20. Have you verified behavior in a real browser/HTTP client and checked differences among 302, 401, and 403?

## 13. Knowledge self-check

**1.** An `XSRF-TOKEN` cookie is auto-sent by the browser on POST. Is that enough CSRF protection?

**Answer:** No. Browsers auto-send cookies on both legitimate and forged requests; JS or a form must supply the token in a **header/form parameter** that an attacker cannot easily craft for the protected origin.

**2.** When should `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` be used?

**Answer:** When same-origin JS must read the cookie and resend the raw token in a header. If JS does not need to read it, prefer keeping the cookie `HttpOnly` to minimize XSS exposure.

**3.** What are the default cookie and header names?

**Answer:** Cookie `XSRF-TOKEN`, header `X-XSRF-TOKEN`. Default form parameter is `_csrf`.

**4.** Why can sending a raw token from a cookie with Spring Security 6's default XOR handler yield 403?

**Answer:** The XOR handler is built to decode masked tokens emitted to views; a raw cookie value is not a masked representation. Either a raw-header resolver or a plain handler (with its trade-off understood) is needed.

**5.** Does `GET /csrf` need to return a JSON body containing the token?

**Answer:** No. It can subscribe to `Mono<CsrfToken>` so the framework sets the cookie and returns 204; JS reads the non-HttpOnly cookie.

**6.** After login/logout, can the old token be reused indefinitely?

**Answer:** Do not assume so. CSRF tokens can be cleared/rotated, so the SPA must initialize/refresh the token cookie appropriately.

**7.** Does `credentials:"include"` let JavaScript at a UI origin read a host-only cookie from another API origin?

**Answer:** No. It affects whether the browser sends credentials per policy; it does not bypass `document.cookie`'s Same-Origin Policy.

**8.** Is a non-HttpOnly CSRF cookie equivalent to an identity-protecting session cookie?

**Answer:** No. The CSRF cookie validates request origin/intent; the session cookie authenticates the session and should stay `HttpOnly`. Still, XSS can read the CSRF token and submit requests, so XSS protection remains mandatory.

**9.** Why does a custom header defend against CSRF better than cookies alone?

**Answer:** Simple cross-origin requests can auto-attach cookies; custom headers require authorized JS execution (and a CORS preflight cross-origin), establishing an extra boundary against attackers who cannot read the token.

**10.** Does an API using Bearer tokens manually attached by JS on each request, with zero browser auto-sent credentials, still need CSRF?

**Answer:** Classic CSRF risk may be lower, though token storage, CORS, XSS, and any other cookies must still be assessed. Never disable CSRF app-wide solely because an API is called REST.

## Official References

- Spring Security 6.5 — CSRF for WebFlux (cookie repository, XOR handler, AJAX/JSON header): https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security 6.5 — `CookieServerCsrfTokenRepository` API (`withHttpOnlyFalse`, `setCookieCustomizer`): https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CookieServerCsrfTokenRepository.html
- Spring Security 6.5 — `ServerCsrfTokenRequestHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestHandler.html
- Spring Security 6.5 — `ServerCsrfTokenRequestAttributeHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRequestAttributeHandler.html
- Spring Security 6.5 — `XorServerCsrfTokenRequestAttributeHandler` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html
- Spring Security — `ServerHttpSecurity.CsrfSpec` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.CsrfSpec.html
- Spring Security — WebFlux Security: https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- Spring Security — Testing CSRF with WebTestClient: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- OWASP — Cross-Site Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
