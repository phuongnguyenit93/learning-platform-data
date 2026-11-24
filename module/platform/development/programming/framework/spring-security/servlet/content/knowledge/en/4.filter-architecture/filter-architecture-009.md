# addFilterBefore, addFilterAfter, and addFilterAt: Choosing Extension Points in Spring Security Servlet

## 1. Problem: inserting a filter at the right place in the security chain

In a Spring Boot application using the **Servlet stack** (such as Spring MVC), an HTTP request traverses a chain of Servlet Filters before reaching a controller. Spring Security implements HTTP security via **SecurityFilterChain**, where filters perform tasks such as loading SecurityContext, handling CSRF, authentication, and authorization.

When custom processing is needed, Spring Security allows attaching a filter to the chain using three methods on **HttpSecurity**:

- **addFilterBefore(customFilter, AnchorFilter.class)**: places the new filter **before** the anchor filter's position.
- **addFilterAfter(customFilter, AnchorFilter.class)**: places the new filter **after** the anchor filter's position.
- **addFilterAt(customFilter, AnchorFilter.class)**: places the new filter at the **same order position** as the anchor filter. This **does not automatically replace** the anchor filter; if both are present, the ordering between them is not guaranteed.

This lesson guides you through choosing extension points, understanding the exact meaning of "before/after/at the same position", building two runnable sample filters, observing effects over HTTP, and avoiding common filter registration mistakes.

**Goals after this lesson:** you know when a filter is needed, can choose an appropriate anchor, distinguish the three methods, avoid accidentally running a filter twice, and know how to verify actual ordering via logs or HTTP tests.

## 2. Architecture map: Servlet filters vs. Spring Security filters

The basic participating layers:

~~~text
HTTP client
    |
    v
Servlet container filter chain
    |
    +-- (Other Servlet Filters of the application, if any)
    |
    +-- DelegatingFilterProxy: springSecurityFilterChain
            |
            v
        FilterChainProxy
            |
            +-- Selects first SecurityFilterChain matching request
                    |
                    +-- Spring Security filters in configured order
                    |
                    v
                DispatcherServlet -> Controller -> Service
~~~

- **DelegatingFilterProxy** connects the Servlet container to the Spring bean named **springSecurityFilterChain**.
- **FilterChainProxy** manages one or more **SecurityFilterChain**s, selecting the first chain whose matcher matches.
- **SecurityFilterChain** is an ordered set of filters that process matching requests.
- **HttpSecurity** is the builder used to define a chain. The addFilterBefore/addFilterAfter/addFilterAt methods insert the filter into the **chain being configured**, not automatically into every other chain.
- **OncePerRequestFilter** is a convenient base class when writing Spring Web filters. It helps avoid repeating filtering within a single dispatch via framework request-attribute tracking; behavior with ASYNC/ERROR dispatches must be understood separately.

Do not confuse **global Servlet Filters** with **filters belonging to a SecurityFilterChain**. A filter registered directly with the Servlet container can run in a different scope and order than filters inserted via HttpSecurity.

### Conceptual ordering example

When an application enables HTTP Basic, part of the chain can be pictured as follows:

~~~text
... SecurityContextHolderFilter ...
    |
    +-- BeforeBasicFilter              (added via addFilterBefore)
    |
    +-- BasicAuthenticationFilter      (HTTP Basic authentication)
    |
    +-- AfterBasicFilter               (added via addFilterAfter)
    |
    ... other filters ...
    |
    +-- AuthorizationFilter            (URL authorization decision)
    |
    v
Controller
~~~

This is an **illustrative snippet** for comparing before/after, not an exhaustive list of every filter or an immutable order across all versions/configurations. To confirm the real chain, check debug logs or inspect the running application's SecurityFilterChain.

## 3. Exact semantics of the three APIs

| API | Requested position | Use when | Keep in mind |
| --- | --- | --- | --- |
| **addFilterBefore(f, A.class)** | Filter f sits before the **order position** of A | You must read/adjust request info before a specific security step | If authentication result is not needed, it can go before the authentication filter |
| **addFilterAfter(f, A.class)** | Filter f sits after the **order position** of A | You need to observe state already processed by filter A, e.g., successful HTTP Basic result | If A ends the request early due to an error, f may not be invoked |
| **addFilterAt(f, A.class)** | f gets the **same registered order** as A | Intentionally designing a mechanism at the same position, typically a custom authentication filter | **Not a replace command**; if A still exists, both filters share one position with no guaranteed order between them |

Call syntax:

~~~java
http.addFilterBefore(myFilter, BasicAuthenticationFilter.class);
http.addFilterAfter(myFilter, BasicAuthenticationFilter.class);
http.addFilterAt(myFilter, BasicAuthenticationFilter.class);
~~~

The three lines above are **merely three alternatives illustrating the API**, not instructions to call all three for the same myFilter instance. When inserting, decide on one clear goal and use one meaningful position.

### What does "Anchor" mean?

**AnchorFilter.class** is the **filter class used as a positional reference** in the order table known to Spring Security. Spring Security determines order through registered filter classes and internal rules, rather than simply finding an object in a list and always inserting right next to it.

Common points of confusion:

1. **The anchor must have an order known to Spring Security.** Choosing an arbitrary filter class with no registered order can cause the application to fail when building SecurityFilterChain; not just any class implementing Filter can serve as an anchor.
2. **An anchor having a known position does not mean an anchor instance is necessarily present in the chain.** Using AnchorFilter.class does not automatically enable the corresponding feature. For instance, merely using UsernamePasswordAuthenticationFilter.class as an anchor does not enable form login.
3. **addFilterBefore/After guarantees relative order with respect to the anchor,** but does not guarantee other filters will always sit immediately adjacent with zero filters in between.
4. **Do not rely on how Spring Security orders filters sharing the same order.** If strict ordering between two custom filters is needed, use explicit before/after relationships.

In a project with multiple SecurityFilterChains, a filter added to a chain serves only that chain. A path not matching that chain will not see that chain's dedicated filter.

## 4. Choosing Before, After, or At based on requirements

**Choose addFilterBefore when preprocessing is needed before a specific step.**

For example: before **BasicAuthenticationFilter**, you want to attach a correlation ID to a request attribute, tag the request for tracing, or normalize some non-sensitive metadata. Choose before when your task **does not need** the Authentication created by BasicAuthenticationFilter.

Note: if another mechanism earlier than Basic already authenticated (session, another filter...), SecurityContext may already contain info. So "before Basic" does **not strictly** mean "the request is always unauthenticated".

**Choose addFilterAfter when data processed by the anchor step is needed.**

For example: immediately after **BasicAuthenticationFilter**, you want to record the minimal fact that the request now has a valid Authentication, then forward it. A filter after Basic can observe SecurityContext after Basic authenticates successfully. If Basic rejects bad credentials and terminates the response, a filter placed after it may not run.

Do not assume "after Basic" means "all authorization decisions are complete": **AuthorizationFilter** still runs at a later stage; a request lacking a role can still receive 403 after your filter ran.

**Choose addFilterAt when intentionally designing a filter at an already defined position.**

A fitting case typically involves implementing a custom authentication filter, where you clearly understand the old mechanism's position and how to disable/remove it from the chain if replacing the old flow. **addFilterAt does not automatically remove built-in filters.** Placing another filter at UsernamePasswordAuthenticationFilter's position while formLogin remains enabled can leave both filters active with undefined relative order.

Easy way to remember: **Before = before the anchor; After = after the anchor; At = same order rank as the anchor, not replacing the anchor.**

### Rules for choosing an extension point

- Need to attach **tracing/correlation IDs, lightweight infrastructure metadata**: choose a filter positioned before the step you want to observe; never log credentials or tokens.
- Need to know **whether Authentication was created by Basic**: choose after Basic, while also handling missing Authentication and early-rejected requests.
- Need to **authenticate using a standard protocol**: first check whether Spring Security already provides built-in mechanisms such as httpBasic, formLogin, oauth2ResourceServer, AuthenticationProvider, or AuthenticationConverter. Only add a custom filter when truly necessary.
- Need to check **which data a user is allowed to access**: use authorizeHttpRequests, method security, or service-layer checks; this is rarely sufficient reason to write a complex authorization filter yourself.
- Need to **replace an existing authentication mechanism**: explicitly configure which mechanism is enabled/disabled, how AuthenticationManager and failure/success are handled, and only then consider addFilterAt.

## 5. Complete example: inserting filters before and after HTTP Basic

We will build a Spring Boot application with two filters to prove positional behavior:

1. **BeforeBasicFilter** adds response header **X-Demo-Before-Basic: visited** before HTTP Basic is processed.
2. **AfterBasicFilter** reads SecurityContext right after HTTP Basic's position and sets header **X-Demo-After-Basic: authenticated** or **missing**. Do not expose usernames or tokens in headers.
3. **SecurityFilterChain** enables HTTP Basic, declares permissions for three endpoints, and adds the two filters via addFilterBefore/addFilterAfter.
4. An in-memory **UserDetailsService** provides two accounts to test 200/401/403 branches.

The example runs with **Java 17+**, **Spring Boot 3.3.13**, **Spring Security 6**, and Maven. This is a local learning environment with sample accounts; do not use hardcoded credentials in real deployments.

### 5.1. File structure

~~~text
filter-extension-demo/
├── pom.xml
└── src/main/java/com/example/filterdemo/
    ├── FilterDemoApplication.java
    ├── SecurityConfig.java
    ├── BeforeBasicFilter.java
    ├── AfterBasicFilter.java
    └── DemoController.java
~~~

### 5.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>filter-extension-demo</artifactId>
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

The Spring Boot parent manages compatible Spring Framework and Spring Security versions, so there is no need to declare a version manually for starter-security.

### 5.3. FilterDemoApplication.java

~~~java
package com.example.filterdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FilterDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(FilterDemoApplication.class, args);
    }
}
~~~

All classes sit in package com.example.filterdemo so Spring Boot automatically discovers SecurityConfig and DemoController.

### 5.4. BeforeBasicFilter.java

~~~java
package com.example.filterdemo;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public final class BeforeBasicFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        // Mark that the request passed through this filter before HTTP Basic's position.
        response.setHeader("X-Demo-Before-Basic", "visited");

        // Allow request to proceed to subsequent filters.
        chain.doFilter(request, response);
    }
}
~~~

**Explanation:**

- **OncePerRequestFilter** provides doFilterInternal to write logic in a single centralized place.
- **setHeader** is used solely as an observation marker in the example. It does not authenticate users or alter permissions.
- **chain.doFilter(...)** transfers control to the next filter. Omitting this line stops the request before reaching controllers and downstream security filters.
- Neither @Component nor @Bean is declared on the filter class in the example. The filter is instantiated directly in SecurityConfig to avoid Spring Boot registering it additionally in the Servlet container.

### 5.5. AfterBasicFilter.java

~~~java
package com.example.filterdemo;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

public final class AfterBasicFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        boolean authenticated =
                authentication != null && authentication.isAuthenticated();

        response.setHeader(
                "X-Demo-After-Basic",
                authenticated ? "authenticated" : "missing");

        chain.doFilter(request, response);
    }
}
~~~

**Explanation:**

- With valid HTTP Basic and the configuration below, **Authentication** has already been created at this position. The response header carries **authenticated**.
- With a request sending no credentials and having no Authentication yet, the header is **missing**. This still allows /public because the permitAll rule permits anonymous requests.
- After this filter, authorization steps still remain. A request carrying the authenticated header **can still receive 403** for lacking role ADMIN.
- If HTTP Basic rejects wrong credentials and terminates processing immediately, AfterBasicFilter **may not be invoked**. Do not rely on this header to determine all authentication outcomes.
- The header is illustrative only and does not prove permissions or security posture of a request. In a real application, you can replace it with properly designed metrics/auditing.

**Note on AnonymousAuthenticationToken:** At a position after Basic yet before AnonymousAuthenticationFilter, an unauthenticated request normally has no Authentication yet. At a position **after** the anonymous filter, Authentication may be anonymous with isAuthenticated() returning true. When needing to distinguish a real user, inspect the token type or use appropriate identity checks rather than relying solely on isAuthenticated().

### 5.6. SecurityConfig.java

~~~java
package com.example.filterdemo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/me").authenticated()
                .requestMatchers(HttpMethod.GET, "/admin").hasRole("ADMIN")
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults())
            .formLogin(AbstractHttpConfigurer::disable);

        // Added only via HttpSecurity: neither filter registers a separate Servlet Filter.
        http.addFilterBefore(new BeforeBasicFilter(),
                             BasicAuthenticationFilter.class);

        http.addFilterAfter(new AfterBasicFilter(),
                            BasicAuthenticationFilter.class);

        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        UserDetails admin = User.withUsername("admin")
            .password(encoder.encode("admin-pass"))
            .roles("ADMIN")
            .build();

        return new InMemoryUserDetailsManager(alice, admin);
    }
}
~~~

**Why is this configuration well suited to observing order?**

- **httpBasic(...)** adds the HTTP Basic mechanism, which includes **BasicAuthenticationFilter** used as our anchor.
- **addFilterBefore** places BeforeBasicFilter before BasicAuthenticationFilter's position.
- **addFilterAfter** places AfterBasicFilter after BasicAuthenticationFilter's position.
- **SessionCreationPolicy.STATELESS** avoids relying on sessions to remember Authentication across requests; each curl Basic command with or without credentials is easy to verify independently.
- **formLogin(disable)** disables the login form so unauthenticated /me gets challenged via HTTP Basic and responds 401 instead of redirecting to a login page.
- **authorizeHttpRequests** requires login for /me, ROLE_ADMIN for /admin, makes /public open, and denies other requests.
- **BCryptPasswordEncoder** hashes sample passwords for verification by the authentication mechanism. In production, store hashes persistently rather than hardcoding passwords.
- **CSRF** is not disabled. The example only uses GET, so no CSRF token is needed; when adding POST/PUT/DELETE, review CSRF policy according to the client model.

**Do not put @Component on BeforeBasicFilter or AfterBasicFilter.** If a filter is a Spring bean of type Filter, Spring Boot can auto-register it with the Servlet container. Simultaneously adding that same bean to SecurityFilterChain can cause it to run twice or in unintended positions.

### 5.7. DemoController.java

~~~java
package com.example.filterdemo;

import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/public")
    public String publicEndpoint() {
        return "public-ok";
    }

    @GetMapping("/me")
    public String profile(Authentication authentication) {
        return "user=" + authentication.getName();
    }

    @GetMapping("/admin")
    public String adminEndpoint() {
        return "admin-ok";
    }
}
~~~

The three endpoints clearly separate **public requests**, **requests requiring valid identity**, and **requests requiring role ADMIN**. Headers added by the two filters can still appear even when the controller does not run, because filters execute prior to the controller stage.

## 6. Running and self-verifying over HTTP

In the **filter-extension-demo** directory containing pom.xml:

~~~bash
mvn spring-boot:run
~~~

Use another terminal to run curl. If Windows PowerShell aliases curl, use **curl.exe** instead of curl; the arguments stay the same.

### Case A — Public GET, no credentials

~~~bash
curl -i http://localhost:8080/public
~~~

Expected key output:

~~~http
HTTP/1.1 200
X-Demo-Before-Basic: visited
X-Demo-After-Basic: missing

public-ok
~~~

This proves both filters were invoked, while no Authentication existed yet at AfterBasicFilter's position. The request is still allowed because GET /public is configured with permitAll.

### Case B — GET /me with valid credentials

~~~bash
curl -i -u alice:alice-pass http://localhost:8080/me
~~~

Expected key output:

~~~http
HTTP/1.1 200
X-Demo-Before-Basic: visited
X-Demo-After-Basic: authenticated

user=alice
~~~

BasicAuthenticationFilter authenticates alice successfully; AfterBasicFilter observes Authentication; the authenticated() rule accepts the request and the controller receives alice's identity.

### Case C — GET /me missing credentials

~~~bash
curl -i http://localhost:8080/me
~~~

Expected key output:

~~~http
HTTP/1.1 401
X-Demo-Before-Basic: visited
X-Demo-After-Basic: missing
WWW-Authenticate: Basic realm="Realm"
~~~

Other headers and WWW-Authenticate details depend on configuration. What to observe: the before filter ran, the after filter saw missing Authentication, and the authenticated() rule caused the system to require authentication.

### Case D — GET /me with wrong password

~~~bash
curl -i -u alice:wrong-pass http://localhost:8080/me
~~~

Key result: **401**. Before the request proceeds, HTTP Basic can handle the authentication error directly and end the response; therefore **X-Demo-After-Basic does not necessarily appear**. This is crucial evidence: addFilterAfter does not guarantee the post-anchor filter runs for every request, especially when the anchor rejects early.

### Case E — Valid login but insufficient permissions

~~~bash
curl -i -u alice:alice-pass http://localhost:8080/admin
~~~

Key output:

~~~http
HTTP/1.1 403
X-Demo-Before-Basic: visited
X-Demo-After-Basic: authenticated
~~~

AfterBasicFilter sees successful Authentication, yet **AuthorizationFilter** denies because alice only has ROLE_USER. A filter placed after Basic is **not** a filter positioned after all authorization.

### Case F — Valid Admin

~~~bash
curl -i -u admin:admin-pass http://localhost:8080/admin
~~~

Expected key output:

~~~http
HTTP/1.1 200
X-Demo-Before-Basic: visited
X-Demo-After-Basic: authenticated

admin-ok
~~~

Comparison table:

| Request | Expected status | X-Demo-Before-Basic | X-Demo-After-Basic | Meaning |
| --- | --- | --- | --- | --- |
| GET /public, no credentials | 200 | visited | missing | Both filters run; public URL |
| GET /me, alice valid password | 200 | visited | authenticated | HTTP Basic creates Authentication |
| GET /me, no credentials | 401 | visited | missing | Authentication required |
| GET /me, alice wrong password | 401 | visited | May be absent | Basic can halt the chain on error |
| GET /admin, alice valid password | 403 | visited | authenticated | Authentication succeeded, missing role |
| GET /admin, admin valid password | 200 | visited | authenticated | Sufficient permissions |

The table shows only key headers/statuses from the example. The HTTP server may also add Date, Cache-Control, X-Content-Type-Options, WWW-Authenticate, or other security headers. Do not compare raw responses byte-for-byte.

**Takeaway from the experiment:** before/after describe positions in the chain; they are **not** a promise that both run if an earlier filter stops the request, nor do they replace standard authentication/authorization steps.

## 7. addFilterAt: understanding "same position" and replacement limits

Suppose a system needs a custom login authentication filter named **CustomLoginAuthenticationFilter** and wants to place it at the position normally reserved for **UsernamePasswordAuthenticationFilter**.

The API call looks like:

~~~java
// Illustrates choosing position; not a standalone program.
// customLoginAuthenticationFilter must be fully implemented and configured.
http.addFilterAt(
    customLoginAuthenticationFilter,
    UsernamePasswordAuthenticationFilter.class);
~~~

**This snippet illustrates configuration once a customLoginAuthenticationFilter instance already exists**; it will not run without creating the filter, AuthenticationManager, and related handlers.

Essential points to understand:

1. **addFilterAt assigns the order position** of UsernamePasswordAuthenticationFilter to the new filter. It **does not remove** an existing UsernamePasswordAuthenticationFilter from the chain.
2. If formLogin is enabled and both the default filter and custom filter coexist at the same order, **you cannot rely on execution order between those two filters**. Login events may be handled by the unintended mechanism.
3. To replace a mechanism, you must **explicitly disable/omit the old mechanism** using supported configuration, then ensure the new filter properly handles success/failure flows, SecurityContext persistence, session strategy, and CSRF.
4. Custom filters need a clear justification. If the goal is merely verifying passwords, converting credentials, or granting authorities, **AuthenticationProvider**, **AuthenticationConverter**, or built-in Spring Security configuration is often a better extension point.
5. If the goal is standard JWT/OAuth2 bearer tokens, prefer **oauth2ResourceServer** with official extension points before writing a filter reading the Authorization header from scratch.
6. Do not use addFilterAt as a "trick" to fix wrong filter ordering. When you only need tracing, timing, or reading context, **addFilterBefore/addFilterAfter** expresses intent more clearly and is easier to test.

### A dangerous misconception

Wrong assumption: "Calling addFilterAt(CustomFilter, BasicAuthenticationFilter.class) replaces BasicAuthenticationFilter".

**Reality:** both can coexist at an equivalent order. Relative order between them is not guaranteed. If CustomFilter breaks the chain, Basic may not run; if Basic goes first, CustomFilter may not receive the expected scenario. Never use this approach to force an old mechanism to disappear.

If the application only needs to customize how Basic authenticates, look into configuring **AuthenticationProvider/UserDetailsService/PasswordEncoder** and supported handlers first.

## 8. Avoiding double filter registration

With Spring Boot, the following code risks running the filter **outside** SecurityFilterChain if you also insert it via HttpSecurity:

~~~java
@Component
public class MyFilter extends OncePerRequestFilter {
    // ...
}
~~~

Cause: **@Component** makes MyFilter a bean of type Filter. Spring Boot can auto-register it with the Servlet container, while **http.addFilterBefore(myFilter, ...)** registers the instance in the security chain. The result can be two execution paths or effects outside matcher scope; OncePerRequestFilter is not a guarantee that you are always at the right position when double-registered.

### Safest approach for small examples

Instantiate the filter directly inside SecurityFilterChain:

~~~java
http.addFilterBefore(
    new BeforeBasicFilter(),
    BasicAuthenticationFilter.class);
~~~

Do not attach @Component or @Bean to that filter class. This is what the runnable example in section 5 does.

### When dependency injection is genuinely required

If the custom filter must be managed as a Spring bean because it needs another service, you can register a **FilterRegistrationBean** to disable automatic Servlet registration while still attaching the filter in SecurityFilterChain:

~~~java
@Bean
FilterRegistrationBean<MyFilter> disableServletRegistration(MyFilter filter) {
    FilterRegistrationBean<MyFilter> registration =
        new FilterRegistrationBean<>(filter);
    registration.setEnabled(false);
    return registration;
}
~~~

The snippet **only illustrates the registration technique** and is not standalone compilable without the MyFilter class and proper imports. When applying it, import org.springframework.boot.web.servlet.FilterRegistrationBean, define the MyFilter bean, and add that exact instance to the chain via HttpSecurity. Do not create an extra unnecessary instance.

Another simple option is injecting the service into the **@Bean SecurityFilterChain** method and instantiating new CustomFilter(service) directly without exposing the filter as a separate bean. The goal is having one clear place controlling where the filter runs.

## 9. Interaction with multiple SecurityFilterChains

An application can have two policies:

- `/api/**` endpoints use HTTP Basic or bearer tokens and are stateless.
- Remaining web pages use sessions/form login.

In that case, each **SecurityFilterChain** has its own matcher and order. **addFilterBefore/After/At** affects only the chain on which it is called. If both chains need a shared filter, you must explicitly attach it to each appropriate chain; do not assume one attachment covers every URL.

With multiple chains, Spring Security picks the **first matching chain** for the request. If a request matches no chain and there is no fallback, it may not be protected by those Security chain filters. Design matchers clearly and test sensitive URLs.

Do not use a global Servlet container filter to "patch" a security chain with a broken matcher, because scope, ordering, and exception/security context mechanics differ.

## 10. Mistakes about ordering and security semantics

### Mistake 1 — Reading Authentication too early

Placing a filter before Basic and expecting getAuthentication() to always return the current HTTP Basic user is incorrect. Credentials have not yet been processed by Basic at that position.

**Fix:** place it after the corresponding authentication filter, or use official listeners/handlers if authentication success/failure signals are needed.

### Mistake 2 — Placing a filter too late to modify the request

If the goal is adding info needed by the authentication step, putting the filter after that step will not reprocess the request that already passed. Conversely, putting a filter too early and expecting Authentication that does not exist yet is also wrong.

**Fix:** pinpoint the exact data the filter needs to read and which filter produces that data, then choose before/after the corresponding anchor.

### Mistake 3 — Trusting addFilterAt to overwrite

addFilterAt does not replace an existing instance. If two filters share a position, order is not guaranteed.

**Fix:** actively configure the old mechanism and consider official extension hooks; only share a position when you thoroughly understand the entire chain.

### Mistake 4 — Picking a filter class with no registered order

Picking an arbitrary Filter class as an anchor unrecognized by Spring Security can prevent HttpSecurity from determining order.

**Fix:** use an anchor class from the standard ordered filter list or establish order through supported mechanisms; verify the chain at startup.

### Mistake 5 — Forgetting chain.doFilter or calling it twice

When a filter only observes requests, **chain.doFilter(...) normally must be called exactly once**. Omitting it halts the whole chain; calling it twice can produce unintended side effects.

**Fix:** clearly decide whether the filter observes or intentionally rejects requests. If rejecting, design consistent status/body and exception handling. Do not block arbitrarily mid-pipeline.

### Mistake 6 — Confusing security filters with global Servlet filters

Putting @Component on a filter and also adding it via HttpSecurity can create multiple registration paths. A global filter can also execute on paths not matching a security chain.

**Fix:** manage filter lifecycle and position explicitly; for filters serving only Spring Security, keep them inside the chain.

### Mistake 7 — Logging secrets while "debugging"

Filters placed near authentication easily see passwords, Authorization headers, cookies, and sensitive tokens.

**Fix:** log only minimal info such as request ID, method, sanitized path, and appropriate outcome; mask or omit credentials. Never echo principals/tokens in response headers in production.

### Mistake 8 — Assuming OncePerRequestFilter always runs once across the entire HTTP lifecycle

A single request can experience REQUEST, ASYNC, or ERROR dispatches. OncePerRequestFilter behavior depends on the dispatch and shouldNotFilterAsyncDispatch/shouldNotFilterErrorDispatch methods. Never use "runs once across all execution paths" as a security assumption.

**Fix:** identify supported dispatch types and test async/error cases if your application uses them.

## 11. Diagnosing when a custom filter does not run or runs at the wrong time

Follow these steps in order:

1. **Is SecurityConfig scanned by Spring?** Verify package, @Configuration, @Bean SecurityFilterChain, and application startup.
2. **Does the request match the SecurityFilterChain containing the filter?** Inspect securityMatcher, chain order, and actual request path.
3. **Which class was chosen as the anchor?** Check whether the anchor class has an order recognized by Spring Security, and whether the anchor filter is actually enabled in the chain.
4. **Where was the filter registered?** Check for @Component/@Bean, FilterRegistrationBean, or duplicate Servlet container registrations.
5. **Did an earlier filter reject the request?** If HTTP Basic handles bad credentials and returns 401, filters after it will not necessarily run.
6. **Is there shouldNotFilter logic?** If present, verify skip conditions match the intended URL/method/dispatch.
7. **Are you observing the right stage?** "After Basic" may still be "before authorization"; 200/401/403 must be interpreted relative to downstream filters.
8. **Has the response already committed?** If custom filter code writes the body or flushes too early, downstream filters/handlers may no longer be able to modify HTTP status/headers.

In development, you can temporarily enable DEBUG for org.springframework.security to see chains and authorization decisions. Never log Authorization headers, passwords, or session tokens.

## 12. Self-practice exercises

### Exercise A — Change position, observe the difference

Change AfterBasicFilter's position from:

~~~java
http.addFilterAfter(new AfterBasicFilter(),
                    BasicAuthenticationFilter.class);
~~~

to:

~~~java
http.addFilterBefore(new AfterBasicFilter(),
                     BasicAuthenticationFilter.class);
~~~

Re-run GET /me with Basic credentials. Observe X-Demo-After-Basic and explain why it can switch from authenticated to missing in a stateless configuration on a fresh request.

**Explanation:** placing it before Basic makes the filter read SecurityContext before HTTP Basic authenticates the request's credentials. Being stateless with no Authentication from an earlier filter, the result at that position is missing. The class name AfterBasicFilter is merely illustrative and does not control placement.

### Exercise B — Why does 403 still have the authenticated header?

Call GET /admin as alice. Why is the HTTP status 403 while X-Demo-After-Basic is authenticated?

**Explanation:** Basic authenticates identity successfully; downstream AuthorizationFilter denies due to missing ROLE_ADMIN. Authentication and authorization are two separate decisions.

### Exercise C — Reading logs on wrong password

Call GET /me with alice and a wrong password. Explain why BeforeBasicFilter can run while AfterBasicFilter does not.

**Explanation:** BasicAuthenticationFilter can handle AuthenticationException and invoke AuthenticationEntryPoint directly to return 401 without passing control further down the chain.

### Exercise D — Evaluating an addFilterAt proposal

A colleague adds CustomLoginAuthenticationFilter using addFilterAt(..., UsernamePasswordAuthenticationFilter.class) while leaving formLogin enabled. List at least three questions that must be answered before adopting it.

**Suggested answer:** Are two filters sitting at the same order? Which mechanism handles the login request and success/failure? Could processing/output be non-deterministic due to sharing a position? Should AuthenticationProvider/AuthenticationConverter be used instead? Have SecurityContext saving and CSRF/session been designed?

### Exercise E — Try adding a POST

Add a state-changing POST endpoint, use valid HTTP Basic credentials without sending a CSRF token. You may receive 403 even though GET /me succeeded earlier. Explain which protection layer is responsible and why CSRF should not be disabled reflexively.

**Suggested answer:** CSRF is a protection layer independent of authentication/roles; risk depends on how clients automatically send credentials, especially cookies/sessions in browsers. Configure CSRF appropriately for your threat model.

## 13. Checklist before bringing a custom filter into a real application

- Clearly identified what task the filter solves and whether a new filter is genuinely necessary.
- Chose before/after/at due to a **concrete technical dependency** on the anchor filter.
- Anchor has a valid order; verified the filter chain is actually built and requests match that chain.
- Did not treat addFilterAt as a replace operation; did not unintentionally keep two authentication mechanisms at the same position.
- Did not double-register the filter between the Servlet container and SecurityFilterChain.
- For observational filters, called chain.doFilter exactly once; for blocking filters, designed clear outcomes and exception handling.
- Did not assume Authentication always exists before an authentication filter or that every request reaches filters downstream of a step that can reject early.
- Tested 200/401/403, allowed/denied paths, wrong passwords, and multi-security-chain scope if applicable.
- Did not log credentials, tokens, or sensitive cookies; did not reflect sensitive user info in response headers.
- Accounted for dispatcher types, async/error, CSRF, CORS, and SecurityContext lifecycle in the real application context.

**Key takeaway:** **addFilterBefore** fits when processing must happen *before* an anchor, **addFilterAfter** when it must run *after* the anchor, and **addFilterAt** when intentionally sharing the *same order* as the anchor. Filter position determines when security data becomes available, yet does not replace configuring authentication, authorization, and HTTP protections with Spring Security's proper mechanisms.
