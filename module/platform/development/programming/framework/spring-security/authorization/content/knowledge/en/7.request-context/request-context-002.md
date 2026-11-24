# Error Endpoints and Avoiding Rejection Loops When Dispatching to /error

In a Spring Boot application using Spring Security, a `404` or `500` error sometimes surfaces as `401`/`403`, the browser is redirected to the login screen, or the logs record an extra `AccessDeniedException` on `/error`. Developers may think the initial exception caused an authorization error; in reality, **the first request encountered an error, and then the error-rendering pass was authorized again and rejected a second time**.

The core issue is that **`DispatcherType.ERROR` and `DispatcherType.REQUEST` are not identical**, even though both relate to a single HTTP call from the user. Spring Security uses `AuthorizationFilter` to check permissions per dispatch, while Spring Boot Servlet typically uses `/error` to display error details. If `/error` or an `ERROR` dispatch is blocked by `anyRequest().denyAll()`, `authenticated()`, or another role check, the user may see the wrong outcome and the team can fall into a misdiagnosis loop or a chain of error redirects.

Lesson goals: distinguish the **root error** from an **error while rendering the error page**; know when to allow `ERROR` dispatches, configure `/error` so it does not become a backdoor, handle multiple `SecurityFilterChain`s, avoid custom error handlers triggering errors recursively, and test status codes and dispatch flows with concrete evidence. Examples use **Spring Boot 3 / Spring Security 6 on the Servlet stack** (Java 17+) and do not apply verbatim to reactive WebFlux.

## 1. What Is Spring Boot's `/error`?

In a **Spring MVC/Servlet** application with error auto-configuration, Spring Boot provides a default error endpoint at **`/error`** (typically via `BasicErrorController`) and registers the error-handling path with the Servlet container. When a request throws an unhandled exception or the container needs to display a status error page, the container can perform an **ERROR dispatch** to this endpoint.

Example:

~~~text
GET /public/boom           DispatcherType.REQUEST
  |
  +-- Spring Security lets /public/** rule pass
  +-- Controller throws IllegalStateException
  |
  +-- Servlet container / Spring Boot error handling
       |
       v
       /error              DispatcherType.ERROR
          |
          +-- Spring Security may re-check authorization
          +-- BasicErrorController builds appropriate error response
~~~

Several points must be understood accurately:

- `/error` is an **error-handling target path**, not automatic proof that a client actively called `GET /error`.
- **`DispatcherType.ERROR`** represents the Servlet container's internal error-handling dispatch pass. A request normally starts with **`DispatcherType.REQUEST`**.
- An ERROR request can carry error attributes such as `jakarta.servlet.error.status_code`, `jakarta.servlet.error.request_uri`, `jakarta.servlet.error.exception`, and `jakarta.servlet.error.message`; the corresponding constants reside in `jakarta.servlet.RequestDispatcher`.
- The output of `/error` can be JSON for APIs or HTML for browsers, depending on content negotiation and configuration, **not always an HTML page**.
- The default path can be changed via `server.error.path`. A custom `ErrorController` or `@ControllerAdvice` can change the handling path; not every exception must pass through the same `/error`.
- In **Spring Boot 3**, the Servlet API belongs to the **`jakarta.servlet`** namespace, not `javax.servlet` from many older applications.

Distinguish **Spring Security's `AccessDeniedHandler`** from **Spring Boot's `BasicErrorController`**: one handles access denial, while the other is how the application/container renders errors. The two mechanisms can run in sequence, but that does not mean every 403 response is routed to `/error`.

## 2. Why Can a Request Be Authorized Multiple Times?

Under the `authorizeHttpRequests` mechanism, **`AuthorizationFilter`** can be invoked for dispatches such as `REQUEST`, `ERROR`, `FORWARD` (and other configured dispatch types). Spring Security checks the current request against the `RequestMatcher`/authority rules for that specific dispatch pass. If the policy only considers the original URL and forgets the error-handling path, a request can undergo two different decisions.

Initial policy example:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .requestMatchers("/api/admin/**").hasRole("ADMIN")
    .anyRequest().authenticated()
);
~~~

Suppose `GET /public/boom` is a public endpoint, yet the controller throws an unhandled exception:

~~~text
1. REQUEST /public/boom
   -> /public/** permitAll -> ALLOW, controller runs
   -> controller throws exception

2. ERROR /error
   -> does not match /public/**
   -> does not match /api/admin/**
   -> anyRequest().authenticated()
   -> may DENY if the context now lacks a valid Authentication

3. Client receives result from the second error instead of the original exception's error page;
   log may show an extra AccessDeniedException/entry point invocation.
~~~

With `anyRequest().denyAll()`, the `ERROR /error` pass is blocked **even with an Authentication** if there is no special rule. With `authenticated()`, the outcome depends on the security context state on the new dispatch pass; you should not assume it is always preserved appropriately across every setup, custom filter, or token mechanism.

**Important:** "rejected twice" is not necessarily an **infinite loop**. The Servlet container, an already committed response, how `sendError`/forward works, error page mappings, and exception handling can limit or alter the number of dispatches. Actual symptoms may be 401/403 masking 404/500, redirecting to login, long repeated logs, or a redirect loop caused by a custom error flow. Measure **`DispatcherType`** and path at each step rather than claiming infinite recursion based solely on many log lines.

## 3. Spring Security's Recommended Rule: Allow `ERROR` Dispatches

In a Spring Boot 3 / Spring Security 6 application with a single `SecurityFilterChain`, the common way to let **the container render errors** without opening up all paths is usually placing a dispatcher rule before general rules:

~~~java
import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ErrorDispatchSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is **Spring configuration code**; it needs `spring-boot-starter-security`, an authentication mechanism/user store, and corresponding MVC endpoints for practical use. It is not a standalone Java program runnable with `javac` using only the JDK.

**Meaning of the first line in the DSL:**

- `dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()` checks the **dispatch type**, not the string `"/error"`. It lets the `ERROR` pass proceed at the **request authorization** layer.
- A normal HTTP client sending `GET /error` has `DispatcherType.REQUEST` and **does not turn into an ERROR dispatch** merely because the URL contains the word `error`. Direct requests still must follow the remaining rules.
- The `/api/admin/**` rule still requires `ROLE_ADMIN` for the **initial REQUEST**. Allowing ERROR dispatches **does not let an unauthorized user access an admin controller** by changing the path.
- `anyRequest().authenticated()` continues protecting the remaining endpoints in the chain. If you want a strict allowlist policy, you can use `anyRequest().denyAll()` and declare allowed URLs; however, consider the 404 behavior for unregistered URLs.

**The `dispatcherTypeMatchers` line must be placed before** catch-all rules, especially `anyRequest()`. Matchers are evaluated in order: the first matching rule decides. Placing `anyRequest().authenticated()` or `anyRequest().denyAll()` before the ERROR rule prevents the ERROR rule from ever applying.

### Should `DispatcherType.FORWARD` Always Be Permitted Too?

Spring Security documentation also gives examples permitting both `FORWARD` and `ERROR`, because an MVC view or JSP may be rendered via forward and encounter a second authorization check.

~~~java
http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(DispatcherType.ERROR, DispatcherType.FORWARD)
        .permitAll()
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

This is a **conditional expansion option**, not a mandatory requirement for every system. If the application does not need FORWARD, **permitting only ERROR** keeps the exception scope narrower. Allowing all FORWARDs means internal forwards bypass HTTP-layer authorization checks by dispatch type; do not use it if policy relies on checking permissions at the forward target or if there are multiple sensitive Servlets. In environments using templates/views, you can permit only a view/error path with an appropriate matcher instead of opening all FORWARDs.

Note that `@ControllerAdvice` can return an error response directly **without** performing a container ERROR dispatch; in that case the ERROR rule is not used. You must understand which error-handling mechanism a request actually passes through.

## 4. How Does `dispatcherTypeMatchers(ERROR)` Differ from `requestMatchers("/error")`?

There are two common ways to ensure error pages are not blocked:

~~~java
// Approach A: allow dispatches marked ERROR by the container.
.dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
~~~

and

~~~java
// Approach B: allow every request matching URL /error,
// including direct REQUESTs from clients when the matcher matches.
.requestMatchers("/error").permitAll()
~~~

They are **not equivalent**:

| Scenario | Approach A: dispatcher ERROR | Approach B: URL `/error` |
| --- | --- | --- |
| `ERROR /error` dispatched by container | ALLOW at authorization | ALLOW if path matches. |
| `REQUEST /error` sent directly by browser | Must follow remaining rules | Allowed by the `/error` rule. |
| ERROR dispatch to a custom error path like `/system/error-page` | Can ALLOW by dispatcher type | Does not match `/error` unless the rule is changed. |
| FORWARD to `/error` | Not exempted by an ERROR-only rule | Can ALLOW because URL matches, even though dispatcher is FORWARD. |
| Error target changed via `server.error.path` | Independent of the `/error` name | Requires updating the matcher to the new path. |
| Path restriction scope | Allows all ERROR dispatches in the chain | Allows path `/error` regardless of dispatcher if matched. |

**Default recommendation:** use **the `DispatcherType.ERROR` rule** to solve the redispatch denial problem accurately without exposing direct `/error` access via normal REQUESTs. However, this is **not an absolute rule**: in systems with multiple servlets, special error paths, or internal security constraints on error dispatches, examine the goal before broadening access.

Permitting the **authorization layer** does not mean skipping control over **the data the error page displays**. Error pages must be designed not to leak stack traces, tokens, sensitive request headers, or another user's information. API policies for normal endpoints still apply in full.

If you want to permit **only ERROR dispatches to `/error`** specifically, you can use a `RequestMatcher` combining dispatcher type and path in the DSL; in return, you must verify the exact matcher path, context/servlet path, and secondary error routes. Narrower is not always safer if the matcher misses the real error page and causes masked statuses again.

## 5. `/error` and 401/403/404/500 Errors: Different Origins

These HTTP outcomes appear close together yet must be distinguished:

| Situation | Initial deciding mechanism | Typical outcome |
| --- | --- | --- |
| Unauthenticated user calls an API requiring login | `AuthenticationEntryPoint` when authentication is needed. | With HTTP Basic/JWT typically **401**; form login may **302 redirect**. |
| Authenticated user lacks authority | `AccessDeniedHandler` handles denied permission. | Typically **403**. |
| Authorized user calls URL with no controller | Spring MVC / Servlet container finds no handler. | Typically **404** if the request passed security. |
| Controller throws unhandled exception | Container / Spring Boot error handling. | Typically **500** if no handler translates it to another status. |
| `ERROR /error` is denied by a security rule again | Authorization during the error dispatch pass. | Can mask original status with 401/403/redirect or secondary error. |
| `@ControllerAdvice` catches and returns response | MVC exception resolver. | Follows handler's `ResponseEntity` or `@ResponseStatus`; may bypass /error. |

Do not hastily treat a `403` response as proof that `@PreAuthorize` or `hasRole` on the original request worked properly. If logs show the controller threw an exception or a route did not exist followed by **`DispatcherType.ERROR` to `/error`**, the 403 may come from **the error page being blocked**, not from the original operation's permissions.

Conversely, when a request is rejected by `AuthorizationFilter` in a normal flow, `ExceptionTranslationFilter` can route `AccessDeniedException` to the entry point or access-denied handler. The handler may write a status, call `sendError`, forward to another page, or return JSON depending on configuration; **not every 401/403 runs through Boot `/error`**. Trace a specific request rather than guessing from status numbers.

### Why Is a 404 Error Sometimes Shown as 401?

Suppose an anonymous user calls a public path that has no controller:

~~~text
GET /public/missing                  REQUEST
  `/public/**` permitAll -> enters MVC
  MVC finds no mapping -> needs to render 404
  Servlet container dispatches to /error  ERROR
  `anyRequest().authenticated()` -> anonymous does not qualify
  AuthenticationEntryPoint -> 401/redirect response
~~~

After adding `dispatcherTypeMatchers(ERROR).permitAll()`, `ERROR /error` can reach the error controller and return **404 matching the original error**, provided no other filters, error controllers, or exception handlers interfere. **Do not replace every 404 response with 401/403**; it makes it hard for frontends, clients, and monitoring to identify the error source.

Also understand the reverse: with an `anyRequest().denyAll()` policy, a **REQUEST to an unruled URL** can get **403 at the security step before MVC ever checks whether a controller exists**. Allowing `ERROR` only fixes error rendering after an error has occurred; it does not turn URLs blocked by `denyAll` into 404s.

## 6. Security Boundaries to Maintain When Allowing ERROR

Allowing `DispatcherType.ERROR` is a **request authorization exception**, not a license to disable the entire security system. Constraints to uphold:

- **Do not use `web.ignoring("/error")` by reflex.** `ignoring` skips the Spring Security filter chain, including security headers and configured protective filters; `permitAll` only allows the request authorization step inside the chain.
- **Do not use `permitAll("/**")` to hide 403 errors.** Such a change can expose business APIs publicly.
- **Do not put sensitive business processing into the error controller.** The error handler should build an error response, not perform admin actions, transfer money, mutate state, or query another tenant's data.
- **Do not trust request-supplied error attributes.** Never directly output stack traces, cookies, tokens, queries containing PII, or unfiltered exception messages. Container error attributes should be used to return safe status codes/messages, not for business authorization.
- **Keep other filters active** as designed: `permitAll(ERROR)` does not automatically disable CSRF, authentication filters, JWT token validation, rate limits, or custom filters. For custom filters, decide whether they handle `ERROR` dispatches rather than requiring roles on the error endpoint.
- **Audit and observability:** distinguish root errors from redispatch errors to avoid double-counting or corrupting metrics. A single user request causing 500 can produce logs across multiple dispatches; correlating by request ID and dispatcher type is very helpful.
- **Do not assume the final status is guaranteed intact.** If the original response was already committed or a custom handler sent another body/status, permitting ERROR does not automatically restore what was already written.

In Spring Boot, you can control error detail exposure via `server.error.include-message`, `server.error.include-stacktrace`, `server.error.include-binding-errors`, and custom error attributes. In public deployments, prefer returning only safe information to clients while storing technical details in controlled server logs.

## 7. Multiple `SecurityFilterChain`s: The ERROR Rule Must Live in the Chain That Actually Receives /error

A deceptive scenario: an application splits an API chain and a web chain:

~~~text
Chain @Order(1): securityMatcher("/api/**")
     -> JWT authentication / API authorization
Chain @Order(2): matches all remaining URLs
     -> form login or fallback authorization
~~~

A client calls `GET /api/orders/42`; the controller throws an error. If the Servlet container performs an ERROR dispatch to **`/error`**, the path of the new pass may **no longer belong to `/api/**`**. When `FilterChainProxy` selects a chain for `/error`, the **fallback chain** is where rules apply; a `dispatcherTypeMatchers(ERROR).permitAll()` placed **only in the API chain** will not necessarily take effect for /error.

Example of a two-chain configuration oriented toward safety (illustrated for Spring Security 6 + Servlet):

~~~java
import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiChainErrorSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
                .requestMatchers(HttpMethod.GET, "/api/public/**").permitAll()
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            );
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain fallback(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .dispatcherTypeMatchers(DispatcherType.ERROR).permitAll()
            .requestMatchers("/public/**").permitAll()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
~~~

**Example scope:** these two chain beans illustrate **selection and authorization**, and do not yet declare a JWT provider, form login, or appropriate identity source; do not use verbatim as a production application. The API chain has `securityMatcher("/api/**")`, while the fallback chain has no `securityMatcher` so it covers other requests, including ERROR to `/error`.

- `REQUEST /api/admin/users` → API chain, ADMIN role remains mandatory.
- `ERROR /error` after an API error → typically enters fallback chain → `DispatcherType.ERROR` rule allows rendering the error.
- `REQUEST /error` called externally → fallback chain → `anyRequest().denyAll()`, not exposed publicly by the ERROR exception.
- `REQUEST /public/status` → fallback chain → public.
- `REQUEST /unknown` → fallback chain → DENY per policy, even though MVC may have no handler.

Specifically, **chain order (`@Order`) and rule order inside a chain are two different layers**. `dispatcherTypeMatchers(ERROR)` only applies if the chain containing it is actually selected. When debugging, identify which chain and filters ran on the ERROR pass rather than looking only at the initial API bean.

If the app uses `server.error.path=/problem`, a custom `ErrorController`, a context path, or a different servlet prefix, test against the actual error dispatch path. Do not blindly hard-code `/error` for every deployment.

### Do Not Use an Overly Narrow securityMatcher and Omit the Fallback Entirely

If you register only an API chain for `/api/**` with no fallback, `/error` may **match no chain**. Errors might then render, yet the request skips the Spring Security filter chain, losing security headers or custom filtering mechanisms. **That is not the recommended fix**. Design a fallback chain covering the application and permit ERROR dispatches as needed.

## 8. FORWARD to a Custom Error Page Differs from an ERROR Dispatch

In an MVC application, two handling paths can be conflated:

~~~text
A. Container error:
   REQUEST /private/boom -> controller/servlet error
   ERROR   /error         -> Boot error controller

B. AccessDeniedHandler forwards to access-denied page:
   REQUEST /private/data  -> AccessDeniedException
   FORWARD /access-denied  -> view/controller configured by application
~~~

With `AccessDeniedHandlerImpl` configured to use an error page, the mechanism can be a **forward**, not an ERROR dispatch to Boot `/error`. If you permit only `ERROR`, case B can still hit another denial on `FORWARD`.

Choose a strategy based on how the error flow is designed:

~~~java
// Option 1: allow both dispatcher types,
// only after verifying FORWARD cannot be used to bypass policy.
.dispatcherTypeMatchers(DispatcherType.ERROR, DispatcherType.FORWARD)
    .permitAll()
~~~

or use a matcher specific enough for the target page and dispatch type:

~~~java
import org.springframework.security.web.util.matcher.DispatcherTypeRequestMatcher;
import jakarta.servlet.DispatcherType;

// Inside authorizeHttpRequests:
.requestMatchers(
    new DispatcherTypeRequestMatcher(DispatcherType.FORWARD, "/access-denied")
).permitAll()
~~~

The second snippet illustrates a **matcher for dispatcher type + HTTP path**. Verify constructor signatures, servlet-path handling, and your specific version when integrating into a project; do not copy across Spring generations without running tests. You can also use `requestMatchers("/access-denied").permitAll()` if you want the error page public via `REQUEST` as well.

For most JSON API applications, forwarding to a view is unnecessary: an `AccessDeniedHandler` can return a safe status and JSON directly, avoiding a second path that must be authorized. For server-side rendered MVC apps, ensure proper paths to templates and static assets of the error page.

## 9. Avoiding Real Loops Caused by Custom Error Handlers

Another problem besides `AuthorizationFilter` blocking ERROR is a **custom error controller / error view triggering additional errors itself**. For example:

- `/error` throws an exception when trying to access an unavailable database.
- The error page depends on session/user profile while the request is anonymous or the authentication context is no longer appropriate.
- The error handler calls the original controller again or uses `return "forward:/error"`, creating another dispatch pass to itself.
- An exception handler re-throws an untranslated exception and the error mapping invokes that same handler again.
- The error page loads JS/CSS that requires login or points to the wrong context path, preventing the error screen from rendering properly.
- A custom security filter running on all requests (including ERROR) calls a service that itself throws an error; when the server dispatches to /error, the filter throws again.

Reduce risk by designing a **minimal and self-contained error page**:

1. **Return a safe response directly** (controlled status, code, message) without dispatching back to `/error` itself.
2. **Do not depend on business DB/cache/network** just to render an unrelated error. Use a generic fallback message when data is unavailable.
3. **Do not require login on the ERROR dispatcher** to display a generic error, unless there is a special reason and an independent fallback mechanism.
4. **Do not expose unfiltered exception messages/stack traces.** Log server-side with a correlation ID to find root causes.
5. **Use minimal static assets** or safe inline CSS if the error page must work in a degraded application state; avoid creating loop accesses through private assets.
6. **Stop early when the response is already committed** or when a custom handler can no longer alter the status per the protocol.
7. **Test the error handler when supporting dependencies are unavailable**, especially authentication services or databases.

A custom error handler's job is to **terminate the error chain**, not to treat itself as a place to "retry" business actions. If retry logic is needed, put it in a separate mechanism with bounded attempts and guaranteed idempotency, never by endlessly forwarding errors.

## 10. Differences Between `permitAll(ERROR)`, Skipping the Filter Chain, and Disabling Dispatcher Checks

Three kinds of changes are easily confused:

| Approach | What is changed | Risks / considerations |
| --- | --- | --- |
| `dispatcherTypeMatchers(ERROR).permitAll()` | Only drops the authorization requirement on ERROR passes in the selected chain. | Other Spring Security filters can still run; prefer this to fix rendering errors. |
| `web.ignoring().requestMatchers("/error")` | Skips the Spring Security filter chain for the ignored URL. | Loses headers and other Spring Security filters; can also apply to direct REQUESTs. |
| Changing filter dispatcher type registration to **not run the security filter chain** on ERROR | Bypasses the entire Spring Security chain on ERROR dispatches. | Broad impact affecting headers/security context/filters; do only with clear architectural analysis. |

**Do not turn off the entire security chain on ERROR to fix a missing authorization rule.** The minimal fix is usually placing the appropriate dispatcher rule in the right chain. However, `permitAll(ERROR)` **does not automatically exempt other filters**. For example, a custom JWT authentication filter might enforce a token on every dispatcher and return 401 before AuthorizationFilter; in that case, fix *that filter's* scope or how it handles ERROR rather than opening all endpoints.

Regarding security headers, do not assume every header is present in every chain. `permitAll` preserves the opportunity for configured header writers to run; `ignoring` removes them from the Spring Security flow. Headers from a reverse proxy/gateway may still exist even if Spring Security is bypassed; test on real responses.

## 11. Standalone Java 17 Illustration: An ERROR Dispatch Does Not Grant Admin Rights

The following example **does not use Spring libraries**. It simulates authorization decisions for `REQUEST` and `ERROR`. Policy:

- `/api/admin/**` is accessible only if authenticated and holding `ROLE_ADMIN`.
- `/public/status` is always public.
- Remaining paths require an authenticated caller.
- If the `permitErrorDispatch` exception is enabled, any `Dispatch.ERROR` is **allowed to proceed to the error renderer** in the model; **the initial REQUEST still enforces all normal rules**.

Save with the exact filename **`ErrorDispatchAuthorizationDemo.java`**:

~~~java
import java.util.Set;

public class ErrorDispatchAuthorizationDemo {
    enum Dispatch { REQUEST, ERROR, FORWARD }
    record Call(Dispatch dispatch, String path, boolean authenticated,
                Set<String> authorities) {}

    static boolean authorized(Call call, boolean permitErrorDispatch) {
        if (permitErrorDispatch && call.dispatch() == Dispatch.ERROR) {
            return true;
        }
        if (call.path().equals("/public/status")) {
            return true;
        }
        if (call.path().startsWith("/api/admin/")) {
            return call.authenticated()
                    && call.authorities().contains("ROLE_ADMIN");
        }
        return call.authenticated();
    }

    public static void main(String[] args) {
        Call anonymousAdmin = new Call(Dispatch.REQUEST, "/api/admin/users",
                false, Set.of());
        Call regularAdmin = new Call(Dispatch.REQUEST, "/api/admin/users",
                true, Set.of("ROLE_USER"));
        Call admin = new Call(Dispatch.REQUEST, "/api/admin/users",
                true, Set.of("ROLE_ADMIN"));
        Call errorPage = new Call(Dispatch.ERROR, "/error", false, Set.of());
        Call directErrorUrl = new Call(Dispatch.REQUEST, "/error", false, Set.of());
        Call publicPage = new Call(Dispatch.REQUEST, "/public/status",
                false, Set.of());

        System.out.println("Anonymous original admin: "
                + authorized(anonymousAdmin, true));
        System.out.println("User original admin: "
                + authorized(regularAdmin, true));
        System.out.println("Admin original admin: "
                + authorized(admin, true));
        System.out.println("ERROR /error before exception: "
                + authorized(errorPage, false));
        System.out.println("ERROR /error with exception: "
                + authorized(errorPage, true));
        System.out.println("REQUEST /error remains private: "
                + authorized(directErrorUrl, true));
        System.out.println("Public status: "
                + authorized(publicPage, true));
        System.out.println("Error exception cannot grant admin: "
                + authorized(regularAdmin, true));
    }
}
~~~

Compile and run with JDK 17 or higher:

~~~bash
javac --release 17 ErrorDispatchAuthorizationDemo.java
java ErrorDispatchAuthorizationDemo
~~~

Standard output:

~~~text
Anonymous original admin: false
User original admin: false
Admin original admin: true
ERROR /error before exception: false
ERROR /error with exception: true
REQUEST /error remains private: false
Public status: true
Error exception cannot grant admin: false
~~~

**How to read the output:** Regular users still lack admin permissions even when `permitErrorDispatch=true`; requests accessing `/api/admin/users` remain denied. On the ERROR pass with an explicit dispatcher type, the policy only lets it proceed to render the error without turning the original request's outcome into a success. Direct `GET /error` is a `REQUEST`, so it does not receive the ERROR exception.

`startsWith("/api/admin/")` in the program is an **illustrative model with known inputs**, and must not be copied as a production security `RequestMatcher`; Spring MVC/Servlet have their own path rules, URL encoding, and firewall. The program does not execute real Servlet error dispatches, does not simulate the body/HTTP status of `BasicErrorController`, and cannot replace Spring integration tests.

## 12. Testing Real Error Flows, Not Just Asserting `/error` Returns 200

A test that merely calls `GET /error` from MockMvc typically starts with the **`REQUEST`** dispatcher, so it **does not** test the scenario where the container dispatched **`ERROR`**. And when an app has no handler at another path, a test returning 401/403 does not necessarily prove the rule for the original endpoint is right; the response may be masked.

Split testing into three layers:

### A. Testing Matcher Logic by Dispatcher Type

In unit/integration tests with `spring-security-test`, construct a request with **`DispatcherType.ERROR`** explicitly set, rather than relying on the URL name:

~~~java
// Snippet inside a Spring MVC/Security test with MockMvc,
// MockMvcRequestBuilders.get and jakarta.servlet.DispatcherType.
mvc.perform(get("/error")
        .with(request -> {
            request.setDispatcherType(DispatcherType.ERROR);
            request.setAttribute(
                RequestDispatcher.ERROR_STATUS_CODE, 500);
            request.setAttribute(
                RequestDispatcher.ERROR_REQUEST_URI, "/public/boom");
            return request;
        }));
// Then assert dispatcher rule/response per actual configuration.
// plain get("/error") would be REQUEST, not ERROR.
~~~

This snippet requires Spring MVC test dependencies, `RequestDispatcher`, `MockMvc`, static imports, a security chain bean, and an appropriate error controller. **Do not assert specific HTTP outcomes from the snippet alone**: controllers, error attributes, and response configurations can vary. To verify that the original error is preserved, follow up with real-container tests.

### B. End-to-End Testing with an Embedded Container

Create a public test endpoint **that throws a controlled exception**:

~~~java
@RestController
class ErrorFixtureController {
    @GetMapping("/public/boom")
    String boom() {
        throw new IllegalStateException("Synthetic error for test");
    }
}
~~~

This is a **test-only fixture**, not an endpoint that should exist in production. With `@SpringBootTest(webEnvironment = RANDOM_PORT)` and a real HTTP client (such as `TestRestTemplate`), call `GET /public/boom`. In an environment using default Boot error handling and no custom exception resolver, the expected final status is usually **500**; not 401/403 arising from `/error` being blocked. Also test a **non-existent public path** and verify **404** if MVC receives that request.

Beyond HTTP status, you can use a test filter recording **`getDispatcherType()` and `getRequestURI()`** to prove a `REQUEST` pass occurred followed by `ERROR`. Do not make the test fixture log sensitive information. With a proxy, add integration tests at the real entry point if deployment transforms paths.

### C. Testing Protected Requests Still DENY

Even when error dispatches are permitted, the following cases must hold:

| Test case | Expectation |
| --- | --- |
| Anonymous `REQUEST /api/admin/users` | Admin controller must not run; HTTP Basic/JWT usually 401, form login may redirect. |
| Regular user `REQUEST /api/admin/users` | 403 or the designed insufficient-permission handling. |
| Valid admin `REQUEST /api/admin/users` | Passes authorization (controller may still raise business errors). |
| Anonymous `ERROR /error` | Passes **ERROR dispatcher rule** to render error. |
| Anonymous `REQUEST /error` | **Not automatically** permitted by an ERROR-only rule. |
| Anonymous `FORWARD /access-denied` | Follows separate FORWARD policy, not inferred from ERROR. |
| ERROR from API when target is no longer `/api/**` | Chain receiving the error target must allow ERROR if rendering is desired. |
| Public endpoint throws exception | Original status (usually 500) is displayed accurately without a second rejection. |
| Public path with no handler | 404 if the request reaches MVC and error mapping works. |
| Custom error handler throws exception itself | Safe fallback exists, no infinite redirect/forward loop. |

To determine **which test proves what**, separate initial authorization rules from error-rendering rules. A 500 status from a public endpoint does not show the admin endpoint is secure; a 403 from admin does not show `/error` is unmasked. Both test groups are needed.

## 13. Diagnosing Unexpected 401/403 on /error with Precise Logs

When encountering symptoms like "non-existent route returns 401" or "500 error response suddenly becomes 403", use a short procedure:

1. **Identify the error on the initial REQUEST:** which path, which method, expected HTTP status, and how far did the controller or filters run?
2. **Find the subsequent dispatch pass:** log `DispatcherType.REQUEST`, `DispatcherType.ERROR`, or `FORWARD`; is the current path `/error` or the path configured in `server.error.path`?
3. **Identify which chain receives that pass:** a single app-wide chain or API chain + fallback? Do `securityMatcher` and `@Order` route `/error` to a different chain?
4. **Identify which authorization matcher wins:** is `dispatcherTypeMatchers(ERROR).permitAll()` placed **before** `anyRequest()` in the appropriate chain?
5. **Identify which filter causes the denial:** `AuthorizationFilter`, CSRF, a custom authentication filter, or another exception handler? `permitAll` does not bypass all of them.
6. **Verify the error controller does not throw itself:** does it query a database, require a user profile, forward back to /error, or is the error page role-protected?
7. **Check final status and headers:** do not accidentally turn the original error into 200, 302, 401, 403, or HTML containing stack traces; match API or browser clients.
8. **Fix only the exact broken spot**, then re-test both the original request and the ERROR dispatch, avoiding changing `anyRequest().denyAll()` to `permitAll()` across the entire app.

You can enable controlled DEBUG logging for `org.springframework.security` and log the filter chain in test environments. Log **request ID/correlation ID**, dispatcher type, normalized URI, and selected rule/chain if observable in the framework. Do not log Authorization bearer tokens, cookies, session IDs, or sensitive stack traces to public responses or unprotected logging systems.

**Warning about `OncePerRequestFilter`:** Spring Security filters and custom filters do not necessarily behave identically across dispatchers. Some filters run only on REQUEST or skip ERROR internally; `AuthorizationFilter` has its own dispatch handling. Therefore, logs showing "filter X ran once while `AuthorizationFilter` ran twice" may reflect a valid pipeline. Do not write assumptions that the entire filter chain in ERROR must have the same side effects as REQUEST.

## 14. Pre-Production Checklist

- [ ] Know whether `/error` is default or a custom error path (`server.error.path`); verify Boot error controller or custom implementation.
- [ ] Distinguish **REQUEST**, **ERROR**, and **FORWARD** without inferring dispatcher type from URL.
- [ ] Have a `DispatcherType.ERROR` rule if container error dispatches need to render without requiring authentication, placed **before** other rules.
- [ ] With multiple chains, the chain actually matching the ERROR target handles the rule properly; the fallback chain covers non-API URLs.
- [ ] Admin endpoints and private APIs still enforce role/authority rules and data policies on the **initial REQUEST**.
- [ ] `permitAll(ERROR)` is not a substitute for disabling CSRF, fixing JWT authentication, or fixing custom filters; verify which filter actually blocks.
- [ ] Do not remove Spring Security from `/error` using `web.ignoring` when you only want to render errors.
- [ ] Custom error controller does not call `/error` again, does not depend on the database to render, and returns no sensitive data.
- [ ] If using a `FORWARD`-based access-denied page, test the FORWARD rule and target page separately.
- [ ] Embedded-container tests verify a public endpoint throwing 500, a missing public URL returning 404, and protected endpoints still denying.
- [ ] Verify status/body for both JSON APIs and browser HTML, including when no session/token exists.
- [ ] Logs include correlation ID, dispatcher type, and path, without leaking tokens or PII.

**Conclusion:** When Spring Security handles **multiple dispatch passes for one request**, the `/error` endpoint can be re-authorized and mask the original error. The usually appropriate fix is **permitting `DispatcherType.ERROR` in the right `SecurityFilterChain`**, keeping REQUEST/FORWARD policies intact as business needs dictate, and keeping error handlers minimal so they do not raise errors themselves. An exception for ERROR dispatches is a way to **allow error rendering**, **not a grant of permission** for users to bypass protected APIs.

### References

- [Spring Security — Authorize HttpServletRequests: All Dispatches Are Authorized / Matching by Dispatcher Type](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Servlet Architecture and Security Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html#servlet-exceptiontranslationfilter)
- [Spring Boot 3.5 — Servlet Web Applications, Error Handling](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html)
- [Spring Boot 3.5 — Common Application Properties: server.error.path](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
