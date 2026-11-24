# Ordering Filters and Avoiding Double Registration of the Same Filter

Spring Security in the **Servlet** architecture relies on a set of `Filter`s running before an HTTP request reaches controllers. Filter ordering determines **when the security context is loaded, when credentials are verified, when permissions are checked**, and whether the request continues down to `DispatcherServlet`. If an authentication filter runs too late, valid permissions can still be denied; if a filter runs too early or is auto-registered outside the security chain, it may fail to see a trusted `Authentication`. Another hazard is the same filter being registered **twice**: once automatically in the Servlet container by Spring Boot, and once inside `SecurityFilterChain` via `http.addFilterBefore/After(...)`.

This lesson belongs to the **Filter Integration** group of Spring Security Authentication. The goal is to distinguish ordering layers, understand `FilterChainProxy` and chain matchers, pick the right insertion point for custom filters, prevent duplicate auto-registration in Spring Boot, recognize the limits of `OncePerRequestFilter`, debug via filter chain logs, and write automated tests. A **standalone console Java 17** example uses real `FilterChainProxy` and mock Servlet requests to show how the exact same filter instance can be invoked twice in **a single request**.

**Core principle summary:** A custom authentication filter should appear **once, in the right `SecurityFilterChain`, in the right position after context/protection setup and before authorization**, and must only set a trusted `Authentication` after a verifier/provider has validated the input.

## 1. Three-Layer Diagram: Where Is Order Decided?

~~~text
HTTP Client
   |
   v
[1] Servlet container FilterChain
     Pre-security container Filter (if any)
     DelegatingFilterProxy("springSecurityFilterChain")
       |
       v
     [2] FilterChainProxy: evaluates SecurityFilterChains by @Order
           SecurityFilterChain #1 /api/admin/**
           SecurityFilterChain #2 /api/**
           SecurityFilterChain #3 fallback /**
           -> ONLY selects the first chain whose matcher matches
              |
              v
     [3] Filter order INSIDE THE SELECTED CHAIN
           SecurityContextHolderFilter
           security/protection filters
           LogoutFilter
           authentication filters (form / Basic / Bearer / custom)
           AnonymousAuthenticationFilter
           ExceptionTranslationFilter
           AuthorizationFilter
              |
              v
     Post-security container Filter (if any)
   |
   v
DispatcherServlet -> Controller
~~~

This diagram is **conceptual**, not a fixed filter list for every version or configuration. The exact filters present depend on `HttpSecurity`, HTTP Basic/form/JWT/OIDC, sessions, CSRF, CORS, and the request path.

| Layer | Unit being ordered | Primary mechanism | Misconception |
|---|---|---|---|
| **Container** | Registered Servlet `Filter`s, including `DelegatingFilterProxy` | `FilterRegistrationBean.setOrder`, Servlet registration | Does not determine placement between Spring Security's authentication and authorization filters |
| **Between chains** | `SecurityFilterChain` beans whose matchers the proxy tests | `@Order` on chain, `securityMatcher` | Proxy does not merge all matching chains into one |
| **Inside a chain** | Ordered list of security filters in the selected chain | Spring Security order, `addFilterBefore/After/At` | `@Order` on a custom filter class does not determine internal chain order |

Crucially, the same `Filter` class can appear in multiple layers. If it sits in both the container and the chain, a single request can pass through **both registration points**. Changing `@Order` on the bean cannot fix that.

### 1.1. DelegatingFilterProxy Does Not Authenticate Passwords

`DelegatingFilterProxy` is the bridge between the Servlet container and the Spring `ApplicationContext`. The container invokes the proxy; the proxy looks up the bean named `springSecurityFilterChain`, typically a `FilterChainProxy`. The proxy itself does not load `UserDetails`, hash passwords, or verify JWT signatures—it delegates to the Spring-managed filter.

`FilterChainProxy` selects the chain and coordinates lifecycle responsibilities like `HttpFirewall`/cleanup. Authentication filters such as `UsernamePasswordAuthenticationFilter`, `BasicAuthenticationFilter`, and `BearerTokenAuthenticationFilter` receive the corresponding credentials. Verification is performed by the appropriate `AuthenticationManager`/provider, decoder, or verifier.

### 1.2. Container FilterChain Differs from SecurityFilterChain

`jakarta.servlet.FilterChain` represents the remaining container filter chain leading to the servlet. `SecurityFilterChain` represents a **matcher + list of security filters** for a request category. When a custom filter calls `chain.doFilter(request,response)`, it lets execution continue downstream; when it does not, the request stops there intentionally.

Not calling `chain.doFilter` does not automatically mean "more secure". A filter blocking a request must emit an HTTP response/exception per protocol; a filter forwarding a request with fabricated authentication opens a vulnerability.

## 2. Ordering in the Servlet Container: @Component, @Order, and FilterRegistrationBean

In a Spring Boot Servlet app, a `Filter` declared as a Spring bean is normally auto-registered with the embedded Servlet container by Spring Boot unless disabled by registration configuration. Example:

~~~java
@Component
public final class CorrelationIdFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        // Handle request correlation ID at the container level.
        chain.doFilter(request, response);
    }
}
~~~

This is a **configuration fragment** requiring Spring Web imports and a real application context, not a standalone program. A correlation ID filter that genuinely needs no logged-in user can be **intentionally designed** to run at the container level for all URLs.

Order at this layer can be configured via:

~~~java
@Bean
FilterRegistrationBean<CorrelationIdFilter> correlationRegistration(
        CorrelationIdFilter filter) {

    FilterRegistrationBean<CorrelationIdFilter> bean =
            new FilterRegistrationBean<>(filter);
    bean.setOrder(-100);
    bean.addUrlPatterns("/*");
    return bean;
}
~~~

This Java snippet illustrates registration. It controls **Servlet container filter order**, not running the filter between `BasicAuthenticationFilter` and `AuthorizationFilter`.

### 2.1. When Is Placing a Filter in the Container Reasonable?

- Generating correlation IDs or normalizing minimal logging metadata independent of the principal.
- Generic request/response operations intentionally designed to run before the security chain.
- Infrastructure concerns governed by container/framework contracts.

If a filter needs a verified `SecurityContextHolder.getContext().getAuthentication()`, placing it **before `DelegatingFilterProxy`** will see null, anonymous, or an uninitialized context. For post-login authorization or auditing, place it inside the security chain or use framework events/handlers.

If a container filter dumps full `Authorization`/`Cookie`/password-bearing bodies for debugging, that creates a credential-leak risk. Correlation IDs should be length-bounded, never using unbounded raw user input as log keys.

## 3. Ordering Between SecurityFilterChains: First-Match Wins

`FilterChainProxy` uses **only the first `SecurityFilterChain` matching the request**. Example:

~~~text
@Order(1) /api/admin/**   -> admin token rules
@Order(2) /api/**         -> general API token rules
fallback /**              -> website session rules

GET /api/admin/users  -> admin chain
GET /api/orders       -> general API chain
GET /home             -> web chain
~~~

If fallback `/**` is evaluated first, it captures every request and the API chains never run. If **no chain matches**, the request can pass to the servlet without going through Spring Security filters for that URL—a **dangerous bypass** for protected endpoints.

### 3.1. @Order on a Chain Is Not Filter Order

~~~java
@Bean
@Order(1)
SecurityFilterChain apiSecurity(HttpSecurity http)
        throws Exception {
    http.securityMatcher("/api/**")
        .authorizeHttpRequests(a -> a
            .requestMatchers("/api/health").permitAll()
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

`@Order(1)` causes the API chain to be evaluated early. It does not mean Basic authentication runs as the very first filter. **Internal filter** ordering is handled by Spring Security and `addFilterBefore/After/At`.

### 3.2. securityMatcher Differs from requestMatchers

- `securityMatcher("/api/**")` defines the scope of **the entire security chain**.
- `requestMatchers("/api/health").permitAll()` only allows public access **within the selected chain**; protection filters remain active per config.
- `web.ignoring()` or URLs matching no chain can **skip all security filter processing**.

A public endpoint may still need HTTP headers, CORS, auditing, or context processing. That is why `permitAll` is usually better than skipping Spring Security completely.

### 3.3. Does a Filter in Two Chains Run Twice?

If the same `myFilter` object is added to both the API chain and the Web chain, since a request selects **only one chain**, that object normally runs once within the selected chain. That is **not** automatically double registration. By contrast, if the object sits **once in the container and once in the selected chain**, or is added **twice to the same selected chain**, it really can run twice.

Distinguish these three situations before changing configuration.

## 4. Filter Order Inside a Chain: Security Milestones

Spring Security designs filter ordering so requests pass through stages in the right sequence:

~~~text
SecurityContext loaded or initialized
       |
Protection: security headers, CORS, CSRF... as configured
       |
Logout handling
       |
Authentication: form, Basic, Bearer, custom API key...
       |
AnonymousAuthenticationFilter when unauthenticated
       |
ExceptionTranslationFilter
       |
AuthorizationFilter
       |
Controller if request is permitted
~~~

This diagram does not represent every possible chain identically; for example, not every API has form login, CSRF, or a bearer filter. Spring Security maintains deliberate order so unauthenticated requests cannot pass authorization as authenticated users.

### 4.1. Why Must Authentication Precede Authorization?

If a valid token arrives at the server yet a custom authentication filter runs **after** `AuthorizationFilter`, authorization sees a null/anonymous context and denies the request. The fix is placing the filter properly **after required setup/protection and before authorization**, not disabling authorization.

The reverse mistake is even more dangerous: a custom filter constructs `UsernamePasswordAuthenticationToken.authenticated(...)` solely from client-sent username/roles, bypassing `AuthenticationManager` or a JWT verifier. In that case, "right position" cannot save you because there is **no trust boundary**. Only set a trusted `Authentication` after credentials/tokens have been verified.

### 4.2. Position Must Depend on Function

| What does the custom filter do? | Which steps must have already happened? | Reference anchor |
|---|---|---|
| Extra pre-authentication protection | Context loadable, policy protections | After `SecurityContextHolderFilter` when appropriate |
| **Custom authentication** | Initial context/protection, before authorization | Typically **after `LogoutFilter`** |
| Authorization/tenant check | Principal/anonymous established | After `AnonymousAuthenticationFilter` and before downstream access is permitted |
| Audit login success/failure events | Authentication outcome, response/error policy known | Prefer success/failure handlers or Spring events if appropriate |
| Trace ID without reading security identity | Independent of auth | Can live in the Servlet container |

The suggestion to "place custom authentication filters after `LogoutFilter`" is a **common rule of thumb**, not a guarantee for every filter. An audit filter that reads the principal **after Basic/JWT verification** may need to sit after that specific authentication filter or use framework events.

## 5. The Three APIs: addFilterBefore, addFilterAfter, addFilterAt

`HttpSecurity` provides:

~~~java
http.addFilterBefore(customFilter, LogoutFilter.class);

http.addFilterAfter(customFilter, BasicAuthenticationFilter.class);

http.addFilterAt(customFilter, UsernamePasswordAuthenticationFilter.class);
~~~

These are **three independent API examples**, not three lines to use together for the same filter.

| Method | Effect | What it does NOT do |
|---|---|---|
| `addFilterBefore` | Places custom filter before a known reference filter **slot** | Does not disable old filters or container registration |
| `addFilterAfter` | Places custom filter after the reference slot | Does not force every chain to contain the filter |
| `addFilterAt` | Places custom filter **at the same position** as reference | **Does not remove the existing filter** |

### 5.1. Trap: addFilterAt Is Not Automatic Replacement

`HttpSecurity` Javadoc clearly states: if multiple filters are registered at the same position, their relative order is **unspecified**, and registering at a slot **does not override an existing filter**. Therefore:

~~~java
http.formLogin(Customizer.withDefaults());
http.addFilterAt(customLoginFilter,
                 UsernamePasswordAuthenticationFilter.class);
~~~

These two lines are a **risky counter-example** if you assume the default filter is definitely replaced. When both filters handle the login endpoint, requests can be consumed or handled by the wrong mechanism.

To replace a login mechanism, explicitly disable or reconfigure the DSL option creating the old filter, define URL/handler/entry point clearly, and inspect the **actual filter list**. Never put two filters in the same slot and rely on implicit ordering.

### 5.2. @Order on a @Component Filter Does Not Replace addFilterBefore

~~~java
@Component
@Order(5)
final class ApiKeyFilter extends OncePerRequestFilter {
    // ...
}
~~~

This is an illustrative snippet. `@Order` may affect Boot's container registration of the `Filter` bean; it **does not directly control** whether this filter runs before `AnonymousAuthenticationFilter` inside the Spring Security chain. Configure internal order through the DSL and test it.

### 5.3. What Is a Recognized Anchor?

`addFilterBefore/After/At` requires a **filter class whose position/order is registered with Spring Security**. Using an arbitrary anchor without a registered order can throw a configuration build error. Do not assume any class implementing `Filter` works as a valid anchor.

For bearer token resource servers, `BearerTokenAuthenticationFilter` belongs to OAuth2 Resource Server and is not present in a form-login-only app. Choose anchors matching your actual auth mechanisms, checking Spring Security's filter list and Javadocs for your exact version.

## 6. Double Registration in Spring Boot: Why Does It Happen?

Scenario:

~~~java
@Component
final class ApiTokenFilter extends OncePerRequestFilter {
    // doFilterInternal(...) verifies the API token via a provider.
}
~~~

and at the same time:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http,
                             ApiTokenFilter tokenFilter)
        throws Exception {
    http.securityMatcher("/api/**")
        .addFilterAfter(tokenFilter, LogoutFilter.class);
    return http.build();
}
~~~

Both are incomplete snippets lacking dependencies/authorization, yet they illustrate the bug:

~~~text
ApiTokenFilter is created as a Spring bean:
     |
     +--> Spring Boot registers the Filter bean in the Servlet container
     |       (e.g. for all requests)
     |
     '--> Security config adds that same bean into the /api/** chain

GET /api/orders:
  Servlet container -> ApiTokenFilter [registration #1]
      -> DelegatingFilterProxy -> FilterChainProxy
           -> /api/** SecurityFilterChain
                -> ApiTokenFilter [registration #2]
                -> AuthorizationFilter
      -> Controller
~~~

A single request can pass through **two registration points**. Consequences:

- Token verification or account lookups run twice, increasing latency.
- Single-use tokens are consumed on the first run and fail on the second.
- Rate limiters, metrics, and audits count twice.
- The filter reads `SecurityContextHolder` in the container before the proxy, seeing no valid principal yet.
- One invocation runs outside the chain, applying to non-API URLs.
- Body/headers get consumed or the response commits before downstream processing.
- Different dispatcher types make the issue appear only on certain requests.

**Do not conclude "only one `doFilterInternal` means safe" if the filter extends `OncePerRequestFilter`**: the marker may skip the body on the nested call, yet it is still mis-layered registration prone to timing bugs.

### 6.1. Two Prints Do Not Always Mean Two HTTP Requests

A filter written as:

~~~java
System.out.println("before");
chain.doFilter(request, response);
System.out.println("after");
~~~

naturally emits two log lines for **one invocation**. One HTTP request can also involve `ASYNC` or `ERROR` dispatches. To prove duplicate registration, inspect:

- Request correlation ID and `DispatcherType`.
- Filter **instance** identity, bean name, and layer.
- Number of times `Filter.doFilter` starts.
- Number of times `OncePerRequestFilter.doFilterInternal` actually executes.
- Which chain `FilterChainProxy` selected and how many entries of the filter sit in it.
- Whether the container has a `FilterRegistrationBean`/auto-registration for that bean.

Never print raw `Authorization`, `Cookie`, or passwords in debug logs.

## 7. Fixing at the Right Layer: Choose Container or Security Chain

### 7.1. If You Want the Filter Only in Spring Security

You can keep the filter as a Spring bean for dependency injection while **disabling automatic container registration**:

~~~java
@Configuration
class FilterRegistrationConfig {

    @Bean
    FilterRegistrationBean<ApiTokenFilter> disableContainerRegistration(
            ApiTokenFilter filter) {

        FilterRegistrationBean<ApiTokenFilter> registration =
                new FilterRegistrationBean<>(filter);
        registration.setEnabled(false);
        return registration;
    }
}
~~~

This is a Spring Boot config fragment. `setEnabled(false)` stops Boot from registering the `Filter` bean independently in the Servlet container; it **does not** remove the instance added by `http.addFilterAfter` to `SecurityFilterChain`.

This fix suits filters that must run **after Spring Security's context/protection setup** and only within the selected namespace. Verify in tests that API endpoints still traverse the security chain; disabling container registration does not widen matchers.

### 7.2. Or Do Not Declare the Instance as a Filter Bean

If the filter does not need an independent Spring bean lifecycle, instantiate it inside the security config and inject dependencies through its constructor:

~~~java
@Bean
SecurityFilterChain apiChain(HttpSecurity http,
                             ApiTokenVerifier verifier)
        throws Exception {

    ApiTokenFilter tokenFilter = new ApiTokenFilter(verifier);

    http.securityMatcher("/api/**")
        .addFilterAfter(tokenFilter, LogoutFilter.class)
        .authorizeHttpRequests(a -> a.anyRequest().authenticated());

    return http.build();
}
~~~

This is an illustrative config snippet; the project's `ApiTokenVerifier` and `ApiTokenFilter` classes must be implemented. Because no `Filter` bean exists in the container context, Boot has no filter bean to auto-register. Still, verify other registration mechanisms (e.g., `@WebFilter` or manual Servlet registration).

### 7.3. If You Want the Filter in the Container

When a filter only handles correlation IDs or principal-independent work, keep **container registration** and **do not add it** to `HttpSecurity`. Then it appears once in the container per its configured URL mapping and order.

If you need both generic request logging in the container and auth-specific auditing in the security chain, split them into **two filters with two responsibilities** or use framework events, instead of putting one bean in both layers.

### 7.4. Wrong Fixes

- Do not use `setOrder(Integer.MAX_VALUE)` to "push the duplicate registration later": two registrations still exist.
- Do not disable `DelegatingFilterProxy` to avoid running a custom filter twice; that disables Spring Security altogether.
- Do not rely solely on `OncePerRequestFilter`/markers to hide duplicates.
- Do not disable authorization/CSRF to bypass 401/403 caused by filter ordering.
- Do not add the same filter with multiple `addFilter...` calls in one chain.
- Do not remove built-in filters and entry points without a complete replacement design.

## 8. OncePerRequestFilter: Bounded Guarantee, Not a Cure for Duplicates

Spring Framework's `OncePerRequestFilter` is a base class controlling `doFilterInternal` execution within an appropriate request/dispatch scope via an **already-filtered request attribute**.

~~~text
Filter.doFilter(...) is called
    |
    v
OncePerRequestFilter.doFilter(...)
    |
    +--> Checks dispatcher type, shouldNotFilter, marker
    |
    +-- Matching marker already present
    |       -> may skip doFilterInternal, continue chain
    |
    '-- No marker yet
            -> mark request
            -> doFilterInternal(...)
            -> clear marker in finally
~~~

If the same instance is registered in the container **outside** the proxy and inside the security chain, the outer call sets the marker before the inner chain runs. When the security chain invokes the filter again, `doFilterInternal` may be skipped—meaning **authentication logic ran at the wrong time** outside the security context. Even if logs showing "logic ran once" look fine, the security design is broken.

### 8.1. Async and Error Dispatches

`OncePerRequestFilter` provides extension points:

~~~java
protected boolean shouldNotFilter(HttpServletRequest request);
protected boolean shouldNotFilterAsyncDispatch();
protected boolean shouldNotFilterErrorDispatch();
~~~

These are illustrative method signatures; defaults/overrides and Servlet dispatcher mappings govern behavior. "Once" does not strictly mean once across all `REQUEST`, `ASYNC`, `ERROR`, or other redispatches.

If **two instances** or differing bean/filter names produce distinct markers, `doFilterInternal` can still run multiple times. Furthermore, business invariants like "charge exactly once" must be enforced via domain idempotency/transactions, not `OncePerRequestFilter`.

### 8.2. When to Use OncePerRequestFilter?

It is useful for per-request custom filters, provided you have:

- Proper placement in `SecurityFilterChain`;
- A trusted verifier/provider mechanism;
- Proper response handling and `chain.doFilter` when needed;
- Token/body limits and log redaction;
- Tests for async/error dispatches and thread reuse;
- No duplicate container registration.

Never use `OncePerRequestFilter` to "ensure a user logs in only once"; that is not what this class means.

## 9. Spring Boot Config Example with Two Chains and a Custom Filter

Below are **integration snippets**, not a standalone project. They assume Spring Boot 3.x, Spring Security Servlet, and a matching `UserDetailsService`/`AuthenticationProvider` or verifier.

### 9.1. Credential-Free Trace Filter

~~~java
@Component
final class SafeTraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        // Illustrates only where to record method/path and correlation ID.
        // NEVER log Cookie/Authorization/raw passwords.
        chain.doFilter(request, response);
    }
}
~~~

### 9.2. Register the Filter at Exactly One Layer

~~~java
@Bean
FilterRegistrationBean<SafeTraceFilter> traceRegistration(
        SafeTraceFilter filter) {

    FilterRegistrationBean<SafeTraceFilter> registration =
            new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
~~~

### 9.3. Configuring Two SecurityFilterChains

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http,
                             SafeTraceFilter trace)
        throws Exception {

    http.securityMatcher("/api/**")
        .addFilterAfter(trace, LogoutFilter.class)
        .authorizeHttpRequests(a -> a
            .requestMatchers("/api/health").permitAll()
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http)
        throws Exception {

    http.authorizeHttpRequests(a -> a
            .requestMatchers("/", "/assets/**").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

**Meaning:** The API chain takes precedence, and the trace filter appears **once** in that chain. `GET /home` uses only the Web chain and never triggers the API trace filter; `GET /api/health`, though `permitAll`, still traverses the API chain. `addFilterAfter(trace, LogoutFilter.class)` only illustrates placement—it **does not prove trace sees an authenticated user**, because `BasicAuthenticationFilter` can run afterwards.

If tracing needs to audit login success/failure, framework handlers/events are better; if a filter needs the auth result, anchor it after the corresponding authentication mechanism and test when authentication blocks the request or throws an exception.

Production configuration must account for CSRF, CORS, HTTP Basic over TLS, sessions, logout, user stores, endpoint paths, and business rules. Do not copy these snippets in place of a complete security design.

## 10. Runnable Java 17 Example: Observing Single vs. Double Invocation of the Same Filter

The following program uses **real Spring Security `FilterChainProxy`** with Spring Test's `MockHttpServletRequest`. No web server is started; it invokes the proxy directly with mock Servlet requests. A plain `jakarta.servlet.Filter` named `TraceFilter` prints `enter`/`exit` before and after delegating downstream.

There are two runs against the same `/api/orders` path:

1. **ONLY SECURITY:** `audit` is only a filter inside `SecurityFilterChain`.
2. **DOUBLE REGISTERED:** outside the proxy, we intentionally invoke the same `audit` instance to simulate container auto-registration, and then inside the proxy **it runs a second time**.

### 10.1. File Structure

~~~text
filter-order-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/example/FilterOrderDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'filter-order-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
version = '1.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.security:spring-security-web:6.3.8'
    implementation 'org.springframework:spring-test:6.1.18'
    implementation 'jakarta.servlet:jakarta.servlet-api:6.0.0'
}

application {
    mainClass = 'example.FilterOrderDemo'
}
~~~

These versions pin an illustrative **Spring Security 6.3.8 / Spring Framework 6.1.18** API demo, **not a recommendation to run these exact versions in current production**. For real apps, use a supported Spring Security/Boot line with unified dependency management/BOM and security patches.

### 10.2. Complete Program

Create `src/main/java/example/FilterOrderDemo.java`:

~~~java
package example;

import java.io.IOException;
import java.util.List;

import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.web.DefaultSecurityFilterChain;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

public final class FilterOrderDemo {

    private static final String PATH = "/api/orders";

    static final class TraceFilter implements Filter {
        private final String name;

        TraceFilter(String name) {
            this.name = name;
        }

        @Override
        public void doFilter(
                ServletRequest request,
                ServletResponse response,
                FilterChain chain)
                throws IOException, ServletException {
            System.out.println("enter " + name);
            chain.doFilter(request, response);
            System.out.println("exit " + name);
        }
    }

    private static void run(
            String title,
            FilterChainProxy proxy,
            TraceFilter shared,
            boolean alsoRegisteredAtContainer)
            throws IOException, ServletException {

        MockHttpServletRequest request =
                new MockHttpServletRequest("GET", PATH);
        request.setServletPath(PATH);
        MockHttpServletResponse response =
                new MockHttpServletResponse();

        FilterChain servlet = (req, res) -> {
            HttpServletRequest http = (HttpServletRequest) req;
            System.out.println("SERVLET " + http.getRequestURI());
        };

        System.out.println("=== " + title + " ===");

        if (alsoRegisteredAtContainer) {
            shared.doFilter(
                    request, response,
                    (req, res) -> proxy.doFilter(req, res, servlet));
        } else {
            proxy.doFilter(request, response, servlet);
        }
    }

    public static void main(String[] args) throws Exception {
        TraceFilter shared = new TraceFilter("audit");

        SecurityFilterChain api = new DefaultSecurityFilterChain(
                new AntPathRequestMatcher("/api/**"),
                new TraceFilter("authentication-slot"),
                shared,
                new TraceFilter("authorization-slot"));

        FilterChainProxy proxy = new FilterChainProxy(List.of(api));

        run("ONLY SECURITY", proxy, shared, false);
        run("DOUBLE REGISTERED", proxy, shared, true);
    }
}
~~~

### 10.3. Compiling/Running with Gradle

In the project directory, if a compatible Gradle Wrapper exists:

~~~bash
./gradlew run
~~~

If only Gradle is installed, use `gradle run`. On Windows PowerShell with a wrapper, use `.\gradlew.bat run`.

Output of the `System.out.println` statements (excluding Gradle logs):

~~~text
=== ONLY SECURITY ===
enter authentication-slot
enter audit
enter authorization-slot
SERVLET /api/orders
exit authorization-slot
exit audit
exit authentication-slot
=== DOUBLE REGISTERED ===
enter audit
enter authentication-slot
enter audit
enter authorization-slot
SERVLET /api/orders
exit authorization-slot
exit audit
exit authentication-slot
exit audit
~~~

### 10.4. Line-by-Line Order Explanation

- In **ONLY SECURITY**, `/api/orders` matches `/api/**`. The proxy runs the three filters in `DefaultSecurityFilterChain`'s array order. Each prints `enter`, calls `chain.doFilter` for the next filter, and finally invokes the Servlet. As the stack unwinds, `exit` lines appear in reverse order.
- In **DOUBLE REGISTERED**, a simulated container `shared.doFilter` call outside the proxy prints `enter audit` first. When the proxy reaches that same `shared` instance inside the chain, it prints **a second time**, producing two matching `exit audit` lines—all within **one mock request** in this scenario.
- `TraceFilter` is an **order-observation marker**; it does not verify tokens or enforce real authorization. The names `authentication-slot`/`authorization-slot` grant no permissions.

The example uses plain `Filter` rather than `OncePerRequestFilter` to make double invocation directly visible. With `OncePerRequestFilter`, the inner nested call might skip `doFilterInternal` due to the request marker—which **does not prove duplicate registration is harmless**.

### 10.5. Experiments to Verify Yourself

- Swap `authentication-slot` and `authorization-slot` in `DefaultSecurityFilterChain` to observe enter/exit order flip. This models misordered filters.
- Remove `shared` from the filter list while keeping the outer proxy call: `audit` now exists only in **the container**, outside the security chain.
- Add `shared` twice inside a single `SecurityFilterChain`: one request still prints `audit` twice even without container registration.
- Add a fallback chain matching `/**` and swap its order against `/api/**`; observe how first-match affects which filters execute.
- Switch to `OncePerRequestFilter` in a test project and log `doFilter` vs. `doFilterInternal` separately.

**Limitations:** the demo does not start a Spring Boot context or real Servlet container, does not test automatic `Filter` bean registration, and includes no JWT/session/CSRF. It verifies `FilterChainProxy` behavior and duplicate invocation by simulating the container call. Boot auto-registration must be tested additionally in a real Spring Boot application as covered next.

## 11. Systematic Debugging of Filter Order and Duplicate Registration

### 11.1. Inspect Both Registration Layers

Diagnose with two separate sets of questions:

~~~text
CONTAINER
- How many registrations exist for the Filter bean?
- Is a FilterRegistrationBean auto-enabled for the custom Filter?
- Is DelegatingFilterProxy registered exactly once?
- Are order, URL mapping, and DispatcherTypes right?

SPRING SECURITY
- Which SecurityFilterChains are inside FilterChainProxy?
- Which request matcher was selected, and what is @Order?
- How many entries of the custom Filter are in the selected chain?
- Where is it placed relative to SecurityContext, auth, anonymous, authorization?
- Were both addFilterBefore and addFilterAfter called on the same instance?

RUNTIME
- One HTTP request or multiple?
- One servlet dispatch or multiple (REQUEST/ASYNC/ERROR)?
- One Filter instance or multiple?
- How many times were Filter.doFilter and doFilterInternal invoked?
- Is the current user null, anonymous, or verified authentication?
~~~

If you only read `FilterChainProxy` logs, you may see the filter inside the security chain **once** while missing the independent container auto-registration outside. Never claim "no duplicates" without checking Boot registrations.

### 11.2. Appropriate Spring Security Logging

In test/dev environments:

~~~properties
logging.level.org.springframework.security=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Startup logs normally list filters in each `DefaultSecurityFilterChain`; proxy TRACE logs show which chain and filters executed. Actual filter lists depend on Spring Security version and config—do not rely on a list copied from documentation.

Do not leave TRACE running indefinitely in production, and never dump raw `Authorization`, `Cookie`, passwords, or full principal claims. Use correlation IDs, bounded metrics, and redaction.

### 11.3. Distinguish HTTP Errors Before Moving Filters

| Symptom | Causes worth checking | What NOT to do |
|---|---|---|
| API returns 401 despite sending token | Auth filter not in selected chain, invalid token, verification error | Never build an authenticated token from raw headers |
| API returns 403 | Authorization denied or CSRF, context not set in time | Never disable CSRF/authorization app-wide |
| Login URL returns 404 | Login URL outside chain matcher or login filter not enabled | Never tweak `@Order` blindly |
| Custom filter never runs | Wrong chain, matcher, disabled filter, wrong path | Never auto-register an extra container filter right away |
| Custom filter runs twice | Bean auto-registration + `addFilter*`, or two entries in chain | Never mask it with `OncePerRequestFilter` alone |
| Trace filter sees null auth | Running before auth filter or outside proxy | Never assume null proves wrong password |
| Bug appears only on error/async | Dispatcher types and once-per-dispatch policy | Never assume all dispatches behave like `REQUEST` |
| Controller cannot read JSON | Custom filter already consumed `InputStream` | Never keep reading raw body without a wrapper |
| Request A sees principal B | `ThreadLocal` leak or static/`currentUser` field | Never use `MODE_GLOBAL` in a multi-user web app |

### 11.4. Observe Without Disclosing Credentials

During investigation, log **filter type, layer, requestId, sanitized method/path, dispatcher type, timing, and outcome**. Avoid logging raw passwords, session cookies, API keys, bearer tokens, or sensitive request bodies. During a security incident, logs are also assets to protect.

## 12. Recommended Test Suite

### 12.1. Unit Testing Ordering Rules

| Test | Outcome to prove |
|---|---|
| `addFilterBefore` | Custom filter runs before anchor in the built chain |
| `addFilterAfter` | Custom filter runs after anchor in the built chain |
| `addFilterAt` same slot | Do not rely on unspecified relative order; default filter is not auto-removed |
| Only API chain present | Non-API URLs must not be assumed protected |
| API chain before fallback | API requests select the specific chain |
| Fallback before API | Test catches that the API matcher is shadowed |
| Custom filter duplicated in one chain | Detects invocation count > 1 |
| Filter present in two different chains | Request executes only the selected chain |
| Filter in container + security chain | Detects two registration points/invocations |
| `OncePerRequestFilter` nested call | Distinguishes `doFilter` vs. `doFilterInternal` |
| `ERROR`/`ASYNC` dispatch | Behavior matches dispatcher mapping and overrides |

### 12.2. Spring Boot Integration Tests with MockMvc

- `GET /api/orders` enters the API chain, custom filter runs once.
- `GET /home` enters the fallback Web chain, untouched by API-only filters.
- `GET /api/health`, though `permitAll`, still traverses the API chain.
- `POST /login` enters the chain creating the login filter and does not 404.
- API requests without credentials are rejected properly by entry point/authorization; invalid tokens never create authenticated principals.
- `FilterRegistrationBean.setEnabled(false)` does not remove the filter from the Security chain.
- With real context and servlet filter registrations active, verify the custom filter instance is not invoked twice.
- Test CSRF on write endpoints per policy instead of diagnosing every 403 as missing authority.
- Test locked accounts, role changes, session/token lifecycles, and zero context leaks across request/worker reuse.
- Test `DispatcherType.ERROR`/`ASYNC` and corresponding `doFilterInternal` invocations.
- Test that custom filters abort the chain cleanly on failure without double-committing responses.

### 12.3. E2E via Embedded Tomcat or a Real Container

MockMvc does not fully reflect automatic Servlet registrations or reverse proxies. Test over a real HTTP port to verify:

- Spring Boot auto-registration, order of `DelegatingFilterProxy`, and custom filters.
- Context path/servlet path URLs, forwarding headers, encoded URLs/path matchers.
- Large request bodies, CORS preflight, CSRF, error dispatches, and async requests.
- Concurrent multi-user traffic to catch leaked request contexts.
- Disabling container registration does not break logging/tracing needed on URLs outside security chains.

**Do not treat passing on a single mock request as proof of production safety.** Use the real filter chain along with attack and regression test cases.

## 13. FAQ: Crucial Misconceptions

**1. Does Spring Security run every `SecurityFilterChain` that matches a request?**  
No. `FilterChainProxy` picks only the first matching chain; it does not combine filters.

**2. Does `@Order(1)` on a `Filter` class force it to run first inside Spring Security?**  
No. Container filter order and internal security filter order are separate layers.

**3. Is a `Filter` bean present in two `SecurityFilterChain`s invoked twice?**  
Not automatically. Only the selected chain runs; check for duplicates within the selected chain or container.

**4. Why can `@Component` plus `addFilterAfter` cause duplicates?**  
Because Boot may auto-register the `Filter` bean in the container while `SecurityFilterChain` also includes it.

**5. Does `addFilterAt` actually replace an existing filter?**  
Not automatically; same-slot ordering is unspecified. Explicitly disable or reconfigure the old filter.

**6. Does `OncePerRequestFilter` guarantee running only once across an HTTP request and all redispatches?**  
No. It depends on markers and dispatcher-type behavior; duplicate registrations must still be fixed.

**7. Does `FilterRegistrationBean.setEnabled(false)` remove a filter from the Spring Security chain?**  
No. It only controls container registration; it does not remove entries added via `HttpSecurity`.

**8. Is validating tokens in the container before Spring Security always right?**  
No. It can lack context/protections, sit outside the proxy lifecycle, and cause double verification. Pick the right security chain/provider.

**9. Why is auth null inside a filter even with a valid token?**  
The filter may run before the authentication mechanism or in the container before the security chain; inspect its position and selected chain.

**10. Are `permitAll` and `web.ignoring` the same?**  
No. `permitAll` still traverses the chain's security filters; ignoring can bypass filters completely.

**11. Can we log the token to debug double parsing?**  
No. Log category, `requestId`, and invocation count without exposing secrets.

**12. To make a business operation run strictly once, can we rely on `OncePerRequestFilter`?**  
No. Use idempotency keys, transactions, unique constraints, and replay defenses in the domain layer.

## 14. Deployment Checklist

- [ ] Distinguish **Servlet container order**, **`SecurityFilterChain` priority**, and **internal filter order**.
- [ ] Verify `DelegatingFilterProxy`/`springSecurityFilterChain` is properly registered by the container without extra proxies.
- [ ] With multiple chains, place narrower matchers before fallbacks and test actual `@Order`.
- [ ] Route every critical endpoint into a chain with appropriate authentication/authorization.
- [ ] Distinguish `securityMatcher` from `requestMatchers`, and `permitAll` from `web.ignoring`.
- [ ] Give every custom filter a clear justification; prefer standard filters/providers/handlers first.
- [ ] Choose `addFilterBefore/After` based on needed context/protection/auth state; never run auth filters after authorization.
- [ ] Never use `addFilterAt` expecting automatic replacement.
- [ ] If a custom `Filter` bean belongs only inside Spring Security, disable container auto-registration via `FilterRegistrationBean.setEnabled(false)` or avoid declaring it as a standalone `Filter` bean.
- [ ] Never add the same filter twice within the selected chain.
- [ ] Understand `OncePerRequestFilter` and test `REQUEST`, `ASYNC`, and `ERROR`.
- [ ] Never construct an authenticated principal from input not verified by a verifier/provider.
- [ ] Never disable CSRF, CORS, headers, or firewall to hide ordering bugs.
- [ ] Inspect Spring Security DEBUG/TRACE logs in suitable environments to confirm filter lists and container registrations.
- [ ] Never leak passwords, bearer tokens, cookies, API keys, or credential-bearing bodies in logs.
- [ ] Maintain unit tests, Boot MockMvc integration tests, and real HTTP tests for double registration.
- [ ] After disabling container auto-registration, confirm behavior on URLs outside security chains was not broken.
- [ ] Use supported Spring Boot/Spring Security versions with security patches when deploying to production.

**Remember:** Custom filters must be placed at **exactly one layer, in the right chain, and at the right position**; `OncePerRequestFilter` is no substitute for controlling registration. Understanding the order from Servlet container to `FilterChainProxy` and then internal filters helps distinguish genuine authentication failures from filters running at the wrong time or twice.

### Official Documentation

- [Spring Security — Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `DelegatingFilterProxy`, `FilterChainProxy`, event ordering, custom filters, and registration pitfalls.
- [Spring Security — HttpSecurity JavaDoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/builders/HttpSecurity.html): `addFilterBefore`, `addFilterAfter`, `addFilterAt`, and same-slot warnings.
- [Spring Security — Java Configuration / Multiple HttpSecurity](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `@Order`, `securityMatcher`/`requestMatchers`.
- [Spring Boot — Embedded Web Servers](https://docs.spring.io/spring-boot/how-to/webserver.html): auto-registering `Filter` beans and `FilterRegistrationBean` to disable registration.
- [Spring Framework — Servlet Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): `OncePerRequestFilter`, `GenericFilterBean`, and Servlet Filter lifecycle.
- [Spring Framework — OncePerRequestFilter JavaDoc](https://docs.spring.io/spring-framework/docs/6.1.18/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): `doFilterInternal`, markers, and dispatch behavior.
