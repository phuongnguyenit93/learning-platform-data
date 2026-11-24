# SecurityFilterChain: Matching Conditions and Filter Lists in Spring Security Servlet

## Lesson Objectives

After this lesson, you will be able to explain what a **SecurityFilterChain** is, which chain is selected for a given request, the difference between **chain selection conditions** and **authorization conditions**, how to observe the actual filter list, and configuration mistakes that leave endpoints unprotected by Spring Security contrary to your intent.

The context is a **Spring MVC/Servlet application with Spring Security 6 and Spring Boot 3.x**, using Java 17 or higher. Key classes include DelegatingFilterProxy, FilterChainProxy, SecurityFilterChain, DefaultSecurityFilterChain, HttpSecurity, RequestMatcher, and security filters.

## 1. Why is SecurityFilterChain needed?

Servlet containers (such as Tomcat) process HTTP requests through Servlet Filters before reaching DispatcherServlet/controllers. Spring Security also protects requests with filters, but security filters are grouped and coordinated through **FilterChainProxy**.

You can picture the flow:

~~~text
HTTP request
    |
Servlet container filter chain
    |
DelegatingFilterProxy ("springSecurityFilterChain")
    |
FilterChainProxy
    |
    +-- finds the FIRST SecurityFilterChain with matches(request) == true
    |       |
    |       +-- runs the security filters of the SELECTED CHAIN, in order
    |               |
    |               +-- authentication, SecurityContext management, CSRF, authorization...
    |                       |
    +-----------------------+--> continues servlet filter chain --> DispatcherServlet
                                                            --> Controller
~~~

Key takeaways:

- **DelegatingFilterProxy** is the bridge from a Servlet-container-managed filter to a Spring bean usually named springSecurityFilterChain.
- That bean is normally **FilterChainProxy**, which manages a list of SecurityFilterChains, each having its own **RequestMatcher** and an **ordered list of Filters**.
- A SecurityFilterChain expresses "which requests enter here?" along with "which filters apply to those requests?". DefaultSecurityFilterChain is the standard implementation.
- Each request goes through the **first matching chain** in priority order, without automatically combining filters from multiple chains.
- If **no chain matches**, FilterChainProxy does not apply Spring Security's security filters to that request. Other security filters at the Servlet container layer may still exist, but you have left an area outside the control of Spring Security's SecurityFilterChains.
- A filter being in the list does not guarantee it takes action on every request: for instance, CsrfFilter usually does not require a token for GET, and a Basic authentication filter may let requests without an Authorization header pass through for the authorization mechanism to decide.

This explains why you must understand **chain scope**, **chain ordering**, and **filter ordering inside each chain**.

## 2. Matching conditions: how is a SecurityFilterChain selected?

### 2.1. RequestMatcher for the entire chain

When creating a SecurityFilterChain bean from HttpSecurity, you can restrict the chain's scope using **securityMatcher(...)**:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
~~~

This is an **illustrative configuration snippet placed inside a @Configuration class** with the corresponding Spring Security imports; a full program example appears later. The securityMatcher("/api/**") condition selects the chain when the application's path matcher determines the request belongs to /api/**. Requests outside this scope **do not pass through the filters of the API chain**.

If securityMatcher is not called, HttpSecurity creates a chain accepting **all requests** by default. With multiple chains, ordering must be specified so specific chains are evaluated before general ones.

A RequestMatcher can also inspect the HTTP method or properties of HttpServletRequest, depending on its implementation. When using string patterns in Spring Security 6, the actual matcher may depend on Spring MVC, implementation details, and application configuration. Therefore, test against real URLs, servlet mappings, and context paths, especially with multiple Servlets or complex path structures.

### 2.2. First-match wins and @Order

Suppose there are two beans:

~~~text
@Order(1): securityMatcher("/api/**") -> HTTP Basic API
@Order(2): default matcher for all requests -> Form Login website
~~~

Selection rules:

| Request | Selected chain | Explanation |
| --- | --- | --- |
| GET /api/status | API, order 1 | Matches /api/** first |
| POST /api/orders | API, order 1 | Still API regardless of method |
| GET /dashboard | Web, order 2 | Does not match API chain, matches fallback |
| GET /public/ping | Web, order 2 | Can be permitAll inside Web chain |
| GET /not-found | Web, order 2 | Still passes through Spring Security; controller may return 404 afterward |

**Lower @Order values have higher priority**. If a chain matching all requests is placed before the API chain, the general chain will capture every request and the API chain may never be selected. If only an /api/** chain is declared without a fallback covering other URLs, URLs outside /api/** can slip past Spring Security's security filters.

Do not rely on arbitrary bean ordering as a security contract. Specify @Order explicitly when there are multiple chains, and include a final chain aligned with the default policy (typically requiring authentication, rather than accidentally bypassing requests).

### 2.3. securityMatcher vs. requestMatchers in authorizeHttpRequests

These are two separate decision layers:

| Configuration | Question it answers | Effect |
| --- | --- | --- |
| http.securityMatcher("/api/**") | Should the request **enter this SecurityFilterChain**? | Selects the entire filter list |
| authorizeHttpRequests(auth -> auth.requestMatchers(...).hasRole(...)) | Once the request **has entered the chain**, does the caller have sufficient permissions? | Authorization rule |
| authorizeHttpRequests(auth -> auth.anyRequest().denyAll()) | How should requests already in the chain that did not match earlier rules be handled? | Denies access within the current chain |

Example:

~~~java
http
    .securityMatcher("/api/**")
    .authorizeHttpRequests(auth -> auth
        .requestMatchers(HttpMethod.GET, "/api/reports/**")
            .hasAuthority("SCOPE_reports.read")
        .anyRequest().denyAll());
~~~

This is a **configuration fragment**, not a standalone runnable program. GET /api/reports/42 is evaluated against the scope rule; POST /api/reports/42 **still enters the API chain** but is rejected by denyAll. GET /dashboard does not enter this chain even though authorization has anyRequest. Do not assume requestMatchers inside authorizeHttpRequests creates or narrows the SecurityFilterChain itself.

Within a chain, authorizeHttpRequests requestMatchers rules are evaluated in declaration order; put specific rules before broad ones and put anyRequest last. Avoid confusing "a request does not match a specific authorization rule" with "a request does not match the chain".

### 2.4. permitAll still passes through the chain

When using:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/public/**").permitAll()
    .anyRequest().authenticated())
~~~

GET /public/ping **still passes through the filters of the selected chain**, even though AuthorizationFilter allows it to proceed. Security headers, context management mechanisms, and other filters can still take effect. An invalid Authorization header can even be rejected by an authentication filter before reaching the permitAll rule, depending on the enabled authentication mechanisms.

Conversely, using WebSecurityCustomizer.ignoring() causes requests to bypass the Spring Security filter chain, potentially skipping necessary security/hardening filters. For ordinary public endpoints, **permitAll** is usually more appropriate; only ignore the entire chain when there is a genuine architectural reason.

## 3. List of filters inside each chain

A chain has no "fixed standard filter list" across every project. Spring Security assembles the list and order based on the features you enable: formLogin, httpBasic, oauth2ResourceServer, csrf, logout, sessionManagement, exceptionHandling, authorizeHttpRequests, and custom filters.

Some filters commonly found in Spring Security Servlet:

| Filter | Primary role |
| --- | --- |
| DisableEncodeUrlFilter | Restricts writing session IDs into URLs via URL encoding; may be present in modern configurations |
| WebAsyncManagerIntegrationFilter | Integrates SecurityContext with Spring MVC asynchronous processing |
| SecurityContextHolderFilter | Loads SecurityContext for the processing scope and clears it after the request in the modern mechanism; other configurations/versions may use SecurityContextPersistenceFilter |
| HeaderWriterFilter | Writes configured security HTTP response headers |
| CsrfFilter | Validates CSRF tokens for protected requests |
| LogoutFilter | Handles configured logout requests, typically before form authentication filters |
| UsernamePasswordAuthenticationFilter | Processes login POST requests for formLogin |
| BasicAuthenticationFilter | Processes Authorization: Basic ... when httpBasic is enabled |
| BearerTokenAuthenticationFilter | Processes Authorization: Bearer ... when using OAuth2 Resource Server |
| RequestCacheAwareFilter | Integrates request caching, such as saving the pre-login request before redirecting to login |
| SecurityContextHolderAwareRequestFilter | Wraps the Servlet request so Servlet APIs are aware of authentication/security |
| AnonymousAuthenticationFilter | Creates an anonymous representation when the request does not yet have an appropriate Authentication |
| ExceptionTranslationFilter | Translates AuthenticationException/AccessDeniedException into an authentication entry point or access-denied handling |
| AuthorizationFilter | Checks access permissions according to AuthorizationManager and authorizeHttpRequests rules |

Filters are registered in an internal order defined by Spring Security; **do not treat the order in this table as exact proof for your application**. In particular, do not assume every chain contains every filter in the table: a chain enabling only formLogin may lack BasicAuthenticationFilter, a Basic-only chain usually lacks UsernamePasswordAuthenticationFilter, and BearerTokenAuthenticationFilter requires Resource Server configuration.

### 3.1. Distinguishing commonly confused steps

**SecurityContextHolderFilter** primarily brings an existing context into scope for processing and cleans it up on time; it does not authenticate username/password itself. **Authentication filters** such as BasicAuthenticationFilter or UsernamePasswordAuthenticationFilter create an Authentication when matching credentials are present and authenticate successfully. **AnonymousAuthenticationFilter** can supply an anonymous Authentication representation if not yet authenticated. **AuthorizationFilter** evaluates authorization rules; then **ExceptionTranslationFilter** assists in returning 401, login redirect, or 403 via the entry point and access-denied handler.

With form login, the login filter may immediately return a redirect once authentication completes, without the login request necessarily continuing to a controller. For requests blocked by CSRF or authorization, the controller may also not run. Filters can redirect, return errors, or terminate the chain; thus "being in the filter list" does not guarantee all filters and the controller finish executing on every request.

### 3.2. Two different kinds of ordering

- **SecurityFilterChain order**: which chain FilterChainProxy evaluates first, usually determined by @Order on the bean.
- **Filter order inside a chain**: Spring Security arranges filters at fixed positions/relationships or via addFilterBefore, addFilterAfter, addFilterAt.

You cannot fix wrong chain selection by moving a filter inside a chain that is never selected. Nor can you fix filter-before/after order by changing @Order on a chain bean that was already selected properly.

## 4. Runnable example: API using HTTP Basic, website using form login

The following example has two SecurityFilterChains to observe the difference between **chain matching** and **activated filters**. Spring Boot 3.x, Java 17+, requiring spring-boot-starter-web and spring-boot-starter-security. The sample API only uses GET to focus on matching/authentication; **CSRF is not disabled**. For APIs with write operations, CSRF must be evaluated based on credentials that browsers may send automatically (HTTP Basic can be cached by browsers); do not disable CSRF merely because the URL starts with /api/.

Directory structure in a typical Spring Boot project:

~~~text
src/main/java/dev/example/chain/
    ChainDemoApplication.java
    ChainSecurityConfig.java
    DemoController.java
~~~

### 4.1. Spring Boot application

File src/main/java/dev/example/chain/ChainDemoApplication.java:

~~~java
package dev.example.chain;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ChainDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ChainDemoApplication.class, args);
    }
}
~~~

### 4.2. Two chains, one demo user

File src/main/java/dev/example/chain/ChainSecurityConfig.java:

~~~java
package dev.example.chain;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class ChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
                .securityMatcher("/api/**")
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/status")
                            .hasRole("USER")
                        .anyRequest().denyAll())
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .httpBasic(withDefaults())
                .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webChain(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/public/**").permitAll()
                        .anyRequest().authenticated())
                .formLogin(form -> form.permitAll())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("demo")
                        .password(encoder.encode("local-demo-password"))
                        .roles("USER")
                        .build());
    }
}
~~~

Explanation of each decision:

1. apiChain has @Order(1), is evaluated first, and accepts only /api/** paths.
2. The API gets BasicAuthenticationFilter via httpBasic. SessionCreationPolicy.STATELESS instructs Spring Security not to use HttpSession to load/save SecurityContext for the API chain. The API only allows GET /api/status if the user has role USER; other API requests hit denyAll.
3. webChain has @Order(2) and sets no securityMatcher, making it the **fallback matching all remaining requests**. This chain enables form login and keeps default session handling, without automatically inheriting BasicAuthenticationFilter just because the API chain uses Basic.
4. /public/** is permitAll **inside the fallback**, still subject to the web chain's filters. All remaining URLs require login.
5. UserDetailsService and PasswordEncoder use local demo data. The sample password is encoded with the encoder before in-memory storage; do not use these credentials outside a learning environment.
6. There is no csrf.disable() call. If you add POST/PUT/DELETE APIs with HTTP Basic, requests may be rejected by CsrfFilter when missing a token; this is intentional behavior that must be evaluated separately.

Even though both chains may share the same UserDetailsService, they **do not share a default filter list**. An /api/status request is handled by the API chain; a /dashboard request is handled by the web chain.

### 4.3. Controller to observe results

File src/main/java/dev/example/chain/DemoController.java:

~~~java
package dev.example.chain;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {

    @GetMapping("/api/status")
    public String apiStatus() {
        return "API OK";
    }

    @GetMapping("/dashboard")
    public String dashboard() {
        return "WEB OK";
    }

    @GetMapping("/public/ping")
    public String publicPing() {
        return "PUBLIC OK";
    }
}
~~~

In a Spring Boot project with the two starters above, run the application with the project wrapper, for example:

~~~bash
./gradlew bootRun
~~~

If the project uses Maven, run with Maven accordingly. You cannot just run javac on individual files because the code depends on Spring Boot/Spring Security libraries; the Java files in the example are written to compile **inside a project with the proper dependencies**.

### 4.4. Test requests and expected results

When running locally on http://localhost:8080, use a terminal:

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/status
curl -s -u demo:local-demo-password http://localhost:8080/api/status
curl -i http://localhost:8080/dashboard
curl -i -u demo:local-demo-password http://localhost:8080/api/unknown
~~~

Expected table for a fresh test session with no prior login cookies:

| Command/request | Chain | Expected result |
| --- | --- | --- |
| GET /public/ping | Web fallback | HTTP 200, body PUBLIC OK |
| GET /api/status, no Basic | API | HTTP 401, usually with WWW-Authenticate: Basic ... |
| GET /api/status, valid Basic | API | HTTP 200, body API OK |
| GET /dashboard, no session | Web fallback | Typically HTTP 302 redirecting to the login page |
| GET /api/unknown, valid Basic | API | HTTP 403 due to anyRequest().denyAll(), does not reach controller |

With the third command, the stdout body from curl -s is the exact string **API OK** (the controller does not append a newline). Exact headers, status, or redirect results may vary if the project has different configuration, a proxy, or additional filters.

**Note:** HTTP on localhost is only for learning on a personal machine; on real networks use HTTPS, do not send passwords over HTTP, and avoid exposing passwords in shell history. In a browser, try form login at /dashboard and inspect cookies/sessions via DevTools, but do not copy real JSESSIONID values into reports. A web chain session cookie does not automatically grant access to an API chain configured with STATELESS and Basic.

## 5. How to inspect the actual filter list

What you want to verify is: **which matcher does each chain have, and which filters are in what order?** Do not infer the list from bean names or from reading documentation examples.

### 5.1. Logs in a development environment

You can enable logging for Spring Security in dev's application.yml:

~~~yaml
logging:
  level:
    org.springframework.security: DEBUG
    org.springframework.security.web.FilterChainProxy: TRACE
~~~

On startup and when sending requests, logs typically report the created security chains/filters and filter execution. Message details and log levels depend on the Spring Security version; do not rely on a fixed log message string for operational rules. Only enable TRACE when debugging, then lower the log level afterward. Filter/request logs can contain paths, context, or sensitive information; always control log access and never print Authorization headers, session IDs, tokens, or passwords.

In SecurityFilterChain, filters will differ between the two chains in the example. For instance, the API chain may have BasicAuthenticationFilter while the web chain has UsernamePasswordAuthenticationFilter. Common filters like HeaderWriterFilter or AuthorizationFilter may appear in both. The exact order must be read from the logs/chains of the running application.

### 5.2. Inspecting component configuration

FilterChainProxy exposes SecurityFilterChains via getFilterChains(); each chain reports its matcher and registered filters. This is a suitable approach when verifying via tests or diagnostic tools. Do not confuse the list of **Filters inside a SecurityFilterChain** with all Servlet Filters registered by the container outside FilterChainProxy.

When analyzing logs, correlate three facts: (1) which path/method was evaluated for the request, (2) which chain matcher was selected first, and (3) which filter executed or rejected before the controller. Reading only the filter list while ignoring the matcher can cause you to debug the wrong chain.

## 6. Inserting a custom filter into the right chain

If you need to add a filter to measure processing time, attach a correlation ID, or inspect technical data, decide **which requests that filter needs to run for** first. Place it in apiChain if it only applies to /api/**; do not register it globally in the Servlet container when the requirement is API-only.

Example Spring Servlet filter class for timing, file src/main/java/dev/example/chain/ApiTimingFilter.java:

~~~java
package dev.example.chain;

import java.io.IOException;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

public class ApiTimingFilter extends OncePerRequestFilter {

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {
        long start = System.nanoTime();
        try {
            chain.doFilter(request, response);
        } finally {
            long elapsedMs = (System.nanoTime() - start) / 1_000_000;
            System.out.println(
                    "API " + request.getMethod()
                    + " status=" + response.getStatus()
                    + " durationMs=" + elapsedMs);
        }
    }
}
~~~

To add it to the apiChain example above, import BasicAuthenticationFilter:

~~~java
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;
~~~

and in the apiChain configuration fluent chain, add the following call **before build()**:

~~~java
.addFilterBefore(new ApiTimingFilter(), BasicAuthenticationFilter.class)
~~~

The last two snippets are **additions to ChainSecurityConfig**, not standalone runnable classes. Spring Security places the custom filter before the API chain's BasicAuthenticationFilter according to internal ordering rules. Since apiChain's matcher is /api/**, the timing filter will not be executed by this chain for /dashboard.

The example uses System.out for illustration; real systems should use a structured logger, restrict what gets logged, and never log secrets/tokens. If you make ApiTimingFilter a Servlet Filter bean via @Component or @Bean while also inserting it into SecurityFilterChain, Spring Boot may auto-register the filter at the Servlet container layer, causing it to run additionally outside Spring Security or multiple times. When DI bean injection is needed, explicitly disable servlet registration for that filter bean (for example via FilterRegistrationBean with setEnabled(false)), then register it in the appropriate security chain.

**addFilterBefore/addFilterAfter** specify relative filter placement. **addFilterAt** does not necessarily replace an existing filter at the same position; read the API semantics and verify the actual list. Every custom filter must call chain.doFilter(request, response) if the request is meant to continue; it may deliberately block, but only with explicit rules.

## 7. Failure modes to recognize

### 7.1. Broad chain placed before specific chain

~~~java
@Order(1) // Unintended if this chain matches every request
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .formLogin(form -> form.permitAll())
            .build();
}
~~~

If the chain above precedes an /api/** chain, FilterChainProxy will select webChain even for /api/status. The HTTP Basic filter present only in the API chain will not process credentials as expected. Fix this with proper @Order ordering: specialized API chain first, fallback chain last.

### 7.2. Missing fallback

~~~java
@Bean
SecurityFilterChain onlyApi(HttpSecurity http) throws Exception {
    return http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth.anyRequest().authenticated())
            .httpBasic(withDefaults())
            .build();
}
~~~

When declaring a custom SecurityFilterChain, do not assume Boot still automatically adds a default chain protecting all URLs. In the example with only the API chain, /dashboard and /admin do not match it and thus risk **not being protected by Spring Security**. Create an intentional fallback and verify endpoints outside /api/**.

### 7.3. Assuming permitAll skips all filters

Permitting /public/** does not mean all filter checks are skipped. A filter positioned before AuthorizationFilter can still act on or reject the request. Inspect logs and the filter chain to understand why a public endpoint receives 401/403.

### 7.4. Taking a filter class name as proof that a feature is enabled

The presence of FilterChainProxy or SecurityFilterChain in an application does not prove Bearer, Basic, or form login is active. Inspect the HttpSecurity configuration and generated filter list. For instance, using requestMatchers("/api/**") inside authorizeHttpRequests does not create BasicAuthenticationFilter on its own.

### 7.5. Filter running twice

A filter that is both registered by the servlet container and added via addFilterBefore to SecurityFilterChain can run unexpectedly. Verify registration scopes, servlet FilterRegistrationBeans, and the Spring Security filter list. With OncePerRequestFilter, "once per request dispatch" logic is no excuse for registering the same filter in two places.

### 7.6. Paths, Servlet mappings, and dispatcher types differing from expectations

Do not merely look at the URL shown in the browser and assume every RequestMatcher will certainly match. Context path, servletPath, how MVC matchers are chosen, reverse proxies, and ERROR/FORWARD/ASYNC dispatcher types can all affect request routing. When using multiple Servlets or custom RequestMatchers, write tests for real paths, methods, and edge cases like /api, /api/, /api/v1/... if they matter for security.

### 7.7. Unexpected 401, 403, or redirects

An HTTP Basic API missing credentials typically returns 401 and WWW-Authenticate; unauthenticated web formLogin typically redirects to /login. If a request meant for an API gets redirected, inspect which chain was selected before debugging passwords. Authenticated requests lacking permissions usually return 403; missing CSRF tokens on state-changing methods can also return 403.

### 7.8. Confusing CORS with chain matching

CORS preflight (OPTIONS) in cross-origin APIs may be sent by the browser without cookies or Authorization headers like the actual request. An API accepting cross-origin requests needs proper CORS configuration and preflight handling ordered before authentication steps that might block it. Do not fix CORS errors by opening all of /api/** with permitAll or disabling security unchecked.

## 8. How to test matching and filter lists

When changing chain configuration, build a small request matrix covering sensitive areas:

| Input | Chain that must be selected | What to assert |
| --- | --- | --- |
| GET /api/status without Authorization | API | Receives Basic challenge, no web login redirect |
| GET /api/status with valid Basic | API | Authenticates via Basic and allowed by role USER |
| GET /api/unknown with valid Basic | API | Rejected by denyAll; controller does not run |
| GET /dashboard without session | Web fallback | Redirects to form login |
| GET /dashboard with logged-in session | Web fallback | Grants access after authorization |
| GET /public/ping without session | Web fallback | Permitted by permitAll yet still traverses the chain |
| GET /unexpected-admin without session | Web fallback | Does not fall outside Spring Security due to missing fallback |

In addition to checking HTTP statuses, check chain matcher/filter logs in dev or use integration tests. With Spring Security test dependencies, you can write MockMvc tests using mock users, Basic headers, and expected requests; note that mock users test authorization, **they do not prove BasicAuthenticationFilter actually authenticates the HTTP header**. To test the full HTTP Basic flow, send requests carrying real Basic credentials in a test environment configured with UserDetailsService as in the example.

A practical rule: whenever adding a new endpoint, check **which chain receives it, which filters execute, and then which authorization rule decides**. These three questions follow the exact order of request processing and help catch both gaps outside chain scope and permission bugs inside the chain.

## 9. Self-check

1. If @Order(1) is a catch-all fallback and @Order(2) is API /api/**, which chain does /api/status enter? Why?
2. Why might an /api/orders request not permitted by requestMatchers(HttpMethod.GET, "/api/status") still pass through the API chain's BasicAuthenticationFilter?
3. What is the difference between securityMatcher("/api/**") and requestMatchers("/api/**").permitAll()?
4. Why is it important to distinguish the order of SecurityFilterChains from the order of filters inside a chain?
5. When an API receives a 302 redirect to /login despite configuring httpBasic for the API, what step should you check first?
6. Why can using ignoring() for public URLs bypass protections that permitAll still maintains?
7. What behavior can a custom filter cause if it is both a Servlet bean and added to apiChain?
8. How do you prove that /admin is not left outside Spring Security after creating a SecurityFilterChain matching only /api/**?

Technical takeaway to remember: **FilterChainProxy selects the first SecurityFilterChain whose matcher matches the request; that chain determines the filter list; finally, authentication, CSRF, and authorization filters decide whether the request continues or is blocked.**