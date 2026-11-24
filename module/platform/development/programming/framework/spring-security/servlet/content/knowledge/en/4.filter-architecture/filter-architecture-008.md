# ExceptionTranslationFilter and the Boundaries of Translated Exceptions

In **Spring Security for Servlet**, `ExceptionTranslationFilter` is the bridge between errors related to **authentication/authorization** and how the application responds over HTTP when those errors occur. It does not authenticate users, does not decide access permissions itself, and is not a handler for every application exception. Its primary responsibility is observing exceptions thrown **by components positioned after it in the filter chain**, and then:

- For `AuthenticationException`: initiating the authentication flow through `AuthenticationEntryPoint`.
- For `AccessDeniedException`: inspecting the caller's authentication state to either **initiate authentication** or **deny access** via `AccessDeniedHandler`.
- For exceptions outside those two families: letting the error continue propagating to another appropriate handling mechanism.

This lesson focuses on the boundaries of translation: **exception types, origin position, exception propagation, response state, and security chain configuration**. Correctly distinguishing these boundaries helps accurately diagnose `401`, `403`, redirects to login pages, and `500` application errors.

## 1. Position of ExceptionTranslationFilter in Servlet architecture

A typical HTTP request passes through the Servlet container, `DelegatingFilterProxy`, `FilterChainProxy`, and **one** selected `SecurityFilterChain`. Within that chain, `ExceptionTranslationFilter` is positioned so it wraps downstream authorization steps, typically including `AuthorizationFilter`.

~~~text
Servlet container
  |
  v
DelegatingFilterProxy ("springSecurityFilterChain")
  |
  v
FilterChainProxy
  |-- selects first SecurityFilterChain matching request
  |
  v
Filters BEFORE ExceptionTranslationFilter
  |    (e.g., certain authentication filters and CSRF)
  v
ExceptionTranslationFilter
  |    try {
  |        chain.doFilter(request, response)
  |    } catch (supported exceptions) {
  |        translate into authentication/denial response
  |    }
  v
Downstream filters, especially AuthorizationFilter
  |
  v
DispatcherServlet -> Controller -> Service
~~~

In this diagram, `ExceptionTranslationFilter`'s `chain.doFilter(...)` invokes the next segment of the chain; hence, the filter **only catches exceptions that actually propagate back through that call**. You cannot assume that every `AuthenticationException` or `AccessDeniedException` occurring anywhere in the request is handled by this filter.

For example, if an authentication filter positioned **before** `ExceptionTranslationFilter` throws an exception itself or handles the error with its own failure handler, that exception may never pass through `ExceptionTranslationFilter`. If `DispatcherServlet` already handled an exception via `@ExceptionHandler` or `HandlerExceptionResolver` and wrote a response, the exception may likewise not propagate back to the filter.

**Two separate decision layers:** `FilterChainProxy` decides **which SecurityFilterChain runs**; `ExceptionTranslationFilter` decides **how to handle a security exception passing through it**. If a request is not routed into a chain containing this filter, it has no opportunity to handle exceptions for that request.

## 2. The two recognized exception families

### 2.1. AuthenticationException: need to initiate authentication

`org.springframework.security.core.AuthenticationException` is the superclass of authentication errors in Spring Security, such as `BadCredentialsException`, `InsufficientAuthenticationException`, or `AuthenticationCredentialsNotFoundException`. When an exception of this kind propagates from the downstream chain into `ExceptionTranslationFilter`, the filter takes the **start authentication** branch.

Crucial point: `ExceptionTranslationFilter` **does not verify usernames/passwords to resolve the error**. It hands off to an `AuthenticationEntryPoint`, for instance:

- HTTP Basic: returns an authentication challenge, typically HTTP `401` with `WWW-Authenticate`.
- Bearer token / OAuth2 Resource Server: can return `401` with the appropriate Bearer challenge.
- Form login: typically issues an HTTP `302` redirect to the login page.
- Custom entry point: can return JSON/status per the application's API contract.

The final response depends on configuration, not a rigid rule that "AuthenticationException always equals 401".

### 2.2. AccessDeniedException: insufficient permissions, yet Authentication type must be checked

`org.springframework.security.access.AccessDeniedException` indicates an operation rejected by the authorization mechanism. For example, a logged-in user without the `ADMIN` role accesses an endpoint requiring that role.

When catching `AccessDeniedException`, `ExceptionTranslationFilter` uses `AuthenticationTrustResolver` and `SecurityContextHolder` to inspect the authentication state:

1. If the caller is deemed **anonymous** or at a **remember-me** level deemed insufficiently assured, the filter can initiate re-authentication, typically via `AuthenticationEntryPoint`. It creates an `InsufficientAuthenticationException` as the reason for starting authentication in this branch.
2. If the caller is fully authenticated yet lacks required permissions, the filter invokes `AccessDeniedHandler`, typically returning `403 Forbidden`.

An `AccessDeniedException` does not automatically mean `403`; anonymous/remember-me conditions change the handling branch. Conversely, valid credentials do not mean the user has enough authorities, so `403` is normal behavior in many cases.

### 2.3. Practical decision table

| Exception reaching ExceptionTranslationFilter | Caller state | Handling branch | Typical response |
| --- | --- | --- | --- |
| `AuthenticationException` | Any | `AuthenticationEntryPoint` | 401 or 302, depending on login method |
| `AccessDeniedException` | Anonymous | Start authentication via entry point | 401 or 302 |
| `AccessDeniedException` | Remember-me per trust resolver | Re-initiate authentication | 401 or 302, depending on configuration |
| `AccessDeniedException` | Fully authenticated, missing permissions | `AccessDeniedHandler` | 403 |
| `IllegalArgumentException`, `NullPointerException`, business errors outside the two families | Any | Not translated by this filter | Continues to other error handling mechanisms; may be 500 |
| Any security error fully handled before reaching the filter | Any | No handling branch in the filter | Depends on the upstream handling component |

"Typical" in the final column means **not guaranteed for every application**. Status, headers, body, redirects, sessions, or error pages are decided by the entry point/handler and other filters/frameworks.

## 3. Exception-catching mechanism: looking beyond the outermost exception

Security exceptions may be wrapped inside Servlet exceptions or other exceptions as they propagate across layers. `ExceptionTranslationFilter` uses `ThrowableAnalyzer` to locate a matching security error within the cause chain, rather than naively inspecting only the outermost layer.

You can picture it as:

~~~text
ServletException
  └── caused by AuthenticationException
          -> ExceptionTranslationFilter recognizes authentication error
          -> triggers AuthenticationEntryPoint

ServletException
  └── caused by AccessDeniedException
          -> handles according to authentication state

ServletException
  └── caused by SQLException / IllegalStateException
          -> no matching security exception
          -> exception continues propagating
~~~

This is an illustrative model. When a cause chain has multiple exceptions or a customized `ThrowableAnalyzer`, error lookup depends on the implementation/version in use. The point to understand is that Spring Security only recognizes **supported security exception families**, and does not arbitrarily convert every `RuntimeException` into an authentication response.

In standard Spring Security 6.x processing, the filter catches errors arising from calling the downstream filter chain, analyzes the cause, selects `AuthenticationException` or `AccessDeniedException` when possible, and handles it. If no matching type is found, the error is rethrown. Certain severe errors, async dispatch cases, or an already committed response may lie beyond the ability to handle by generating a new response.

## 4. What does the AuthenticationEntryPoint branch do?

When authentication must be initiated, `ExceptionTranslationFilter` performs the following logical sequence:

1. Clears/detaches the current security context from request processing so stale authentication is not mistakenly used when starting authentication.
2. Asks `RequestCache` to save the original request if a request-saving mechanism is configured (commonly form login wanting to return to the original URL).
3. Calls `AuthenticationEntryPoint.commence(request, response, authenticationException)`.
4. The entry point decides the response: redirect, status code, challenge header, or response body.

Diagram:

~~~text
AuthenticationException
        |
        v
ExceptionTranslationFilter
        |
        +--> resets SecurityContext for starting login
        |
        +--> RequestCache.saveRequest(...) (as configured)
        |
        +--> AuthenticationEntryPoint.commence(...)
                      |
                      +--> HTTP Basic: challenge / 401
                      +--> Form login: 302 /login
                      +--> Custom REST entry point: JSON 401
~~~

**RequestCache does not always mean writing to a session.** With form login, `HttpSessionRequestCache` is normally suitable to remember the URL and return after login. With stateless REST APIs, applications typically use `NullRequestCache` or a no-session-creation policy to avoid accidentally saving requests. Choosing the request cache and session policy must stay consistent with API design.

Do not try calling `AuthenticationEntryPoint` manually from controllers for ordinary business errors. This component has a specific purpose: initiating/redirecting users into the authentication flow.

## 5. What does the AccessDeniedHandler branch do?

If the caller is **fully authenticated** and an `AccessDeniedException` reaches `ExceptionTranslationFilter`, the filter delegates responsibility to `AccessDeniedHandler`.

`AccessDeniedHandlerImpl` typically sends HTTP `403`; it also supports forwarding to a configured error page via `errorPage`. A custom `AccessDeniedHandler` can write JSON or include allowable error details, provided it does not leak sensitive authorization/identity internals.

Application example:

- User `alice` is logged in and has `ROLE_USER`.
- Endpoint `GET /admin/reports` requires `ROLE_ADMIN`.
- `AuthorizationFilter` throws `AccessDeniedException`.
- The exception propagates back through `ExceptionTranslationFilter`.
- Because `alice` is neither anonymous nor remember-me according to `AuthenticationTrustResolver`, `AccessDeniedHandler` handles it; the default is typically `403`.

**Do not confuse permissions with authentication:** "Logged in" answers who the user is; "permitted to access" answers whether that user has sufficient rights for the specific resource.

## 6. Exceptions ExceptionTranslationFilter DOES NOT resolve

Knowing the boundaries is core to the mechanism:

### 6.1. Does not turn every Java exception into 401/403

Errors like `NullPointerException`, `IllegalStateException`, broken database queries, service timeouts, programming bugs, or ordinary `ResponseStatusException`s do not become security exceptions merely because the request passed through Spring Security. They belong to application error-handling mechanisms such as `@ControllerAdvice`, `HandlerExceptionResolver`, `BasicErrorController`, or the servlet container.

An unhandled error may eventually lead to `500 Internal Server Error`, though the actual status depends on exception resolvers and application error handling.

### 6.2. Does not catch errors raised in filters before it

Remember the call-stack structure:

~~~java
// Conceptual model of filter A before ExceptionTranslationFilter:
filterA.doFilter(request, response, chain);  // may throw exception
// ExceptionTranslationFilter only runs if the request reaches it.

// Conceptual model inside ExceptionTranslationFilter:
try {
    chain.doFilter(request, response); // DOWNSTREAM filters
} catch (Exception exception) {
    // Only inspects errors propagating back through this point.
}
~~~

This is **pseudocode**, not code to copy into a real program; Spring Security's actual catch types/branches are more intricate. If `BasicAuthenticationFilter` or another upstream authentication filter handles `AuthenticationException` with its own failure handler, `ExceptionTranslationFilter` does not re-handle that error.

Therefore, when an incorrect password returns `401`, do not claim `ExceptionTranslationFilter` produced the `401`. Another authentication filter/entry point may have done so earlier.

### 6.3. Does not replace Spring MVC exception handling

Exceptions from controllers/services can be handled by:

- `@ExceptionHandler` inside a controller.
- `@ControllerAdvice` shared across MVC.
- `HandlerExceptionResolver`, framework status or response handlers.
- Error-handling components after Servlet dispatch.

If MVC already consumed the exception and wrote a response, the outer filter no longer sees an exception to translate. If an `AccessDeniedException` genuinely propagates through the downstream chain unhandled, the filter **can** catch it. Thus it is also inaccurate to say `ExceptionTranslationFilter` "only handles errors from AuthorizationFilter"; the error source can be any suitable downstream component, as long as the exception propagates through it.

An overly broad `@ControllerAdvice` catching `Exception.class` can accidentally intercept security exceptions and return JSON `500`/`200` before `ExceptionTranslationFilter` sees them. Consider exception resolver ordering and security policies when catching broad exceptions.

### 6.4. Does not automatically handle all CSRF errors

`CsrfFilter` normally runs **before** `ExceptionTranslationFilter`. When a CSRF token is missing or invalid, the CSRF filter can use its own `AccessDeniedHandler` to return `403` without the exception passing through `ExceptionTranslationFilter`. `MissingCsrfTokenException` and `InvalidCsrfTokenException` belong to denied-access errors, yet their origin point and `CsrfFilter`'s handling decide which filter sends the response.

Hence, seeing `403` is not enough to conclude a role is missing. On HTTP `POST`/`PUT`/`DELETE`, check CSRF before concluding authorization rules are wrong.

### 6.5. Cannot rewrite an already committed response

Once status/headers/body have been sent to the client (`response.isCommitted()`), it is no longer guaranteed that you can forward to login, send a challenge, change the status, or write another error JSON. `ExceptionTranslationFilter` contains logic recognizing committed responses and may rethrow handling errors rather than attempting to write an invalid response.

Common scenario: a filter or controller wrote part of the response and only then threw `AccessDeniedException`. The fix is checking permissions before streaming data whenever possible, avoiding partial responses followed by security exceptions.

### 6.6. Does not apply if no matching security chain exists

`FilterChainProxy` selects the **first SecurityFilterChain matching the request**. If all chains are restricted by `securityMatcher("/api/**")` and URL `/reports` does not match, the API chain's `ExceptionTranslationFilter` does not run for `/reports`. Nor can an `anyRequest().authenticated()` rule inside the API chain protect that URL.

Additionally, `web.ignoring()` excludes requests from security filtering, which can keep `ExceptionTranslationFilter` out of the flow. Contrast with `permitAll()`: permitting in authorization rules can still keep requests flowing through security filters.

### 6.7. Async/error dispatches have their own lifecycle

Servlet `ASYNC` or `ERROR` dispatches can traverse different filter sets, or happen after the original thread has exited. Filter registration scope, dispatcher type, how Spring Security applies security to async, and response committed state affect whether an exception passes through `ExceptionTranslationFilter`. Test in practice; never assume an exception thrown in a late async task is always handled by the filter wrapping the initial request.

## 7. Standalone Java 17 decision simulation

The code below **simulates the branching policy** for learning and does not implement real Spring Security classes. It classifies only three exception groups and three authentication states; networking, request cache, and Servlet filter chains are omitted. The code runs on Java 17+ and lets you verify the branches immediately.

~~~java
public class ExceptionTranslationDecisionDemo {
    enum Caller { ANONYMOUS, REMEMBER_ME, FULLY_AUTHENTICATED }

    static class AuthFailure extends RuntimeException {}
    static class Denied extends RuntimeException {}

    static String decide(Caller caller, RuntimeException error) {
        if (error instanceof AuthFailure) {
            return "START_AUTH";
        }
        if (error instanceof Denied) {
            if (caller == Caller.ANONYMOUS || caller == Caller.REMEMBER_ME) {
                return "START_AUTH";
            }
            return "ACCESS_DENIED";
        }
        return "PROPAGATE";
    }

    static void show(Caller caller, RuntimeException error) {
        System.out.println(caller + " + " + error.getClass().getSimpleName()
                + " -> " + decide(caller, error));
    }

    public static void main(String[] args) {
        show(Caller.ANONYMOUS, new AuthFailure());
        show(Caller.ANONYMOUS, new Denied());
        show(Caller.REMEMBER_ME, new Denied());
        show(Caller.FULLY_AUTHENTICATED, new Denied());
        show(Caller.FULLY_AUTHENTICATED, new IllegalStateException());
    }
}
~~~

Save the file with exact name `ExceptionTranslationDecisionDemo.java`, then run:

~~~bash
javac ExceptionTranslationDecisionDemo.java
java ExceptionTranslationDecisionDemo
~~~

Exact stdout:

~~~text
ANONYMOUS + AuthFailure -> START_AUTH
ANONYMOUS + Denied -> START_AUTH
REMEMBER_ME + Denied -> START_AUTH
FULLY_AUTHENTICATED + Denied -> ACCESS_DENIED
FULLY_AUTHENTICATED + IllegalStateException -> PROPAGATE
~~~

Meaning:

- `START_AUTH` corresponds to invoking the entry point, **not necessarily HTTP 401**.
- `ACCESS_DENIED` corresponds to invoking the access denied handler, **usually** returning 403.
- `PROPAGATE` means the filter does not translate that exception into an authentication/authorization flow.
- The model assumes the exception actually reaches the filter and the response is not yet committed. The program does not simulate nested cause analysis, context, request cache, or ordering.

## 8. Practical configuration with Spring Security 6.x Servlet

A minimal configuration for a Spring Boot 3.x, Java 17+, Spring Security 6.x application with `spring-boot-starter-web` + `spring-boot-starter-security` can look like:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class AccessRulesConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This configures a single chain covering all requests and using HTTP Basic. When an unauthenticated user accesses `/admin/report`, authorization can throw `AccessDeniedException`; `ExceptionTranslationFilter` detects the anonymous user and invokes `BasicAuthenticationEntryPoint`, typically returning `401` with a challenge. When an authenticated user lacking `ROLE_ADMIN` accesses that endpoint, the denied-access branch typically returns `403`.

Two paths leading to the same 401 status must be distinguished:

1. **Missing or insufficient authentication at authorization:** downstream `AuthorizationFilter` throws an error, and `ExceptionTranslationFilter` can invoke the entry point.
2. **Sending wrong HTTP Basic credentials:** `BasicAuthenticationFilter` has its own authentication failure handling and can invoke the entry point without going through `ExceptionTranslationFilter`.

Seeing HTTP 401 alone cannot distinguish these two mechanisms. To analyze, check which filter actually detected the error.

A sample controller in the same project:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SampleController {
    @GetMapping("/public")
    public String publicEndpoint() {
        return "public";
    }

    @GetMapping("/admin/report")
    public String adminReport() {
        return "report";
    }
}
~~~

Role `ADMIN` is interpreted by Spring Security as the default authority `ROLE_ADMIN` when using `hasRole("ADMIN")`. If the system stores authorities without that prefix convention, align the authority and rule configurations.

### Customizing AuthenticationEntryPoint and AccessDeniedHandler

In JSON-based API applications, error responses can be customized via the `exceptionHandling` DSL:

~~~java
http.exceptionHandling(ex -> ex
    .authenticationEntryPoint((request, response, exception) -> {
        response.setStatus(401);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"error\":\"authentication_required\"}");
    })
    .accessDeniedHandler((request, response, exception) -> {
        response.setStatus(403);
        response.setContentType("application/json;charset=UTF-8");
        response.getWriter().write("{\"error\":\"access_denied\"}");
    })
);
~~~

This is an **addition inside the method configuring `HttpSecurity`**, placed before `http.build()`, not a standalone Java class. The exception handling layer only controls **how responses are formatted**; it does not replace `AuthenticationProvider`, `AuthorizationManager`, or matcher policies.

**Be careful with HTTP Basic and Bearer:** If you override the entry point to return only JSON 401 as above, the response may lose the `WWW-Authenticate` header clients need to recognize the authentication scheme. For APIs conforming to HTTP Basic or OAuth2 Bearer, preserve the appropriate challenge header or use the protocol's entry point instead of blindly copying the JSON snippet.

For stateless APIs, you may also consider configuring request cache and session:

~~~java
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.savedrequest.NullRequestCache;

// Inside HttpSecurity configuration, before build():
http.sessionManagement(session -> session
        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
    .requestCache(cache -> cache.requestCache(new NullRequestCache()));
~~~

The snippet only illustrates opting out of request saving for APIs; when an application needs form login, sessions, or "return to previous page", use appropriate configuration instead of disabling request cache globally.

## 9. Testing 401 and 403 branches with MockMvc

Using the configuration and controller from section 8, Spring Boot integration tests can verify anonymous, insufficient-permission, and authorized branches. Include `spring-security-test` alongside `spring-boot-starter-test` and enable Spring Security filters in MockMvc.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class SecurityExceptionFlowTest {
    @Autowired
    MockMvc mockMvc;

    @Test
    void anonymousIsAskedToAuthenticate() throws Exception {
        mockMvc.perform(get("/admin/report"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedWithoutRoleIsForbidden() throws Exception {
        mockMvc.perform(get("/admin/report")
                        .with(user("reader").roles("USER")))
                .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedWithRoleIsAllowed() throws Exception {
        mockMvc.perform(get("/admin/report")
                        .with(user("manager").roles("ADMIN")))
                .andExpect(status().isOk());
    }
}
~~~

Assertions are expected to pass when using **the exact HTTP Basic configuration from section 8**, with no custom entry point/handler altering statuses, GET requests, existing controller, and Spring Security filters active in MockMvc. Mock users supplied by `spring-security-test` test authorization without needing real passwords.

To distinguish upstream vs. downstream filter errors, add separate tests for bad-credential authentication and endpoints blocked by `CsrfFilter`. Do not write assertions like "every AccessDeniedException from any layer always returns 403"; that ignores origin position, MVC handling, anonymous authentication, and committed responses.

### How to trace in logs

In development or test environments, you can temporarily enable:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.web.access.ExceptionTranslationFilter=TRACE
logging.level.org.springframework.security.web.access.intercept=TRACE
~~~

Logs help locate the selected chain and path through filters. Exact phrasing and log levels can vary by version, so **use HTTP assertions and actual configuration as primary evidence**, rather than testing against log messages. Avoid logging credentials, tokens, or session cookies.

When encountering unexpected results, check step by step:

1. Did the request enter the right `SecurityFilterChain`? Did a `securityMatcher` exclude the request from the chain?
2. Is the root exception `AuthenticationException`, `AccessDeniedException`, or another type?
3. Was the exception thrown in a filter **before or after** `ExceptionTranslationFilter`? Did another component handle it first?
4. Is the authentication anonymous, remember-me, or fully authenticated? What are the current authorities?
5. Do the applied `AuthenticationEntryPoint` / `AccessDeniedHandler` match the request type?
6. Is the response already committed, and is the request in an async/error dispatch?
7. Did `CsrfFilter`, an MVC exception resolver, or a custom filter proactively write a response first?

## 10. Easily confused scenarios and how to handle them

| Symptom | Explanation to verify | Diagnostic step |
| --- | --- | --- |
| Anonymous user calls protected endpoint and gets 302 instead of 401 | Form login entry point may redirect | Check `formLogin()`, entry point, and response `Location` |
| Logged-in user gets 403 | Authenticated but missing role/authority, or blocked by CSRF | Inspect `AccessDeniedException`, security context, CSRF, and handler |
| Wrong password returns 401, no ETF log seen | An authentication filter before ETF may have handled it directly | Check `BasicAuthenticationFilter`/failure handler |
| Controller throws IllegalStateException and returns 500 | Not one of the two security exception families | Inspect stack trace, MVC exception resolver, and error handling |
| Controller throws AccessDeniedException but @ControllerAdvice returns custom JSON | MVC may have caught the exception before it reached the filter | Check `@ExceptionHandler` and `HandlerExceptionResolver` |
| permitAll POST endpoint still gets 403 | CSRF is still enabled, and CsrfFilter can handle it separately | Check token, `CsrfFilter`, and CSRF applicability rules |
| Stateless API creates a session after challenge | Request cache or another component may be saving the request | Check `RequestCache`, session policy, and cookies |
| Filter does not receive errors from a certain route | Request may enter a different chain or no security chain | Check chain order and matchers |
| Caught AccessDeniedException yet response cannot change to 403 | Response is already committed | Inspect streaming, response write order, and error logs |
| 403 is returned but not by ETF's AccessDeniedHandler | Another filter may return 403 directly | Enable trace and identify which component wrote the response |

In particular, **401 differs from 403 in protocol meaning**: 401 requests an authentication process (usually with a matching challenge); 403 signifies the request is refused. Although both statuses commonly appear in ETF branches, they are not a one-to-one mapping from exception class to HTTP status code.

## 11. Self-check exercises

**Scenario A.** An unauthenticated guest calls `GET /admin/report`. `AuthorizationFilter` throws `AccessDeniedException`, the request goes through `ExceptionTranslationFilter`, and the application uses form login. Which branch is expected?

**Answer:** The filter treats anonymous access denied as needing authentication, so it invokes `AuthenticationEntryPoint`. With form login, the typical result is a redirect to the login page (302), not necessarily 403.

**Scenario B.** A user authenticated via HTTP Basic has `ROLE_USER` while the endpoint requires `ROLE_ADMIN`. The authorization exception propagates to the filter. What is the usual result?

**Answer:** `AccessDeniedHandler` handles it because the user is fully authenticated yet lacks permissions. With the default handler, status is usually 403. This is not a signal asking to re-enter a password in normal configuration.

**Scenario C.** A `BasicAuthenticationFilter` rejects a wrong password, returning 401 via its own entry point. Is `ExceptionTranslationFilter` required to handle it in order to return 401?

**Answer:** No. An authentication filter can handle errors itself when positioned before ETF. A 401 status does not prove ETF caught an exception.

**Scenario D.** A controller throws `NullPointerException` with no security exception in the cause chain. Does ETF convert it into `AccessDeniedException` or 403?

**Answer:** No. That error is outside ETF's translation scope. It continues to the corresponding application/servlet error-handling mechanism.

**Scenario E.** A controller throws `AccessDeniedException`, but a `@ControllerAdvice` catches it and returns HTTP 400. Does ETF overwrite it with 403?

**Answer:** No if the exception was fully handled by MVC and does not propagate out to the filter. If consistent security handling is desired, design exception resolvers to avoid swallowing security exceptions unintentionally.

**Scenario F.** `ExceptionTranslationFilter` catches a security exception, yet the controller already streamed lots of data over the network. Is it guaranteed to turn into 401/403?

**Answer:** No. If the response is already committed, changing status/headers may be impossible; design permission checks before sending data and handle errors in the appropriate flow.

## 12. Design and diagnostic checklist

- Identify the **selected chain** and the position of `ExceptionTranslationFilter` within that chain.
- Clearly distinguish **`AuthenticationException`**, **`AccessDeniedException`**, and ordinary application exceptions.
- For `AccessDeniedException`, evaluate **anonymous / remember-me / fully authenticated** before assuming 401 or 403.
- Distinguish **`AuthenticationEntryPoint`** from **`AccessDeniedHandler`**, and inspect the actual response configuration.
- Review `RequestCache`, sessions, and security context when using login redirects or stateless APIs.
- Determine whether the exception originated **before or after the filter**, and whether MVC/CSRF/authentication filters handled it separately.
- Check committed responses, async/error dispatches, and custom exception resolvers when error responses look unusual.
- Write tests for anonymous, authenticated without permission, authenticated with permission, authentication failures, and independent business errors.

**Conclusion:** `ExceptionTranslationFilter` translates a set of security exceptions **propagated to it** into flows that initiate authentication or deny access. Its handling boundaries are determined simultaneously by **exception type, position in the filter chain, authentication state, and response state**. Understanding those four factors prevents confusing 401/403/302 with application bugs, and builds easily verifiable Servlet security flows.