# Tracing a Request from the First Filter to the Controller

One day, a normally working `GET /me` API suddenly starts returning `401`. The developer owning the Controller sets a breakpoint inside `me()`, yet the breakpoint **is never hit**. They assume the application is misrouting, when in reality the request reached Spring Boot and was rejected **before entering the Controller**. Another day, `POST /notes` returns `403` despite a valid username/password; this time the culprit is the CSRF filter blocking the request from continuing. How do you know where the request stopped?

You need to read the **trace through the Servlet `FilterChain`**, especially the Spring Security filter chain. In Spring MVC, an HTTP request travels from the servlet container through any container filters, into `DelegatingFilterProxy`, into `FilterChainProxy`, picks one `SecurityFilterChain`, runs its security filters in sequence, and **only if not blocked** reaches `DispatcherServlet` and the Controller. Once the Controller returns, `chain.doFilter` calls unwind in reverse, letting filters execute their `finally`/post-processing blocks.

This lesson equips you to answer with evidence:

- Did the request enter Spring Security?
- Which `SecurityFilterChain` was selected, and which filters actually executed?
- When was `SecurityContext` loaded, when were credentials verified, and when was access denied?
- Why did a request stop before the Controller, or run the Controller and fail afterward?
- Distinguish `401`, `403`, `302`, `404`, and `500` by trace evidence rather than guesswork.
- Read Spring Security `DEBUG`/`TRACE` logs in order and correlate them to the same request.
- Place **before/after checkpoints** inside the security chain to observe entry, exit, and short-circuiting.
- Run a **Java 17+ / Spring Boot 4.1.2** application and verify exact traces using `MockMvc`.

Scope is the **Servlet stack** of Spring Security with Spring MVC. WebFlux uses `WebFilter`/`SecurityWebFilterChain` and Reactor Context, without the same `jakarta.servlet.FilterChain` and `DispatcherServlet` model.

## 1. Visualizing the Path of an HTTP Request

Outside-in diagram:

~~~text
Client
  |
  |  GET /me
  |  Authorization: Basic <redacted value>
  v
Reverse proxy / load balancer / TLS termination (if present)
  |
  v
Servlet container: Tomcat/Jetty/Undertow
  |
  +--> Container-level Servlet Filters (if registered)
  |       |
  |       v
  +--> DelegatingFilterProxy ("springSecurityFilterChain")
  |       |
  |       v
  |   Spring Bean: FilterChainProxy
  |       |
  |       +--> HttpFirewall validates/wraps request
  |       +--> Select FIRST matching SecurityFilterChain
  |       |
  |       +--> Security Filter A (e.g., SecurityContextHolderFilter)
  |       +--> Security Filter B (e.g., CsrfFilter)
  |       +--> Security Filter C (e.g., BasicAuthenticationFilter)
  |       +--> Security Filter D (e.g., AnonymousAuthenticationFilter)
  |       +--> Security Filter E (e.g., ExceptionTranslationFilter)
  |       +--> Security Filter F (e.g., AuthorizationFilter)
  |       |
  |       v
  +--> Downstream container filters, if any
  |       |
  |       v
  +--> DispatcherServlet
          |
          +--> HandlerMapping selects Controller method
          +--> HandlerInterceptor.preHandle if present
          +--> Argument resolvers / binding / validation
          +--> Controller
          +--> Service / repository
          +--> Serialize response
          +--> Applicable HandlerInterceptor.postHandle / afterCompletion
  |
  v
HTTP response
~~~

**This is a conceptual diagram**, not an exact list/order for every Spring Security version. Which filters are present depends on whether you enable form login, HTTP Basic, OAuth2 resource server, CSRF, CORS, sessions, logout, custom filters, and separate chains. When debugging, **log the real list from your running app** instead of copying a static list from the Internet.

### Distinguishing Four Component Types

| Component | Position | Purpose |
| --- | --- | --- |
| Servlet `Filter` | Before/after `DispatcherServlet` | Can inspect/block/wrap requests or responses |
| `FilterChainProxy` | Spring Security, invoked by `DelegatingFilterProxy` | Selects one Spring Security filter list per request |
| `HandlerInterceptor` | Spring MVC, after request reaches `DispatcherServlet` | Adds processing around MVC handlers; does not replace security filters |
| Controller/Service | Application layer | Executes business logic after earlier steps allow the request through |

When a Controller breakpoint does not fire, that **does not prove** the Controller is broken. First ask: was the request blocked by a `Filter`, rejected by `HttpFirewall`, redirected, or unmatched to any URL/handler?

A `Filter` can skip calling `chain.doFilter`; when it does, the entire downstream chain is skipped. This is valid Servlet Filter behavior and is exactly how many security filters reject requests.

## 2. chain.doFilter: Inbound Path and Unwind Path

Typical Java Servlet snippet:

~~~java
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    before();                 // Before downstream
    try {
        chain.doFilter(request, response); // Invoke next step
    } finally {
        after();              // After downstream, even on exception
    }
}
~~~

This is an illustrative fragment; `before()` and `after()` are hypothetical application-provided methods, not Servlet APIs.

Suppose filters A, B, and C all call `chain.doFilter` and the Controller succeeds:

~~~text
A: before
  B: before
    C: before
      Controller
    C: after
  B: after
A: after
~~~

The **inbound** order is A → B → C → Controller; the **unwind** order is C → B → A. `finally` blocks unwind down the call stack even when a deeper filter throws an exception (unless the process/JVM terminates abnormally).

If B decides to return `403` without **calling `chain.doFilter`**, neither C nor the Controller runs:

~~~text
A: before
  B: before
  B: reject -> response 403
  B: after (if B has finally)
A: after
~~~

Missing C/Controller entries in a trace **is not necessarily a logging bug**; the pipeline very likely short-circuited legitimately.

### Why Might a Filter Log "after" Yet the Request Still Isn't Finished?

An outer filter can log an "after" line once downstream finishes, yet before the container flushes the full response or completes async work. Even `response.getStatus()` inside a filter **deep in the chain** may not reflect the final HTTP status if an **outer** filter catches an exception and changes the status afterward.

Therefore, know **where each filter sits** when interpreting logs. An `after` mark in a custom filter proves control returned to that point, not always the final HTTP status.

## 3. FilterChainProxy Picks a Chain Before Running Security Filters

Each `SecurityFilterChain` has a `RequestMatcher` and a list of Spring Security filters. `FilterChainProxy` evaluates them in order and uses the **first matching chain**.

Example:

~~~text
@Order(1): securityMatcher("/api/**")
@Order(2): securityMatcher("/admin/**")
@Order(3): default matcher, matches any request

GET /api/data    -> API chain
GET /admin/panel -> Admin chain
GET /web/me      -> fallback chain
~~~

Once the API chain is chosen, if an API filter returns 401, the proxy **does not try** the Admin/Web chains next to find another login method. Filters in later chains are also **never appended** to the first chain.

If no fallback exists and no chain matches, Spring Security may **leave that request unprotected**. This differs sharply from a request that entered a chain yet was allowed by `permitAll()`:

- **No matching chain:** skips the security filters provided by those chains.
- **`permitAll()`:** passes through the selected chain, while the authorization rule grants access.

### Reading Matchers Correctly in Logs

~~~java
http.securityMatcher("/api/**")
    .authorizeHttpRequests(a -> a
        .requestMatchers("/api/public").permitAll()
        .anyRequest().authenticated());
~~~

`securityMatcher` **selects the chain**. `requestMatchers` inside `authorizeHttpRequests` selects the **authorization rule after the chain is selected**. `anyRequest()` here evaluates only requests belonging to that chain, **not URLs outside `/api/**`**.

To read traces accurately, identify the selected chain; otherwise you can misread a rule sitting in a chain that was never invoked.

## 4. Common Filters and Observable Signals

A username/password or HTTP Basic request can traverse multiple stages:

| Stage | Typical Filter / Group | What Can Be Observed |
| --- | --- | --- |
| Request normalization | `HttpFirewall` applied by `FilterChainProxy` | Abnormal paths rejected early, potentially before per-filter logs appear |
| Restore SecurityContext | `SecurityContextHolderFilter` | Context can load lazily from repository and is cleared post-request |
| Security response headers | `HeaderWriterFilter` | Configured protective headers are written |
| CSRF | `CsrfFilter` | POST/PUT/... missing or invalid token can get 403 before Authentication |
| Authentication | `BasicAuthenticationFilter`, `UsernamePasswordAuthenticationFilter`, or token filter | Password/token verified; invalid credentials can end with 401/redirect |
| Anonymous fallback | `AnonymousAuthenticationFilter` | If no identity yet, may set an `AnonymousAuthenticationToken` |
| Security exception translation | `ExceptionTranslationFilter` | Translates auth/access errors to entry point or `AccessDeniedHandler` |
| Authorization | `AuthorizationFilter` | Permits/denies based on request and Authentication |
| MVC dispatch | `DispatcherServlet` | Selects handler, invokes Controller, handles serialization/errors |

**Real chains include other filters too**, such as `DisableEncodeUrlFilter`, `WebAsyncManagerIntegrationFilter`, `LogoutFilter`, `RequestCacheAwareFilter`, and `SecurityContextHolderAwareRequestFilter`. Do not infer from this table that every filter is always present or that CSRF is the first filter.

Broadly: **SecurityContext → exploit protections → authentication → authorization → controller**. To know for sure, inspect the filter list Spring Security prints at startup under DEBUG or per-request TRACE logs.

### 4.1. SecurityContextHolderFilter Is Not Password Verification

`SecurityContextHolderFilter` makes `SecurityContext` from `SecurityContextRepository` available to the request. It **does not verify passwords itself**. With session-based login, context can be restored from the HTTP session; with stateless APIs, another filter authenticates request credentials.

In Spring Security 6/7, `SecurityContextHolderFilter` focuses on **loading** context and does not automatically save on behalf of custom code. Once the request ends, the thread-bound security context must be cleared properly. That does not log the user's session out.

### 4.2. BasicAuthenticationFilter Can Block Before the Controller

Example:

~~~text
GET /me
Authorization: Basic <base64 username:password, not secure encryption>
        |
        v
BasicAuthenticationFilter
        |
   wrong password
        |
        v
AuthenticationEntryPoint -> HTTP 401
        |
    Does not reach Controller
~~~

With a valid password, the provider returns a valid `Authentication`; subsequent steps can use principal/authorities for authorization. Never log Basic credentials in base64: anyone reading the logs can decode the raw password.

### 4.3. CsrfFilter Can Block Before Authentication Even Runs

When CSRF protection is enabled for mutating methods and the request lacks a token:

~~~text
POST /notes
Authorization: Basic <redacted>
        |
        v
CsrfFilter
        |
    missing / invalid CSRF token
        |
        v
AccessDeniedHandler -> HTTP 403
        |
   BasicAuthenticationFilter may not have run
   AuthorizationFilter does not run
   Controller does not run
~~~

This is why **you must never assume 403 always means missing `ROLE_...`**. It can come from CSRF protection rather than `AuthorizationFilter`.

### 4.4. How Does ExceptionTranslationFilter Translate Security Errors?

Conceptual diagram:

~~~text
ExceptionTranslationFilter
    |
    +--> calls downstream: AuthorizationFilter / MVC / service
    |        |
    |        +--> AccessDeniedException or AuthenticationException
    |                 |
    |                 v
    +--> Classify principal state and exception
              |
              +--> Needs authentication -> AuthenticationEntryPoint
              |       HTTP Basic typically 401 + WWW-Authenticate
              |       Form login typically redirects to /login
              |
              +--> Authenticated yet lacks authority
                      -> AccessDeniedHandler
                         typically 403
~~~

It is **not** a catch-all handler for every Java exception. For instance, a `NullPointerException` in a Controller normally follows MVC exception handling and/or error dispatch rather than turning into 403.

On the other hand, if a filter **ahead of `ExceptionTranslationFilter`** blocks the request itself, `ExceptionTranslationFilter` never gets a chance to handle that failure. When tracing a status code, look at filters placed upstream of it as well, not only `ExceptionTranslationFilter`.

## 5. Reading Startup Logs: Which Filters Are Configured?

Add **dev/test-only** configuration to `application.properties`:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

When Spring Security initializes the chain, you can see log output like:

~~~text
DEBUG ... DefaultSecurityFilterChain :
  Will secure any request with [
    ...,
    SecurityContextHolderFilter,
    HeaderWriterFilter,
    CsrfFilter,
    BasicAuthenticationFilter,
    AnonymousAuthenticationFilter,
    ExceptionTranslationFilter,
    AuthorizationFilter
  ]
~~~

This is an **abbreviated illustrative log**, not the exact stdout of the project below. Security version, mode, and enabled features can produce a different list.

You learn three things:

1. **Matcher:** which requests this chain protects (`any request` or another pattern).
2. **Filter list:** the filters actually in the chain, in order.
3. **Custom filter insertion point:** which anchor filter your custom filter sits before/after.

Startup logs alone **do not prove** a given request selected that chain. To know which filters ran for a specific request, you need per-request logs.

### Scoped TRACE Configuration

In dev:

~~~properties
logging.level.org.springframework.security.web.FilterChainProxy=TRACE
~~~

Broader logging can be turned on temporarily when needed:

~~~properties
logging.level.org.springframework.security=TRACE
~~~

These levels generate high volume, expose request metadata, and increase operational cost. **Never leave broad TRACE enabled permanently in production**, and never log `Authorization`, `Cookie`, raw passwords, OTPs, refresh tokens, JWTs, or full `Authentication` objects. Redact sensitive fields and restrict log access.

### What Does a Per-Request Trace Look Like?

~~~text
DEBUG ... FilterChainProxy : Securing GET /me
TRACE ... FilterChainProxy : Invoking DisableEncodeUrlFilter (1/...)
TRACE ... FilterChainProxy : Invoking WebAsyncManagerIntegrationFilter (2/...)
TRACE ... FilterChainProxy : Invoking SecurityContextHolderFilter (3/...)
TRACE ... FilterChainProxy : Invoking HeaderWriterFilter (4/...)
TRACE ... FilterChainProxy : Invoking CsrfFilter (5/...)
...
TRACE ... FilterChainProxy : Invoking BasicAuthenticationFilter (.../...)
...
TRACE ... FilterChainProxy : Invoking AuthorizationFilter (.../...)
DEBUG ... FilterChainProxy : Secured GET /me
~~~

This is an **abbreviated version with `...`**, not meant for verbatim matching in tests. Indices, filter names, and log formats are not stable API contracts. The focus is **the sequence of filters invoked**.

From `Invoking XFilter`, we know `FilterChainProxy` **is about to invoke filter X**, not that filter X allowed the request to proceed. If the trace stops at X, X may have returned a response, thrown an exception, or taken a special branch. Check logs from that filter/entry point/handler plus the response status before concluding.

## 6. Four Typical Scenarios: Pinpointing Where It Stopped

### 6.1. Success: Valid Basic, Authorized

~~~text
Securing GET /me
  -> SecurityContextHolderFilter
  -> HeaderWriterFilter / CsrfFilter ...
  -> BasicAuthenticationFilter
       user=mai authenticated successfully
  -> AnonymousAuthenticationFilter
       does not overwrite existing Authentication
  -> ExceptionTranslationFilter
  -> AuthorizationFilter
       authenticated() rule satisfied
  -> DispatcherServlet
  -> DemoController.me()
  <- HTTP 200 Response
~~~

Not every filter logs a separate "SUCCESS". A successful Controller invocation with a valid `SecurityContext` indicates the request cleared earlier steps, yet you still must test **resource-level authorization** if the service reads private data.

### 6.2. Wrong Password: Blocked at Authentication

~~~text
Securing GET /me
  -> early filters in chain
  -> BasicAuthenticationFilter
       AuthenticationManager/Provider rejects credentials
       AuthenticationEntryPoint handles failure
  <- HTTP 401
  (AuthorizationFilter and Controller do not run in this flow)
~~~

Depending on mechanism, filters/entry points differ; do not insist every failed login must expose `BadCredentialsException` in public logs. In real systems, user-store outages and wrong passwords must be distinguished internally while external responses avoid account enumeration.

### 6.3. Valid Password, Missing Authority: Blocked at Authorization

~~~text
Securing GET /admin
  -> BasicAuthenticationFilter
       user=mai authenticated successfully
  -> AuthorizationFilter
       requires ROLE_ADMIN; mai has only ROLE_USER
       throws AccessDeniedException
  <- ExceptionTranslationFilter/AccessDeniedHandler
  <- HTTP 403
  (Controller /admin does not run)
~~~

If code in `AuthorizationFilter` throws an exception, filters **deeper** do not run, while `finally` blocks of filters wrapping the downstream segment can still execute before the handler writes the response status.

### 6.4. Missing CSRF: Denied Before Authorization

~~~text
Securing POST /notes
  -> SecurityContextHolderFilter
  -> HeaderWriterFilter
  -> CsrfFilter
       missing or invalid CSRF token
       AccessDeniedHandler -> 403
  <- HTTP 403
  (BasicAuthenticationFilter, AnonymousAuthenticationFilter,
   AuthorizationFilter, and Controller do not necessarily run)
~~~

If you only put a custom filter **right before `AuthorizationFilter`**, you **will not see your custom log** in this scenario. That is a consequence of filter placement, not proof that the request bypassed Spring Security.

## 7. Runnable Project: Marking a Request at Three Key Checkpoints

We will build a Spring MVC Servlet project with three main markers:

1. **ENTRY:** a custom `OncePerRequestFilter` placed **before `SecurityContextHolderFilter`** in the security chain. It marks the entry of **the chain segment we want to observe** without claiming to be the very first filter in the entire Servlet container; standard framework filters can precede it.
2. **BEFORE_AUTHORIZATION:** a second custom filter placed **before `AuthorizationFilter`**, after normal authentication steps. It records the recognized principal name (only in a learning-environment request attribute).
3. **CONTROLLER:** the Controller records a mark when the handler method is actually invoked.

Each filter also records a `finally` mark when downstream returns control. On a successful request, the expected sequence is:

~~~text
01 security-entry
02 before-authorization:mai
03 controller
04 after-authorization
05 security-exit
~~~

For requests blocked **before authorization**, markers 02/03/04 are absent while 01/05 can still appear. For requests denied **by `AuthorizationFilter`**, markers 02 and 04 appear, while 03 is absent.

**Important warning:** the two custom filters below write solely to an **`HttpServletRequest` attribute**, read back by tests. They do not expose traces in HTTP headers/bodies and never log passwords. This is a safer way to illustrate filter placement; it does not replace real distributed tracing/observability.

### 7.1. Structure

~~~text
servlet-filter-trace-lab/
  pom.xml
  src/main/java/com/example/trace/
    FilterTraceApplication.java
    SecurityConfiguration.java
    TraceSupport.java
    DemoController.java
  src/test/java/com/example/trace/
    FilterTraceIntegrationTest.java
~~~

APIs used: Java 17, Spring Boot **4.1.2**, Spring Security managed by Boot BOM, `OncePerRequestFilter`, `SecurityContextHolderFilter`, `AuthorizationFilter`, `Authentication`, and MockMvc.

### 7.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>servlet-filter-trace-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-test</artifactId>
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
~~~

Spring Boot parent manages dependency versions for Security, Spring MVC, and tests. Do not specify `spring-security-web`/`spring-security-test` versions manually. In Spring Boot 4, the MVC starter is named `spring-boot-starter-webmvc`; avoid blindly copying `spring-boot-starter-web` from Boot 3 tutorials without checking differences.

### 7.3. Main Class

Create `src/main/java/com/example/trace/FilterTraceApplication.java`:

~~~java
package com.example.trace;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterTraceApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterTraceApplication.class, args);
    }
}
~~~

### 7.4. TraceSupport.java: Recording Markers on HttpServletRequest

Create `src/main/java/com/example/trace/TraceSupport.java`:

~~~java
package com.example.trace;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

// Invoked by Spring Security filters/Controller within the same request.
// Do not expose trace attribute in production responses.
final class TraceEvents {
    static final String ATTRIBUTE =
        TraceEvents.class.getName() + ".EVENTS";

    private TraceEvents() {
    }

    @SuppressWarnings("unchecked")
    static void add(HttpServletRequest request, String step) {
        List<String> steps =
            (List<String>) request.getAttribute(ATTRIBUTE);
        if (steps == null) {
            steps = new ArrayList<>();
            request.setAttribute(ATTRIBUTE, steps);
        }
        steps.add(step);
    }

    @SuppressWarnings("unchecked")
    static List<String> snapshot(HttpServletRequest request) {
        List<String> steps =
            (List<String>) request.getAttribute(ATTRIBUTE);
        return steps == null ? List.of() : List.copyOf(steps);
    }
}

// Do not use @Component / @Bean on this filter:
// add solely via HttpSecurity.addFilterBefore to avoid double registration.
final class EntryTraceFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        TraceEvents.add(request, "01 security-entry");
        try {
            filterChain.doFilter(request, response);
        } finally {
            TraceEvents.add(request, "05 security-exit");
        }
    }
}

final class BeforeAuthorizationTraceFilter
        extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        Authentication auth =
            SecurityContextHolder.getContext().getAuthentication();
        String name = (auth == null) ? "none" : auth.getName();

        TraceEvents.add(
            request, "02 before-authorization:" + name);

        try {
            filterChain.doFilter(request, response);
        } finally {
            TraceEvents.add(request, "04 after-authorization");
        }
    }
}
~~~

Note: `TraceSupport.java` holds **three package-private classes** with no `public` class. Java allows this; the filename need not match the package-private class names. All three share a package with the Controller and `SecurityConfiguration`, so they are directly accessible.

Key points to grasp:

- `EntryTraceFilter` runs before `SecurityContextHolderFilter`, so upon entering **do not expect** `SecurityContextHolder` to hold the request's principal yet. It only records a marker.
- `BeforeAuthorizationTraceFilter` sits before `AuthorizationFilter`; with valid HTTP Basic, Authentication is already populated, so it can read `auth.getName()`.
- `TraceEvents` is a request attribute **strictly for synchronous demos**. Never turn this `ArrayList` into a concurrent/async production trace store; async requires thread-safety and lifecycle handling.
- Each filter uses `try/finally`, making the unwind path observable even when downstream throws an exception.
- `OncePerRequestFilter` has specific rules for async/error dispatches. "Once" does not guarantee a single dispatch in every situation; check `shouldNotFilterAsyncDispatch()`/`shouldNotFilterErrorDispatch()` when extending.

### 7.5. SecurityConfiguration.java

Create `src/main/java/com/example/trace/SecurityConfiguration.java`:

~~~java
package com.example.trace;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.intercept.AuthorizationFilter;
import org.springframework.security.web.context.SecurityContextHolderFilter;

@Configuration(proxyBeanMethods = false)
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
            User.withUsername("mai")
                .password(encoder.encode("demo-password"))
                .roles("USER")
                .build(),
            User.withUsername("admin")
                .password(encoder.encode("demo-password"))
                .roles("ADMIN")
                .build()
        );
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .addFilterBefore(
                new EntryTraceFilter(),
                SecurityContextHolderFilter.class
            )
            .addFilterBefore(
                new BeforeAuthorizationTraceFilter(),
                AuthorizationFilter.class
            )
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

We use **one `SecurityFilterChain`** with the default match-all matcher to avoid multi-chain complexity while learning tracing. HTTP Basic lets `curl` or MockMvc send credentials per request.

Why place the two checkpoints at two different positions?

| Custom Filter | Position | What Does It See? |
| --- | --- | --- |
| `EntryTraceFilter` | Before `SecurityContextHolderFilter` | The request entered the security chain segment containing the marker |
| `BeforeAuthorizationTraceFilter` | Before `AuthorizationFilter` | Authentication after Basic/anonymous steps, if downstream reached here |
| `AuthorizationFilter` | After checkpoint 02 | Can deny and prevent Controller execution |
| Controller | After filters | Invoked only once the request passes security filtering and handler matching |

**Do not put `@Component` on the demo filters.** If Spring Boot auto-registers a `Filter` bean on the Servlet container and you also `addFilterBefore` that object/class into the security chain, it can run twice or in the wrong slot. Two separate classes also let the framework distinguish custom filter ordering by filter type rather than adding multiple instances of one class at different slots.

### 7.6. DemoController.java

Create `src/main/java/com/example/trace/DemoController.java`:

~~~java
package com.example.trace;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicPage(HttpServletRequest request) {
        TraceEvents.add(request, "03 controller");
        return "public";
    }

    @GetMapping("/me")
    public String me(
            HttpServletRequest request,
            Authentication authentication) {
        TraceEvents.add(request, "03 controller");
        return "hello-" + authentication.getName();
    }

    @GetMapping("/admin")
    public String admin(
            HttpServletRequest request,
            Authentication authentication) {
        TraceEvents.add(request, "03 controller");
        return "admin-" + authentication.getName();
    }

    @PostMapping("/notes")
    public String createNote(
            HttpServletRequest request,
            Authentication authentication) {
        TraceEvents.add(request, "03 controller");
        return "created:" + authentication.getName();
    }
}
~~~

Keep methods simple so **business logic is not confused with security**. In real apps, services must additionally verify resource, owner, tenant, and transaction permissions; `hasRole("ADMIN")` does not automatically authorize reading every piece of data.

`POST /notes` illustrates CSRF without persisting real data. The code leaves CSRF enabled; tests intentionally send a request missing a token to observe it being blocked.

### 7.7. MockMvc Integration Tests: Verifying Order via Request Attributes

Create `src/test/java/com/example/trace/FilterTraceIntegrationTest.java`:

~~~java
package com.example.trace;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;

import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class FilterTraceIntegrationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void successfulRequestVisitsBothFiltersAndController()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/me").with(httpBasic("mai", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("hello-mai"))
            .andReturn();

        assertEquals(List.of(
            "01 security-entry",
            "02 before-authorization:mai",
            "03 controller",
            "04 after-authorization",
            "05 security-exit"
        ), TraceEvents.snapshot(result.getRequest()));
    }

    @Test
    void missingCredentialsStopBeforeController()
            throws Exception {
        MvcResult result = mvc.perform(get("/me"))
            .andExpect(status().isUnauthorized())
            .andReturn();

        List<String> events =
            TraceEvents.snapshot(result.getRequest());
        assertTrue(events.contains("01 security-entry"));
        assertTrue(events.contains("05 security-exit"));
        assertFalse(events.contains("03 controller"));
    }

    @Test
    void wrongPasswordStopsBeforeController()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/me").with(httpBasic("mai", "incorrect")))
            .andExpect(status().isUnauthorized())
            .andReturn();

        assertFalse(
            TraceEvents.snapshot(result.getRequest())
                .contains("03 controller"));
    }

    @Test
    void missingRoleStopsAtAuthorization()
            throws Exception {
        MvcResult result = mvc.perform(
                get("/admin").with(httpBasic("mai", "demo-password")))
            .andExpect(status().isForbidden())
            .andReturn();

        List<String> events =
            TraceEvents.snapshot(result.getRequest());
        assertTrue(
            events.contains("02 before-authorization:mai"));
        assertTrue(events.contains("04 after-authorization"));
        assertFalse(events.contains("03 controller"));
    }

    @Test
    void missingCsrfTokenStopsBeforeAuthorization()
            throws Exception {
        MvcResult result = mvc.perform(
                post("/notes").with(httpBasic("mai", "demo-password")))
            .andExpect(status().isForbidden())
            .andReturn();

        List<String> events =
            TraceEvents.snapshot(result.getRequest());
        assertTrue(events.contains("01 security-entry"));
        assertFalse(events.contains("03 controller"));
        assertFalse(
            events.stream().anyMatch(s ->
                s.startsWith("02 before-authorization")));
    }

    @Test
    void validCsrfAndPasswordReachController()
            throws Exception {
        MvcResult result = mvc.perform(
                post("/notes")
                    .with(csrf())
                    .with(httpBasic("mai", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("created:mai"))
            .andReturn();

        assertEquals(List.of(
            "01 security-entry",
            "02 before-authorization:mai",
            "03 controller",
            "04 after-authorization",
            "05 security-exit"
        ), TraceEvents.snapshot(result.getRequest()));
    }

    @Test
    void publicEndpointStillRunsSecurityFilters()
            throws Exception {
        MvcResult result = mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(content().string("public"))
            .andReturn();

        List<String> events =
            TraceEvents.snapshot(result.getRequest());
        assertTrue(events.contains("01 security-entry"));
        assertTrue(events.contains("03 controller"));
        assertTrue(events.contains("05 security-exit"));
    }

    @Test
    void adminCanReachAdminController()
            throws Exception {
        mvc.perform(
                get("/admin")
                    .with(httpBasic("admin", "demo-password")))
            .andExpect(status().isOk())
            .andExpect(content().string("admin-admin"));
    }
}
~~~

These are **eight integration tests** traversing Spring Security and Spring MVC, not direct controller method calls. They focus on three questions:

- When **allowed**, does marker ordering match the expected inbound/unwind sequence?
- When **blocked**, is the Controller marker absent and which checkpoints still appear?
- When `/public` is `permitAll`, does the request **still traverse security filters**? Yes.

The `missingCsrfTokenStopsBeforeAuthorization` test highlights an especially important behavior: the request is blocked by `CsrfFilter` **before** the custom checkpoint ahead of `AuthorizationFilter`, so marker 02 does not appear even though the request entered Spring Security.

Several technical details when reading the tests:

1. Spring Security Test's `httpBasic("mai","demo-password")` adds the Authorization header to the MockMvc request rather than pre-marking Mai authenticated; `BasicAuthenticationFilter` still verifies the password via the provider.
2. `csrf()` supplies a valid CSRF token for the POST test; no need to disable CSRF in `SecurityFilterChain`.
3. `@SpringBootTest` + `@AutoConfigureMockMvc` uses the sample app's real filter chain.
4. Traces are stored in a request attribute, so tests read them back from `result.getRequest()` without relying on timestamps or thread order.
5. This is a **synchronous demo** with single requests and no async dispatch; if adding `Callable`, `DeferredResult`, or `@Async`, add lifecycle tests.
6. When an outer filter such as `ExceptionTranslationFilter` handles an error from `AuthorizationFilter`, marker `04 after-authorization` can be recorded in `finally` **before** the outer filter sets status 403. Hence tests assert markers and HTTP status **independently** rather than pretending marker 04 knows the final status.

### 7.8. Running Commands

In the directory containing `pom.xml`:

~~~bash
java -version
mvn -version
mvn test
mvn spring-boot:run
~~~

Observable outcomes:

- `mvn test` runs **8 tests**; the tests are designed to pass with Spring Boot 4.1.2 and BOM-compatible dependencies.
- `GET /me` with the valid demo password returns body `hello-mai`.
- Anonymous `GET /me` and wrong passwords typically return HTTP 401 due to HTTP Basic.
- `GET /admin` as Mai returns 403; as Admin returns 200 and body `admin-admin`.
- `POST /notes` missing a CSRF token returns 403; the test with `csrf()` and valid Basic returns 200 with body `created:mai`.
- `GET /public` returns 200 yet still carries markers from the security chain.

These are **expected outcomes based on the code and documentation**, not a report of an actual Maven run in the learner's environment. Console output may include timestamps, thread names, bootstrap warnings, and machine-specific details.

Manual checks with **local dummy passwords only**:

~~~bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me
curl -i -u mai:demo-password http://localhost:8080/me
curl -i -u mai:demo-password http://localhost:8080/admin
curl -i -u admin:demo-password http://localhost:8080/admin
~~~

Key outputs/statuses (abbreviated, not pretending to be full HTTP transcripts):

~~~text
GET /public                   -> 200 body=public
GET /me without credentials   -> 401
GET /me as mai                -> 200 body=hello-mai
GET /admin as mai             -> 403
GET /admin as admin           -> 200 body=admin-admin
~~~

Never run `curl -u` with real passwords on shared machines, because secrets can leak via command history/process inspection. Never send HTTP Basic over the Internet without TLS.

**Never send `curl -X POST`, see 403, and conclude Basic auth failed.** CSRF is a separate mechanism: supply valid cookies and tokens or use MockMvc `.with(csrf())` in tests rather than disabling protections for convenience.

## 8. Reading Traces in Real Apps Where TraceEvents Does Not Exist

The project above is a **checkpoint-marking exercise** to understand the mechanics. In real systems, you usually rely on:

- Trace IDs or correlation IDs generated by gateways/observability.
- Reverse proxy/load balancer access logs.
- Servlet container access logs.
- Spring Security `FilterChainProxy` DEBUG/TRACE logs.
- Authentication success/failure events.
- Application loggers in Controllers/Services.
- Database spans/metrics from observability instrumentation.
- Redacted `AccessDeniedHandler`/`AuthenticationEntryPoint` logging.

To "follow a single request" without mixing requests, attach a **correlation ID** issued/validated by a trusted party. If clients send `X-Request-ID`, validate format/length to prevent untrusted values from causing log injection; many systems generate their own gateway IDs or replace invalid values.

Example **illustrative log with sensitive data redacted**:

~~~text
19:42:10.101 INFO  [req=9af3] ingress GET /me
19:42:10.102 DEBUG [req=9af3] FilterChainProxy Securing GET /me
19:42:10.105 TRACE [req=9af3] Invoking BasicAuthenticationFilter
19:42:10.121 INFO  [req=9af3] auth outcome=success actorId=101
19:42:10.122 TRACE [req=9af3] Invoking AuthorizationFilter
19:42:10.124 INFO  [req=9af3] controller=me outcome=success
19:42:10.126 INFO  [req=9af3] egress status=200 durationMs=25
~~~

This is not a built-in default log template from Spring Security; lines like `ingress`, `auth outcome`, `controller`, and `egress` are instrumentation points an operations team **can design**. Framework logs also do not share a `req` field automatically unless tracing/MDC or structured logging propagation is configured.

### Using MDC

Logger MDC typically relies on `ThreadLocal`. In synchronous Servlet requests, an outer servlet filter can put a correlation ID into MDC at request start and **remove it in `finally`** so it never leaks to the next request on a pooled thread. With async dispatches, thread switches, or reactive pipelines, use proper context propagation rather than assuming `ThreadLocal` carries over automatically.

Conceptual snippet:

~~~java
String requestId = validatedRequestIdOrNewId(request);
org.slf4j.MDC.put("requestId", requestId);
try {
    chain.doFilter(request, response);
} finally {
    org.slf4j.MDC.remove("requestId");
}
~~~

This is a **fragment**; variables and `validatedRequestIdOrNewId` are undefined. Its purpose is illustrating MDC ownership, not guaranteeing that logging filter is registered ahead of every Spring Security filter.

**Never use usernames/emails, session IDs, or JWTs as trace IDs.** Correlation IDs must never expose private data or act as credentials.

## 9. Symptom-Based Debugging: What Appears vs. What Is Missing?

| Symptom | Possible Cause | Next Check |
| --- | --- | --- |
| No access log at the app | Request blocked by proxy/firewall/network upstream | Gateway logs, routing, DNS, container listener |
| Access log shows request, yet no Spring Security log | No chain matched, wrong proxy registration, insufficient log level | `springSecurityFilterChain`, `securityMatcher`, log config |
| `FilterChainProxy` logs `Securing...`, then firewall rejects | Path violates firewall policy | `StrictHttpFirewall`, encoded slashes, semicolons, double slashes |
| Log stops at `CsrfFilter`, returns 403 | Missing or invalid CSRF | Cookie/token, HTTP method, origin, response handler |
| Log stops at Basic authentication, returns 401 | Bad password/token or provider error | Internal auth event/error; avoid exposing credentials |
| Pre-authorization mark exists, no Controller, returns 401 | Unauthenticated or anonymous prompted to log in | Entry point, chain, `authenticated()` |
| Pre-authorization mark exists, no Controller, returns 403 | Missing role/authority or policy denial | `AuthorizationFilter`, `AccessDeniedHandler`, authorities |
| Controller breakpoint hit, yet response is 500 | Handler/service/serialization bug or method security exception | Controller logs, filtered stack trace, exception handler |
| Controller ran, yet response is 403 | Method security or service policy threw `AccessDeniedException` | `@PreAuthorize`, service permissions, `ExceptionTranslationFilter` |
| `GET /api` returns `302 /login` instead of 401 | Request fell into form-login chain | `@Order`, `securityMatcher`, entry point |
| `GET /login` returns 404 | Filter-generated endpoint outside security matcher, or no handler | Chain covering login URL, `formLogin` config |
| Custom filter runs twice per request | Registered in both container and `HttpSecurity`, or multiple dispatches | `FilterRegistrationBean`, `addFilterBefore`, dispatcher types |
| Only initial request has context; next request is anonymous | Context not saved/cookie not sent, or stateless policy | `SecurityContextRepository`, session ID, explicit-save |
| Traces mixed across two users | Static/global mutable trace, uncleaned MDC, thread reuse | Per-request state and context propagation |

**Never jump to conclusions from a single log line.** Correlate HTTP method/path, correlation ID, final status, selected security chain, and Controller trace together.

## 10. Different Stopping Points Producing 401/403/302/404/500

### HTTP 401 Unauthorized

Usually means the request **lacks valid Authentication** and a Basic/Bearer entry point demands proof of identity. With Basic, `WWW-Authenticate` may be present. `401` does not mean "controller saw a wrong password": in most cases it stops inside a filter.

### HTTP 403 Forbidden

Could be:

1. Authenticated user lacks required authority.
2. Missing/invalid CSRF token on a mutating HTTP method.
3. Custom CORS/security policy or custom filter.
4. Method security in the service layer denying access.
5. Custom `AccessDeniedHandler` returning 403.

**Different stopping points.** Read the trace to see whether `CsrfFilter`, `AuthorizationFilter`, or the service denied it.

### HTTP 302 Redirect

With form login, unauthenticated requests may redirect to `/login`. Do not treat every 302 as a business error; it can be a security entry point. Flows also redirect after login, logout, or OAuth2. When tracing across requests, redirects initiate a **new HTTP request**; correlation IDs may not automatically match unless span/trace propagation is designed.

### HTTP 404 Not Found

Either `DispatcherServlet` found no handler, or a filter-generated endpoint like `/login` is missing from the chain you thought ran. `404` **does not prove** whether Spring Security protected the URL. A request can clear every security filter and still have no Controller mapping.

### HTTP 500 Internal Server Error

Can originate in a Controller, Service, serializer, Servlet filter, or exception handler. If an exception arises **before** `DispatcherServlet`, `@ControllerAdvice` does not automatically handle it; filter/container-level error handling is needed. When errors happen inside MVC handlers, `HandlerExceptionResolver` and error dispatches may participate.

**Safety policy:** internal logs need enough detail to fix issues, whereas client response bodies must omit stack traces, SQL, private keys, tokens, and exact security config descriptions.

## 11. "Invoking XFilter" Does Not Mean "Passed XFilter"

With per-request TRACE:

~~~text
TRACE ... Invoking BasicAuthenticationFilter (8/15)
~~~

The core meaning is that `FilterChainProxy` is **about to call** that filter. Several outcomes are possible:

- The filter calls `chain.doFilter`: an `Invoking NextFilter` line follows.
- The filter detects invalid credentials and writes 401 directly: no `NextFilter` line appears.
- The filter throws an exception handled by an outer filter: exception/entry-point logs may appear during unwind.
- The filter redirects (e.g., logout/login success): the request ends or turns into a new request without hitting the original controller.
- The filter passes through, yet the Controller is later blocked by an MVC interceptor: Spring Security's trace may finish before the business failure.

Distinguish **call invocation** from **filter outcome**. Never read `(7/15)` and assume 7 filters approved the request.

### Startup Filter List vs. Runtime Invocations

| Source | Tells You | Does Not Prove |
| --- | --- | --- |
| `DefaultSecurityFilterChain` DEBUG at startup | Which filters are configured in each chain | That a specific request traversed all of them |
| `FilterChainProxy` TRACE during a request | Which filters started running for that specific request | That the filter forwarded downstream or succeeded |
| Authentication provider logs/events | Identity verification result | That the user has permission on the resource |
| Authorization/access denied logs | Policy reason access was denied | That the Controller definitely ran |
| Controller logs | Handler method was entered | That subsequent async/callbacks finished |
| Container/proxy access logs | Final method/path/status | Which internal filter logic caused that status |

Use **multiple layers of evidence** during serious incidents, especially when proxies, dispatches, or async processing can alter paths.

## 12. When You Need to Know Which Filter Runs Before/After Another

Spring Security standardizes the order of many key filters. You can use these APIs:

~~~java
http.addFilterBefore(customFilter, BasicAuthenticationFilter.class);
http.addFilterAfter(customFilter, BasicAuthenticationFilter.class);
http.addFilterAt(customFilter, BasicAuthenticationFilter.class);
~~~

These are **fragments**, not standalone programs; `customFilter` must be a proper Servlet `Filter` and you must understand registered order. `addFilterAt` does not guarantee another class at that same slot is completely removed in every situation; read the specific contract and test.

Placement depends on what data you need:

| Goal | Where to Place Checkpoint? | Why |
| --- | --- | --- |
| Detect early entry into Spring Security | Before `SecurityContextHolderFilter` or near chain start | Does not depend on authentication yet |
| Inspect current `SecurityContext` | After context holder loads / identity is populated | Earlier, identity may be null |
| Observe Basic authentication outcome | Place marker before/after Basic per goal, paired with event/provider logs | Bad passwords can stop at Basic |
| Need role/identity before authorization | After auth/anonymous, before `AuthorizationFilter` | Identity is ready for policy evaluation |
| Observe whether Controller ran | `HandlerInterceptor`, controller instrumentation, or service logs | Security filters cannot prove the controller executed |
| Observe final request outcome | Outer container filter/access log with async awareness | Deep filters may not see the final status |

Never register a `@Component Filter` on the Servlet container and also `addFilterBefore` it into the Security chain: it can **run twice**. For the demo filters, we instantiate `new EntryTraceFilter()` and `new BeforeAuthorizationTraceFilter()` directly when building `HttpSecurity`, never registering them as standalone `Filter` beans.

## 13. Which Point Is "The First Filter"?

The phrase "the first filter" has **at least three meanings**:

1. The first filter at the **reverse proxy/gateway** layer. It does not even run inside the JVM.
2. The first filter in the **Servlet container chain**. Perhaps request logging, character encoding, or tracing, sitting ahead of `DelegatingFilterProxy`.
3. The first filter in the **selected `SecurityFilterChain`**. That list may begin with internal filters such as `DisableEncodeUrlFilter`, depending on config/version.

The `EntryTraceFilter` checkpoint in the demo is placed **before `SecurityContextHolderFilter`**, not necessarily ahead of every Spring Security filter. Thus it does not directly measure gateway ingress or `HttpFirewall` rejections before chain execution starts.

If a request is rejected by the firewall **before chain selection**, `EntryTraceFilter`'s marker will not appear even though the HTTP request reached the container. To observe the entire journey, combine **container ingress traces**, Spring Security filter TRACE logs, and Controller traces.

### Snippet: An Outer Container-Level Observation Filter

This is an **advanced fragment** (not needed for the runnable demo project):

~~~java
// Fragment: requires an application-provided IngressFilter implementation.
@Bean
FilterRegistrationBean<IngressFilter> ingressFilter() {
    var registration =
        new FilterRegistrationBean<>(new IngressFilter());
    registration.addUrlPatterns("/*");
    registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
    return registration;
}
~~~

This container filter can log "received GET /me" before reaching Spring Security (depending on other filter registrations), then log status when downstream finishes. To be sure which container filter runs before another, check actual registration orders and dispatcher types rather than relying on `@Order` on `SecurityFilterChain`s.

**Never use outer filters to log request bodies/passwords.** If you need correlation IDs, process only approved metadata fields; with async responses be careful because `chain.doFilter` can return before work finishes.

## 14. When a Request Does Not Reach the Controller, Check MVC Routing Too

A request can pass **every Spring Security filter** and still miss the intended handler, because `DispatcherServlet` still performs:

1. Determining which `HandlerMapping` holds a mapping.
2. Matching HTTP method and path.
3. Checking `consumes`, `produces`, params, headers, and versioning if configured.
4. Executing `HandlerInterceptor.preHandle`, which may return `false`.
5. Resolving arguments and binding/validating input; errors can throw before calling the method.
6. Invoking the Controller method.
7. Running conversion/serialization and response handling.
8. Handling exceptions via resolvers/advice and possibly an error dispatch.

Therefore "the trace shows `AuthorizationFilter` finished" does not guarantee the Controller ran. The request may have missed MVC mappings, carried malformed JSON, or been stopped by another filter/interceptor.

### Regarding ControllerAdvice

`@ControllerAdvice` or `@RestControllerAdvice` is MVC's exception-handling mechanism, **not** a blanket replacement for errors occurring before `DispatcherServlet`. An `AuthenticationEntryPoint` or `AccessDeniedHandler` normally handles errors raised in the Security filter chain, while advice handles MVC exceptions.

If a business exception occurs in a service and advice translates it into 400/500, Spring Security logs can still report that the filter chain completed. Read the actual stack trace and dispatch sequence instead of blaming Security for every error.

## 15. Request Dispatches, Async, and Multi-Pass Traces

Servlets support dispatcher types such as `REQUEST`, `FORWARD`, `ERROR`, and `ASYNC`. One URL can spawn additional dispatches:

~~~text
REQUEST /me
  |
  +--> Security filters
  +--> DispatcherServlet / Controller
           |
           +--> exception
                   |
                   v
                ERROR dispatch /error
                   |
                   +--> filters/handlers run per config
~~~

`OncePerRequestFilter` guards against repeated calls within certain dispatches per its contract, and can be customized via:

~~~java
@Override
protected boolean shouldNotFilterAsyncDispatch() {
    return true;  // demo skips async dispatch
}

@Override
protected boolean shouldNotFilterErrorDispatch() {
    return true;  // demo skips error dispatch
}
~~~

This is a **fragment** for a custom `OncePerRequestFilter`. Many defaults already skip those dispatches, yet you must verify against your version and container. Never assume trace line count always equals HTTP request count when async/error dispatches happen.

For long-running async requests, a Filter's "after" on the initial request may run before the final async result is sent. Use `AsyncListener` events or async-aware interceptors/observability when measuring **true end-to-end response completion time**.

### SecurityContext Across Async

Spring Security integrates with Servlet/MVC async to propagate context in specific scenarios. Never assume spawning `new Thread` or an `ExecutorService` carries `SecurityContextHolder` automatically; you may need `DelegatingSecurityContextExecutor` or explicit `CurrentActor` propagation per policy. When context is missing or leaked, thread IDs in logs will not separate users reliably.

## 16. Common Trace-Interpretation Mistakes

1. **"No Controller log means the request never reached the backend."** False; filters/proxies can block it.
2. **"Seeing FilterChainProxy logs means all filters ran to completion."** No; filters can short-circuit.
3. **"Invoking CsrfFilter means CSRF passed."** No; that logs filter entry, not the verdict.
4. **"401 means missing `ROLE_ADMIN`."** Usually unauthenticated; missing role for an authenticated user is typically 403.
5. **"403 is always from `AuthorizationFilter`."** It can come from CSRF or custom filters.
6. **"Password is valid yet POST gives 403, so `DaoAuthenticationProvider` is broken."** CSRF can block before the Basic filter even runs.
7. **"ExceptionTranslationFilter catches every exception in the app."** No; it primarily translates matching security exceptions.
8. **"`SecurityContextHolderFilter` verifies passwords."** No; it loads context.
9. **"Seeing `anonymousUser` means login succeeded."** No; that is typically the anonymous authentication fallback.
10. **"`permitAll` means no security filters run."** No; requests still traverse the chain.
11. **"A request can run multiple `SecurityFilterChain`s cumulatively."** No; the first matching chain is selected.
12. **"No fallback chain means unmatched URLs are blocked by default."** No; they may bypass Spring Security.
13. **"Status read inside a deep filter is always the final status."** No; outer filters can alter status later.
14. **"Missing `after` line proves the filter never ran."** The filter might lack a `finally` log, or hit async/abnormal termination.
15. **"One HTTP request always equals one Servlet dispatch."** No; `ERROR`/`FORWARD`/`ASYNC` dispatches can occur.
16. **"`OncePerRequestFilter` guarantees strictly once across all dispatches."** Do not assume that; understand skip/dispatch options.
17. **"`ControllerAdvice` catches every `AuthenticationException` from filters."** No; MVC advice does not replace Security entry points.
18. **"Using JWT or session cookies as trace IDs is convenient."** No; putting secrets in logs is a serious risk.
19. **"Leaving TRACE on permanently in production is always better."** No; high overhead and risk of leaking sensitive metadata.
20. **"Logging full `Authentication` is safe because Spring erases credentials."** Custom principals/details can still hold sensitive data.
21. **"200 proves the request was properly authorized."** No; the URL might have matched no chain or lacked a policy.
22. **"Enabling DEBUG on Spring MVC shows all security filter invocations."** No; you need Spring Security's loggers.
23. **"`@Order` on a filter and `@Order` on a `SecurityFilterChain` are equivalent."** No; one governs container/filter order, the other chain selection.
24. **"A custom `@Component` Filter passed to `addFilterBefore` cannot run twice."** It can double-register.
25. **"TRACE logs can be used to recover forgotten user passwords."** Never; never log credentials.
26. **"A browser redirect to `/login` is the same request continuing."** Redirects initiate a new HTTP request.
27. **"A filter that skipped downstream must have thrown a 500 error."** No; filters can legitimately complete responses.
28. **"Spring Security infers roles from URLs without Authentication."** Authorization requires an identity or explicit policy; never trust client-asserted roles.
29. **"Thread ID suffices to correlate logs in a thread pool."** No; threads are reused—use correlation IDs/spans.
30. **"Testing with `@WithMockUser` proves Basic passwords are verified."** No; it injects a pre-built test Authentication.
31. **"Testing 200 on `/public` proves the filter chain works."** No; assert traces/filters or test protected endpoints.
32. **"Seeing a custom marker before `AuthorizationFilter` proves every upstream filter succeeded."** It proves flow reached that checkpoint, not how every policy behaved.

## 17. Test Matrix When an Endpoint Suddenly Fails

| Request | Stages It Should Reach | Expected | Trace Check |
| --- | --- | --- | --- |
| Anonymous `GET /public` | Security chain + Controller | 200 | Entry, authz, controller, and unwind markers present |
| `GET /me` valid Basic | Auth + Authorization + Controller | 200 | Expected `Authentication.getName()`, all 5 markers |
| `GET /me` no credentials | Authorization → entry point | 401 | No Controller marker |
| `GET /me` wrong password | Basic filter | 401 | No Controller, auth failure logged |
| `GET /admin` Mai lacks role | `AuthorizationFilter` | 403 | Pre-authz marker present, no Controller |
| `GET /admin` Admin has role | Controller | 200 | Controller present, expected body |
| `POST /notes` missing CSRF | `CsrfFilter` | 403 | Does not reach pre-authorization marker |
| `POST /notes` valid CSRF + Basic | Controller | 200 | All 5 markers present |
| `GET /unknown` | Security chain, then MVC routing | Depends on auth; if authenticated typically 404 | Cleared Security yet no handler |
| Unauthenticated form login | Form `AuthenticationEntryPoint` | 302 | Redirects to login URL in right chain |
| Abnormal URL encoding | `HttpFirewall` | Possibly 400/reject | May stop before custom security marker |
| `/api/**` missing fallback | No chain match | Bypass risk | No filter trace, yet Controller may run |
| Exception in service | Controller/Service | 5xx/handler-specific | Controller marker present; inspect filtered stack trace |
| `ERROR` dispatch | Servlet ERROR path | Depends on policy | May trigger extra filter/log pass |
| Async processing | Thread switch/dispatch | Depends on outcome | Correlation ID, not solely thread name |

**Always test negative paths**: a request blocked at the right stage is a valid security outcome. Testing only happy paths easily hides missing fallback matchers or bypassed role checks.

### Reviewing a Bug Report

A useful recording template, **containing no credentials**:

~~~text
Request ID: req-2026-0012
Method/path: POST /notes
Expected: 200
Actual: 403
Chain matched: catch-all servlet security chain
Last observed filter: CsrfFilter
Security decision: invalid/missing CSRF token
Controller invoked: no
Sensitive data in report: none
Root cause hypothesis: frontend did not send a valid CSRF token
Fix/verification: send token via standard flow; MockMvc.with(csrf())
~~~

This is dummy sample data for trace-reading practice, not a real incident log. "Last observed filter" must come from live runtime evidence, never guesswork.

## 18. Plain Java 17: Learning the Before/After Stack with Exact Stdout

To understand `chain.doFilter` mechanics without booting Spring, we can simulate a filter list using `Runnable`. This program **does not replace Spring Security**; it teaches nested calls and short-circuiting.

Create `FilterWalkthrough.java`:

~~~java
import java.util.List;

public class FilterWalkthrough {

    @FunctionalInterface
    interface Filter {
        void apply(Runnable next);
    }

    static Filter trace(String name) {
        return next -> {
            System.out.println("> " + name);
            try {
                next.run();
            } finally {
                System.out.println("< " + name);
            }
        };
    }

    static Filter reject(String name) {
        return next -> {
            System.out.println("> " + name);
            System.out.println("RESPONSE 403");
            // Does not call next.run(), so subsequent steps are skipped.
        };
    }

    static Runnable compose(
            List<Filter> orderedFilters,
            Runnable controller) {
        Runnable current = controller;

        for (int i = orderedFilters.size() - 1; i >= 0; i--) {
            Filter filter = orderedFilters.get(i);
            Runnable downstream = current;
            current = () -> filter.apply(downstream);
        }
        return current;
    }

    public static void main(String[] args) {
        System.out.println("=== ALLOWED ===");
        compose(
            List.of(
                trace("Entry"),
                trace("SecurityContext"),
                trace("Authentication"),
                trace("Authorization")
            ),
            () -> System.out.println("CONTROLLER")
        ).run();

        System.out.println("=== DENIED ===");
        compose(
            List.of(
                trace("Entry"),
                trace("SecurityContext"),
                trace("Authentication"),
                reject("Authorization")
            ),
            () -> System.out.println("CONTROLLER")
        ).run();
    }
}
~~~

Compile and run with Java 17:

~~~bash
javac FilterWalkthrough.java
java FilterWalkthrough
~~~

Stdout **exact per the plain Java logic**:

~~~text
=== ALLOWED ===
> Entry
> SecurityContext
> Authentication
> Authorization
CONTROLLER
< Authorization
< Authentication
< SecurityContext
< Entry
=== DENIED ===
> Entry
> SecurityContext
> Authentication
> Authorization
RESPONSE 403
< Authentication
< SecurityContext
< Entry
~~~

Lessons from stdout:

1. When every filter calls downstream, `CONTROLLER` executes before any `< ...` lines print.
2. When `reject("Authorization")` skips `next.run()`, `CONTROLLER` never executes; `< Authorization` also does not print because `reject` has no `finally`.
3. Upstream filters still unwind through the call stack and print `< Authentication`, `< SecurityContext`, and `< Entry`.
4. This program does not simulate JWT/CSRF/Spring MVC faithfully, has no real `FilterChainProxy`, and has no real `HttpServletRequest`/`Response`. It demonstrates solely **enter — short-circuit — unwind**.

## 19. Practice Exercises

**Exercise 1 — Verify where CSRF stops:** Enable Spring Security TRACE in the demo project and run `missingCsrfTokenStopsBeforeAuthorization`. Confirm `CsrfFilter` appears, the custom marker before authorization does not, and the Controller is not called. Contrast 403 here with a missing-role 403.

**Exercise 2 — Shift marker positions:** Replace `EntryTraceFilter`'s slot with `addFilterAfter(..., BasicAuthenticationFilter.class)` in a separate test branch. Observe why on a bad password that marker vanishes even though the request entered the security chain.

**Exercise 3 — Add form login:** Add `.formLogin(Customizer.withDefaults())` and verify anonymous `GET /me` redirects per the configured entry point. If keeping both Basic and form login, understand how `RequestMatcher` selects entry points rather than assuming every unauthenticated GET gets the same response.

**Exercise 4 — Place a custom filter on the container:** Use `FilterRegistrationBean` to create a trace outside Spring Security and compare it with `EntryTraceFilter`. For firewall-rejected requests, the container filter logs while the security checkpoint never runs.

**Exercise 5 — Multiple SecurityFilterChains:** Separate `/api/**` and a web fallback, attaching two checkpoints per chain. Verify `GET /api/private` and `GET /web/private` pass through only their respective chain's filters without mixing lists.

**Exercise 6 — Diagnose 404:** Try a URL with no Controller mapping while authenticated. Confirm the security trace ran yet `DispatcherServlet` found no handler. Contrast with `/login` when handled by a filter.

**Exercise 7 — Exceptions in a service:** Have a service throw `AccessDeniedException` or a business exception, then inspect responses/logs. Distinguish `ExceptionTranslationFilter`'s path from MVC exception handling.

**Exercise 8 — Request IDs:** Generate a per-request correlation ID, put it into MDC inside a trusted servlet filter, and remove it in `finally`. Verify two requests reusing the same thread do not inherit stale IDs; never log tokens/cookies.

## 20. Self-Check Questions

**Question 1.** Through which two components does a request travel from the Servlet container into Spring Security?

*Answer:* The container invokes `DelegatingFilterProxy`, the proxy delegates to the `FilterChainProxy` bean, and the proxy selects the matching `SecurityFilterChain`.

**Question 2.** Does `FilterChainProxy` run every `SecurityFilterChain` that matches a URL?

*Answer:* No. It picks the first matching chain in configured order; later chains are not combined.

**Question 3.** If a filter implements `doFilter` yet skips `chain.doFilter`, does the Controller run?

*Answer:* No, unless another independent call path exists. Within that Servlet `FilterChain`, downstream does not continue.

**Question 4.** Why do "after" logs print in reverse order compared to "before" logs?

*Answer:* Because `chain.doFilter` forms nested calls; as downstream returns, the call stack unwinds in reverse.

**Question 5.** Does `DEBUG DefaultSecurityFilterChain` at startup prove `BasicAuthenticationFilter` ran for the current request?

*Answer:* No; it only shows the filter is configured in the chain. Inspect per-request traces/matchers.

**Question 6.** Does `Invoking CsrfFilter` mean the CSRF token is valid?

*Answer:* Not yet. It only means the filter was invoked; check subsequent logs/results.

**Question 7.** Password is right yet `POST /notes` returns 403 before the Controller—which filter should you check?

*Answer:* Specifically check `CsrfFilter`, CSRF tokens, and HTTP method; 403 is not caused solely by roles.

**Question 8.** When an authenticated user lacks `ROLE_ADMIN`, who typically makes the access decision and who translates the exception?

*Answer:* `AuthorizationFilter` decides per rule; `ExceptionTranslationFilter` can handle `AccessDeniedException` via `AccessDeniedHandler`, typically returning 403.

**Question 9.** Does `SecurityContextHolderFilter` verify passwords itself?

*Answer:* No. It supplies context; authentication providers/filters verify credentials.

**Question 10.** Can a URL return 200 even if no Controller was called?

*Answer:* Yes. A filter can complete a response itself, or filter-handled endpoints like login/logout can respond.

**Question 11.** How do `permitAll` and matching no `SecurityFilterChain` differ?

*Answer:* `permitAll` still passes through the chain's security filters; matching no chain can bypass that entire protective layer.

**Question 12.** Why should you avoid printing `Authorization` headers when enabling debug logging?

*Answer:* Basic contains base64-encoded `username:password` (not encryption); Bearer contains reusable tokens.

**Question 13.** Does seeing `"04 after-authorization"` in logs prove the final status was 200?

*Answer:* No. An outer filter can catch an exception after that point and return 401/403.

**Question 14.** Why can one client request produce multiple filter log segments?

*Answer:* Servlets can perform `FORWARD`, `ERROR`, or `ASYNC` dispatches; login redirects also initiate new requests.

**Question 15.** Does `@WithMockUser` prove `BasicAuthenticationFilter` verified raw passwords?

*Answer:* No. It injects a pre-built test Authentication; testing passwords requires Basic headers or the real authentication flow.

**Question 16.** When an endpoint returns 404, how do you tell Security apart from MVC?

*Answer:* Check whether a security chain matched/completed, whether a controller mapping exists, whether the endpoint is filter-generated, and inspect response/error dispatches.

## 21. End-to-End Request Investigation Checklist

- [ ] Have request method, path, timestamp, and a credential-free correlation ID.
- [ ] Have gateway/proxy and container traces confirming the request reached the app.
- [ ] Verified `springSecurityFilterChain` is registered exactly once.
- [ ] Verified the right `SecurityFilterChain` matched without falling into an unintended fallback or no chain.
- [ ] Reviewed startup security filter lists and per-request traces when needed.
- [ ] Correctly distinguished `Invoking XFilter` from "XFilter allowed the request to proceed".
- [ ] Checked `HttpFirewall` for unusual paths/encodings before blaming controllers.
- [ ] Verified `SecurityContextHolderFilter`/repository and Authentication are present at the right stage.
- [ ] On 401, checked authentication mechanism, entry point, credentials, and safe provider error logs.
- [ ] On 403, distinguished CSRF, authorization, custom policies, and method security.
- [ ] On 302, verified redirects, request cache, form/OAuth2 entry points, and follow-up requests.
- [ ] On 404, checked Servlet mappings, MVC `HandlerMapping`, and filter-generated endpoints.
- [ ] On 500, distinguished filter, controller/service, serializer, and error-dispatch failures.
- [ ] Never treated `permitAll` as skipping security filters, nor 200 as sufficient proof of security.
- [ ] Used `try/finally` in tracing filters to observe unwind, without inferring final status from deep filters.
- [ ] Avoided double registration of custom filters between Servlet container and `HttpSecurity`.
- [ ] Checked dispatcher types, async completion, and request/session correlation when seeing repeated logs.
- [ ] Never used `ThreadLocal`/MDC without cleanup or propagation across thread switches.
- [ ] Never logged Authorization/Cookie/passwords/JWTs/OTPs/full Authentication/sensitive request bodies.
- [ ] Added integration tests covering valid requests, missing credentials, wrong passwords, missing roles, missing CSRF, and Controller called/not called.
- [ ] Enabled TRACE only in controlled environments/short windows with a clear downgrade procedure.
- [ ] Enforced owner/tenant/resource-level protections in services, not just URL roles.
- [ ] After fixes, re-tested negative paths and other chains to ensure no new gaps were introduced.

### Summary

To trace an HTTP request in Servlet Spring Security, follow three steps: **(1) verify whether the request entered the container and `FilterChainProxy`, (2) identify the selected chain and last filter actually invoked, and (3) verify whether the Controller/Service executed and which layer finalized the response**.

`chain.doFilter` creates both **inbound** and **unwind** paths; a filter can respond immediately and halt everything downstream. `FilterChainProxy` selects only the first matching chain; inside that chain, CSRF can block before authentication, authentication can stop before authorization, and authorization can prevent the Controller from running. Therefore, **a missing marker is not proof "the request never reached the backend"**: it may be proof the request was legitimately blocked at a security layer.

The most effective debugging question is not "what is wrong with the Controller?", but **"which checkpoint did the request reach, which filter decided not to call next, and which handler wrote the final status?"**

### Official Documentation

- [Spring Security — Servlet Architecture and Filters](https://docs.spring.io/spring-security/reference/servlet/architecture.html)
- [Spring Security — FilterChainProxy API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/FilterChainProxy.html)
- [Spring Security — SecurityFilterChain API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/SecurityFilterChain.html)
- [Spring Security — Java Configuration and Multiple Chains](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html)
- [Spring Security — SecurityContext Persistence](https://docs.spring.io/spring-security/reference/servlet/authentication/persistence.html)
- [Spring Security — Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)
- [Spring Security — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Form Login](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/form.html)
- [Spring Security — Spring MVC MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/)
- [Spring Framework — OncePerRequestFilter API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html)
- [Spring Boot 4.1.2 Release](https://spring.io/blog/2026/10/23/spring-boot-4-1-2-available-now/)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
