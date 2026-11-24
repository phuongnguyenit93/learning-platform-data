# Distinguishing Continuing the Chain, Returning a Response, and Delegating Errors to the Right Component

## 1. Three Decisions of a Servlet Filter That Must Not Be Mixed

In a Servlet-based Spring Security application, every HTTP request passes through a filter chain before reaching `DispatcherServlet`, a controller, or a target servlet. A filter may inspect headers, authenticate, rate-limit, enforce authorization, or log. Once it finishes inspecting the request, the filter **must choose how to hand off control**: let downstream layers proceed, terminate the response itself, or let an appropriate error-handling mechanism decide.

These three choices have vastly different consequences:

1. **Continue the chain:** call `FilterChain.doFilter(request,response)`. Remaining filters and the servlet/controller get to run.
2. **Handle the response directly:** set HTTP status/headers/body or redirect and then **return**, without calling the chain further. The filter has taken responsibility for concluding the current request.
3. **Throw an exception:** throw a semantically accurate exception for a configured handler, **which only works if the exception actually passes through a matching catcher in the current filter order**. Security exceptions do not magically turn into 401/403 everywhere.

This is the core of **"Distinguishing Continuing the Chain, Returning a Response, and Delegating Errors to the Right Component"**, part of the **"Filter Integration"** group in Spring Security - authentication.

**After this lesson**, readers can:

- Precisely distinguish `chain.doFilter`, `return` after writing a response, and `throw`.
- Understand how `ExceptionTranslationFilter`, `AuthenticationEntryPoint`, `AccessDeniedHandler`, and `AuthenticationFailureHandler` differ.
- Pick the right handling path for insufficient authentication, failed login, missing permissions, rate limiting, validation errors, and system failures.
- Recognize the impact of **filter order** and **committed response** state.
- Test every branch using a Java 17 program running through Spring Security 6.5 APIs and Servlet mocks.

## 2. A Filter Chain Is Nested Calls, Not an Auto-Running List

A `jakarta.servlet.Filter` has the method:

```java
void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException;
```

Calling `chain.doFilter(...)` means the filter is **handing execution to the rest of the chain**. It is not merely "signaling done" or "moving to the next line" in an abstract list.

Example with three filters:

```text
Client
  |
  v
Filter A -- before
  |
  +--> chain.doFilter(...)
           |
           v
        Filter B -- before
           |
           +--> chain.doFilter(...)
                    |
                    v
                 Filter C -- before
                    |
                    +--> chain.doFilter(...)
                             |
                             v
                         Controller/Servlet
                             |
                    <--------+
                    |
                 Filter C -- after
           <--------+
           |
        Filter B -- after
  <--------+
  |
Filter A -- after
  |
  v
Response
```

If `Filter B` **does not call the chain** and returns an HTTP response, `Filter C` and the controller **do not run**, yet code in `Filter A` **after its `chain.doFilter` call** can still execute as the call stack unwinds normally.

This is easy to overlook: **"Stopping the chain at Filter B" does not unwind or cancel code after `chain.doFilter` in earlier filters.** `finally` blocks or post-chain code in upstream filters can still run. Therefore, never write extra response bodies or late redirects in post-processing code when another filter may have already committed the response.

### Key Properties to Understand

- `chain.doFilter` should normally be called **once** along a given processing path, unless an explicit looping mechanism is designed.
- After delegating downstream, a filter **can run post-processing logic** if no exception alters control flow.
- If a filter **does not call the chain**, nothing guarantees the Servlet/controller will run.
- If a filter **throws an exception**, the stack unwinds until a matching catch block; filters downstream of the throw never get a chance to run.
- `sendRedirect`, `sendError`, and writing a response **do not call the chain automatically**; they are operations on the response.
- `return` exits the current `doFilter` method; it does not mean "proceed to the next filter".

### Typical Java Skeleton

```java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    // Before the rest of the application.
    doBefore(request);

    try {
        chain.doFilter(request, response);
    } finally {
        // Cleanup or timing, even if downstream throws an error.
        cleanup();
    }
}
```

This is an **illustrative snippet** requiring a class that defines `doBefore` and `cleanup`; it is not a standalone program. Use `finally` for proper cleanup, and **never** write an error JSON in `finally` when downstream may have already succeeded or committed the response.

## 3. Decision A: Continue the Chain When the Filter Does Not Consume the Request

Appropriate scenarios:

- The request **does not match** the endpoint this filter owns, e.g., a filter handling `POST /login` receives `GET /catalog`.
- A valid, non-blocking check, such as attaching a verified correlation ID.
- A per-request authentication mechanism succeeded and is designed to pass through to authorization/controllers, such as a resource-server bearer token filter.
- A filter solely recording metrics, wrapping request/response objects, or applying downstream policies.

Proper pattern:

```java
if (!appliesToThisRequest(request)) {
    chain.doFilter(request, response);
    return;
}

if (passesPolicy(request)) {
    chain.doFilter(request, response);
    return;
}

// From here policy has rejected. Choose response handling or exception.
```

This is **Java pseudocode** requiring corresponding methods and variables. Returning after `chain.doFilter` is optional if the method ends naturally, yet makes it explicit that the branch **does not fall through into error-handling code below**.

### Distinguish Authentication Filters from Authorization Filters

A per-request authentication filter can establish authentication and continue the chain; by contrast, when `UsernamePasswordAuthenticationFilter` / `AbstractAuthenticationProcessingFilter` receives **the matching login processing request**, it normally **consumes the request** and invokes success/failure handlers without continuing to a controller like a normal request.

Therefore:

> "When authentication succeeds, every filter must call `chain.doFilter`" is a false conclusion.

Whether it should depends on **filter type and endpoint contract**. Token authentication on `GET /api/orders` differs from form login `POST /login`.

### An Example with `OncePerRequestFilter`

`OncePerRequestFilter` is helpful for custom Servlet filters because it provides `doFilterInternal(HttpServletRequest,HttpServletResponse,FilterChain)` and manages dispatch-scoped marker attributes and skip hooks per contract.

```java
public final class RequestMarkerFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        response.setHeader("X-Request-Checked", "true");
        chain.doFilter(request, response);
    }
}
```

This is an **illustrative class for projects using Spring Web**, requiring imports. The header is set before `chain.doFilter` to avoid trying to write headers after the response commits. It performs no authentication; it only demonstrates pass-through.

**Do not assume `OncePerRequestFilter` guarantees "strictly once across every `REQUEST`/`ERROR`/`ASYNC` dispatch".** How the filter is registered, skip methods, dispatcher types, and Servlet lifecycle must still be verified.

## 4. Decision B: Write the HTTP Response and End the Current Filter

When a filter genuinely **owns the response**—such as rejecting a request due to rate limits or handling a dedicated JSON endpoint—it can set status, headers, content type/body, and **return**.

Rate-limiting example:

```java
if (!rateLimiter.allow(request)) {
    response.setStatus(HttpServletResponse.SC_TOO_MANY_REQUESTS);
    response.setContentType("application/json");
    response.setCharacterEncoding("UTF-8");
    response.setHeader("Cache-Control", "no-store");
    response.getWriter().write(
            "{\"error\":\"too_many_requests\"}");
    return; // Do not call chain after deciding to block.
}

chain.doFilter(request, response);
```

This is **integration code**: `rateLimiter` is undefined; never deploy this without real rate limiting and trusted IP/user source analysis.

This branch means:

- **Downstream** filters/controllers do not run.
- The client receives a response per the filter's contract.
- No `AuthenticationException` is thrown for another authentication handler to reshape the response.
- **Upstream** filters may still execute cleanup/post-processing as the stack unwinds.
- Once a body is written, **never continue the chain** and let a controller write a second body.

### `setStatus` Differs from `sendError` and `sendRedirect`

| Operation | Effect | Common risk or misconception |
| --- | --- | --- |
| `response.setStatus(401)` | Sets HTTP code; does not pick a body or auto-commit immediately. | Must ensure body/headers satisfy the API contract and terminate cleanly. |
| `response.getWriter().write(...)` | Writes response content via writer. | Cannot mix with `getOutputStream` on the same response; charset/content type must match. |
| `response.sendError(403)` | Asks container to handle error response/status per Servlet semantics. | May trigger an error page/`ERROR` dispatch depending on container; not the same as throwing `AccessDeniedException` to Spring Security. |
| `response.sendRedirect("/login")` | Sends redirect with `Location` header via container. | Must not continue chain; never redirect to client-controlled URLs (open redirect). |
| `response.flushBuffer()` | Forces buffer flush, usually **committing** headers/status. | After commit, status/headers can no longer be changed cleanly. |
| `return` | Exits current filter method. | Does **not** set status or body itself; leaving them unset may send an unintended default response. |

**Special distinction:** `sendError(401)` **is not equivalent to** `throw new BadCredentialsException(...)`. One asks the Servlet container to manage an error response; the other is an exception that Spring Security handlers can catch if positioned and contracted properly.

### Never Call `chain.doFilter` After Sending a Response

**Wrong:**

```java
response.setStatus(401);
response.getWriter().write("{\"error\":\"unauthorized\"}");
chain.doFilter(request, response); // May still execute the controller!
```

**Right for self-handled branch:**

```java
response.setStatus(401);
response.setContentType("application/json");
response.getWriter().write("{\"error\":\"unauthorized\"}");
return;
```

However, if this is a security failure governed by Spring Security authentication/authorization policies, **you should normally use the appropriate `EntryPoint`/`FailureHandler`/`AccessDeniedHandler`** rather than scattering 401/403 logic across every custom filter. Sections 6–8 classify these.

### Why Must You Not "Return Empty 200" When Blocking?

If code only says:

```java
if (blocked) {
    return;
}
```

the response may retain default status `200` with an empty body, leading the client to think the request succeeded. Whether that branch means "awaiting MFA", "rate-limited", or "unauthorized", define an **explicit HTTP contract**: status, body, retry/error semantics, and how the client proceeds.

In multi-step authentication, returning `null` from a method like `attemptAuthentication` can mean "incomplete", yet the subclass must still send its redirect/response; it does **not** automatically send 401 or 202.

## 5. Decision C: Throw a Semantically Accurate Exception in the Right Position

A filter or controller may detect a condition that a centralized component should handle. Instead of duplicating status/body writing everywhere, it can **throw the right exception type**.

Example:

```java
throw new AccessDeniedException("Policy denies this resource");
```

Before throwing, ask **three questions**:

1. **Who will catch it?** `ExceptionTranslationFilter`, a login filter's `AuthenticationFailureHandler`, `@ControllerAdvice`, MVC exception resolvers, or the Servlet container?
2. **Is the position right?** Is the exception thrown **inside the `chain.doFilter` call wrapped by the catching component**?
3. **Can the response still be modified?** Have status, headers, or body already been committed earlier?

An exception **does not inherently carry a fixed HTTP status**. `AuthenticationException` is Spring Security's authentication exception family; `AccessDeniedException` is its access-denial family. Mapping to 401/403/302 depends on handlers/entry points, policies, and current authentication.

### Use Appropriate Exceptions, Do Not Abuse Them

- **`AuthenticationException`:** a request requires authentication, or authentication is insufficient/invalid per Spring Security contract, e.g., `BadCredentialsException`, `InsufficientAuthenticationException`.
- **`AccessDeniedException`:** **authorization/security policy** evaluated the request and denied access. Can trigger either an entry point or access-denied handler depending on authentication state.
- **Request validation errors:** normally return 400 or structured error via controller/validation/error handler; never convert them into `AuthenticationException` to "pass through Spring Security".
- **Database errors, timeouts, bugs/null pointers:** belong to operational/application error handling. Never turn every error into `AccessDeniedException` returning 403 to hide bugs.
- **Rate limits:** normally return HTTP 429 via a dedicated rate-limit handler/filter. Not equivalent to wrong credentials or missing roles.
- **Resource not found:** normally 404 per app contract and anti-disclosure policy; never stuff into `BadCredentialsException`.

**Rule:** pick the exception type reflecting **the real cause and the component authorized to handle it**; if you cannot identify which handler owns it, do not throw it hoping Spring Security will figure it out.

## 6. ExceptionTranslationFilter: Bridge Between Security Exceptions and HTTP

In Spring Security Servlet, **`ExceptionTranslationFilter`** is the standard component that translates `AuthenticationException` and `AccessDeniedException` thrown within **the portion of the chain it wraps** into HTTP actions.

Basic diagram:

```text
             ExceptionTranslationFilter
                        |
                  try {
                        |
                        v
                  chain.doFilter(...)
                        |
              downstream filters/controllers
                        |
                  may throw ...
                        |
                  } catch (...)
                        |
            +-----------+--------------+
            |                          |
   AuthenticationException     AccessDeniedException
            |                          |
            v                  +-------+--------+
   AuthenticationEntryPoint    |                |
   initiate authentication     v                v
                           anonymous /        fully authenticated
                           remember-me         |
                               |                |
                               v                v
                    AuthenticationEntryPoint  AccessDeniedHandler
                         usually 401/302        usually 403
```

Note: **`ExceptionTranslationFilter` does not verify credentials or make authorization decisions itself**. Other filters, providers, and authorization components do that; the translation filter chooses how to respond based on the exception and context.

### 6.1. `AuthenticationException` → AuthenticationEntryPoint

When a security exception of type `AuthenticationException` reaches the translator, it invokes authentication-initiation logic. Depending on configuration:

- **Form login:** `LoginUrlAuthenticationEntryPoint` can redirect to the login page.
- **HTTP Basic:** `BasicAuthenticationEntryPoint` typically returns HTTP 401 and a `WWW-Authenticate` challenge header per scheme.
- **Bearer token/resource server:** `BearerTokenAuthenticationEntryPoint` applies bearer-scheme responses/challenges.
- **Custom REST API:** a custom entry point can return JSON 401 without disclosing sensitive details.

A request denied for lacking valid credentials does **not necessarily** receive any specific fixed text or body; that is decided by the entry point.

### 6.2. `AccessDeniedException` Does Not Always Return 403

When catching `AccessDeniedException`, the translator inspects current authentication:

- **Anonymous**: needs to start authentication; normally calls `AuthenticationEntryPoint` (401 or redirect).
- **Remember-me** deemed insufficient for the requirement: may call the entry point to demand stronger authentication.
- **Fully authenticated** yet lacking privileges: calls `AccessDeniedHandler`; usually 403.

That explains why a URL requiring `ROLE_ADMIN` can return **401/302 for an unauthenticated visitor** yet return **403 for a logged-in user with `ROLE_READER`**.

**Do not assume `AccessDeniedException` always produces HTTP 403.** An anonymous user has no verified identity to justify "logged in yet missing role". Classification is also shaped by `AuthenticationTrustResolver` and policy.

### 6.3. RequestCache and Saved Requests

When initiating authentication, the translator can use `RequestCache` to save the original request so the user returns to the page they wanted after logging in. In session-backed setups, the cache may use `HttpSession`; in stateless APIs, `NullRequestCache` is often used.

This explains a redirect sequence like:

```text
GET /reports/annual -> 302 /login
POST /login (succeeds)
-> redirects back to /reports/annual
```

**Do not confuse saved requests with granting permissions.** Request cache does not replace authentication or authorization; post-login redirects still traverse the security filter chain. Never accept arbitrary user-supplied return URLs that create open redirects.

### 6.4. Exceptions the Translator Is Not Responsible For

`ExceptionTranslationFilter` is not a universal `catch(Throwable)`:

- `IllegalArgumentException`, `NullPointerException`, JDBC errors, JSON parsing failures, or ordinary `IOException`s are not automatically turned into security 401/403s.
- If an MVC `HandlerExceptionResolver`/`@ControllerAdvice` handles an exception inside `DispatcherServlet` and writes a response, the translator may **never see the exception**.
- If an exception is thrown by a filter **before** the translator **prior to calling the chain**, the translator is not on the call stack to catch it.
- If the response is already **committed**, even if the translator sees `AuthenticationException`/`AccessDeniedException`, it can no longer safely build an error response; the framework may throw an extra `ServletException` indicating it cannot handle the error safely.

### 6.5. Filter Order Has Concrete Control-Flow Meaning

Suppose the chain runs in this order:

```text
Filter A
  |
  v
ExceptionTranslationFilter
  |
  v
Filter B (authorization)
  |
  v
Controller
```

`ExceptionTranslationFilter` calls `chain.doFilter(...)` to invoke **B + controller**. If B throws `AccessDeniedException`, the exception unwinds through the translator and becomes a response. However, if **A throws an exception before calling `chain.doFilter`**, the translator has not been called yet and **cannot catch it**. That is a direct consequence of nested filter calls.

**Do not assume adding `ExceptionTranslationFilter` to a security chain makes custom filters anywhere automatically turn exceptions into 401/403.** If a custom authentication filter sits upstream of the translator, it must normally use **its own failure handler/entry point**, or follow an explicitly designed error path.

## 7. Distinguishing AuthenticationEntryPoint, FailureHandler, and AccessDeniedHandler

The three interfaces carry distinct responsibilities:

| Component | When should it be called? | Typically handles | Not primarily responsible for |
| --- | --- | --- | --- |
| **`AuthenticationEntryPoint`** | Request does not meet auth requirements; need to start/challenge login | Redirect to login page, HTTP 401 + challenge header, JSON 401 | Does not verify raw passwords in a login POST. |
| **`AuthenticationFailureHandler`** | A **login attempt** was tried by an authentication filter and failed | Redirect `/login?error`, JSON error, 401, safe messaging policy | Does not decide 403 for all authorization failures. |
| **`AccessDeniedHandler`** | Sufficiently authenticated yet lacking permissions | 403, denied page, or JSON per API contract | Does not invite anonymous login in every situation. |

### 7.1. Wrong-Password Form Login Usually Does Not Reach ExceptionTranslationFilter

With `UsernamePasswordAuthenticationFilter` (a subclass of `AbstractAuthenticationProcessingFilter`), the basic branch is:

```text
POST /login
    |
    v
UsernamePasswordAuthenticationFilter
    |
    +--> AuthenticationManager.authenticate(...)
             |
             +-- wrong --> BadCredentialsException
                          |
                          v
                    unsuccessfulAuthentication(...)
                          |
                          v
                    AuthenticationFailureHandler
                          |
                         RETURN
             |
             +-- right --> successfulAuthentication(...)
                          |
                          v
                    AuthenticationSuccessHandler
                          |
                         RETURN
```

The login filter **catches authentication exceptions inside its own attempt flow** and invokes the failure handler. It does not forward wrong-password exceptions to the downstream translator. If you write a custom filter and throw `BadCredentialsException` **before** the translator, you cannot expect the translator to catch it.

Never write:

```java
try {
    authenticationManager.authenticate(token);
} catch (AuthenticationException ex) {
    throw new AccessDeniedException("Not allowed", ex);
}
```

to "force login failures into 403". That mixes authentication and authorization, yields wrong statuses/messages, and can leak information. Use the proper authentication failure mechanism.

### 7.2. Accessing a Protected Resource Unauthenticated

`AuthorizationFilter` can deny access because the user fails policy. The translator placed before it in the filter chain catches the matching exception and calls the entry point to **initiate authentication**.

This might be HTTP 401 for an API or a redirect for a browser—no `POST /login` needs to be in that request.

### 7.3. Logged In Yet Missing a Role

An authenticated user with `ROLE_READER` calls `GET /admin`, which requires `ROLE_ADMIN`. The error is **authorization**, not a wrong password: `AccessDeniedHandler` can return 403.

**Never clear `SecurityContext` to force 401 instead of 403** just because the UI wants to show a login screen. Downgrading authentication or demanding step-up must come from an explicit trust policy with clear justification.

## 8. Branch Selection Table by Real Scenario

| Scenario | Continue chain? | Handle response directly? | Delegate error to whom? |
| --- | --- | --- | --- |
| Filter only adds correlation ID | **Yes**, after setting header/context | No | Downstream handles application exceptions |
| Custom filter does not apply to current URL | **Yes** | No | No error |
| Resource-server filter validates bearer token cleanly | Usually **yes** so authorization/controller run | Not here | Per authentication filter/framework |
| Form `POST /login` succeeds | Usually **no** inside login processing filter | Success handler may send 200/204/302 | `AuthenticationSuccessHandler` |
| Form `POST /login` wrong password | Usually **no** | Failure handler may send 401/302 | `AuthenticationFailureHandler` |
| Protected request from anonymous user | Exception reaches translator | Entry point may send 401/302 | `AuthenticationEntryPoint` |
| Authenticated user lacks authority | Exception reaches translator | Denied handler usually sends 403 | `AccessDeniedHandler` |
| Rate limit detected before controller | No when blocking | May return 429 | Dedicated rate-limit handler/filter |
| Required field missing in JSON body | Per controller/validation flow | 400 per API error contract | MVC validation/`@ControllerAdvice` |
| Database outage / bug | Exception normally routes to error handling | 5xx per policy, no stack trace dump | Application error handler/container |
| Multi-step auth callback incomplete | No inside filter-consumed request | Redirect/202/challenge per protocol | Corresponding filter/protocol handler |
| Response already committed when denial discovered | Cannot safely change status | Too late | Logging/rollback/fix ordering, never write a second response |

This table is a **decision guide**. Exact HTTP outcomes depend on `SecurityFilterChain`, authentication mechanisms, Servlet container, configured handlers, dispatcher types, and request/response lifecycles.

## 9. Committed Response: Point of No Return for Rewriting the Response

`HttpServletResponse` has a **buffer**. Once headers/status are committed, the app cannot freely alter them. Actions that commit or lead to committing:

- `response.flushBuffer()`.
- `sendError(...)` or `sendRedirect(...)` per Servlet contract.
- Writing a body large enough to overflow the buffer.
- Framework completing/flushing the response or connection beginning transmission.
- Streaming/SSE/async mechanisms flushing headers early.

A dangerous pattern:

```java
response.getWriter().write("partial response");
response.flushBuffer();
throw new AccessDeniedException("Permission missing");
```

At that point `ExceptionTranslationFilter`, even if properly positioned, **cannot turn an already-committed response into a clean error response**. You may hit a `ServletException` indicating the security exception cannot be handled because the response is already committed.

**Practical rule:** verify authentication, authorization, tenant policies, and denial conditions **before** writing a body or starting a stream. For streaming, define explicit post-commit error behavior (closing the connection, protocol-specific error frames/events, auditing) rather than trying to emit a second 401 JSON.

### How Does `isCommitted()` Help?

`response.isCommitted()` helps debug or guard error handlers against illegal writes, yet must never become "if committed, silently swallow the exception". The system still needs tracing and clear incident handling. More importantly, design flows so permission checks never happen too late.

### Why Do `sendError` and `ERROR` Dispatch Differ from Spring Security Exceptions?

`sendError(403)` asks the Servlet container to handle an error response. Depending on container/config, it can dispatch to an error page via `DispatcherType.ERROR`. By contrast, throwing `AccessDeniedException` to `ExceptionTranslationFilter` invokes `AccessDeniedHandler` or `AuthenticationEntryPoint` based on security context.

An app can combine both layers: the denied handler calls `sendError(403)`, and the container dispatches to `/error`. Verify authorization rules and filters for `ERROR` dispatches to prevent error loops or accidentally exposing sensitive data on error pages.

## 10. Runnable Java 17 Example with Spring Security 6.5.11

This program uses **Spring Security Web 6.5.11** and **Spring Framework 6.2.12 Servlet mocks**, requiring no web server or database. It directly tests all three decisions:

- `chain.doFilter` continuing to the terminal.
- Writing HTTP status/body directly and returning.
- Throwing `AuthenticationException`/`AccessDeniedException` **downstream** of `ExceptionTranslationFilter`.
- Distinguishing **anonymous** vs. **authenticated** denials.
- Non-security exceptions not being converted into 401/403 by the translator.
- Responses committed before a security throw cannot safely change status.
- Exceptions thrown by a filter **upstream** of the translator are not caught by the translator.

**Never use this simulation as a production login mechanism.** `SecurityContext` is populated with pre-built objects **strictly to study error-routing**, not to issue identities from real requests.

### 10.1. File Layout

```text
filter-routing-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    └── FilterRoutingDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'filter-routing-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
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
    implementation 'org.springframework.security:spring-security-web:6.5.11'
    implementation 'org.springframework:spring-test:6.2.12'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'demo.FilterRoutingDemo'
}
```

The versions above are fixed to test APIs in the Spring Security 6.5.11 line. In real Spring Boot apps, use BOM/dependency management to align supported Spring Framework/Spring Security versions. Library logs or warnings may appear depending on the environment; they are not part of the intentional stdout lines.

### 10.2. File `src/main/java/demo/FilterRoutingDemo.java`

```java
package demo;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authentication.InsufficientAuthenticationException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.access.ExceptionTranslationFilter;
import org.springframework.security.web.savedrequest.NullRequestCache;

public final class FilterRoutingDemo {

    // This filter is only for observing routing choices.
    // Not a complete production authorization policy.
    static final class DecisionFilter implements Filter {

        @Override
        public void doFilter(
                ServletRequest rawRequest,
                ServletResponse rawResponse,
                FilterChain chain)
                throws IOException, ServletException {

            HttpServletRequest request = (HttpServletRequest) rawRequest;
            HttpServletResponse response = (HttpServletResponse) rawResponse;
            String path = request.getRequestURI();

            switch (path) {
                case "/continue":
                    chain.doFilter(request, response);
                    return;

                case "/respond":
                    response.setStatus(202);
                    response.setContentType("text/plain");
                    response.getWriter().write("accepted");
                    return;

                case "/auth-required":
                    throw new InsufficientAuthenticationException(
                            "Authentication required");

                case "/denied":
                    throw new AccessDeniedException(
                            "Missing authority");

                case "/bug":
                    throw new IllegalStateException(
                            "Unexpected application failure");

                case "/late-denied":
                    response.flushBuffer(); // commit before reporting error
                    throw new AccessDeniedException(
                            "Authorization checked too late");

                default:
                    chain.doFilter(request, response);
            }
        }
    }

    private static void assumePrincipal(boolean anonymous) {
        SecurityContext context = SecurityContextHolder.createEmptyContext();

        // Sample identity only; NEVER create authenticated Authentication
        // from client-supplied username/roles in production.
        Authentication auth;
        if (anonymous) {
            auth = new AnonymousAuthenticationToken(
                    "demo-anonymous-key",
                    "anonymousUser",
                    AuthorityUtils.createAuthorityList("ROLE_ANONYMOUS"));
        } else {
            auth = UsernamePasswordAuthenticationToken.authenticated(
                    "lan",
                    null,
                    AuthorityUtils.createAuthorityList("ROLE_READER"));
        }

        context.setAuthentication(auth);
        SecurityContextHolder.setContext(context);
    }

    private static void run(
            String label,
            String path,
            boolean anonymous,
            ExceptionTranslationFilter translator,
            DecisionFilter decision,
            AtomicInteger entryCalls,
            AtomicInteger deniedCalls) {

        SecurityContextHolder.clearContext();
        assumePrincipal(anonymous);

        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", path);
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        int[] terminalCalls = {0};
        FilterChain terminal = (req, res) -> terminalCalls[0]++;

        FilterChain downstream =
                (req, res) -> decision.doFilter(req, res, terminal);

        int oldEntry = entryCalls.get();
        int oldDenied = deniedCalls.get();
        String thrown = "-";

        try {
            translator.doFilter(request, response, downstream);
        } catch (Exception ex) {
            // Only to DISPLAY the consequence in the console demo.
            // Real applications must report operational errors properly.
            thrown = ex.getClass().getSimpleName();
        }

        System.out.println(label
                + " status=" + response.getStatus()
                + " terminal=" + terminalCalls[0]
                + " entry=" + (entryCalls.get() - oldEntry)
                + " denied=" + (deniedCalls.get() - oldDenied)
                + " thrown=" + thrown);

        SecurityContextHolder.clearContext();
    }

    private static void runUpstream(
            DecisionFilter decision,
            ExceptionTranslationFilter translator,
            AtomicInteger entryCalls,
            AtomicInteger deniedCalls) {

        SecurityContextHolder.clearContext();
        assumePrincipal(true);

        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", "/auth-required");
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        int[] terminalCalls = {0};
        FilterChain terminal = (req, res) -> terminalCalls[0]++;

        // REVERSED layout: decision sits BEFORE translator.
        // When decision throws immediately, translator has never been invoked.
        FilterChain downstream =
                (req, res) -> translator.doFilter(req, res, terminal);

        int oldEntry = entryCalls.get();
        int oldDenied = deniedCalls.get();
        String thrown = "-";

        try {
            decision.doFilter(request, response, downstream);
        } catch (Exception ex) {
            thrown = ex.getClass().getSimpleName();
        }

        System.out.println("upstreamAuth"
                + " status=" + response.getStatus()
                + " terminal=" + terminalCalls[0]
                + " entry=" + (entryCalls.get() - oldEntry)
                + " denied=" + (deniedCalls.get() - oldDenied)
                + " thrown=" + thrown);

        SecurityContextHolder.clearContext();
    }

    public static void main(String[] args) {

        AtomicInteger entryCalls = new AtomicInteger();
        AtomicInteger deniedCalls = new AtomicInteger();

        ExceptionTranslationFilter translator =
                new ExceptionTranslationFilter(
                        (request, response, authException) -> {
                            entryCalls.incrementAndGet();
                            response.setStatus(401);
                        },
                        new NullRequestCache());

        translator.setAccessDeniedHandler(
                (request, response, accessDeniedException) -> {
                    deniedCalls.incrementAndGet();
                    response.setStatus(403);
                });

        translator.afterPropertiesSet();

        DecisionFilter decision = new DecisionFilter();

        run("continue", "/continue", true,
                translator, decision, entryCalls, deniedCalls);

        run("respond", "/respond", true,
                translator, decision, entryCalls, deniedCalls);

        run("authentication", "/auth-required", true,
                translator, decision, entryCalls, deniedCalls);

        run("anonymousDenied", "/denied", true,
                translator, decision, entryCalls, deniedCalls);

        run("authenticatedDenied", "/denied", false,
                translator, decision, entryCalls, deniedCalls);

        run("bug", "/bug", false,
                translator, decision, entryCalls, deniedCalls);

        run("lateDenied", "/late-denied", false,
                translator, decision, entryCalls, deniedCalls);

        runUpstream(decision, translator, entryCalls, deniedCalls);
    }
}
```

### 10.3. Run Command and stdout

With JDK 17+ and a Java-17-compatible Gradle/Gradle Wrapper:

```bash
gradle run --quiet
```

**Expected lines printed by the program itself** under the example config, excluding Gradle/runtime output:

```text
continue status=200 terminal=1 entry=0 denied=0 thrown=-
respond status=202 terminal=0 entry=0 denied=0 thrown=-
authentication status=401 terminal=0 entry=1 denied=0 thrown=-
anonymousDenied status=401 terminal=0 entry=1 denied=0 thrown=-
authenticatedDenied status=403 terminal=0 entry=0 denied=1 thrown=-
bug status=200 terminal=0 entry=0 denied=0 thrown=IllegalStateException
lateDenied status=200 terminal=0 entry=0 denied=0 thrown=ServletException
upstreamAuth status=200 terminal=0 entry=0 denied=0 thrown=InsufficientAuthenticationException
```

In the demo, `MockHttpServletResponse` starts with a default status of **200**. Thus `bug`, `lateDenied`, and `upstreamAuth` showing `status=200` on the mock object **does not mean a production client would receive a success**: those branches threw exceptions, and a real Servlet container/error handler may return HTTP 5xx or a configured error response. Nor do the results simulate the entire filter chain auto-configured by Spring Boot.

### 10.4. Why Does Each Line Produce That Output?

**`continue`:** `DecisionFilter` calls `terminal.doFilter` once. The translator sees no exception; mock status stays 200.

**`respond`:** the filter writes 202 and text itself, then `return`s; neither terminal, entry point, nor denied handler runs.

**`authentication`:** `DecisionFilter` downstream of the translator throws `InsufficientAuthenticationException`, an `AuthenticationException`. The translator catches it, performs context cleanup, and invokes the demo's entry point returning 401. Because `NullRequestCache` is configured, no session cache is used here.

**`anonymousDenied`:** even though the exception is `AccessDeniedException`, the current principal is `AnonymousAuthenticationToken`, so the translator invokes the entry point (401) instead of the denied handler.

**`authenticatedDenied`:** the simulated principal is authenticated with `ROLE_READER`, lacking the required permission in the demo scenario; the translator calls the denied handler returning 403.

**`bug`:** `IllegalStateException` is neither security exception type. The translator does not turn it into 401/403; the exception propagates outward to application/container error handling.

**`lateDenied`:** the code calls `flushBuffer` before throwing `AccessDeniedException`; the mock response is already committed. The translator cannot safely issue a new 403 and throws `ServletException` per its implementation. The mock status remains the committed 200; never infer the final network status on a real web server from this.

**`upstreamAuth`:** `DecisionFilter` sits outside the translator and throws before calling the chain. Because the translator is not on the call stack, the entry point is never called. This proves why **filter position determines whether a thrown exception reaches its handler**.

### 10.5. Limitations of the Demo

- Does not use `FilterChainProxy` or a full Boot-configured `SecurityFilterChain`; the demo assembles real Spring Security components in a unit/integration-style harness.
- Does not execute `AuthenticationManager.authenticate(...)`: principals are set programmatically for testing. **Never** copy `assumePrincipal` into real app filters.
- Has no credentials, session cookies, OAuth2/JWT, CSRF, or account-status checks.
- `NullRequestCache` avoids creating saved requests/sessions in the demo; real browser apps often use `HttpSessionRequestCache`.
- Has no MVC `@ControllerAdvice`, clearly illustrating exceptions escaping the filter stack when no resolver intercepts them.
- Status codes and callback counts reflect the demo handlers' contract, **not mandatory statuses for all Spring Security apps**.
- `entryCalls`/`deniedCalls` counters only verify branch execution, not security auditing.

## 11. Integrating Inside a Real SecurityFilterChain: Order Matters Greatly

### 11.1. Standard Component Positions

A typical `SecurityFilterChain` contains components across multiple stages:

```text
[Restore SecurityContext]
         |
[CSRF/CORS/headers and request protection]
         |
[Authentication filter: form/basic/bearer...]
         |
[AnonymousAuthenticationFilter when applicable]
         |
[ExceptionTranslationFilter]
         |
[AuthorizationFilter]
         |
[DispatcherServlet / controller]
```

This diagram is **conceptual**, not an exhaustive list or absolute order for every application. Spring Security may include many additional filters, multiple security chains, and version/config-specific variations. Enable controlled DEBUG/TRACE logging to inspect the actual order. Never log credentials when enabling trace.

**Consequence:** Authentication filters normally process credentials **before `ExceptionTranslationFilter`**, so they must proactively use their own failure handlers or entry points. `AuthorizationFilter` typically sits downstream of the translator, so denials it throws are handled by the translator according to authentication state.

### 11.2. Placing a Custom Filter in the Right Stage

Before adding:

```java
http.addFilterAfter(customFilter, AnonymousAuthenticationFilter.class);
```

clarify what the filter does: authentication, authorization, exploit protection, correlation ID, or rate limiting?

Above is a **DSL excerpt** requiring a configuration class/bean. `addFilterAfter(..., AnonymousAuthenticationFilter.class)` places the filter after the anonymous filter, yet **does not guarantee it sits downstream of `ExceptionTranslationFilter`**. In common layouts, it may still sit **before the translator**, meaning an `AccessDeniedException` thrown by that custom filter will not automatically be caught by the translator.

This is a very easy mistake to make:

> "I added a tenant authorization filter after `AnonymousAuthenticationFilter` and threw `AccessDeniedException`, why didn't I get a clean 403 like `AuthorizationFilter`?"

Because your custom filter may **run earlier than `ExceptionTranslationFilter`**. The right solution is inspecting the actual filter order and choosing one of these deliberate designs:

- Put authorization logic into `authorizeHttpRequests` policies, method security, or an `AuthorizationManager` so the framework handles it.
- If a custom filter owns a denial itself, configure an appropriate **`AccessDeniedHandler`/`AuthenticationEntryPoint`** right there instead of expecting a downstream translator to catch it.
- If you intentionally want the translator to wrap your filter, place it downstream of the translator and upstream of resource handling, understanding all ordering/authorization implications.
- For custom authentication, use an authentication filter/framework pattern with proper failure handling.

Do not arbitrarily move a filter after `AuthorizationFilter` just so exceptions get caught if doing so skips checks needed **before authorization**. Position filters according to responsibility and test thoroughly.

### 11.3. Multiple SecurityFilterChains

Spring Security can configure:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated());
    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain web(HttpSecurity http) throws Exception {
    http.authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());
    return http.build();
}
```

This is a **configuration excerpt**, requiring imports for `@Bean`, `@Order`, `HttpSecurity`, `SecurityFilterChain`, `Customizer`, plus complete session/CSRF/authentication policies. `FilterChainProxy` selects **the first matching security chain**, rather than "merging all chains". Thus `/api/**` can use different entry points/authorization than browser paths. Never debug a filter in the web chain assuming it handles the API chain.

**Security chain selection differs from `chain.doFilter`:** selecting a chain chooses **the list of filters**, whereas `chain.doFilter` inside decides **whether to run the rest of the selected list**.

### 11.4. Registering a Filter Twice

In Spring Boot, a `Filter` declared as `@Component` or `@Bean` can be auto-registered with the Servlet container. If that same instance or class is also added via `http.addFilterBefore/After`, the filter can run twice, outside and inside different security chains. That scrambles chain invocation counts, logs, response statuses, and exception-catching boundaries.

If a filter must be a Spring bean for dependency injection yet run only inside a Spring Security chain, disable container registration via `FilterRegistrationBean` or equivalent config, and test single execution at the exact position. Never assume `OncePerRequestFilter` solves all double-registration issues automatically.

## 12. MVC @ControllerAdvice, Servlet ERROR Dispatch, and Spring Security Differ

When an error occurs **inside a controller**, many Spring MVC apps use `@ControllerAdvice`/`@ExceptionHandler` or `HandlerExceptionResolver` to render exceptions as JSON or views. They **can handle errors before exceptions ever escape to the filter stack**.

| Error location | Who can handle it | What to verify |
| --- | --- | --- |
| Inside MVC-invoked controller/service | MVC `@ExceptionHandler`/`@ControllerAdvice`, or exception propagates out | Was the handler matched and did it write a response? |
| Inside a filter before `DispatcherServlet` | Filter-local handler, appropriate Spring Security filter, Servlet container | MVC advice does not automatically catch exceptions thrown before the dispatcher runs. |
| Inside an authentication filter | The filter's authentication failure handler/entry point | Does it catch `AuthenticationException` properly? |
| Inside `AuthorizationFilter` downstream of translator | `ExceptionTranslationFilter` | Anonymous/remember-me/authenticated context selects entry vs. denied. |
| Exception thrown by filter outside security chain | Surrounding container/global filter | Inner security translator never sees it if never entered. |
| `sendError` or unhandled exception | Servlet container error handling/`ERROR` dispatch | Dispatcher type, error page, and response commit state. |

### A Common Pitfall with `@ControllerAdvice`

Writing an overly broad `@RestControllerAdvice` catching `Exception.class` and returning HTTP 200 or a generic error JSON can **swallow `AccessDeniedException`** thrown by method security inside MVC. Then the translator never gets to handle it and the client receives the wrong status.

Do not blindly follow "let every `AccessDeniedException` bubble out of controllers": whether an exception escapes MVC depends on registered exception resolvers. Test `@PreAuthorize`/authorization and error mappings directly to ensure 401/403 reflect policy.

### Using ProblemDetail / RFC 9457

If an API uses `application/problem+json`, handlers can return structures with `type`, `title`, `status`, `detail`, and `instance` per contract. However:

- Never leak raw passwords, access tokens, bearer tokens, hashes, stacktraces, or sensitive account info.
- Actual HTTP status must match `status` in the body.
- Authentication entry points/`AccessDeniedHandler` remain the right places to handle security errors arising in the filter chain.
- Never build a new problem JSON after the response commits.
- A uniform body format does not mean collapsing every error type into HTTP 200.

## 13. When Do You Need 401, 403, 404, 429, or 5xx?

Each status describes a distinct situation. Never pick a status merely because "I want the request to stop".

| Code | Common meaning | Handling example |
| --- | --- | --- |
| **400 Bad Request** | Invalid request syntax/validation | MVC validation or API handler. |
| **401 Unauthorized** | Missing/invalid authentication; may issue a challenge | `AuthenticationEntryPoint`, appropriate login failure handler. |
| **403 Forbidden** | Resource denied per authorization policy | `AccessDeniedHandler`, `AuthorizationFilter`/method security. |
| **404 Not Found** | Resource does not exist or policy intentionally hides presence | MVC/resource handler per contract. |
| **409 Conflict** | Business state conflict | Service/controller exception mapping. |
| **422 Unprocessable Content** | Used by some APIs for syntactically valid input violating processing rules | API error mapping per contract, never treated as auth failure. |
| **429 Too Many Requests** | Request exceeds quota/rate limit | Gateway/filter/rate-limiter; may include `Retry-After` when justified. |
| **500 Internal Server Error** | Unhandled server bug/error | Global error handler, never expose stacktraces. |
| **503 Service Unavailable** | Downstream infrastructure temporarily unavailable | Error handler + retry/circuit-breaker policy, never disguised as wrong password. |

**401 does not automatically mean "wrong password"** and **403 does not automatically mean "logged in"**: policies, implementation, and actual context govern them. Standard HTTP 401 carries authentication challenge semantics; standardized endpoints should attach scheme-appropriate headers/challenges rather than arbitrary bodies alone.

### Example with Rate Limiting and Authentication

When rate-limited **before credential verification**, returning `429` and stopping the chain prevents wasting password-hashing CPU. When a login attempt reaches the provider and the password is wrong, the failure handler can return `401` or redirect. If both policies coexist, define their order and responses clearly—never wrap `rate limit exceeded` in `BadCredentialsException` just to reuse one handler.

### Example with Database Outage

If `UserDetailsService` cannot reach the database, that is an **infrastructure** failure, not proof of a wrong password. Trigger error/alert handling without granting authentication or exposing stacktraces. Returning 401 encourages users to retry passwords endlessly and hides the outage.

## 14. The "Sent Response Yet Still Ran Controller" Bug

Suppose a custom filter has:

```java
if (!tokenValid) {
    response.sendError(401);
}

chain.doFilter(request, response);
```

When the token is invalid, the filter requested a 401 error yet **still called the chain**, allowing downstream components to run, throw exceptions, log, mutate business state, or try writing another response. You cannot rely on `sendError` to terminate Java control flow.

**Minimal fix:**

```java
if (!tokenValid) {
    response.sendError(401);
    return;
}

chain.doFilter(request, response);
```

Understand that this is purely a **control-flow** example. For real token authentication, do not hand-roll a JWT verifier or bypass resource-server policies—check issuer, audience, signature, and expiry with the proper library and route failures to the right entry point. In a true authentication filter, use framework-supported failure handlers and entry points.

### Another Bug Variant: Calling the Chain Twice

```java
if (matchesSomeRule) {
    chain.doFilter(request, response);
}

chain.doFilter(request, response); // Second time!
```

When the condition is true, downstream runs twice, duplicating controller execution and causing unpredictable side effects. Always `return` after a branch or maintain a single `chain.doFilter` call path.

### Why Not "Solve" Things by Catching Every Exception?

```java
try {
    chain.doFilter(request, response);
} catch (Exception ex) {
    response.setStatus(200);
}
```

This is a severe anti-pattern: it suppresses security exceptions, disguises real failures and bugs as fake successes, breaks tracing, and risks inconsistent responses. If logging is needed, log safely and **rethrow** or delegate to the right handler. Never log raw credentials, `Authorization` headers, or sensitive response bodies during debugging.

## 15. Designing a Custom Filter with a Clear Contract

Before coding, write a decision table for your filter:

```text
Input: which filters has the HTTP request already passed?
    |
    v
Does this filter apply to the request?
    |
    +-- No: chain.doFilter -> return
    |
    +-- Yes:
         |
         +-- Valid condition and must proceed downstream?
         |       |
         |       +-- Yes: set appropriate attrs/headers/context
         |               -> chain.doFilter -> return
         |
         +-- Filter owns an error/early response?
         |       |
         |       +-- Yes: set status/headers/body or redirect
         |               -> return (do not call chain)
         |
         +-- Security error for framework to handle?
         |       |
         |       +-- Yes: identify exact exception class
         |               -> verify where catcher/handler sits
         |               -> throw or invoke handler per contract
         |
         +-- Business/infrastructure error?
                 |
                 +-- Route to matching MVC/global/container error
                     mechanism; never fake an auth error
```

A code review should answer:

1. Which **chain** does this filter sit in, and at what **position**?
2. On every branch, is `chain.doFilter` called **0, 1, or more times**?
3. When 0 times, **who wrote the response**?
4. When throwing an exception, **which layer catches it**, and is that layer **upstream or downstream** of the throwing filter?
5. Could anything write headers/body after the response has committed?
6. Do anonymous, remembered, and fully authenticated requests branch differently?
7. Could 4xx errors get mapped to 200, or infrastructure errors mapped to 401?
8. Does filter registration cause double execution across the Servlet container and `SecurityFilterChain`?
9. Does any sensitive data appear in `Authentication`, request logs, or exception messages?
10. On `ERROR`/`ASYNC` dispatches, does the filter re-run or skip, and is cleanup safe?

### Safe Post-Processing After `chain.doFilter`

Use `finally` or post-processing strictly for actions that **do not alter a committed response**, such as metrics/timing or clearing MDC/`ThreadLocal` state created by the filter itself. Never call `response.reset()` or overwrite HTTP status 200/401 in `finally`, as that can wipe or corrupt results from controllers or dedicated handlers.

## 16. Testing Must Cover Both Chain and Handlers

### 16.1. Unit Tests for Filter Flow

For a custom filter, include:

| Test | Setup | Useful assertion |
| --- | --- | --- |
| Does not apply | Different URL/method | `chain.doFilter` called exactly once. |
| Allowed | Valid token/policy | Request reaches downstream; filter writes no error status. |
| Blocked with response | Rate limit | Status 429, expected body, chain never called. |
| Auth exception downstream of translator | `AuthenticationException` | Entry point invoked, terminal never runs. |
| Access denied while anonymous | `AnonymousAuthenticationToken` | Entry point/challenge per policy. |
| Access denied while authenticated | Real `Authentication` | `AccessDeniedHandler` returns 403 per policy. |
| Non-security error | `IllegalStateException` | Not converted into 401/403 by translator. |
| Committed response | Flushed, then denied | No second status/body written; error properly observed. |
| Filter earlier than translator | Throws before calling chain | Translator does not intercept exception. |
| Dispatcher types | `REQUEST`/`ERROR`/`ASYNC` | No improper registration/execution across lifecycle. |

Use Mockito/`MockFilterChain` or Java lambdas with counters to prove which filter ran. **Never assert only the response status**: a filter can return 401 while still letting the controller execute and cause side effects.

### 16.2. Integration Tests with MockMvc and Spring Security

With a real `SecurityFilterChain`, use `MockMvc` and Spring Security test support to verify:

- Anonymous request to protected URL → scheme-appropriate entry point.
- Valid/wrong form login → matching success/failure handler and session/CSRF policy.
- Authenticated user missing role → 403.
- Custom rate limit → 429 and controller **never** called.
- Validation failure → 400 via MVC handler, never converted to login failure.
- System error → 5xx/error contract without leaking internal info.
- Filter/chain order: custom filter runs once and is not skipped due to another chain's `securityMatcher`.
- Redirect responses have valid `Location` without open redirects.
- `ERROR` and async dispatches if used in production.

`@WithMockUser` helps test authorization yet **does not prove** real authentication paths, filter matchers, password encoders, or session persistence. Use real credentials and authentication managers/providers in integration tests whenever verifying login.

### 16.3. Testing Status vs. Body After Response Commit

A test using only `MockHttpServletResponse` may allow simulated operations that behave differently in a real Servlet container. When products involve streaming, error dispatches, complex buffering, or reverse proxies, run integration tests against a real server and inspect actual HTTP bytes/statuses. Never extrapolate a default mock 200 into assuming production clients received HTTP 200.

## 17. Debugging Clues and Common Traps

1. **Wrote JSON 401 yet controller still ran:** forgot `return` or still called `chain.doFilter`.
2. **Filter ran twice:** registered in both container and security chain, or called `chain` twice.
3. **`AccessDeniedException` never reached `AccessDeniedHandler`:** thrown **before** `ExceptionTranslationFilter`, or caught earlier by MVC/resolver.
4. **Anonymous user got 401 instead of 403:** translator invokes entry point when auth is insufficient; often the intended behavior.
5. **Low-privilege user got 403:** access denied after full authentication; distinct from wrong password.
6. **Wrong-password login never hit `ExceptionTranslationFilter`:** authentication filters normally handle it via failure handlers.
7. **Swapping `BadCredentialsException` for `AccessDeniedException` to get 403:** wrong semantics, increases leak risk and breaks UX.
8. **Returning 200 with body `{"error":...}`:** clients and monitoring may treat it as success; statuses must be accurate.
9. **Writing body then throwing exception:** response may commit; handlers cannot cleanly rewrite body/status.
10. **`sendError` then continuing the chain:** Servlet error responses do not halt Java control flow.
11. **Throwing `RuntimeException` expecting Spring Security to return 401:** translator only handles matching security exception types.
12. **`@ControllerAdvice` catching broad `Exception.class` and swallowing authorization denials:** bypasses expected security handlers.
13. **Placing filter after `AnonymousAuthenticationFilter` assuming it is after translator:** check real filter order; those are two distinct milestones.
14. **Putting a custom filter after authorization when it needs to run before authorization:** too late or bypasses required policies.
15. **Sharing one chain for API and web while forgetting different entry points:** browsers may get JSON or APIs may get HTML redirects.
16. **Having multiple `SecurityFilterChain`s and debugging only one:** the first matching chain may lack the filter you expected.
17. **Returning `null` in an authentication filter without sending a response:** client may receive an empty response or ambiguous status.
18. **Enabling `continueChainBeforeSuccessfulAuthentication` to force controller execution:** downstream may run before the new authentication is saved.
19. **Writing response body inside `finally`:** downstream may have already committed or another handler is processing an exception.
20. **Catching every exception and converting to 403:** hides DB outages/bugs and muddies access control observability.
21. **Throwing `AccessDeniedException` for rate limits or infrastructure errors:** conflates 429/5xx with authorization.
22. **HTTP Basic 401 missing challenge header:** clients may not know how to authenticate; use scheme-standard entry points.
23. **Mutating `SecurityContextHolder` arbitrarily to force 403/401:** authentication state must come from trusted mechanisms with clean lifecycle cleanup.
24. **Constructing an authenticated token from client header values:** risks spoofing and privilege escalation.
25. **Logging full usernames/passwords/access tokens while debugging filter errors:** leaks credentials into logs/traces.
26. **Failing to test `DispatcherType.ERROR`:** error pages may get blocked a second time or restore wrong contexts.
27. **Ignoring streaming/async responses:** post-header errors need dedicated contracts rather than "redoing" a 401 JSON.
28. **Assuming `OncePerRequestFilter` prevents all double registration:** false across multiple registration/dispatch paths.
29. **Confusing `FilterChainProxy` chain selection with `FilterChain.doFilter`:** one chooses configuration; the other executes the rest of the chain.
30. **Asserting only status without asserting downstream invocation counts:** misses side effects even when responses look right.

## 18. Self-Check Questions

**Question 1.** What does calling `chain.doFilter(request,response)` mean?

**Answer:** It delegates execution to the rest of the filter chain and ultimately the servlet/controller. Once the call returns, upstream filters can run post-processing. It does not write a response itself.

**Question 2.** If a filter calls `response.sendError(401)`, does execution stop automatically?

**Answer:** No. Code must `return` or take another branch that avoids calling the chain; `sendError` operates on the Servlet response, not Java control flow.

**Question 3.** When is it appropriate for a filter to return 429 directly?

**Answer:** When a rate-limiter filter/gateway owns quota enforcement and the API response; it sets status/headers/body per contract and stops the chain to save downstream resources.

**Question 4.** Why doesn't `AccessDeniedException` always return HTTP 403?

**Answer:** `ExceptionTranslationFilter` may invoke `AuthenticationEntryPoint` for anonymous or insufficient remember-me principals; only sufficiently authenticated users lacking permissions normally reach `AccessDeniedHandler` for 403.

**Question 5.** Which component handles wrong-password form logins?

**Answer:** `AbstractAuthenticationProcessingFilter`/`UsernamePasswordAuthenticationFilter` normally catches `AuthenticationException` during the login attempt and invokes `AuthenticationFailureHandler`. Not every login failure propagates to the translator.

**Question 6.** Filter A throws `AuthenticationException` before calling a translator downstream of it. Can the translator catch it?

**Answer:** No. The translator has not been called yet, so it is not on the call stack to catch that exception. Choose the right filter order or a local handler.

**Question 7.** An MVC `@ExceptionHandler` on a controller already catches `AccessDeniedException` and returns a response. Will the translator always see it?

**Answer:** No. Once the resolver handles it, the exception no longer escapes to the translator. Always test real `@ControllerAdvice`/method-security mappings.

**Question 8.** A filter downstream of the translator throws `IllegalStateException`. Does it automatically become HTTP 401?

**Answer:** No. It is neither `AuthenticationException` nor `AccessDeniedException`; it normally routes to operational/MVC/container 5xx error handling.

**Question 9.** If a response is already committed and `AccessDeniedException` is thrown afterwards, can `setStatus` safely change it to 403?

**Answer:** Not reliably. Headers/status may already have been sent; Spring Security may throw an extra `ServletException` because it cannot handle it safely. Check permissions before streaming bodies.

**Question 10.** How does `AuthenticationEntryPoint` differ from `AuthenticationFailureHandler`?

**Answer:** An entry point initiates/challenges authentication for requests lacking sufficient identity; a failure handler presents **the failed outcome of a login attempt** tried by a filter.

**Question 11.** Is a custom filter placed after `AnonymousAuthenticationFilter` guaranteed to sit after the translator?

**Answer:** Never assume so. Common chains place the translator later; inspect the actual filter list and verify who catches exceptions.

**Question 12.** For stateless APIs, why must 401/403 not be decided solely by whether a session cookie exists?

**Answer:** Authentication may rely on bearer tokens or other mechanisms; policies must examine the real context, authentication level, and authorities. Session cookies are not a universal criterion.

**Question 13.** Why shouldn't `@WithMockUser` be used to conclude that the login filter works?

**Answer:** Mock user annotations inject `SecurityContext` directly without exercising matchers, providers, password encoders, failure handlers, or authentication persistence.

**Question 14.** What proves that a filter genuinely blocked a request?

**Answer:** Beyond verifying expected response status/body, verify **`chain.doFilter` was not called**, controllers had no side effects, the right handler ran, and no second response was written.

**Question 15.** A response object shows status 200 yet the filter method threw an exception—does that mean login succeeded?

**Answer:** No. A mock Servlet response can retain default status 200 before container exception handling runs. Observe exceptions and real HTTP server responses rather than relying on an isolated mock status.

## 19. Official References

- [Spring Security 6.5.11 — Servlet Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html): `FilterChain`, `FilterChainProxy`, filter ordering, `ExceptionTranslationFilter`, adding custom filters, and double-registration notes.
- [Spring Security 6.5.11 — ExceptionTranslationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html): handling `AuthenticationException`/`AccessDeniedException`, entry points, denied handlers, and request cache.
- [Spring Security 6.5.11 — AbstractAuthenticationProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html): login attempts, success/failure handlers, and `null` outcomes.
- [Spring Security 6.5.11 — AuthenticationEntryPoint API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/AuthenticationEntryPoint.html): starting/challenging authentication per scheme.
- [Spring Security 6.5.11 — AccessDeniedHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/access/AccessDeniedHandler.html): responding when permissions are insufficient.
- [Spring Security 6.5.11 — AuthenticationFailureHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html): responding to failed login attempts.
- [Spring Security 6.5 — Authorization Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationFilter` and HTTP authorization rules.
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): `SecurityContextHolder`, repositories, filter lifecycles, and explicit save.
- [Spring Framework 6.2 — MockHttpServletResponse API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/mock/web/MockHttpServletResponse.html): status/commit/buffer behavior in Servlet mocks.
- [Jakarta Servlet 6.0 — Filter / FilterChain / HttpServletResponse](https://jakarta.ee/specifications/servlet/6.0/apidocs/): `doFilter`, `sendError`, `sendRedirect`, and commit contracts.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): semantics of HTTP statuses and authentication challenges.

**Conclusion:** Inside a Servlet filter chain, **`chain.doFilter` lets downstream run**, **writing a response and returning lets the filter conclude the request**, and **throwing an exception hands off to whatever handler genuinely wraps the throw site**. In Spring Security, `AuthenticationEntryPoint` handles requests needing authentication initiation, `AuthenticationFailureHandler` handles failed login attempts, and `AccessDeniedHandler` handles insufficient permissions for properly authenticated callers. `ExceptionTranslationFilter` connects downstream security exceptions to those handlers, yet **is not a global catch** and cannot rescue an already-committed response. Choosing the right branch, filter position, and HTTP status—and asserting **chain invocation counts**—yields secure, predictable behavior.