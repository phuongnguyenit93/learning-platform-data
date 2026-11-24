# Logout Limitations, Error Handling, and Separating Basic from Form Login Chains

## 1. Three Issues to Distinguish

In a Spring Security Servlet application, HTTP Basic and form login can both authenticate via username/password, but they **differ in how the client sends credentials, how state is maintained, and what happens on failure**.

- **HTTP Basic:** each request can carry the `Authorization: Basic <base64(username:password)>` header. The client or browser may retain and resend credentials. The server authenticates the request based on the credentials received.
- **Form login:** the user enters credentials into a form; after successful authentication, the web application typically stores the `SecurityContext` via an HTTP session and the browser sends a session cookie, such as `JSESSIONID`, on subsequent requests.
- **Logout:** with a form-login session, the server can invalidate the session to block reuse of the old session. With Basic, invalidating the session or clearing `SecurityContext` **does not stop the browser/client from possessing or sending the credentials**.

Therefore, a mixed system should clearly define which endpoints use Basic, which endpoints use form login, what each group's authentication failure response is, and what state logout affects.

This lesson focuses on **Spring Security Servlet (Spring Boot 3.x, Spring Security 6.x, Java 17+)**. For Spring WebFlux, the filter chain configuration and APIs differ; do not copy Servlet examples as-is to Reactive.

## 2. Why Does HTTP Basic Have No "Logout" Equivalent to Form Login?

### 2.1. Form Login Has a Server-Side Login Session

Typical form login flow:

~~~text
Browser
  ├─ GET /web/me (no session yet)
  │      → 302 redirect /login
  ├─ GET /login → login page
  ├─ POST /login + username/password + CSRF token
  │      → authentication succeeds, SecurityContext saved via session
  │      → browser receives/keeps session cookie
  ├─ GET /web/me + session cookie → private content
  └─ POST /logout + CSRF token
         → LogoutFilter runs LogoutHandlers
         → clears SecurityContext, invalidates session
         → redirects to /login?logout (per configuration)
~~~

Once the session is invalidated, **the old session cookie no longer represents a valid login session**. That is the core meaning of session-based logout. Deleting the cookie in the browser is an additional cleanup step; the server still must prevent reuse of the invalidated session.

Spring Security typically provides `LogoutFilter` and `SecurityContextLogoutHandler`. Depending on configuration, actions include clearing `SecurityContext`, invalidating `HttpSession`, and cleaning up Remember Me state. With default CSRF enabled, the actual logout action is normally **POST /logout with a valid CSRF token**; `GET /logout` may only show a confirmation page. Do not treat a GET request to the logout URL as the default logout mechanism.

### 2.2. HTTP Basic Does Not Create a "Logged-In" Credential to Invalidate

A Basic flow can look like this:

~~~text
Client
  ├─ GET /api/me + Authorization: Basic ...
  │      → server checks username/password → 200
  ├─ GET /api/me + same Authorization: Basic ...
  │      → server checks credentials again → 200
  └─ Server clears SecurityContext or invalidates HTTP session
         → client still holds username/password
         → GET /api/me + Authorization: Basic ... → can still return 200
~~~

Even if `/logout` is called and the server returns a "logged out" message, the client can resend valid Basic credentials on the next request. `SecurityContextHolder.clearContext()` only clears the processing thread's context; `HttpSession.invalidate()` only destroys the corresponding session. **Neither operation revokes HTTP Basic's username/password or forces the browser to forget cached credentials.**

With Basic used in stateless mode, there is no per-login server session to revoke. Credential caching behavior belongs to the client; there is no standard HTTP Basic API guaranteeing that all browsers clear credentials. Trying to send `401`, change the `realm`, or redirect to another URL to "force logout" is not a reliable solution, because behavior depends on the browser and can trigger a re-login prompt dialog.

### 2.3. What Should Practical Basic Logout Do?

| Context | Measure aligned with goal | Limitations |
| --- | --- | --- |
| Script, cURL, or desktop app | Stop attaching `Authorization`; discard client-stored credentials and stop request jobs | If the script still holds username/password, the next request can still authenticate. |
| Browser using HTTP Basic dialog | Close/switch the browser session or clear saved credentials per browser instructions; verify with a fresh request | No consistent "one-button logout" guarantee across all browsers. |
| Web app needing a clear Logout button | Prefer form login + session, or a token mechanism with lifecycle and revocation | Requires designing state, CSRF, and token management properly. |
| Compromised credentials / immediate block needed | Lock the account, change/reset the password, revoke backend access permissions, and purge leaked data | Invalidating a single request/session does not disable a still-valid password. |
| Simple API-to-API | Can keep using Basic **over HTTPS** with managed, rotated, least-privilege secrets | Requires retry rate limiting, avoiding logging credentials, and secret lifecycle management. |

**Practical conclusion:** a Basic API should not promise "once logged out, credentials cannot be reused" if the backend still accepts the same username/password. A client-side "forget credentials" button only ensures that client application stops sending them automatically within its control; it does not revoke the credentials on the server.

## 3. Basic Error Handling: Returning 401, 403, and Contextual Challenges

### 3.1. HTTP 401: Authentication Has Not Succeeded

For Basic, when credentials are missing or invalid, the response is typically:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="api"
Content-Type: application/json;charset=UTF-8

{"error":"unauthorized"}
~~~

The `WWW-Authenticate` header tells the client that the resource accepts HTTP Basic and specifies the `realm`. The JSON message is an application choice, **not an RFC requirement**. When customizing `AuthenticationEntryPoint`, decide whether to preserve the Basic challenge; standard HTTP clients may need it to know how to authenticate.

In Spring Security, `BasicAuthenticationFilter` processes `Authorization: Basic …` and reports authentication failures via `AuthenticationEntryPoint`. If a request carries no credentials, an access rule requiring login causes `ExceptionTranslationFilter` to invoke the corresponding entry point. A request with a wrong password does not automatically "fall back" to form login in another filter chain.

### 3.2. HTTP 403: Authenticated, but Access Denied

Suppose `reader` authenticates successfully with only `ROLE_USER`, while `/api/admin` requires `ROLE_ADMIN`:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json;charset=UTF-8

{"error":"forbidden"}
~~~

This is an **authorization** failure. `AccessDeniedHandler` is suitable for controlling the 403 response. Do not turn every 403 into 401: clients would think they need to re-enter a password, whereas the actual cause is missing permissions.

Remember that 403 can also occur when CSRF or another security filter blocks a request; do not infer a missing role from the status code alone without inspecting the request, chain, and safe logs.

### 3.3. Form Login Errors Differ from Basic

Form login targets web pages and session state. A default-configured application may send unauthenticated users to `/login` via redirect; on a wrong password in the form, it typically redirects to `/login?error`; on successful logout it may redirect to `/login?logout`.

| Scenario | Expected Basic API behavior | Expected form-login web page behavior |
| --- | --- | --- |
| Unauthenticated | `401`, with `WWW-Authenticate` | Redirect to login page (typically 302). |
| Wrong username/password | `401`; no login session created | Return to login page with error state. |
| Authenticated but missing role | `403` | `403` or access-denied page depending on configuration. |
| Logout | Client stops sending credentials; backend can still accept old credentials | Invalidate session, clear SecurityContext, and navigate to post-logout page. |

The responses above are the **intended contract of the example**, not a guarantee for every Spring Security configuration. A single chain with both `formLogin` and `httpBasic` may select an entry point via request matchers or content negotiation; when customizing, test with both real browsers and HTTP clients.

### 3.4. Precautions When Building JSON Error Responses

- Never return messages distinguishing "username does not exist" from "wrong password" to external callers; overly specific messages aid account enumeration.
- Never include passwords, `Authorization` values, Base64 credentials, session IDs, or full request headers in error JSON, logs, or traces.
- Limit details returned to the client, while recording security events with **sensitive data masked** sufficiently for operational investigation.
- If using retries or rate limits, enforce them according to real policy; repeated 401 responses do not automatically stop password guessing.
- With browsers, repeatedly receiving Basic challenges can pop up unwanted login dialogs; that is why web flows should be separated.

## 4. How Does an Application with Two SecurityFilterChains Work?

`FilterChainProxy` selects **the first SecurityFilterChain whose matcher matches the request**. That first matching chain handles the request; Spring Security does not fall through to a later chain just because credentials are wrong or an access rule denies the request.

Partitioning example:

~~~text
Request enters FilterChainProxy
           │
           ├─ Path starts with /api/**
           │    → @Order(1), API security chain
           │    → HTTP Basic + API policy
           │    → 401 challenge / 403 / API controller
           │
           └─ Remaining paths
                → Web security chain (fallback)
                → Form login + session + logout + CSRF
                → /login /logout /web/** / ...
~~~

Two easily confused concepts:

- `http.securityMatcher("/api/**")` decides **whether a request enters that chain**.
- `authorizeHttpRequests(...requestMatchers("/api/admin").hasRole("ADMIN"))` decides **permissions inside the already-selected chain**; it does not select the chain.

`@Order(1)` causes the API chain to be evaluated first. The web chain declares no `securityMatcher` so it acts as the fallback for all remaining paths. If both chains only match narrow paths and a request matches neither chain, it can end up **unprotected by Spring Security**. That is a serious configuration bug.

Also remember that filter-generated endpoints must fall within that chain's matched paths. If the form chain only matches `/web/**` yet still uses default `/login` and `/logout` URLs, those URLs may not reach the right chain; the result is broken login/logout or 404. The example below keeps the web chain as the fallback so default URLs work.

## 5. Complete Example: API Uses Basic, Website Uses Form Login

We build a Spring Boot 3.x / Java 17+ application with:

- `GET /api/me` — accessible only with valid Basic.
- `GET /api/admin` — valid Basic **and** `ROLE_ADMIN`.
- `GET /web/me` — login via form and session.
- `GET /` — public data page serving as a default target.
- `GET /login`, `POST /login`, `POST /logout` — using endpoints created by Spring Security in the web chain.

The example uses read-only GET endpoints for the API to illustrate the authentication flow. CSRF **remains enabled**; if you later add POST/PUT/DELETE APIs, determine whether the API is called by browsers and auto-sends credentials before deciding CSRF configuration.

### 5.1. Dependencies

In a project configured with the Spring Boot Gradle plugin and dependency management, include:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

This is the `dependencies` block, not a complete `build.gradle`. The classes below use the Jakarta Servlet API provided by Spring Boot 3. If you do not have a project yet, generate a Java 17+ project with Spring Web and Spring Security from Spring Initializr and add the files in the right package.

### 5.2. Application and Controller

Create `src/main/java/com/example/authsplit/AuthSplitApplication.java`:

~~~java
package com.example.authsplit;

import java.security.Principal;
import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class AuthSplitApplication {
    public static void main(String[] args) {
        SpringApplication.run(AuthSplitApplication.class, args);
    }

    @RestController
    static class Routes {
        @GetMapping("/")
        Map<String, String> home() {
            return Map.of("message", "public");
        }

        @GetMapping("/api/me")
        Map<String, String> apiMe(Principal principal) {
            return Map.of("apiUser", principal.getName());
        }

        @GetMapping("/api/admin")
        Map<String, String> apiAdmin(Principal principal) {
            return Map.of("apiAdmin", principal.getName());
        }

        @GetMapping("/web/me")
        Map<String, String> webMe(Principal principal) {
            return Map.of("webUser", principal.getName());
        }
    }
}
~~~

`Principal` is used only on endpoints requiring authentication. Spring MVC resolves the authenticated identity from the security context for the request; controllers do not need to decode Base64 themselves.

### 5.3. Two Chains and Custom 401/403 Handling for the API

Create `src/main/java/com/example/authsplit/SecurityConfig.java`:

~~~java
package com.example.authsplit;

import java.io.IOException;
import java.nio.charset.StandardCharsets;

import jakarta.servlet.http.HttpServletResponse;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        AuthenticationEntryPoint apiEntryPoint = (request, response, ex) -> {
            response.setHeader(
                HttpHeaders.WWW_AUTHENTICATE,
                "Basic realm=\"api\""
            );
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            writeJson(response, "{\"error\":\"unauthorized\"}");
        };

        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .httpBasic(basic -> basic
                .authenticationEntryPoint(apiEntryPoint)
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(apiEntryPoint)
                .accessDeniedHandler((request, response, ex) -> {
                    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
                    writeJson(response, "{\"error\":\"forbidden\"}");
                })
            );

        return http.build();
    }

    @Bean
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            );

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("reader")
                .password(encoder.encode("reader-pass"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    private static void writeJson(
        HttpServletResponse response,
        String json
    ) throws IOException {
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.getWriter().write(json);
    }
}
~~~

Configuration decisions:

1. **`@Order(1)` + `securityMatcher("/api/**")`:** every request starting with `/api/` enters the API chain. Because the API chain does not enable `formLogin`, there is no redirect to a login page for unauthenticated API requests.
2. **`httpBasic`:** the API chain uses Basic and an entry point returning 401 JSON; `WWW-Authenticate` is retained so clients know the scheme.
3. **`exceptionHandling`:** uses the same entry point when an API request lacks authentication and is denied by rules; a dedicated `AccessDeniedHandler` returns 403 JSON when an identity exists but lacks permissions.
4. **`STATELESS`:** the API chain does not create or use an HTTP session to store `SecurityContext` for authentication. Each Basic request relies on its own credentials; this is not a "logout command."
5. **Web chain as fallback:** `/login`, `/logout`, and `/web/me` are all served by the web chain; this chain enables `formLogin` and logout, and **does not enable HTTP Basic**.
6. **CSRF kept at default:** web forms and `POST /logout` remain subject to CSRF protection. The GET API endpoints in the example do not need CSRF tokens. If the API has state-changing requests from browsers using Basic, CSRF must still be evaluated.
7. **Shared demo user store:** both chains can share the same `UserDetailsService`/`PasswordEncoder`, but credential transmission and state persistence are two separate mechanisms. Splitting chains does not by default isolate user lists or roles.
8. **Demo passwords:** passwords exist in source only for local development testing. Production requires an appropriate user/secret store, HTTPS, log protection, and retry controls. BCrypt is password hashing, not reversible encryption.

Note: the example configures a default `SecurityFilterChain` without `securityMatcher` to cover remaining URLs. Do not write a "fallback" using `securityMatcher("/web/**")` and accidentally leave `/login`, `/logout`, `/error`, or new endpoints unprotected.

### 5.4. Running the Application

In a Spring Boot project directory with the Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`. Because the code depends on Spring Boot and Spring Security, standalone `javac` lacks the necessary classpath; Gradle compiles and runs the app.

Test directly with cURL; the demo server runs at `http://localhost:8080`. **This HTTP address is only for localhost testing; in deployment you must use HTTPS.** On PowerShell you can invoke `curl.exe` if `curl` is aliased.

~~~bash
# Unauthenticated API: must return 401 + Basic challenge.
curl -i http://localhost:8080/api/me

# API with valid Basic credentials: 200.
curl -i -u reader:reader-pass http://localhost:8080/api/me

# Logged in validly but missing admin role: 403.
curl -i -u reader:reader-pass http://localhost:8080/api/admin

# Admin login: 200.
curl -i -u admin:admin-pass http://localhost:8080/api/admin

# Web page without session: redirects to /login.
curl -i http://localhost:8080/web/me

# Login page generated by Spring Security, served via web chain.
curl -i http://localhost:8080/login

# Public page.
curl -i http://localhost:8080/
~~~

Results to verify:

| Test command | HTTP status | Content / point to observe |
| --- | --- | --- |
| `GET /api/me` without credentials | `401` | `WWW-Authenticate: Basic realm="api"` and `{"error":"unauthorized"}`. |
| `GET /api/me` with `reader:reader-pass` | `200` | `{"apiUser":"reader"}`. |
| `GET /api/admin` with reader | `403` | `{"error":"forbidden"}`; not a wrong password. |
| `GET /api/admin` with admin | `200` | `{"apiAdmin":"admin"}`. |
| `GET /web/me` without session | `302` | `Location` points to `/login`; no Basic challenge sent. |
| `GET /login` | `200` | HTML login form generated by Spring Security. |
| `GET /` | `200` | `{"message":"public"}`. |

Do not assert exact minor headers, header ordering, session cookie attributes, or form HTML: those details depend on the servlet container and version. What QA needs to verify is **status, authentication scheme, chain routing, and permission boundaries**.

Security note for demo commands: the `-u username:password` flag can appear in command history or process lists. Use dummy accounts only. When handling real credentials, use environment-appropriate secret provisioning methods and never capture or log Basic headers.

## 6. Testing Form Logout and Proving Basic Remains Independent

In a browser, visit `http://localhost:8080/web/me`. Unauthenticated requests will be taken to `/login`.

1. Log in via the form using the demo account `reader` / `reader-pass`. The browser submits the form with the CSRF token provided by Spring Security's generated login page; the application establishes a session.
2. Open `/web/me`. Upon successful session authentication, the endpoint returns JSON containing the `webUser` key.
3. Visit `/logout`. With CSRF enabled, Spring Security may show a confirmation page. Click the Logout button to send a **POST** with the CSRF token.
4. After logout, the browser typically redirects to `/login?logout`. Revisiting `/web/me` will prompt for form login because the old session is no longer valid.
5. Use cURL to send Basic credentials to the API again:

~~~bash
curl -i -u reader:reader-pass http://localhost:8080/api/me
~~~

The result is still `200` with `{"apiUser":"reader"}` because the username/password is still valid. This is direct proof that **form logout does not revoke Basic credentials**. The two flows are routed through different chains, even though they share the demo user database.

Also test a request to `/api/me` **without** Basic credentials while sending the web session cookie: with the API chain's `STATELESS` setting, that cookie is not used to obtain a `SecurityContext` for the API request; the expected result is 401. This is an important test to catch accidental session sharing into the API.

Conversely, merely including `Authorization: Basic …` on `GET /web/me` does not turn the API Basic filter into web login, because this request enters the web chain which does not configure `httpBasic`. Without a form session, the web chain still requires form login.

## 7. Common Configuration Mistakes When Mixing Basic and Form Login

### Mistake 1: Enabling Both Mechanisms in One Catch-All Chain

~~~java
// Illustrates a confusing configuration, not used in the example.
http
    .authorizeHttpRequests(auth -> auth
        .anyRequest().authenticated()
    )
    .httpBasic(Customizer.withDefaults())
    .formLogin(Customizer.withDefaults());
~~~

This configuration is not inherently invalid, but when both browsers and APIs share one chain, unauthenticated responses can depend on how Spring Security chooses the entry point. An API expecting `401` JSON might get `302` HTML, or a browser expecting a login page might get a Basic challenge/login dialog. When the two client groups have different contracts, use separate chains with explicit matchers.

### Mistake 2: Confusing `securityMatcher` with `requestMatchers`

Placing `requestMatchers("/api/**")` inside `authorizeHttpRequests` alone does not create a separate chain for the API. You must specify `http.securityMatcher("/api/**")` on the API chain, along with the right priority order. For a request matching both, Spring Security picks the first chain and **does not try the next chain after the first returns 401/403**.

### Mistake 3: Leaving "Gaps" Between Chains

Two chains `/api/**` and `/web/**` do not automatically protect `/admin`, `/actuator/**`, or new endpoints outside those two prefixes. Use an appropriate fallback chain (with no `securityMatcher`) or an explicit default-deny policy. Do not assume "matches no chain" equals "denied".

### Mistake 4: Putting Login/Logout URLs Outside the Web Chain's Matcher

If the web chain only matches `/web/**` yet uses default `POST /login` and `POST /logout`, those two requests do not enter the chain containing the filters that handle them. The fix is to make the web chain a fallback as in the example, or move `loginPage`, `loginProcessingUrl`, and `logoutUrl` inside the matcher scope and provide a suitable login page.

### Mistake 5: Disabling CSRF Thinking Stateless Basic Is Safe

`SessionCreationPolicy.STATELESS` does not eliminate CSRF risk when browsers automatically attach cached Basic credentials to requests. If the API can be accessed by browsers and has state-changing operations, CSRF must be evaluated seriously. Only consider omitting CSRF for APIs serving strictly non-browser clients that do not auto-attach credentials under a verified threat model. CORS does **not** replace CSRF protection.

### Mistake 6: Treating `POST /logout` as a Command to Erase Basic Credentials

The logout filter clears the context and session it manages; new API requests can still authenticate using unrevoked credentials. If the goal is to ban old credentials, you must update the account/password state or design a different revocable credential mechanism.

### Mistake 7: Turning Every Authentication Error into 403

Invalid passwords or missing credentials should normally be 401; authenticated users lacking permissions should be 403. An API with custom JSON errors must still behave consistently on both the invalid Basic credential branch and the missing credential branch. When configuring public endpoints and custom filters, test both cases.

### Mistake 8: Debugging by Logging All Headers

Logging the raw `Authorization` header exposes username/password via Base64. Log error type, normalized path, request ID, timestamp, and outcome (401/403), never tokens or credentials. If deeper analysis is needed, perform it in a controlled environment and purge sensitive data immediately once finished.

## 8. Test Plan and Acceptance Criteria

After implementing the two chains, run at least the following tests:

| Test | Request | Expected result |
| --- | --- | --- |
| API-01 | `GET /api/me`, no Authorization | 401, Basic challenge; no HTML login redirect. |
| API-02 | `GET /api/me`, wrong password | 401, without disclosing whether the user exists. |
| API-03 | `GET /api/me`, valid Basic credentials | 200; returns API identity. |
| API-04 | `GET /api/admin`, valid reader | 403; not 401. |
| API-05 | `GET /api/admin`, valid admin | 200. |
| WEB-01 | `GET /web/me`, no session | Redirect to login, no Basic challenge triggered. |
| WEB-02 | `POST /login` with valid credentials + CSRF token | Web login succeeds and maintains session. |
| WEB-03 | `POST /logout` with valid CSRF token | Session is invalidated and cannot be reused. |
| ISOLATION-01 | `GET /api/me` with only web session cookie, no Basic | 401, proving API does not rely on web session. |
| ISOLATION-02 | `GET /web/me` with only Basic header, no session | Prompts for form login, proving web chain does not enable Basic. |
| ISOLATION-03 | Web logout, then call API with still-valid Basic credentials | API can still return 200; demonstrates Basic logout limitation. |
| ROUTING-01 | New URL outside `/api/**`, e.g. `/unexpected` | Fallback chain still protects it or returns status per declared policy. |

When a test fails unexpectedly, debug in order:

1. **Which chain received the request?** Check the URL after reverse proxies, context path, `@Order`, and `securityMatcher`. Do not look only at `requestMatchers` rules.
2. **What credentials/session are present?** For API, check for a Basic header (presence and scheme only, never log values); for web, check session/cookie and persisted authentication state.
3. **Is the failure in authentication or authorization?** Inspect `AuthenticationEntryPoint`, `AccessDeniedHandler`, roles/authorities, `UserDetailsService`, and `PasswordEncoder`.
4. **If it occurs on POST/PUT/DELETE:** check CSRF before concluding a role is missing.
5. **If the browser shows a Basic dialog:** verify whether the request accidentally hit the API chain or received an unexpected `WWW-Authenticate`.
6. **If authentication persists after logout:** determine whether that request used a **web session** or sent **Basic credentials**; those are two distinct causes.

## 9. Takeaways

- HTTP Basic **has no standard logout that guarantees the client deletes username/password**. Clearing `SecurityContext` or the session only clears state held by the server.
- Form login can log out by invalidating the session; with default CSRF enabled, `POST /logout` requires a valid CSRF token.
- `401 Unauthorized` is for failed/missing authentication; Basic typically includes `WWW-Authenticate`. `403 Forbidden` is for denied requests, typically due to missing permissions or CSRF.
- `securityMatcher` selects the **filter chain**; `requestMatchers` inside `authorizeHttpRequests` applies **permission rules within that chain**. Only the first matching chain is used.
- Using a prioritized Basic API chain for `/api/**` and a form-login fallback chain for web pages lets you control 401 JSON, 302 login, 403, and session logout independently.
- Stateless configuration and chain splitting **do not replace HTTPS, CSRF assessment, credential protection, rate limiting, or password lifecycle management**.

### References

- RFC 7617 — The 'Basic' HTTP Authentication Scheme: https://www.rfc-editor.org/rfc/rfc7617
- Spring Security Reference — Basic Authentication (Servlet): https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html
- Spring Security Reference — Java Configuration, Multiple HttpSecurity Instances: https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- Spring Security Reference — Handling Logouts: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security Reference — CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
