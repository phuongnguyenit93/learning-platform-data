# Testing Filters, Interceptors, CORS, and Spring Security Boundaries

> **Context:** Spring Boot – web-runtime → **Web runtime testing**. This lesson guides testing the exact boundaries between **Servlet Filters**, **Spring MVC HandlerInterceptors**, **CORS**, and **Spring Security FilterChainProxy**, avoiding tests that pass merely because security filters were accidentally disabled. Examples use **Java 17+, Spring Boot 3.3.x (Maven parent 3.3.13), Spring Framework 6.1.x, Spring Security 6.3.x**. Includes Maven POM, a complete application file, MockMvc test suite, real HTTP smoke test, curl commands, and an error matrix. Focus is Spring MVC/Servlet; WebFlux is compared separately to avoid API confusion.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Describe the request flow from Tomcat → Servlet filters → Spring Security → DispatcherServlet → HandlerMapping → HandlerInterceptor → controller.
2. Distinguish Filters at the **Servlet layer** from Interceptors at the **MVC handler layer**: Security can return 401/403 before any interceptor runs.
3. Choose `OncePerRequestFilter`, `@Order`, or `FilterRegistrationBean` appropriately and prevent double registration.
4. Test `HandlerInterceptor.preHandle`, `postHandle`, and `afterCompletion` in the right lifecycle, knowing when no handler matched.
5. Distinguish browser **CORS preflight OPTIONS** from actual cross-origin GET/POST requests; use `Origin` and `Access-Control-Request-*` headers accurately.
6. Ensure CORS is resolved **before authentication** in the Security chain, since preflight requests usually omit cookies/sessions.
7. Distinguish 401 (unauthenticated), 403 (insufficient role, bad CSRF, or rejected CORS), and 200 (allowed); never treat identical status codes as identical causes.
8. Verify CORS origin/method/header allowlists, `Access-Control-Allow-Credentials`, caching, and error response handling.
9. Separate **CORS** from authentication, authorization, and **CSRF**; a passing preflight does not exempt the actual POST from CSRF.
10. Run `@SpringBootTest + @AutoConfigureMockMvc` with filters active and `spring-security-test` using `user()`, `httpBasic()`, and `csrf()`.
11. Know the limits of `@WebMvcTest` slices and `MockMvcBuilders.standaloneSetup`; never use `addFilters=false` as proof the system is protected.
12. Supplement with `RANDOM_PORT` HTTP smoke tests and browser/proxy tests since MockMvc creates no real network sockets.
13. Spot `SecurityFilterChain`/route matcher ordering bugs, filter double registration, async/error dispatches, and forwarded-header mismatches.
14. Build a regression matrix covering happy paths, negative security tests, CORS preflight, actual requests, errors, and runtime.

## 2. Request Path in Spring MVC

~~~text
HTTP client / Browser
         |
         v
Servlet container: Tomcat
         |
         v
Servlet Filter chain
  +-- custom request marker / tracing Filter (if registered early)
  +-- DelegatingFilterProxy("springSecurityFilterChain")
  |      |
  |      v
  |   FilterChainProxy
  |      |
  |      +-- CorsFilter (when .cors(...) is configured)
  |      +-- security context / authentication
  |      +-- CSRF / authorization / exception translation
  |      |
  |      +-- may short-circuit with 401/403 here
  +-- other Servlet filters
         |
         v
DispatcherServlet
         |
         v
HandlerMapping + MVC CORS checks (when relevant)
         |
         v
HandlerInterceptor.preHandle(...)
         |
         v
HandlerAdapter -> Controller
         |
         v
postHandle / exception resolver / afterCompletion
         |
         v
Response flows back through Filters
~~~

This is a **typical model**, not an absolute ordering for every app. Filter order depends on registration; a filter can block before Security; `CorsFilter` can complete a preflight without entering `DispatcherServlet`. Async/error dispatches involve multiple phases. When multiple `SecurityFilterChain` beans exist, Spring Security selects the **first chain whose matcher matches**.

### Responsibility Comparison Table

| Component | API | Timing | Good For | Should Not Be Used As |
|---|---|---|---|---|
| Servlet Filter | `Filter`, `OncePerRequestFilter` | Before MVC handler resolution | Tracing/correlation, wrappers, redacted request logs, cross-cutting | Primary role/permission decision layer when Spring Security is present |
| Spring MVC Interceptor | `HandlerInterceptor` | After HandlerMapping finds an MVC handler | Handler-tied auditing, locale, metrics, MVC context | Protecting all Servlet/static/non-MVC endpoints |
| Spring Security | `SecurityFilterChain`, `FilterChainProxy` | Inside Servlet filter chain, usually before MVC | Authentication, authorization, CSRF, sessions, security headers | A hand-rolled interceptor |
| Spring MVC CORS | `@CrossOrigin`, `addCorsMappings` | HandlerMapping/handler-specific | Browser origins/methods/headers | Authentication |
| CorsFilter | `CorsFilter` / Security `.cors(...)` | Before auth inside security chain | Preflight and CORS response headers | CSRF protection |

A cross-origin browser JavaScript call allowed by CORS **does not mean** the user is logged in or authorized to read data. `curl`/server-side clients do not enforce browser CORS, yet remain subject to server authentication/authorization.

## 3. What Must Be Tested on Servlet Filters?

`jakarta.servlet.Filter` can observe requests/responses, wrap them, set attributes/headers, and forward via `chain.doFilter(request,response)`. It can short-circuit early, even when no matching MVC controller exists.

~~~java
// Snippet inside a class implementing Filter, not a standalone file.
@Override
public void doFilter(
        ServletRequest request,
        ServletResponse response,
        FilterChain chain)
        throws IOException, ServletException {

    long began = System.nanoTime();
    try {
        chain.doFilter(request, response);
    } finally {
        long elapsed = System.nanoTime() - began;
        // Record metric; never log Authorization/Cookie/PII.
    }
}
~~~

Forgetting `chain.doFilter` on a branch stops downstream controllers/Interceptors/Security filters on that branch from running. That may be an intentional rejection policy, which needs tests proving why.

### OncePerRequestFilter: “Once” Has Limits

`OncePerRequestFilter` prevents repeated execution **within a single request dispatch** per its API contract, yet async dispatches, error dispatches, and dispatcher type configurations can change filter invocations. Know these:

- `DispatcherType.REQUEST` for the primary request.
- `DispatcherType.ASYNC` for async processing.
- `DispatcherType.ERROR` for error dispatches.
- `shouldNotFilterAsyncDispatch()` and `shouldNotFilterErrorDispatch()`.
- One Servlet request can pass through multiple dispatch phases.

Therefore, never assume a filter callback executes strictly once per logical request across all async/ERROR flows. For tracing/MDC, test cleanup to prevent `ThreadLocal` state from leaking onto reused threads.

### Registration and Ordering

Boot automatically registers Spring beans implementing `Filter`. `@Order(Ordered.HIGHEST_PRECEDENCE)` places a marker filter very early. `FilterRegistrationBean` specifies URL patterns, dispatcher types, and explicit ordering.

~~~java
// Snippet illustrating alternative registration.
// Do not combine @Component auto-register with re-registering the same filter.
@Bean
FilterRegistrationBean<MyFilter> registerMyFilter(
        MyFilter filter) {
    FilterRegistrationBean<MyFilter> bean =
            new FilterRegistrationBean<>(filter);
    bean.addUrlPatterns("/api/*");
    bean.setDispatcherTypes(DispatcherType.REQUEST);
    bean.setOrder(Ordered.HIGHEST_PRECEDENCE);
    return bean;
}
~~~

`MyFilter` must be defined by the app, and the method requires proper imports. In the runnable project below we **only use `@Component` + `@Order`** for the filter, omitting this snippet to avoid double registration. Placing a filter inside `HttpSecurity.addFilterBefore(...)` registers it inside the **Security filter chain**, unlike a container-level filter; choose ownership and ordering deliberately.

## 4. HandlerInterceptor Has a Different Scope Than Filter

`HandlerInterceptor` has three core callbacks:

- `preHandle(request,response,handler)`: before the MVC controller; returning `false` halts the handler chain.
- `postHandle(...)`: after handler execution, before rendering per lifecycle; with REST response bodies, the response may already be committed.
- `afterCompletion(...)`: cleanup after request completion per contract; not invoked identically on all error/async paths.

For async MVC, there is also `AsyncHandlerInterceptor.afterConcurrentHandlingStarted(...)`. If an interceptor is registered only for `/api/**`, routes outside that pattern do not pass through it automatically.

~~~java
// Fragment of a HandlerInterceptor.
@Override
public boolean preHandle(
        HttpServletRequest request,
        HttpServletResponse response,
        Object handler) {
    response.setHeader("X-Mvc-Interceptor", "entered");
    return true;
}
~~~

The header is only a marker in the lab. If Security returns 401/403 before `DispatcherServlet`, the interceptor may **never run**, so the missing marker is expected. A 404 with no matched handler also does not imply the interceptor is broken.

**Do not treat `HandlerInterceptor` as a primary security boundary**. Spring Framework recommends Spring Security/filter chains for security because MVC path matching, static resources, and non-MVC endpoints have different scopes.

## 5. Spring Security FilterChainProxy Is the Primary Protection Layer

In Servlet applications, a `DelegatingFilterProxy` is normally registered by the container to invoke the `springSecurityFilterChain` bean—namely `FilterChainProxy`. Inside sit configured security filters: authentication, CSRF, exception handling, authorization, sessions, and CORS.

A request can be blocked before the controller ever sees it:

| HTTP Request | User State | Lab Result | Reason |
|---|---|---:|---|
| `GET /api/public` | anonymous | 200 | `permitAll` |
| `GET /api/private` | anonymous | 401 | authentication required |
| `GET /api/private` | wrong Basic password | 401 | authentication failed |
| `GET /api/private` | valid Basic viewer | 200 | authenticated |
| `GET /api/admin/report` | `ROLE_USER` | 403 | lacks `ROLE_ADMIN` |
| `GET /api/admin/report` | `ROLE_ADMIN` | 200 | authorized |
| `POST /api/notes` | authenticated, no CSRF token | 403 | CSRF rejected |
| `POST /api/notes` | authenticated + valid CSRF token | 200 in lab | authorization + CSRF valid |

**Do not assume 403 = missing role**. 403 can stem from insufficient privileges, an invalid/missing CSRF token, or a rejected CORS origin/method/header. Inspect origin, method, authentication, CSRF, and exception category.

`@RestControllerAdvice` does not automatically handle errors thrown from Security filters before `DispatcherServlet`. If production requires consistent `ProblemDetail`/JSON for 401/403, configure appropriate `AuthenticationEntryPoint` and `AccessDeniedHandler` implementations in Spring Security instead of relying solely on MVC exception handlers.

## 6. CORS Preflight and Actual Requests

CORS is a browser security mechanism governing whether JavaScript on one origin can read a response from another origin. An origin comprises scheme, host, and port. Browsers send a preflight before the actual request whenever the request is not a safelisted simple request.

### Actual Cross-Origin GET

~~~http
GET /api/public HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
~~~

Response may include:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json
~~~

This shows the meaningful headers only; real responses include additional security/cache headers. Server authentication still runs independently. Adding an `Origin` header in `curl` will not block reading the response by CORS; the browser enforces browser policy.

### Browser Preflight OPTIONS

~~~http
OPTIONS /api/private HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

If permitted, the server may respond:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: authorization
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

**Preflights normally do not send cookies/sessions**, so Spring Security docs require handling CORS **before authentication**. If Security treats `OPTIONS` as unauthenticated and returns 401 before checking CORS, browsers report a “CORS error” even when the actual endpoint works.

To test preflight, you need **`Origin`** and **`Access-Control-Request-Method`**, plus **`Access-Control-Request-Headers`** when custom headers are involved. An `OPTIONS` call lacking those headers does not prove preflight handling works.

### CORS Allowlist

Core properties of `CorsConfiguration`:

| Property | Controls | Guidance |
|---|---|---|
| `allowedOrigins` | Permitted origins | Use exact trusted HTTPS origins |
| `allowedMethods` | Permitted actual HTTP methods | Allow only actually used GET/POST/etc. |
| `allowedHeaders` | Headers frontend may send | Review `Authorization`/`Content-Type`/... |
| `exposedHeaders` | Response headers JS may read | Do not expose secrets |
| `allowCredentials` | Cross-origin browser credentials | Never pair recklessly with wildcard origin |
| `maxAge` | Preflight cache lifetime | Test cache/rollout policy |
| `Vary` | Avoid cross-origin cache poisoning | Verify gateway/CDN behavior |

**Never combine `Access-Control-Allow-Origin: *` with `Access-Control-Allow-Credentials: true`**. When credentials are needed, use a specific origin allowlist or tightly controlled origin patterns. Do not echo arbitrary `Origin` headers back and call it an allowlist.

## 7. CORS Does Not Replace Authentication or CSRF

A completely valid flow:

~~~text
OPTIONS preflight from trusted origin
  -> CORS allowed, 200

POST actual /api/notes from same origin
  -> authenticated user valid
  -> CSRF token missing or invalid
  -> 403
~~~

Preflight only lets the browser **attempt the actual request**; it grants no user permissions and creates no CSRF token. With cookie/session authentication, CSRF protection plays a vital role; never disable CSRF just to “fix CORS.”

In `spring-security-test`:

~~~java
// Snippet inside a test with MockMvc mvc and spring-security-test imports.
mvc.perform(post("/api/notes")
        .with(user("viewer").roles("USER"))
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"text\":\"hello\"}"))
    .andExpect(status().isForbidden());

mvc.perform(post("/api/notes")
        .with(user("viewer").roles("USER"))
        .with(csrf())
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"text\":\"hello\"}"))
    .andExpect(status().isOk());
~~~

`with(csrf())` creates a valid token **for the test**, not designing how the production frontend obtains tokens. If the real app uses sessions/cookies, it must issue tokens and send them from the browser per security design; if stateless JWT bearer, evaluate the threat model before choosing a CSRF policy.

## 8. Choosing the Right Test Layer

| Test Approach | Covers | Does Not Fully Cover |
|---|---|---|
| Direct JUnit with mock `FilterChain` | Single Filter logic | Real filter ordering/context |
| `@WebMvcTest` + MockMvc | MVC controller, selected MVC beans | Custom configurations outside the slice |
| `@SpringBootTest` + `@AutoConfigureMockMvc` | App context + registered filters + Security chain + MVC in mock environment | Real socket/TLS/proxy/container-specific behavior |
| `@SpringBootTest(RANDOM_PORT)` | Real embedded HTTP server and actual headers | Browser CORS enforcement/ingress behavior |
| Browser E2E | Real browser CORS, credentials, redirects, cookies | Does not replace unit/security negative tests |
| Staging through gateway | TLS/proxy/CORS duplication/forwarded headers | Slow, environment dependent |

**Do not test security with `@AutoConfigureMockMvc(addFilters=false)`**: it removes filters in MockMvc, including Spring Security. If the true goal is purely controller unit behavior, a filter-disabled test may be acceptable when clearly named, provided other tests run with filters enabled to prove security.

`@WebMvcTest` is a slice: it may scan certain `Filter`/`HandlerInterceptor`/`WebMvcConfigurer` beans, yet custom `@Configuration` and authentication beans may be absent unless imported. A slice test returning 200 does not automatically prove the production `SecurityFilterChain` is right. This lesson uses the full context to reduce the risk of testing the wrong configuration.

## 9. Runnable Lab: Spring MVC + Security + CORS

Four endpoints:

~~~text
GET  /api/public         : anonymous 200
GET  /api/private        : authenticated user
GET  /api/admin/report   : requires ROLE_ADMIN
POST /api/notes          : authenticated + CSRF

RequestMarkerFilter @Order(HIGHEST_PRECEDENCE)
   -> Spring Security CorsFilter/auth/CSRF/role
   -> DispatcherServlet
   -> HandlerMarkerInterceptor for /api/**
   -> Controller
~~~

Marker headers in responses: `X-Request-Filter: seen` if the custom Servlet filter ran, `X-Mvc-Interceptor: entered` if `preHandle` ran. These headers are **not authentication certificates**, merely trace markers allowing boundary verification.

### 9.1. Project Layout

~~~text
web-boundary-lab/
  pom.xml
  src/main/java/example/webboundary/WebBoundaryApplication.java
  src/main/resources/application.properties
  src/test/java/example/webboundary/WebBoundaryApplicationTests.java
  src/test/java/example/webboundary/RealHttpCorsSmokeTests.java
~~~

### 9.2. Complete pom.xml

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
    <groupId>example</groupId>
    <artifactId>web-boundary-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
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
~~~

Boot parent's BOM manages Security 6.3 and Spring Framework 6.1 versions in the 3.3 branch; do not override individual dependencies without compatibility/security reasons. `spring-security-test` is in `test` scope and is not packaged as a production runtime library.

### 9.3. application.properties

~~~properties
server.port=8080
server.error.include-message=never
server.error.include-exception=false
server.error.include-stacktrace=never
~~~

### 9.4. Full Java Application

Create `src/main/java/example/webboundary/WebBoundaryApplication.java`:

~~~java
package example.webboundary;

import java.io.IOException;
import java.util.List;
import java.util.Map;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@SpringBootApplication
public class WebBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebBoundaryApplication.class, args);
    }

    @Component
    @Order(Ordered.HIGHEST_PRECEDENCE)
    static class RequestMarkerFilter extends OncePerRequestFilter {
        @Override
        protected void doFilterInternal(
                HttpServletRequest request,
                HttpServletResponse response,
                FilterChain chain)
                throws ServletException, IOException {

            response.setHeader("X-Request-Filter", "seen");
            chain.doFilter(request, response);
        }
    }

    @Component
    static class HandlerMarkerInterceptor
            implements HandlerInterceptor {

        @Override
        public boolean preHandle(
                HttpServletRequest request,
                HttpServletResponse response,
                Object handler) {

            response.setHeader("X-Mvc-Interceptor", "entered");
            return true;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class MvcConfiguration implements WebMvcConfigurer {
        private final HandlerMarkerInterceptor marker;

        MvcConfiguration(HandlerMarkerInterceptor marker) {
            this.marker = marker;
        }

        @Override
        public void addInterceptors(InterceptorRegistry registry) {
            registry.addInterceptor(marker)
                    .addPathPatterns("/api/**");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class SecurityConfiguration {

        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {

            return http
                .cors(Customizer.withDefaults())
                // Do not disable CSRF: POST must carry a valid token.
                .authorizeHttpRequests(auth -> auth
                    .requestMatchers(
                        HttpMethod.GET, "/api/public").permitAll()
                    .requestMatchers("/api/admin/**")
                        .hasRole("ADMIN")
                    .anyRequest().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(AbstractHttpConfigurer::disable)
                .build();
        }

        @Bean
        UrlBasedCorsConfigurationSource corsConfigurationSource() {
            CorsConfiguration config = new CorsConfiguration();
            config.setAllowedOrigins(
                List.of("https://app.example.test"));
            config.setAllowedMethods(
                List.of("GET", "POST", "OPTIONS"));
            config.setAllowedHeaders(
                List.of("Authorization",
                        "Content-Type", "X-Request-ID"));
            config.setExposedHeaders(
                List.of("X-Request-Filter",
                        "X-Mvc-Interceptor"));
            config.setAllowCredentials(true);
            config.setMaxAge(600L);

            UrlBasedCorsConfigurationSource source =
                    new UrlBasedCorsConfigurationSource();
            source.registerCorsConfiguration("/api/**", config);
            return source;
        }

        @Bean
        PasswordEncoder passwordEncoder() {
            return PasswordEncoderFactories
                    .createDelegatingPasswordEncoder();
        }

        @Bean
        UserDetailsService userDetailsService(
                PasswordEncoder encoder) {

            // Static credentials FOR LAB ONLY; never use in production.
            return new InMemoryUserDetailsManager(
                User.withUsername("viewer")
                    .password(encoder.encode("viewer-pass"))
                    .roles("USER")
                    .build(),
                User.withUsername("admin")
                    .password(encoder.encode("admin-pass"))
                    .roles("ADMIN")
                    .build()
            );
        }
    }

    public record NoteInput(String text) {
    }

    @RestController
    static class ApiController {

        @GetMapping("/api/public")
        public Map<String, String> publicInfo() {
            return Map.of("visibility", "public");
        }

        @GetMapping("/api/private")
        public Map<String, String> privateInfo(
                Authentication authentication) {
            return Map.of(
                "user", authentication.getName(),
                "visibility", "private");
        }

        @GetMapping("/api/admin/report")
        public Map<String, String> adminReport() {
            return Map.of("report", "admin-only");
        }

        @PostMapping(value = "/api/notes",
                     consumes = MediaType.APPLICATION_JSON_VALUE)
        public ResponseEntity<Map<String, String>> createNote(
                @RequestBody NoteInput note,
                Authentication authentication) {
            return ResponseEntity.ok(Map.of(
                "owner", authentication.getName(),
                "text", note.text()));
        }
    }
}
~~~

### 9.5. Explaining the Code Classes

**`RequestMarkerFilter`** is registered into the Servlet container by Boot because it is a Spring bean of type `Filter`. With `@Order(HIGHEST_PRECEDENCE)` in the lab, it executes before the Security chain and sets the header before `chain.doFilter`. Security may return 401/403 yet the header is already set, so tests observe `X-Request-Filter: seen`.

**`HandlerMarkerInterceptor`** applies only after MVC mapping chooses a handler for `/api/**`. Requests rejected earlier by Security never reach the interceptor, so `X-Mvc-Interceptor` is absent. Neither marker verifies tokens, passwords, or roles.

**`SecurityConfiguration`** supplies an explicit `SecurityFilterChain` and `UrlBasedCorsConfigurationSource` bean. `http.cors(Customizer.withDefaults())` integrates CORS ahead of Security authentication checks. Authorization leaves `GET /api/public` open, requires `ROLE_ADMIN` on admin routes, and requires authentication for the rest; HTTP Basic is enabled for the lab while form login is disabled so the API returns 401. CSRF stays enabled, protecting POST.

**`InMemoryUserDetailsManager`** contains two simulated users with encoded passwords; **never deploy these users/passwords to production**. Usernames/passwords are included in the guide solely for local curl exercises. Production needs an IdP, secret manager, HTTPS, and security review. `CORS.allowCredentials=true` pairs with an exact trusted Origin, not a wildcard.

**`ApiController`** includes a POST accepting JSON to test CSRF; data is not persisted to a DB, so `createNote` in the lab merely echoes input. Real products storing user input require Bean Validation, object/tenant-level authorization, and input bounds.

## 10. Full MockMvc Test File: Keeping Filters Active

Create `src/test/java/example/webboundary/WebBoundaryApplicationTests.java`:

~~~java
package example.webboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class WebBoundaryApplicationTests {
    private static final String ORIGIN =
            "https://app.example.test";

    @Autowired
    MockMvc mvc;

    @Test
    void publicRouteCrossesFilterAndMvcInterceptor()
            throws Exception {
        mvc.perform(get("/api/public"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Request-Filter", "seen"))
            .andExpect(header().string(
                "X-Mvc-Interceptor", "entered"))
            .andExpect(jsonPath("$.visibility")
                .value("public"));
    }

    @Test
    void anonymousRequestIsStoppedBeforeMvc() throws Exception {
        mvc.perform(get("/api/private"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                "X-Request-Filter", "seen"))
            .andExpect(header().doesNotExist(
                "X-Mvc-Interceptor"));
    }

    @Test
    void wrongBasicPasswordFails() throws Exception {
        mvc.perform(get("/api/private")
                .with(httpBasic("viewer", "wrong-pass")))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validBasicPasswordReachesController() throws Exception {
        mvc.perform(get("/api/private")
                .with(httpBasic("viewer", "viewer-pass")))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Mvc-Interceptor", "entered"))
            .andExpect(jsonPath("$.user").value("viewer"));
    }

    @Test
    void viewerIsForbiddenFromAdminReport() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("viewer").roles("USER")))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                "X-Mvc-Interceptor"));
    }

    @Test
    void adminIsAuthorized() throws Exception {
        mvc.perform(get("/api/admin/report")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.report")
                .value("admin-only"));
    }

    @Test
    void allowedPreflightDoesNotRequireCredentials()
            throws Exception {
        mvc.perform(options("/api/private")
                .header(HttpHeaders.ORIGIN, ORIGIN)
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "GET")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
                    "Authorization"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ORIGIN))
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_CREDENTIALS,
                "true"))
            .andExpect(header().doesNotExist(
                "X-Mvc-Interceptor"));
    }

    @Test
    void rejectedOriginPreflightHasNoAllowOrigin()
            throws Exception {
        mvc.perform(options("/api/private")
                .header(HttpHeaders.ORIGIN,
                    "https://evil.example.test")
                .header(
                    HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD,
                    "GET"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
    }

    @Test
    void actualCorsGetHasAllowOrigin() throws Exception {
        mvc.perform(get("/api/public")
                .header(HttpHeaders.ORIGIN, ORIGIN))
            .andExpect(status().isOk())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ORIGIN));
    }

    @Test
    void actualCorsGetStillRequiresAuthentication()
            throws Exception {
        mvc.perform(get("/api/private")
                .header(HttpHeaders.ORIGIN, ORIGIN))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN,
                ORIGIN));
    }

    @Test
    void authenticatedPostWithoutCsrfIsForbidden()
            throws Exception {
        mvc.perform(post("/api/notes")
                .with(user("viewer").roles("USER"))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isForbidden())
            .andExpect(header().doesNotExist(
                "X-Mvc-Interceptor"));
    }

    @Test
    void authenticatedPostWithCsrfPasses()
            throws Exception {
        mvc.perform(post("/api/notes")
                .with(user("viewer").roles("USER"))
                .with(csrf())
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"text\":\"hello\"}"))
            .andExpect(status().isOk())
            .andExpect(header().string(
                "X-Request-Filter", "seen"))
            .andExpect(header().string(
                "X-Mvc-Interceptor", "entered"))
            .andExpect(jsonPath("$.text").value("hello"))
            .andExpect(jsonPath("$.owner").value("viewer"));
    }
}
~~~

### Meaning of the 12 Tests

- Public endpoint test verifies **both filter and interceptor** are present when the controller runs.
- Anonymous test checks 401 and that the filter marker appears while the interceptor marker does not, demonstrating Security short-circuiting.
- Wrong/valid HTTP Basic tests go through real authentication instead of faking a user.
- Viewer/admin tests separate role authorization checks from authentication.
- Allowed preflight test sends no Basic credentials, yet receives allow-origin from the CORS policy; the MVC interceptor does not run.
- Unknown Origin preflight gets 403, **without** allow-origin.
- Actual cross-origin GET is permitted by CORS, yet the private endpoint still returns 401 when unauthenticated.
- POST without CSRF returns 403; with a CSRF token via `with(csrf())`, it reaches the MVC controller and returns JSON.

**Distinguish two test helpers:** `with(user(...))` populates an authenticated principal in the Security test context to test authorization, **without** verifying password hashes or JWT signatures. `with(httpBasic(...))` creates a Basic Authorization header that genuinely exercises the lab's authentication provider. For production OAuth2/JWT, write tests hitting decoder/issuer/audience/signature validation instead of merely mocking a user and claiming token verification works.

`@AutoConfigureMockMvc` does not set `addFilters=false`, so real security filters are registered in the mock environment. This test **does not** start a real TCP server.

## 11. Smoke Test on a Real HTTP Server

MockMvc operates inside test MVC infrastructure; it does not simulate all network/container details. Add a `RANDOM_PORT` test with `TestRestTemplate`.

Create `src/test/java/example/webboundary/RealHttpCorsSmokeTests.java`:

~~~java
package example.webboundary;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealHttpCorsSmokeTests {

    @Autowired
    TestRestTemplate http;

    @Test
    void realHttpResponseContainsCorsAndMarkerHeaders() {
        HttpHeaders headers = new HttpHeaders();
        headers.setOrigin("https://app.example.test");

        ResponseEntity<String> response = http.exchange(
                "/api/public",
                HttpMethod.GET,
                new HttpEntity<>(headers),
                String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("https://app.example.test",
                response.getHeaders().getFirst(
                    HttpHeaders.ACCESS_CONTROL_ALLOW_ORIGIN));
        assertEquals("seen",
                response.getHeaders().getFirst(
                    "X-Request-Filter"));
        assertEquals("entered",
                response.getHeaders().getFirst(
                    "X-Mvc-Interceptor"));
    }
}
~~~

`RANDOM_PORT` starts a real embedded HTTP server on a random port and `TestRestTemplate` sends HTTP requests. It verifies CORS/marker headers on the wire; **it does not replace a browser E2E test**, because HTTP test clients do not enforce CORS like browsers. `@SpringBootTest` contexts for mock and real-server tests may differ and incur separate startup times.

### Running the Test Suite

~~~bash
mvn clean test
mvn clean package
~~~

With valid Java 17/Maven/dependencies and proper package layout, the suite has **12 MockMvc tests + 1 real HTTP test**; Maven should report passing tests. Build output/timestamps/log lines vary by OS and tool versions; do not match stdout character-for-character.

If a test fails, check the first status/header failure, security chain, and CORS config before deleting assertions. Never change tests to `addFilters=false` to force green builds.

## 12. Testing Live with curl

Run in the project directory:

~~~bash
mvn spring-boot:run
~~~

In another terminal:

~~~bash
# 200: filter + MVC interceptor.
curl -i http://localhost:8080/api/public

# 401: filter runs; MVC interceptor does not run.
curl -i http://localhost:8080/api/private

# 200: valid HTTP Basic (local lab credentials ONLY).
curl -i -u viewer:viewer-pass \
  http://localhost:8080/api/private

# 403: USER lacks ROLE_ADMIN.
curl -i -u viewer:viewer-pass \
  http://localhost:8080/api/admin/report

# 200: ADMIN permitted.
curl -i -u admin:admin-pass \
  http://localhost:8080/api/admin/report
~~~

Equivalent success JSON bodies (field order may vary):

~~~json
{"visibility":"public"}
~~~

~~~json
{"user":"viewer","visibility":"private"}
~~~

~~~json
{"report":"admin-only"}
~~~

### Preflight Allowed Origin

~~~bash
curl -i -X OPTIONS \
  "http://localhost:8080/api/private" \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Authorization"
~~~

Expect status 200 and headers `Access-Control-Allow-Origin: https://app.example.test`, `Access-Control-Allow-Credentials: true` per lab config. Preflight **does not need** `Authorization`/cookies to be processed by CORS.

### Preflight Denied Origin

~~~bash
curl -i -X OPTIONS \
  "http://localhost:8080/api/private" \
  -H "Origin: https://evil.example.test" \
  -H "Access-Control-Request-Method: GET"
~~~

Expect 403 and no `allow-origin` for the evil origin. Browsers prevent JavaScript on the evil origin from reading the response per policy; curl can still print the raw bytes because it is not a browser.

### Actual Cross-Origin Private GET Missing Basic

~~~bash
curl -i \
  "http://localhost:8080/api/private" \
  -H "Origin: https://app.example.test"
~~~

Expect **401** even though `Origin` is allowed. This proves “CORS allowed” differs from “authenticated.”

### Authenticated POST Missing CSRF

~~~bash
curl -i \
  -u viewer:viewer-pass \
  -H "Content-Type: application/json" \
  -d '{"text":"hello"}' \
  "http://localhost:8080/api/notes"
~~~

Expect **403** because no valid CSRF token is present. `curl` does not generate CSRF tokens automatically; the positive test uses `with(csrf())`. In a real frontend needing POST with cookies/sessions, implement proper CSRF token exchange. Never disable CSRF carelessly.

### Method/Header Not in Allowlist

~~~bash
curl -i -X OPTIONS \
  "http://localhost:8080/api/private" \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: DELETE" \
  -H "Access-Control-Request-Headers: X-Unapproved-Header"
~~~

Expect CORS rejection (403) because the lab policy forbids `DELETE` and custom headers. Testing both allowed origins **and** disallowed methods/headers is essential; testing only the good origin is insufficient.

## 13. @WebMvcTest, standaloneSetup, and False Positives

`@WebMvcTest` is an MVC-focused slice, typically faster than full context, yet limits scanned beans. `Filter`, `HandlerInterceptor`, and `WebMvcConfigurer` may be included by component type, while custom `@Configuration` or service dependencies are not loaded by default. Without importing security config, a test may run a **different `SecurityFilterChain`** than production.

Snippet:

~~~java
// Illustrative setup; not a complete test class.
@WebMvcTest(WebBoundaryApplication.ApiController.class)
@Import({
    WebBoundaryApplication.SecurityConfiguration.class,
    WebBoundaryApplication.MvcConfiguration.class
})
class ApiSliceTest {
    @Autowired MockMvc mvc;
}
~~~

For other service dependencies, use `@MockBean`/test config per Boot 3.3. Do not import every auto-configuration manually; test slices have Boot's own management mechanism.

### Comparing Easily Confused Test Setups

| Test Setup | Pitfall |
|---|---|
| `MockMvcBuilders.standaloneSetup(controller)` | Lacks Spring Security `FilterChainProxy` automatically |
| `@WebMvcTest` missing custom config | May not reflect actual role/CORS rules |
| `@AutoConfigureMockMvc(addFilters=false)` | Disables Security/CORS/Servlet filters |
| `with(user("admin").roles("ADMIN"))` | Does not verify Basic passwords/JWT signatures |
| `with(httpBasic(...))` | Hits Basic auth provider yet does not test browser cookie policy |
| `MockMvc` | Does not test TCP/TLS/container-specific behavior |
| `RANDOM_PORT` `TestRestTemplate` | Real HTTP yet does not enforce browser CORS |
| Browser test | Real CORS/cookies/redirects yet still needs dedicated backend authorization tests |

Manual `MockMvc` with `WebApplicationContext` should apply the Spring Security test configurer:

~~~java
// Snippet; requires WebApplicationContext context.
MockMvc mvc = MockMvcBuilders
        .webAppContextSetup(context)
        .apply(springSecurity())
        .build();
~~~

In the lab, `@AutoConfigureMockMvc` integrates the full context's Security filter chain, avoiding manual builders. For OAuth2 resource servers, add dedicated tests for decoding/signature/issuer/audience/scope rather than mocking roles alone.

## 14. When Multiple SecurityFilterChains Exist

Spring Security picks the first chain matching a request by `securityMatcher`/`@Order`. Example:

~~~java
// Structural fragment, not a complete SecurityConfig.
@Bean
@Order(1)
SecurityFilterChain adminChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/admin/**")
        .authorizeHttpRequests(a -> a
            .anyRequest().hasRole("ADMIN"))
        .httpBasic(Customizer.withDefaults())
        .build();
}

@Bean
@Order(2)
SecurityFilterChain fallback(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(a -> a
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
~~~

A chain matching only `/admin/**` **does not automatically protect** other routes. The fallback chain is critical. In multi-chain apps, CORS/CSRF/session policies may differ across chains; configure and test each group, avoiding two `CorsConfigurationSource` beans that prevent Spring Security from picking automatically.

### Required Negative Tests

- `GET /admin/report` with `USER` → 403; `ADMIN` → 200.
- `GET /api/private` anonymous → 401 **from fallback**.
- New routes outside `/api/**` or `/admin/**` are not unintentionally public.
- `OPTIONS` preflight on admin/public APIs per each real chain's policy.
- URL path encoding, servlet path, trailing slash, and proxy rewrite cases if present.
- Authenticated role vs object ownership: `ROLE_ADMIN`/`ROLE_USER` alone do not prove tenant/resource-level authorization.

Never substitute a custom interceptor because it failed to match `SecurityFilterChain`. Every protected resource must have a clearly defined owner.

## 15. Async, Error Dispatch, 404, and Response Commit

A REST controller may use `Callable`, `DeferredResult`, or reactive return adapters in Spring MVC. When async dispatch occurs, `OncePerRequestFilter`, interceptor callbacks, and MDC/ThreadLocal require dedicated tests. With `ERROR` dispatch, controller advice, Servlet error pages, and Security filters can execute in different phases.

- A Servlet filter can set headers before the chain; setting headers **after** the chain when the response is already committed may have no effect.
- `postHandle` is not guaranteed to be able to add headers on every REST response; the response body may already be flushed.
- An interceptor may not run if Security blocks or `HandlerMapping` finds no handler.
- `afterCompletion` depends on `preHandle`/lifecycle to run.
- Filters on `/error` or actuator endpoints may match different URL patterns/dispatcher types than `/api/**`.
- For exceptions inside a filter before `DispatcherServlet`, `@RestControllerAdvice` is not always the active error handler.
- For async timeouts/cancellations, verify cleanup of request attributes, pooled resources, and correlation context, not just status.

### URL Matching Mismatches

URL variations like `/api/private`, `/api/private/`, `/api//private`, uppercase, encoded dot segments, or semicolon parameters can be normalized differently across proxies/Tomcat/MVC/Security depending on version/config. Never assume they yield identical outcomes. When testing authorization policies, test normalized routes with explicit matchers; keep `StrictHttpFirewall`/framework defaults per Spring Security guidance rather than disabling the request firewall to “fix” 400/404.

## 16. CORS Through Proxy and Browser

A passing MockMvc test does not prove the app works behind ingress:

~~~text
Browser https://app.example.test
  | OPTIONS /api/private
  v
CDN / Ingress / NGINX
  | may redirect, cache, rewrite, or add CORS headers
  v
Spring Security CorsFilter
  |
  v
Controller (actual request after preflight)
  |
  v
Response back through proxy/browser
~~~

Cases to test:

1. Reverse proxy returns 301/302 on `OPTIONS` for HTTP→HTTPS or another path.
2. Gateway sets `Access-Control-Allow-Origin: *` while Spring returns an exact origin, causing duplicate/conflicting headers.
3. CDN caches a CORS response without `Vary: Origin`, serving one origin's allow-origin to another.
4. Browser requests use headers missing from the allowlist, e.g., `Authorization` + `X-Client-Version`.
5. Actual request returns 401/403 yet the error response lacks CORS headers; browser reports “CORS error” instead of letting code read the error body.
6. Cookie `SameSite`, `Secure`, domain/path, and browser credentials mode mismatch; not every login failure is CORS.
7. Proxy rewrites `Host`, scheme/forwarded headers wrongly; trust only trusted ingress, never arbitrary `X-Forwarded-*` from the internet.
8. Browser preflight caching causes stale behavior after changing allowlists; inspect browser network tab and cache behavior.
9. NGINX/Envoy/service mesh and the app both enforce CORS policies without a single owner, letting preflight pass while actual requests fail.

**Always verify against the final public HTTPS URL**, not just localhost, and use browser/E2E tests for browser enforcement. Direct `curl` is great for inspecting raw headers/statuses, yet does not enforce browser CORS restrictions.

## 17. Acceptance Matrix

| Case | Security Outcome | CORS Outcome | Filter Marker | MVC Marker |
|---|---|---|---|---|
| Anonymous GET public | 200 | No Origin | Yes | Yes |
| Anonymous GET private | 401 | No Origin | Yes | No |
| Wrong Basic password | 401 | No Origin | Yes | No |
| Valid Basic viewer | 200 | No Origin | Yes | Yes |
| Viewer calling admin | 403 | No Origin | Yes | No |
| Admin calling admin | 200 | No Origin | Yes | Yes |
| Allowed preflight OPTIONS | No auth required | 200 + allow-origin | Yes in lab setup | No |
| Denied origin preflight | Blocked early | 403, no allow-origin | Yes in lab setup | No |
| Actual CORS GET public | 200 | Allow-origin | Yes | Yes |
| Actual CORS GET private anonymous | 401 | Allow-origin | Yes | No |
| Authenticated POST without CSRF | 403 | No Origin | Yes | No |
| Authenticated POST with CSRF | 200 | No Origin | Yes | Yes |
| CORS disallowed DELETE/header | Blocked early | 403 | Yes in lab setup | No |
| Route with no MVC handler | 404 or error per config | Depends on route/CORS mapping | Filter may run | Not guaranteed |
| Error/async dispatch | Per container/security context | Per dispatch | Depends on dispatcher types | Per async/error lifecycle |

These are the lab's outcomes, **not universal defaults for every app**. A project with a custom `AuthenticationEntryPoint` or CSRF exemptions may respond differently; document the contract and test the actual policy.

## 18. Anti-Patterns to Avoid

| Mistake | Consequence | Fix |
|---|---|---|
| Disabling filters to make security tests pass | Bypasses `FilterChainProxy` and CORS | Use full context + MockMvc with filters |
| Using `with(user())` to prove passwords/JWT | Authentication provider is never exercised | `httpBasic()` or JWT decoder tests |
| Checking only 200 | Misses 401/403/CSRF/CORS failures | Positive + negative matrix |
| `OPTIONS` missing `Origin`/`Request-Method` | Does not genuinely test preflight | Send complete headers |
| Requiring cookies on preflight | Browser preflights usually lack them | Run CORS before authentication |
| Disabling CSRF to fix CORS errors | Can open a CSRF vulnerability | Check request policy/filter order |
| Treating CORS allow-origin as logged in | API may still be unauthenticated | Keep AuthN/AuthZ independent |
| Wildcard `allowedOrigins` with `credentials=true` | Violates security/browser semantics | Exact trusted origins |
| Testing only allowed origins | Overly permissive policy goes unnoticed | Denied-origin/header/method tests |
| Filter setting “authenticated” header | Pre-Security headers carry no auth trust | Use authenticated `SecurityContext` when appropriate |
| Checking roles in an Interceptor instead of Spring Security | Misses non-MVC/static/matcher mismatches | `SecurityFilterChain` |
| Registering filter in both container and security | Runs twice, skews audit/rate-limit | Single registration owner |
| Slice test missing `@Import` custom config | May test a chain differing from production | `@Import` or full `@SpringBootTest` |
| `@ControllerAdvice` catching all 401/403 | Security errors may happen before MVC | `EntryPoint` + `AccessDeniedHandler` |
| Treating MockMvc as enough for HTTP2/TLS/cookies | No real socket/browser | `RANDOM_PORT` + E2E |
| Both proxy and app writing CORS headers | Duplicates cause browser rejection | Single owner and tests |
| Not testing fallback `SecurityFilterChain` | New endpoints may become public | Negative tests for unknown routes |
| Ignoring `ASYNC`/`ERROR` dispatches | Lost traces/broken cleanup | Dispatcher types + async/error tests |

## 19. WebFlux Differences

If the application is Spring WebFlux/Reactive, do not port MVC Interceptors/Servlet Filters directly:

| Concern | Spring MVC | Spring WebFlux |
|---|---|---|
| Request filter | `jakarta.servlet.Filter`/`OncePerRequestFilter` | `org.springframework.web.server.WebFilter` |
| Filter chain | `FilterChain` | `WebFilterChain` |
| Handler interception | `HandlerInterceptor` | Reactive handler filters/`WebFilter`; no MVC interceptor |
| Security | `SecurityFilterChain`/`HttpSecurity` | `SecurityWebFilterChain`/`ServerHttpSecurity` |
| CORS | `CorsFilter`/MVC CORS | WebFlux CORS/`CorsWebFilter` |
| Tests | `MockMvc`, `spring-security-test` | `WebTestClient`, reactive Security test support |
| Request context | Servlet request/thread-local | `ServerWebExchange`/Reactor Context |
| Cancellation | Servlet async lifecycle | Reactive publisher cancellation |

A WebFlux filter snippet:

~~~java
// Fragment, not a standalone Java file.
@Bean
WebFilter reactiveMarker() {
    return (exchange, chain) -> {
        exchange.getResponse().getHeaders()
                .add("X-Reactive-Filter", "seen");
        return chain.filter(exchange);
    };
}
~~~

It does not replace authentication. In the reactive stack, `SecurityWebFilterChain` and CORS filter ordering follow reactive mechanisms. Use `@WebFluxTest` or `@SpringBootTest + @AutoConfigureWebTestClient` appropriately, importing custom reactive security configs into slices if needed. With both `starter-web` and `starter-webflux` on Boot 3.3, MVC usually takes precedence as the default server stack: do not assume you tested a WebFlux server merely by seeing `Mono` in code.

## 20. Troubleshooting by Symptom

**A. Browser reports CORS error yet curl GET returns 200.**  
Check actual `Origin`, preflight `OPTIONS`, `Access-Control-Request-Method`/`Headers`, `Allow-Origin` response, credentials mode, and proxies. Curl does not enforce CORS.

**B. Preflight returns 401.**  
Check `http.cors(...)`, `CorsConfigurationSource`/MVC CORS integration, and Security ordering; do not require browser preflights to carry session cookies.

**C. Preflight 200 yet POST returns 403.**  
Check CSRF, authentication, role, and actual request; preflight does not waive CSRF.

**D. Unauthenticated test still returns 200.**  
Check for `addFilters=false`, `standaloneSetup`, global mock principals, or default/test chains differing from production.

**E. Missing `X-Mvc-Interceptor` on 401.**  
Security likely blocked before `DispatcherServlet`, which is the right behavior.

**F. Missing marker on `OPTIONS` preflight.**  
`CorsFilter` can handle it before MVC so the interceptor does not run; do not assume `OPTIONS` always hits controllers.

**G. 403 from an unrecognized origin.**  
Likely CORS rejection before Security authz, not a role issue. Inspect response headers and logs.

**H. Passes locally yet fails in production.**  
Check gateway rewrites/redirects, caching/`Vary`, cookie `SameSite`, TLS/forwarded headers, and duplicate CORS policies.

**I. Filter invoked twice.**  
Look for `@Component`, `FilterRegistrationBean`, `addFilterBefore`/`addFilterAfter`, and dispatcher types; eliminate duplicate registration.

**J. New admin route slips past Security.**  
Check `securityMatcher`, ordering, fallback chain, and path normalization; add negative tests for the new route.

## 21. CI and Review Checklist

- [ ] Maven/JUnit runs on Java 17+ with matching Boot 3.3 dependencies.
- [ ] MockMvc tests keep Servlet filters enabled and use the real `SecurityFilterChain`.
- [ ] 200 public, 401 anonymous private, 401 invalid Basic.
- [ ] 403 authenticated USER on admin, 200 ADMIN.
- [ ] Preflight allowed origin/method/header succeeds without cookies.
- [ ] Preflight denied origin/method/header omits allow-origin.
- [ ] Actual cross-origin requests still enforce authentication when credentials are missing.
- [ ] Authenticated POST without CSRF gets 403; with CSRF token succeeds.
- [ ] `RequestMarkerFilter` runs on early denial; `HandlerMarkerInterceptor` does not.
- [ ] Success path carries both Filter and Interceptor markers.
- [ ] Slice tests have proper `@Import`/configs or full-context tests cover them.
- [ ] Real HTTP `RANDOM_PORT` smoke test runs against a real embedded server.
- [ ] Browser/gateway E2E tests verify Origin/cookies/redirects/caching.
- [ ] Security matcher fallbacks and non-API routes are protected per contract.
- [ ] No duplicate filters or CORS headers.
- [ ] No lab credentials, raw auth/cookies, or secrets in production logs.
- [ ] Negative regression tests cover CORS, CSRF, and `SecurityFilterChain` changes.

If CI fails, do not “fix” it by disabling filters or adding `permitAll`. Trace request path/matchers, preflight headers, security context, CSRF, filter ordering, and exception ownership.

## 22. Self-Check Questions

**1. Do Filters and Interceptors share the same scope?**  
No. Filters operate at the Servlet layer; Interceptors operate at the Spring MVC handler layer.

**2. When Security returns 401 before `DispatcherServlet`, must `preHandle` run?**  
No. Interceptors normally do not run when the security chain short-circuits early.

**3. Does CORS replace authentication?**  
No. It is a browser cross-origin access policy.

**4. Is an `OPTIONS` request without `Origin` a valid browser preflight?**  
Insufficient. Preflights include `Origin` and `Access-Control-Request-Method`.

**5. Do preflight requests usually carry a `JSESSIONID` cookie?**  
No. That is why CORS must be evaluated before authentication checks.

**6. If preflight succeeds, is the actual POST exempt from CSRF?**  
No. CSRF and CORS are two separate concerns.

**7. Does 403 always mean a missing role?**  
No. CSRF or CORS rejections can also return 403.

**8. Why not use `HandlerInterceptor` as the sole security boundary?**  
It does not consistently cover non-MVC endpoints and risks path-matcher mismatches.

**9. Does `@WebMvcTest` always import custom `SecurityFilterChain` beans?**  
No. Slices can omit external `@Configuration`; import explicitly or use full context.

**10. Does `addFilters=false` prove production authentication works?**  
No. It can strip `FilterChainProxy` from MockMvc.

**11. Does `with(user(...))` verify real passwords?**  
No. It mocks an authenticated principal; the `httpBasic` helper goes through the Basic provider.

**12. What does `with(csrf())` do?**  
Generates a valid test CSRF token for protected unsafe methods.

**13. Does MockMvc use real TCP sockets?**  
No, in mock web environments. Use `RANDOM_PORT` to test a real HTTP server.

**14. Does `curl` enforce browser CORS?**  
No. Browsers enforce cross-origin access restrictions.

**15. Is allowing credentials with `Origin=*` valid?**  
Incompatible with browser CORS credential semantics; use exact trusted origins.

**16. Can a filter run on a 404?**  
Yes, filters run before `HandlerMapping`; an interceptor may not run.

**17. With two `SecurityFilterChain` beans, which chain is selected?**  
The first chain matching the request by order; a fallback is needed so URLs are not left unprotected.

**18. When CORS is allowed yet an actual private GET is anonymous, what should the lab return?**  
401, and it may still carry the `Allow-Origin` header.

**19. Why test rejected Origins?**  
To catch overly permissive policies, not just confirm the happy path.

**20. On WebFlux, should you copy MVC `HandlerInterceptor`?**  
No. Use `WebFilter`, `SecurityWebFilterChain`, and `WebTestClient` for the reactive stack.

## 23. Official References

- [Spring Boot 3.3 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@WebMvcTest`, `@SpringBootTest`, `@AutoConfigureMockMvc`, and `RANDOM_PORT`.
- [Spring Framework – Spring MVC CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): preflight and actual request handling.
- [Spring Framework – MVC Interceptors](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/interceptors.html): `HandlerInterceptor` callbacks and security caveats.
- [Spring Framework – Filters](https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html): Servlet filter integration, async dispatcher types.
- [Spring Framework 6.1 – OncePerRequestFilter](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/filter/OncePerRequestFilter.html): async/error dispatch and once-per-dispatch semantics.
- [Spring Security 6.3 – CORS Servlet Integration](https://docs.spring.io/spring-security/reference/6.3/servlet/integrations/cors.html): preflight must be processed before authentication.
- [Spring Security – Servlet Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `DelegatingFilterProxy`, `FilterChainProxy`, `SecurityFilterChain`.
- [Spring Security – MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): `springSecurity()` configurer.
- [Spring Security – MockMvc Request Post Processors](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html): `user()`, `httpBasic()`, and authentication testing.
- [Spring Security – Testing with CSRF](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html): `with(csrf())` and negative tests.
- [Spring Security – Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): `requestMatchers`, role constraints, and fallback.
- [Spring Boot 3.3 – Servlet Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/servlet.html): Servlet stack and filters.
- [Spring Boot 3.3 – Test Auto-Configuration](https://docs.spring.io/spring-boot/3.3/appendix/test-auto-configuration/slices.html): slice boundaries.
- [MDN – Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS): browser semantics.
- [OWASP – CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF threat model.

**Conclusion:** Reliable web runtime testing requires knowing **which layer** handles each request. Filters run at the Servlet level, Interceptors at the MVC handler level, CORS governs browser cross-origin access, and Spring Security owns authentication, authorization, and CSRF. An allowed preflight **does not** mean the actual request is authorized; a test with filters disabled **is not** proof of security.