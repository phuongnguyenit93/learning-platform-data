# Filter Runs Twice or Processes Results in the Wrong Place in Spring Security

## 1. Goal: Diagnosing "Twice" and "Wrong Place" Properly

In Spring Security, a request passes through the **Servlet container filter chain**, `DelegatingFilterProxy`, `FilterChainProxy`, and a matching `SecurityFilterChain`. A custom filter might verify an API key, read a bearer token, attach a correlation ID, check a tenant, or write logs. Simply registering a filter in two places or placing it in the wrong order can cause confusing symptoms:

- Credential-verification logs appear twice for the same request.
- A valid API key still gets 401 because the filter ran before `SecurityContext` was expected or the context was overwritten.
- Login uses the right password yet the handler returns the wrong JSON/redirect; the response was already committed and then written to again.
- One request runs the filter on `REQUEST` and again on `ERROR` or `ASYNC` dispatch.
- The controller runs once while the filter logs twice; or one user click triggers `OPTIONS` + `POST`.
- `AuthenticationException` turns into 500 because the custom filter threw it **before** `ExceptionTranslationFilter`.
- A filter finishes handling the request yet still calls `chain.doFilter(...)`, letting the controller and downstream filters keep running.
- A successful authentication is mistaken for successful authorization; the final 403 makes developers think the auth filter failed.

This lesson belongs to the **Diagnostics** section of **Spring Security - authentication**, aiming to show **root causes, evidence to collect, configuration fixes, and how to test**. Content targets Spring Security **Servlet/MVC** (Spring Boot 3.5.x, Java 17+), with notes where relevant for WebFlux.

After this lesson, you can distinguish three cases:

1. **True duplicate registration:** the filter is both registered by the servlet container and invoked by the Security chain.
2. **Multiple valid dispatches/requests:** one browser action can emit multiple HTTP requests or one request can have `ERROR/ASYNC/FORWARD` dispatches, which is not necessarily a filter bug.
3. **Processing in the wrong place:** authentication, authorization, exception translation, failure/success handlers, and response commits are misordered.

**First principle:** never "fix" by deleting a log line or adding a global boolean flag. Identify **how many HTTP requests, how many dispatches, how many filter instances, how many authentications, and where a response is committed**.

## 2. Request Path: Container Filters and `SecurityFilterChain`

Conceptual diagram for a Servlet HTTP request:

```text
HTTP client
    |
    v
Servlet container
    |
    |  Filter A (if container-registered)
    |
    v
DelegatingFilterProxy("springSecurityFilterChain")
    |
    v
FilterChainProxy
    |
    +--> selects FIRST SecurityFilterChain matching request
             |
             +--> SecurityContextHolderFilter
             +--> HeaderWriterFilter / CsrfFilter / CorsFilter ...
             +--> LogoutFilter
             +--> authentication filters
             +--> AnonymousAuthenticationFilter
             +--> ExceptionTranslationFilter
             +--> AuthorizationFilter
             +--> custom filters placed by anchor/order
             |
             v
         DispatcherServlet
             |
             v
       MVC Controller / Handler
```

Exact ordering depends on version, DSL, and enabled filters. The diagram is neither an exhaustive list nor a guarantee every filter is always present. Useful invariants:

- The **Servlet container** can hold filters outside Spring Security.
- `DelegatingFilterProxy` bridges to the `FilterChainProxy` bean usually named `springSecurityFilterChain`.
- `FilterChainProxy` selects **the first matching `SecurityFilterChain`** in the list; it does not run all matching chains sequentially.
- Within the chosen chain, filter order determines which context is available, whether CSRF/CORS ran, and where exceptions are caught.
- `chain.doFilter(request, response)` passes execution to the **next element**. A filter can stop the request by writing a response **without** calling onward.

### 2.1. Two Separate Registration Systems

This is an extremely common bug:

```java
@Component
class DemoTokenFilter extends OncePerRequestFilter {
    // ...
}

@Bean
SecurityFilterChain securityFilterChain(
        HttpSecurity http,
        DemoTokenFilter tokenFilter) throws Exception {
    return http
        // ...
        .addFilterAfter(tokenFilter, LogoutFilter.class)
        .build();
}
```

**Problem:** the filter is a `@Component` Spring bean. Spring Boot can **auto-register** beans implementing `jakarta.servlet.Filter` into the embedded servlet container. Then you also register **the exact same filter instance** in Spring Security. A request can traverse both filter paths in an unintended order.

Spring Security's documentation on *Declaring Your Filter as a Bean* warns about this exact scenario. When it happens, you cannot reliably conclude "the filter ran exactly twice" merely by reading code: `OncePerRequestFilter` has an already-filtered marker, and container filter order plus dispatch types may cause `doFilterInternal` to run only once even while **registered in two places**. Worse, it may execute **outside `SecurityFilterChain`**, where context/exception handling behaves unexpectedly.

### 2.2. Two Spring-Documented Fixes

**Option A — preferred when the filter is used only inside Spring Security:** do not declare the filter as `@Component`/`@Bean`; instantiate it locally inside `SecurityFilterChain` and inject **other dependencies** via the `@Bean` method.

```java
@Bean
SecurityFilterChain apiChain(
        HttpSecurity http, AuthenticationManager manager)
        throws Exception {

    DemoTokenFilter tokenFilter = new DemoTokenFilter(manager);

    return http
        .securityMatcher("/api/**")
        // ...
        .addFilterAfter(tokenFilter, LogoutFilter.class)
        .build();
}
```

**Option B — when the filter genuinely needs to be a Spring bean:** disable **container** auto-registration while still using that bean inside Spring Security.

```java
@Bean
FilterRegistrationBean<DemoTokenFilter> filterRegistration(
        DemoTokenFilter filter) {

    FilterRegistrationBean<DemoTokenFilter> registration =
        new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
```

Add import `org.springframework.boot.web.servlet.FilterRegistrationBean`. Option B is an **excerpt**, assuming a `DemoTokenFilter` bean exists and is registered in a chain. `setEnabled(false)` here disables only **servlet container auto-registration**; it does **not** disable the instance inside `SecurityFilterChain`.

**Do not mix both approaches arbitrarily.** A local non-bean instance does not need a `FilterRegistrationBean` to disable auto-registration.

## 3. "Filter Ran Twice" Has at Least Six Causes

| Cause | Symptom | What to Verify |
| --- | --- | --- |
| Bean filter + `addFilterBefore/After` | Same class sits in both container and security chain | Filter registrations + security chain composition |
| Two instances of the same type added to one chain | Two `doFilterInternal` logs for a single `REQUEST` | Instance ID, filter name, chain order |
| Container and security both enable **same feature** | E.g. CORS/encoding/security headers processed at two layers | Config sources in MVC, Boot, proxy, Security |
| `REQUEST` then `ERROR/ASYNC/FORWARD` dispatch | Same correlation ID yet different dispatcher types | `request.getDispatcherType()`, URI, and trace |
| Browser emits `OPTIONS` + main request | Two distinct HTTP methods | Network tab and separate request IDs |
| Client/gateway retries the HTTP request | Two real HTTP request IDs; possibly identical payload | Retry headers/traces, gateway policy, idempotency |

Additionally, a frontend SPA can call an API twice due to duplicate event listeners, component re-renders, dev Strict Mode/side effects, or user double-clicks. Before editing Spring Security, check **Network**: did truly only one request reach the server?

### 3.1. Things That Do Not Prove a Filter Ran Twice

- Two log lines from **two different loggers** during the same filter invocation.
- One "Securing GET ..." line and one "Secured GET ..." line from Spring Security.
- CORS preflight `OPTIONS` and the real `POST`: these are **two requests**, not the same filter processing one request twice.
- Two application events, such as `AuthenticationSuccessEvent` and `InteractiveAuthenticationSuccessEvent`: do not prove the login filter ran twice.
- A 401 response after an "Authenticated" log: authentication may have succeeded while downstream authorization, session persistence, or response handling failed.
- Controller invoked once: does not rule out duplicate filter registration before or after the controller.

**Always correlate request ID + dispatcher type + filter instance ID + selected chain + log points before/after `chain.doFilter`.**

## 4. What Does `OncePerRequestFilter` Guarantee — and Not Guarantee?

Spring Framework's `OncePerRequestFilter` ensures a filter runs **once per matching dispatch/execution on the request thread**, via a request attribute suffixed with `.FILTERED` (from `ALREADY_FILTERED_SUFFIX`). It provides `doFilterInternal(...)` instead of writing raw `doFilter(...)` yourself.

A standard class:

```java
final class TraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        // Runs once for the dispatches supported by this filter.
        chain.doFilter(request, response);
    }
}
```

**What must not be inferred:**

- It does not mean one user click produces only one HTTP request.
- It does not mean one request cannot trigger `ASYNC` or `ERROR` dispatches.
- It does not replace registering the filter **in only one place**; the already-filtered marker can distort effect ordering when auto-registered twice.
- It does not deduplicate two **distinct instances**, especially with differing filter names/attributes.
- It does not keep the marker forever: subsequent requests need processing again; the marker lives for that execution.
- It does not make auth results/sessions/tokens idempotent.
- It does not make a filter a valid Spring Security auth/authz mechanism if placed in the wrong chain.

### 4.1. Async and Error Dispatches

Servlets can use `DispatcherType.REQUEST`, `ASYNC`, `ERROR`, `FORWARD`, or `INCLUDE`. `OncePerRequestFilter` provides hooks:

```java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return true;  // Do not re-filter ASYNC dispatches.
}

@Override
protected boolean shouldNotFilterErrorDispatch() {
    return true;  // Do not re-filter ERROR dispatches.
}
```

These methods are **excerpts** inside a subclass. `OncePerRequestFilter` defaults generally skip async/error dispatches; however, it also depends on **Servlet filter registration `dispatcherTypes`** and custom code. Check the Javadoc for your running Spring Framework version.

Calling `sendError(...)` on a response can trigger a **nested ERROR dispatch**; Spring Framework includes `doFilterNestedErrorDispatch(...)` to handle wrappers during nested dispatches. A log line with the same URI and `DispatcherType=ERROR` is not automatic proof of duplicate registration.

### 4.2. `shouldNotFilter` by Path

For an API-only filter:

```java
@Override
protected boolean shouldNotFilter(HttpServletRequest request) {
    return !request.getServletPath().startsWith("/api/");
}
```

This helps when one filter instance sits on a broad chain. Still, the better **primary boundary** is `securityMatcher("/api/**")` on a separate `SecurityFilterChain` when routes have distinct auth models. Never use `shouldNotFilter` as a substitute for authorization policy.

**Watch context path:** `getRequestURI()` may include the context path, while `getServletPath()` has different semantics. Test with deployed context paths and reverse proxies, not only localhost root.

## 5. Multiple `SecurityFilterChain`s Do Not Automatically Mean Running Twice

Spring Security selects **the first matching chain**. Example:

```java
@Bean
@Order(1)
SecurityFilterChain machineApi(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/**")
        // API authentication config ...
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browser(HttpSecurity http) throws Exception {
    return http
        // Form login/session config ...
        .build();
}
```

For `GET /api/whoami`, the `@Order(1)` chain is chosen; the second chain does not also run, even if a broad matcher on the second chain would also match. **Order matters:**

- If a catch-all chain precedes `/api/**`, the API chain may **never run**.
- If a filter is attached only to the web chain while the request hits the API chain, it is not called.
- If you copy the same filter into two chains, each request still picks only one chain; however, two chains may hold different instances and differing config bugs.
- A filter **outside** `FilterChainProxy` in the servlet container can run regardless of which chain Spring Security picks.
- `web.ignoring()` differs from `permitAll()`: ignoring generally skips the security chain altogether; public endpoints via `permitAll` still receive security headers and matching filters. Do not use ignore to "fix" login bugs unless you understand the consequences.

### 5.1. `securityMatcher` and `requestMatchers` Are Not the Same

`securityMatcher("/api/**")` chooses which requests **the entire `SecurityFilterChain`** applies to. `authorizeHttpRequests(auth -> auth.requestMatchers(...))` sets rules **inside the already-selected chain**.

If a chain has only `securityMatcher("/api/**")`, `/web/**` requests do not enter that chain. If you forget a trailing chain covering `/web/**`, routes can end up **unprotected by Spring Security**. Always ensure a suitable chain covers every protected endpoint, and test negative paths.

## 6. Filter Placement: Authentication, Authorization, Audit, and Response

Spring Security docs recommend ordering based on what has already happened:

| Custom Filter Kind | Must Run After What? | Risk If Wrong |
| --- | --- | --- |
| API-key authentication filter | Appropriate security context baseline and exploit protection; often after `LogoutFilter` | Missing context, broken CSRF/CORS, logout, or duplicate auth |
| Authorization/tenant check | Authentication already established; often after `AnonymousAuthenticationFilter` | Null/anonymous principal, false denials, or bypass |
| Logging/correlation | Before/after request as needed | Missing context if too early; wrong status logged if before commit |
| Response header decoration | Before response commits, or via proper wrapper | `IllegalStateException`, missing header, double-write |
| HTTP outcome metrics | When downstream completes, including exceptions/async | Miscounts before response finishes or across dispatches |
| Login success/failure handler | Inside the filter's authentication mechanism | Skipped if attached only to an MVC controller |
| Access-denied response | Through authorization manager/`AccessDeniedHandler` | Every 403 confused with bad credentials |

**Do not rely on hard-coded filter index numbers across major versions.** Use standard DSLs like `httpBasic()`, `formLogin()`, `oauth2ResourceServer()`, or `addFilterBefore/After(..., KnownFilter.class)` with an appropriate anchor.

### 6.1. `addFilterBefore`, `addFilterAfter`, `addFilterAt`

```java
http
    .addFilterBefore(myFilter, UsernamePasswordAuthenticationFilter.class);
// Or:
http
    .addFilterAfter(myFilter, LogoutFilter.class);
```

These are **two alternative examples**; do not call both on the same instance without reason. `addFilterAt(custom, BasicAuthenticationFilter.class)` places a filter at that filter's slot; **do not simultaneously enable `httpBasic()` and manually add another `BasicAuthenticationFilter` at the same slot**. Spring Security 7 documentation notes such configs cause conflicts/exceptions when filters share a slot.

If you just need HTTP Basic authentication, `http.httpBasic(Customizer.withDefaults())` is enough. If replacing an implementation, check your version's API docs and disable the built-in DSL where needed; never accidentally stack two mechanisms.

## 7. `Authentication` Result and HTTP Response Are Two Different Things

A manager may return a valid `Authentication`, yet the request can still fail afterward:

```text
ApiKeyFilter
    |
    | AuthenticationManager.authenticate(...) -> SUCCESS
    | SecurityContextHolder <- authenticated principal
    v
AnonymousAuthenticationFilter  (usually skipped if already authenticated)
    |
    v
AuthorizationFilter
    |
    | hasAuthority("API_READ")?
    |   YES -> Controller
    |   NO  -> AccessDeniedException
    v
ExceptionTranslationFilter / AccessDeniedHandler
    |
    v
HTTP 200 or 403
```

**Authentication** success is not **authorization** success. A filter logging "authenticated principal=alice" before `chain.doFilter` followed by a 403 **does not prove the filter was called twice**.

Similarly, default Spring Security form login can return an HTTP 302 redirect after valid credentials. An API client expecting 200 JSON may mistake it for an "authentication failure", when it is actually a **default success handler** mismatching the API contract.

Three boundaries:

1. **Authentication filter/provider:** verifies credentials and produces an authenticated principal.
2. **`AuthorizationManager`/`AuthorizationFilter`:** decides whether the principal can access the resource/action.
3. **`AuthenticationSuccessHandler`/`FailureHandler`/`AuthenticationEntryPoint`/`AccessDeniedHandler`:** determines the HTTP response at the matching stage.

Do not build one monolithic custom filter doing everything: checking passwords, assigning roles, writing to the DB, formatting JSON, setting cookies, redirecting, and logging outcomes in one method when standard Spring Security DSL pieces apply.

## 8. Results Handled in the Wrong Place: Five Especially Dangerous Bugs

### 8.1. Writing a Response and Still Calling `chain`

```java
// WRONG: response sent an error yet downstream still executes.
if (invalidCredential) {
    response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
}
chain.doFilter(request, response);
```

Right approach:

```java
if (invalidCredential) {
    response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
    return; // STOP, do not let request reach controller.
}
chain.doFilter(request, response);
```

Likewise, if the controller already wrote JSON/the response stream, an outer filter attempting `sendRedirect(...)` after `chain.doFilter` can hit `response.isCommitted() == true`. Fix it in the **handler responsible for the response** or use a properly designed wrapper instead of writing arbitrarily.

### 8.2. Calling `chain` Twice

```java
// WRONG: can cause downstream/Controller to be invoked twice.
chain.doFilter(request, response);
if (shouldContinueAgain) {
    chain.doFilter(request, response);
}
```

A filter must call `chain.doFilter` **once on the continue branch**; if rejecting, **do not call it**. Calling it multiple times causes duplicate side effects, broken transaction integrity, and already-committed response errors.

### 8.3. Catching Downstream Errors and Turning Them Into 401

```java
// WRONG: catch wraps the downstream controller and authorization too.
try {
    Authentication result = manager.authenticate(token);
    SecurityContextHolder.getContext()
        .setAuthentication(result);
    chain.doFilter(request, response);
} catch (AuthenticationException ex) {
    response.sendError(401);
}
```

If downstream throws `AuthenticationException` or another handler processes errors, a broad catch turns failures from **the entire chain** into "bad API key", even after the response is committed. Scope the catch strictly around **manager invocation**:

```java
Authentication accepted;
try {
    accepted = manager.authenticate(token);
} catch (AuthenticationException ex) {
    response.sendError(401);
    return;
}

SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(accepted);
SecurityContextHolder.setContext(context);

try {
    chain.doFilter(request, response);
} finally {
    SecurityContextHolder.clearContext();
}
```

This is an excerpt inside a custom stateless authentication filter; it does not define `manager`, `token`, context repository, session strategy, success handler, or request variables. In a real app, use the complete design in Section 11.

### 8.4. Throwing `AuthenticationException` Too Early Expecting `ExceptionTranslationFilter` to Catch It

`ExceptionTranslationFilter` calls `chain.doFilter(...)` and catches exceptions thrown **downstream**. If a custom authentication filter sits **before** it and lets an exception escape uncaught, the exception is not translated to 401 as hoped; it can become a Servlet 500.

**Proper handling:** the custom authentication filter catches `AuthenticationException` from `AuthenticationManager` and invokes the appropriate failure handler/entry point, or uses standard DSL mechanisms. For custom authorization checks, prefer `AuthorizationManager` ordered after authentication and compatible with `ExceptionTranslationFilter`.

Never catch `Exception` and return 401 for everything: programming bugs, DB outages, serialization failures, and `NullPointerException` do not mean invalid credentials.

### 8.5. Setting `SecurityContext` Without Saving When Sessions Are Wanted

Spring Security 6.x uses `SecurityContextHolderFilter` with **explicit save**. If a custom login filter wants session-based authentication across subsequent requests, it cannot just do:

```java
SecurityContextHolder.getContext().setAuthentication(accepted);
// response returns 200, yet the next request may be anonymous again.
```

You must call `SecurityContextRepository.saveContext(...)` with the designed session strategy and lifecycle, or use standard authentication filters like `formLogin`. For stateless API keys, **do not** store into `HttpSession` just to skip authenticating the next request.

**Do not turn a missing `saveContext` into "filter ran twice"**. The symptoms differ: request A authenticates cleanly while request B becomes anonymous, even though request A ran the filter only once.

## 9. Distinguishing HTTP Statuses and Responsible Handlers

| Situation | Where It Happens | Component That Should Handle It |
| --- | --- | --- |
| `POST /login` wrong password, valid CSRF | `UsernamePasswordAuthenticationFilter` tries auth and fails | `AuthenticationFailureHandler` |
| Anonymous `GET /web/profile` | Authorization requires authentication | `AuthenticationEntryPoint` (browser may redirect to login) |
| `GET /api/private` missing API key | Authorization or authentication filter | Entry point / custom auth rejection with 401 contract |
| `GET /admin` logged in yet lacking role | `AuthorizationFilter` | `AccessDeniedHandler`, usually 403 |
| `POST /login` missing CSRF | `CsrfFilter` | CSRF/access-denied handling, usually 403 |
| Bad JSON input in controller | MVC input binding | `@ControllerAdvice`/MVC exception resolution |
| OAuth2 callback invalid state | OAuth2 authentication filter | OAuth2 failure handler |
| Invalid Bearer token | Resource server bearer filter | Bearer challenge, usually 401 `WWW-Authenticate` |
| CORS preflight rejected | CORS processor | CORS response, not login failure |
| Exception in custom filter before `ExceptionTranslationFilter` | Custom filter | Catch `AuthException` cleanly and send matching response/entry point |

### 9.1. `AuthenticationFailureHandler` Does Not Catch Every 401

`formLogin().failureHandler(...)` is bound to the form authentication mechanism. It does not automatically run when:
- an unauthenticated user hits a protected resource;
- a JWT bearer signature is invalid on a resource server;
- a CSRF token is missing on login;
- a controller throws a validation exception;
- a custom API-key filter handles another request.

### 9.2. `AuthenticationSuccessHandler` Is Not Called in Place of a Controller

A successful form login can enter `AuthenticationSuccessHandler` and redirect to a saved request. If a frontend expects JSON, configure an appropriate handler. Do not call `chain.doFilter(...)` after the success handler already sent a response/redirect if login is complete. For a machine-to-machine API-key filter, interactive login redirects are normally unnecessary; the filter sets `Authentication` and **lets the main request continue** so authorization/controller can run.

**Choose based on request type and threat model** rather than using the same HTML handler for all clients.

## 10. Distinguishing Double Registration From CORS, Frontend Retries, and Dispatches

### 10.1. CORS Preflight Is a Separate Request

The browser may send:

```http
OPTIONS /api/items HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
```

And only afterward send:

```http
POST /api/items HTTP/1.1
Origin: https://app.example.com
Authorization: Bearer <redacted-token>
Content-Type: application/json

{"name":"item"}
```

These are **two different HTTP requests**. Preflight is not "API key filter ran twice for POST"; if a custom filter demands the main request's cookie/header on `OPTIONS`, it can return 401 and the browser reports a CORS error.

Configure `http.cors(...)` in proper order with an origin allowlist and dedicated preflight handling. **Never disable authentication for main requests** just to let `OPTIONS` pass. CORS replaces neither authentication nor CSRF.

### 10.2. Redirects Spawn Subsequent Requests

Typical form login:
```text
POST /login -> 302 Location: /web/profile
GET  /web/profile -> 200
```

One login click generates two requests. Filter logs on both POST and GET may be normal even though the user clicked once. Use method/path/request ID to tell them apart.

### 10.3. HTTP Retries

Clients/gateways may retry on timeouts/502/network failures. If the request has side effects, two real requests can execute twice. A filter is not the sole place for idempotency; business logic needs idempotency keys, unique constraints, or transactional design. Never "skip authentication" on retries just because an idempotency key appeared before.

### 10.4. Error Dispatches

A controller throwing an error or calling `sendError` can trigger an `ERROR` dispatch to `/error`. If a logging filter runs across multiple dispatcher types, two logs with the same correlation ID can reflect one request lifecycle with multiple dispatches. Check `jakarta.servlet.error.request_uri` and dispatcher type before concluding there is a filter loop.

## 11. Spring Boot 3.5.16 / Java 17 Example: Registering a Filter in Exactly One Place

This example intentionally provides two independent authentication paths:

- `/api/**` uses a stateless **API key header**. `DemoApiKeyFilter` is created **locally** inside `SecurityFilterChain`, **not** annotated `@Component` and not declared as a `@Bean`.
- `/web/**` uses **form login + session** with a demo user; it never passes through the API-key filter.
- `/health` is public in the web chain.
- `FilterProbe` is a **counter-only bean**, not implementing `Filter`, so MockMvc can verify each simple request enters `doFilterInternal` once.
- The filter catches errors only around `manager.authenticate(...)`, never wrapping downstream.
- A 401 response is written **once** and returns; when authentication succeeds, the filter sets context and invokes `chain` **once**.
- Authorization lives in `authorizeHttpRequests`; the filter never decides roles itself.

API key and password values are injected via environment variables for **local lab** use only. No production secrets appear in source code.

### 11.1. Project Structure

```text
filter-diagnostics-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/filters/FilterDiagnosticsApplication.java
    │   └── resources/application.yml
    └── test/
        └── java/demo/filters/FilterDiagnosticsApplicationTests.java
```

### 11.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>filter-diagnostics-demo</artifactId>
    <version>1.0.0</version>
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
```

### 11.3. `application.yml`

```yaml
server:
  port: 8080

app:
  demo:
    api-key: "${DEMO_API_KEY}"
    login-password: "${DEMO_LOGIN_PASSWORD}"
```

There are no default credentials. The API key must be **64 lowercase hex characters** generated by a CSPRNG. The lab password should be a sufficiently long string reused nowhere else. Missing variables fail startup rather than silently enabling a bypass.

### 11.4. `FilterDiagnosticsApplication.java`

```java
package demo.filters;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Principal;
import java.util.Collection;
import java.util.Enumeration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.logout.LogoutFilter;
import org.springframework.security.web.context.NullSecurityContextRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;

@SpringBootApplication
public class FilterDiagnosticsApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterDiagnosticsApplication.class, args);
    }
}

/** Does not implement Filter, so Boot does not auto-register it in the container. */
final class FilterProbe {
    private final AtomicInteger executions = new AtomicInteger();

    void markExecution() {
        executions.incrementAndGet();
    }

    int count() {
        return executions.get();
    }
}

/** Dedicated Authentication: holds only the API key before verification. */
final class DemoApiKeyToken extends AbstractAuthenticationToken {
    private final String principal;
    private String rawKey;

    private DemoApiKeyToken(
            String principal,
            String rawKey,
            Collection<? extends GrantedAuthority> roles,
            boolean authenticated) {
        super(roles);
        this.principal = principal;
        this.rawKey = rawKey;
        super.setAuthenticated(authenticated);
    }

    static DemoApiKeyToken requested(String rawKey) {
        return new DemoApiKeyToken(null, rawKey, null, false);
    }

    static DemoApiKeyToken verified() {
        return new DemoApiKeyToken(
            "integration-reader", null,
            List.of(new SimpleGrantedAuthority("API_READ")), true);
    }

    @Override
    public String getPrincipal() {
        return principal;
    }

    @Override
    public Object getCredentials() {
        return rawKey;
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        rawKey = null;
    }

    @Override
    public void setAuthenticated(boolean authenticated) {
        if (authenticated) {
            throw new IllegalArgumentException(
                "Use verified() after checking the key");
        }
        super.setAuthenticated(false);
    }
}

/** Verifies only high-entropy keys; never takes roles from the client. */
final class DemoApiKeyProvider implements AuthenticationProvider {
    private static final Pattern KEY_FORMAT =
        Pattern.compile("[0-9a-f]{64}");

    private final byte[] expectedHash;

    DemoApiKeyProvider(String secret) {
        if (secret == null ||
                !KEY_FORMAT.matcher(secret).matches()) {
            throw new IllegalArgumentException(
                "DEMO_API_KEY must be 64 lowercase hex chars");
        }
        this.expectedHash = sha256(secret);
    }

    @Override
    public boolean supports(Class<?> type) {
        return DemoApiKeyToken.class.isAssignableFrom(type);
    }

    @Override
    public Authentication authenticate(Authentication request)
            throws AuthenticationException {
        if (!(request instanceof DemoApiKeyToken token)
                || token.isAuthenticated()) {
            return null;
        }

        Object value = token.getCredentials();

        if (!(value instanceof String key)
                || !KEY_FORMAT.matcher(key).matches()
                || !MessageDigest.isEqual(
                    expectedHash, sha256(key))) {
            throw new BadCredentialsException("Invalid API key");
        }

        return DemoApiKeyToken.verified();
    }

    private static byte[] sha256(String text) {
        try {
            return MessageDigest.getInstance("SHA-256")
                .digest(text.getBytes(StandardCharsets.UTF_8));
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException("Missing SHA-256", ex);
        }
    }
}

/**
 * Custom API authentication filter, living solely in the API security chain.
 * No @Component, no @Bean Filter, no container auto-registration.
 */
final class DemoApiKeyFilter extends OncePerRequestFilter {
    private final AuthenticationManager manager;
    private final FilterProbe probe;

    DemoApiKeyFilter(AuthenticationManager manager, FilterProbe probe) {
        this.manager = manager;
        this.probe = probe;
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {

        probe.markExecution();

        Enumeration<String> headers =
            request.getHeaders("X-Demo-Key");

        // Let authorization/entry point return 401 when the key is missing.
        if (!headers.hasMoreElements()) {
            chain.doFilter(request, response);
            return;
        }

        String rawKey = headers.nextElement();

        if (headers.hasMoreElements()) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        Authentication accepted;

        try {
            // Catch ONLY manager's AuthenticationException.
            // Do NOT wrap chain.doFilter() in this try/catch!
            accepted = manager.authenticate(
                DemoApiKeyToken.requested(rawKey));
        } catch (AuthenticationException failed) {
            response.sendError(HttpServletResponse.SC_UNAUTHORIZED);
            return;
        }

        SecurityContext context =
            SecurityContextHolder.createEmptyContext();
        context.setAuthentication(accepted);
        SecurityContextHolder.setContext(context);

        try {
            // Once only after authentication succeeds.
            chain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    FilterProbe filterProbe() {
        return new FilterProbe();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(
            PasswordEncoder encoder,
            @Value("${app.demo.login-password}") String password) {
        if (password == null || password.length() < 20) {
            throw new IllegalStateException(
                "DEMO_LOGIN_PASSWORD is missing or short");
        }
        UserDetails user = User.withUsername("learner")
            .password(encoder.encode(password))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(user);
    }

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(
            HttpSecurity http,
            FilterProbe probe,
            @Value("${app.demo.api-key}") String apiKey)
            throws Exception {

        AuthenticationManager apiManager =
            new ProviderManager(
                List.of(new DemoApiKeyProvider(apiKey)));

        // Local filter: Boot does not auto-register it in the servlet container.
        DemoApiKeyFilter keyFilter =
            new DemoApiKeyFilter(apiManager, probe);

        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(s -> s.sessionCreationPolicy(
                SessionCreationPolicy.STATELESS))
            .securityContext(s -> s.securityContextRepository(
                new NullSecurityContextRepository()))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/whoami")
                    .hasAuthority("API_READ")
                .anyRequest().denyAll())
            .exceptionHandling(e -> e.authenticationEntryPoint(
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            // Auth filter after LogoutFilter per position recommended
            // by Spring Security docs.
            .addFilterAfter(keyFilter, LogoutFilter.class)
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain browserChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers("/web/**").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}

@RestController
class DemoEndpoints {

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "up");
    }

    @GetMapping("/api/whoami")
    Map<String, String> apiWhoami(Principal principal) {
        return Map.of(
            "principal", principal.getName(),
            "mechanism", "api-key");
    }

    @GetMapping("/web/profile")
    Map<String, String> webProfile(Principal principal) {
        return Map.of(
            "principal", principal.getName(),
            "mechanism", "form-login");
    }
}
```

### 11.5. Why Is This Configuration in the Right Place?

1. `DemoApiKeyFilter` is constructed with `new ...` inside `apiChain`, not a bean; Boot **does not auto-register** it in the container.
2. `@Order(1)` + `securityMatcher("/api/**")` routes only machine endpoints to the API chain.
3. `@Order(2)` protects web endpoints with session form login, without applying the API-key filter to `/login`.
4. `FilterProbe` is a plain bean holding only an `AtomicInteger`, so it is not servlet-auto-registered.
5. API-key authentication failures are caught inside the filter and **return**. It does not throw `BadCredentialsException` early past the filter hoping `ExceptionTranslationFilter` catches it.
6. Form login's `AuthenticationFailureHandler` is not needed for API keys. The API config returns 401; form login gets Spring-managed success/failure redirects.
7. `SecurityContext` is created fresh for a valid key and cleared in `finally` after downstream. The API chain uses `NullSecurityContextRepository` and a stateless session policy.
8. Business authorization is `hasAuthority("API_READ")`; the provider assigns authorities server-side, never from headers.
9. `csrf.disable()` applies only to the **stateless API-key header chain** that uses no browser auto-attached session credentials. The browser chain keeps default CSRF.
10. The code never logs raw API keys and never returns secrets in JSON. The demo uses SHA-256 digests and `MessageDigest.isEqual` on high-entropy keys; production needs key IDs/rotation/revocation stores and rate limits.

**Limitations:** the example has no database storing key verifiers, does not support multiple keys, expiration, or tenants, and does not persist audit logs. Never deploy the demo key into production.

## 12. Running Locally and Observing the Path

Prepare Maven, Java 17+, and OpenSSL; generate random keys for a **local lab**:

```bash
export DEMO_API_KEY="$(openssl rand -hex 32)"
export DEMO_LOGIN_PASSWORD="$(openssl rand -hex 24)"
mvn spring-boot:run
```

If using PowerShell on Windows, replace the `export` syntax with `$env:...` and an appropriate secret generator. Never take screenshots, paste keys into tickets, or commit them to Git.

Test the API:

```bash
curl -i http://localhost:8080/health

curl -i http://localhost:8080/api/whoami \
  -H "X-Demo-Key: $DEMO_API_KEY"

curl -i http://localhost:8080/api/whoami

curl -i http://localhost:8080/api/whoami \
  -H "X-Demo-Key: invalid"
```

Expectations:

| Request | Authentication | Outcome |
| --- | --- | --- |
| `GET /health` | Not required | 200 + JSON `{"status":"up"}` |
| `GET /api/whoami` with right key | API provider succeeds | 200 + `{"principal":"integration-reader","mechanism":"api-key"}` |
| `GET /api/whoami` missing header | Filter passes chain onward; authorization requires authenticated | 401 |
| `GET /api/whoami` wrong key | Provider `BadCredentialsException`, filter returns 401 and stops | 401 |
| `GET /web/profile` anonymous | Web chain + entry point | 302 to login page |
| Browser login `learner` with lab password then `GET /web/profile` | Form login/session | 200, JSON user `learner` |

Requests to `/health` and `/web/**` themselves **never enter `DemoApiKeyFilter`**, because the API filter belongs solely to the API chain. On each simple `GET /api/whoami` in a single `REQUEST` dispatch, `probe.markExecution()` is expected to increment by **1**; two real HTTP requests increment it by **2**.

**Caution:** the app uses Spring Security form login and a random env password. For browser login, the password lives only in your lab terminal. Never place it in URL query strings or logs. In automated tests, use a fixed synthetic test fixture password, not a real secret.

## 13. MockMvc: Testing Single Filter Execution for a Single Simple Request

Create `src/test/java/demo/filters/FilterDiagnosticsApplicationTests.java`:

```java
package demo.filters;

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

@SpringBootTest(properties = {
    "app.demo.api-key=" +
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "app.demo.login-password=synthetic-local-test-password-123456"
})
@AutoConfigureMockMvc
class FilterDiagnosticsApplicationTests {

    private static final String VALID_KEY =
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

    @Autowired MockMvc mvc;
    @Autowired FilterProbe probe;

    @Test
    void validApiKeyIsAuthenticatedExactlyOnceForSingleRequest()
            throws Exception {
        int before = probe.count();

        mvc.perform(get("/api/whoami")
                .header("X-Demo-Key", VALID_KEY))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal")
                .value("integration-reader"));

        assertThat(probe.count()).isEqualTo(before + 1);
    }

    @Test
    void twoApiRequestsAreNotAFilterDuplicate() throws Exception {
        int before = probe.count();

        mvc.perform(get("/api/whoami")
                .header("X-Demo-Key", VALID_KEY))
            .andExpect(status().isOk());

        mvc.perform(get("/api/whoami")
                .header("X-Demo-Key", VALID_KEY))
            .andExpect(status().isOk());

        assertThat(probe.count()).isEqualTo(before + 2);
    }

    @Test
    void missingKeyIsRejectedByApiChain() throws Exception {
        int before = probe.count();

        mvc.perform(get("/api/whoami"))
            .andExpect(status().isUnauthorized());

        assertThat(probe.count()).isEqualTo(before + 1);
    }

    @Test
    void invalidKeyReturns401WithoutEnteringController()
            throws Exception {
        int before = probe.count();

        mvc.perform(get("/api/whoami")
                .header("X-Demo-Key", "not-a-valid-key"))
            .andExpect(status().isUnauthorized());

        assertThat(probe.count()).isEqualTo(before + 1);
    }

    @Test
    void webRequestDoesNotUseApiKeyFilter() throws Exception {
        int before = probe.count();

        mvc.perform(get("/web/profile"))
            .andExpect(status().is3xxRedirection());

        assertThat(probe.count()).isEqualTo(before);
    }

    @Test
    void formLoginAndFollowingSessionGetUseWebChain()
            throws Exception {
        int before = probe.count();

        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password",
                    "synthetic-local-test-password-123456"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
            login.getRequest().getSession(false);

        assertThat(session).isNotNull();

        mvc.perform(get("/web/profile").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.principal").value("learner"));

        assertThat(probe.count()).isEqualTo(before);
    }
}
```

Run:

```bash
mvn test
```

Expect **6 passing tests** given the proper environment and dependencies. This is a **static** check of the example, not a claim that Maven was executed in this workspace task.

**Important:** MockMvc simulates the Servlet request/filter chain inside the Spring test context. It is **not sufficient to prove** a real-world embedded container did not auto-register the same filter bean. In our example, the API filter is not a bean, eliminating Boot auto-registration risk by design. To test a real app that uses filter beans, add an integration test starting an embedded server and inspecting actual filter registrations.

**Counter limitation:** `FilterProbe` increments inside `doFilterInternal`. If the same `OncePerRequestFilter` instance is invoked twice through **nested** registrations, the already-filtered marker can make `doFilterInternal` run only once while **two registrations** still exist. Therefore a green counter **does not replace** checking container registrations.

If tests run in parallel, `probe` is a shared bean; before/after delta comparisons can be affected by concurrent tests. This fixture assumes sequential test execution, or requires a scoped probe/request-ID collector.

## 14. Integration Diagnostics: Checking Instances, Filter Registrations, and Dispatches

A production-safe debugging plan observes **each layer**, not just error messages:

1. **Network:** how many HTTP requests? `OPTIONS`/`POST`, redirects, retries? Do correlation IDs differ?
2. **Servlet container:** does the filter registration list contain an app filter bean outside `springSecurityFilterChain`?
3. **Spring Security:** how many `SecurityFilterChain`s exist, which matcher selected the request, and what is the filter list inside that chain?
4. **Custom filter:** filter instance identity, dispatcher type, request method/path, timing before/after `chain`.
5. **Authentication:** was the manager/provider called once or multiple times? Did auth succeed yet lack an authority?
6. **Authorization:** which role/authority does the resource need? Where was the exception thrown?
7. **HTTP response:** final status, when the response committed, and who called `sendError/sendRedirect/getWriter`?
8. **Async/error:** was the request re-dispatched under `ERROR/ASYNC`?
9. **Runtime:** do all app nodes share identical registrations/configs/versions?
10. **Client:** does the frontend double-submit, retry, hold stale cookies, or hit token-refresh races?

### 14.1. Controlled Logging

Locally/in dev, you can try:

```yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
```

Depending on the Spring Security release, TRACE can show the filter list and invocations. Enable only in environments **that do not log raw credentials**; lower log levels once done. Never turn on full HTTP wire tracing in production.

**Logs should include:** server-generated request ID, chain name/matcher, method, sanitized path, dispatcher type, filter class/identity, and event category. **Never log:** `Authorization`, `Cookie`, `X-API-Key`, passwords, raw tokens, CSRF tokens, session IDs, or full principal objects.

**Illustrative** log example, not a Spring default:

```text
request_id=req-319 method=GET path=/api/whoami dispatcher=REQUEST
chain=apiKey filter=DemoApiKeyFilter instance=0x5f11 phase=before
request_id=req-319 auth=SUCCESS principal_ref=integration-reader
request_id=req-319 phase=after status=200 committed=true
```

If the same request ID shows **two instance IDs**, suspect two instances of the same type. If one instance ID shows **two registration paths**, inspect container registrations and `FilterChainProxy`. If the same correlation ID shows different dispatcher types, analyze the error/async lifecycle. If there are two **different request IDs**, it may be a client/gateway retry.

### 14.2. Listing Servlet Filter Registrations

In a managed test/application, you can inspect `ServletContext.getFilterRegistrations()`:

```java
// Excerpt running inside a Servlet application/integration test.
Map<String, ? extends FilterRegistration> registrations =
    servletContext.getFilterRegistrations();

registrations.forEach((name, registration) ->
    logger.debug("containerFilterName={} className={}",
        name, registration.getClassName()));
```

Imports: `jakarta.servlet.FilterRegistration`, `jakarta.servlet.ServletContext`, `java.util.Map`. Note that `ServletContext` registrations show **container registrations**, while Spring Security's filter list comes from `FilterChainProxy`; the two lists are **not identical**. Do not interpret every container filter as a duplicate.

In integration tests for apps with filter beans, assert that the filter is **absent** from container registrations when you intentionally disabled auto-registration.

### 14.3. Controlled Inspection of `FilterChainProxy`

```java
// Excerpt inside an integration test / internal diagnostic tool.
@Autowired
FilterChainProxy proxy;

@Test
void listSecurityChainsForDiagnostics() {
    for (SecurityFilterChain chain : proxy.getFilterChains()) {
        System.out.println(chain);
    }
}
```

Imports: `org.springframework.security.web.FilterChainProxy` and `SecurityFilterChain`. This snippet is a **separate excerpt**, not part of the main test file. Never expose the security configuration list via a public endpoint.

### 14.4. Logging Before and After `chain` Properly

```java
long start = System.nanoTime();
try {
    logger.debug("filter before path={} dispatcher={}",
        request.getServletPath(), request.getDispatcherType());
    chain.doFilter(request, response);
} finally {
    logger.debug("filter after status={} committed={} tookNs={}",
        response.getStatus(), response.isCommitted(),
        System.nanoTime() - start);
}
```

The snippet above works well for synchronous requests. With async dispatches, the initial `chain.doFilter` can return before the async task's response finishes; to measure the full lifecycle, use Servlet async listeners/observability integrations. Do not treat the "after" log as confirmation the response was sent to the client in all cases.

## 15. Diagnostic Table: Symptom → Root Cause → Proper Fix

| Symptom | Likely Cause | Proper Fix |
| --- | --- | --- |
| Custom filter logs twice on one `REQUEST` | `@Component` + `addFilter...` or two instances | Single registration owner; local filter or disable Boot registration |
| Filter logs once yet context is wrong | Filter actually runs outside Security chain; already-filtered marker hides double registration | Inspect container registrations and security ordering |
| Filter runs on `/login` even though meant only for API keys | App-wide servlet container auto-registration | Create local filter inside API chain or disable registration |
| Filter does not run on `/api/**` | Catch-all `@Order(1)` chain shadows API chain | Order specific chain first, test matchers |
| Right API key yet 403 | Missing authority/tenant permission | Check authorization; do not confuse with authentication |
| Right API key yet next request is anonymous | Stateless or context not saved | If sessions wanted, use explicit-save repository; if stateless, authenticate per request |
| Missing key returns 302 `/login` HTML | Form-login EntryPoint applied to API chain | JSON/HTTP 401 entry point or right API chain |
| Invalid token causes 500 | Exception escaped custom filter before translation | Catch auth exceptions around manager or use standard filter |
| `POST /login` wrong password returns 403 | Missing/bad CSRF before reaching login filter | Fetch/attach CSRF token; do not edit `FailureHandler` |
| CORS preflight `OPTIONS` returns 401 | Custom filter or auth blocks `OPTIONS` before CORS | Integrate CORS in right order without dropping real request protection |
| Controller runs twice | `chain.doFilter` called twice or client retry | Review control flow + request IDs |
| JSON response followed by redirect | Handler wrote response and code continued | Return immediately; single response owner |
| `IllegalStateException: response already committed` | Writing response too late after downstream | Decide response before commit or use designed wrapper |
| Filter runs again on `/error` | `ERROR` dispatch, `sendError` | Check dispatcher types and `OncePerRequestFilter` hooks |
| Filter runs again on async completion | `ASYNC` redispatch | Define `shouldNotFilterAsyncDispatch`/dispatcher mapping |
| One login emits multiple auth events | Multiple providers/parent managers, token reauth, client retries | Trace manager/outcomes; do not assume filter duplication |
| AOP/metrics log twice | Two instrumentation paths or duplicated events | Distinguish filter invocation from metrics instrumentation |
| Filter misses session after login | Chain order/`NullSecurityContextRepository` wrong scope | Separate stateless API chain from stateful form chain |
| `TenantFilter` sees no principal | Placed before authentication | Move after `AnonymousAuthenticationFilter` or to authorization layer |
| Service throws `AccessDenied` yet gets 500 | Exception thrown before `ExceptionTranslationFilter` or outside security chain | Place policy downstream/`AuthorizationManager` or proper handler |
| Dev tests pass, production fails | Embedded container registration, proxy path, error dispatch, Boot config differences | Embedded-server integration tests, audit runtime setup |

## 16. When to Use a Filter vs a Framework Extension?

**A custom Servlet filter fits** work truly tied to request transport/authentication, such as reading an API-key header and invoking `AuthenticationManager`. However, not all logic belongs in a filter.

| Need | Preferred Extension |
| --- | --- |
| Reading username/password and browser login | `formLogin()` / `UsernamePasswordAuthenticationFilter` |
| HTTP Basic | `httpBasic()` |
| Bearer JWT | `oauth2ResourceServer().jwt()`, `BearerTokenAuthenticationFilter` |
| OAuth2/OIDC login | `oauth2Login()` |
| Custom credential verification | `AuthenticationProvider` + appropriate filter/manager |
| Per-resource role/permission checks | `AuthorizationManager` / `authorizeHttpRequests` / method security |
| Triggering login when anonymous | `AuthenticationEntryPoint` |
| Responding to failed login attempts | `AuthenticationFailureHandler` |
| Responding to insufficient privileges post-login | `AccessDeniedHandler` |
| Handling JSON validation errors in controllers | `@ControllerAdvice` / MVC exception resolver |
| Auditing after authentication outcomes | `AuthenticationEventPublisher` / appropriate listener |
| Observing HTTP request lifecycle | Servlet filter/observability + async handling |

Fewer custom filters mean fewer places for duplicate registration or misordered result handling. Still, **never replace credential verification by reading a header and granting roles**. When using a custom filter, keep a trusted verifier/provider.

## 17. Security Requirements for the Fix

A fix that "stops running twice" **is insufficient** if it causes any of these side effects:

1. **Credentials are no longer checked** on some endpoints due to missing matcher coverage.
2. Turning 401 into 200 by skipping `chain.doFilter` or adding broad `permitAll`.
3. Disabling CSRF on the `formLogin` chain to fix `POST /login`.
4. Logging API keys/plaintext tokens to debug.
5. Failing to clear `SecurityContextHolder` on thread pools after custom stateless authentication.
6. Saving API-key `Authentication` into sessions when policy requires stateless per-request revocation.
7. Letting clients supply roles/authorities directly in headers.
8. Bypassing `AccessDeniedHandler` or catching every exception to return "bad key".
9. Moving security filters outside the chain to dodge CORS preflight errors.
10. Using a homegrown `ThreadLocal<Boolean> alreadyProcessed` without clearing in `finally`, leaking request state across users.
11. Setting a global static boolean to "run only once" per JVM; after the first request, others bypass auth.
12. Emitting 2 response bodies on one request because code continued after error/redirect.

**Minimum negative tests:** bad key → 401; missing key → 401; valid key lacking privilege → 403; anonymous web → login redirect; valid web login → reaches protected endpoint; no path outside policy returns 200.

## 18. Safe Ordered Fix Workflow

### Step 1 — Gather Evidence

Record one real request with a distinct ID, method, normalized path, dispatcher type, and status. Verify how many requests the frontend sent, and whether `OPTIONS`/redirects/retries/error dispatches occurred. Never log secrets.

### Step 2 — Check Filter Registrations

Find filters that are `@Component`/`@Bean implements Filter` and also passed to `addFilterBefore/After/At`. If found, choose **one owner**: a local filter in the chain or disable auto-registration with `FilterRegistrationBean.setEnabled(false)`. Never tweak formatting/timeouts to mask it.

### Step 3 — Identify the Selected `SecurityFilterChain`

Inspect `@Order`, `securityMatcher`, and fallback chains. Ensure specific API chains precede the web catch-all; leave no protected endpoint without a chain.

### Step 4 — Verify Relative Placement

Auth filters belong after appropriate context/exploit-protection setup; authorization/tenant checks belong after authentication completes. Never place auth logic inside MVC controllers when Spring Security providers apply.

### Step 5 — Verify Control Flow

Each branch:
- If rejecting: write one response per contract and **return**.
- If accepting: set context properly, call `chain.doFilter` **exactly once**, clean up in `finally`.
- Catch `AuthenticationException` strictly around authentication work.
- Never write more to the response after downstream commits.

### Step 6 — Verify Appropriate Persistence

Stateful login: session strategy and `SecurityContextRepository`. Stateless API: authenticate each request independently, never letting one request's context survive to the next.

### Step 7 — Write Regression Tests

Unit tests for provider/filter, MockMvc for 401/403/login/chains; embedded-container integration tests for auto-registration; browser E2E for preflights, redirects, cookies, and retries; load tests for async/concurrency. Use negative-path tests to prove removing duplication opened no bypass.

### Step 8 — Monitor During Rollout

Track provider call counts, 401/403/5xx rates, duplicate request IDs, auth latency, filter invocations, and session anomalies. Compare before/after using **HTTP request counts**, not just log volume.

## 19. Self-Check Questions

1. Why can a `@Component` filter + `addFilterAfter` create duplicate registration?
2. If you use `OncePerRequestFilter`, can you skip checking container registration? **No.**
3. When both `OPTIONS` and `POST` appear, is that one request processed twice? **No.**
4. Does `FilterChainProxy` execute every matching `SecurityFilterChain`? **No, it picks the first matching chain.**
5. How does `securityMatcher` differ from `authorizeHttpRequests.requestMatchers`?
6. Why can a catch block around `chain.doFilter` turn downstream errors into "bad credentials"?
7. Why should you usually `return` after `response.sendError(401)`?
8. What happens if you call `chain.doFilter` twice on the success branch?
9. Does a successful `Authentication` guarantee the endpoint returns 200? **No; authorization can still deny.**
10. Why can a filter throwing `AuthException` before `ExceptionTranslationFilter` cause a 500?
11. Does a `POST /login` missing CSRF belong to `AuthenticationFailureHandler`? **Normally no.**
12. When a user has a valid session, must `GET /web/profile` re-invoke the password provider? **Normally no.**
13. Why must a stateless API-key filter clear `SecurityContext` in `finally`?
14. When should `FilterRegistrationBean.setEnabled(false)` be used?
15. Is one log on `REQUEST` and one on `ERROR` guaranteed to be a duplicate filter bug?
16. Does MockMvc counting `doFilterInternal = 1` prove an embedded container did not auto-register the filter? **No.**
17. Which test detects a catch-all chain ordered ahead of an API chain?
18. Why does form login's success callback differ from letting an API-key request continue to the controller?
19. When lacking an admin role, is editing the auth filter to grant the role a valid fix? **No; check authorization policy and server-side authorities.**
20. When a frontend retries a POST request, where should idempotency live? **In the business contract/transaction, never by skipping auth in the filter.**

## 20. Official Documentation

- Spring Security 6.5 – Servlet Architecture, `FilterChainProxy`, custom filters, and registration: https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html
- Spring Security – Current Servlet Architecture: https://docs.spring.io/spring-security/reference/servlet/architecture.html
- Spring Framework 6.2 – `OncePerRequestFilter` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html
- Spring Security – Servlet Authentication Architecture: https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html
- Spring Security – Form Login: https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html
- Spring Security – SecurityContext Persistence: https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html
- Spring Security – CSRF: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security – CORS: https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html
- Spring Security – MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html
- Spring Boot – Servlet Web Applications and Filters: https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html
- Spring Security – `FilterChainProxy` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html
- Spring Security – `ExceptionTranslationFilter` Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html
