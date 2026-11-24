# Investigating Lost Logins Caused by Cookies, Sessions, or Unsaved Context

> **Context:** Spring Security — fundamentals / Observability and Debugging. This guide addresses *login succeeding yet the very next request being treated as unauthenticated*, focusing on **Servlet** applications using **session cookies + HttpSession + SecurityContextRepository**. The full example uses Java 17+, Spring Boot 3.5.0, and Spring Security 6.x. A separate section explains why stateless JWT/HTTP Basic apps do not necessarily persist sessions.

## 1. Identifying the Exact Symptom

The problematic sequence is typically:

1. The user submits username/password and gets a success response; the server may return `302` to redirect.
2. The user navigates or refreshes.
3. `GET /api/me` returns `401`, the browser gets redirected back to `/login`, or the SPA displays an anonymous state.

**Do not jump to the conclusion that the session was lost.** A `403` can come from missing authority or CSRF; a `302` redirect can occur because a request is unauthenticated, yet a login response can also redirect on success. Seeing `JSESSIONID` also does not prove the user logged in: a session can exist solely to hold a CSRF token or saved request.

Three layers must be checked in exact order:

| Layer | Question | If It Fails |
|---|---|---|
| **Client-side cookie** | Did the server issue the right cookie and did the browser send the current cookie back? | Browser/client does not carry a session identifier to the server |
| **Server-side session** | Does the cookie map to an active `HttpSession` on the right instance/store? | Cookie exists, yet session timed out, was invalidated, restarted, or was lost across nodes |
| **Spring Security context** | Did `SecurityContextRepository` save and restore the verified `Authentication` for the next request? | Session exists, yet Spring Security treats the user as anonymous |

**Investigation goal:** capture evidence from at least **two consecutive HTTP requests**: the login and the request immediately after login. Fix only the link identified as broken; do not disable protections to make the error vanish.

## 2. Lifecycle of a Login Session

~~~mermaid
sequenceDiagram
    participant C as Client
    participant S as Spring Security
    participant R as SecurityContextRepository
    participant H as HttpSession
    C->>S: POST /login + credentials + CSRF
    S->>S: Authenticate via AuthenticationManager
    S->>S: Create SecurityContext holding Authentication
    S->>R: saveContext(context, request, response)
    R->>H: Store context in session
    S-->>C: 302 + Set-Cookie session ID
    Note over C,S: Session ID may rotate to prevent session fixation
    C->>S: GET /api/me + Cookie with new session ID
    S->>R: load context for new request
    R->>H: Retrieve session by ID
    H-->>R: Saved SecurityContext
    R-->>S: User's Authentication
    S-->>C: 200: verified principal
~~~

`SecurityContextHolder` is **not session storage**. In the Servlet stack, the context is bound to the request-processing thread by default; Spring Security clears the context when the request finishes so identity does not leak to another thread or request. Thus, seeing `SecurityContextHolder` empty after a request **is not a bug**. What must be verified is whether the repository saved and reloaded the context.

Three things frequently confused:

- **`JSESSIONID` cookie**: the identifier referencing a session; the name can be reconfigured (or `SESSION` with Spring Session).
- **`HttpSession`**: where the servlet container/session store holds data across multiple requests.
- **`SecurityContext`**: holds the authenticated `Authentication`, normally linked to the session by the repository.

A session created to store `CsrfToken` can exist **before login**. After login, the ID may change due to session fixation protection; the client must update to the latest cookie.

## 3. Root-Cause Isolation Table

| Evidence | Top Hypothesis | Next Check |
|---|---|---|
| Login `302`, next request lacks `Cookie` | `SameSite`, `Secure`, `Path`, `Domain`, cookie blocked/expired, missing `fetch.credentials` | DevTools → Network/Cookies → blocked reasons; compare host, scheme, origin |
| `Cookie` present, `getSession(false)` is null | Session timeout, logout/invalidate, restart, session store not shared across nodes | TTL, session store, node A/B, logout events, cookie ID after login |
| Session exists, no saved `SecurityContext` | Custom login forgot `saveContext`, `NullSecurityContextRepository`, `STATELESS`, mismatched repo | Login success code, chain's repository, session policy |
| Context exists yet Authentication is anonymous | Login failed; context overwritten/cleared; concurrent-session handling | Authentication events, failure handler, logout, principal |
| Authentication valid yet `403` | Missing authority or CSRF; not necessarily lost login | `authorizeHttpRequests` rules, `@PreAuthorize`, CSRF |
| Curl with cookie jar works, browser fails | Cookie policy or cross-origin/CORS in browser | `Set-Cookie`/cookie policy, fetch credentials, frontend URL |
| Works intermittently behind load balancer | Per-node in-memory sessions without a shared store | Instance ID, Spring Session/Redis/JDBC, affinity |
| Bearer request has no session yet succeeds | Stateless behavior by design | JWT/Basic request credentials, `SessionCreationPolicy` |

`401 Unauthorized` usually means no valid credentials for an API; `302` can be a form-login redirect; `403 Forbidden` can occur when an authenticated user lacks authority or a CSRF token. Never conflate these three responses.

## 4. Investigating in the Browser Across Two HTTP Exchanges

Enable **Network → Preserve log** in DevTools, perform a login, then call the protected API. Record the following fields, while **never storing raw cookie/token values**:

1. Login request: URL, method, scheme/host/port, status, and `Location` if redirected.
2. Login response: whether `Set-Cookie` is present, cookie name, `Secure`, `HttpOnly`, `SameSite`, `Path`, `Domain`, `Max-Age/Expires`. Sometimes the cookie was already created by an earlier pre-login CSRF request.
3. Application → Cookies: did the browser actually store the cookie? Is there a "blocked reason" or a domain/path mismatch with the API?
4. **Next** request `GET /api/me`: does it carry a `Cookie` header with the latest cookie? Did the request go to the right API host?
5. Post-login response: actual HTTP status, redirect headers, body, server logs. If the request carried the cookie, check session lookup and SecurityContext loading.
6. With multiple nodes, record **the node serving login and the node serving the follow-up request**.

Example headers with **secret values redacted**:

~~~http
HTTP/1.1 302 Found
Location: /
Set-Cookie: JSESSIONID=REDACTED; Path=/; HttpOnly; SameSite=Lax
~~~

Next request:

~~~http
GET /api/me HTTP/1.1
Host: localhost:8080
Cookie: JSESSIONID=REDACTED
~~~

If the cookie is missing on the second request, investigate client/cookie handling. If the cookie is sent yet the server finds no session, investigate the session store/timeout. If the session exists without an Authentication, investigate how `SecurityContext` is saved.

**Never print raw `Cookie`, `Set-Cookie`, session IDs, Bearer tokens, usernames/passwords, or CSRF tokens into logs or tickets.** Session cookies act as credentials; leaking their values risks session hijacking.

## 5. Cookie Attributes and Reasons Browsers Drop Them

### Domain, Host, and Path

A host-only cookie is sent only to the exact host that set it. `api.example.com` and `web.example.com` are not the same host. `localhost` and `127.0.0.1` are two distinct hosts. `Domain=example.com` can widen scope to valid subdomains, though it should not be set broader than necessary.

A `Path=/app` cookie is not automatically sent to `/api/me`; if a reverse proxy changes the context path or fails to align `Set-Cookie Path`, requests may omit the cookie. Port is not part of cookie scope, **but it does affect origin/CORS**.

### Secure

A `Secure` cookie is sent only over secure connections per browser rules; some browsers exempt `localhost`, yet production must never rely on that. If the login page uses HTTPS while the API uses HTTP, the session cookie may not be sent. **Use HTTPS consistently and configure proxies properly** instead of turning off `Secure` in production.

### HttpOnly

`HttpOnly` hides a cookie from ordinary JavaScript (`document.cookie`), without preventing the browser from sending the cookie automatically on eligible HTTP requests. Thus "I cannot see JSESSIONID in `document.cookie`" **does not mean the cookie vanished**. Inspect DevTools Storage/Network; never disable `HttpOnly`.

### SameSite

- `Strict`: restricts the cookie on many cross-site requests.
- `Lax`: usually fits standard navigating web apps; cross-site `fetch` POSTs or subresources may omit the cookie.
- `None`: allows cross-site cases per browser policy, but requires `Secure`; third-party cookie blocking/partitioning can still interfere.

**Same-site is not same-origin.** `https://app.example.com` and `https://api.example.com` may be same-site yet remain two different origins; `http://localhost:3000` and `http://localhost:8080` are different origins because of the port.

### Max-Age/Expires vs. Session Timeout

Cookies with `Max-Age` or `Expires` can be purged by the browser when expired. Session cookies without an explicit expiration normally depend on the browser lifecycle (some browsers restore sessions). **Server session timeout** is a separate setting: the cookie may still exist on the client after the server evicted the session. Logout, concurrent-session limits, or invalidation events can also terminate a session.

## 6. SPAs, CORS, and Credentials: Cookie Exists Yet API Requests Omit It

Suppose the frontend is at `https://web.example.com` and the backend is at `https://api.example.com`. Because those are **two different origins**, browser requests must align `fetch`, CORS, and cookies:

~~~javascript
// Runs on the frontend, not a standalone Java program.
const response = await fetch("https://api.example.com/api/me", {
  method: "GET",
  credentials: "include"
});
~~~

Independent prerequisites:

1. `credentials: "include"` tells the browser to send cookies on cross-origin requests when permitted.
2. The server must return matching CORS headers: a **specific** origin and `Access-Control-Allow-Credentials: true` when credentials are allowed. `Access-Control-Allow-Origin: *` is invalid for credentialed responses.
3. The cookie must satisfy Domain/Path/Secure/SameSite and not be blocked by browser policies.
4. The backend must still hold a valid session/context.

If the API sets `SameSite=None` without `Secure`, the browser can refuse to store it. If frontend code calls `fetch("/api/me")` on `web.example.com` without a matching proxy, it sends the request to **web**, not **api**. Check the actual Request URL before changing the backend.

**CORS is not CSRF protection.** Browser cookies can be sent automatically on cross-site requests in attack scenarios; state-changing endpoints need CSRF protection or an alternative risk-assessed design.

## 7. Spring Security 6: Who Saves and Who Loads SecurityContext?

Three roles exist:

- `SecurityContextHolder`: the context active for the current request, usually `ThreadLocal`.
- `SecurityContextRepository`: the persistence mechanism to save/load context.
- `Authentication`: the authenticated principal and authorities stored inside `SecurityContext`.

Key implementations:

| Repository | Purpose | Remembers Login Across Requests? |
|---|---|---|
| `HttpSessionSecurityContextRepository` | Binds context to `HttpSession` | **Yes**, if session remains and client sends the right cookie |
| `RequestAttributeSecurityContextRepository` | Preserves context across dispatches of the **same request**, e.g., error dispatch | **No** for a separate subsequent HTTP request |
| `DelegatingSecurityContextRepository` | Delegates load/save to multiple repositories; often combines the two above | **Yes** if it includes a session-backed repository |
| `NullSecurityContextRepository` | Does not save context | **No**, used when stateless is desired |

Spring Security 6 defaults to a `DelegatingSecurityContextRepository` combining request-attribute and HTTP-session repositories in standard Servlet configurations.

### SecurityContextHolderFilter and Explicit Save

`SecurityContextHolderFilter` **loads the context** but **does not automatically save** it at the end of the request. If you write a custom login filter or controller, never assume calling `SecurityContextHolder.setContext(...)` alone creates a persistent login session. An older mechanism like `SecurityContextPersistenceFilter` could auto-detect/save context at request end; do not assume your Spring Security 6 app still behaves that way.

Illustrative code for custom session authentication:

~~~java
// Code snippet: requires AuthenticationManager, repository, and Servlet request/response.
// "candidate" is an UNAUTHENTICATED Authentication built from client input.
Authentication verified = authenticationManager.authenticate(candidate);

SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

// Save before sending redirect / committing response.
securityContextRepository.saveContext(context, request, response);
response.sendRedirect("/dashboard");
~~~

This is **not a standalone class**. Production custom logins must also handle `SessionAuthenticationStrategy`/session fixation, CSRF, success/failure handlers, remember-me if used, and share the exact same repository as the filter chain on subsequent requests. If you only need standard form login, use **Spring Security's built-in `formLogin()`** instead of reimplementing this flow.

### SessionCreationPolicy

| Policy | Core Behavior |
|---|---|
| `ALWAYS` | Spring Security proactively creates an `HttpSession` |
| `IF_REQUIRED` | Spring Security creates a session only when actually needed; fits session login |
| `NEVER` | Does not create one itself, but can use an existing session |
| `STATELESS` | Does not create or use a session to obtain `SecurityContext` for Spring Security |

`STATELESS` does not mean "JSESSIONID can never exist under any circumstance"; other libraries or servlet code can still create a session. However, it does not satisfy traditional form-login's requirement to "automatically restore Authentication from the session on the next request."

If your auth mechanism is stateless JWT/HTTP Basic, rebuilding `Authentication` on every request is **normal**. Do not force session persistence when the product does not call for it.

## 8. Runnable Java 17 Example: formLogin and an Identity Check Endpoint

Goal: build a **runnable baseline** to compare against a failing application. Spring Security handles form login, session fixation protection, and context saving; we expose `GET /api/me` requiring authentication and `GET /api/csrf` so curl can obtain a CSRF token.

Structure:

~~~text
session-debug-demo/
├── pom.xml
├── src/main/resources/application.properties
├── src/main/java/com/example/sessiondebug/
│   ├── SessionDebugApplication.java
│   ├── SecurityConfig.java
│   └── DiagnosticController.java
└── src/test/java/com/example/sessiondebug/
    └── SessionLoginTest.java
~~~

**Requirements:** JDK 17+, Maven 3.9+, internet access or cached Maven dependencies. Password `pw` and `{noop}` are **for localhost learning only**; never use them in production.

### 8.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>session-debug-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

### 8.2. application.properties

~~~properties
server.servlet.session.timeout=15m
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
spring.main.banner-mode=off
~~~

The demo runs on `http://localhost:8080`, so **`Secure=true` is not enforced on localhost** for easy testing. Production requires HTTPS, `Secure` cookies, and trusted reverse-proxy/forwarded-header configuration. `15m` is only an educational value, not automatically the right policy for every system.

### 8.3. SessionDebugApplication.java

~~~java
package com.example.sessiondebug;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SessionDebugApplication {
    public static void main(String[] args) {
        SpringApplication.run(SessionDebugApplication.class, args);
    }
}
~~~

### 8.4. SecurityConfig.java

~~~java
package com.example.sessiondebug;

import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.context.HttpSessionSecurityContextRepository;
import org.springframework.security.web.context.SecurityContextRepository;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityContextRepository securityContextRepository() {
        return new HttpSessionSecurityContextRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, SecurityContextRepository repository)
            throws Exception {
        http
            .securityContext(ctx -> ctx
                .securityContextRepository(repository))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(
                    DispatcherType.ERROR, DispatcherType.FORWARD).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/csrf").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me").authenticated()
                .anyRequest().denyAll())
            .formLogin(form -> form.permitAll())
            .exceptionHandling(errors -> errors
                .defaultAuthenticationEntryPointFor(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED),
                    new AntPathRequestMatcher("/api/**")));
        // CSRF remains enabled by default.
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password("{noop}pw")
                .roles("USER")
                .build()
        );
    }
}
~~~

**Explanation:** `IF_REQUIRED` permits sessions; `HttpSessionSecurityContextRepository` saves context consistently; built-in `formLogin` handles `POST /login`; `GET /api/csrf` lets curl retrieve a token in the same session; `GET /api/me` is the protected endpoint. `HttpStatusEntryPoint` causes unauthenticated API calls to return `401` rather than an HTML redirect. `formLogin().permitAll()` explicitly permits default login URLs; anything outside the allowlist is denied via `denyAll`. CSRF remains enabled for POST.

`AntPathRequestMatcher` may trigger deprecation warnings in newer Spring Security releases; this snippet targets Spring Security 6.x for the project. Do not copy it verbatim to Spring Security 7 without checking the corresponding APIs.

### 8.5. DiagnosticController.java

~~~java
package com.example.sessiondebug;

import java.util.List;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DiagnosticController {

    @GetMapping("/api/csrf")
    public CsrfView csrf(HttpServletRequest request) {
        CsrfToken csrf = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        // Triggers token retrieval/generation when CSRF is deferred.
        return new CsrfView(csrf.getParameterName(), csrf.getToken());
    }

    @GetMapping("/api/me")
    public UserView me(Authentication authentication) {
        List<String> roles = authentication.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .sorted()
            .toList();
        return new UserView(authentication.getName(), roles);
    }

    public record CsrfView(String parameterName, String token) {}
    public record UserView(String name, List<String> roles) {}
}
~~~

The CSRF endpoint is an **illustrative helper only** in the demo, not a public API every production app should expose. CSRF tokens must follow your app's same-origin/CORS policy; never log tokens. The `/api/me` endpoint returns no session IDs, credentials, or sensitive data.

### 8.6. SessionLoginTest.java

~~~java
package com.example.sessiondebug;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SessionLoginTest {
    @Autowired MockMvc mvc;

    @Test
    void loginPersistsAuthenticationForNextRequest() throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "alice")
                .param("password", "pw"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session =
            (MockHttpSession) login.getRequest().getSession(false);
        assertThat(session).isNotNull();

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.roles[0]").value("ROLE_USER"));

        // Without sending the logged-in session: new request must be anonymous.
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void missingCsrfCannotSubmitLogin() throws Exception {
        mvc.perform(post("/login")
                .param("username", "alice")
                .param("password", "pw"))
            .andExpect(status().isForbidden());
    }

    @Test
    void csrfTokenCanBeRetrievedBeforeLogin() throws Exception {
        mvc.perform(get("/api/csrf"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.parameterName").value("_csrf"))
            .andExpect(jsonPath("$.token").isNotEmpty());
    }

    @Test
    void unauthenticatedApiIs401() throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

The first test distinguishes **succeeding during the login request** from **identity persisting to the next request**, by passing the same `MockHttpSession`. The sessionless test confirms the protected endpoint returns 401. The CSRF test shows that 403 on POST does not mean the cookie was lost.

`MockMvc` exercises the servlet filter chain and simulated session in Spring Test, yet **does not faithfully simulate browser cookie policies**, CORS, proxies, or multi-node setups. Supplement with real HTTP/browser tests for those aspects.

## 9. Running the Example and Reproducing Failures with a curl Cookie Jar

Run inside the directory containing `pom.xml`:

~~~bash
mvn test
mvn spring-boot:run
~~~

`mvn test` runs the tests; `mvn spring-boot:run` starts the server on `http://localhost:8080` if the port is free. Actual execution results depend on dependencies and environment; do not treat this doc snippet as a captured build report.

**Step A — request without a cookie:**

~~~bash
curl -i http://localhost:8080/api/me
~~~

Expected status: `401`.

**Step B — fetch CSRF token while keeping the session cookie.** With bash and `jq` installed:

~~~bash
csrf=$(curl -fsS -c cookies.txt \
    http://localhost:8080/api/csrf | jq -r '.token')
test -n "$csrf" && echo "CSRF token received"
~~~

Expected stdout: `CSRF token received`. `-c cookies.txt` stores the session cookie associated with the token. Do not print real tokens to logs.

**Step C — POST login with the same session, saving the new cookie if the ID rotates:**

~~~bash
curl -i -b cookies.txt -c cookies.txt \
    --data-urlencode "username=alice" \
    --data-urlencode "password=pw" \
    --data-urlencode "_csrf=$csrf" \
    http://localhost:8080/login
~~~

A valid login is expected to return `302` to the next page. `-b` sends the current cookie and `-c` saves the cookie set by the server after login. Never omit `-c` when the session ID may rotate for session fixation protection.

**Step D — compare requests with and without the cookie:**

~~~bash
curl -i -b cookies.txt http://localhost:8080/api/me
curl -i http://localhost:8080/api/me
~~~

The first command expects `200` with body (JSON field order not guaranteed):

~~~json
{"name":"alice","roles":["ROLE_USER"]}
~~~

The second command expects `401`. This is a simple control test to prove whether the issue lies in **cookie transmission**.

**Intentionally induce failures in a learning environment:** omit `-b` on the follow-up request; omit `-c` after login; wait out the 15-minute inactivity timeout; restart the app when sessions live only in memory; swap stateful config for `STATELESS` in a separate test setup. Each causes 401 yet has a different root cause.

`cookies.txt` holds session credentials; never commit or share it, keep strict read permissions, and delete it after testing. The example password `pw` is for localhost only.

## 10. Custom Login Forgetting saveContext: Symptoms and Fix

Buggy code pattern:

~~~java
// WRONG when you want to remember the session across requests:
Authentication verified = authenticationManager.authenticate(candidate);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);
response.sendRedirect("/dashboard");
// Missing saveContext: the next request may be anonymous.
~~~

Correct contract with explicit save:

~~~java
// Illustrative: not a standalone class to copy and run.
Authentication verified = authenticationManager.authenticate(candidate);
SecurityContext context = SecurityContextHolder.createEmptyContext();
context.setAuthentication(verified);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(context, request, response);
response.sendRedirect("/dashboard");
~~~

Save before committing the response and use the same repository that the **next request's** filter chain loads from. This snippet does not replace a full authentication filter; production also needs `SessionAuthenticationStrategy` (against session fixation), CSRF handling, events, remember-me, failure/success handlers, rate limiting, and cleanup. For standard form login, prefer Spring Security's built-in mechanism.

Use breakpoints or controlled logging:

~~~text
POST /login:
  authenticate(candidate) -> succeeded?
  SecurityContextHolder -> holds trusted Authentication?
  saveContext(...) -> was it called?
  HttpSession -> exists?
  Response -> redirect and current session cookie?

GET /api/me:
  Cookie -> sent properly?
  getSession(false) -> exists?
  SecurityContextRepository -> loaded context?
  SecurityContextHolder -> expected principal/authorities?
  Authorization/CSRF -> which one denied?
~~~

If the cookie **never reached the server**, fixing context saving will not help. If the cookie arrived and the session exists yet context is not restored, check `saveContext` and the repository.

## 11. Reading Configuration and Session Events Properly

### SessionCreationPolicy and Filter Chains

`SessionCreationPolicy.STATELESS` is wrong if the product requires reusing a form-login session. `NullSecurityContextRepository` prevents context from being saved. `RequestAttributeSecurityContextRepository` serves only within one request and its dispatches, not cross-request session persistence.

With multiple `SecurityFilterChain` beans, the `/auth/**` login chain and `/api/**` API chain can use different repositories or policies. Inspect **`securityMatcher`, chain order, `securityContextRepository`, and `SessionCreationPolicy`** for both requests. Never assume the repository configured on the login chain automatically applies to the API chain.

### Logout, Timeout, Concurrent Sessions

Even when a cookie is sent, the session may have been `invalidate()`d by logout, timeout, password change, maximum-sessions policy, or a revocation mechanism. Look for the corresponding audit event. Spring Security typically rotates the session ID after login to prevent session fixation—**ID rotation is not a bug**, yet curl/browsers must store the new ID.

### Async and Other Threads

If only work running via `@Async`/executors reports missing `SecurityContextHolder` while HTTP requests remain logged in, that is a **cross-thread propagation** issue, not necessarily a session loss. Use dedicated integration such as `DelegatingSecurityContextExecutor` or your project's async context support; do not enable `MODE_GLOBAL` in multi-user servers.

### Stateful vs. Stateless

- **Form login/browser:** normally stores Authentication in a session.
- **HTTP Basic:** resends credentials on every request.
- **Resource Server Bearer/JWT:** normally verifies the token on every request rather than storing login in `HttpSession`.
- **OAuth2 Login/OIDC client:** may use a session for the login flow and browser session after callback; also debug `state`, cookies across redirects, code exchange, and repositories.

Only fix "login not remembered" when the architecture actually requires **persisting Authentication across requests**.

## 12. Proxies, Load Balancers, and Session Stores

### HTTPS Termination / Forwarded Headers

Clients may visit `https://app.example.com` while the proxy forwards HTTP to the backend. If the server does not recognize the public scheme/host, `Location`, `Secure` cookies, and callback URLs can break. Verify `Forwarded`/`X-Forwarded-Proto` at a **trusted proxy**, configure `server.forward-headers-strategy` appropriately, and inspect any `Set-Cookie Path/Domain` rewriting.

Never trust `X-Forwarded-*` headers directly from Internet clients: the proxy must strip or overwrite them at the trust boundary.

### Two Nodes Not Sharing Sessions

~~~text
POST /login -> instance A: JSESSIONID created on A
GET /api/me -> instance B: cookie is valid, yet B has no session
Result: anonymous / 401 even though browser sent the cookie.
~~~

Symptoms typically look like intermittent load-balancer failures, post-deploy/rollout errors, or autoscaling issues. Check instance IDs, session lookup hits/misses, TTL, and session storage. For multi-node apps needing durable sessions, consider **Spring Session + Redis/JDBC** or an appropriate infrastructure strategy. Sticky sessions help with affinity but do not replace a shared store when a node restarts.

When using Spring Session, verify namespace/TTL, serialization, class versions, cache eviction, and Redis/DB connectivity. Never dump `Authentication` objects containing sensitive data into logs.

### Valid Cookie Yet Still 403

If `GET /api/me` returns 200 while `POST /api/transfer` returns 403, the cause is likely CSRF or authorization, not a lost session. Inspect method, path, CSRF token, and authorities before touching cookies.

## 13. Safe Observability and Decision Table

Useful log fields:

| Log | Do Not Log |
|---|---|
| Correlation ID, route pattern, method/status, instance ID | Raw `Cookie`/`Set-Cookie` and session IDs |
| `hasSessionCookie`, `getSession(false) != null` | Passwords, Authorization Basic/Bearer, refresh tokens |
| `contextLoaded`, `authenticated` (boolean flags) | Full raw `SecurityContext` or credentials |
| Authentication success/failure type | CSRF tokens, OAuth authorization codes |
| Cookie attribute policy and session timeout config | Login request bodies and secrets in query strings |

When inspecting server state, use `request.getSession(false)` to avoid **creating a new session merely by debugging**. You can temporarily enable:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Enable only in safe environments for a short window, and never auto-log all headers. Leaving TRACE on or dumping credentials in production is a data-leakage risk.

Example comparison table of two requests after anonymization:

~~~text
                    POST /login       GET /api/me
Instance            node-A            node-B
Cookie reached srv  yes               yes
Session found       yes               no
Context active      yes               no
HTTP status         302               401

Priority branch: session store / routing between two nodes.
No evidence that the browser dropped the cookie.
~~~

Likewise, if the session is found on both requests yet context loads as null on GET, prioritize `saveContext` or repository/chain selection rather than cookie Domain/SameSite.

## 14. Debugging Decision Tree

~~~mermaid
flowchart TD
    A["Request after login treated as anonymous"] --> B{"Did login actually authenticate?"}
    B -->|"No"| X["Authentication provider / credentials / failure handler"]
    B -->|"Yes"| C{"Does next request carry right session cookie?"}
    C -->|"No"| D["Set-Cookie, SameSite, Secure, Domain/Path, CORS, credentials"]
    C -->|"Yes"| E{"Can server find HttpSession?"}
    E -->|"No"| F["Timeout, logout/invalidate, restart, LB node, shared store"]
    E -->|"Yes"| G{"Did SecurityContextRepository load Authentication?"}
    G -->|"No"| H["saveContext, Null repository, STATELESS, different chain"]
    G -->|"Yes"| I{"Are principal and authorities right?"}
    I -->|"No"| J["Context overwritten, logout/revoke, identity"]
    I -->|"Yes"| K["Check authorization/CSRF; not proven to be lost login"]
~~~

**Fix only the right branch:**

1. Cookie not sent → verify browser/cookie config, domain/path, HTTPS/Secure, SameSite, and frontend credentials/CORS.
2. Session missing → verify timeout, logout, node routing, shared session store, and post-login ID rotation.
3. Context not loaded → verify `SecurityContextRepository`, explicit `saveContext`, session policy, and multiple filter chains.
4. Context loaded right yet request denied → check roles/permissions/CSRF.
5. Stateless token-based login → ensure the client sends the token on every request rather than trying to force session storage.

## 15. Post-Fix Test Plan

| Case | Passing Evidence |
|---|---|
| Login with valid CSRF and cookie | Login succeeds; response/header contract valid |
| Next request with latest cookie | `/api/me` returns right principal |
| No cookie sent | No identity, `401` in demo |
| Different session of another user | No principal mix-up |
| Old cookie after logout | Does not restore logged-out Authentication |
| Server-side session expired | Client must log in again even if cookie remains |
| Session ID rotates after login | Cookie jar updates to new ID; session still works |
| POST missing/invalid CSRF | Rejected; do not conclude session was lost |
| Requests across two instances | Identity restored if app requires shared sessions |
| Browser/API on different origins | Cookies/CORS verified with a real browser |
| HTTPS and reverse proxy | No downgrade to HTTP; Secure cookie handled right |
| Stateless API | Bearer/Basic verified per request; no session required |

**Post-fix security checks:** logout must invalidate the session; expired sessions must stop granting access; Alice never becomes Bob; 403s for missing API permissions must still fire. Never "fix lost logins" by making sessions infinite, dropping HTTPS/CSRF, or loosening endpoint authorization.

## 16. Common Reasoning Traps and Self-Check Questions

- **"There is a JSESSIONID, so the user is logged in."** False: a session may have been created pre-login to store CSRF.
- **"I don't see the cookie in `document.cookie`, so it was lost."** False: `HttpOnly` hides it from JavaScript.
- **"Login returned 302, so SecurityContext was saved."** Insufficient: verify the next request restores context.
- **"Session ID changing is a bug."** Not necessarily: that can be session fixation protection.
- **"403 means Authentication was lost."** Not necessarily: CSRF or roles may have denied it.
- **"Disable CSRF to fix login."** Can open vulnerabilities; send the valid token instead.
- **"STATELESS still remembers logins via sessions."** Contradicts what the policy means.
- **"Calling `setContext` alone works for every request."** Incorrect under explicit-save mechanics.
- **"If one node works, the whole cluster works."** Shared sessions and routing must be verified.
- **"Set CORS `*` and cookies will stop disappearing."** Credentialed responses cannot use a wildcard origin, and cookies remain subject to browser policies.
- **"Enable TRACE and print Cookies to debug."** Risks leaking session credentials; use controlled correlation instead.

Answer for yourself:

1. If `POST /login` returns 302 and `GET /api/me` returns 401, why check `Cookie` on the second request first?
2. Cookie reaches the server yet `getSession(false)==null`: which causes belong to the session store?
3. If the session exists yet the repository fails to load context, where do you place breakpoints/logs in custom authentication?
4. Why does `RequestAttributeSecurityContextRepository` not replace `HttpSessionSecurityContextRepository` across independent requests?
5. Distinguish `SessionCreationPolicy.IF_REQUIRED` from `STATELESS`.
6. Why does a cross-origin browser call need `fetch(credentials:"include")`, matching CORS, and valid cookies together?
7. How does a 403 caused by CSRF differ from a 401 caused by being anonymous?
8. How do MockMvc tests verify session persistence, and why are browser/proxy tests still needed?
9. Which protections must stay intact when fixing cookies (Secure, HttpOnly, SameSite, CSRF, session fixation defense)?
10. If two nodes receive the same cookie yet one node has no session, what infrastructure solutions fit?

**Conclusion:** "Lost login" must be investigated along a measurable causal chain: **cookie stored/sent → HttpSession found → SecurityContext saved/loaded → Authentication established → authorization/CSRF allows**. Capture evidence across two consecutive requests, distinguish stateful from stateless designs, and fix only the mechanism actually failing.

## Official Reference Documentation

- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html)
- [Spring Security 6.5 — Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Boot 3.5 — SameSite Session Cookies](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot — Common Application Properties](https://docs.spring.io/spring-boot/appendix/application-properties/)
- [Spring Session — Reference](https://docs.spring.io/spring-session/reference/)
- [MDN — HTTP Cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)
