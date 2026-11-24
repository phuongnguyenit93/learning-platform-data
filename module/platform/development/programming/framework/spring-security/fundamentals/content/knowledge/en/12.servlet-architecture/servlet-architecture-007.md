# ExceptionTranslationFilter and Translating Security Errors into Responses

In **Spring Security on the Servlet stack**, rejecting a request and **turning that rejection into an HTTP response** are two related yet distinct responsibilities. `AuthorizationFilter` and authorization checks can throw `AccessDeniedException`; authentication components can throw `AuthenticationException`. **`ExceptionTranslationFilter`** is dedicated to translating **certain security exceptions thrown downstream of the filter** into either an authentication prompt or an access-denied response.

Once you understand this filter properly, you can explain why:

- An anonymous call to `GET /api/me` can receive **401 Unauthorized** in a REST API, or a **302 redirect to /login** in a form-login web app.
- A signed-in user lacking `ROLE_ADMIN` calling `GET /api/admin` typically receives **403 Forbidden**.
- A user with remember-me authentication accessing a resource requiring stronger authentication can be routed to **`AuthenticationEntryPoint`** for full sign-in rather than being treated as fully authenticated.
- A wrong password in `BasicAuthenticationFilter` still yields 401, yet that error **does not necessarily get caught by ExceptionTranslationFilter**: the Basic filter has its own authentication failure flow.
- A missing CSRF token can yield **403 from CsrfFilter/AccessDeniedHandler**, which does not mean every 403 status went through ExceptionTranslationFilter.
- `@ControllerAdvice` does not automatically catch exceptions thrown inside Servlet filters before `DispatcherServlet` runs.

This lesson belongs to the **Servlet Architecture** group, based on **Java 17+, Spring Boot 3, Spring Security 6.x, Spring MVC/Servlet**. We will examine the flow, decision branches, configuration code, MockMvc testing, scope boundaries, and a standalone Java 17 model. If you use Spring Security 7, Spring WebFlux, or a custom OAuth2 resource server, verify APIs and filter chains against your version/stack.

## 1. Architecture Map: Where Do Errors Arise?

```text
Client
  |
  v
Servlet container FilterChain
  |
  +-- DelegatingFilterProxy("springSecurityFilterChain")
            |
            v
       FilterChainProxy
            |
            +-- SecurityContextHolderFilter / context
            +-- CsrfFilter / HTTP Basic / form login / bearer filter...
            +-- AnonymousAuthenticationFilter
            |
            +-- ExceptionTranslationFilter
            |       |
            |       | chain.doFilter(request, response)
            |       v
            |    AuthorizationFilter
            |       |
            |       +-- If denied: throw AccessDeniedException
            |       |
            |       v
            |    DispatcherServlet
            |       |
            |       +-- HandlerMapping -> HandlerAdapter
            |       +-- Controller -> Service
            |       +-- @PreAuthorize / method security (if applicable)
            |
            +-- ExceptionTranslationFilter catches a matching exception
                    |
                    +-- AuthenticationEntryPoint
                    |       401 / WWW-Authenticate / redirect...
                    |
                    +-- AccessDeniedHandler
                            403 / error page / JSON...
```

This is a **conceptual diagram**, not an exhaustive list of every filter across every configuration. Security filter ordering and membership change with form login, HTTP Basic, JWT bearer, CSRF, sessions, multiple `SecurityFilterChain` beans, and custom filters.

The key mechanism is that `ExceptionTranslationFilter` invokes `chain.doFilter` so everything **after** it runs. If downstream throws a supported exception type, it delegates to one of two extension points. If a filter **running before it** already caught the error or wrote the response, ExceptionTranslationFilter may never get involved.

### 1.1. Three Responsibility Groups

| Component | What Does It Do? | What Does It NOT Do? |
| --- | --- | --- |
| `AuthenticationManager`/`AuthenticationProvider` | Verifies credentials, establishes Authentication | Not a universal HTTP error renderer for every request |
| `AuthorizationFilter`/`AuthorizationManager` | Decides whether request access is allowed; can deny with `AccessDeniedException` | Does not itself choose JSON bodies/redirects on failure |
| `ExceptionTranslationFilter` | Catches matching security exceptions from downstream and coordinates responses | **Does not perform authorization checks itself** |
| `AuthenticationEntryPoint` | Initiates an authentication request, e.g., 401 or redirect | Does not validate submitted passwords itself |
| `AccessDeniedHandler` | Writes the response when access is denied for an authenticated user on that branch | Does not elevate privileges or alter authorization outcomes |
| `DispatcherServlet` and `HandlerExceptionResolver` | Handles requests/exceptions within Spring MVC scope | Does not replace Servlet/Spring Security filters |

The word "Translation" accurately states its responsibility: turning error/exception outcomes at the security layer into an appropriate **HTTP response interface**. It is not a "permission-checking filter".

## 2. Two Exception Families to Recognize

### 2.1. AuthenticationException

`AuthenticationException` is Spring Security's root class for **authentication failures**, such as:

- `BadCredentialsException`: invalid login credentials.
- `AuthenticationCredentialsNotFoundException`: missing required authentication at a step needing authentication.
- `InsufficientAuthenticationException`: authentication level is insufficient for the current action.
- `DisabledException`/`LockedException`: account status issues, in corresponding flows/providers.
- Other subclasses from authentication components.

When an `AuthenticationException` is **thrown from the downstream scope wrapped by ExceptionTranslationFilter**, the filter invokes `AuthenticationEntryPoint.commence`. However, **not every BadCredentialsException passes through this filter**: `BasicAuthenticationFilter` can handle failures and call the entry point directly; `UsernamePasswordAuthenticationFilter` typically uses an authentication failure handler.

Never conclude "ExceptionTranslationFilter catches every authentication error in the application". What matters is **filter order + where the exception originates + whether a component already handled it**.

### 2.2. AccessDeniedException

`AccessDeniedException` indicates **access is denied**. `AuthorizationFilter` can throw this exception when `hasRole`, `hasAuthority`, or `denyAll` rules disallow a request. Method security can also produce an access-denied exception when `@PreAuthorize` blocks a method call and the exception propagates to the translation filter's scope.

An access-denied exception alone does not tell whether the response will be 401 or 403. You must know **whether the current identity is anonymous, remember-me, or fully authenticated**.

### 2.3. Errors Outside Those Two Families

`ExceptionTranslationFilter` is not a global catcher for every Java exception:

| Error Thrown | Typical Handling Component | Translated by ExceptionTranslationFilter by Default? |
| --- | --- | --- |
| `AuthenticationException` from downstream | Entry point | **Yes**, if the exception escapes within the wrapped chain segment |
| `AccessDeniedException` from downstream | Entry point or denied handler | **Yes**, depending on auth state |
| `BadCredentialsException` inside Basic filter | Basic authentication failure flow/entry point | Does not necessarily go through ETF |
| `MissingCsrfTokenException`/`InvalidCsrfTokenException` at CsrfFilter | CsrfFilter calls AccessDeniedHandler per config | Do not assume it goes through ETF |
| `IllegalArgumentException` from business service | MVC exception resolver or container/error flow | No, unless another mechanism translates it into a security exception |
| `MethodArgumentNotValidException` at MVC binding | `@ControllerAdvice`/MVC error handler | Not standard security translation |
| `NoHandlerFoundException`/missing mapping | MVC/container 404 behavior | No |
| `NullPointerException` or DB failure | MVC/container error processing, possibly 500 | Not turned into 401/403 just because it occurred in a request |
| Exception from a filter running **before** ETF | That filter/Servlet container or matching handler | Downstream ETF does not wrap it |

**Rule:** Never convert every exception into `AccessDeniedException` just to return HTTP 403. That masks business/infrastructure failures, corrupts monitoring, and turns 500s into misleading security responses.

## 3. Decision Tree of ExceptionTranslationFilter

Modeling the common branches:

```text
ExceptionTranslationFilter calls chain.doFilter(...)
         |
         +-- No matching exception
         |       -> normal response
         |
         +-- AuthenticationException from downstream
         |       -> startAuthentication(...)
         |             - clear SecurityContext
         |             - RequestCache.saveRequest(...) per configuration
         |             - AuthenticationEntryPoint.commence(...)
         |
         +-- AccessDeniedException from downstream
                 |
                 +-- Anonymous or remember-me?
                 |       -> InsufficientAuthenticationException
                 |       -> startAuthentication(...) / entry point
                 |
                 +-- Fully authenticated?
                         -> AccessDeniedHandler.handle(...)
```

In the Spring Security version covered here, `AuthenticationTrustResolver` identifies anonymous/remember-me identities to decide **whether full authentication should be requested**. Note that special authentication types or custom configurations can change outcomes; checking `authentication != null` alone is insufficient to classify identity.

### 3.1. AuthenticationException → AuthenticationEntryPoint

When downstream throws `AuthenticationException`, the filter starts authentication:

1. Clears `SecurityContextHolder` on the start-authentication branch.
2. Saves the original request using `RequestCache` **if the cache strategy is configured to save**.
3. Calls `AuthenticationEntryPoint.commence(request, response, exception)`.
4. The entry point chooses the response instructing the client what to do.

`AuthenticationEntryPoint` **does not only return 401**:

- REST API/HTTP Basic: typically returns HTTP 401, possibly with a `WWW-Authenticate` header.
- Browser form login: `LoginUrlAuthenticationEntryPoint` can redirect (302) to the login page.
- Bearer token resource server: response may include `WWW-Authenticate: Bearer ...` per the applicable standard.
- API with custom entry point: JSON error contract, status, and headers you explicitly define.

HTTP 401 means **valid authentication is required** (or current authentication is insufficient). Do not equate "401 always means wrong password": a request **without credentials** to a protected URL also receives 401.

### 3.2. AccessDeniedException + Anonymous → EntryPoint

For example, `GET /api/admin` from an unauthenticated client:

```text
AuthorizationFilter: hasRole("ADMIN")
              |
              +-- Anonymous lacks role -> AccessDeniedException
                        |
                        v
              ExceptionTranslationFilter
                        |
                        +-- AuthenticationTrustResolver.isAnonymous() == true
                        +-- AuthenticationEntryPoint.commence(...)
                        v
              401 in Basic API / redirect in form login
```

Even though the exception is `AccessDeniedException`, the outcome is **not necessarily 403**, because the system must give the client a chance to authenticate.

### 3.3. AccessDeniedException + Remember-Me

Remember-me authentication may be considered insufficient for a sensitive resource. On the branch where the filter detects remember-me, it can prompt for stronger authentication via the entry point rather than invoking the denied handler. That avoids confusing "an Authentication object exists" with "identity was proven at an adequate level".

Some configurations do not use remember-me or define custom step-up policies; inspect the actual `AuthenticationTrustResolver` and chain rather than hardcoding every case as a redirect.

### 3.4. AccessDeniedException + Authenticated → AccessDeniedHandler

For example, `reader` logs in validly with `ROLE_USER` yet lacks `ROLE_ADMIN`:

```text
AuthorizationFilter: hasRole("ADMIN")
              |
              +-- User authenticated, lacks ROLE_ADMIN
                        |
                        v
              AccessDeniedException
                        |
                        v
              ExceptionTranslationFilter
                        |
                        +-- AuthenticationTrustResolver: not anonymous
                        +-- not remember-me branch
                        |
                        v
              AccessDeniedHandler.handle(...)
                        |
                        v
              403 Forbidden (in sample API config)
```

**Successful authentication does not mean successful authorization.** An API can allow `reader` to access `/api/me` while denying `/api/admin`.

### 3.5. Decision Table

| Exception Caught by ETF | Principal State | Handling Point | Example Result |
| --- | --- | --- | --- |
| `AuthenticationException` | Any | `AuthenticationEntryPoint` | 401 Basic/Bearer, 302 form login |
| `AccessDeniedException` | Anonymous | `AuthenticationEntryPoint` | 401/302 |
| `AccessDeniedException` | Remember-me deemed insufficient | `AuthenticationEntryPoint` | Prompts for full login |
| `AccessDeniedException` | Fully authenticated | `AccessDeniedHandler` | 403 |
| No exception | Complies with policy | Chain continues | 200, 201, 204, or other MVC result |
| Exception outside those 2 families | Any | Another component | 400/404/500/other response |

Statuses are **examples from typical entry points/handlers**, not hardcoded inside the two exception classes themselves.

## 4. Distinguishing 401, 403, 302, and Other Outcomes

**401 Unauthorized** in HTTP means the client must supply valid credentials for the protected resource. In schemes like Basic or Bearer, the server typically uses `WWW-Authenticate` to convey the challenge.

**403 Forbidden** means the server understood the request yet **refuses permission** under the current policy. A user may already be validly logged in yet still lack the required role/scope/ownership.

**302 Found / redirect to /login** is one way to initiate authentication in a form/session-based website. Never mistake a 302 login redirect as evidence that an API granted data access.

**404 Not Found** can occur because `DispatcherServlet` found no handler; `permitAll` does not create a controller. Some products intentionally return 404 instead of 403 to avoid leaking resource existence; that is an explicit access-policy choice to verify, not default ETF behavior.

**400 Bad Request** for validation/parsing errors differs from 401/403. **500 Internal Server Error** signals unexpected processing failures; never swallow all exceptions and convert them into 403, blinding incident detection.

### 4.1. Should You Always Return JSON with Custom Codes?

For pure REST APIs, a JSON error contract helps clients distinguish states systematically:

```json
{"code":"AUTHENTICATION_REQUIRED"}
```

```json
{"code":"ACCESS_DENIED"}
```

Never include passwords, tokens, stack traces, or user-enumeration details. Add a correlation ID (from trusted infrastructure) and log appropriately server-side. If implementing `application/problem+json`/RFC Problem Details, follow the full format and media type; do not loosely claim the JSON above is Problem Details when it lacks the required fields/contract.

### 4.2. WWW-Authenticate Should Not Be Dropped Carelessly

For Basic APIs, a custom `AuthenticationEntryPoint` should preserve proper challenge behavior if clients rely on it. Returning 401 without `WWW-Authenticate` can break clients expecting the challenge. Conversely, browsers/SPAs may want to suppress Basic pop-ups depending on request type; consult Spring Security documentation on `X-Requested-By: XMLHttpRequest` and your actual config.

Never put passwords or Authorization headers into error bodies, request cache logs, or exception messages returned to clients.

## 5. RequestCache and Saved Requests

When an anonymous user requests a protected page on a website, the framework can save the initial request so after login the user returns to that URL:

```text
GET /account/statement (not logged in)
     |
     +-- AccessDeniedException
     +-- EntryPoint redirects to /login
     +-- RequestCache saves target /account/statement (if enabled)
     |
POST /login (valid credentials)
     |
     +-- SavedRequestAwareAuthenticationSuccessHandler
     +-- Redirect back to /account/statement
```

`RequestCache` is an abstraction with options:

- `HttpSessionRequestCache` can store the saved request in the HTTP session.
- `NullRequestCache` saves nothing; typically suited for stateless/Basic API clients that can replay requests themselves.
- Custom implementations can control how requests are saved and restored.

**Never claim ETF always creates a session or always saves requests.** That depends on `RequestCache` configuration. In the API example below, we use `NullRequestCache` so form-login-style saved requests are not retained. If you adapt the code to browser sessions/form login, design the request cache for UX, session policy, and redirect safety.

### 5.1. Open Redirect Traps and Saved Requests

When redirecting after login, be careful with client-supplied return URLs. Only accept trusted internal targets or saved requests managed by configured mechanisms; avoid redirecting to an attacker's domain via unvalidated `next=https://...` parameters.

A saved request is not an authorization grant. After login, **authorization must still be evaluated again** when the user returns to the original URL.

## 6. ExceptionTranslationFilter and Other Filters: Crucial Boundaries

### 6.1. BasicAuthenticationFilter Can Handle Failures Directly

Typical Basic flow:

```text
Authorization: Basic <base64(username:password)>
       |
       v
BasicAuthenticationFilter
       |
       +-- AuthenticationManager.authenticate(...)
       |
       +-- Wrong password?
       |       +-- Clear context
       |       +-- RememberMeServices.loginFail(...)
       |       +-- Invoke AuthenticationEntryPoint per Basic flow
       |       +-- Do not proceed to controller
       |
       +-- Valid password?
               +-- Store Authentication
               +-- chain.doFilter(...)
```

`BasicAuthenticationFilter` normally sits **before** `ExceptionTranslationFilter` in the chain. Therefore, a `BadCredentialsException` handled by the Basic filter **is not proof that ETF caught it**. Both flows may share the same `AuthenticationEntryPoint`, producing a similar 401 response from two different handling sites.

### 6.2. UsernamePasswordAuthenticationFilter Has a Failure Handler

With form login, `UsernamePasswordAuthenticationFilter` (built on `AbstractAuthenticationProcessingFilter`) processes form credentials. On authentication failure, it typically invokes `AuthenticationFailureHandler` to redirect to `/login?error` or follow your configured behavior.

Do not swap `exceptionHandling().authenticationEntryPoint(...)` assuming every `POST /login` failure will return that JSON. The form authentication failure flow and the unauthenticated-request-to-protected-resource flow are separate.

### 6.3. CsrfFilter Has Its Own AccessDeniedHandler

In Spring Security 6.5, when a protected HTTP method (e.g., POST) has a missing/invalid CSRF token, `CsrfFilter` can invoke **its own** `AccessDeniedHandler` and halt the request. `CsrfFilter` typically sits **before** `ExceptionTranslationFilter`, so that 403 may not pass through the handler configured in `exceptionHandling`.

Testing implication: `POST /public` can be rejected with **403** even though `/public` is `permitAll` if CSRF is enabled and the token is missing. Do not misdiagnose that 403 as `hasRole("ADMIN")`.

If you want consistent error JSON for CSRF, check `CsrfFilter`'s `accessDeniedHandler` config or handle errors at the right layer; configuring only ETF's denied handler may not suffice.

### 6.4. @ControllerAdvice Can Alter the Path of MVC Exceptions

If a controller/service throws `AccessDeniedException`, the exception unwinds through Spring MVC. If `HandlerExceptionResolver` or `@ControllerAdvice` **catches and handles** that exception and writes a response, it may never bubble back out to ETF. If MVC leaves it unhandled, the matching exception propagates out to the security filter chain where ETF translates it.

That is why an overly broad global `@ExceptionHandler(Exception.class)` can accidentally **swallow security exceptions**, breaking entry point/handler logic and turning 401/403 into 500/200 or leaking unintended details. When writing global exception handlers, explicitly scope which exception types you own and leave security exceptions to the security layer.

### 6.5. Exceptions from Servlet Filters Before ETF

If a custom `Servlet Filter` outside `DelegatingFilterProxy` throws an error, or a custom security filter running before ETF throws an uncaught exception, ETF **does not wrap it**. To turn it into a security response, design the handler/filter boundary properly; never assume ETF is a try/catch wrapping the whole Servlet container.

### 6.6. Committed Responses

Once `response.getWriter().flush()` runs or the body has been sent, an error handler cannot safely change status/headers/body. ETF may error out when the response is already committed rather than trying to write a second response. In custom entry points/denied handlers, check `response.isCommitted()` if that situation can occur; never append a second JSON body to an already committed response.

Do not build a catch-all filter that "catches every Throwable and calls sendError(403)", as that hides critical bugs, corrupts committed state, and hampers incident debugging.

## 7. Configuring ExceptionHandling in HttpSecurity

Common configuration point:

```java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(myAuthenticationEntryPoint)
    .accessDeniedHandler(myAccessDeniedHandler)
);
```

This is a **fragment** requiring definitions for both handlers, imports, and security configuration. Spring Security wires these components into the `ExceptionTranslationFilter` flow of the corresponding `SecurityFilterChain`.

Available handlers include:

- `BasicAuthenticationEntryPoint`: HTTP Basic challenge.
- `LoginUrlAuthenticationEntryPoint`: redirect to login page.
- `BearerTokenAuthenticationEntryPoint`: OAuth2 Bearer challenge.
- `HttpStatusEntryPoint`: sends a specified HTTP status.
- Custom `AuthenticationEntryPoint`: JSON/body/headers per your API contract.
- `AccessDeniedHandlerImpl`: default denied handling, typically 403.
- Custom `AccessDeniedHandler`: JSON, auditing, 403 status response.
- `DelegatingAuthenticationEntryPoint` or request-matcher-based config: selects different entry points by request type.

**Distinguish config scope:** With multiple `SecurityFilterChain` beans, each chain can have its own matcher, filter list, and exception handling. An API chain can return JSON 401/403 while a web chain redirects to login/error pages. Do not apply a global JSON handler to form login and be surprised when UX breaks or redirect loops occur.

### 7.1. Why Does SecurityFilterChain Order Matter?

`FilterChainProxy` selects the **first SecurityFilterChain matching the request**. Suppose:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a.anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

This is a multi-chain fragment, not combined with the single-chain demo project below. `/api/**` uses the API chain; remaining paths use the web fallback chain. Without a fallback, URLs outside the API chain risk being unprotected by Spring Security. If the web chain comes first and matches everything, the API chain behind it will never be chosen.

### 7.2. Entry Points for APIs vs. Web Can Differ in Status

| Client | Appropriate Entry Point | Expected Response |
| --- | --- | --- |
| API with HTTP Basic | Basic or custom JSON preserving challenge | 401 + appropriate WWW-Authenticate |
| API with Bearer | BearerTokenAuthenticationEntryPoint | 401 + appropriate Bearer challenge |
| Web form login | LoginUrlAuthenticationEntryPoint | Login redirect, typically 302 |
| Fully authenticated yet lacking role | AccessDeniedHandler | 403 |
| AJAX/SPA | Clearly defined JSON API entry point/handler | 401/403 JSON, no unintended HTML redirect |

Never label "403 = AuthenticationException" or "401 = AccessDeniedException". The exact same `AccessDeniedException` can produce **401** when anonymous or **403** when fully authenticated.

## 8. Spring Boot 3 Example: JSON 401/403 with a Diagnostic Filter

The following code implements a local HTTP Basic **Servlet REST API**. It is designed to prove:

1. `AuthorizationFilter` rejects anonymous calls on `/api/me` and missing roles on `/api/admin`.
2. `ExceptionTranslationFilter` dispatches to the matching authentication/denied branch.
3. A diagnostic filter placed **immediately after ExceptionTranslationFilter** can throw `AuthenticationException` or `AccessDeniedException` so you observe ETF catching downstream exceptions.
4. Bad credentials at `BasicAuthenticationFilter` still use the entry point, yet do not necessarily pass through ETF.
5. Missing a CSRF token can yield 403 from `CsrfFilter` before ETF, not necessarily sharing the JSON body of ETF's denied handler.
6. `permitAll` does not create an MVC handler; Spring MVC can still return 405 on mismatched HTTP methods.

**Limitations:** Hardcoded users/passwords are strictly for local testing on `http://localhost`. Production requires HTTPS, a secure user store, password policies, rate limiting, monitoring, and audited JSON errors that never leak secrets.

Project structure:

```text
src/main/java/example/translation/
    TranslationApplication.java
    SecurityConfig.java
    DemoFailureFilter.java
    DemoController.java

src/test/java/example/translation/
    ExceptionTranslationFlowTest.java
```

### 8.1. Dependencies

In the Groovy DSL `build.gradle` of a Spring Boot 3 project already configured with plugins/repositories/Java 17 toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

This is only the `dependencies` block; with Maven use the equivalent starters and `spring-security-test` in test scope. Rely on Spring Boot's BOM to keep Spring Security versions aligned; never mix Spring Boot 3 with Spring Framework/Security 7 without verifying compatibility.

### 8.2. TranslationApplication.java

```java
package example.translation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TranslationApplication {
    public static void main(String[] args) {
        SpringApplication.run(TranslationApplication.class, args);
    }
}
```

### 8.3. DemoFailureFilter.java

This filter sits **inside the Spring Security chain**, after ETF, to deliberately trigger both security exception types. It omits `@Component` so Spring Boot does not also auto-register it with the Servlet container.

```java
package example.translation;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.web.filter.OncePerRequestFilter;

public class DemoFailureFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String path = request.getServletPath();

        if ("/demo/auth-failure".equals(path)) {
            throw new AuthenticationCredentialsNotFoundException(
                "demonstration authentication failure"
            );
        }

        if ("/demo/access-denied".equals(path)) {
            throw new AccessDeniedException(
                "demonstration access denied"
            );
        }

        chain.doFilter(request, response);
    }
}
```

In production, **never** expose public routes that throw exceptions just for testing; this is a learning probe separating the branches. Calling `/demo/access-denied`:

- Anonymous: ETF routes to entry point.
- Authenticated Reader: ETF routes to denied handler.
- The filter itself merely **throws the exception**; it never sets an HTTP status.

### 8.4. SecurityConfig.java

```java
package example.translation;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;
import org.springframework.security.web.access.ExceptionTranslationFilter;
import org.springframework.security.web.savedrequest.NullRequestCache;

@Configuration
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder(10);
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("reader-local-password"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-local-password"))
            .roles("USER", "ADMIN")
            .build();

        return new InMemoryUserDetailsManager(reader, admin);
    }

    @Bean
    AuthenticationEntryPoint apiEntryPoint() {
        return (request, response, failure) -> {
            response.setStatus(401);
            response.setHeader(
                "WWW-Authenticate", "Basic realm=\"demo\""
            );
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(
                StandardCharsets.UTF_8.name()
            );
            response.getWriter().write(
                "{\"code\":\"AUTHENTICATION_REQUIRED\"}"
            );
        };
    }

    @Bean
    AccessDeniedHandler apiDeniedHandler() {
        return (request, response, denial) -> {
            response.setStatus(403);
            response.setContentType(MediaType.APPLICATION_JSON_VALUE);
            response.setCharacterEncoding(
                StandardCharsets.UTF_8.name()
            );
            response.getWriter().write(
                "{\"code\":\"ACCESS_DENIED\"}"
            );
        };
    }

    @Bean
    SecurityFilterChain api(
            HttpSecurity http,
            AuthenticationEntryPoint entryPoint,
            AccessDeniedHandler deniedHandler) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(
                    HttpMethod.GET,
                    "/demo/auth-failure",
                    "/demo/access-denied"
                ).permitAll()
                .requestMatchers(
                    HttpMethod.GET, "/api/me"
                ).authenticated()
                .requestMatchers(
                    HttpMethod.GET, "/api/admin"
                ).hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .requestCache(cache -> cache
                .requestCache(new NullRequestCache())
            )
            .httpBasic(basic -> basic
                .authenticationEntryPoint(entryPoint)
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(entryPoint)
                .accessDeniedHandler(deniedHandler)
            )
            .addFilterAfter(
                new DemoFailureFilter(),
                ExceptionTranslationFilter.class
            )
            .build();
    }
}
```

**Line-by-line highlights:**

1. `apiEntryPoint` writes JSON **401** and the Basic challenge header. When ETF needs authentication, it invokes this handler. When `BasicAuthenticationFilter` encounters a bad password, we also configure it to use the **same** entry point via `httpBasic`; hence the response matches even though the trigger mechanism differs.
2. `apiDeniedHandler` returns JSON **403** for access denied on this handler branch. It never grants roles or overrides authorization decisions.
3. `requestCache(new NullRequestCache())` avoids browser-session-style saved requests for a Basic API; clients can retry requests themselves.
4. `/public` is `permitAll` across all HTTP methods for **authorization**; because the controller defines only `@GetMapping`, a POST with a valid CSRF token still produces MVC **405**.
5. `/demo/...` is `permitAll`, yet the filter placed after ETF throws an exception before the target Servlet/controller executes.
6. `/api/me` requires `authenticated`; `/api/admin` requires `ROLE_ADMIN`. User `reader` logs in validly yet lacks the admin role.
7. `anyRequest().denyAll()` prevents accidentally exposing undeclared endpoints.
8. `addFilterAfter(new DemoFailureFilter(), ExceptionTranslationFilter.class)` keeps the custom filter **downstream** of ETF so ETF can catch its exceptions. Since the custom filter is not a separate bean, the Servlet container does not auto-register it again.
9. The config uses Spring Security 6.x `SecurityFilterChain`, not the removed `WebSecurityConfigurerAdapter`.
10. `BCryptPasswordEncoder(10)` and hardcoded passwords are for localhost demos only; never pick production cost factors from demo numbers.

**Note on HTTP Basic and CSRF:** HTTP Basic only Base64-encodes credentials and **does not encrypt transport**; HTTPS is mandatory in production. `CsrfFilter` is enabled by default to protect unsafe HTTP methods in cookie/session browsers; stateless token APIs may have a different threat model, yet **never disable CSRF out of habit just to make tests pass**.

### 8.5. DemoController.java

```java
package example.translation;

import java.util.Map;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public Map<String, String> publicEndpoint() {
        return Map.of("message", "public");
    }

    @GetMapping("/api/me")
    public Map<String, String> me(Authentication auth) {
        return Map.of("username", auth.getName());
    }

    @GetMapping("/api/admin")
    public Map<String, String> admin() {
        return Map.of("message", "admin");
    }
}
```

The controller has no mappings for `/demo/auth-failure` or `/demo/access-denied` because the filter throws beforehand. When testing those two routes, the goal is verifying **security error translation**, not MVC handlers.

The controller also knows nothing about password hashes or exception translation logic; it simply receives the `Authentication` already verified by Spring Security.

### 8.6. Running with Gradle

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Assuming the demo app listens on `http://localhost:8080`:

```bash
# Public: 200
curl -i http://localhost:8080/public

# Anonymous accessing protected resource: 401 JSON
curl -i http://localhost:8080/api/me

# Valid Basic login: 200
curl -i -u reader:reader-local-password \
  http://localhost:8080/api/me

# Wrong Basic: 401, handled by Basic failure flow
curl -i -u reader:wrong-password \
  http://localhost:8080/api/me

# Authenticated reader lacking ROLE_ADMIN: 403
curl -i -u reader:reader-local-password \
  http://localhost:8080/api/admin

# Admin with full permissions: 200
curl -i -u admin:admin-local-password \
  http://localhost:8080/api/admin

# AuthenticationException deliberately thrown downstream: 401
curl -i http://localhost:8080/demo/auth-failure

# AccessDeniedException with anonymous -> entry point: 401
curl -i http://localhost:8080/demo/access-denied

# AccessDeniedException with reader -> denied handler: 403
curl -i -u reader:reader-local-password \
  http://localhost:8080/demo/access-denied

# POST public without CSRF token -> 403 at CsrfFilter
curl -i -X POST http://localhost:8080/public
```

Statuses/bodies are **expectations from the code**, not live server logs executed in this article. This is a local HTTP demo; never send real credentials over plain HTTP or place real raw passwords in shell history/process lists.

**Expected response for `GET /api/me` without credentials:**

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="demo"
Content-Type: application/json;charset=UTF-8

{"code":"AUTHENTICATION_REQUIRED"}
```

Exact casing/spacing of `Content-Type` may vary by Servlet container; the contract to verify is status 401, the challenge header, and the JSON body written by the entry point.

**Expected response for `reader` calling `GET /api/admin`:**

```http
HTTP/1.1 403 Forbidden
Content-Type: application/json;charset=UTF-8

{"code":"ACCESS_DENIED"}
```

No stack trace, password, JWT, or granular authorization reason appears in the response. Production deployments should add correlation IDs and proper server-side auditing without exposing sensitive details via exception messages.

## 9. JUnit 5 and MockMvc: Testing Every Branch

Create `src/test/java/example/translation/ExceptionTranslationFlowTest.java`:

```java
package example.translation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ExceptionTranslationFlowTest {

    @Autowired
    MockMvc mvc;

    @Test
    void publicEndpointAllowsAnonymous() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("public"));
    }

    @Test
    void anonymousMeUsesAuthenticationEntryPoint()
            throws Exception {
        mvc.perform(get("/api/me"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "WWW-Authenticate",
                containsString("Basic")
            ))
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void correctBasicPasswordReachesController() throws Exception {
        mvc.perform(get("/api/me").with(httpBasic(
                "reader", "reader-local-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("reader"));
    }

    @Test
    void incorrectBasicPasswordUsesBasicFailurePath()
            throws Exception {
        mvc.perform(get("/api/me").with(httpBasic(
                "reader", "incorrect")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void authenticatedReaderWithoutRoleIsForbidden()
            throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic(
                "reader", "reader-local-password")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }

    @Test
    void adminRoleIsAllowed() throws Exception {
        mvc.perform(get("/api/admin").with(httpBasic(
                "admin", "admin-local-password")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.message").value("admin"));
    }

    @Test
    void thrownAuthenticationExceptionUsesEntryPoint()
            throws Exception {
        mvc.perform(get("/demo/auth-failure"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void thrownAuthenticationExceptionEvenForReaderUsesEntryPoint()
            throws Exception {
        mvc.perform(get("/demo/auth-failure").with(httpBasic(
                "reader", "reader-local-password")))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void deniedForAnonymousUsesEntryPoint() throws Exception {
        mvc.perform(get("/demo/access-denied"))
            .andExpect(status().isUnauthorized())
            .andExpect(jsonPath("$.code")
                .value("AUTHENTICATION_REQUIRED"));
    }

    @Test
    void deniedForAuthenticatedReaderUsesDeniedHandler()
            throws Exception {
        mvc.perform(get("/demo/access-denied").with(httpBasic(
                "reader", "reader-local-password")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }

    @Test
    void unsafeMethodWithoutCsrfIsForbidden()
            throws Exception {
        mvc.perform(post("/public"))
            .andExpect(status().isForbidden());
        // Do not assert JSON from ETF handler: CSRF has its own handler.
    }

    @Test
    void validCsrfButWrongMvcMethodIsMethodNotAllowed()
            throws Exception {
        mvc.perform(post("/public").with(csrf()))
            .andExpect(status().isMethodNotAllowed());
    }

    @Test
    void unknownRouteDoesNotBecomePublicForReader()
            throws Exception {
        mvc.perform(get("/unmapped").with(httpBasic(
                "reader", "reader-local-password")))
            .andExpect(status().isForbidden())
            .andExpect(jsonPath("$.code").value("ACCESS_DENIED"));
    }

    @Test
    void unknownRouteAnonymousStillNeedsAuthentication()
            throws Exception {
        mvc.perform(get("/unmapped"))
            .andExpect(status().isUnauthorized());
    }
}
```

Run:

```bash
./gradlew test --tests example.translation.ExceptionTranslationFlowTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.translation.ExceptionTranslationFlowTest
```

**Expected:** there are **14 test methods**, designed to pass with the Spring Boot 3/Spring Security 6.x project described above. This expectation is based on code review; **we do not claim Gradle was run or that actual PASS logs exist**.

### 9.1. Which Branch Does Each Test Cover?

| Test | Layer Tested | Proper Interpretation |
| --- | --- | --- |
| `/public` | Authorization permitAll + MVC | No security error |
| Anonymous `/api/me` | AuthorizationFilter → ETF → EntryPoint | 401, unauthenticated request |
| Valid Basic password | Basic authentication + MVC | 200, not exception translation |
| Wrong Basic password | BasicAuthenticationFilter failure handler/entry point | 401, yet do not conclude ETF caught it |
| Reader calling admin | AuthorizationFilter → ETF → DeniedHandler | 403 due to missing role |
| Admin calling admin | Authentication + authorization + MVC | 200 |
| `/demo/auth-failure` | Downstream AuthenticationException → ETF | EntryPoint, 401 |
| `/demo/access-denied` anonymous | Downstream AccessDeniedException → ETF | EntryPoint, 401 |
| `/demo/access-denied` reader | Downstream AccessDeniedException → ETF | DeniedHandler, 403 |
| POST missing CSRF | CsrfFilter/handler | 403, not guaranteed JSON denied handler |
| POST with CSRF, wrong method | MVC handler matching | 405 |
| Unknown path | `anyRequest().denyAll` | 401 anonymous / 403 authenticated |

With `@WithMockUser`, you can test authorization branches in isolation using a mock principal, yet **it does not prove the password provider actually authenticated**. Testing `httpBasic(...)` against the demo user store covers the credential path.

### 9.2. Why Not Assert All FilterChainProxy Internals in MockMvc?

MockMvc simulates Servlet requests/filters for testing; it does not prove network/TLS behavior, browser redirect state, load balancers, error dispatches, or every container-specific filter registration. To verify filter ordering, committed responses, real multi-chain deployments, and real statuses/headers, add integration tests with an embedded server/random port and HTTP clients.

### 9.3. Additional Tests Needed for Production Apps

- Anonymous requests across multiple entry points: JSON API vs. web login redirect.
- OAuth2 Bearer insufficient scope: verify RFC 6750 challenge and status per resource server config.
- Remember-me accessing an endpoint requiring full authentication: verify entry point triggers.
- `AccessDeniedException` from `@PreAuthorize` not swallowed by global `@ControllerAdvice`.
- Missing/invalid CSRF: proper handler without data leaks.
- Only one `SecurityFilterChain` matches the intended request; fallback chain covers all URLs.
- Servlet filter before ETF throwing an error: do not assume ETF handles it.
- Committed error responses: never write JSON a second time.
- Error messages and logs exclude passwords, cookies, Authorization headers, and reset tokens.
- Regression tests when upgrading Spring Security/Servlet containers.

## 10. Standalone Java 17: Simulating Exception Translation Logic

This problem belongs to Servlet Spring Security, so **plain JDK cannot instantiate a real `ExceptionTranslationFilter`** without dependencies. To practice the 401/403 decision tree, the program below models the **decision tree** using Java 17 types. It uses no real HTTP, has no `AuthenticationManager`, and does not replace the framework integration tests above.

Create `ExceptionTranslationModel.java`:

```java
public class ExceptionTranslationModel {

    enum Identity {
        ANONYMOUS,
        REMEMBER_ME,
        FULLY_AUTHENTICATED
    }

    sealed interface Failure
        permits AuthFailure, AccessFailure {}

    record AuthFailure(String reason) implements Failure {}
    record AccessFailure(String reason) implements Failure {}

    static String translate(Identity identity, Failure failure) {
        if (failure instanceof AuthFailure) {
            return "ENTRY_POINT:401";
        }

        if (identity == Identity.ANONYMOUS
                || identity == Identity.REMEMBER_ME) {
            return "ENTRY_POINT:401";
        }

        return "ACCESS_DENIED_HANDLER:403";
    }

    public static void main(String[] args) {
        System.out.println(
            "authFailure:anonymous="
                + translate(
                    Identity.ANONYMOUS,
                    new AuthFailure("credential missing")
                )
        );

        System.out.println(
            "authFailure:authenticated="
                + translate(
                    Identity.FULLY_AUTHENTICATED,
                    new AuthFailure("re-auth required")
                )
        );

        System.out.println(
            "denied:anonymous="
                + translate(
                    Identity.ANONYMOUS,
                    new AccessFailure("admin only")
                )
        );

        System.out.println(
            "denied:rememberMe="
                + translate(
                    Identity.REMEMBER_ME,
                    new AccessFailure("step-up needed")
                )
        );

        System.out.println(
            "denied:authenticated="
                + translate(
                    Identity.FULLY_AUTHENTICATED,
                    new AccessFailure("admin only")
                )
        );
    }
}
```

Compile/run with JDK 17:

```bash
javac ExceptionTranslationModel.java
java ExceptionTranslationModel
```

**Exact stdout per the code logic above:**

```text
authFailure:anonymous=ENTRY_POINT:401
authFailure:authenticated=ENTRY_POINT:401
denied:anonymous=ENTRY_POINT:401
denied:rememberMe=ENTRY_POINT:401
denied:authenticated=ACCESS_DENIED_HANDLER:403
```

In this model, every entry point is assumed to return 401 like a Basic API; **in real Spring Security, an entry point can redirect 302**. The goal is recognizing the **handler branch**, not simulating the entire Servlet lifecycle.

Key observations:

1. `AuthFailure` always goes to the entry point, regardless of identity enum.
2. `AccessFailure` with `ANONYMOUS` or `REMEMBER_ME` goes to the entry point.
3. `AccessFailure` with `FULLY_AUTHENTICATED` goes to the denied handler.
4. There is no "catch every exception" branch: `Failure` is bounded by a `sealed interface` to emphasize scope.
5. The model does not represent filter-chain position; in real apps, only exceptions **passing through ETF's wrapped region** are handled by ETF.

## 11. Method Security and Exception Propagation

`@EnableMethodSecurity` enables annotations like `@PreAuthorize` on service methods. Example:

```java
@Service
class ReportService {

    @PreAuthorize("hasAuthority('report:export')")
    public byte[] exportReport(long reportId) {
        // Verify owner/tenant of reportId using appropriate domain logic.
        return new byte[0];
    }
}
```

This is a fragment: it requires enabling method security, dependencies, and imports. `@PreAuthorize` can raise `AccessDeniedException` if authority is lacking. In a Servlet request passing through ETF, the exception can propagate through the Controller/`DispatcherServlet` out to the filter; **however**, `@ControllerAdvice`/MVC `HandlerExceptionResolver` may handle it first. Always test the **actual exception propagation path** to ensure JSON/error/status align with policy.

Method security does not replace resource owner/tenant checks; someone permitted to export reports is not necessarily allowed to export someone else's report. Never return 403 for roles while overlooking BOLA/IDOR vulnerabilities.

### 11.1. Never Translate Exceptions Arbitrarily

An anti-pattern:

```java
try {
    reportService.exportReport(id);
} catch (Exception ex) {
    return ResponseEntity.status(403).build();
}
```

This turns database outages, `NullPointerException`s, timeouts, and bugs into 403s while masking system health. It is far better to design typed exception handlers, keep security error handling in the security stack, and record redacted logs/audits.

## 12. Debugging Why a Request Returned 401 or 403

When troubleshooting, proceed in order:

1. **Actual request:** URL, HTTP method, Content-Type, Accept, dispatcher type, presence of Authorization/cookies (never log secret values).
2. **FilterChainProxy:** which security chain did the request match? Is `securityMatcher` too narrow, missing a fallback, or misordered?
3. **Authentication state:** anonymous, remember-me, authenticated, and what authorities/roles/scopes? Is Authentication in SecurityContext right?
4. **Filter raising the error:** BasicAuthenticationFilter, CsrfFilter, AuthorizationFilter, custom filter, method security, or MVC?
5. **Exception type:** `AuthenticationException` or `AccessDeniedException`? Any wrapper/nested cause?
6. **Where is ETF:** did the exception arise **before or after** ETF? Did it reach ETF, or was it already handled elsewhere?
7. **Which entry point/denied handler:** from which chain, and which custom config? HTTP Basic, Bearer, form login, REST JSON?
8. **Is the response already committed:** did a filter/controller write the body before throwing?
9. **RequestCache:** is the API using `NullRequestCache` or is web using `HttpSessionRequestCache`?
10. **CSRF:** if POST/PATCH/PUT/DELETE returns 403, check the CSRF token before concluding a role is missing.
11. **MVC errors:** for 404/405/500, inspect `DispatcherServlet`/`ControllerAdvice` and error dispatches.
12. **Tests:** reproduce with MockMvc and real HTTP tests when filter order/network behavior matters.

### 12.1. Controlled Logging

Example in `application.properties` for dev environments:

```properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
logging.level.org.springframework.security.web.access.ExceptionTranslationFilter=TRACE
```

This helps uncover selected chains, security errors, and how responses are dispatched. Never leave TRACE enabled long-term in production without controlling potential data exposure. Never log `Authorization` headers, raw passwords, session cookies, bearer tokens, reset links, or sensitive personal data.

### 12.2. Useful Breakpoints

| Breakpoint | Question Answered |
| --- | --- |
| `FilterChainProxy.doFilter` | Which security chain matched? |
| `BasicAuthenticationFilter.doFilterInternal` | Did credentials arrive via Basic? Where is failure handled? |
| `CsrfFilter.doFilterInternal` | Is the request missing a CSRF token? |
| `ExceptionTranslationFilter.doFilter` | Did a matching exception escape from downstream? |
| `ExceptionTranslationFilter.handleAccessDeniedException` | Anonymous/remember-me or authenticated? |
| `AuthenticationEntryPoint.commence` | Who generated the 401/redirect and challenge header? |
| `AccessDeniedHandler.handle` | Who generated the 403 and error body? |
| `AuthorizationFilter.doFilter` | Which authorization rule denied access? |
| `DispatcherServlet.doDispatch` | Did the request reach MVC? |
| `HandlerExceptionResolver.resolveException` | Did MVC handle the exception before ETF saw it? |

Method names can vary across versions; set breakpoints in the source of the exact downloaded dependency. For a custom filter, set breakpoints before/after `chain.doFilter` and observe the actual sequence.

## 13. Easy-to-Hit Anti-Patterns

### 13.1. "ExceptionTranslationFilter checks permissions"

False. It is a **translator**. `AuthorizationFilter`/method security evaluates permissions. Without an authorization mechanism, if every request is allowed through, ETF will not deny access itself to "protect everything".

### 13.2. "AccessDeniedException always returns 403"

False. If anonymous or remember-me is deemed insufficient, ETF routes to the entry point. Basic APIs typically return 401; web logins typically redirect.

### 13.3. "AuthenticationException is always a wrong-password error"

False. Missing credentials, expired authentication, or insufficient step-up can also raise `AuthenticationException`. Never leak detailed reasons to clients.

### 13.4. "Every 401 comes from ExceptionTranslationFilter"

False. `BasicAuthenticationFilter` or a bearer authentication filter can handle authentication failures itself via the entry point.

### 13.5. "Every 403 comes from the AccessDeniedHandler configured in exceptionHandling"

False. `CsrfFilter` can invoke its own `AccessDeniedHandler`. MVC/controllers or gateways can also return 403.

### 13.6. "permitAll skips all security filters"

False. `permitAll` skips the **authorization** requirement for that URL, not `CsrfFilter`/headers and other filters. `web.ignoring` differs from `permitAll` and skips the security chain.

### 13.7. "A global ControllerAdvice catches every security exception"

False. Filters running before MVC can write responses without MVC ever being invoked; conversely, a catch-all `ControllerAdvice` can accidentally swallow security exceptions thrown from controllers.

### 13.8. "Changing 401 to 403 prevents information disclosure"

No single status-code swap solves information disclosure. Design authentication challenges, resource-existence policies, API contracts, and controlled error messages properly. Swapping 401/403 wrongly can break client behavior and skew monitoring.

### 13.9. "A saved request is always needed"

No. Browser form logins may need URL restoration; stateless APIs normally choose `NullRequestCache`. Avoid creating unnecessary sessions or unsafe saved requests.

### 13.10. "Throw AccessDeniedException for every validation error"

False. Malformed JSON or failed field validation is normally 400, not an authorization failure. Keep errors in the right domain layer.

### 13.11. "Set 200 first and let the exception handler write 401"

Once the response is committed, you cannot safely write a new status/body. Never stream responses before completing necessary security checks.

### 13.12. "Leave default handlers for a REST API; they surely return JSON"

No. Default entry points may redirect HTML or return bodyless challenges. APIs must explicitly configure and test response contracts if consistent JSON is required.

### 13.13. "Two SecurityFilterChains always combine"

No. `FilterChainProxy` selects the first matching chain. One chain's error handling does not apply to requests routed into another chain.

### 13.14. "@WithMockUser is enough to test password login"

No. It bypasses credential authentication. Use `httpBasic(...)` or form-login tests to prove the real authentication provider works.

### 13.15. "Throwing an exception directly in a filter before ETF will be caught by ETF"

No. A downstream filter cannot catch an exception thrown from an outer layer before it was ever invoked.

### 13.16. "A 403 CSRF error means the user lacks ROLE_ADMIN"

No. An authenticated request with the right role can still lack a CSRF token. Test authentication, authorization, and CSRF separately.

### 13.17. "Return 401 for a missing role to ask for the password again"

When a user is already fully authenticated yet lacks a role, prompting for the password again will not grant the role. Return 403 per policy and fix permissions rather than creating login loops.

### 13.18. "Put exception.message into JSON returned to the client"

Internal messages can expose usernames, token details, policy info, or stack traces. Use stable error codes, minimal details, correlation IDs, and redacted logs.

### 13.19. "If no controller exists, ExceptionTranslationFilter must still handle it"

No. A `permitAll` URL with no MVC handler normally returns 404/405; ETF does not replace `DispatcherServlet` or handler mappings.

### 13.20. "In async dispatches, you only need to think about a single FilterChain pass"

Async, `FORWARD`, and `ERROR` dispatches can trigger additional processing and security authorization per `DispatcherType`/config. Evaluate filter registrations, `SecurityContext` propagation, and error dispatches to prevent unexpected status changes.

## 14. Design Verification Checklist

**Authentication vs. authorization**

- [ ] List enabled authentication mechanisms: HTTP Basic, form, bearer/JWT, OAuth2, SSO.
- [ ] Know which principals are anonymous/remember-me/fully-authenticated.
- [ ] Understand each authentication filter's direct failure handler.
- [ ] Do not map every `AuthenticationException` to "bad password".
- [ ] Do not map every `AccessDeniedException` to 403 regardless of principal state.

**ETF and error handlers**

- [ ] Identify how each `SecurityFilterChain` configures `AuthenticationEntryPoint`/`AccessDeniedHandler`.
- [ ] Entry points preserve proper `WWW-Authenticate` challenges or redirect behavior.
- [ ] `AccessDeniedHandler` returns 403/body appropriate for APIs/browsers.
- [ ] `RequestCache` fits the use case: `NullRequestCache` for stateless/Basic when needed, saved requests for web when needed.
- [ ] Distinguish exceptions before vs. after `ExceptionTranslationFilter`.
- [ ] Test CSRF filter errors separately without confusing handlers.
- [ ] Ensure no catch-all `ControllerAdvice` breaks security responses.
- [ ] Never write a response a second time after commit.
- [ ] Never expose credentials, tokens, stack traces, or policy details.

**Servlet/MVC and QA**

- [ ] Verify `SecurityFilterChain` order, `securityMatcher`, and fallback.
- [ ] Verify `AuthorizationFilter`/roles/scopes and method-level authorization.
- [ ] Verify owner/tenant/object-level permissions at the service layer.
- [ ] Test anonymous 401/302, authenticated missing-role 403, and authentication success 200.
- [ ] Test wrong Basic password handled by the authentication filter.
- [ ] Test CSRF 403, MVC 404/405, and security 403 separately.
- [ ] Test JSON/status/`WWW-Authenticate` headers with MockMvc.
- [ ] Test filters before ETF and downstream exceptions when using custom filters.
- [ ] Maintain monitoring and redacted security audits rather than relying solely on client status codes.
- [ ] Cross-check Spring Security APIs against your BOM's exact version; never copy WebFlux config.

## 15. Self-Check Questions and Answers

**1. Does ExceptionTranslationFilter check roles/authorities itself?**  
No. It translates supported security exceptions into HTTP responses; authorization lives in other filters/managers.

**2. Which filter typically throws AccessDeniedException when a URL fails a rule?**  
`AuthorizationFilter` (via `AuthorizationManager`).

**3. When an anonymous caller hits a URL requiring `authenticated`, what status can a Basic API return?**  
401 from `AuthenticationEntryPoint`, triggered by ETF after `AccessDeniedException`.

**4. A user logs in validly yet lacks `ROLE_ADMIN`; which handler is normally invoked?**  
`AccessDeniedHandler`, typically returning 403.

**5. Why does AccessDeniedException sometimes go to AuthenticationEntryPoint?**  
Because `AuthenticationTrustResolver` identifies anonymous or insufficient remember-me authentication; authentication must be requested.

**6. Where does an AuthenticationException caught by ETF go?**  
`AuthenticationEntryPoint`, with `SecurityContext` cleared and `RequestCache` invoked per configuration.

**7. Must AuthenticationEntryPoint always return 401 JSON?**  
No. Form login typically redirects; Basic/Bearer typically sends a 401 challenge.

**8. Does AccessDeniedHandler ever grant admin roles?**  
No. It only produces the response when access is denied.

**9. Why can an HTTP Basic wrong password return 401 without passing through ETF?**  
`BasicAuthenticationFilter` has its own authentication failure handling and calls the entry point directly.

**10. Why does a POST missing a CSRF token return 403 even on a `permitAll` endpoint?**  
`CsrfFilter` operates independently before authorization and has its own denied handling.

**11. Why is @ControllerAdvice not guaranteed to catch exceptions from a Servlet filter?**  
Because MVC's exception resolver handles MVC scope only, whereas filters can run before `DispatcherServlet`.

**12. Does RequestCache always create a session?**  
No; `NullRequestCache` saves nothing, while `HttpSessionRequestCache` can store inside the session.

**13. Once the response is committed, can you reliably change the status to 401?**  
No. Writing a new response can fail and trigger secondary errors.

**14. If multiple SecurityFilterChains match a request, which handler applies?**  
The first matching chain selected by `FilterChainProxy`; chains are not combined.

**15. What is the right way to test that `reader` lacks admin permission?**  
MockMvc `GET /api/admin` with valid `reader` credentials, asserting 403 and the error contract.

**16. Why should you not use @WithMockUser to verify password hashing/login works?**  
That annotation injects a mock `Authentication`, bypassing real credential verification.

**17. When receiving 403, where should you check first?**  
`CsrfFilter`, `AuthorizationFilter`, `AccessDeniedHandler`, principal authorities, and route matchers.

**18. Does Spring WebFlux use the same Servlet ExceptionTranslationFilter?**  
No. WebFlux has a reactive security chain and corresponding components; never copy Servlet APIs directly.

## 16. Official References

- [Spring Security 6.5 – Servlet Architecture and ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 – Authentication Architecture, EntryPoint](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 – HTTP Basic Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/basic.html)
- [Spring Security 6.5 – CSRF Protection](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security – ExceptionTranslationFilter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/ExceptionTranslationFilter.html)
- [Spring Security – AuthenticationEntryPoint Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/AuthenticationEntryPoint.html)
- [Spring Security – AccessDeniedHandler Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/access/AccessDeniedHandler.html)
- [Spring Security – RequestCache Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/savedrequest/RequestCache.html)
- [Spring Framework 6.2 – DispatcherServlet](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-servlet.html)
- [Jakarta Servlet 6.0 – Servlet API specification](https://jakarta.ee/specifications/servlet/6.0/)
