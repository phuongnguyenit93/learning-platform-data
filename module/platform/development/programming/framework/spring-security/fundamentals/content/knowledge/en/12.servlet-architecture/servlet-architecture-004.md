# Order of Filter Groups: Context, Authentication, Protection, and Authorization

> **Key takeaway:** In **Servlet-based** Spring Security, a request does not go directly to a controller and get security-checked afterward. It passes through an **ordered chain of Servlet Filters**. Logically, Spring Security needs to (1) prepare/restore the `SecurityContext`; (2) apply request protections such as CORS, CSRF, and headers; (3) authenticate credentials from Basic, form login, Bearer tokens, or other mechanisms; (4) populate an anonymous identity when no principal is present and set up exception handling; and (5) enforce authorization rules at `AuthorizationFilter` before letting the request enter `DispatcherServlet`. Order matters because **each filter only sees the state prepared by filters before it**, and **a filter rejecting a request can stop all downstream filters from running**.

This lesson belongs to the **Servlet Architecture** group of the **Spring Security – fundamentals** module. Examples use **Java 17+, Spring Boot 3.5.16, Spring Security 6.5.x, Spring MVC/Servlet**. The actual filter list depends on configuration and version; there is no single immutable full list for every project. With **WebFlux**, you must use `SecurityWebFilterChain` and a different reactive model.

## 1. Learning Outcomes

After completing this lesson, you will be able to:

1. Explain the path `Servlet FilterChain` → `DelegatingFilterProxy` → `FilterChainProxy` → one `SecurityFilterChain` → `DispatcherServlet`.
2. Distinguish **SecurityFilterChain selection order** from **Filter order inside the selected chain**.
3. Identify the responsibilities and relationships of `SecurityContextHolderFilter`, `HeaderWriterFilter`, `CorsFilter`, `CsrfFilter`, `LogoutFilter`, `BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`, `AnonymousAuthenticationFilter`, `ExceptionTranslationFilter`, and `AuthorizationFilter`.
4. Explain why `CsrfFilter` can block a POST before HTTP Basic authentication is processed.
5. Describe the difference between 401 for missing/invalid credentials and 403 for insufficient authority/CSRF.
6. Understand that `ExceptionTranslationFilter` **only catches exceptions within the downstream scope it wraps**, not every error across the entire chain.
7. Choose custom filter placement with `addFilterBefore`/`addFilterAfter` based on prerequisites; never confuse `addFilterAt` with removing an existing filter.
8. Avoid registering a custom filter twice via Spring Boot servlet filter auto-registration and `HttpSecurity`.
9. Distinguish `securityMatcher`, `requestMatchers`, `@Order`, and `permitAll`; never leave URLs outside every chain.
10. Observe the filter list via DEBUG/TRACE and write MockMvc tests verifying real order along with 200/401/403/500 cases.
11. Understand boundaries involving session form login, JWT, multi-chain setups, ASYNC/ERROR dispatches, and business-resource permissions.

## 2. Servlet Filter: Order Is Not Just Presentation

A `Filter` can read/modify the request or response, reject a request early, or call `chain.doFilter` to pass control onward. As the response unwinds, code after `chain.doFilter` runs in reverse order, like a stack:

```text
Request enters:
  Filter A.before
    Filter B.before
      Filter C.before
        DispatcherServlet -> Controller
      Filter C.after
    Filter B.after
  Filter A.after
Response exits.
```

With exceptions, statements after `chain.doFilter` do not necessarily run unless the filter uses `finally`. Therefore, the lifecycles of `SecurityContext`, response headers, and exception handling all depend on ordering.

Basic snippet:

```java
@Override
public void doFilter(ServletRequest request,
        ServletResponse response, FilterChain chain)
        throws IOException, ServletException {

    prepareRequest(request);
    try {
        chain.doFilter(request, response);
    } finally {
        finishRequest(response);
    }
}
```

This is an **explanatory snippet**, not a standalone file because `prepareRequest`/`finishRequest` are application-defined methods. In practice, not every filter is obligated to proceed: `CsrfFilter` rejecting a POST missing a token halts processing, and the controller will never run.

**Rule:** Never infer "every filter in the startup log ran for this request". The registered list shows which filters *can* run; **short-circuiting** and request matchers determine which filters actually execute.

## 3. Outer Layer: Container, DelegatingFilterProxy, and FilterChainProxy

### 3.1. Full Diagram

```text
HTTP request
    |
    v
Servlet container (Tomcat/Jetty/Undertow)
    |
    v
Container FilterChain
    |
    +-- other Servlet Filters (if registered)
    |
    v
DelegatingFilterProxy ("springSecurityFilterChain")
    |
    v
FilterChainProxy (Spring-managed Filter)
    |
    +-- HttpFirewall and request matching
    |
    +-- select the FIRST matching SecurityFilterChain
          |
          +-- SecurityContextHolderFilter
          +-- protection filters (headers/CORS/CSRF...)
          +-- LogoutFilter
          +-- authentication filters (Basic/form/Bearer...)
          +-- AnonymousAuthenticationFilter
          +-- ExceptionTranslationFilter
          +-- AuthorizationFilter
          |
          v
DispatcherServlet -> Controller -> Service
    |
    v
Response unwinds back through filters
```

`DelegatingFilterProxy` is an adapter between the Servlet container lifecycle and a Spring-managed filter bean. `FilterChainProxy` is the filter bean behind that adapter, responsible for holding `SecurityFilterChain` instances and selecting the matching chain. In Spring Boot with `spring-boot-starter-security`, registering the proxy is normally handled by Boot; you typically declare `SecurityFilterChain` beans rather than writing `web.xml`.

`FilterChainProxy` also integrates `HttpFirewall` when handling requests and enforces critical security lifecycles such as security context cleanup. Do not manually register individual Spring Security Filters directly with the container to "optimize" and accidentally bypass the proxy's protections.

### 3.2. Chain Selection Comes First

Each `SecurityFilterChain` has a `RequestMatcher`, and `FilterChainProxy` evaluates them in order. **Only the first matching chain runs**; other chains do not add extra filters to that request.

```text
Ordered chains:
  @Order(1)  matcher /api/**   -> Basic + stateless API
  @Order(2)  matcher /admin/** -> admin policy
  default    matcher any       -> remaining web UI

GET /api/tasks:
  selects chain #1, does NOT continue to chain #2 or default.

GET /home:
  tries #1 no match, #2 no match,
  selects default.
```

If a request **matches no chain**, Spring Security may not protect that request; this is a severe misconfiguration, especially when declaring a chain with `securityMatcher("/api/**")` and forgetting a catch-all chain for remaining paths.

### 3.3. Two Independent Orderings

| Configuration | What Does It Order? | What Does It NOT Mean? |
| --- | --- | --- |
| `@Order(1)` on `SecurityFilterChain` bean | Which chain's matcher is checked first | Does not change `BasicAuthenticationFilter`'s position inside the chain |
| `http.securityMatcher("/api/**")` | Selects requests protected by this chain | Does not alter authorization rules in other chains |
| `http.authorizeHttpRequests().requestMatchers(...)` | Selects authorization rule **after chain matched** | Does not make the chain match additional paths |
| `http.addFilterAfter(...)` | Filter position **inside the selected chain** | Does not change container-level filter order |
| Servlet `FilterRegistrationBean`/`@Order` | Filter order at the container level | Not equivalent to `HttpSecurity` filter order |

The order of DSL method calls in Java is also **not** the execution order: writing `.authorizeHttpRequests(...)` before `.httpBasic(...)` in source code does not make `AuthorizationFilter` run before `BasicAuthenticationFilter`. `HttpSecurity.build()` uses the framework's ordering rules.

## 4. Filter Group Order Within a Chain

The Spring Security 6.5 reference recommends learning by **functional milestones**:

```text
┌──────────────────────────────────────────────┐
│ SecurityContext is loaded/prepared           │
│ SecurityContextHolderFilter                  │
├──────────────────────────────────────────────┤
│ Request protection: headers, CORS, CSRF      │
│ HeaderWriterFilter / CorsFilter / CsrfFilter │
├──────────────────────────────────────────────┤
│ LogoutFilter (if request is logout)          │
├──────────────────────────────────────────────┤
│ Credential authentication by mechanism       │
│ Form / Basic / Bearer / OAuth2 / X.509 ...   │
├──────────────────────────────────────────────┤
│ AnonymousAuthenticationFilter and helpers    │
│ RequestCacheAwareFilter, request wrappers ...│
├──────────────────────────────────────────────┤
│ ExceptionTranslationFilter                   │
│ Wraps downstream & handles security exceptions│
├──────────────────────────────────────────────┤
│ AuthorizationFilter                          │
│ Allow/deny per HTTP authorization rules      │
└──────────────────────────────────────────────┘
                      |
                      v
             DispatcherServlet / Controller
```

These are **groups**, not an exhaustive list. Depending on the app there may be `DisableEncodeUrlFilter`, `WebAsyncManagerIntegrationFilter`, `SessionManagementFilter`, `ConcurrentSessionFilter`, `RememberMeAuthenticationFilter`, `DefaultLoginPageGeneratingFilter`, and various other authentication filters.

### 4.1. An Illustrative Filter List from Official Documentation

A configuration with form login + HTTP Basic might print:

```text
DisableEncodeUrlFilter
WebAsyncManagerIntegrationFilter
SecurityContextHolderFilter
HeaderWriterFilter
CsrfFilter
LogoutFilter
UsernamePasswordAuthenticationFilter
DefaultLoginPageGeneratingFilter
DefaultLogoutPageGeneratingFilter
BasicAuthenticationFilter
RequestCacheAwareFilter
SecurityContextHolderAwareRequestFilter
AnonymousAuthenticationFilter
ExceptionTranslationFilter
AuthorizationFilter
```

**Do not memorize this list as immutable truth.** Enabling/disabling form login, OAuth2 Resource Server, CORS, request cache, sessions, or changing versions alters the list. Check the DEBUG log for `DefaultSecurityFilterChain` and the filter list of the **exact chain matching your request**, rather than copying a list from a random blog post.

## 5. Context Group: SecurityContextHolderFilter

`SecurityContextHolderFilter` loads the `SecurityContext` from `SecurityContextRepository` and makes the context accessible via `SecurityContextHolder` for the scope of the request. The holder uses `ThreadLocal` by default for Servlet apps, and the filter/framework must clear it properly when the request ends.

```text
Request A: has session authentication Alice
  SecurityContextHolderFilter -> can restore Alice.

Request B: stateless, carries Basic Authorization header
  SecurityContextHolderFilter -> initially typically empty.
  BasicAuthenticationFilter -> authenticates Alice afterward.

Request C: anonymous
  SecurityContextHolderFilter -> context initially empty.
  AnonymousAuthenticationFilter -> may populate anonymous.
```

Never conclude that once `SecurityContextHolderFilter` has run the user is "authenticated"—it prepares/restores context, **it does not verify username/password**. Conversely, never claim it is "always null before Basic": a valid `HttpSession` can supply authentication from a previous request.

**Load / save / clear are three distinct operations:**

- **Load:** makes the context available for the current request.
- **Save:** persists context in the repository/session per policy so subsequent requests can restore it. For custom authentication in Spring Security 6, explicit `SecurityContextRepository.saveContext(context, request, response)` may be needed.
- **Clear:** clears the thread's context after the request; **not synonymous with logout** or invalidating sessions/refresh tokens.

With `SessionCreationPolicy.STATELESS`, apps typically authenticate from credentials/tokens on each new request rather than a server session. With form login, repository/session and saved-request behavior differ. Never call `clearContext()` mid-controller and strip the principal from the rest of the request.

## 6. Protection Group: Headers, CORS, CSRF, and Logout

### 6.1. HeaderWriterFilter

`HeaderWriterFilter` adds configured browser security headers, such as `X-Content-Type-Options: nosniff`. Depending on implementation, headers are handled on the response path or at commit time, meaning it does not only execute code "before" the controller.

`permitAll()` on a URL **does not skip** HeaderWriterFilter if the URL still passes through the chain. By contrast, `web.ignoring()` or a URL matching no chain can skip essential security filters altogether.

### 6.2. CorsFilter Must Handle Preflight Before Login Requirements

A browser may send:

```http
OPTIONS /api/orders HTTP/1.1
Origin: https://frontend.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
```

Preflight requests normally carry no `JSESSIONID` cookie and no authentication credentials like the main request. If the system checks login before handling CORS, preflights can be wrongly rejected. Spring Security integrates via:

```java
http.cors(Customizer.withDefaults());
```

However, this configuration requires an appropriate `CorsConfigurationSource` or Spring MVC CORS configuration. **CORS is not authentication and does not replace CSRF**. Do not "fix" preflight by setting `anyRequest().permitAll()` or opening Origins globally without understanding trust boundaries.

### 6.3. CsrfFilter Can Block POST Before Basic Authentication

`CsrfFilter` checks the CSRF token on protected requests; by default GET/HEAD/OPTIONS/TRACE are treated as safe methods, whereas POST/PUT/PATCH/DELETE normally require a token when CSRF is enabled.

**Critical flow:**

```text
POST /notes
Authorization: Basic writer:demo-pass
CSRF token: MISSING

SecurityContextHolderFilter
  -> HeaderWriterFilter
  -> CsrfFilter: missing token -> AccessDeniedHandler -> 403
  -> STOP

BasicAuthenticationFilter: may NOT have run yet.
AuthorizationFilter:      may NOT have run yet.
Controller:               does not run.
```

Therefore, **a CSRF 403 does not prove the password is valid**. When testing `NOTE_WRITE` permission on POST, first test with a valid CSRF token. Do not disable CSRF app-wide just to make tests green; evaluate browser cookie/Basic auto-attachment and your real threat model. A Bearer API using only explicit Authorization headers in non-browser clients can have a different policy, but it must be designed deliberately.

### 6.4. LogoutFilter Is Not a Regular Authentication Filter

`LogoutFilter` sits early before many authentication filters and can handle logout requests: invoking logout handlers, clearing context/session per policy, redirecting, or writing a response. It does not assert every request is authenticated, nor does it automatically revoke JWTs at an issuer or all refresh tokens in a distributed system. When the filter decides logout succeeded, downstream components may not run.

## 7. Authentication Group: From Credentials to Authentication

| Login Type | Typical Filter | Credential Source |
| --- | --- | --- |
| HTTP Basic | `BasicAuthenticationFilter` | `Authorization: Basic ...` |
| Form login | `UsernamePasswordAuthenticationFilter` | POST login form |
| Bearer JWT/OAuth2 Resource Server | `BearerTokenAuthenticationFilter` | `Authorization: Bearer ...` |
| OAuth2 Login | `OAuth2LoginAuthenticationFilter` + other filters | Redirect/callback/code |
| X.509 | `X509AuthenticationFilter` | Verified client certificate from TLS |
| Pre-auth | `AbstractPreAuthenticatedProcessingFilter` or implementation | Principal trusted from upstream |

Only configured filters appear. An authentication filter typically extracts credentials, builds an unauthenticated `Authentication`, calls `AuthenticationManager`/`AuthenticationProvider`, places the verified `Authentication` into `SecurityContext`, and handles success/failure.

**A valid password does not mean sufficient authority.** Alice with `ROLE_USER` still cannot automatically enter a URL requiring `ROLE_ADMIN`. Authentication answers *who is calling*; authorization answers *what they may do*; object-level policy must also check *on which resource, belonging to which tenant*.

### 7.1. BasicAuthenticationFilter and 401 Errors

When `BasicAuthenticationFilter` receives bad credentials, it can invoke `AuthenticationEntryPoint`/failure handling itself to return `401` and halt the filter chain **before reaching `AuthorizationFilter`**. For an anonymous GET to a protected endpoint without a Basic header, the Basic filter normally passes through, `AnonymousAuthenticationFilter` sets anonymous, and then authorization rejects it and `ExceptionTranslationFilter` triggers the entry point. Both yield 401 yet take **different paths**.

### 7.2. RequestCacheAwareFilter and Anonymous

`RequestCacheAwareFilter` helps restore saved requests in redirect/form-login flows. It is not a password provider. `AnonymousAuthenticationFilter` populates an `AnonymousAuthenticationToken` when no Authentication is present, helping components treat anonymous uniformly.

A trap:

```java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();

if (auth != null && auth.isAuthenticated()) {
    // NOT sufficient to treat as a properly signed-in user.
}
```

With an anonymous token, the `isAuthenticated()` flag can be true. Use `authenticated()`/`hasAuthority`/`AuthenticationTrustResolver` or method security instead of gating access on this flag yourself.

## 8. Authorization Group and Exception Translation

`AuthorizationFilter` evaluates `authorizeHttpRequests(...)` rules. `ExceptionTranslationFilter` normally sits right before the authorization region, invoking downstream inside a `try/catch` to handle `AuthenticationException` or `AccessDeniedException` appropriately.

```text
ExceptionTranslationFilter
  try {
      AuthorizationFilter
        -> granted: DispatcherServlet
        -> denied: AccessDeniedException
  } catch (AuthenticationException | AccessDeniedException) {
      if login needed: AuthenticationEntryPoint
      if already authenticated yet lacks authority: AccessDeniedHandler
  }
```

Typical cases:

| Request | Stopping Point | Response in HTTP Basic Lab |
| --- | --- | --- |
| GET /me anonymous | AuthorizationFilter → ExceptionTranslationFilter | 401 |
| GET /me wrong credentials | BasicAuthenticationFilter failure | 401 |
| GET /admin Alice valid password | AuthorizationFilter → ExceptionTranslationFilter | 403 |
| POST /notes writer valid yet missing CSRF | CsrfFilter (upstream) | 403 |
| POST /notes Alice valid + valid CSRF yet lacks NOTE_WRITE | AuthorizationFilter | 403 |
| POST /notes writer valid + valid CSRF | Proceeds to controller | 200 |

**Critical limitation:** `ExceptionTranslationFilter` **does not catch every error** in filters preceding it. An exception thrown by a custom filter placed before `ExceptionTranslationFilter` may not be handled by it. `CsrfFilter` has its own error handler; the Basic authentication filter also has its own failure mechanism. Non-security business errors do not automatically turn into HTTP 401/403.

If you need custom access checks, prefer `AuthorizationManager`, `authorizeHttpRequests`, method security, or service-layer owner/tenant checks; avoid rushing to write a custom filter throwing `AccessDeniedException` in a spot not wrapped by the translator.

## 9. Example: Three Requests Through the Filter Chain

### 9.1. Basic GET /me with Valid Password

```text
GET /me, Alice's Basic Authorization

FilterChainProxy selects matching chain
  -> SecurityContextHolderFilter: context ready
  -> CsrfFilter: GET normally does not require CSRF
  -> LogoutFilter: not a logout request
  -> BasicAuthenticationFilter: authenticates Alice
  -> AnonymousAuthenticationFilter: does not overwrite Alice
  -> ExceptionTranslationFilter: wraps downstream
  -> AuthorizationFilter: authenticated() = PASS
  -> Controller: "me:alice"
  -> Context cleanup at end of request
```

### 9.2. Anonymous GET /me

```text
GET /me without Authorization header
  -> BasicAuthenticationFilter: no credentials, continues
  -> AnonymousAuthenticationFilter: anonymous
  -> AuthorizationFilter: requires authenticated, denies
  -> ExceptionTranslationFilter: triggers Basic entry point, 401
  -> Controller does not run
```

### 9.3. Alice's GET /admin

```text
GET /admin, Alice's password valid
  -> BasicAuthenticationFilter: Alice authenticated, ROLE_USER
  -> AuthorizationFilter: requires ROLE_ADMIN, denies
  -> ExceptionTranslationFilter: AccessDeniedHandler, 403
  -> Controller does not run
```

### 9.4. POST /notes Missing CSRF

```text
POST /notes, writer's Basic is valid yet CSRF token missing
  -> CsrfFilter: 403, stops
  -> Cannot conclude Basic filter verified password
```

### 9.5. POST /notes With CSRF Yet Lacking Authority

```text
POST /notes, Alice's Basic valid, CSRF valid
  -> CsrfFilter passes
  -> BasicAuthenticationFilter authenticates Alice
  -> AuthorizationFilter requires NOTE_WRITE which Alice lacks
  -> ExceptionTranslationFilter translates to 403
```

Two requests returning the same **403** status can have completely different causes. Tests/filter traces must distinguish where the request stopped.

## 10. Runnable Sample App: Observing Before/After Basic Authentication

**Approach:** create a stateless HTTP Basic Spring Security chain with three in-memory/BCrypt users. Insert **two custom probe filters** that only record request attributes:
- `ContextProbeFilter` after `SecurityContextHolderFilter`, before `BasicAuthenticationFilter`.
- `AfterAuthenticationProbeFilter` after `AnonymousAuthenticationFilter`, before `ExceptionTranslationFilter`/`AuthorizationFilter`.
- Endpoint `GET /flow` reads three milestones: `before`, `after`, and `controller`.
- Test actual ordering via `FilterChainProxy.getFilters(...)` and behavior via MockMvc.

**Do not turn probes into auth mechanisms:** they must not alter principals/roles or expose sensitive responses to the Internet. All sample users/passwords here are localhost-only.

### 10.1. Structure

```text
servlet-filter-order-demo/
├── pom.xml
└── src/
    ├── main/java/demo/filterorder/FilterOrderApplication.java
    └── test/java/demo/filterorder/FilterOrderTests.java
```

Java 17, Spring Boot `3.5.16`, Spring Security 6.5.x via Boot BOM. Version 3.5.16 was released on 2026-06-25 and is the final OSS release of the 3.5 line; for new products, pick a supported Boot line and update code/tests accordingly.

### 10.2. Complete pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>servlet-filter-order-demo</artifactId>
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

### 10.3. Complete Java Application

Create `src/main/java/demo/filterorder/FilterOrderApplication.java`:

```java
package demo.filterorder;

import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;
import org.springframework.security.web.context.SecurityContextHolderFilter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
public class FilterOrderApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterOrderApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class LabSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build(),
            User.withUsername("writer")
                .password(encoder.encode("demo-pass"))
                .authorities("ROLE_USER", "NOTE_WRITE")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-pass"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public")
                    .permitAll()
                .requestMatchers(HttpMethod.GET,
                    "/me", "/flow", "/boom")
                    .authenticated()
                .requestMatchers(HttpMethod.GET, "/admin")
                    .hasRole("ADMIN")
                .requestMatchers(HttpMethod.POST, "/notes")
                    .hasAuthority("NOTE_WRITE")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(Customizer.withDefaults())
            // Probe 1: context is prepared; Basic has not run yet.
            .addFilterAfter(
                new ContextProbeFilter(),
                SecurityContextHolderFilter.class)
            // Probe 2: after auth filters and anonymous fallback.
            .addFilterAfter(
                new AfterAuthenticationProbeFilter(),
                AnonymousAuthenticationFilter.class)
            .build();
    }
}

// Not @Component / @Bean: registered only inside SecurityFilterChain.
class ContextProbeFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request,
            HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        request.setAttribute("phase.before", PhaseNames.current());
        chain.doFilter(request, response);
    }
}

class AfterAuthenticationProbeFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request,
            HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        request.setAttribute("phase.after", PhaseNames.current());
        chain.doFilter(request, response);
    }
}

final class PhaseNames {
    private PhaseNames() { }

    static String current() {
        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        return auth == null ? "none" : auth.getName();
    }
}

@RestController
class LabRoutes {
    @GetMapping("/public")
    String publicPage() {
        return "public";
    }

    @GetMapping("/me")
    String me(Authentication auth) {
        return "me:" + auth.getName();
    }

    @GetMapping("/flow")
    String flow(HttpServletRequest request, Authentication auth) {
        return "before=" + request.getAttribute("phase.before")
            + ";after=" + request.getAttribute("phase.after")
            + ";controller=" + auth.getName();
    }

    @GetMapping("/admin")
    String admin() {
        return "admin";
    }

    @PostMapping("/notes")
    String createNote(Authentication auth) {
        return "created:" + auth.getName();
    }

    @GetMapping("/boom")
    String boom() {
        throw new ResponseStatusException(
            HttpStatus.INTERNAL_SERVER_ERROR, "lab error");
    }
}
```

### 10.4. Reading the Code in Order

- `UserDetailsService` provides users/password hashes; bcrypt `PasswordEncoder` lets the provider verify credentials.
- `SecurityFilterChain` defines URL rules. `HttpSecurity` still orders filters properly even though source calls `authorizeHttpRequests` before `httpBasic`.
- `ContextProbeFilter` after `SecurityContextHolderFilter`: in this stateless Basic demo, it normally reads `none` because authentication has not happened yet.
- `BasicAuthenticationFilter` runs after the CSRF and logout groups, checking the password.
- `AfterAuthenticationProbeFilter` after `AnonymousAuthenticationFilter`: with valid Basic credentials, it reads the authenticated username.
- `AuthorizationFilter` after the probe enforces role/authority rules and can deny before the controller.
- Neither probe is a bean, preventing Boot from auto-registering them a second time on the container outside Spring Security.
- `/boom` allows authenticated users to test filter cleanup after an error response.
- Demo password `demo-pass` is hardcoded in public source: **never deploy a demo app to a public network**.
- CSRF remains enabled. To make POST succeed in MockMvc you must attach a valid token; a plain curl without a token will get 403.

```text
GET /flow with Alice's valid password:
    ContextProbeFilter        -> "none"
    BasicAuthenticationFilter -> Alice
    AfterAuthenticationProbe  -> "alice"
    AuthorizationFilter       -> Alice permitted
    Controller                -> "alice"

Expected body:
before=none;after=alice;controller=alice
```

If using session-based form login where authentication is restored before Basic, `before` can already be the signed-in user. This is a **property of the stateless demo**, not a law of every chain.

## 11. MockMvc Tests: Verifying Order via FilterChainProxy and Real Requests

Create `src/test/java/demo/filterorder/FilterOrderTests.java`:

```java
package demo.filterorder;

import java.util.List;

import jakarta.servlet.Filter;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.FilterChainProxy;
import org.springframework.security.web.access.ExceptionTranslationFilter;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;
import org.springframework.security.web.authentication.logout.LogoutFilter;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
import org.springframework.security.web.context.SecurityContextHolderFilter;
import org.springframework.security.web.csrf.CsrfFilter;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterOrderTests {

    @Autowired
    MockMvc mvc;

    @Autowired
    FilterChainProxy proxy;

    private int indexOf(Class<? extends Filter> type) {
        // Convenience method checking path.
        // For RequestMatchers depending on method/headers,
        // also test real requests through MockMvc.
        List<Filter> filters = proxy.getFilters("/flow");
        assertNotNull(filters);

        for (int i = 0; i < filters.size(); i++) {
            if (type.isInstance(filters.get(i))) {
                return i;
            }
        }
        throw new AssertionError("Missing: " + type.getName());
    }

    @Test
    void filtersAreOrderedByDependenciesNotJavaDslOrder() {
        int context = indexOf(SecurityContextHolderFilter.class);
        int early = indexOf(ContextProbeFilter.class);
        int csrfFilter = indexOf(CsrfFilter.class);
        int logout = indexOf(LogoutFilter.class);
        int basic = indexOf(BasicAuthenticationFilter.class);
        int anon = indexOf(AnonymousAuthenticationFilter.class);
        int late = indexOf(AfterAuthenticationProbeFilter.class);
        int translator = indexOf(ExceptionTranslationFilter.class);
        int authorization = indexOf(AuthorizationFilter.class);

        assertTrue(context < early);
        assertTrue(early < csrfFilter);
        assertTrue(csrfFilter < logout);
        assertTrue(logout < basic);
        assertTrue(basic < anon);
        assertTrue(anon < late);
        assertTrue(late < translator);
        assertTrue(translator < authorization);
    }

    @Test
    void showsBeforeAndAfterBasicAuthentication() throws Exception {
        mvc.perform(get("/flow")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "before=none;after=alice;controller=alice"));

        mvc.perform(get("/flow")
                .with(httpBasic("writer", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "before=none;after=writer;controller=writer"));

        assertNull(SecurityContextHolder.getContext()
            .getAuthentication());
    }

    @Test
    void distinguishesAuthenticationFromAuthorization()
            throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"))
            .andExpect(header().string(
                "X-Content-Type-Options", "nosniff"));

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic("alice", "bad")))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/me")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("me:alice"));

        mvc.perform(get("/admin")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(get("/admin")
                .with(httpBasic("admin", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void csrfCanDenyBeforeAuthenticationAndAuthorization()
            throws Exception {
        // Writer has NOTE_WRITE, but CSRF is missing.
        mvc.perform(post("/notes")
                .with(httpBasic("writer", "demo-pass")))
            .andExpect(status().isForbidden());

        mvc.perform(post("/notes")
                .with(httpBasic("writer", "demo-pass"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        // Valid CSRF, but Alice lacks NOTE_WRITE.
        mvc.perform(post("/notes")
                .with(httpBasic("alice", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isForbidden());

        // Writer valid credentials + CSRF + NOTE_WRITE.
        mvc.perform(post("/notes")
                .with(httpBasic("writer", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created:writer"));
    }

    @Test
    void errorAndNextRequestDoNotKeepPreviousIdentity()
            throws Exception {
        mvc.perform(get("/boom")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isInternalServerError());

        assertNull(SecurityContextHolder.getContext()
            .getAuthentication());

        mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/unknown")
                .with(httpBasic("alice", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

**Test significance:**

- `indexOf(...)` reads Spring Security's real filter list and asserts the ordering relationship: context → CSRF → logout → Basic → anonymous → exception translator → authorization.
- `getFilters(String)` is only a URL-based test utility. For matchers depending on HTTP method/headers/dispatchers, it does not replace MockMvc requests.
- `/flow` with Alice/Writer proves identity appears after `BasicAuthenticationFilter`, not from a global variable in the controller.
- `httpBasic(...)` exercises the real password authentication path. `@WithMockUser` only injects a mock user and is insufficient to test the provider/encoder.
- `CsrfFilter` and `AuthorizationFilter` can both produce HTTP 403 for different reasons; tests cover missing token, missing authority, and success.
- Testing `/boom` with HTTP 500 shows the next request does not inherit Alice's authentication, and the context on the test thread is cleared.
- `/public` returns 200 yet still receives the `nosniff` security header, proving `permitAll` differs from omitting the security chain.
- Demo passwords carry no real security value; the entire lab is strictly educational.

## 12. Running Maven and Observing

In the project directory:

```bash
java -version
mvn -version
mvn test
mvn spring-boot:run
```

**Expected outcomes**, not executed logs captured during authoring:

| Request | User/token | Expected HTTP/body |
| --- | --- | --- |
| GET /public | Anonymous | 200, `public` |
| GET /me | Anonymous | 401 |
| GET /me | Alice wrong password | 401 |
| GET /flow | Alice valid password | 200, `before=none;after=alice;controller=alice` |
| GET /flow | Writer valid password | 200, `before=none;after=writer;controller=writer` |
| GET /admin | Alice valid password | 403 |
| GET /admin | Admin valid password | 200, `admin` |
| POST /notes | Writer, missing CSRF | 403 |
| POST /notes | Writer, invalid CSRF | 403 |
| POST /notes | Alice, valid CSRF | 403 |
| POST /notes | Writer, valid CSRF | 200, `created:writer` |
| GET /boom | Alice valid password | 500 |
| GET /me immediately after /boom | Anonymous | 401 |
| GET /unknown | Alice valid password | 403 |

Try with curl **on localhost only** (curl prompts for `demo-pass` when using `-u`):

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u alice http://localhost:8080/flow
curl -i -u writer http://localhost:8080/flow
curl -i -u alice http://localhost:8080/admin
curl -i -u admin http://localhost:8080/admin
```

Never store raw Basic headers/passwords in logs or shell history. Base64 in Basic authentication is **not encryption**; real environments require HTTPS. To test POST with a valid CSRF token, use MockMvc as shown.

## 13. How to Insert a Custom Filter at the Right Position

### 13.1. Questions Before Adding a Filter

1. Does the filter need `SecurityContext` already prepared?
2. Does it require an **authenticated user** or can it handle anonymous?
3. Does it verify credentials or check permissions/tenants?
4. Must it run before or after `CsrfFilter`/`LogoutFilter`?
5. If it throws `AccessDeniedException`, is it inside the scope wrapped by `ExceptionTranslationFilter`?
6. Will Boot auto-register it with the Servlet container?

| Task | Typically Appropriate Position/Solution | Warning |
| --- | --- | --- |
| Initialize metadata/tracing once context is ready | After `SecurityContextHolderFilter` | Auth may not exist yet |
| Custom authentication mechanism | Spring docs suggest after `LogoutFilter` | Design provider/success/failure/context save yourself |
| Read principal after auth mechanisms | After `AnonymousAuthenticationFilter` | Anonymous still has a principal; exceptions here may precede translator |
| Throw AccessDeniedException wanting translator to catch | Downstream of `ExceptionTranslationFilter` and before target | Watch order/anchor; `AuthorizationManager` is usually better |
| URL/method permissions | `authorizeHttpRequests` | No need to write a custom filter |
| Object owner/tenant permissions | Service/method security | Do not rely solely on path or username |
| CORS | `http.cors(...)` | Preflight must be handled early |
| Security headers | `http.headers(...)` | Avoid unnecessary custom filters |

### 13.2. Three Filter Placement APIs

```java
http.addFilterBefore(customFilter, AnchorFilter.class);
http.addFilterAfter(customFilter, AnchorFilter.class);
http.addFilterAt(customFilter, AnchorFilter.class);
```

This is a **snippet**: `customFilter`/`AnchorFilter` are undefined so it is not standalone. `addFilterBefore/After` specifies order relative to a known filter. `addFilterAt` places the filter at the same order slot; **never assume it removes a default filter registered by another DSL call**. If both `httpBasic(...)` and a custom `BasicAuthenticationFilter` exist, you may encounter duplicate/unpredictable behavior. To replace a built-in filter, check its DSL configurer to swap or disable it properly.

### 13.3. Why Might addFilterBefore(BasicAuthenticationFilter.class) Be Wrong?

If a custom filter needs to check `ROLE_ADMIN` on a Basic user, placing it **before `BasicAuthenticationFilter`** in a stateless API can cause it to read an empty context. Only use this slot when the filter genuinely intends to **perform authentication itself** or logic prior to Basic, not to check verified permissions.

### 13.4. Custom Filter Registered Twice

If you write:

```java
@Component
class MySecurityFilter extends OncePerRequestFilter {
    // Implementation.
}

// Then also:
http.addFilterAfter(mySecurityFilter, BasicAuthenticationFilter.class);
```

Spring Boot may auto-register the `@Component Filter` at the **container level**, while `HttpSecurity` also registers it inside the Spring Security chain. It can execute twice or out of expected order.

Solutions:
- Omit the bean declaration and instantiate the filter with `new` inside `HttpSecurity` whenever possible.
- If DI/a bean is needed, use a `FilterRegistrationBean<MySecurityFilter>` with `setEnabled(false)` to block container registration, and still add the bean to the chain.
- Test invocation counts with real filters active, including error requests.

Snippet:

```java
@Bean
FilterRegistrationBean<MySecurityFilter> disableContainerRegistration(
        MySecurityFilter filter) {
    FilterRegistrationBean<MySecurityFilter> registration =
        new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
```

## 14. Multiple SecurityFilterChains: First Match Wins

A separate configuration **for understanding chain selection**, not used simultaneously with the Section 10 demo app:

```java
@Bean
@Order(1)
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .anyRequest().hasRole("API_USER"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public").permitAll()
            .anyRequest().authenticated())
        .formLogin(Customizer.withDefaults())
        .build();
}
```

`/api/orders` uses only the API chain's filters; it does not inherit the form-login filter from the fallback chain. `/home` uses the fallback. `anyRequest` inside the API chain applies only to URLs matching `/api/**`. If you omit the fallback, URLs outside `/api/**` may bypass Spring Security.

**Filter-provided endpoints:** When using `formLogin()`, filters can serve `GET /login` and `POST /login`. If the chain has `securityMatcher("/secured/**")` while the login URL is `/login`, the login path falls outside the matcher and may fail to work. Configure `loginPage/loginProcessingUrl` to fit the chain's scope.

`permitAll` still passes through security filters; `web.ignoring` and "no matching chain" bypass filters. For public URLs, prefer explicit permit rules to retain headers/CSRF where appropriate.

## 15. Read Logs Instead of Guessing

In a **local/test-only** configuration:

```properties
logging.level.org.springframework.security.web.DefaultSecurityFilterChain=DEBUG
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
```

Startup DEBUG typically prints something like:

```text
Will secure any request with [
  SecurityContextHolderFilter, HeaderWriterFilter,
  CsrfFilter, LogoutFilter, BasicAuthenticationFilter,
  AnonymousAuthenticationFilter,
  ExceptionTranslationFilter, AuthorizationFilter
]
```

The list above is an **abbreviated illustration**, not exact output from a run or a full list. The demo app also has two probe filters and several helper filters. Runtime TRACE can print:

```text
Securing GET /me
Invoking SecurityContextHolderFilter (index/total)
Invoking CsrfFilter (index/total)
Invoking BasicAuthenticationFilter (index/total)
...
Invoking AuthorizationFilter (index/total)
Secured GET /me
```

`index/total` is placeholder notation, not real numbers. If a request is blocked early, invocation logs for subsequent filters will not appear. Never leave TRACE enabled long-term in production or log passwords, Basic/Bearer headers, cookies, tokens, or raw `Authentication` objects.

An effective debugging workflow:

1. Check URL/method/dispatcher and reverse-proxy rewrites.
2. Identify the **selected chain** and `@Order`/`securityMatcher` ordering.
3. Inspect the filter list via startup DEBUG or `FilterChainProxy.getFilters(...)`.
4. For POST 403, check CSRF first; for 401, check authentication filter/entry point; for GET 403, check authorities/authorization.
5. For custom filters, verify anchor, exception scope, double registration, and `chain.doFilter` calls.
6. For sessions, verify context repository save/load/clear.
7. For ERROR/ASYNC dispatches, check Servlet dispatcher types and version-specific `OncePerRequestFilter` behavior.
8. Retest with MockMvc using real credentials + CSRF and check routes outside the matcher.

## 16. Common Mistakes

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Relying on DSL line order | Assuming authorize runs before Basic | Check real filter order |
| Thinking all matching chains run | Relying on another chain's filters | First matching SecurityFilterChain wins |
| Having only `/api/**` chain yet also `/admin` | URLs outside matcher may be unprotected | Catch-all chain |
| Using `permitAll` as "bypass all security" | Misunderstanding headers/CSRF | PermitAll is only an authorization rule |
| Using `web.ignoring` carelessly | Drops security headers and exploit protections | Prefer permitAll |
| Enabling CORS after authentication | Preflight gets 401 | Handle CORS first |
| Assuming POST 403 means missing role | Could be blocked by CSRF | Test valid CSRF then check permissions |
| Expecting AuthorizationFilter on bad Basic password | Basic filter can return 401 itself | Check provider/entry point |
| Placing custom filter needing identity before Basic | Context may have no user yet | Place after auth or use AuthorizationManager |
| Throwing AccessDeniedException in custom filter before translator | Error not translated as expected | Custom error handler / move downstream / use authz |
| Thinking `addFilterAt` deletes built-in filter | Potential duplicate filters | Disable/configure DSL properly |
| `@Component Filter` plus addFilterAfter | Runs twice or in wrong order | Use a single registration path |
| Forgetting `chain.doFilter` on happy path | Controller never runs | Only short-circuit deliberately |
| Forgetting to clear context on custom threads | Identity leakage on worker reuse | Framework lifecycle / proper try-finally |
| Thinking logout = clear ThreadLocal | Session/JWT may still remain valid | Dedicated logout/revocation policy |
| Using HTTP Basic outside localhost | Credentials exposed on network | HTTPS |
| Using `auth.isAuthenticated()` for anonymous | May falsely grant access | Spring authorization / trust resolver |
| Testing only with `@WithMockUser` | Skips password/provider checks | MockMvc + real httpBasic |
| Checking only HTTP path roles | IDOR/BOLA on resources | Service owner/tenant checks |
| Copying Servlet filters to WebFlux | Wrong execution/context model | Reactive SecurityWebFilterChain |

## 17. Pull Request Review Checklist

- [ ] Confirmed Spring MVC/Servlet rather than WebFlux?
- [ ] Understood container FilterChain, DelegatingFilterProxy, FilterChainProxy, and SecurityFilterChain?
- [ ] Distinguished filter ordering from chain selection order?
- [ ] Does every protected URL match at least one chain?
- [ ] Is there a default catch-all chain or explicit deny policy for other URLs?
- [ ] Does `SecurityContextHolderFilter` establish context scope before anything reads it?
- [ ] Are CSRF/CORS/headers aligned with the threat model, and preflights handled properly?
- [ ] Are authentication filters present when configuring the corresponding mechanism?
- [ ] Are anonymous principals prevented from being treated as real logins?
- [ ] Does ExceptionTranslationFilter wrap authorization failures that need translation?
- [ ] Are you not assuming it handles every error from upstream filters?
- [ ] Are custom filters placed by prerequisites rather than Java DSL line position?
- [ ] Is Boot filter-bean double registration avoided?
- [ ] Is `addFilterAt` not used ambiguously to replace built-in filters?
- [ ] Are there tests for POST missing CSRF, invalid/valid token, and missing authority?
- [ ] Are there tests for anonymous GET 401, wrong Basic 401, missing role 403, and 200 success?
- [ ] Are exception paths, cleanup, and ensuring next requests do not inherit identity tested?
- [ ] Do `permitAll` public routes still receive appropriate headers?
- [ ] Was filter order traced in the right chain and TRACE removed before production?
- [ ] Are method security and object/tenant authorization verified?
- [ ] For session login, are SecurityContextRepository, saved requests, and logout verified?
- [ ] For Bearer APIs, are JWT signature/issuer/audience/scope and appropriate CSRF policy verified?
- [ ] Are demo passwords and debug endpoints kept out of production?

## 18. Self-Assessment

**1.** Does writing `.authorizeHttpRequests(...)` before `.httpBasic(...)` in source make the authorization filter run before Basic?

**Answer:** No. Spring Security orders filters by their registration order in `HttpSecurity`. Check the real filter list or DEBUG logs.

**2.** Why can a missing CSRF token return 403 even when the Basic password is valid?

**Answer:** CsrfFilter sits before many authentication filters and can block POST, so Basic may not even have run.

**3.** Are two SecurityFilterChains matching the same URL merged together?

**Answer:** No. FilterChainProxy selects only the first chain matching the request.

**4.** Does `securityMatcher("/api/**")` with `anyRequest().authenticated()` protect `/admin`?

**Answer:** Only if another chain matches `/admin`. `anyRequest` in the API chain applies only to requests matching `/api/**`.

**5.** Why does `ExceptionTranslationFilter` sit before `AuthorizationFilter`?

**Answer:** It wraps downstream and translates `AuthenticationException`/`AccessDeniedException` raised by authorization into an entry point / access-denied response.

**6.** Can you place a custom filter throwing `AccessDeniedException` before `ExceptionTranslationFilter` and expect the translator to catch it?

**Answer:** No. The translator only catches exceptions from downstream within the `chain.doFilter` call it wraps.

**7.** Does `permitAll()` make `HeaderWriterFilter` disappear?

**Answer:** No. It is only an authorization rule. Bypassing the chain is a separate mechanism and can lose headers/CSRF.

**8.** Why can a `@Component` filter added via `addFilterAfter` run twice?

**Answer:** Boot may auto-register the Filter bean in the servlet container while HttpSecurity registers it in the Spring Security chain.

**9.** Do HTTP 401 for wrong Basic password and HTTP 401 for anonymous login required follow the exact same handling path?

**Answer:** Not necessarily. BasicAuthenticationFilter handles bad credentials; anonymous authorization failure is normally routed by ExceptionTranslationFilter to AuthenticationEntryPoint.

**10.** Why is testing only with `@WithMockUser` insufficient to prove Basic authentication order?

**Answer:** A mock principal bypasses the credential provider. Test via `httpBasic(...)` against a real user store/encoder.

## 19. Final Takeaways

1. **Filter order is part of your security model**, not the line order of Java DSL calls.
2. **SecurityContext** is prepared first, **CSRF/CORS/headers** protect the request, **authentication filters** verify credentials, and **AuthorizationFilter** enforces permissions.
3. **ExceptionTranslationFilter** wraps downstream to translate authz errors; it does not cover upstream failures.
4. **A CSRF 403 does not prove the password is right**; distinguish it from a missing-authority 403.
5. **FilterChainProxy selects the first matching chain**; `securityMatcher` differs from `requestMatchers`, and you should have a catch-all policy.
6. **Place custom filters by prerequisites**; avoid double registration and use the right error-handling scope.
7. **Verify with evidence**: DEBUG/TRACE, actual filter list, MockMvc with 200/401/403/500 and CSRF.
8. **HTTP security does not replace domain authorization**: after filters allow a request, services must still check actor/tenant/resource.

## Official Documentation

- [Spring Security 6.5 — Servlet Architecture, Filters, Order, Custom Filters, and ExceptionTranslationFilter](https://docs.spring.io/spring-security/reference/6.5/servlet/architecture.html)
- [Spring Security 6.5 — Java Configuration, Multiple HttpSecurity, securityMatcher](https://docs.spring.io/spring-security/reference/6.5/servlet/configuration/java.html)
- [Spring Security 6.5 — Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html)
- [Spring Security 6.5 — Authentication Persistence/SecurityContextHolderFilter](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/persistence.html)
- [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html)
- [Spring Security 6.5 — CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html)
- [Spring Security 6.5 — CORS](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/cors.html)
- [Spring Security 6.5 — HTTP Security Headers](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/headers.html)
- [Spring Security 6.5 — FilterChainProxy Javadoc](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/FilterChainProxy.html)
- [Spring Security 6.5 — MockMvc HTTP Basic](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/http-basic.html)
- [Spring Security 6.5 — MockMvc CSRF](https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html)
- [Spring Boot 3.5.16 release](https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/)
