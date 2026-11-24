# CSRF, CORS, and Cookies When Browser Clients Call a JSON Login Endpoint

## 1. Scope: JSON Login Using HTTP Sessions in Spring Security Servlet

A web application can have JavaScript call `POST /api/login` with a JSON body instead of submitting an HTML form. When the login request succeeds, the backend verifies username/password, saves `SecurityContext` into the HTTP session, and sends a session cookie (usually `JSESSIONID`). Subsequent API calls do not need to resend the password: the browser sends the cookie so the backend can locate the authenticated session.

Three distinct mechanisms interact simultaneously:

| Mechanism | What does it decide? | Common observable signs |
| --- | --- | --- |
| **CSRF** | Does a state-changing request relying on browser-attached credentials carry valid anti-forgery proof? | Token in header `X-CSRF-TOKEN`; missing/wrong usually returns 403. |
| **CORS** | Is JavaScript running on another **origin** permitted to send/read the request and response under browser policy? | `Origin`, `OPTIONS` preflight, `Access-Control-Allow-Origin`, `Access-Control-Allow-Credentials`. |
| **Session cookie** | Does the browser store and send the session ID to the backend; can the backend restore identity from that ID? | `Set-Cookie: JSESSIONID=...` and `Cookie: JSESSIONID=...`. |

**JSON does not automatically make requests immune to CSRF.** If authentication relies on session cookies, the browser normally attaches cookies automatically to matching requests; that is what makes CSRF an issue. Conversely, CORS is only a browser policy governing JavaScript access to responses; it is neither an authentication mechanism nor a guarantee against CSRF.

This lesson uses **Spring Boot 3.x, Spring Security 6.x, Java 17+, and Spring MVC/Servlet**. It assumes the JSON login endpoint maintains a login session. An API using Bearer tokens explicitly placed by the client in the `Authorization` header has a different threat model and must be evaluated separately; never assume that simply being JSON implies CSRF applies or does not apply.

## 2. Distinguish Origin and Site Before Configuring

An **origin** is the triple `scheme + host + port`. Thus:

- `http://localhost:5173` and `http://localhost:8080`: **different origins** (different ports) yet usually **same site**.
- `https://app.example.com` and `https://api.example.com`: **different origins** (different subdomains) yet same site if sharing scheme and registrable domain.
- `https://frontend.example.net` and `https://api.example.com`: different origins **and** different sites.

Browsers enforce **CORS by origin**, whereas the cookie `SameSite` attribute evaluates the **site** relationship (modern browsers typically consider the scheme as well, called *schemeful same-site*). Two consequences follow:

1. A client at `localhost:5173` calling backend `localhost:8080` still needs CORS configured, even though `SameSite=Lax` may not block the cookie because they are same-site.
2. A frontend on a completely different domain from the backend usually needs `SameSite=None; Secure` cookies to be sent via cross-site `fetch`, yet may still be blocked by browser third-party cookie restrictions; enabling CORS alone will not solve that.

Cookie `Domain` and `Path` determine which hosts/paths receive the cookie. A host-only cookie set by `api.example.com` is still sent to `api.example.com` when a frontend at `app.example.com` calls the API, provided other conditions allow; you do not need to set `Domain=.example.com` yourself. Setting a cookie for the entire parent domain can widen scope unnecessarily.

## 3. JSON Login Flow with Session Cookie and CSRF

Suppose the frontend runs on `http://localhost:5173` and the backend on `http://localhost:8080`.

~~~text
Frontend browser                 Spring Security / Backend
       |                                    |
       | GET /api/csrf                     |
       | credentials: include              |
       |----------------------------------->|
       |       create/read CSRF token       |
       |<-----------------------------------|
       | JSON: headerName + token           |
       | Set-Cookie: JSESSIONID=...         |
       |                                    |
       | OPTIONS /api/login (preflight)     |
       | Origin, Content-Type, X-CSRF-TOKEN |
       |----------------------------------->|
       |<-----------------------------------|
       | CORS allows origin/header/method   |
       |                                    |
       | POST /api/login                    |
       | Cookie: JSESSIONID=...             |
       | X-CSRF-TOKEN: <token>              |
       | Body: {"username":"alice",...}     |
       |----------------------------------->|
       | CSRF filter checks token           |
       | AuthenticationManager authenticates|
       | rotate session id, save SecurityContext|
       |<-----------------------------------|
       | 200 JSON + new session cookie (if needed)
       |                                    |
       | GET /api/csrf (new token)          |
       |----------------------------------->|
       |<-----------------------------------|
       |                                    |
       | GET /api/me + session cookie       |
       |----------------------------------->|
       |<-----------------------------------|
       | 200 {"username":"alice"}           |
~~~

**Why fetch a CSRF token before login?** Spring Security protects state-changing HTTP methods such as POST. Login itself is sensitive: a forged login request (*login CSRF*) can force a victim into an attacker-controlled account, causing them to inadvertently enter data into that account. Configuring `/api/login` with `permitAll()` only means **no prior login is required**; it **does not bypass `CsrfFilter`**.

**Why fetch a CSRF token again after login?** Under Spring Security's CSRF mechanism, `CsrfAuthenticationStrategy` can clear the old token upon successful authentication; `CsrfLogoutHandler` clears the token after logout. The client should request a fresh token before the next POST. Spring Security 6 also uses deferred tokens and BREACH protection, so never assume the token value is static or only needs to be fetched once for the app's entire lifetime.

## 4. What Is CSRF and When Does It Happen?

Suppose a user is already logged in to `https://api.example.com` via a session cookie. They visit a malicious page on another origin. That malicious page can trick the browser into sending a state-changing request to the API; whenever the browser automatically attaches the cookie, the backend may accept the request on behalf of the current user.

CSRF does not require the attacker to know the password or read an `HttpOnly` cookie. The defining characteristic of CSRF is **abusing credentials automatically attached by the browser**.

Logic example:

~~~text
Victim has a valid session cookie -> opens attacker's page
-> that page attempts to send an action to the target website
-> browser attaches cookie automatically if cookie policy permits
-> if server only checks cookie, the action may execute
-> CSRF token / proper Origin check can block forgery
~~~

Make one more distinction: a JSON request with `Content-Type: application/json` usually triggers a **CORS preflight** when sent cross-origin. That causes some JavaScript-initiated requests to be blocked before sending, yet it **does not replace CSRF protection**. You still must account for HTML forms, endpoints accepting simple content types, proxy configurations, untrusted same-site subdomains, and future behavior changes. On session-cookie systems, keep CSRF protection enabled for state-changing operations.

### 4.1. How Is the Token Verified?

In a typical Spring Security Servlet configuration:

1. The server generates or loads a token from `CsrfTokenRepository`; the default is typically `HttpSessionCsrfTokenRepository`.
2. The client obtains the token via an HTML page or a GET endpoint designed to issue the token.
3. For POST/PUT/PATCH/DELETE, JavaScript places the token in a header, typically `X-CSRF-TOKEN`.
4. `CsrfFilter` checks the request's token against the server's expected token **before the login controller is invoked**.
5. Missing, wrong, or expired tokens usually receive `403 Forbidden`, even when username/password are correct.

Never send anti-CSRF tokens in a URL query string: URLs can leak into history, `Referer`, or logs. In JSON APIs, a dedicated request header is the standard choice.

### 4.2. HttpSessionCsrfTokenRepository vs CookieCsrfTokenRepository

Two common token distribution strategies:

| | `HttpSessionCsrfTokenRepository` | `CookieCsrfTokenRepository` |
| --- | --- | --- |
| Where expected token is stored | Server-side HTTP session | Browser-side cookie |
| How the SPA obtains the token | GET `/api/csrf` returning JSON or server-rendered meta tag | SPA can read the `XSRF-TOKEN` cookie if configured non-`HttpOnly` |
| Header sent back | Typically `X-CSRF-TOKEN` | Typically `X-XSRF-TOKEN` |
| Spring Security 6 note | Token can be deferred and masked against BREACH | If JS sends the raw cookie value unmasked, configure the SPA request handler appropriately for BREACH |
| Preference in this example | **Used to avoid exposing the token in a JS-readable cookie** | Fits when an SPA framework expects an XSRF cookie mechanism; must be configured properly |

**`JSESSIONID` is not a CSRF token.** The session cookie should generally be `HttpOnly`; JavaScript does not need to read the session ID. The `GET /api/csrf` endpoint can return the CSRF token via JSON to JavaScript with appropriate access; the response should not be cached by shared caches and allowed origins must be restricted.

## 5. What Does CORS Do for Browser Fetch?

CORS is enforced by the browser when JavaScript at **origin A** calls a URL at **origin B**. The server declares allowed origins/methods/headers; the browser decides whether JavaScript may read the response or whether a preflighted request may proceed.

For the request:

~~~http
OPTIONS /api/login HTTP/1.1
Host: localhost:8080
Origin: http://localhost:5173
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

The backend might reply (illustrative):

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: http://localhost:5173
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Content-Type,X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
~~~

`OPTIONS` is the **preflight**: the browser queries policy before sending the POST. Preflight requests normally **carry no session cookie**, so Spring Security must handle CORS before the authentication layer; if OPTIONS is blocked for being "unauthenticated", the browser reports a CORS error even when the POST itself would be valid.

Key points to remember:

- `Access-Control-Allow-Origin` must match the **exact origin** when using credentials. Never pair `Access-Control-Allow-Credentials: true` with `Access-Control-Allow-Origin: *`.
- `Access-Control-Allow-Credentials: true` lets the browser expose credentialed CORS responses per policy; it **does not create cookies** and does not replace `credentials: "include"` on `fetch`.
- `Access-Control-Allow-Headers` must allow `Content-Type` and `X-CSRF-TOKEN` when the client sends them.
- CORS does not protect against requests from cURL or server-to-server apps: non-browser clients are not bound by browser CORS enforcement.
- Do not enable CORS globally for all origins just for local development. Restrict specifically to the needed origins, methods, headers, and endpoints.
- Even if JavaScript cannot read a response due to CORS, a simple request that was already dispatched can still mutate server state. **CORS is not an anti-CSRF firewall.**

## 6. Cookies: `HttpOnly`, `Secure`, `SameSite`, and Browser Policy

A session cookie should carry an unpredictable random ID; authentication state lives on the backend. After login, the server can rotate `JSESSIONID` to prevent session fixation. Simplified header example:

~~~http
Set-Cookie: JSESSIONID=<opaque-session-id>; Path=/; HttpOnly; Secure; SameSite=Lax
~~~

| Attribute | Practical meaning |
| --- | --- |
| `HttpOnly` | Prevents JavaScript from reading the cookie via `document.cookie`, reducing session-ID theft via XSS. The browser can still send the cookie in HTTP requests. |
| `Secure` | Sends the cookie only over HTTPS (some browsers grant an exception for `localhost`). Production must use HTTPS. |
| `SameSite=Strict` | Restricts cookies on cross-site requests more strictly, though it can impact navigation flows. |
| `SameSite=Lax` | Reduces cookie sending in many cross-site contexts; usually fits **same-site** frontend/backend. Does not replace CSRF tokens. |
| `SameSite=None; Secure` | Allows sending the cookie in cross-site contexts if browser/third-party cookie policy permits; requires HTTPS. |
| `Path` / `Domain` | Restricts which paths and hosts can receive the cookie; prefer an appropriately narrow scope. |
| `Max-Age` / `Expires` | Governs cookie lifetime; **does not guarantee the server session is still alive**. |

Browsers may block third-party cookies, partition cookies, or apply other privacy controls; hence **`SameSite=None` does not guarantee cross-site login works on every device**. If the product allows, deploying the SPA and API under the same site or using a same-origin backend-for-frontend/reverse proxy usually simplifies things.

**`HttpOnly` note:** do not use `document.cookie` to read `JSESSIONID`. JavaScript only needs:

~~~js
fetch("http://localhost:8080/api/me", {
  credentials: "include"
});
~~~

The browser decides whether to attach the cookie. On cross-origin requests, `fetch` defaults to `credentials: "same-origin"`, so if the frontend is on another port, you must set `"include"`. Even when set, cookies can still be blocked by `SameSite`, `Secure`, `Domain`, `Path`, third-party cookie policy, or browser settings.

You cannot read `Set-Cookie` via `response.headers.get("set-cookie")` in JavaScript: it is a forbidden response header protected by the browser. Inspect cookies via DevTools Network/Application or HTTP client tests; never try to manually set a `Cookie` header in `fetch`.

## 7. Spring Boot 3.x Example: JSON Login, Session Cookie, CSRF, and CORS

A **runnable** example using Spring Boot 3.x / Spring Security 6.x, Java 17+. The backend listens on default `localhost:8080`; the frontend dev server runs on `localhost:5173`. Account and password are dummy data for the demo only.

### 7.1. Dependencies and File Structure

In a project already configured with the Gradle Spring Boot plugin, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Three Java files (same package `com.example.jsonlogin`):

~~~text
src/main/java/com/example/jsonlogin/
├── JsonLoginApplication.java
├── SecurityConfig.java
└── AuthController.java
~~~

Create `JsonLoginApplication.java`:

~~~java
package com.example.jsonlogin;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class JsonLoginApplication {
    public static void main(String[] args) {
        SpringApplication.run(JsonLoginApplication.class, args);
    }
}
~~~

### 7.2. SecurityConfig.java

~~~java
package com.example.jsonlogin;

import java.util.List;

import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.session.ChangeSessionIdAuthenticationStrategy;
import org.springframework.security.web.authentication.session.CompositeSessionAuthenticationStrategy;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfAuthenticationStrategy;
import org.springframework.security.web.csrf.CsrfTokenRepository;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(
            HttpSecurity http,
            SecurityContextRepository contexts,
            CsrfTokenRepository tokens,
            CorsConfigurationSource corsSource) throws Exception {
        http
            .cors(cors -> cors.configurationSource(corsSource))
            .csrf(csrf -> csrf.csrfTokenRepository(tokens))
            .securityContext(sc -> sc.securityContextRepository(contexts))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.POST, "/api/login").permitAll()
                .anyRequest().authenticated())
            .formLogin(AbstractHttpConfigurer::disable)
            .httpBasic(AbstractHttpConfigurer::disable)
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint((req, res, ex) ->
                    res.sendError(HttpServletResponse.SC_UNAUTHORIZED)))
            .logout(logout -> logout
                .logoutUrl("/api/logout")
                .logoutSuccessHandler((req, res, auth) ->
                    res.setStatus(HttpServletResponse.SC_NO_CONTENT)));

        return http.build();
    }

    @Bean
    CsrfTokenRepository csrfTokenRepository() {
        return new HttpSessionCsrfTokenRepository();
    }

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SessionAuthenticationStrategy sessionAuthenticationStrategy(
            CsrfTokenRepository tokens) {
        return new CompositeSessionAuthenticationStrategy(List.of(
            new ChangeSessionIdAuthenticationStrategy(),
            new CsrfAuthenticationStrategy(tokens)
        ));
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("http://localhost:5173"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build()
        );
    }

    @Bean
    AuthenticationManager authenticationManager(
            UserDetailsService users,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider dao = new DaoAuthenticationProvider();
        dao.setUserDetailsService(users);
        dao.setPasswordEncoder(encoder);
        return new ProviderManager(dao);
    }
}
~~~

Explanation of security-impacting settings:

1. `csrf(csrf -> csrf.csrfTokenRepository(tokens))` keeps CSRF protection enabled, using `HttpSessionCsrfTokenRepository`. `POST /api/login` is `permitAll` yet still requires a token.
2. `cors(...configurationSource(...))` ensures CORS is handled through Spring Security; origin `localhost:5173` is explicitly allowed with credentials. When deploying, change it to the **real frontend HTTPS origin** (without a trailing `/`).
3. `securityContextRepository(contexts)` configures where Spring Security restores and saves authentication context, so the login controller can use the same repository when writing the session.
4. `IF_REQUIRED` allows a session when needed. **Do not use `STATELESS`** for a session-based login example.
5. `formLogin` and `httpBasic` are disabled because this endpoint handles login itself via a JSON body instead of form/Basic login filters. `POST /api/logout` is still handled by `LogoutFilter`.
6. `SessionAuthenticationStrategy` pairs session ID rotation (`ChangeSessionIdAuthenticationStrategy`) with clearing the old CSRF token after authentication (`CsrfAuthenticationStrategy`). Because the **controller authenticates manually**, we must invoke this strategy; in standard login filter mechanisms, Spring Security manages the corresponding steps.
7. `AuthenticationManager` uses `DaoAuthenticationProvider`, `UserDetailsService`, and BCrypt. Provider constructor/setter APIs vary/deprecate across Spring Security 6.x minor releases; the setter form here matches the 6.3 line in Spring Boot 3.3. Never copy demo passwords into real environments.

### 7.3. AuthController.java

~~~java
package com.example.jsonlogin;

import java.security.Principal;
import java.util.Map;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.session.SessionAuthenticationStrategy;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AuthController {

    private final AuthenticationManager manager;
    private final SecurityContextRepository contexts;
    private final SessionAuthenticationStrategy sessionStrategy;

    public AuthController(
            AuthenticationManager manager,
            SecurityContextRepository contexts,
            SessionAuthenticationStrategy sessionStrategy) {
        this.manager = manager;
        this.contexts = contexts;
        this.sessionStrategy = sessionStrategy;
    }

    public record LoginRequest(String username, String password) {}

    @GetMapping("/api/csrf")
    public CsrfToken csrf(CsrfToken token) {
        // Access the token to issue it to the client; GET requires no login.
        return token;
    }

    @PostMapping("/api/login")
    public ResponseEntity<Map<String, String>> login(
            @RequestBody LoginRequest input,
            HttpServletRequest request,
            HttpServletResponse response) {
        try {
            Authentication authentication = manager.authenticate(
                UsernamePasswordAuthenticationToken.unauthenticated(
                    input.username(), input.password()));

            sessionStrategy.onAuthentication(authentication, request, response);

            SecurityContext context =
                SecurityContextHolder.createEmptyContext();
            context.setAuthentication(authentication);
            SecurityContextHolder.setContext(context);
            contexts.saveContext(context, request, response);

            return ResponseEntity.ok(Map.of(
                "username", authentication.getName()));
        } catch (AuthenticationException ex) {
            return ResponseEntity.status(HttpStatus.UNAUTHORIZED)
                .body(Map.of("error", "invalid_credentials"));
        }
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Principal principal) {
        return Map.of("username", principal.getName());
    }
}
~~~

**Why is `saveContext` required?** Starting in Spring Security 6, when authenticating manually inside a controller, placing `Authentication` in `SecurityContextHolder` only helps the current request. For the next request to have identity via the session, you must persist `SecurityContext` using `SecurityContextRepository`. If you skip this step, `POST /api/login` may report success while the subsequent `GET /api/me` returns 401.

**Why not return `JSESSIONID` directly in JSON?** The backend sends the session cookie via `Set-Cookie`. JavaScript does not need to receive or store the session ID in `localStorage`. Putting the session ID in JSON and attaching headers manually can defeat `HttpOnly` protection and increase session exposure risk.

**Why not handle POST logout manually in the controller?** Configuring `logoutUrl("/api/logout")` routes logout through `LogoutFilter`, which already includes standard handlers to clear the context and invalidate the session. The controller only handles `/api/login` and `/api/csrf`; do not create a duplicate logout endpoint.

**Demo limitations:** Any real login system needs policies for passwords, sessions, user management, rate limiting, lockouts/backoff, secure logging, timeouts, and exception handling. This example illustrates **CSRF-CORS-cookies** accurately, not a complete account management system. The Java source depends on Spring Boot/Security so run it via Gradle, not `javac` without the classpath.

### 7.4. Cookie Configuration for Development and Production

Use Spring Boot defaults for testing on `localhost`. When deploying over HTTPS, you can configure `src/main/resources/application-prod.properties`:

~~~properties
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.secure=true
server.servlet.session.cookie.same-site=lax
~~~

`lax` fits when the SPA and API are **same-site** (e.g., `https://app.example.com` -> `https://api.example.com`), even if different origins still needing CORS. If the two sides are **truly cross-site** and rely on cross-site cookies, consider `same-site=none` with `secure=true`, test browser privacy restrictions, and evaluate deploying frontend/backend under the same site. Do not arbitrarily apply production `Secure=true` cookie settings over HTTP and then conclude the API fails to create sessions; browsers reject/send cookies differently depending on the environment.

Behind a reverse proxy, ensure the application recognizes public HTTPS properly and the proxy does not strip `Set-Cookie`. Never widen the session cookie `Domain` without a clear reason.

## 8. JavaScript Fetch: Initializing CSRF, Logging In, Calling APIs, and Logging Out

Example running from a frontend page at `http://localhost:5173`. `fetch` will not include cookies on cross-origin requests without `credentials: "include"`.

~~~js
const API = "http://localhost:8080";

async function csrfToken() {
  const response = await fetch(API + "/api/csrf", {
    method: "GET",
    credentials: "include",
    cache: "no-store"
  });
  if (!response.ok) throw new Error("Cannot obtain CSRF token");
  return response.json(); // { headerName, parameterName, token }
}

async function login(username, password) {
  const csrf = await csrfToken();
  const response = await fetch(API + "/api/login", {
    method: "POST",
    mode: "cors",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      [csrf.headerName]: csrf.token
    },
    body: JSON.stringify({ username, password })
  });
  if (!response.ok) {
    throw new Error("Login failed: HTTP " + response.status);
  }

  const user = await response.json();
  // Authentication changed the session/token; fetch a new token for subsequent POSTs.
  await csrfToken();
  return user;
}

async function currentUser() {
  const response = await fetch(API + "/api/me", {
    method: "GET",
    credentials: "include"
  });
  if (!response.ok) {
    throw new Error("Not authenticated: HTTP " + response.status);
  }
  return response.json();
}

async function logout() {
  const csrf = await csrfToken();
  const response = await fetch(API + "/api/logout", {
    method: "POST",
    credentials: "include",
    headers: { [csrf.headerName]: csrf.token }
  });
  if (!response.ok) {
    throw new Error("Logout failed: HTTP " + response.status);
  }
  // A new CSRF token may be issued for the unauthenticated user.
  await csrfToken();
}

// Example from real UI actions; never log passwords to the console.
// const user = await login("alice", "demo-pass");
// const profile = await currentUser();
// await logout();
~~~

Critical points:

- `credentials: "include"` must apply to **all** of `GET /api/csrf`, `POST /api/login`, `GET /api/me`, and `POST /api/logout` across different origins; if POST includes it while `GET /csrf` does not keep the session cookie, the token easily mismatches the session.
- `Content-Type: application/json` and `X-CSRF-TOKEN` are non-simple request headers, typically triggering preflight; the backend must allow them.
- The returned `CsrfToken` contains `headerName` and `token`; use the exact name/value rather than hardcoding and causing mismatches.
- `Set-Cookie` may appear in DevTools, yet JS cannot read the session cookie if `HttpOnly`. Not being able to read the cookie via JavaScript is a **protective behavior**, not evidence that login failed.
- Never log CSRF tokens, passwords, or session cookies to the console/logs. A CSRF token protects requests; it is not a password, yet it should not be exposed unnecessarily.
- When a CSRF token expires or the session is invalidated, fetch a fresh token via GET and ask the user to log in again if needed. Never infinitely auto-retry sensitive POSTs.

## 9. Troubleshooting 401, 403, and "CORS error" by Root Cause

| Symptom | Causes to check | Action |
| --- | --- | --- |
| `POST /api/login` returns **403** despite right credentials | Missing/wrong CSRF token, token tied to another session, or expired | GET `/api/csrf` with same-session cookie, resend correct header; check session and CSRF. |
| `POST /api/login` returns **401** | Username/password rejected by `AuthenticationManager` | Check demo credentials, encoder, user status; do not leak account details. |
| Login **200** yet `GET /api/me` **401** | Cookie not stored/sent, session ID rotated, or `SecurityContext` not saved | Check `Set-Cookie`, request `Cookie`, `credentials`, SameSite/Secure, `saveContext`. |
| Browser reports **CORS blocked** | Origin not allowed, missing Allow-Headers/Methods/Credentials, preflight got 401/403 | Inspect **Network -> OPTIONS** and response headers; handle CORS before auth. |
| `POST /api/logout` returns **403** | Missing/stale CSRF token, or already logged out/session expired | Call GET CSRF for a fresh token, send proper POST; check cookie and session. |
| Browser shows `JSESSIONID` yet JS cannot read it | Cookie has `HttpOnly` | This is proper design; use `credentials: "include"`. |
| Works on localhost, production domain drops session | HTTPS, SameSite, third-party cookies, proxy, cookie Domain/Path | Test against the real origin/site in target browsers. |
| `OPTIONS` succeeds yet POST fails | CORS allowed the request, but CSRF/authentication/backend failed | Check status and server logs of the **POST**, do not treat it as a CORS error. |

**401 and 403 are not interchangeable.** In the example, invalid credentials return 401, missing CSRF returns 403 from the filter before the controller, and unauthenticated `GET /api/me` returns 401 via the entry point. A CORS failure may appear in the console as a network error where JS cannot read the actual response; inspecting Network distinguishes it from HTTP 403.

## 10. Manual Testing with Browser and curl

### 10.1. Start the Backend

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`. Make sure the frontend is running at `http://localhost:5173` or adjust `setAllowedOrigins(...)` to the actual origin.

Open DevTools -> Network and perform login in order: `/api/csrf` -> `OPTIONS` preflight (if any) -> `POST /api/login` -> `/api/csrf` -> `GET /api/me`. Verify:

1. **GET /api/csrf:** returns JSON containing `token` and may create `JSESSIONID`. In Network/Application, did the browser actually accept the cookie?
2. **OPTIONS /api/login:** preflight is allowed before authentication; has exact `Access-Control-Allow-Origin`, matching `Allow-Headers`, and `Allow-Credentials: true`?
3. **POST /api/login:** includes `Origin`, `Content-Type: application/json`, CSRF header, and required request cookie? Returns 200 and maintains the post-auth session?
4. **GET /api/me:** request sends the session cookie and returns `{"username":"alice"}`?
5. **POST /api/logout:** valid token, returns 204; afterward `GET /api/me` with the old cookie no longer represents the user -> 401?

To tell **CORS** apart from **CSRF**, try calling POST from the frontend while intentionally omitting the CSRF header: preflight/credentials may still be valid, yet Spring Security blocks the POST with 403. Try changing `allowedOrigins` to a wrong origin: JavaScript is blocked by CORS, potentially before the POST. Never use intentionally broken configurations in production.

### 10.2. cURL Proving CSRF Is Not CORS

cURL is not subject to browser CORS enforcement, yet is still subject to server-side CSRF. Use a cookie jar and real token content:

~~~bash
# Fetch CSRF JSON and save cookie into jar (demo account only).
curl -i -c cookies.txt http://localhost:8080/api/csrf

# Login with JSON but WITHOUT sending CSRF token: expected HTTP 403.
curl -i -b cookies.txt -c cookies.txt \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"demo-pass"}' \
  http://localhost:8080/api/login
~~~

Note that the first command prints the token; to log in successfully, take the `token` field value from the JSON received and attach the `X-CSRF-TOKEN` header along with the cookie jar:

~~~bash
curl -i -b cookies.txt -c cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-TOKEN: <token-from-previous-json>" \
  -d '{"username":"alice","password":"demo-pass"}' \
  http://localhost:8080/api/login
~~~

`<token-from-previous-json>` is a placeholder, do not run it verbatim: replace it with the actual token received. This command **illustrates a manual step**, with no fixed output because tokens are random. When running in PowerShell, you can use `curl.exe`; adjust quotes to match the shell. Never save real cookies/tokens/passwords to files or shell history outside a controlled environment.

A subsequent GET CSRF after login returns a new token if the prior one was cleared. To check the session, continue calling `GET /api/me` with `-b cookies.txt`. If it returns 401, inspect the cookie jar, session ID, session timeout, and the `saveContext` step.

### 10.3. Minimum QA Matrix

| Case | Condition | Expected outcome |
| --- | --- | --- |
| CSRF-01 | Login POST without CSRF header | 403, login controller not invoked. |
| CSRF-02 | Valid CSRF header yet cookie belongs to another session | 403. |
| LOGIN-01 | Login POST with valid CSRF, wrong password | 401, no login identity created. |
| LOGIN-02 | Login POST with valid CSRF, valid demo credentials | 200; session persists `SecurityContext`. |
| SESSION-01 | `GET /api/me` after login, sending session cookie | 200, returns user. |
| SESSION-02 | `GET /api/me` without cookie after login | 401. |
| CORS-01 | Origin `http://localhost:5173` | Preflight/response allow origin and credentials. |
| CORS-02 | Origin not in allowedOrigins | Browser blocked by CORS. |
| LOGOUT-01 | Logout POST missing CSRF | 403. |
| LOGOUT-02 | Logout POST with valid CSRF | 204; login session invalidated. |
| LOGOUT-03 | `GET /api/me` after logout | 401. |
| COOKIE-01 | `HttpOnly` cookie | Session ID unreadable via JavaScript; browser still sends it automatically when permitted. |
| DEPLOY-01 | Production HTTPS frontend/backend | `Secure` and `SameSite` match site relationship, login maintains session. |

## 11. Mistakes That Easily Create Vulnerabilities or Hard-to-Debug Bugs

1. **Disabling CSRF with `csrf.disable()` just because requests are JSON.** With session cookies sent automatically by browsers, this can open the door to login CSRF, logout CSRF, and other forged actions. Only adjust based on a real, evaluated credential model.
2. **Putting `/api/login` in `permitAll` and assuming CSRF is bypassed.** `permitAll` belongs to authorization, while `CsrfFilter` handles POSTs separately. A 403 before the controller does not necessarily mean wrong password.
3. **Using `Access-Control-Allow-Origin: *` with credentials.** Credentialed CORS requires an explicit origin; wildcards are invalid when `Access-Control-Allow-Credentials: true`.
4. **Failing to handle preflight because OPTIONS carries no cookie.** Preflights inherently carry no login session. CORS must be processed before security auth.
5. **Missing `credentials: "include"` on one of the requests.** Fetching a CSRF token in session A while login POST creates session B easily causes 403; login 200 yet `/me` 401 can happen because the cookie stops being sent.
6. **Not rotating the CSRF token after authentication/logout.** Once Spring Security clears the old token, the next POST receives 403 until the client fetches a new token.
7. **Using `SameSite=None` without `Secure`**, or using cross-site configuration when the product can actually be deployed same-site. Modern browsers can reject misconfigured cookies.
8. **Setting `HttpOnly=false` on `JSESSIONID` so JavaScript can read it.** Unnecessary; expands session-ID exposure via XSS. Distinguish session cookies from CSRF cookies.
9. **Returning JSON login success while forgetting `SecurityContextRepository.saveContext`.** The login request can succeed while the next request loses authentication.
10. **Forgetting session fixation protection in a custom login controller.** Default Spring Security filters integrate session handling; manual auth in a controller must invoke the corresponding strategy, such as `ChangeSessionIdAuthenticationStrategy`.
11. **Believing CORS protects the server from every other source.** cURL, server-to-server clients, and simple HTML forms are not governed by JavaScript's CORS response-reading rules like `fetch`.
12. **Accidentally logging sensitive data.** Never log plaintext passwords, session cookies, full `Set-Cookie` headers, or CSRF tokens in logs/traces. Enable HTTPS, secure cookies, login rate limits, and generic error messages.

## 12. Design Summary

For session-based browser JSON login, keep the chain of responsibility clear:

~~~text
Browser fetch + credentials: include
           |
           +-- CORS checks whether the JavaScript origin is allowed
           |
           +-- Cookie policy decides whether the browser sends the session ID
           |
           +-- CsrfFilter checks token for unsafe methods
           |
           +-- AuthenticationManager verifies username/password at login
           |
           +-- SessionAuthenticationStrategy prevents session fixation,
           |                           handles CSRF token upon successful auth
           |
           +-- SecurityContextRepository saves/restores Authentication
           |
           +-- AuthorizationFilter decides endpoint permissions
~~~

**Design checklist:** use HTTPS; appropriate `HttpOnly` and `Secure` cookies; `SameSite` matching the actual site relationship; CORS allowlist of explicit origins and proper credentials; CSRF enabled for login/logout POSTs and state-changing actions; fetch/rotate tokens per lifecycle; save SecurityContext and rotate session ID after login; logout invalidates the session; verify 401/403/preflight/session via DevTools.

### References

- Spring Security Reference — CSRF (Servlet): https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security Reference — CORS (Servlet): https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security Reference — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security Reference — Logout: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- MDN — Fetch API credentials: https://developer.mozilla.org/en-US/docs/Web/API/Request/credentials
- MDN — Set-Cookie attributes: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie
