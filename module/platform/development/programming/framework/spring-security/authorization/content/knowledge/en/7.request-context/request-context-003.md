# Internal Forwards and Re-Executed Requests

## 1. An Allowed URL Is Not the Entire Request Lifecycle

When learning Servlet-based Spring Security, we often picture an HTTP request passing through the filter chain, getting authorized once, and reaching the controller. In reality, an **HTTP request can go through multiple internal dispatch passes**: a controller forwards to a view via `forward`, the container dispatches to an error page, or the application starts asynchronous processing and re-dispatches the result. Each pass can have a **target path, `DispatcherType`, and processing entry point different from the first pass**.

Therefore, two questions must be answered independently:

1. **Is the first request allowed to enter the initial endpoint?**
2. **If the same request is forwarded/re-dispatched, is the new target executed under the right policy?**

Suppose a user accesses `GET /app/orders`. The HTTP rule lets logged-in users view the list page; the controller then returns a view name, and the view resolver forwards to `/WEB-INF/views/orders.jsp`. If authorization runs again on the `FORWARD` pass, a rule permitting only `/app/orders` can cause the JSP page to receive 403. Yet fixing it by opening **all forwards** could allow a forward to a sensitive handler to become a path outside policy if there is no business-layer protection.

That is the central problem: **distinguish internal dispatches used for rendering from paths executing actions that require permissions; protect both without confusing an "old request" with "already authorized to do everything".**

### Lifecycle Illustration

```text
Client
  |
  | GET /app/orders
  v
Servlet container: DispatcherType.REQUEST
  |
  v
Spring Security filter chain
  |  check permission for /app/orders
  v
Spring MVC controller
  |  return "orders"
  v
View resolver / RequestDispatcher.forward(...)
  |
  v
Servlet container: DispatcherType.FORWARD
  |  target path /WEB-INF/views/orders.jsp
  |  still within original logical request
  |  but is a different dispatch pass
  v
Filters matching the dispatcher type may run again
  |
  v
View renders and returns response
```

If the controller throws an exception or calls `sendError(...)`, the server may create an `ERROR` pass targeting an error page. If the request processes asynchronously and is re-dispatched, the subsequent pass may carry `ASYNC`. **Not every component runs on every pass**: it also depends on filter registration by dispatcher type, filter ordering, `OncePerRequestFilter` policies, and servlet/container configuration.

## 2. The Five Servlet DispatcherTypes

Jakarta Servlet defines five dispatch types. Servlet-based Spring Security must be understood on that foundation.

| `DispatcherType` | When does it occur? | Key notes |
| --- | --- | --- |
| `REQUEST` | Normal incoming request from client | Starts the HTTP processing chain |
| `FORWARD` | A servlet/controller transfers processing to another resource using `RequestDispatcher.forward(...)` | Target path and parameters may be adjusted; an initial request pass already occurred |
| `INCLUDE` | A resource embeds another resource's output using `RequestDispatcher.include(...)` | Target page is not replaced wholesale; response is restricted on status/headers |
| `ERROR` | Container routes request to error-handling mechanism/page | Can be an additional dispatch pass after an exception or error code |
| `ASYNC` | Request is re-dispatched via `AsyncContext.dispatch(...)` | Processing may resume on another thread; requires understanding security context |

Each `HttpServletRequest` can provide:

```java
DispatcherType type = request.getDispatcherType();
```

Where `DispatcherType` is `jakarta.servlet.DispatcherType`. A filter may be invoked by the container for one dispatch type and not another, depending on how it is registered. **`getDispatcherType()` itself does not decide access**; it is a fact used to select policy and understand the lifecycle.

### 2.1. `REQUEST` Is Not "All Passes"

The first pass is `REQUEST`. However, if a controller returns a view using forward, or the container renders an error page, part of the handling can be invoked again. Thus:

- Do not claim "filters are guaranteed to run only once across the whole HTTP request".
- Do not claim "whenever there is another pass, the user sent a new HTTP request".
- Do not assume authorization on the first pass automatically covers actions on every internal target.

### 2.2. Forward vs. Redirect

| Criterion | Internal Forward | Redirect |
| --- | --- | --- |
| Who controls it? | Servlet container/server | Server returns 3xx and `Location` so client sends next request |
| Number of client requests | Usually still one client request | Usually creates a subsequent HTTP request from client |
| `DispatcherType` at target | `FORWARD` | New request usually starts with `REQUEST` |
| URL shown in browser | Usually keeps the original URL | Usually switches to the new URL |
| Request attributes | Can be carried within the same logical request | Not automatically carried to the new HTTP request |
| Security context | Usually continuous in forwarded request, depending on filters/context | Must authenticate/restore via the new request's mechanism |
| What must be protected | Both initial endpoint and forwarded target | Both initial endpoint and new endpoint |

Spring MVC example:

```java
@GetMapping("/old-page")
public String forward() {
    return "forward:/new-page";
}

@GetMapping("/moved-page")
public String redirect() {
    return "redirect:/new-page";
}
```

This is an **illustrative controller snippet**, not a standalone program. `forward:` requests internal forwarding; `redirect:` produces a response directing the client to navigate to the target path. Specific router and view resolver mechanics still need checking against the MVC configuration.

**A redirect is not considered pre-authorized merely because the source endpoint allowed access.** A browser or client can call the target URL directly without going through the source, and the new HTTP request must be subject to its own policy.

### 2.3. Forward vs. Include

`RequestDispatcher.include(...)` embeds another resource's output into the current response. During include, the original request's path info is preserved per Servlet semantics, and the included resource is restricted from changing status/headers. Conversely, forward transfers responsibility for generating the response to the target resource, typically adjusts visible paths/parameters, and must occur **before the response is committed**.

Both remain server-side mechanisms. Including an HTML or JSP fragment does not grant that fragment implicit permission to read sensitive data. If the fragment reads data, the involved services/repositories must still enforce subject-based permissions.

## 3. What Is Preserved and What Changes During a Forward?

### 3.1. Same Request Lifecycle, Changed Target

The Servlet API ensures forwarding preserves request/response per contract (or corresponding wrappers). With a `RequestDispatcher` obtained by path, path and parameter information are adjusted to reflect the target resource; hence code at the target may observe different path values than the first pass.

After `forward(...)`:

- `request.getDispatcherType()` at the target returns `FORWARD`.
- The current path may point to the target resource.
- Server-set request attributes can persist and be read at the target.
- Standard forward attributes preserve the initial request information.
- No new principal is created just because execution moved to a view.
- If the response is already committed, calling forward is invalid and can throw `IllegalStateException`.

This explains why logs recording only `requestURI` without dispatcher type sometimes make one request look like "two endpoints were called". Two log lines may belong to **one client request with two internal processing passes**.

### 3.2. Standard Request Attributes for Forward

Jakarta Servlet provides attribute name constants in `jakarta.servlet.RequestDispatcher`:

```java
import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.http.HttpServletRequest;

Object originalUri = request.getAttribute(
    RequestDispatcher.FORWARD_REQUEST_URI
);
Object originalContextPath = request.getAttribute(
    RequestDispatcher.FORWARD_CONTEXT_PATH
);
Object originalServletPath = request.getAttribute(
    RequestDispatcher.FORWARD_SERVLET_PATH
);
Object originalQuery = request.getAttribute(
    RequestDispatcher.FORWARD_QUERY_STRING
);
```

This is **Servlet integration code**, assuming variable `request` already exists. The constant names correspond to standard request attributes set by the container upon forwarding. Original details are useful for logging, reconstructing context, debugging routes, or appropriate business handling.

**Never use `FORWARD_REQUEST_URI` as an "authorization ticket"**: "the initial request targeted a public URL" does not prove "the current sensitive target is also allowed". Sensitive targets or services need their own policies. On the other hand, do not trust a custom-named request attribute if it could be copied from unverified headers/queries.

### 3.3. Does the Security Context Persist?

In normal cases, the `SecurityContext` established during `REQUEST` is retained so subsequent components can use the same identity. Spring Security also documents carrying context across dispatch passes. However, **which filters participate, whether context is loaded/saved, and when `SecurityContextHolder` is accessed** depend on configuration.

Do not deduce that:

- Forward automatically refreshes a JWT/role from the IdP.
- A request attribute containing a username is proof of authentication.
- Merely having a principal in the initial controller means every other dispatch pass is permitted.
- Moving to an async thread can rely by default on the `ThreadLocal` context from the initial pass.

If decisions depend on recently revoked permissions, separate solutions for TTL, session/token revocation, or policy lookup are needed. Forward only moves processing within the request lifecycle; it does not alter permission revocation mechanics.

### 3.4. Request Parameters Can Be Affected by Forward

When forwarding to a target path with query parameters, the target request can receive parameters adjusted per the Servlet contract. Therefore, do not use `getParameter("role")` to determine permissions or `getParameter("tenant")` to grant scope: clients and application code can influence those values. Critical decisions must rely on `Authentication`, membership, server-side data, and policy.

## 4. Which Dispatch Passes Does Spring Security Check?

### 4.1. AuthorizationFilter Can Authorize Multiple Times

In Spring Security Servlet 6.x `authorizeHttpRequests` configuration, the official documentation states `AuthorizationFilter` authorizes not only on `REQUEST` passes, but also on other dispatch passes such as `FORWARD`, `ERROR`, and `INCLUDE` when the filter participates in processing.

Example:

```text
REQUEST /app/orders
  -> hasAuthority("order:read")
  -> controller returns view
FORWARD /WEB-INF/views/orders.jsp
  -> AuthorizationFilter may evaluate again
  -> if no matching rule exists, denyAll may return 403
```

This is not necessarily a bug in user authentication. It may simply be that **the request on the forward pass is matched by the new path**, while the configuration only had rules for the initial path.

**Technical condition to remember:** additional checks occur only if `springSecurityFilterChain`/relevant filters are registered and actually invoked for that dispatcher type. Servlet/container configuration and filter registration can change the outcome. Do not conclude "every request is always authorized exactly N times".

### 4.2. SecurityFilterChain Selection Can Differ per Pass

`FilterChainProxy` picks a matching `SecurityFilterChain` based on the current request. If the filter proxy is invoked on a forward, the forward pass's path and dispatcher type may cause **a different chain** to be selected compared to the initial REQUEST pass.

Example:

```text
SecurityFilterChain A:
  securityMatcher("/api/**")
SecurityFilterChain B:
  fallback (all other paths)

REQUEST /api/report
  -> chain A

FORWARD /WEB-INF/views/report.jsp
  -> may select chain B when proxy is invoked again
```

An `anyRequest().denyAll()` in chain A **does not cover** `/WEB-INF/views/report.jsp` if that pass does not match chain A. Conversely, chain B might process the forward target with stricter rules than expected. You must inspect **filter registration, securityMatcher, chain ordering**, and rules inside the chain actually selected.

Do not reason "already passed chain A so chain B does not matter" or "all chains run cumulatively". On a single `FilterChainProxy` invocation, the first matching chain is chosen.

### 4.3. `dispatcherTypeMatchers(...)` Conditions

The Spring Security DSL lets you evaluate dispatcher type as an authorization criterion:

```java
import static jakarta.servlet.DispatcherType.ERROR;
import static jakarta.servlet.DispatcherType.FORWARD;

http.authorizeHttpRequests(auth -> auth
    .dispatcherTypeMatchers(FORWARD, ERROR).permitAll()
    .requestMatchers("/app/orders").authenticated()
    .anyRequest().denyAll()
);
```

This is an **illustrative configuration snippet** following Spring Security Servlet 6.x API style. It permits every `FORWARD` and `ERROR` pass seen by the authorization matcher, helping many MVC apps render views or error pages without unintended denials.

**However, this is not blanket advice for every system.** Broad `FORWARD` and `ERROR` rules can let a forward pass to a sensitive handler bypass request-level authorization. If the target handles sensitive data, enforce checks at method/service/data layers and/or narrow the rule to controlled internal targets.

### 4.4. A Configuration Narrowed by Forward Target

The following example illustrates permitting only **forwards to a view area** and **error dispatches to a simple error page**, while all business paths still require authorities. This is a **Spring Boot 3.x / Spring Security Servlet 6.x skeleton**, not standalone-runnable; it requires matching authentication, MVC mappings, and view renderer configuration.

```java
import jakarta.servlet.DispatcherType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
@EnableMethodSecurity
public class DispatchAuthorizationConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        // Illustration only for an app with servlet paths as below.
        // In practice, verify view resolver/container mappings.
        RequestMatcher internalViewForward = request ->
            request.getDispatcherType() == DispatcherType.FORWARD
                && request.getServletPath()
                    .startsWith("/WEB-INF/views/");

        RequestMatcher errorPageDispatch = request ->
            request.getDispatcherType() == DispatcherType.ERROR
                && "/error".equals(request.getServletPath());

        http.authorizeHttpRequests(auth -> auth
            // Protect business actions on every dispatch pass
            // that Spring Security actually handles.
            .requestMatchers(HttpMethod.GET, "/api/documents/**")
                .hasAuthority("document:read")
            .requestMatchers(HttpMethod.POST, "/api/documents/**")
                .hasAuthority("document:write")
            .requestMatchers(HttpMethod.GET, "/admin/**")
                .hasAuthority("admin:read")

            // Only open controlled view-rendering and error-page scopes.
            .requestMatchers(internalViewForward).permitAll()
            .requestMatchers(errorPageDispatch).permitAll()

            .requestMatchers(HttpMethod.GET, "/app/home")
                .authenticated()
            .anyRequest().denyAll()
        );

        return http.build();
    }
}
```

Key points to understand:

1. `/api/documents/**` and `/admin/**` routes are declared before the exception branches. If a forward targets a business route matching those matchers, the corresponding authority is still checked.
2. `internalViewForward` requires both **dispatcher type FORWARD** and the target path lying in the defined view area. Direct `REQUEST` calls to that path are not permitted by this branch.
3. `errorPageDispatch` selects only `ERROR` to `/error`. It does not expose `/error` to external requests under the same rule.
4. `anyRequest().denyAll()` closes unclassified cases.
5. The example relies on `getServletPath()` for views; if servlet mappings differ, this value can differ. Test with real requests. Granting access to the view area is only reasonable if views **do not execute sensitive business actions themselves**.
6. If the application has multiple `SecurityFilterChain`s, this rule must be placed in the chain actually covering the forward/error pass, or have a protective fallback. It cannot fix missing coverage at the `FilterChainProxy` level.

**Limitation:** `getServletPath().startsWith(...)` in this snippet is used only as a clear illustration of intent; in real apps verify path normalization, encoded URLs, servlet mappings, and view types. Prefer matchers compatible with your router/container. Never allow sensitive business logic to run simply because a resource sits under a folder named `views`.

### 4.5. Why Can an Overly Broad Rule Be Dangerous?

Suppose:

```text
FORWARD /any-path -> permitAll
REQUEST /admin/delete -> hasRole(ADMIN)
```

If there is a public controller whose forward target can be influenced and it forwards to the `/admin/delete` handler, the FORWARD pass can pass through the `permitAll` rule while the sensitive action requires admin. When using broad forward permits, it is only safe when **no arbitrary target-control paths exist** and **service/data layers still enforce independent policies**, along with other boundaries.

Do not assume an internal endpoint cannot be invoked simply because clients cannot see the forward path. Permission checks must rely on identity and action, not on whether the invocation path is "internal".

## 5. `OncePerRequestFilter` and Avoiding Duplicate Processing

The name `OncePerRequestFilter` easily creates the misconception that this filter runs strictly once under all circumstances. In practice, it is a base class in Spring Framework designed to control filter execution within a request pass using a marker attribute mechanism; behavior across other dispatchers is also affected by filter registration and configuration methods.

Points to remember:

- A filter may be invoked by the container on `REQUEST`, `FORWARD`, `ERROR`, and `ASYNC` depending on dispatcher type registration.
- For an ongoing processing pass, the "already filtered" mechanism prevents duplicate `doFilterInternal` logic under the same conditions guarded by the base class.
- `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()` adjust whether the filter skips async/error passes. The common default is to skip.
- Do not infer that registering a filter with multiple dispatcher types makes the filter handle all of them automatically; both condition layers (registration and filter logic) take effect.
- Do not use the name "OncePerRequest" to conclude that the authorization manager or another filter is also evaluated strictly once.

In particular, **`AuthorizationFilter` cannot be equated with `OncePerRequestFilter`**. Spring Security can evaluate permissions across multiple dispatch passes when participating in them, whereas a custom filter extending `OncePerRequestFilter` has its own behavior.

### 5.1. Illustrative Filter Code with Async/Error Conditions

```java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.springframework.web.filter.OncePerRequestFilter;

public class CorrelationFilter extends OncePerRequestFilter {
    @Override
    protected boolean shouldNotFilterAsyncDispatch() {
        return false;
    }

    @Override
    protected boolean shouldNotFilterErrorDispatch() {
        return false;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        try {
            // Read/create a controlled request correlation ID
            // and set up appropriate logging context.
            chain.doFilter(request, response);
        } finally {
            // Clean up context on the executing thread.
        }
    }
}
```

This is only an **integration code skeleton**: filter registration and the logger/correlation ID implementation are omitted. Returning `false` is insufficient to force the filter to run if the container does not register it for the corresponding dispatcher type. Do not turn an observational filter into an authorization point based on raw headers. When running asynchronously, handle cleanup properly per thread and avoid overwriting/misusing logging context.

### 5.2. Warning About Logic Running Multiple Times

An observational filter or handler invoked extra times due to dispatches can:

- Increment counters or write logs multiple times for a single client HTTP request.
- Record "processed" audits multiple times when there was actually only one business decision.
- Add headers multiple times or generate a new correlation ID, breaking traces.
- Invoke non-idempotent business logic if misconfigured (which must be strictly avoided).

Do not solve this with a global static `alreadyProcessed` variable; that can cause other valid requests to interfere with each other. You must determine **which level is being counted**: one dispatch pass, one client HTTP request, one business transaction, or a command with an idempotency key.

## 6. Async: "Re-Dispatched Request" Differs from "Job Running on Another Thread"

### 6.1. Async Servlet Dispatch

In Servlet async, a request can call `startAsync()`, temporarily release the initial thread, continue work, and re-dispatch via `AsyncContext.dispatch(...)`. The re-dispatched pass carries `DispatcherType.ASYNC`. Filters registered for async can participate in another processing pass.

Thread switching makes `SecurityContextHolder` critical: the default strategy in Servlet typically uses `ThreadLocal`, so do not feel confident that the security context will be present in arbitrary callbacks/threads. Spring Security provides integration with Spring MVC async and security context propagation wrappers, yet you still need to understand the exact version, usage, and permission check points.

### 6.2. Do Not Equate Three Execution Styles

| Situation | Nature | Is it an `ASYNC` redispatch? |
| --- | --- | --- |
| Servlet `AsyncContext.dispatch()` | Re-dispatch pass within one HTTP request lifecycle | Yes |
| Spring MVC async `Callable`/`DeferredResult` | Asynchronous HTTP handling with Servlet/framework integration | Can lead to an async dispatch per framework mechanics |
| `@Async`, executor, `CompletableFuture`, or standalone queue job | Work running on another thread/worker | Not a Servlet ASYNC dispatch by default |
| Client sends next HTTP request | A new request | No |

This point is crucial for authorization: **message consumers or scheduled jobs do not automatically pass through Spring Security HTTP filters**, and often do not share the same principal as the request that triggered the work. Background tasks must have a service identity or explicit delegation model, enforce permissions at service/data layers, and manage expiration/revocation appropriately.

### 6.3. Timing of Permission Checks for Long-Running Tasks

Suppose a user is allowed to request a report export at 10:00, yet the export job executes at 10:15 after permissions have been revoked. You must define the policy: are permissions snapshotted when creating the job, or must they be re-checked before reading data and before downloading the file? Servlet provides no default answer; this is a system business/security decision.

A typical design includes:

1. Check permission to create the task.
2. Bind the task to a verified principal/tenant and scope, without trusting raw payloads.
3. Re-check necessary conditions at execution time based on expiration/revocation rules.
4. When the job generates a file, control access to the finished artifact.
5. Record audits for the job and ensure no cross-tenant usage.

An `Authentication` `Supplier` in authorization does not automatically sync updated permissions or propagate context to background threads.

## 7. ERROR Dispatch: Why Can an Error Page Get 403?

When a controller throws an exception, the container may create an `ERROR` pass to display an error page, such as `/error`. If `AuthorizationFilter` is applied on that pass, an `anyRequest().denyAll()` rule can reject `/error`. Users see a confusing HTTP result, and logs can contain both the original exception and an authorization failure on the error page.

Spring Security documentation notes this as a common situation. You can permit necessary error dispatches, provided you understand the scope:

- An error handler returning only a status code or non-secret static page can normally be permitted.
- An error handler displaying business data or querying user resources still needs data protection.
- Do not use an error dispatch as a way to embed forbidden resource content into the error body.
- Do not return stack traces, session tokens, SQL, or sensitive identifying data to clients.

Standard Servlet request attributes such as `RequestDispatcher.ERROR_STATUS_CODE`, `ERROR_REQUEST_URI`, and `ERROR_EXCEPTION` can help identify the root error; handle and log them appropriately without exposing them in the response. If the error page itself throws an exception, avoid hard-to-diagnose error loops.

### 7.1. When Can Broad `FORWARD` and `ERROR` Allowance Be Appropriate?

In an MVC app that forwards only to view templates with no sensitive data operations, or whose error handler always outputs a safe error page, `dispatcherTypeMatchers(FORWARD, ERROR).permitAll()` can be simple and suitable. However, the deciding conditions must be verified:

- Can a forward target URL be influenced by user input?
- Could the target be a controller performing sensitive operations?
- Do method security and object policies block the action?
- Does filter chain registration apply to that dispatch type?
- Can rules be narrowed to exact view/error paths instead of opening everything?

**Dispatcher-type protection does not replace business-layer protection.**

## 8. Standalone Java 17 Program: Simulating Dispatch Passes and Permissions

The following example helps visualize that **an allowed REQUEST pass does not mean a FORWARD pass to a sensitive resource is also allowed**. It is a pure Java model, does not implement a filter container, and does not claim to accurately simulate all Spring Security internals.

Save file `ServletRedispatchAuthorizationDemo.java`:

```java
import java.util.HashSet;
import java.util.Set;

public class ServletRedispatchAuthorizationDemo {
    enum Kind { REQUEST, FORWARD, INCLUDE, ERROR, ASYNC }

    record Principal(long id, long tenantId, Set<String> authorities) {}
    record Document(long id, long tenantId, long ownerId) {}
    record Dispatch(Kind kind, String method, String path) {}

    static boolean allowed(
            Dispatch dispatch,
            Principal principal,
            Document document) {

        if (dispatch == null || dispatch.kind() == null
                || dispatch.method() == null
                || dispatch.path() == null) {
            return false;
        }

        // Only allow forward into server-managed view area.
        if (dispatch.kind() == Kind.FORWARD
                && dispatch.path().startsWith("/WEB-INF/views/")) {
            return true; // Render only, no business execution.
        }

        // Only allow error dispatch to error page without sensitive data.
        if (dispatch.kind() == Kind.ERROR
                && "/error".equals(dispatch.path())) {
            return true;
        }

        // Normal page endpoint requires an authenticated user.
        if (dispatch.kind() == Kind.REQUEST
                && "GET".equals(dispatch.method())
                && "/app/home".equals(dispatch.path())) {
            return principal != null;
        }

        // Every dispatch to this API must satisfy resource permissions.
        if ("GET".equals(dispatch.method())
                && dispatch.path().matches("/api/docs/[0-9]+")) {
            return principal != null
                && principal.authorities() != null
                && principal.authorities().contains("doc:read")
                && document != null
                && principal.tenantId() == document.tenantId()
                && principal.id() == document.ownerId();
        }
        return false;
    }

    static void show(
            String label,
            Dispatch dispatch,
            Principal principal,
            Document document) {
        System.out.println(label + ": "
            + allowed(dispatch, principal, document));
    }

    public static void main(String[] args) {
        Principal owner =
            new Principal(10, 1, Set.of("doc:read"));
        Principal stranger =
            new Principal(20, 1, Set.of("doc:read"));
        Document doc = new Document(7, 1, 10);

        show("initial home request",
            new Dispatch(Kind.REQUEST, "GET", "/app/home"),
            owner, null);

        show("forward to safe view",
            new Dispatch(
                Kind.FORWARD, "GET", "/WEB-INF/views/home.jsp"),
            null, null);

        show("forward to private api anonymous",
            new Dispatch(Kind.FORWARD, "GET", "/api/docs/7"),
            null, doc);

        show("direct private api owner",
            new Dispatch(Kind.REQUEST, "GET", "/api/docs/7"),
            owner, doc);

        show("forward to private api owner",
            new Dispatch(Kind.FORWARD, "GET", "/api/docs/7"),
            owner, doc);

        show("forward to private api stranger",
            new Dispatch(Kind.FORWARD, "GET", "/api/docs/7"),
            stranger, doc);

        show("error page dispatch",
            new Dispatch(Kind.ERROR, "GET", "/error"),
            null, null);

        show("error into private api",
            new Dispatch(Kind.ERROR, "GET", "/api/docs/7"),
            null, doc);

        show("async resume owner",
            new Dispatch(Kind.ASYNC, "GET", "/api/docs/7"),
            owner, doc);

        show("async resume without context",
            new Dispatch(Kind.ASYNC, "GET", "/api/docs/7"),
            null, doc);

        show("include private api anonymous",
            new Dispatch(Kind.INCLUDE, "GET", "/api/docs/7"),
            null, doc);

        // In-memory idempotency simulation only, not a real DB.
        Set<String> processed = new HashSet<>();
        System.out.println("first operation: "
            + processed.add("operation-1"));
        System.out.println("repeated operation: "
            + processed.add("operation-1"));
    }
}
```

Compile/run with JDK 17 or higher:

```bash
javac ServletRedispatchAuthorizationDemo.java
java ServletRedispatchAuthorizationDemo
```

Expected stdout output:

```text
initial home request: true
forward to safe view: true
forward to private api anonymous: false
direct private api owner: true
forward to private api owner: true
forward to private api stranger: false
error page dispatch: true
error into private api: false
async resume owner: true
async resume without context: false
include private api anonymous: false
first operation: true
repeated operation: false
```

Interpretation:

1. The home page is valid for a logged-in user.
2. The `FORWARD` pass to the view is permitted thanks to the **designated target**, not the dispatch type in general.
3. Forwards to the document API with a missing principal or non-owner are denied. The owner is permitted on both `REQUEST` and `FORWARD` because all resource conditions hold.
4. `ERROR /error` is permitted to render non-sensitive errors; an error dispatched to the document API does not thereby gain permission to read the document.
5. An `ASYNC` pass can access the document only if valid identity and permissions remain in the context evaluated by the policy; this does not guarantee the real framework propagates context automatically.
6. The Set ensures the same key is not added twice **within this program**. In real systems, a `HashSet` is not a durable idempotency mechanism across processes or transactions. You must use business keys/unique constraints or proper duplicate handling.

Do not take the number of log lines printed in the demo as the mandatory number of Spring Security authorization passes. Actual filter passes depend on dispatcher mapping/container.

## 9. "Re-Executed Requests" Can Also Mean Client Retry or Replay

The phrase "re-executed request" can refer to two distinct phenomena:

**A. Redispatch within the same request:** `FORWARD`, `ERROR`, `ASYNC`, and `INCLUDE` are processing passes within a Servlet request's lifecycle per container mechanics.

**B. New request or retry:** a client resends `POST /api/payments` after a timeout; a browser reloads, a proxy retries, a user clicks a button twice; a message queue redelivers a task. These are usually **independent requests or events**, not a `DispatcherType.FORWARD` pass. They must be **re-authenticated and re-authorized** per the applicable mechanism, and protected against executing a transaction twice.

### 9.1. Idempotency Differs from Forward Permission

For sensitive APIs like payments, order cancellation, or account creation:

- Caller permissions must be checked on every executing request, including retry requests.
- Duplicates must be detected using an **idempotency key** or explicitly designed business key (paired with principal/tenant, request content, and appropriate expiration).
- The database needs constraints/transactions so two concurrent requests cannot both write side effects.
- Resource state and version must be checked at execution time.
- With external systems (payment gateways, email), consider an outbox, idempotent downstream APIs, or reconciliation; a DB transaction cannot automatically roll back external effects.

Do not rely solely on a request attribute `"processed=true"` to prevent retries across two different HTTP requests: each new request has a separate object and lifecycle. Nor assume a filter running "once per request" stops a business operation from being resubmitted.

### 9.2. TOCTOU When Permissions or Resources Change Between Passes

If a handler checks permissions and then waits asynchronously, data can change before writing. For example, a document is DRAFT at the start yet gets approved while waiting; upon resuming, the edit-DRAFT operation must be re-checked or executed using a conditional update.

Depending on risk, use versioning/optimistic locking, pessimistic locking, `UPDATE ... WHERE status = 'DRAFT'`, transactions, and affected-row count checks. Do not treat "authorized on REQUEST" as proof that data state remains valid after a wait.

## 10. Designing and Testing by Dispatch Matrix

### 10.1. Mandatory Matrix

| Situation | Dispatcher type / mechanism | Protection expectation |
| --- | --- | --- |
| Authorized user accesses page | `REQUEST` | Enter route if permissions suffice |
| MVC forwards to static view | `FORWARD` | Render if view target is allowed |
| Direct request to `/WEB-INF/views/...` | `REQUEST` | Not accessible merely because of the forward rule |
| Forward to sensitive API | `FORWARD` | Does not bypass method/object policies |
| Error page of normal endpoint | `ERROR` | Can render controlled error |
| ERROR dispatch to sensitive handler | `ERROR` | Do not treat ERROR as permission to access resources |
| Include rendering fragment | `INCLUDE` | Do not leak sensitive data from fragment |
| Async resume with valid principal | `ASYNC` | Enforces still-valid permissions and data |
| Async callback without context | Thread/background | Not allowed by default |
| Redirect to admin page | New HTTP request | Must authenticate/authorize target |
| Client retries same POST | New HTTP request | Check permissions and idempotency |
| Proxy auto-retries on timeout | New/replayed request | Does not produce duplicate side effects |
| Session/JWT expires between requests | Subsequent request | Updated/revoked permissions per policy |
| Two concurrent requests | Two threads/transactions | Consistent constraints and transactions |

A 403 result does not prove "the right dispatch was blocked": it could be missing CSRF, wrong `SecurityFilterChain`, or missing authentication. Isolate the condition under test.

### 10.2. Testing Spring Security Rules Separately

With Spring Security Test and Spring MVC `MockMvc`, initial tests should verify:

1. Users lacking permissions to `/api/documents/7` are blocked.
2. Users with sufficient authority who are not the owner are denied at the service/repository.
3. Routes allowed to render views do not suffer forward 403s from undeclared rules.
4. Direct requests to view/error paths do not accidentally gain permissions like internal dispatches.
5. Varying dispatcher type, path, and principal yields the expected decision.
6. Error endpoints do not leak exception details/secrets.

Example **snippet placed in a test class that already has `MockMvc`, controllers, and fixtures**:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

// Fixture: /api/documents/7 is protected by document:read.
mockMvc.perform(get("/api/documents/7")
        .with(user("viewer").authorities(
            new SimpleGrantedAuthority("document:read"))))
    .andExpect(status().is2xxSuccessful());
```

Requires importing `org.springframework.security.core.authority.SimpleGrantedAuthority`. This snippet **is not a standalone compilable file** and 2xx holds only if the user has permissions on document 7 per the actual fixture. Do not use this test to claim filters re-run on `FORWARD` or `ASYNC` passes; some Servlet container behaviors are not fully simulated by plain MVC tests.

### 10.3. Testing Dispatcher Types with MockHttpServletRequest

To **unit-test a single matcher** based on `DispatcherType`, you can build a mock request:

```java
import jakarta.servlet.DispatcherType;
import org.springframework.mock.web.MockHttpServletRequest;

MockHttpServletRequest req =
    new MockHttpServletRequest("GET", "/WEB-INF/views/home.jsp");

req.setServletPath("/WEB-INF/views/home.jsp");
req.setDispatcherType(DispatcherType.FORWARD);

boolean internalView = req.getDispatcherType()
        == DispatcherType.FORWARD
    && req.getServletPath().startsWith("/WEB-INF/views/");

// internalView == true with this mock data.
```

This proves **matcher logic** on mock request data. It does not prove the container actually invokes `springSecurityFilterChain` on forward, does not prove SecurityContext is propagated properly, and does not prove the view causes no side effects.

Add integration tests using an embedded servlet container or real dispatch configuration when proving the filter/dispatch lifecycle. With Spring Security, verify the filter bean is registered for required `DispatcherType`s and observe actual execution passes.

### 10.4. Testing Filter Registration and Logs

In test/staging environments with appropriate security logging, observe at minimum:

- Client request Correlation ID.
- `DispatcherType` of each pass.
- Method and path on the current pass, and if needed the original URI in standard attributes.
- Selected chain and rule (avoid logging secrets).
- Minimal verified principal/authorities, ALLOW/DENY decision.
- Whether a business transaction executed a side effect.

If one client request produces two authorization log lines, that may be expected behavior. If one business action creates two payments, that is usually a critical bug. Do not infer data integrity solely from filter log counts.

### 10.5. Testing Response Commit and Nested Errors

Verify that forwards happen before the response commits. Once a handler flushes the response, forwarding can be invalid. Test that error pages appear when handlers throw exceptions or send error codes, and ensure error handlers do not call protected endpoints again or fall into continuous error loops.

If using AJAX/JSON APIs, forwarding to a view may be unnecessary; a structured error response is usually easier to manage. Design authorization/error handling separately for APIs and web views instead of sharing one broad rule across all client types.

## 11. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming `REQUEST` is the whole lifecycle | Ignores `FORWARD/ERROR/ASYNC` | Trace flows by dispatcher type |
| Accidentally blocking all forwards | MVC view renders 403 | Define policy for target views and test |
| `permitAll()` on all FORWARDs | Can bypass HTTP authorization of sensitive targets | Narrow targets or retain trusted business gates |
| `permitAll()` ERROR on handler with private data | Data leaks or unwanted state | Open only safe error views |
| Assuming filters always run on every dispatch | Expected checks do not exist | Verify dispatcher registration and filter behavior |
| Assuming `OncePerRequestFilter` means strictly once forever | Overlooks async/error and double invocation | Understand markers and shouldNotFilter methods |
| Basing permissions on self-declared request attributes | Spoofing tenant/user via headers | Use verified Authentication and membership |
| Using `FORWARD_REQUEST_URI` to authorize targets | Client influences source URL then forwards to another target | Authorize by actual target and resource |
| Forgetting fallback SecurityFilterChain | Forward/error selects path outside chains | Cover all routes and appropriate dispatches |
| Relying on `SecurityContextHolder` in arbitrary async threads | Lost or wrong principal | Propagate context safely, design task identity |
| Writing side effects in views/filters | An extra dispatch pass writes duplicates | Separate business logic from rendering/filters |
| Treating retry as FORWARD | Fails to block duplicate POST | Use durable idempotency and transactions |
| Testing only for a 403 response | Cannot tell if blocked by CSRF or authorization | Isolate root cause, inspect data after request |
| Logging each dispatch as a transaction | Corrupts audit/metric counts | Separate request ID, dispatch ID, business operation ID |
| Calling forward after response commit | IllegalStateException or broken response | Forward before flushing/committing |
| Checking state only on REQUEST, writing after async | TOCTOU on state/permissions | Recheck/conditional write/versioning |

## 12. Practice Exercises

### Exercise 1 — Diagramming an MVC Page Flow

For `GET /app/orders` returning JSP view `orders`, diagram the `REQUEST` and `FORWARD` passes. Specify method, path, dispatcher type, which SecurityFilterChain can match, when the controller runs, and which view renders. Explain why an "order approved" event should not be recorded inside view-rendering code.

### Exercise 2 — Fixing 403 on Forward

An app has `anyRequest().denyAll()`, allowing only `GET /app/orders`. The view resolver forwards to `/WEB-INF/views/orders.jsp` and gets 403. Propose a rule permitting forwards only to the controlled view area. Write a test ensuring direct client requests to the view area are not granted access by that rule.

### Exercise 3 — Protecting Sensitive Targets

A public controller accepts parameter `target` and forwards to a user-supplied path. Explain the risk of using a broad `FORWARD.permitAll()`. Redesign using a fixed target allowlist, method security, and tenant checks in the service. Prove forwarding to a sensitive API cannot bypass permissions.

### Exercise 4 — Running Java 17

Run `ServletRedispatchAuthorizationDemo.java`. Change the forward to `/api/docs/7` using a user from another tenant, add a case targeting `/WEB-INF/views/home.jsp` with dispatcher `REQUEST`, and a redirect modeled as a new request. Predict stdout and then verify.

### Exercise 5 — Async and Security Context

Create an endpoint returning `Callable` or `DeferredResult`, safely logging dispatcher type and principal. Verify security context on the involved threads in real configuration, then check permissions in the service. Test permission revocation while the job is pending to establish the effective policy.

### Exercise 6 — Retry and Idempotency

Simulate a client sending `POST /api/payments` twice with the same operation key. Using a data store with unique constraints and processing status, prove side effects are not executed twice. Compare against using only request attributes or a local `HashSet`, explaining why the latter is insufficient in multi-instance systems.

## 13. Implementation Checklist

- [ ] Know the exact dispatcher types in which Servlet filters and Spring Security filters participate.
- [ ] Distinguished `REQUEST/FORWARD/INCLUDE/ERROR/ASYNC` from redirects and HTTP retries.
- [ ] Forward targets used for rendering do not execute sensitive business actions.
- [ ] Sensitive handlers enforce authority and object permissions in service/data layers.
- [ ] `dispatcherTypeMatchers(...)` is used within reviewed bounds, not broadened arbitrarily.
- [ ] `SecurityFilterChain`s cover all target paths and dispatches needing protection.
- [ ] `OncePerRequestFilter` is configured appropriately for async/error and filter registration.
- [ ] Original URI, request attributes, or raw headers are never used to grant permissions.
- [ ] Async/background work has a clear principal/context/tenant model.
- [ ] Non-idempotent operations have replay/retry protection at the data layer.
- [ ] Thorough tests cover original requests, forwards, errors, async, and direct access to views/handlers.
- [ ] Logs include correlation IDs for requests, dispatches, and business operations without leaking secrets.
- [ ] State/version checks exist at execution time after asynchronous waits.

## 14. End-of-Lesson Self-Check

1. **Does a forward create a new HTTP request from the browser?** Normally no; it is server-side forwarding within the current request's lifecycle.
2. **How does redirect differ from forward?** Redirect returns 3xx instructing the client to send a new request; forward is an internal dispatch with `DispatcherType.FORWARD`.
3. **Why can a JSP view receive 403 after an allowed controller?** Because the FORWARD pass can be evaluated by `AuthorizationFilter` against the new target path and lack a matching rule.
4. **Does Spring Security automatically check every dispatch in every container setup?** Cannot be assumed unconditionally; the filter proxy still must be registered and actually run for that dispatcher type.
5. **Should all FORWARDs be permitted by default?** Only when the forward model and business layer guarantee safety; if sensitive handlers exist, use narrow rules and separate checks.
6. **Is `FORWARD_REQUEST_URI` proof of permission to access the target?** No. It is original request metadata for reference/debugging.
7. **Does OncePerRequestFilter guarantee never running again in async/error?** Do not guess from the name; inspect dispatcher registration and shouldNotFilter methods.
8. **Is an ASYNC dispatch the same as an `@Async` background job?** No. One is a Servlet request dispatch pass; the other is a task on a separate thread that may lack request context.
9. **Does a client POST retry have `DispatcherType.FORWARD`?** No; it is usually a new HTTP request requiring separate authorization and idempotency handling.
10. **Why not use a request attribute `processed=true` to block duplicate payments between two requests?** Because requests have independent lifecycles and can run across multiple instances; durable data/business constraints are required.
11. **If a service checked permissions before an async wait, must it re-evaluate at execution time?** Depending on policy, expiration, and risk, yet mutated data/versions must be protected at execution time.
12. **Does having `admin:read` allow viewing another tenant's document via forward?** Not by default; object policy must check tenant/owner and actual permission scope.

**Remember:** forwards and redispatches show that **an HTTP request is not necessarily a single processing pass**. Proper protection must recognize dispatcher type, current target, trusted principal source, which filters actually run, and still-valid business policies. Allowing a view or error page to render does not mean allowing sensitive actions; client retries are new requests needing separate authorization and idempotency controls.

### Official References

- [Spring Security 6.5 – Authorize HTTP Requests / All Dispatches Are Authorized](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security – Servlet Architecture and FilterChainProxy](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Framework – Servlet Filters / OncePerRequestFilter](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html)
- [Jakarta Servlet – RequestDispatcher](https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/RequestDispatcher.html)
- [Jakarta Servlet – ServletRequest.getDispatcherType()](https://jakarta.ee/specifications/servlet/6.1/apidocs/jakarta.servlet/jakarta/servlet/ServletRequest.html)