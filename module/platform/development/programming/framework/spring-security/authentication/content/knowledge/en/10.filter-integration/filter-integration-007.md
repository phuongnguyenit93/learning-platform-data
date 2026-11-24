# AuthenticationSuccessHandler and AuthenticationFailureHandler

**Module:** Spring Security – authentication. **Parent topic:** Filter Integration. **Scope:** Spring Security Servlet, especially form login and authentication filters based on `AbstractAuthenticationProcessingFilter`.

## 1. Problem: Authentication Is Done, Where Does the HTTP Response Go?

When a user submits `POST /login`, the application must resolve **two separate concerns**:

1. **Authentication**: are username/password, account lock status, credentials, MFA, and other conditions valid? This belongs to `AuthenticationManager`, `AuthenticationProvider`, and the authentication mechanisms.
2. **Response after the authentication attempt**: on success, should the user go back to the requested page, go to the dashboard, or receive JSON? On failure, should it redirect to the login form or return HTTP 401 with a safe message? This belongs to **`AuthenticationSuccessHandler`** and **`AuthenticationFailureHandler`**.

Example:

~~~text
POST /login  [username/password]
      |
      v
UsernamePasswordAuthenticationFilter
      |
      v
AuthenticationManager.authenticate(...)
      |
      +--- SUCCESS ------> AuthenticationSuccessHandler
      |                       |
      |                       +--> 302 /dashboard
      |                       +--> 302 URL saved before login
      |                       +--> 200 JSON for the corresponding frontend
      |
      +--- FAILURE ------> AuthenticationFailureHandler
                              |
                              +--> 302 /login?error
                              +--> 401 JSON generic message
~~~

**Core point:** These two handlers decide **how to complete the response/navigation** after an authentication attempt has been processed. They **do not verify passwords in place of the provider**, **do not directly grant permissions**, and **do not by themselves guarantee `SecurityContext` is saved into the HTTP session**.

This lesson applies directly to `UsernamePasswordAuthenticationFilter`/`formLogin`, while distinguishing it from bearer tokens, HTTP Basic, OAuth2/OIDC, logout, and authorization errors so handlers are never placed in the wrong spot.

## 2. Separating the Stages of the Servlet Authentication Flow

A form login flow typically consists of:

1. `UsernamePasswordAuthenticationFilter` sees a request matching `loginProcessingUrl`, typically `POST /login`.
2. The filter extracts username/password from the request and creates an **unauthenticated** `UsernamePasswordAuthenticationToken`.
3. The filter calls `AuthenticationManager.authenticate(...)`.
4. `AuthenticationProvider` processes it: loads `UserDetails`, compares password, checks account flags, returns an authenticated `Authentication` or throws `AuthenticationException`.
5. If successful, the filter machinery invokes `SessionAuthenticationStrategy`, prepares/saves `SecurityContext`, coordinates remember-me and publishes the appropriate event, then invokes **`AuthenticationSuccessHandler`**.
6. If failed, the filter machinery clears `SecurityContextHolder`, invokes the remember-me failure hook if present, and invokes **`AuthenticationFailureHandler`**.
7. The handler produces the appropriate response and terminates or redirects the request per its implementation.

~~~text
                   Servlet FilterChain
                          |
                          v
           AbstractAuthenticationProcessingFilter
                          |
             requiresAuthentication(request)?
                 |                   |
                no                  yes
                 |                   |
                 v                   v
           continue chain     attemptAuthentication(...)
                                     |
                              +------+------+
                              |             |
                             ok        AuthenticationException
                              |             |
                              v             v
                     Session strategy   Clear holder /
                     SecurityContext    remember-me fail
                     remember-me        |
                     success event      |
                              |             |
                              v             v
                     successful...    unsuccessful...
                              |             |
                              v             v
                    SuccessHandler    FailureHandler
                              |             |
                              v             v
                    Redirect/JSON     Redirect/JSON
~~~

This is a **simplified diagram**. Real programs may have additional filters, session policies, and auth mechanisms. `attemptAuthentication(...)` can return `null` when the flow is still in progress (e.g., multi-step), so not every request reaching the filter immediately calls one of the two handlers.

### Who Is Responsible for What?

| Component | Primary job | Must NOT be forced to do |
| --- | --- | --- |
| `AuthenticationManager` | Coordinates credential verification | Generate redirects/HTML/JSON for form login |
| `AuthenticationProvider` | Verifies credentials and account state | Read query `next` and decide navigation |
| `SecurityContextRepository` | Loads/saves context per request/session policy | Check passwords or pick the next page |
| `AuthenticationSuccessHandler` | Finalizes HTTP response after successful authentication | Grant admin/roles from client input |
| `AuthenticationFailureHandler` | Finalizes HTTP response when authentication is rejected | Disclose whether a username exists or why an account is locked |
| `AuthenticationEntryPoint` | Starts login/challenge when accessing a resource **unauthenticated** | Handle every wrong-password form submission |
| `AccessDeniedHandler` | Handles insufficient privileges once authenticated, usually 403 | Turn authorization errors into wrong-password errors |
| `LogoutSuccessHandler` | Navigation/response after logout | Be confused with login success handler |

## 3. AuthenticationSuccessHandler Contract

Interface:

~~~java
package org.springframework.security.web.authentication;

// Abbreviated signature; not a standalone Java file.
public interface AuthenticationSuccessHandler {

    void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            Authentication authentication)
            throws IOException, ServletException;

    default void onAuthenticationSuccess(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain,
            Authentication authentication)
            throws IOException, ServletException;
}
~~~

In Spring Security 6.5.11, these are Servlet signatures using `jakarta.servlet.*`, **not legacy `javax.servlet.*`**.

Parameters:

- `request`: the HTTP request that just completed authentication.
- `response`: the HTTP response to redirect, forward, or set status, headers, or body.
- `authentication`: the result verified by the trusted mechanism, containing principal/authorities.
- `chain` on the four-parameter overload: supports continuing the filter chain in certain authentication flows; do not assume every form login calls this overload by default.

**Handlers should not routinely re-invoke `authenticationManager.authenticate(...)`.** Re-authenticating inside a handler can cause side effects, extra latency, loops, or wrong session policies. By the time it is called, the framework normally already holds the verified result.

### What a Success Handler Typically Does

- Chooses a valid URL to redirect to, such as the pre-login page or dashboard.
- Returns JSON/HTTP status suited for a frontend using an AJAX-style form-login endpoint.
- Emits an audit event **containing no credentials**; emits controlled success metrics.
- Selects the next step **based on trusted server state** (e.g., onboarding, mandatory setup), never a client-sent role flag.
- Performs lightweight, deterministic HTTP work, avoiding slow external calls or writing critical business data after the response commits.

### What Is Not Its Default Responsibility

`AuthenticationSuccessHandler` does not by itself:

- Save account changes to the database or alter passwords;
- Defend against session fixation in place of `SessionAuthenticationStrategy`;
- Create `SecurityContext`/cookies if a custom login controller bypassed framework steps;
- Refresh revoked privileges inside an existing old session;
- Verify JWTs on every resource server request.

## 4. AuthenticationFailureHandler Contract

Interface:

~~~java
package org.springframework.security.web.authentication;

// Abbreviated signature; not a standalone Java file.
public interface AuthenticationFailureHandler {

    void onAuthenticationFailure(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException;
}
~~~

`exception` represents the internal reason the authentication system rejected the attempt, such as:

- `BadCredentialsException`;
- `LockedException`;
- `DisabledException`;
- `AccountExpiredException`;
- `CredentialsExpiredException`;
- Some `AuthenticationServiceException`, depending on failure and provider.

**Exception details are internal information**, not automatically UI copy. In particular, never do:

~~~java
// UNSAFE: leaks cause/status/account information.
response.getWriter().write(exception.getMessage());
~~~

For public logins, normalize wrong password, nonexistent username, and locked/disabled account into a **generic response**, while keeping detailed internal audits under controlled access.

`AuthenticationFailureHandler` receives the attempt's **`AuthenticationException`**. A database failure, JSON parse error, filter error, or other `RuntimeException` might not go through this handler depending on implementation; separate safe infrastructure error handling is required.

## 5. What Happens Before and After the Handler?

### 5.1. Success Branch

In the `AbstractAuthenticationProcessingFilter` flow:

~~~text
attemptAuthentication() -> Authentication result
                 |
                 v
        SessionAuthenticationStrategy
                 |
                 v
       successfulAuthentication(...)
                 |
          +------+-------+
          |              |
  SecurityContext      RememberMeServices
  prepared/saved       loginSuccess
          |              |
          +------+-------+
                 |
       InteractiveAuthenticationSuccessEvent
                 |
                 v
       AuthenticationSuccessHandler
                 |
                 v
         HTTP response/redirect
~~~

The flow above follows the Spring Security 6.5 documentation. Exact ordering, repositories, and session strategies depend on the filter/configuration. **Never move saving the context to after the handler has already redirected.**

When using `UsernamePasswordAuthenticationFilter` configured by `formLogin`, the framework sets up security context persistence. If writing a custom `AbstractAuthenticationProcessingFilter` subclass/filter, configure the proper `SecurityContextRepository` and session strategy; the filter API docs note that a manually constructed instance may **not persist context** by default if no repository is set.

### 5.2. Failure Branch

~~~text
attemptAuthentication(...) throws AuthenticationException
                 |
                 v
       SecurityContextHolder cleared
                 |
                 v
       RememberMeServices.loginFail
                 |
                 v
       AuthenticationFailureHandler
                 |
                 v
    Generic login URL / Generic HTTP 401
~~~

The failure handler is not a place to "grant limited permissions" so a locked user can still sign in. When auth fails, never place `Authentication(isAuthenticated=true)` into the context or issue an authenticated session to complete the response.

### 5.3. Events and Auditing

`InteractiveAuthenticationSuccessEvent` is published by the appropriate filter machinery on successful login. Authentication failures may be recorded via events from `AuthenticationManager`/providers depending on configuration; do not assume a symmetric failure event is emitted directly by `AbstractAuthenticationProcessingFilter`.

You can write an independent `ApplicationListener`, event publisher, audit service, or metrics recorder. When logging inside a handler, record minimal info: verified user ID, request/correlation ID, outcome, and a safe category. Never log raw passwords, bearer tokens, cookies, full principals, or full stack traces containing sensitive data.

## 6. Built-in Handlers: Choose Before Writing Your Own

### Success

| Implementation | Primary behavior | When to use |
| --- | --- | --- |
| `SavedRequestAwareAuthenticationSuccessHandler` | Prefers the URL saved prior to the login prompt, if present; otherwise uses default target | Browser form login, returning to the page the user tried to open |
| `SimpleUrlAuthenticationSuccessHandler` | Redirects/forwards to a target URL per base-class policy | Fixed or simple navigation flows |
| `ForwardAuthenticationSuccessHandler` | Server-side forward to a desired URL | When you want a forward instead of a browser redirect and understand request semantics |
| `HttpMessageConverterAuthenticationSuccessHandler` | Builds response via configured HTTP message conversion | API integration when framework and converter match |

### Failure

| Implementation | Primary behavior | Notes |
| --- | --- | --- |
| `SimpleUrlAuthenticationFailureHandler` | Redirects to `defaultFailureUrl` if configured; if no URL, sends HTTP 401 | API docs note the default 401 branch may include the exception message; standardize on public APIs |
| `ForwardAuthenticationFailureHandler` | Forwards to a failure-handling URL | Does not make the request authenticated |
| `ExceptionMappingAuthenticationFailureHandler` | Maps exception types to URLs | Avoid leaking locked/disabled/not-found via URLs |
| `DelegatingAuthenticationFailureHandler` | Selects a sub-handler by `AuthenticationException` subclass | Helpful for internal routing, yet public responses must still not act as an oracle |
| `AuthenticationEntryPointFailureHandler` | Delegates failure handling to an `AuthenticationEntryPoint` | Use when the same challenge/response policy fits |

These classes are **navigation utilities**, not complete security policies. A default handler suited for HTML may **not** fit a JSON-only frontend.

## 7. SavedRequestAwareAuthenticationSuccessHandler and RequestCache

This is the key difference between "go to dashboard after login" and "return to the originally requested page after login".

### 7.1. A Typical Browser Flow

~~~text
1. GET /orders/42          [unauthenticated]
            |
            v
2. Authorization requires authenticated
            |
            v
3. ExceptionTranslationFilter / AuthenticationEntryPoint
            |
            +--> RequestCache saves original request
            +--> redirect /login
            |
            v
4. POST /login             [valid password]
            |
            v
5. SavedRequestAwareAuthenticationSuccessHandler
            |
            +--> retrieves SavedRequest from RequestCache
            +--> redirect /orders/42
            |
            v
6. GET /orders/42          [authenticated session present]
~~~

`ExceptionTranslationFilter` and `RequestCache` save the original request; `SavedRequestAwareAuthenticationSuccessHandler` reads it back to choose the target.

### 7.2. Target Selection Order per API 6.5

According to the Javadoc:

1. If `alwaysUseDefaultTargetUrl=true`, use `defaultTargetUrl` and clear the saved request appropriately.
2. If `targetUrlParameter` is configured and the request carries a value for that parameter, the handler may use the parameter URL; the saved request is cleared along this path.
3. If a `SavedRequest` exists in `RequestCache`, redirect to the saved URL.
4. If there is no saved request, fall back to superclass `SimpleUrlAuthenticationSuccessHandler` logic (typically the default target).

**Security note:** `targetUrlParameter` or a query like `next=/...` is **untrusted input**. Never redirect directly to a user-supplied external URL, or you create an **open redirect** usable for phishing.

### 7.3. Common formLogin Configuration Examples

~~~java
// INTEGRATION CODE for Spring Security Servlet; not standalone.
http.formLogin(form -> form
        .loginPage("/login")
        .defaultSuccessUrl("/dashboard", false)
        .failureUrl("/login?error")
        .permitAll());
~~~

`defaultSuccessUrl("/dashboard", false)`: when a matching saved request exists, the user is normally sent back to the prior URL; when none exists, `/dashboard` is used.

~~~java
// INTEGRATION CODE, not standalone:
http.formLogin(form -> form
        .defaultSuccessUrl("/dashboard", true));
~~~

`true` forces always using the default target URL, ignoring returning to the pre-login requested page under this config.

**Do not** wire a custom handler just to achieve a simple redirect that `defaultSuccessUrl`/`failureUrl` already handles.

### 7.4. Post-Login Target URL Must Not Decide Permissions

A user with `ROLE_USER` redirected to `/admin` must still face `AuthorizationManager`, `@PreAuthorize`, or server-side policies on the actual endpoint; the handler does not grant `ROLE_ADMIN` merely by changing the URL.

When selecting a landing page by role, read authorities from the **`Authentication` returned by a trusted provider** and pick only from internal/allowlisted URLs. Never use `request.getParameter("role")` to decide privileges or an admin destination.

## 8. SimpleUrlAuthenticationFailureHandler: Redirects and Session-Side Exceptions

`SimpleUrlAuthenticationFailureHandler` Javadoc notes:

- If `defaultFailureUrl` is configured, the handler uses a redirect (or forward if `useForward=true`).
- If no URL is configured, the implementation sends 401; the message may originate from `AuthenticationException`.
- When forwarding/redirecting, it may store the exception in a request/session attribute for the view (depending on `allowSessionCreation`/`useForward`).

This leads to two observations:

**Saving the exception for the view does not mean you may render `exception.getMessage()`.** A `LockedException` can say "account is locked". Display a generic message on the login page, such as "Invalid username or password, or unable to sign in right now".

**A failure redirect can create a session** if the handler stores the exception and `allowSessionCreation=true`. When debugging why a `JSESSIONID` exists before login, inspect `RequestCache`, the failure handler, and other filters instead of blaming only `SecurityContextRepository`.

### Traditional Form Login

~~~java
http.formLogin(form -> form
        .loginPage("/login")
        .failureUrl("/login?error")
        .permitAll());
~~~

On the login page, show the same public message when the `error` parameter is present. Never encode the cause into `/login?locked=true`, `/login?userNotFound=true`, or `X-Account-Status`.

## 9. Comparing Three HTTP Response Options

| Client model | On login success | On login failure | Notes |
| --- | --- | --- | --- |
| Browser form navigation | `302` to saved URL or dashboard | `302` to `/login?error` | Browser issues GET after redirect; session cookie maintains login |
| AJAX calling form-encoded endpoint | `200` JSON/status per API contract | Generic `401` JSON | Still a form-urlencoded request when using default `UsernamePasswordAuthenticationFilter` |
| Custom-designed stateless API login/token issuance | `200`/`201` and suitable token/session contract | `401`/protocol-appropriate code | Needs dedicated filter/controller/provider and token handling, not just swapping handlers |

**Do not mechanically apply one response style to every protocol.** For HTTP Basic, bearer tokens, or OAuth2/OIDC, entry points/challenges/error semantics may dictate specific headers/statuses. Choose responses suited to the auth mechanism and avoid leaking account existence/state unnecessarily.

### Redirect vs. Forward

- **Redirect**: server sends 3xx with `Location`; browser issues a new request to the target URL.
- **Forward**: dispatches internally on the server for the same request/response via `RequestDispatcher`; does not trigger a new browser request.
- Forwarding after a POST can let the target page see the POST method/body; you must understand CSRF, request-scoped attributes, displayed URLs, and avoid accidentally re-processing credentials.

For Post/Redirect/Get in HTML login, redirect is usually easier to manage.

## 10. Runnable Java 17 Example: Two Handlers Returning Safe JSON

This complete example creates **real handlers implementing Spring Security 6.5.11 interfaces**, yet invokes them directly using `MockHttpServletRequest`/`MockHttpServletResponse`. It **requires no Spring Boot, DB, server, TLS, or filter chain**. The purpose is verifying exact **response contents** and confirming two distinct internal failure causes produce the same public response.

**Safety boundary:** `Authentication` is constructed directly in the test program to simulate an already-verified result. **Never** create an authenticated token from client-sent username/roles in production. In a real app, `AuthenticationManager`/providers must verify credentials before the success handler runs.

### 10.1. Directory Structure

~~~text
authentication-handlers-demo/
├── build.gradle
└── src/main/java/example/AuthenticationHandlersDemo.java
~~~

**File `build.gradle`:**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework.security:spring-security-core:6.5.11'
    implementation 'org.springframework:spring-test:6.2.15'
    implementation 'org.springframework:spring-web:6.2.15'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'example.AuthenticationHandlersDemo'
}
~~~

**File `src/main/java/example/AuthenticationHandlersDemo.java`:**

~~~java
package example;

import java.util.List;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.web.authentication.AuthenticationSuccessHandler;
import org.springframework.security.web.authentication.AuthenticationFailureHandler;

public final class AuthenticationHandlersDemo {

    private static final String OK =
            "{\"code\":\"LOGIN_OK\"}";

    private static final String FAIL =
            "{\"code\":\"AUTHENTICATION_FAILED\"}";

    private static AuthenticationSuccessHandler successHandler() {
        return (request, response, authentication) -> {
            // Framework only calls success handler after successful authentication.
            // This extra check highlights the trust boundary in the demo.
            if (authentication == null || !authentication.isAuthenticated()) {
                throw new IllegalStateException("Missing trusted authentication");
            }

            response.setStatus(200);
            response.setCharacterEncoding("UTF-8");
            response.setContentType("application/json");
            response.setHeader("Cache-Control", "no-store");
            response.getWriter().write(OK);
        };
    }

    private static AuthenticationFailureHandler failureHandler() {
        return (request, response, exception) -> {
            // May emit restricted-access internal audit here.
            // Never return exception class/message/username to client.
            response.setStatus(401);
            response.setCharacterEncoding("UTF-8");
            response.setContentType("application/json");
            response.setHeader("Cache-Control", "no-store");
            response.getWriter().write(FAIL);
        };
    }

    private static MockHttpServletRequest newLoginRequest() {
        return new MockHttpServletRequest("POST", "/login");
    }

    public static void main(String[] args) throws Exception {
        // Construct authenticated token only in this trusted demo.
        Authentication trusted =
                UsernamePasswordAuthenticationToken.authenticated(
                        "linh", null,
                        List.of(new SimpleGrantedAuthority("ROLE_USER")));

        MockHttpServletResponse success = new MockHttpServletResponse();
        successHandler().onAuthenticationSuccess(
                newLoginRequest(), success, trusted);

        System.out.println("success.status=" + success.getStatus());
        System.out.println("success.json="
                + success.getContentAsString());
        System.out.println("success.contentTypeIsJson="
                + success.getContentType().startsWith("application/json"));
        System.out.println("success.cacheControl="
                + success.getHeader("Cache-Control"));

        AuthenticationFailureHandler failureHandler = failureHandler();

        MockHttpServletResponse bad = new MockHttpServletResponse();
        failureHandler.onAuthenticationFailure(
                newLoginRequest(), bad,
                new BadCredentialsException("internal bad credentials"));

        MockHttpServletResponse locked = new MockHttpServletResponse();
        failureHandler.onAuthenticationFailure(
                newLoginRequest(), locked,
                new LockedException("internal account locked"));

        System.out.println("bad.status=" + bad.getStatus());
        System.out.println("locked.status=" + locked.getStatus());
        System.out.println("failure.sameBody="
                + bad.getContentAsString().equals(
                        locked.getContentAsString()));
        System.out.println("failure.publicJson="
                + locked.getContentAsString());
        System.out.println("failure.leaksInternal="
                + (locked.getContentAsString().contains("internal")
                   || bad.getContentAsString().contains("internal")));
        System.out.println("failure.cacheControl="
                + locked.getHeader("Cache-Control"));
    }
}
~~~

### 10.2. Running

Use **JDK 17+**, a compatible Gradle version, and Maven Central access for the initial dependency download. Inside `authentication-handlers-demo`:

~~~bash
gradle -q run
~~~

If the project has a Gradle Wrapper, use `./gradlew -q run`; on Windows use `gradlew.bat -q run`.

**Program stdout** (excluding Gradle/library logs when configured):

~~~text
success.status=200
success.json={"code":"LOGIN_OK"}
success.contentTypeIsJson=true
success.cacheControl=no-store
bad.status=401
locked.status=401
failure.sameBody=true
failure.publicJson={"code":"AUTHENTICATION_FAILED"}
failure.leaksInternal=false
failure.cacheControl=no-store
~~~

### 10.3. Output Explanation

- `success.status=200` and JSON `LOGIN_OK`: the success handler completed the response **without redirecting**.
- `success.contentTypeIsJson=true`: the response uses a JSON media type.
- `Cache-Control: no-store`: prevents caching login-session-related responses; production also needs cookie/session flags, HTTPS, and policy headers.
- `bad.status=401`, `locked.status=401`: both rejection cases receive the same generic HTTP status.
- `failure.sameBody=true`, `failure.leaksInternal=false`: the body does not disclose whether the user is locked or gave a wrong password.
- `failure.publicJson`: returns only a safe error code; the frontend can display a generic guidance message.
- The demo **does not** test timing, header, or cookie differences between existing and nonexistent accounts in a live auth flow. To evaluate account enumeration, test against the real HTTP/filter chain and user store.

### 10.4. Why Doesn't the Example Check Passwords?

`AuthenticationSuccessHandler` is designed to run **after authentication**. If the demo invoked `AuthenticationManager`, we would be studying a different component. In production, the handler **must never treat receiving an arbitrary `Authentication` object from the client as successful authentication**; that object must be issued by the framework/provider inside a trusted flow.

No session cookie or JWT is created by the demo. Retaining login across subsequent requests requires properly configured Spring Security filters, repositories, and session strategies.

## 11. Spring Boot Servlet Config: Form Login Redirect

The most standard pattern needs no custom classes:

~~~java
// Spring Security Servlet app imports:
// @Bean, HttpSecurity, SecurityFilterChain;
// UserDetailsService/AuthenticationProvider configured separately.
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/assets/**").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form
            .loginPage("/login")
            .loginProcessingUrl("/login")
            .defaultSuccessUrl("/dashboard", false)
            .failureUrl("/login?error")
            .permitAll());

    return http.build();
}
~~~

**This is an integration snippet**, not self-compiling/standalone: the app needs user/password-encoder or provider beans, a `GET /login` page rendering the form, and Spring Security/Servlet dependencies.

**Points to test:**

- `GET /login` renders the form with a valid CSRF token.
- `POST /login` is genuinely matched by the filter with the right default `username` and `password` parameters.
- Invalid credentials go to `/login?error` with a generic message.
- Valid credentials go to the saved request if present, or `/dashboard`.
- Session ID/CSRF/session fixation are handled by the framework mechanisms.
- `/dashboard` URL is only navigation, not a role grant; the endpoint still enforces its own authorization.

### Form Login DSL and Handlers

~~~java
// Alternative option: register custom handlers.
http.formLogin(form -> form
        .loginPage("/login")
        .successHandler(customSuccessHandler)
        .failureHandler(customFailureHandler));
~~~

`successHandler(...)`/`failureHandler(...)` attach handlers to **the login filter configured by the DSL**, not to every other `SecurityFilterChain` or every auth mechanism across the app.

## 12. Configuration for AJAX Frontends: JSON Response Yet Still Form-Encoded Request

If the frontend sends form-encoded requests and wants to manage UI state after login, you can use JSON-returning handlers like the demo:

~~~java
// SKETCH CODE inside a Spring Boot Servlet app.
// successHandler and failureHandler are application-defined beans.
@Bean
SecurityFilterChain ajaxLoginChain(
        HttpSecurity http,
        AuthenticationSuccessHandler successHandler,
        AuthenticationFailureHandler failureHandler) throws Exception {

    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/login").permitAll()
            .anyRequest().authenticated())
        .formLogin(form -> form
            .loginProcessingUrl("/login")
            .successHandler(successHandler)
            .failureHandler(failureHandler));

    return http.build();
}
~~~

**Important warning:** `UsernamePasswordAuthenticationFilter` reads `username`/`password` from **Servlet request parameters** by default, typically `application/x-www-form-urlencoded`. Swapping `successHandler`/`failureHandler` **does not turn `POST /login` into an endpoint that parses a JSON request body**.

If the frontend sends:

~~~json
{
  "username": "linh",
  "password": "a-secret-value"
}
~~~

while the filter still reads `request.getParameter("username")`, the request will not work as expected. For JSON login, you need a dedicated filter/controller mechanism to parse JSON, build an unauthenticated token, authenticate via the manager, and handle context, session strategy, CSRF, and success/failure hooks. **Do not just change the response Content-Type.**

For browsers maintaining sessions via cookies, fetch/AJAX must send cookies properly and handle CSRF tokens and CORS correctly. Avoid disabling CSRF recklessly just to make a login request succeed.

## 13. Custom SuccessHandler with Role-Based Navigation

You may want to route users to different UIs based on their roles. A minimal pattern:

~~~java
// ILLUSTRATIVE CODE in a Servlet application, not standalone.
AuthenticationSuccessHandler handler = (request, response, auth) -> {
    boolean admin = auth.getAuthorities().stream()
            .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));

    String target = admin ? "/admin" : "/dashboard";

    response.sendRedirect(
            request.getContextPath() + target);
};
~~~

This is **page-selection** logic, not authorization. Keep protecting `/admin` with server-side Spring Security rules. If you want to preserve saved requests, consider extending/delegating to `SavedRequestAwareAuthenticationSuccessHandler` or keeping default behavior instead of rigidly sending every user to the dashboard.

**Redirect safety:**

- Use only local paths/allowlists; never reflect an arbitrary `next` URL.
- Block redirects to `javascript:`, protocol-relative URLs, external hosts, path traversal, and multi-encoded URLs.
- If external redirects like OAuth2 are needed, use framework-supported protocol flows validating `state`, redirect URIs, and trusted origins.
- Never put access tokens or raw passwords in redirect query strings.
- Commit the response exactly once; never call both `sendRedirect` and `write JSON` afterwards.

If impersonation/switch-user is supported, record the true actor and audit per policy rather than relying solely on `ROLE_ADMIN` in the client.

## 14. Custom FailureHandler with Generic Error and Separate Audit

Production-style example for form/AJAX login:

~~~java
// ILLUSTRATIVE CODE in a Spring application context; not standalone.
AuthenticationFailureHandler handler = (request, response, ex) -> {
    // Emit internal audit: normalized error category, request/correlation ID.
    // Do not log ex.getMessage() if it may contain sensitive data.
    // Do not put detailed reasons in the response.

    response.setStatus(401);
    response.setCharacterEncoding("UTF-8");
    response.setContentType("application/json");
    response.setHeader("Cache-Control", "no-store");
    response.getWriter().write(
            "{\"code\":\"AUTHENTICATION_FAILED\","
          + "\"message\":\"Login failed.\"}");
};
~~~

**Why not split details in public responses?** Attackers can use differences to enumerate accounts:

~~~text
Wrong username    -> 404 UNKNOWN_USER
Wrong password    -> 401 WRONG_PASSWORD
Account locked    -> 423 LOCKED
Account disabled  -> 403 DISABLED
~~~

Even when wording is normalized, HTTP status, response length, redirect query parameters, headers, response timing, and rate-limit behavior can still leak state.

**Better design:** return a generic response for public authentication failures, while internal telemetry distinguishes `BAD_CREDENTIALS`, `LOCKED`, `DISABLED`, and infrastructure errors under proper access controls. For users who have verified ownership through a stronger channel, unlock/reset guidance can be shown in a separate flow.

### A Caveat About the Default Failure Handler

`SimpleUrlAuthenticationFailureHandler` Javadoc notes that when **no failure URL** is set, the handler can send `401` with a message derived from `AuthenticationException`. Do not rely on that default as an anti-enumeration strategy; configure a generic redirect or a security-reviewed custom handler.

## 15. AuthenticationFailureHandler vs. AuthenticationEntryPoint and AccessDeniedHandler

An unauthenticated request to `GET /admin` is not the same as a wrong-password attempt at `POST /login`:

| Scenario | Appropriate handler | Typical outcome |
| --- | --- | --- |
| Unauthenticated, accessing protected resource | `AuthenticationEntryPoint` triggered by `ExceptionTranslationFilter` | Redirect to login or 401 challenge |
| Submitting login form with wrong password | `AuthenticationFailureHandler` of the authentication filter | Redirect `/login?error` or generic 401 |
| Logged in, lacking permission for `/admin` | `AccessDeniedHandler` via authorization/`ExceptionTranslationFilter` | 403 Forbidden |
| Login succeeds | `AuthenticationSuccessHandler` | Redirect to target/saved request or JSON |
| Logout succeeds | `LogoutSuccessHandler` | Redirect or HTTP status for logout |

**Never handle authorization errors by faking a login failure.** For example, an authenticated user missing `ROLE_ADMIN` should receive 403, not be told "wrong password" or have their authentication needlessly wiped.

**There is no automatic global handler for an entire resource server.** Invalid bearer tokens normally use `AuthenticationEntryPoint`/OAuth2 error responses; missing scopes/authorities go through `AccessDeniedHandler`. Do not treat `formLogin.failureHandler` as covering all API 401s.

## 16. Filter Chains, RequestMatcher, and Skipped Handlers

A very common mistake: declaring a handler bean and attaching it to `formLogin`, yet when sending JSON login or calling another endpoint, the handler never runs.

Causes to check:

1. Request **does not match the filter**: `loginProcessingUrl`, HTTP method, or `securityMatcher`.
2. Request is blocked **before the login filter**: missing CSRF, CORS preflight, request size/malformed body, another custom filter.
3. Request is handled by a different chain when multiple `SecurityFilterChain`s have different `@Order`/matchers.
4. Actual auth mechanism is HTTP Basic, bearer, `oauth2Login`, or a custom filter without the handler registered.
5. Error thrown inside `attemptAuthentication(...)` is not an `AuthenticationException`.
6. Endpoint is a controller calling `AuthenticationManager` directly instead of going through `UsernamePasswordAuthenticationFilter`.
7. Another handler configured later overwrote the setting on the same filter/configurer.

**Tip:** test with real requests passing through the Spring Security filter chain. Do not just unit-test `handler.onAuthenticationSuccess(...)` and assume the login endpoint uses it.

### Multiple Chains Example (Illustrative)

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .sessionManagement(s -> s
            .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated())
        .oauth2ResourceServer(o -> o.jwt(Customizer.withDefaults()));
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(a -> a
            .anyRequest().authenticated())
        .formLogin(form -> form
            .successHandler(webSuccess)
            .failureHandler(webFailure));
    return http.build();
}
~~~

This is **non-standalone integration code**, requiring imports, `webSuccess`/`webFailure` beans, and a JWT decoder/issuer config with dependencies. It shows that web handlers **do not govern responses for `/api/**`**.

## 17. SecurityContextRepository, Session Fixation, and Response Commit

The success handler runs at **the end of an authentication attempt**, yet login validity across the next request depends on **context persistence**:

- `SecurityContextHolder` holds context for the current thread/request.
- `SecurityContextRepository` defines how context is saved/loaded, using `HttpSession`, request attributes, or null.
- Spring Security 6 uses `SecurityContextHolderFilter`/explicit save in modern configs.
- When properly configured, `AbstractAuthenticationProcessingFilter` proactively saves context in the success flow before calling the handler.
- A custom login controller/filter without proper repository config can return 200 from its success handler **without keeping the browser logged in on the next request**.

If calling `AuthenticationManager.authenticate(...)` directly in a controller:

~~~java
// SKETCH CODE for custom login, not standalone.
// Must handle SessionAuthenticationStrategy, CSRF,
// success/failure handling, and response lifecycle completely.

Authentication verified =
        authenticationManager.authenticate(unauthenticatedToken);

sessionAuthenticationStrategy.onAuthentication(
        verified, request, response);

SecurityContext context =
        securityContextHolderStrategy.createEmptyContext();
context.setAuthentication(verified);
securityContextHolderStrategy.setContext(context);

securityContextRepository.saveContext(context, request, response);

// Finalize redirect/JSON only after saving.
successHandler.onAuthenticationSuccess(
        request, response, verified);
~~~

**Do not treat this snippet as advice to replace standard `formLogin`**: the framework also handles session fixation, remember-me, exception mapping, events, concurrent session controls, request caching, and more. When forced to write a custom filter, configure all of them deliberately.

**Save before response commit**: `response.sendRedirect(...)` or writing a large body can commit the response before the session cookie is written. The handler must be the final step in the HTTP flow—never wait until after the handler redirects to persist the context.

## 18. Post-Login Navigation and Open Redirect Risk

Parameters such as:

~~~text
/login?next=https://attacker.example/
POST /login (targetUrlParameter=http://outside.example/)
~~~

must never be blindly trusted. A handler calling `response.sendRedirect(request.getParameter("next"))` turns a legitimate domain into a phishing relay.

### Safe Target Policies

- Prefer fixed internal URLs like `/dashboard`.
- To preserve the original URL, use `RequestCache`/`SavedRequestAwareAuthenticationSuccessHandler` under controlled policy rather than storing an unverified `next`.
- If a redirect parameter is allowed, enforce a **strict allowlist** on scheme/host/path; even better, accept only normalized context-relative paths.
- Never trust `Referer` as authorization proof; it can be missing or spoofed.
- Never allow redirects into endpoints that perform state-changing actions via GET alone.
- When redirects include a tenant ID or state, verify tenant membership/authorization server-side.
- Never place tokens, passwords, or sensitive emails in query strings; URLs leak into browser history, logs, and `Referer`.

Even a valid redirect **never grants permissions**. The destination resource must enforce server-side policies itself.

## 19. Failure Handlers Should Not Arbitrarily Become Brute-Force Managers

`AuthenticationFailureHandler` can emit audit events, increment counters, or trigger alerts. However, if all brute-force defense lives inside the handler after the provider has checked the password, attackers can burn BCrypt CPU before being throttled.

A layered design:

~~~text
Request /login
    |
    +--> Reverse proxy / WAF / IP + device throttling
    |
    +--> Application rate limit / risk check
    |
    +--> AuthenticationManager, PasswordEncoder
    |
    +--> Success/Failure handlers
                 |
                 +--> Audit event, metrics
                 +--> Public generic response
~~~

Considerations:

- Rate-limit by normalized IP/device/account and risk signals; not IP alone where NAT exists.
- Avoid counters or `429` acting as an oracle triggered only for existing usernames.
- Lockouts must not let an attacker permanently lock someone else's account via repeated failed tries.
- Use verified recovery channels; do not disclose account status before ownership is proven.
- Event auditing should be idempotent/retryable if queued; never block logins indefinitely on logging systems.
- CPU-intensive password hashing requires capacity planning; never "artificially sleep" in ways that invite DoS.

**Handlers are just where post-failure responses happen**, not the sole anti-automation layer.

## 20. Single Response and Side Effects Inside Handlers

A handler may send:

~~~java
response.sendRedirect("/dashboard");
~~~

or:

~~~java
response.setStatus(200);
response.getWriter().write("{\"code\":\"LOGIN_OK\"}");
~~~

**Never do both on the same response.** After `sendRedirect`/`sendError`, or once the response is committed, writing extra body, changing status, setting cookies, or saving context can throw `IllegalStateException` or be silently ignored.

### Things to Avoid in a Success Handler

- Calling slow external services before responding to the browser.
- Writing critical business data **after** sending the redirect.
- Assigning `ROLE_ADMIN` merely because the destination is `/admin`.
- Logging the full `Authentication`, passwords, or hashes.
- Putting access/refresh tokens in the URL.
- Using mutable singleton fields on the handler to hold current user state across requests.
- Writing a response and still continuing the filter chain down an unintended branch.

### Things to Avoid in a Failure Handler

- `ex.printStackTrace()` to stdout/HTTP or putting `ex.getMessage()` into JSON.
- Redirecting to distinct pages for unknown, locked, or disabled if it enables account enumeration.
- Logging raw submitted passwords or sensitive identifiers.
- Setting a trusted `SecurityContext` after authentication failed.
- Sending email/SMS on every failed attempt without rate limiting.
- Masking all infrastructure errors as 401 so operations never notices the system is broken.

**Additional note:** In apps returning JSON, use `ObjectMapper` or message converters for dynamic data instead of concatenating strings from client input. Constant JSON in the demo is purely minimal illustration; never interpolate usernames or exceptions directly into strings.

## 21. Separating Servlet and WebFlux

Both interfaces studied here belong to the **Servlet stack**:

~~~text
AuthenticationSuccessHandler  (jakarta.servlet.http.HttpServletRequest,...)
AuthenticationFailureHandler  (jakarta.servlet.http.HttpServletRequest,...)
~~~

In **WebFlux**, use reactive interfaces like `ServerAuthenticationSuccessHandler`/`ServerAuthenticationFailureHandler` with `WebFilterExchange`/`ServerWebExchange` and `Mono<Void>`, plus `ServerSecurityContextRepository`. Never copy Servlet handlers or `ThreadLocal` patterns into WebFlux.

Similarly, when authenticating via OAuth2/OIDC:

- Servlet OAuth2 login can attach success/failure handlers on the appropriate filter.
- OIDC adds nonce/state validation, callbacks, and session/client authorization flows; do not hand-roll redirect protocol logic from scratch.
- Bearer resource servers do not call the form-login handler on every request by default.
- Logout uses `LogoutSuccessHandler`, separate from login success handlers.

## 22. Testing Functionality at the Right Boundaries

### 22.1. Handler Unit Tests

With `MockHttpServletRequest`/`MockHttpServletResponse`:

- Success handler receives a trusted `Authentication` and returns expected status/Location/Content-Type/body.
- Failure handler facing `BadCredentials`/`Locked`/`Disabled` returns the same generic public response per policy.
- Never leaks exception messages, username existence, password hashes, sensitive authorities, or stack traces.
- Response does not cache sensitive data and contains no URLs outside the allowlist.
- Never sends both a redirect and JSON.
- Invoking the handler across multiple requests does not leak state via mutable singleton bean fields.

### 22.2. Filter Chain Integration Tests

**This is the crucial end-to-end verification.** Test HTTP requests through `SecurityFilterChain` with `MockMvc`/Spring Security Test:

~~~java
// PSEUDO-TEST: requires Spring Boot Test + spring-security-test,
// mock users, real SecurityFilterChain, and matching CSRF setup.
// Not a standalone JUnit class.

mvc.perform(formLogin().user("linh").password("correct"))
    .andExpect(authenticated());

mvc.perform(formLogin().user("linh").password("incorrect"))
    .andExpect(unauthenticated());

// If custom failure handler returns JSON:
mvc.perform(post("/login")
        .with(csrf())
        .param("username", "linh")
        .param("password", "incorrect"))
    .andExpect(status().isUnauthorized())
    .andExpect(content().json(
        "{\"code\":\"AUTHENTICATION_FAILED\"}"));
~~~

Tests must match the configured handlers: if using `failureUrl` 302, do not assert 401 on the same endpoint. If custom login expects a JSON body, send JSON and prove the right filter/controller parses it.

### 22.3. Complete Integration Matrix

| Scenario | What to verify |
| --- | --- |
| Valid credentials | Success handler runs **once**; context/session persists on next request if stateful |
| Wrong credentials | Failure handler runs, right status/body/redirect, no authenticated session |
| Unknown username | Public response does not leak account existence |
| Locked/disabled/expired | Login denied; consistent public contract, internal audit distinguishes |
| Saved URL existed before login | `SavedRequestAware` sends user to valid URL per policy |
| No saved URL | Uses default target accurately |
| `alwaysUseDefaultTargetUrl=true` | Does not restore saved URL against config |
| Malicious `targetUrlParameter`/`next` | No open redirect to external domains |
| Redirect after login | Session cookie set properly and next request is authenticated |
| Missing CSRF token | May be rejected before form filter per CSRF policy; handler need not run |
| Stateless API | Does not issue a session via form flow and never triggers unexpected web handlers |
| `AuthenticationManager` backend error | No stack trace leaked; operational failure handled separately |
| Concurrent logins | No context/principal leakage across requests |
| Multiple chains | Real endpoint hits the right chain/handler |
| Session fixation | Session ID protected per framework strategy |
| Logout | Dedicated logout handler; login handler is not reused in its place |
| Rate-limit | Does not leak `userExists` via 429/headers/timing |
| Audit/metrics | Never logs passwords/tokens/full principals; safe correlation IDs |

### 22.4. Why Testing Handlers Directly Is Not Enough

The Java demo calls `onAuthenticationSuccess`/`onAuthenticationFailure` directly on a mock response. It **does not** verify that the app's `UsernamePasswordAuthenticationFilter` registered the right instance, nor does it test CSRF, `SecurityContextRepository`, or session cookies.

A component can pass unit tests while the live HTTP endpoint still uses the default handler. Always send requests through the chain and test **the subsequent request** after login too.

## 23. Troubleshooting Common Errors

| Symptom | Common cause | Fix |
| --- | --- | --- |
| Login succeeds yet always goes to `/` | Default success target; no saved request or different handler | Check `SavedRequestAware` and `defaultSuccessUrl` |
| Login goes to dashboard, not original URL | `alwaysUseDefaultTargetUrl=true` or custom success ignores `RequestCache` | Use `false`/`SavedRequestAware` as intended |
| Failed login shows backend error details | Rendering `exception.getMessage()` or unstandardized default 401 | Generic failure response + separate audit |
| Login API receives JSON yet `formLogin` misses username | `UsernamePasswordAuthenticationFilter` reads request parameters | Use form-urlencoded or a full custom JSON auth flow |
| Created handler bean yet it never runs | Not wired to `formLogin`/filter or wrong chain/matcher | Check `SecurityFilterChain`, URL, method |
| Missing CSRF token stops failure handler from running | Request blocked by `CsrfFilter` before authentication | Provide/validate CSRF per policy |
| Login returns 200 yet next request is 401 | Custom controller didn't save `SecurityContext`/session | Explicit save to proper repository and session strategy |
| `sendRedirect` followed by setting JSON status | Response already committed | Pick one response type only |
| `/login?next=https://...` redirects to external site | Open redirect | Allow only normalized local URLs/allowlist |
| Logged-in user lacking privilege gets login failure | Confusing `AccessDeniedHandler` with auth failure | Return authorization 403 per policy |
| Bearer API endpoint doesn't invoke web handler | Resource server has its own filter/entry point | Attach policy to the right authentication mechanism |
| Login failure creates session storing exception | `SimpleUrlAuthenticationFailureHandler` saves it for view rendering | Use generic view, adjust session policy if needed |
| Handler announces account is locked | Public response leaks account status | Identical status/body/headers across sensitive failures |
| Session fixation from custom login | Skipped `SessionAuthenticationStrategy` | Integrate standard strategy/framework login |
| Two users see mixed redirect state | Singleton handler with mutable per-user field | Keep handlers stateless; read from request/auth |
| Login success slow due to external API call | Blocking I/O inside handler | Queue audit/notifications or handle async safely |
| Swapped handler yet remember-me still wrong | Different auth flow/config/filter; remember-me hooks independent | Inspect the full lifecycle |
| Unit tests pass yet production fails | Only unit-tested handler, skipped chain/cookie/redirect | Run MockMvc + real integration tests |

## 24. Production Checklist

1. **Choose login mechanism:** browser form/session, AJAX form-encoded, custom JSON, SSO, or bearer; never assume one handler fits all.
2. **Identify the right filter:** `UsernamePasswordAuthenticationFilter`, OAuth2 filter, or custom filter with matching URL/method/chain matcher.
3. **Keep providers doing authentication:** handlers never verify raw passwords or self-grant authorities.
4. **Pick one response contract:** redirect/forward or JSON, never mixed.
5. **Success target:** use `SavedRequestAware` if returning to original URLs, default target otherwise; guard against open redirects.
6. **Public failure:** identical response for unknown/bad/locked/disabled per threat model; never return exception messages.
7. **Internal auditing:** record minimal error category and request ID, never credentials or tokens.
8. **Session persistence:** custom stateful logins save `SecurityContext` via `SecurityContextRepository` before response commit.
9. **Session fixation:** use `SessionAuthenticationStrategy` and appropriate session/cookie flags.
10. **CSRF/CORS:** browser cookie auth must have CSRF protection; configure CORS and `SameSite` accurately.
11. **Rate limiting:** enforce before/outside `PasswordEncoder` appropriately; avoid account enumeration via 429/headers.
12. **No re-auth in handlers:** use the already-verified trusted authentication result.
13. **No mutable per-user state in beans:** Spring beans are normally singletons, so handlers must be concurrency-safe.
14. **Never block responses on external I/O:** audit/notifications need timeouts, retries, and queuing where appropriate.
15. **Logout is a separate flow:** configure `LogoutSuccessHandler` and proper session/token cleanup.
16. **Multiple chains:** test auth and responses per matcher; never confuse WebFlux with Servlet.
17. **Filter integration tests:** verify redirects/JSON, session cookies, and follow-up requests—not just handler methods.
18. **Security regressions:** test brute-force, account enumeration, open redirects, response leaks, CSRF, and error paths.

## 25. Self-Check Questions

**1.** Is `AuthenticationSuccessHandler` responsible for checking whether a password is right or wrong?  
**Answer:** No. That belongs to `AuthenticationManager`/`AuthenticationProvider`. The handler processes the HTTP response after success.

**2.** Using form login, the user wants to return to `/orders/42` after being redirected to login. Which handler should be used?  
**Answer:** `SavedRequestAwareAuthenticationSuccessHandler` paired with `RequestCache`, or default `formLogin` when no customization is needed.

**3.** How does `defaultSuccessUrl("/dashboard", true)` differ from `false`?  
**Answer:** `true` always goes to `/dashboard`; `false` preserves returning to the saved request when one exists per the success handler's policy.

**4.** A failure handler returns HTTP 423 when locked and HTTP 401 when password is wrong. What is the risk?  
**Answer:** Attackers can enumerate accounts and lock status from status codes. Return a generic public response per your threat model.

**5.** Does merely declaring an `AuthenticationFailureHandler` bean make every login attempt in the app use it?  
**Answer:** No. It must be attached to the right filter/configurer/`SecurityFilterChain`; other auth mechanisms have their own entry points and failure logic.

**6.** Why can a success handler return 200 JSON yet the next request still gets 401?  
**Answer:** A custom flow may have failed to save context/session, omitted the cookie, or the request entered the wrong chain; the handler does not guarantee persistence by itself.

**7.** Does swapping success/failure handlers make `UsernamePasswordAuthenticationFilter` read a JSON body?  
**Answer:** No. By default the filter reads servlet parameters; JSON login requires a dedicated parsing/authentication mechanism.

**8.** How do you distinguish `AuthenticationEntryPoint` from `AuthenticationFailureHandler`?  
**Answer:** The entry point initiates a login/challenge when accessing a resource unauthenticated; the failure handler handles a rejected authentication attempt.

**9.** How does `AccessDeniedHandler` differ from `AuthenticationFailureHandler`?  
**Answer:** `AccessDeniedHandler` handles insufficient authorization (usually 403) when already authenticated; the failure handler handles a failed login/auth attempt.

**10.** Can you redirect directly to a client's `next` query parameter?  
**Answer:** No. Validate/allowlist it to prevent open redirects and leaking tokens/secrets.

**11.** Why shouldn't `exception.getMessage()` be used as the login response?  
**Answer:** Messages can expose locked, disabled, or unknown-username states, infrastructure details, or account information.

**12.** If you want JSON back for an AJAX frontend while still using `formLogin`, how should requests be sent?  
**Answer:** By default, send `username`/`password` as form parameters (typically form-urlencoded) along with valid CSRF/cookies; JSON bodies require a different filter.

**13.** Does `AuthenticationSuccessHandler` have an overload accepting `FilterChain`?  
**Answer:** Yes, the Spring Security 6.5 Servlet interface has a four-parameter default overload; not every login filter necessarily invokes it.

**14.** Why can `SimpleUrlAuthenticationFailureHandler` create a session on a failed login request?  
**Answer:** It may store the exception in the session for the view to display after redirecting, if configured to allow session creation.

**15.** Once success/failure handlers pass unit tests, are they ready for production?  
**Answer:** Not yet. You must test the actual filter chain, URL/method, redirects, sessions, CSRF, saved requests, auditing, and security regressions.

## 26. Official References

- [Spring Security 6.5 – Form Login](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html): login filter, success/failure flows, and form configuration.
- [Spring Security 6.5 – Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, session strategies, and authentication results.
- [AuthenticationSuccessHandler API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationSuccessHandler.html): `onAuthenticationSuccess` overloads.
- [AuthenticationFailureHandler API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html): `onAuthenticationFailure`.
- [AbstractAuthenticationProcessingFilter API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html): `attemptAuthentication`, `successfulAuthentication`, `unsuccessfulAuthentication`, hooks, repository, and filter lifecycle.
- [SavedRequestAwareAuthenticationSuccessHandler API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SavedRequestAwareAuthenticationSuccessHandler.html): target URL selection order.
- [SimpleUrlAuthenticationSuccessHandler API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SimpleUrlAuthenticationSuccessHandler.html): target URL and session failure attribute cleanup.
- [SimpleUrlAuthenticationFailureHandler API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/SimpleUrlAuthenticationFailureHandler.html): default failure URL, 401, and saving exceptions.
- [DelegatingAuthenticationFailureHandler API 6.5.11](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/DelegatingAuthenticationFailureHandler.html): selecting handlers by exception type.
- [Spring Security 6.5 – Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): persisting context for custom authentication.
- [OWASP Authentication Cheat Sheet – Error Messages](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html#authentication-and-error-messages): preventing account enumeration through error responses, timing, and flow.
- [OWASP Unvalidated Redirects and Forwards Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Unvalidated_Redirects_and_Forwards_Cheat_Sheet.html): allowlisting redirect targets.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session security, fixation, and logout lifecycle.

**Remember:** `AuthenticationSuccessHandler` answers **"authentication succeeded—where does the client go / what does it receive?"**; `AuthenticationFailureHandler` answers **"authentication failed—what safe response does the client receive?"**. They sit **after `AuthenticationManager`/provider decisions** and never replace credential verification. For form login, prefer configuring `defaultSuccessUrl`, `failureUrl`, and `SavedRequestAwareAuthenticationSuccessHandler`; for AJAX, return JSON per contract while keeping sessions/CSRF/filters fully configured. When customizing, never leak account state through errors or redirect to untrusted URLs.
