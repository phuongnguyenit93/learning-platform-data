# AbstractAuthenticationProcessingFilter and Core Processing Steps

## 1. Role of the Login Processing Filter in Spring Security Servlet

In a web application using Spring Security, a request does not become "logged in" merely because it carries `username` and `password` fields. The framework must identify **which request is an authentication request**, convert untrusted input into an *unauthenticated* `Authentication`, delegate verification to `AuthenticationManager`, handle the outcome, and decide the `SecurityContext` state and HTTP response.

**`AbstractAuthenticationProcessingFilter`** is the abstract base class for **Servlet filters that process interactive authentication requests**, especially mechanisms with a dedicated login endpoint. Classic examples include `UsernamePasswordAuthenticationFilter`, as well as certain OAuth2/SAML/WebAuthn login filters with a matching processing lifecycle. This class lives in the package:

```java
org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter
```

It extends `GenericFilterBean` and implements Servlet `Filter`; it is **not** an `AuthenticationProvider`, `UserDetailsService`, controller, or password-hashing mechanism.

The core can be remembered through four questions:

1. **Is this a login request that needs processing?** — `requiresAuthentication(...)` and `RequestMatcher`.
2. **Can this request be authenticated yet?** — `attemptAuthentication(...)`, defined by the subclass; it may return a result, throw an exception, or return `null`.
3. **After authentication succeeds, what must happen?** — session strategy, create/save `SecurityContext`, remember-me, success event, and success handler.
4. **When it fails, what must happen?** — clear the current context, notify remember-me, failure handler, and appropriate HTTP response.

**Right mindset:** this filter **orchestrates the authentication request lifecycle**, while whether the password/OTP/token evidence is valid is checked by `AuthenticationManager` and the responsible provider. A custom filter that sets `authenticated=true` from client data without verifying credentials is a **vulnerability**, not an optimization.

## 2. Collaborating Components and Scopes of Responsibility

| Component | Where is it called? | Primary job |
| --- | --- | --- |
| `RequestMatcher` | Before authentication | Selects which method/path/request must pass through the login filter. |
| `AbstractAuthenticationProcessingFilter` | Inside `SecurityFilterChain` | Orchestrates matching → attempt → session → success/failure. |
| Subclass's `attemptAuthentication` | When matcher matches | Reads request, creates input `Authentication`, delegates to manager or starts a multi-step flow. |
| `AuthenticationManager` | Inside attempt | Verifies `Authentication` via the appropriate provider. |
| `AuthenticationProvider` | Selected by manager | Checks password/hash, user status, or specialized credential. |
| `SessionAuthenticationStrategy` | After successful attempt, before success handler | Handles new login, e.g., session fixation protection or session limits when configured. |
| `SecurityContextHolder` | During success/failure | Holds the current `Authentication` in the execution context. |
| `SecurityContextRepository` | On success if configured | Saves context to request attribute/`HttpSession` or another mechanism for scoped restoration. |
| `RememberMeServices` | After success/failure | Manages remember-me option if enabled by the application. |
| `AuthenticationSuccessHandler` | End of success branch | Redirects or writes the success HTTP response. |
| `AuthenticationFailureHandler` | End of failure branch | Redirects on error or writes the error HTTP response. |
| `AuthenticationEntryPoint` | Usually in `ExceptionTranslationFilter` | Prompts the user to **initiate authentication** when accessing a protected resource without a valid identity. |

**Key distinction:** `AuthenticationEntryPoint` is used to invite/challenge for authentication when needed; `AuthenticationFailureHandler` handles **a login attempt that was tried and failed**. These are distinct roles even though both can produce HTTP 401 or a redirect.

### Relationship to `UsernamePasswordAuthenticationFilter`

`UsernamePasswordAuthenticationFilter` is the concrete subclass that reads the `username` and `password` form parameters, constructs a `UsernamePasswordAuthenticationToken`, and submits it to the manager. By default it typically processes **POST `/login`**; parameter names are configurable.

```text
POST /login
Content-Type: application/x-www-form-urlencoded

username=lan&password=...
```

This is a protocol illustration, not a sample request for logging real passwords. The base filter **does not automatically understand** JSON bodies, an `email` field name, OTPs, or signatures: for custom mechanisms, choose a suitable converter/subclass/provider or existing authentication filter.

## 3. Main Control Flow of `doFilter`

Conceptual flow as of Spring Security **6.5.11**:

```text
Servlet FilterChain
       |
       v
AbstractAuthenticationProcessingFilter.doFilter(req, res, chain)
       |
       +--> requiresAuthentication(req, res)?
       |           |
       |           +-- false --> chain.doFilter(...) --> do not attempt login
       |
       v  true
attemptAuthentication(req, res)
       |
       +-- return null --------> flow not yet complete;
       |                         filter RETURNS immediately, no success/failure
       |
       +-- throw AuthenticationException
       |           |
       |           v
       |     unsuccessfulAuthentication(...)
       |       clear SecurityContextHolder
       |       rememberMeServices.loginFail(...)
       |       failureHandler.onAuthenticationFailure(...)
       |           |
       |          RETURN
       |
       +-- return Authentication
                   |
                   v
       sessionAuthenticationStrategy.onAuthentication(...)
                   |
                   v
       (if continueChainBeforeSuccessfulAuthentication = true,
        chain.doFilter(...) runs HERE)
                   |
                   v
       successfulAuthentication(...)
         create SecurityContext / set Authentication
         save via configured SecurityContextRepository
         rememberMeServices.loginSuccess(...)
         publish InteractiveAuthenticationSuccessEvent if publisher present
         successHandler.onAuthenticationSuccess(...)
                   |
                 RETURN
```

**Note:** the diagram describes the basic flow; it does not dictate that the success handler must redirect or that every system must create a session. Exceptions raised in the session strategy and callback components have their own effects, explained below.

### Why Do Non-Matching Requests Still Proceed?

When `requiresAuthentication(...) == false`, the filter calls `chain.doFilter(request,response)`. This is normal: a custom login filter should only intercept requests belonging to the **login endpoint**, while endpoints like `/orders`, `/me`, or `/css/style.css` pass through to other filters and the application per configuration.

Do not interpret `requiresAuthentication=false` as "the user is already authenticated". It only says **this request is not a login attempt owned by the current filter**.

## 4. Selecting the Right Request with `RequestMatcher`

`AbstractAuthenticationProcessingFilter` provides `setRequiresAuthenticationRequestMatcher(RequestMatcher)` and constructors accepting a matcher. A matcher can inspect path, HTTP method, or other controlled conditions.

A simple option in a Spring Security 6.5 demo:

```java
RequestMatcher loginPost =
        new AntPathRequestMatcher("/login-demo", "POST");
```

The `AntPathRequestMatcher` API is marked deprecated in the Spring Security 6.5 line in favor of newer matchers; the demo uses it because it is straightforward to observe with mock Servlet requests. In new production projects, pick the current recommended `RequestMatcher` in Spring Security and test paths accurately against the Servlet context/application router.

**Matching only the URL while ignoring the HTTP method is a common mistake:** if the filter accepts `GET /login` as well, credentials can leak into query strings or the endpoint can be triggered unintentionally. For form login, Spring Security's `UsernamePasswordAuthenticationFilter` requires POST by default; applications should preserve this restriction alongside appropriate CSRF protection.

### Paths in Servlet Are Not Always Equal to the Raw Sent URL

`getRequestURI()` may include the context path; `getServletPath()` and `getPathInfo()` have distinct semantics. Framework-provided request matchers inspect the right fields, whereas **you should not manually concatenate request URI strings and compare with `equals`** when context paths, `;jsessionid` path parameters, proxy rewrites, or trailing slashes are involved.

Test matrix to cover:

| Request | Matcher `/login-demo` + POST | Behavior |
| --- | --- | --- |
| `POST /login-demo` | Matches | Attempts authentication. |
| `GET /login-demo` | Does not match | Continues filter chain. |
| `POST /login-demo/extra` | Does not match exact matcher | Continues chain. |
| `POST /private` | Does not match | Continues chain. |
| A login path behind reverse proxy/context path | Depends on resolved Servlet path | Run real integration test, do not guess. |

A misconfigured filter matcher can **skip login** or, worse, intercept non-login requests by mistake; that is often mistaken for an `AuthenticationManager` bug.

## 5. `attemptAuthentication`: Turning a Request into an Input Authentication

This is the **central abstract method** that subclasses must implement:

```java
public abstract Authentication attemptAuthentication(
        HttpServletRequest request,
        HttpServletResponse response)
        throws AuthenticationException, IOException, ServletException;
```

The signature above illustrates the current API; imports belong to `jakarta.servlet` and Spring Security. Inside a subclass, it typically:

1. Extracts authentication data according to the allowed format (form fields, dedicated header, token callback, etc.).
2. Validates required input conditions, size limits, and missing fields.
3. Builds an **unauthenticated** `Authentication`. For example, `UsernamePasswordAuthenticationToken.unauthenticated(username,password)`.
4. Optionally sets `details` from an appropriate `AuthenticationDetailsSource` if request metadata is needed.
5. Calls `getAuthenticationManager().authenticate(candidate)` and returns the verified result on success.

```java
@Override
public Authentication attemptAuthentication(
        HttpServletRequest request,
        HttpServletResponse response) {

    String username = request.getParameter("username");
    String password = request.getParameter("password");

    UsernamePasswordAuthenticationToken candidate =
            UsernamePasswordAuthenticationToken.unauthenticated(
                    username, password);

    return getAuthenticationManager().authenticate(candidate);
}
```

This is a **code excerpt**, omitting the enclosing class, filter wiring, exception handling, and full configuration. In production, do not let `null`, overly long strings, or malformed input pass through unchecked; validation must preserve password policies without leaking user information. Do not lower-case or trim passwords automatically.

### Three Exact Outcomes of `attemptAuthentication`

| Outcome | Meaning | What will the filter do? |
| --- | --- | --- |
| Returns an `Authentication` verified by manager | Authentication attempt succeeded | Runs session strategy and success path. |
| Throws `AuthenticationException` | Authentication attempt failed | Runs `unsuccessfulAuthentication` and failure handler. |
| Returns `null` | Authentication processing **not yet complete** | Returns immediately; the subclass must have already performed the needed action, e.g., redirect/await next request. |

**Returning `null` does not mean failure and does not mean success.** It only signals stopping the current branch because another stage follows. If a subclass returns `null` without sending a meaningful response, the client may receive a confusing default HTTP status; the demo below explicitly sets `202` to make this branch visible.

**Do not use `return null` to swallow a wrong password.** When credentials are invalid and login must be rejected, throw an appropriate `AuthenticationException` so the framework invokes the failure handler.

### Why Not Return a Token Manually Marked Authenticated?

`UsernamePasswordAuthenticationToken.authenticated(principal, credentials, authorities)` is meant for code that **already has a trusted basis** to construct authentication. If a filter reads `username`/`roles` from a JSON body and calls this factory, an attacker can claim `ROLE_ADMIN` without a password. The right pattern is an **unauthenticated** token passed through `AuthenticationManager` or an equivalent verifying provider.

### Bounded Multi-Step Handling

OAuth2 callbacks, SAML, or MFA each have their own lifecycles. In a custom subclass, `return null` can represent "redirected to next step" or "awaiting additional evidence", but **do not hand-roll secure MFA**. Proper MFA requires transaction/state/nonce/expiry management, user–device binding, replay protection, and using existing framework mechanisms where appropriate.

## 6. AuthenticationManager and AuthenticationProvider: Where Real Verification Lives

`AbstractAuthenticationProcessingFilter` does not query the database or check password hashes itself. It needs an `AuthenticationManager`:

```text
Filter reads request
   |
   +--> UsernamePasswordAuthenticationToken(authenticated=false)
   |
   v
AuthenticationManager (typically ProviderManager)
   |
   +--> AuthenticationProvider.supports(token type)?
   |
   +--> UserDetailsService.loadUserByUsername(...)
   |
   +--> PasswordEncoder.matches(raw, storedHash)
   |
   +--> account status / credential expiry / custom checks
   |
   v
Verified result Authentication
   principal + authorities + authenticated=true
```

Not every provider is `DaoAuthenticationProvider`: for other tokens or protocols, the manager selects the corresponding provider. If the manager has no provider supporting the `Authentication` type, login can fail with `ProviderNotFoundException`, not because of a URL matcher.

**Access permissions** after authentication come from `GrantedAuthority` established by a trusted system, never copied directly from a `role=ADMIN` field sent by the client.

A notable operational pitfall is keeping a reference to a lazy `UserDetails`/JPA entity inside the principal: authentication may succeed, yet code reading authorities outside the transaction throws `LazyInitializationException`. Account repository adapters should map to a `UserDetails` independent of the ORM session within the read transaction.

## 7. SessionAuthenticationStrategy: Between Attempt and Success

When `attemptAuthentication` returns an `Authentication`, the filter calls `SessionAuthenticationStrategy.onAuthentication(authentication,request,response)` **before `successfulAuthentication`**.

Purposes of the strategy may include:

- **Session fixation** protection, e.g., rotating the session ID upon login.
- Limiting concurrent sessions per policy.
- Registering the session in a session registry.
- Handling other session mechanisms tied to a fresh login.

**Important:** the base class has a default no-op strategy if you do not configure one. Do not assume that seeing the method called means every **custom filter** has session fixation protection. Standard `formLogin(...)`/security DSL wires session management automatically; when instantiating a filter manually with `new`, you must supply the right strategy for your security policy.

### When SessionAuthenticationStrategy Fails

A strategy can throw `SessionAuthenticationException` (a subclass of `AuthenticationException`), for example when violating a session limit. In Spring Security 6.5's flow, that exception routes to the failure path. **Even a verified password does not guarantee login success** if session policy forbids it.

Do not place non-idempotent operations arbitrarily inside a session strategy or catch the exception and continue as success. Changing/rotating session IDs also needs coordination with `SecurityContextRepository`, response cookies, and logout.

## 8. `successfulAuthentication`: Work Done When a Login Request Succeeds

Once the manager and session strategy complete, the base class runs the success branch. In Spring Security 6.5.11, the core actions include:

1. Create a `SecurityContext` for the current request and set the newly verified `Authentication`.
2. Set the context on the configured `SecurityContextHolderStrategy` so code in the current execution context can access it.
3. **Save** the context through the `SecurityContextRepository` **configured on the filter**.
4. Notify `RememberMeServices.loginSuccess(...)`.
5. Publish `InteractiveAuthenticationSuccessEvent` when an `ApplicationEventPublisher` is present.
6. Invoke `AuthenticationSuccessHandler.onAuthenticationSuccess(...)` to decide the redirect/status/body.

**Exact ordering** matters if the success handler calls `sendRedirect(...)` or commits the body: saving the session/context before the response commits allows the next request to restore the identity.

### Current Context vs. Persistence

`SecurityContextHolder.getContext().setAuthentication(...)` (or setting a new context) only makes authentication present within the current execution scope. It **does not automatically create a persistent login session across requests** unless the context is saved to an appropriately persistent repository.

`AbstractAuthenticationProcessingFilter.setSecurityContextRepository(...)` lets you set the repository. The 6.5.11 API docs explicitly note that **the base filter's own default does not automatically save to a persistent store** without configuration. When using a filter created by `formLogin`/DSL, the configuration may attach the repository for you. When **instantiating a custom filter with `new`**, set the repository explicitly per your architecture.

Example:

```java
SecurityContextRepository repository =
        new DelegatingSecurityContextRepository(
                new RequestAttributeSecurityContextRepository(),
                new HttpSessionSecurityContextRepository());

filter.setSecurityContextRepository(repository);
```

This is a **configuration snippet**, requiring imports and the filter object. The delegating repository saves to a request attribute for internal dispatches and to `HttpSession` to retain login across requests, if policy allows.

**If you choose `RequestAttributeSecurityContextRepository` alone**, the login request has the context, but the **next** HTTP request will not automatically retain that identity. The console example in section 12 intentionally uses the request-only repository to inspect behavior **without creating an HTTP session**.

### Remember-me: A Separate Feature

`RememberMeServices.loginSuccess` can create/handle a remember-me token or cookie if configured and policy conditions are met. It is **not synonymous** with a session cookie and does not create a remember-me cookie on every login by default. A configuration without remember-me typically uses a no-op implementation.

Do not implement remember-me by stuffing a username into a cookie. Tokens require cryptographic signing or random series/tokens, binding, expiry, revocation handling, and theft protection.

### InteractiveAuthenticationSuccessEvent

This event represents a successful interactive login. It is not proof that **every authenticated request** emits a new event; a request arriving with an existing session does not go through the login filter.

Audit logging on success can use an appropriate event/handler, but never rely solely on this event to grant business permissions or update balances. Event delivery and business transactions are not automatically atomic.

### The Default Success Handler Can Redirect

`SavedRequestAwareAuthenticationSuccessHandler` is the base filter's default choice. It can prioritize the URL the user was trying to visit before login (saved request), or use a configured target URL. That is why many successful form logins return a **302 redirect** rather than JSON 200.

If you want a REST endpoint to return `204` or structured JSON, configure a dedicated `AuthenticationSuccessHandler`. It **handles the response** and must never decide credentials are valid before a provider verifies them.

## 9. `unsuccessfulAuthentication`: Failure Is a Controlled Branch

When `attemptAuthentication` throws `AuthenticationException`, or related authentication/session steps fail per contract, the filter invokes the failure branch:

1. **Clear `SecurityContextHolder`** for the current execution context.
2. Call `RememberMeServices.loginFail(...)` to cancel/adjust remember-me per policy.
3. Call `AuthenticationFailureHandler.onAuthenticationFailure(request,response,exception)`.
4. Return control per filter lifecycle; never grant an authenticated `Authentication` from a failed attempt.

In some older APIs/configurations, error details were stored in the session to re-display on the form. Details **depend on the failure handler and session-creation policy**; do not assume every failure writes a session attribute or creates a new session.

### Does It Return 401 or Redirect by Default?

With `SimpleUrlAuthenticationFailureHandler`:

- No failure URL configured: it can send HTTP **401**.
- If a failure URL is configured: it can redirect to the login page with a generic error signal.

Standard `formLogin` configurations may choose their own handling URL. A Java `BadCredentialsException` does not automatically imply HTTP 401 or 403 in every application; the **failure handler** decides how the response is presented.

**Do not disclose account existence** just to show "wrong username" differently from "wrong password"; public APIs should generally return a consistent authentication failure message. Internal logs may classify safely per policy without recording raw passwords, tokens, or the full `Authentication`.

### Failure Does Not Mean All Sessions Are Logged Out

`SecurityContextHolder.clearContext()` only clears the context on the current thread/strategy. Another HTTP session belonging to the same user may still remain valid. If account locking is required or credential stuffing is suspected, separate session invalidation/token revocation mechanisms are needed.

If a user **already has an existing logged-in session** and submits a wrong login again in the same browser, how the session/context is handled depends on policy and filter configuration; do not deduce it solely from the exception name.

## 10. Three Attempt Outcomes and FilterChain: Quick Reference Table

| Case | Calls manager? | Session strategy? | New context saved? | Handler? | Default `chain.doFilter`? |
| --- | --- | --- | --- | --- | --- |
| Matcher does not match | No | No | Not by this filter | None | **Yes** |
| Returns `Authentication` | Yes, if subclass calls manager | Yes | Yes if repository configured to save | Success | **No** |
| Throws `AuthenticationException` | Usually yes, though pre-validation may fail first | No, unless error in strategy itself | Not from success path | Failure | **No** |
| Returns `null` (pending) | Depends on subclass | No | Not from success path | Neither success nor failure | **No** |
| Session strategy throws `SessionAuthenticationException` | Already got manager result | Running and failed | Not from success path | Failure | **No** |

**This is the normal behavior with `continueChainBeforeSuccessfulAuthentication=false`.** If this special flag is enabled, the success path runs the chain **before** `successfulAuthentication`. That can make downstream code run before the holder contains the new login result and before the success handler runs, which is uncommon for login endpoints.

### What Is `setContinueChainBeforeSuccessfulAuthentication(true)`?

This option serves specialized integration environments. When enabled:

```text
attemptAuthentication -> session strategy -> chain.doFilter
                                         -> successfulAuthentication
                                         -> successHandler
```

Downstream filters in the chain **may not yet see the new authentication** when they execute, and then the success handler still controls the response; if the response is already committed, redirects or saving can fail. Do not enable it just thinking "a successful request must continue to the controller". For form login, having **the filter consume the login request** and hand off to the success handler is the intended design.

If you need an API that accepts a JWT on every request and lets the controller handle it, use an appropriate authentication filter model such as `AuthenticationFilter` or a resource-server token filter, rather than flipping this chain flag.

## 11. Example Spring Boot Servlet Config and Where Custom Filters Attach

### 11.1. Use Standard Form Login When Appropriate

If the requirement is simply a username/password form, **prefer `formLogin(...)`** instead of writing a new subclass:

```java
@Configuration
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login", "/css/**").permitAll()
                .anyRequest().authenticated())
            .formLogin(form -> form
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .usernameParameter("username")
                .passwordParameter("password")
                .defaultSuccessUrl("/home", false)
                .failureUrl("/login?error"))
            .logout(Customizer.withDefaults());

        return http.build();
    }
}
```

This is a **configuration excerpt**, omitting the login page/controller, `UserDetailsService`, `PasswordEncoder`, database, or form CSRF token. `loginProcessingUrl` is the endpoint **handled by the filter**, whereas `loginPage` is the page/form seen by the user. Do not create a `@PostMapping("/login")` controller on the same endpoint already consumed by `UsernamePasswordAuthenticationFilter` without a clear purpose and ordering.

Session-based form login typically requires **CSRF** protection: the HTML POST form must send the valid token, and the session cookie needs `Secure`/`HttpOnly`/`SameSite` per architecture. Do not disable `csrf().disable()` globally just because a demo form failed to submit.

### 11.2. When Should You Write a Subclass Yourself?

A custom `AbstractAuthenticationProcessingFilter` subclass may be needed when an authentication mechanism has **its own interactive endpoint/format** not conveniently supported by an existing filter—such as a multi-step login protocol or a specialized payload/credential that has been properly designed and audited.

Before deciding to subclass, consider:

- `UsernamePasswordAuthenticationFilter` with custom parameter names or a custom `AuthenticationConverter` if only minor form-data adjustments are needed.
- `AuthenticationFilter` with an `AuthenticationConverter` and handlers for general request-to-authentication flows with less subclass coupling.
- Dedicated framework OAuth2/OIDC/SAML/WebAuthn/token filters when matching standard protocols; avoid hand-rolling cryptographic verifiers or callbacks.
- Whether authentication genuinely needs state/session or should be stateless per request.

**Do not copy existing filter code just to change a URL**, because `formLogin().loginProcessingUrl(...)` already provides that capability.

### 11.3. Registering a Filter Exactly Once

A custom filter must live in the right **`SecurityFilterChain`**, in the right order relative to other filters, using appropriate manager/repository/handlers. If you mark a filter with `@Component` (Servlet container auto-registration) **and** call `http.addFilterBefore/After`, it may run **twice**—both outside and inside the Spring Security chain.

With Spring Boot, pay attention to `FilterRegistrationBean`/`@Bean` registration and the Spring Security DSL. **Never** accidentally let a filter with a manager/handler execute outside the security context, bypassing CSRF or the session strategy.

If you have multiple `SecurityFilterChain`s for `/api/**` and `/**`, determine which chain owns the filter and which URL is the login endpoint. A filter placed in a different chain will not be invoked even if its internal URL matcher would match.

## 12. Runnable Java 17 Example: Four Branches of the Real Filter

This console program uses **Spring Security Web 6.5.11 + Spring Framework Mock Servlet** to run a real `AbstractAuthenticationProcessingFilter` without starting a web server. It verifies:

1. `GET /login-demo` does not match the POST matcher, so it delegates down the chain.
2. `POST /login-demo` with the right password calls the manager, session strategy, success handler, and saves `SecurityContext` into a **request attribute**.
3. `POST /login-demo` with the wrong password calls the manager and failure handler, and saves no new authentication.
4. `POST /login-demo` with the special username `pending` simulates `attemptAuthentication` returning `null` and setting `202` itself; manager, handlers, and session strategy are not invoked.
5. A `POST` to another URL does not match the matcher and continues down the chain.

**Security limitation:** the demo manager only compares two hard-coded strings to illustrate **control flow**, not production password storage. Do not reuse this check for real users. In production, the manager must use an appropriate provider and `PasswordEncoder`, accounts from a trusted user store, and full status checks.

### 12.1. Project Structure

```text
authentication-filter-flow-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/
    └── FilterFlowDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'authentication-filter-flow-demo'
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
    mainClass = 'demo.FilterFlowDemo'
}
```

In a real Spring Boot project, let a supported Boot version's BOM/dependency management coordinate compatible Spring/Spring Security libraries. The versions above are fixed **for the console demo** to demonstrate the Spring Security 6.5.11 API.

### 12.2. File `src/main/java/demo/FilterFlowDemo.java`

```java
package demo;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.authentication.AbstractAuthenticationProcessingFilter;
import org.springframework.security.web.context.RequestAttributeSecurityContextRepository;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

public final class FilterFlowDemo {

    static final class DemoFilter extends AbstractAuthenticationProcessingFilter {

        DemoFilter(AuthenticationManager manager) {
            // AntPathRequestMatcher is only to illustrate the 6.5 API;
            // for new projects use the currently recommended matcher.
            super(new AntPathRequestMatcher("/login-demo", "POST"), manager);
        }

        @Override
        public Authentication attemptAuthentication(
                HttpServletRequest request,
                HttpServletResponse response)
                throws AuthenticationException, IOException, ServletException {

            String username = request.getParameter("username");

            // Simulates a multi-step flow that already sent a response.
            // This is NOT an MFA implementation.
            if ("pending".equals(username)) {
                response.setStatus(202);
                return null;
            }

            String password = request.getParameter("password");
            Authentication input =
                    UsernamePasswordAuthenticationToken.unauthenticated(
                            username, password);

            return getAuthenticationManager().authenticate(input);
        }
    }

    private static void runCase(
            String label,
            DemoFilter filter,
            RequestAttributeSecurityContextRepository repository,
            AtomicInteger managerCalls,
            AtomicInteger sessionCalls,
            String method,
            String path,
            String username,
            String password) throws IOException, ServletException {

        SecurityContextHolder.clearContext();

        MockHttpServletRequest request =
                new MockHttpServletRequest(method, path);
        request.setServletPath(path);
        request.setParameter("username", username);
        request.setParameter("password", password);

        MockHttpServletResponse response = new MockHttpServletResponse();

        int[] chainCalls = {0};
        FilterChain chain = (servletRequest, servletResponse) ->
                chainCalls[0]++;

        int managerBefore = managerCalls.get();
        int sessionBefore = sessionCalls.get();

        filter.doFilter(request, response, chain);

        Authentication current =
                SecurityContextHolder.getContext().getAuthentication();
        String principal = current == null
                ? "(none)" : current.getName();

        System.out.println(label
                + ": http=" + response.getStatus()
                + ", chain=" + chainCalls[0]
                + ", manager=" + (managerCalls.get() - managerBefore)
                + ", session=" + (sessionCalls.get() - sessionBefore)
                + ", saved=" + repository.containsContext(request)
                + ", principal=" + principal);

        SecurityContextHolder.clearContext();
    }

    public static void main(String[] args)
            throws IOException, ServletException {

        AtomicInteger managerCalls = new AtomicInteger();
        AtomicInteger sessionCalls = new AtomicInteger();

        // Mock manager for demo only. DO NOT store or compare plaintext
        // with String.equals in a real application.
        AuthenticationManager manager = input -> {
            managerCalls.incrementAndGet();

            if ("lan".equals(input.getName())
                    && "DemoPass123!".equals(input.getCredentials())) {
                return UsernamePasswordAuthenticationToken.authenticated(
                        "lan", null,
                        AuthorityUtils.createAuthorityList("ROLE_READER"));
            }

            throw new BadCredentialsException("Invalid credentials");
        };

        DemoFilter filter = new DemoFilter(manager);

        RequestAttributeSecurityContextRepository repository =
                new RequestAttributeSecurityContextRepository();

        filter.setSecurityContextRepository(repository);

        // Callback counter only; NOT real session fixation protection.
        filter.setSessionAuthenticationStrategy(
                (authentication, request, response) ->
                        sessionCalls.incrementAndGet());

        filter.setAuthenticationSuccessHandler(
                (request, response, authentication) ->
                        response.setStatus(204));

        filter.setAuthenticationFailureHandler(
                (request, response, exception) ->
                        response.setStatus(401));

        // Self-constructed filter not managed by Spring: verify manager is set.
        filter.afterPropertiesSet();

        runCase("notMatchedMethod", filter, repository,
                managerCalls, sessionCalls,
                "GET", "/login-demo", "lan", "DemoPass123!");

        runCase("success", filter, repository,
                managerCalls, sessionCalls,
                "POST", "/login-demo", "lan", "DemoPass123!");

        runCase("failure", filter, repository,
                managerCalls, sessionCalls,
                "POST", "/login-demo", "lan", "wrong-password");

        runCase("pending", filter, repository,
                managerCalls, sessionCalls,
                "POST", "/login-demo", "pending", "unused");

        runCase("notMatchedPath", filter, repository,
                managerCalls, sessionCalls,
                "POST", "/another-path", "lan", "DemoPass123!");
    }
}
```

### 12.3. Run Command

In the directory containing `build.gradle`, using JDK 17+ and a compatible Gradle/Gradle Wrapper:

```bash
gradle run --quiet
```

**Expected program stdout**, ignoring deprecation warnings or Gradle/framework logs:

```text
notMatchedMethod: http=200, chain=1, manager=0, session=0, saved=false, principal=(none)
success: http=204, chain=0, manager=1, session=1, saved=true, principal=lan
failure: http=401, chain=0, manager=1, session=0, saved=false, principal=(none)
pending: http=202, chain=0, manager=0, session=0, saved=false, principal=(none)
notMatchedPath: http=200, chain=1, manager=0, session=0, saved=false, principal=(none)
```

These lines reflect **a single filter running against mock Servlet requests and configured handlers**, not an entire web application. Each case creates a new request, so the request-attribute repository does not carry data from previous cases. The 200 status when the matcher does not match is `MockHttpServletResponse`'s default in the demo because the downstream chain only increments a counter without writing a body or status.

### 12.4. Reading Each Branch in stdout

**`notMatchedMethod`:** the matcher requires POST, so GET does not invoke `attemptAuthentication`; neither manager nor session strategy runs. The filter forwards to `FilterChain` once.

**`success`:** the filter reads form parameters, the manager returns a trusted `Authentication` (mocked), the session strategy is called once, `successfulAuthentication` sets the holder and saves the context in the request attribute, and the success handler returns HTTP 204. The chain does not run because this login endpoint was consumed by the filter.

**`failure`:** the manager throws `BadCredentialsException`. The failure path clears `SecurityContextHolder`, invokes the handler returning HTTP 401, and saves no context in the request repository. The demo does not configure an active remember-me service.

**`pending`:** the subclass intentionally sets 202 and returns `null` before calling the manager. The filter does not call the session strategy, success/failure handlers, or chain. It simulates the "incomplete" contract, **not a secure MFA flow**.

**`notMatchedPath`:** HTTP method is POST, but the path differs from `/login-demo`. The filter continues the chain without authenticating or creating a context.

### 12.5. What the Demo Cannot Prove

- **Does not** prove BCrypt/PBKDF2/Argon2, because the mock manager compares fake strings to exercise branches. In real systems, use `ProviderManager` + an `AuthenticationProvider` such as `DaoAuthenticationProvider` and a `PasswordEncoder`.
- **Does not** prove `HttpSession` login persistence: the demo deliberately chose the request-attribute repository.
- **Does not** simulate `JSESSIONID` cookies, session ID rotation, CSRF, remember-me tokens, `ERROR` servlet dispatches, redirects, or logout.
- **Does not** guarantee the behavior of a filter registered in a Spring Boot chain if order, matcher, strategy, or repository differs.
- **Is not** a complete MFA or custom login protocol template; never use `pending` this way to protect real accounts.
- **Does not** measure timing attacks, exception message exposure, or session concurrency.

To apply this knowledge in production, implement and test the real filter chain together with dependency injection, a Servlet container, and full security configuration.

## 13. AuthenticationSuccessHandler/FailureHandler: Responses Do Not Replace Security

### 13.1. For Browser/Form Login

Common handlers:

- `SavedRequestAwareAuthenticationSuccessHandler`: can send the user back to the resource they were trying to access before login.
- `SimpleUrlAuthenticationSuccessHandler`: redirects to an appropriate target URL.
- `SimpleUrlAuthenticationFailureHandler`: redirects to an error page or sends 401 when no error URL is set.

When using saved requests, verify that target URLs are trustworthy—never read an arbitrary `redirectUrl` from the client and redirect to an arbitrary domain (open redirect). `RequestCache` and default handlers have built-in rules, but custom code must never skip validation.

### 13.2. For JSON APIs

A JSON handler can:

- Return a clear HTTP status and a consistently formatted JSON body.
- Omit credentials, hashes, and stacktraces from responses.
- Use a generic error message for wrong username/password to prevent enumeration.
- Limit response size and avoid writing twice after the response commits.

Do not simply swap in a JSON success handler and declare authentication stateless. If the repository still writes to `HttpSession`, the app may **still be using sessions**. Token issuance, refresh, expiry, and revocation require dedicated design.

### 13.3. When Is the Outcome 401, 403, or 302?

| Scenario | Typical behavior | Deciding component |
| --- | --- | --- |
| Unauthenticated access to protected URL | 302 to login or HTTP 401 | `AuthenticationEntryPoint`/exception handling |
| POST login with wrong password | 302 to `login?error` or HTTP 401 | `AuthenticationFailureHandler` |
| Valid login, browser form | 302 to saved request/success URL | `AuthenticationSuccessHandler` |
| Valid login, custom API | 200/204/JSON per design | Success handler |
| Authenticated but missing permission | Usually HTTP 403 | Authorization/`AccessDeniedHandler` |

Do not hard-associate `BadCredentialsException` with 403, nor assume HTTP 204 alone proves valid credentials if a handler was invoked out of order by custom code.

## 14. Core Security When Customizing Filters

### 14.1. Mark Authenticated Only After Verification

**Wrong:**

```java
// DANGEROUS: client picks name and authority and is blindly trusted.
return UsernamePasswordAuthenticationToken.authenticated(
        request.getParameter("username"),
        null,
        AuthorityUtils.createAuthorityList("ROLE_ADMIN"));
```

**Right in principle:**

```java
Authentication candidate =
        UsernamePasswordAuthenticationToken.unauthenticated(
                username, submittedPassword);

return authenticationManager.authenticate(candidate);
```

The client is the source of a **credential claim**, not the source of authorization decisions. Authority data must come from a trusted provider/store after verification.

### 14.2. Do Not Hash or Normalize Passwords Manually in the Filter

The filter should extract the password per protocol format and pass the raw password to the provider/encoder according to contract. Do not:

- `strip()`, `trim()`, lower-case, or arbitrarily normalize passwords.
- Write passwords into audit logs, MDC, exceptions, tracing, or request dumps.
- Call `encoder.encode(raw).equals(storedHash)` to compare BCrypt or salted KDFs.
- Put passwords into query strings or redirect URLs.

Username lookup may require canonicalization per policy, but it must align consistently with registration and the user store; never apply username transformations to passwords.

### 14.3. CSRF, Brute Force, Session Fixation, and Remember-me

A login-processing filter **does not replace**:

- **CSRF protection** for cookie/session endpoints, especially form POSTs and state-changing endpoints.
- **Rate limiting / credential stuffing defense** at gateway/service level by user/IP/device, with policies that do not enumerate accounts.
- **Session fixation protection** after successful authentication; needs a proper session strategy, not just creating any session.
- **HTTPS and cookie policies**: `Secure`, `HttpOnly`, `SameSite` per architecture.
- **MFA/step-up**, password reset, and account recovery have dedicated flows.
- **Logout and session revocation** on password change, account lock, or explicit session termination.

If you build a filter in tests with a counting lambda as `SessionAuthenticationStrategy`, **do not** use that as your production session mechanism. Wire it to a properly configured standard strategy.

### 14.4. Preventing SecurityContext and Credential Leaks

After a request completes, the Spring Security filter chain manages the `SecurityContextHolder` lifecycle, including clearing the context when appropriate. However, if custom code spawns threads or async tasks, it must never leave a previous user's `ThreadLocal` on a thread used by a later request. Use standard context propagation and explicit cleanup.

`ProviderManager` erases credentials after successful authentication by default for supported objects; do not assume custom principals automatically wipe all password hashes. Never store JPA entities, lazy proxies, or entire request objects in the session principal.

## 15. Maintenance and Testing in Real Spring Security Applications

### 15.1. Essential Test Matrix

| Test | Setup | What must be verified |
| --- | --- | --- |
| Matcher method mismatch | GET to POST login URL | Filter does not call manager; chain continues. |
| Matcher path mismatch | POST to another URL | Does not intercept wrong request; chain continues. |
| Valid login | Valid credentials via real provider | Session strategy, success handler, context saved per policy. |
| Wrong login | Wrong password | Failure handler; no trusted authentication created. |
| User not found | Non-existent username | Safe response, no enumeration details leaked. |
| User disabled/locked/expired | Valid password but invalid status | Provider rejects; no success context. |
| `attemptAuthentication == null` | Simulated multi-step with response | No premature success/failure; valid continuation mechanism. |
| Session strategy rejects | Exceeds session limit/policy violation | Failure path, no session granted. |
| `continueChainBeforeSuccessfulAuthentication` | Intentional custom usage | Downstream/holder/response ordering matches expectations. |
| Session context | Session/delegating repository | Next request with same cookie restores authentication. |
| Request-only context | `RequestAttribute` repository | Next request does not retain login. |
| Success redirect | Form login and `RequestCache` | Hits saved request or fallback URL, no open redirect. |
| Session fixation | Existing session before login | Session ID rotates per policy and state stays valid. |
| Login CSRF | Cookie/session form | Missing/invalid token rejected where CSRF is required. |
| Failure UI | Browser/REST | Safe status/redirect and generic error message. |
| Multiple filter chains | URL belongs to right chain | Only expected filter runs; no double registration. |

### 15.2. How to Use `@WithMockUser`?

`@WithMockUser` populates a security context for authorization tests. It **does not prove**:

- `requiresAuthentication` matched properly.
- `attemptAuthentication` invoked the manager.
- `PasswordEncoder.matches` ran.
- Session strategy or success/failure handlers were called.
- `SecurityContextRepository` persisted the session across requests.

To test real login, use `MockMvc` with the Spring Security filter chain, `WebEnvironment` tests, or invoke the filter/provider as in the console example. For session-backed apps, tests must pass the same `MockHttpSession`/cookie across requests and verify persistence/invalidation.

### 15.3. Observing Production Errors Without Leaking Passwords

You can log or emit metrics for signals such as:

- Aggregated login attempts/successes/failures per endpoint and failure category.
- Latency of `AuthenticationManager`/providers and failure handlers.
- Rates of locked/disabled account statuses, rate-limiter triggers, and CSRF failures.
- Session strategy exceptions, session creation/rotation, and replay anomalies.
- Invocation counts of a custom filter within a single HTTP request, helping detect double registration.

**Strictly avoid:** raw passwords, `Authorization` headers, reset tokens, TOTP secrets, full `Authentication.credentials`, intact password hashes, or stacktraces containing sensitive data. If auditing needs a user identifier, apply data minimization and strict audit access controls.

## 16. Common Mistakes

1. **Equating `AbstractAuthenticationProcessingFilter` with `AuthenticationProvider`.** The filter orchestrates HTTP; the provider verifies credentials.
2. **Assuming every request passing through the filter is a login.** The matcher selects login requests; other URLs must continue down the chain.
3. **Ignoring HTTP method when matching the login URL.** Risks accepting GET and leaking credentials in query strings/URLs.
4. **Returning `UsernamePasswordAuthenticationToken.authenticated(...)` from client input.** Skips verification and risks arbitrary privilege escalation.
5. **Returning `null` on a wrong password.** `null` signals an incomplete flow; failure must throw an appropriate `AuthenticationException`.
6. **Calling `AuthenticationManager` but skipping the session strategy.** Custom filters can miss session fixation protection or session limits.
7. **Assuming the default `SessionAuthenticationStrategy` always prevents fixation when instantiating a filter with `new`.** The default can be a no-op; wire it explicitly.
8. **Calling only `SecurityContextHolder.setContext` and expecting the next request to stay logged in.** The context must be saved into an appropriately persistent repository.
9. **Assuming every base filter auto-saves to session.** The API exposes `setSecurityContextRepository`; the default does not guarantee durable persistence.
10. **Using `RequestAttribute` repository alone when login must span new requests.** A new request does not carry previous request attributes.
11. **Calling `chain.doFilter` manually after the success handler has committed.** Can write a response body twice or break filter semantics.
12. **Enabling `setContinueChainBeforeSuccessfulAuthentication(true)` thinking it means pass-through filter.** It changes ordering so the chain runs before auth success is set/saved, usually undesirable.
13. **Assuming `AuthenticationSuccessHandler` verifies passwords.** The handler only receives an already-verified result from upstream.
14. **Confusing `AuthenticationEntryPoint` with `AuthenticationFailureHandler`.** One prompts to start login; the other reports a failed login attempt.
15. **Believing HTTP 401 always logs the user out.** Status codes/handlers do not automatically invalidate all sessions or tokens.
16. **Failing to implement failure handlers safely.** Can leak account existence, internal exceptions, or stacktraces.
17. **Disabling CSRF globally because login POST didn't work.** Send the proper CSRF token or design a valid token/cookie policy instead.
18. **Not checking cookies and session IDs after login.** Authentication succeeds yet the session is not stored/sent, causing a "login again" UX loop.
19. **Registering a filter both as `@Component` and in the Spring Security DSL.** The filter may run twice or outside the right context.
20. **Using `@WithMockUser` as proof of login testing.** It typically bypasses matchers, providers, and handlers.
21. **Writing raw passwords into audit/error logs for debugging.** Authentication secrets leak into the logging system.
22. **Thinking a filter grants admin privileges just because the client sent roles.** Authorities must be issued by a trusted provider/store.
23. **Not testing behavior when the session strategy throws an exception.** Even a correct password can be rejected by session policy.
24. **Mixing session-based login with a stateless API without clearly defining the repository.** The system may issue tokens while accidentally retaining sessions.
25. **Overriding `successfulAuthentication` and forgetting `super`/context saving.** Loses remember-me, events, context persistence, or expected handler behavior.
26. **Overriding `unsuccessfulAuthentication` and forgetting to clear the holder.** Risks leaving stale authentication on the request/thread.
27. **Applying inconsistent username normalization in the filter vs. the store.** Causes lookup failures, duplicate identities, or account confusion.
28. **Letting the user principal reference a lazy JPA entity beyond the transaction.** Keeping the context in session does not keep the ORM Session open.
29. **Assuming the interactive success event automatically grants business permissions.** Events/audits are informational and do not replace domain authorization.
30. **Testing only the happy path while skipping null/failure/non-matching branches.** The filter has multiple critical branches that need regression protection during refactoring.

## 17. Self-Check Questions

**Question 1.** How does `AbstractAuthenticationProcessingFilter` differ from `DaoAuthenticationProvider`?

**Answer:** The filter matches/receives HTTP requests, invokes `AuthenticationManager`, and coordinates session/context/handlers. `DaoAuthenticationProvider` is a provider that checks username/password hashes and account status via `UserDetailsService` and `PasswordEncoder`.

**Question 2.** Does `requiresAuthentication` returning false mean the request is already authenticated?

**Answer:** No. It only indicates that this filter does not treat the request as a login attempt and normally passes it along the filter chain.

**Question 3.** What are the valid ways `attemptAuthentication` can finish?

**Answer:** Return a verified `Authentication` on success, throw an `AuthenticationException` on failure, or return `null` if the process is not yet complete and the subclass has already handled the response/transition to the next step.

**Question 4.** If `attemptAuthentication` returns `null`, do success or failure handlers run?

**Answer:** Not along the default path. The filter returns immediately without running the session strategy or saving a success context.

**Question 5.** Does `sessionAuthenticationStrategy.onAuthentication` run before or after `successfulAuthentication`?

**Answer:** After the attempt returns a verified `Authentication`, and **before** `successfulAuthentication`. Session policy failures can send login down the failure path.

**Question 6.** Why can a custom filter that calls `SecurityContextHolder.setContext` still leave the next request anonymous?

**Answer:** The holder only holds the current context; it must be saved to an appropriate `SecurityContextRepository` (such as session/delegating) with a valid cookie/session so the next request can restore it.

**Question 7.** Should `setContinueChainBeforeSuccessfulAuthentication(true)` be enabled so a controller receives a login POST after authentication?

**Answer:** Usually no. It runs the chain before success processing, which can mean downstream code does not yet see the new authentication and responses get processed out of order. Use an appropriate success handler or endpoint design instead.

**Question 8.** Why is a failure handler not an authentication entry point?

**Answer:** A failure handler reports the outcome of a failed login attempt; an entry point challenges the user to initiate authentication when attempting to access a protected resource.

**Question 9.** Which parameters does `UsernamePasswordAuthenticationFilter` read by default?

**Answer:** `username` and `password` from the form, with the default login processing URL `/login`; parameter names and URL can be configured via `formLogin`/filter APIs.

**Question 10.** Is instantiating a filter with `new` and setting only the manager enough to prevent session fixation?

**Answer:** No. You also need the right `SessionAuthenticationStrategy`, context repository, cookie/session policy, CSRF, handlers, and integration tests. The manager only verifies credentials.

**Question 11.** Why doesn't `@WithMockUser` prove that the login filter works?

**Answer:** Mock user tests typically pre-populate `SecurityContext` without executing the matcher, `attemptAuthentication`, manager, session strategy, or handlers.

**Question 12.** When login fails, what should `unsuccessfulAuthentication` do?

**Answer:** Clear the current context, notify remember-me of the failure, and delegate response handling to the failure handler; never issue a trusted `Authentication`.

**Question 13.** A POST is valid and the manager succeeds, but the filter has no persistent repository configured. What happens?

**Answer:** The user can be authenticated within the current login request and the success handler still runs, yet subsequent requests will not necessarily restore the context. A persistent repository suited to a session-backed model is required.

**Question 14.** Why is a JSON 204 API response insufficient to prove a real login mechanism is secure?

**Answer:** A handler can return 204 in a demo without providers or security policies being tested. You must verify real passwords, user status, session/CSRF, brute-force defenses, context persistence, and token policies across the full filter chain.

## 18. Official References

- [Spring Security 6.5.11 — AbstractAuthenticationProcessingFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AbstractAuthenticationProcessingFilter.html): `requiresAuthentication`, the three outcomes of `attemptAuthentication`, session strategy, handlers, repository, and filter chain behavior.
- [Spring Security 6.5 — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): interplay among `SecurityContextHolder`, `AuthenticationManager`, `AuthenticationProvider`, entry points, and `AbstractAuthenticationProcessingFilter`.
- [Spring Security 6.5.11 — UsernamePasswordAuthenticationFilter API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/UsernamePasswordAuthenticationFilter.html): form fields, POST, `/login`, and subclass behavior.
- [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContextHolderFilter`, explicit context save, session strategies, and migration.
- [Spring Security 6.5 — Persisting Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html): `SecurityContextRepository`, HttpSession/RequestAttribute/Delegating repositories, and persistence.
- [Spring Security 6.5.11 — SessionAuthenticationStrategy API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/session/SessionAuthenticationStrategy.html): callback after fresh authentication and session management strategies.
- [Spring Security 6.5.11 — AuthenticationSuccessHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationSuccessHandler.html): contract for handling responses after successful login.
- [Spring Security 6.5.11 — AuthenticationFailureHandler API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/AuthenticationFailureHandler.html): contract for handling authentication failures.
- [Spring Security 6.5.11 — RememberMeServices API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/authentication/RememberMeServices.html): `loginSuccess`, `loginFail`, and remember-me tokens/cookies.
- [Spring Framework 6.2 — MockHttpServletRequest API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/mock/web/MockHttpServletRequest.html): mock Servlet request for the Java 17 example.

**Conclusion:** `AbstractAuthenticationProcessingFilter` is the **login-request orchestrator inside the Servlet filter chain**. It selects requests via `RequestMatcher`, delegates actual verification to `AuthenticationManager` through `attemptAuthentication`, and handles exactly three outcomes: authenticated, failed, or pending. On success, pay attention to **session strategy → SecurityContext/Repository → remember-me/event → success handler**; on failure, clear the context and hand response control to the failure handler. With custom code, the biggest responsibility is **never granting identity solely from client input**, never omitting session/CSRF protections, and never forgetting authentication persistence when identity must span multiple HTTP requests.