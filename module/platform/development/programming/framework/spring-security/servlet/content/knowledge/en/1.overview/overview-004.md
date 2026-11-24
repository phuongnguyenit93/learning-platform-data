# Request Flow from Browser to Security Filters, MVC, and the Business Layer

## 1. Objective and Big Picture

In a **Spring Boot application using the Servlet stack** (for example, Spring MVC on Tomcat), an HTTP request does not go directly from the browser into a `@RestController`. The Servlet container passes the request through registered `Filter`s; Spring Security typically participates here, **before** `DispatcherServlet` selects a controller. After the request clears HTTP-level security, MVC code and the business layer process the request. Method- or data-level access controls may continue to execute **inside the business layer**.

Running example: a browser or HTTP client calls `GET /orders/42`. The system needs to distinguish: who is calling, whether they are allowed to call this path, and whether they have permission to view **order 42 specifically**.

~~~text
Browser / HTTP client
    |  HTTPS request: method, path, headers, cookies, body
    v
Reverse proxy / TLS termination (if any)
    |
    v
Servlet container (Tomcat/Jetty; creates HttpServletRequest/Response)
    |
    v
Servlet Filters, commonly including:
  DelegatingFilterProxy("springSecurityFilterChain")
    -> FilterChainProxy
       -> SecurityFilterChain matching the request
          -> Spring Security filters
    |
    | request allowed to proceed
    v
DispatcherServlet (Spring MVC)
    -> HandlerMapping / HandlerAdapter
    -> Controller (parse input, validate, call service)
    -> Service (business logic, resource-level permission checks)
    -> Repository / database / external systems
    |
    v
HTTP response travels back through MVC, Servlet filters, and container
    |
    v
Browser / HTTP client
~~~

**Scope distinction:** this document describes Spring Security on the **Servlet stack** (`SecurityFilterChain`, `HttpSecurity`, `HttpServletRequest`). For Spring WebFlux, the pipeline is `WebFilter`/`SecurityWebFilterChain` with reactive processing, so the Servlet classes above do not apply verbatim.

## 2. Who Is Responsible at Each Layer?

| Component | Role in Request Processing | Misconceptions to Avoid |
| --- | --- | --- |
| Browser/client | Sends URL, method, session cookie, `Authorization` header, body | Cookie presence alone does not prove the user is authenticated |
| Servlet container | Receives HTTP, creates Servlet request/response objects, runs the filter chain | The container does not automatically enforce all Spring Security rules |
| `DelegatingFilterProxy` | Bridge from the Servlet Filter mechanism to the Spring bean `springSecurityFilterChain` | This is not where individual access rules are defined |
| `FilterChainProxy` | Selects the matching Spring Security `SecurityFilterChain` and coordinates security filters | A request does not run **every** chain by default |
| Authentication filters/providers | Reads appropriate credentials, verifies identity, sets `Authentication` | Having authentication does not mean access to every resource |
| `AuthorizationFilter` | Checks HTTP access permissions according to `authorizeHttpRequests` | Does not automatically enforce ownership of individual records |
| `ExceptionTranslationFilter` | Translates security exceptions from downstream into 401/403 responses or appropriate login redirects | Not a filter that performs authentication or makes authorization decisions itself |
| `DispatcherServlet` + controller | Selects handler, performs binding/validation, calls service, builds response | Controller is not the sole enforcement point |
| Service/repository | Executes business logic, checks resource-specific rules, reads/writes data | Passing security filters is not enough to skip ownership checks |

Servlet `Filter` and Spring MVC `HandlerInterceptor` are two different mechanisms. Interceptors run during MVC dispatch, after the request has already passed upstream filters; therefore HTTP authentication/authorization should live in the Spring Security filter chain, while business rules should be enforced in the service.

## 3. Tracing a Request: From Browser to Controller

### Step 1 — Client Creates an HTTP Request

A request carries a method (`GET`, `POST`...), path (`/orders/42`), headers, optional body, and possibly cookies or authentication headers. Use **HTTPS** to protect data in transit. With session-based login, the browser usually sends a cookie carrying a **session ID**, while login state resides on the server. With bearer tokens, the client sends `Authorization: Bearer <token>` and the server validates the token as configured. HTTP Basic sends Base64-encoded credentials, **which is not security encryption**; only use it over HTTPS.

A reverse proxy may terminate TLS and forward the request to the application. When reading client address or scheme from `Forwarded`/`X-Forwarded-*`, trust headers only when controlled by a trusted proxy; do not rely on client-supplied values for authorization decisions.

### Step 2 — Servlet Container Invokes Filters Before MVC

The container selects Servlet filters matching the URL and dispatcher type. In common Spring Boot/Spring Security setups, `DelegatingFilterProxy` points to a bean named `springSecurityFilterChain`. This bean is usually `FilterChainProxy`, which internally manages one or more `SecurityFilterChain`s.

Easily confused names:

- **Servlet filter chain:** the container-managed filter chain, which may include logging, encoding, and `DelegatingFilterProxy`.
- **Spring Security filter chain:** the security filters inside `FilterChainProxy`.
- **`SecurityFilterChain`:** configuration of a security filter sequence applied to a specific set of requests.

A request may traverse several Servlet filters, but `FilterChainProxy` picks the **first matching SecurityFilterChain** in order. When using multiple chains, `securityMatcher(...)` defines the scope for selecting the chain; `requestMatchers(...)` inside `authorizeHttpRequests` defines permissions **inside the selected chain**. A URL left uncovered by any chain can result in that URL having no Spring Security protection.

### Step 3 — Security Filters Do Their Work

Actual filter order depends on configuration and login mechanisms. Common roles in Spring Security 6 include:

1. **Security context:** `SecurityContextHolderFilter` loads or prepares `SecurityContext` via `SecurityContextRepository`. `SecurityContextHolder` allows code during the request to look up the current `Authentication`. In Spring Security 6, do not assume every context mutation is automatically saved: the appropriate login mechanism must save the context if state needs to persist.
2. **HTTP security headers, CORS, CSRF:** when configured, the corresponding filters handle protective headers, CORS, and CSRF. CSRF is especially important for state-changing requests when browsers automatically send credentials like session cookies.
3. **Authentication:** depending on the application, `UsernamePasswordAuthenticationFilter` handles form login, `BasicAuthenticationFilter` handles HTTP Basic, and `BearerTokenAuthenticationFilter` handles bearer tokens. Not all of them are present in every application.
4. **Anonymous authentication:** when no authenticated identity exists yet, `AnonymousAuthenticationFilter` may place an anonymous authentication object. Hence checking only `getAuthentication() != null` is **insufficient** to conclude a user is logged in.
5. **Authorization:** `AuthorizationFilter` enforces rules such as `permitAll()`, `authenticated()`, `hasRole(...)`. It can reject a request before MVC is invoked.
6. **Exception translation:** `ExceptionTranslationFilter` handles `AuthenticationException` or `AccessDeniedException` thrown in the downstream filters/handlers it wraps, via `AuthenticationEntryPoint` or `AccessDeniedHandler`.

These are **roles**, not an exact ordering diagram for every configuration. For instance, `ExceptionTranslationFilter` must sit ahead of `AuthorizationFilter` in call order to catch exceptions thrown by authorization downstream.

Authentication typically has its own flow:

~~~text
Authentication filter reads credentials
   -> AuthenticationManager (usually ProviderManager)
   -> Appropriate AuthenticationProvider
      -> UserDetailsService + PasswordEncoder (e.g., user/password)
      or JwtDecoder / token validation (e.g., JWT)
   -> Valid Authentication + authorities
   -> SecurityContextHolder holds Authentication for the request
   -> Appropriate mechanism saves SecurityContext if login persistence is needed
~~~

`principal` is the identity (usually username/user object); `authorities` are the permissions (e.g., `ROLE_USER`). With `hasRole("ADMIN")`, the default convention equates to looking for authority `ROLE_ADMIN`; do not manually prepend `ROLE_` twice inside `hasRole`.

### Step 4 — Deciding to Proceed or Block

Separate three questions:

1. **Authentication:** who is the client? Are the credentials valid?
2. **HTTP authorization:** is that identity allowed to reach `/orders/**`?
3. **Resource/business authorization:** is this person allowed to read **order ID 42**?

If HTTP policy requires `authenticated()` and the request is unauthenticated, Spring Security typically invokes the entry point: for APIs using HTTP Basic/bearer, this is **401 Unauthorized**; for web form login, it may be a **302 redirect** to the login page. If the user is authenticated but lacks permission, the response is typically **403 Forbidden**. Details depend on the configured authentication entry point and access denied handler.

If authentication/authorization fails in a filter, **the controller and service do not run**. For a request that succeeds at the filter layer, the call continues to Servlet/MVC; that **does not guarantee** a controller has a matching mapping, the request is valid, or the user owns the requested record.

### Step 5 — DispatcherServlet Routes the Request into MVC

`DispatcherServlet` is Spring MVC's front controller. It uses `HandlerMapping` to locate a handler matching path/method; `HandlerAdapter` invokes the controller along with resolvers for `@PathVariable`, `@RequestParam`, `@RequestBody`, validation... If no mapping exists, the result is usually 404 (depending on configuration, and filters may already have blocked earlier).

Example:

~~~java
@GetMapping("/orders/{id}")
public String getOrder(@PathVariable long id) {
    return orderService.findOrderForCurrentUser(id);
}
~~~

Here the controller receives the ID and **delegates to the service**. Do not trust fields such as a client-sent `userId` merely because the request passed `authenticated()`.

### Step 6 — Service Executes Business Logic and Checks Data Permissions

In the service, a method can be protected by Spring Method Security (for example, `@PreAuthorize` when `@EnableMethodSecurity` is present). Beyond checking roles, ownership or access scope rules must be enforced on the **exact resource**. For instance, a successfully authenticated user still must not retrieve `/orders/42` if that order belongs to another user.

One approach to prevent IDOR/BOLA is binding queries to the current user/tenant, conceptually `findByIdAndOwnerId(orderId, currentUserId)`, or checking ownership explicitly before returning data. For proxy-based method security, calls **through the Spring bean/proxy** are intercepted as expected; calling an annotated method internally within the same instance (self-invocation) usually bypasses the proxy.

The repository layer accesses data; `@Transactional` manages transactions if present, and **does not replace authorization rules**. Input errors, missing data, business errors, or database errors can become different HTTP status codes depending on controller/exception handler translation.

### Step 7 — Returning the Response in Reverse Order

The controller/MVC writes HTTP status, headers, and body; servlet filters finish in reverse call order, potentially adding headers, saving or clearing context per their mechanism, and then the container sends the response. In the standard flow, the request-bound security context is cleared after the request completes to avoid leaking identity to another request on a reused thread.

Async/error dispatch cases may traverse different dispatcher types and filters depending on configuration. When debugging a forwarded request, a 404/500 error, or asynchronous processing, determine the **dispatcher type** and do not assume filters run only once.

## 4. Complete Example: Spring Boot 3.x / Spring Security 6.x

The following example uses Java 17+, Spring MVC, HTTP Basic, and in-memory users **solely to observe the flow**. It clearly illustrates the boundary: filters decide whether the caller is logged in; the service checks which user a specific order belongs to. Use `{noop}` credentials only in local demos; real applications need password hashing, a database/identity provider, and HTTPS.

Structure:

~~~text
security-flow/
├── pom.xml
└── src/main/java/com/example/flow/
    ├── SecurityFlowApplication.java
    ├── SecurityConfig.java
    ├── OrderController.java
    └── OrderService.java
~~~

**`pom.xml`**

~~~xml
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
    <artifactId>security-flow</artifactId>
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

**`SecurityFlowApplication.java`**

~~~java
package com.example.flow;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityFlowApplication {
    public static void main(String[] args) {
        SpringApplication.run(SecurityFlowApplication.class, args);
    }
}
~~~

**`SecurityConfig.java`**

~~~java
package com.example.flow;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers("/orders/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("alice").password("{noop}pass").roles("USER").build(),
            User.withUsername("bob").password("{noop}pass").roles("USER").build()
        );
    }
}
~~~

`authorizeHttpRequests` protects paths before MVC. `permitAll()` allows entry to the public endpoint, though requests can still pass through the Spring Security filter chain. `authenticated()` verifies there is a logged-in identity; it does not check order ownership. `anyRequest().denyAll()` closes undeclared paths. The configuration still **keeps CSRF at default**; all illustrated endpoints use GET only. Do not infer from this example that every Basic-authenticated API should disable CSRF, especially when browsers can automatically send credentials.

**`OrderController.java`**

~~~java
package com.example.flow;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/public")
    String publicEndpoint() {
        return "OK public";
    }

    @GetMapping("/orders/{id}")
    String order(@PathVariable long id) {
        return orderService.findOrderForCurrentUser(id);
    }
}
~~~

**`OrderService.java`**

~~~java
package com.example.flow;

import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
class OrderService {

    @PreAuthorize("isAuthenticated()")
    public String findOrderForCurrentUser(long id) {
        Authentication authentication =
            SecurityContextHolder.getContext().getAuthentication();

        // Simulated data: only order 42 exists, belonging to alice.
        if (id != 42) {
            throw new ResponseStatusException(
                HttpStatus.NOT_FOUND, "Order not found");
        }
        if (!"alice".equals(authentication.getName())) {
            throw new AccessDeniedException("Not the order owner");
        }
        return "Order 42 belongs to alice";
    }
}
~~~

`@EnableMethodSecurity` enables intercepting `@PreAuthorize` when the controller calls the service bean through a Spring proxy. The check inside the service is a demo for easy observation; real systems should determine the owner from the database and a trusted principal, with policies to hide resource existence when appropriate.

Run in the directory containing `pom.xml` (requires JDK 17+ and Maven; first-time dependency download requires network access):

~~~bash
mvn spring-boot:run
~~~

Test each case with `curl`; to print only the status code (independent of dynamic headers), use:

~~~bash
curl -s http://localhost:8080/public
# OK public

curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8080/orders/42
# 401

curl -s -o /dev/null -w '%{http_code}\n' -u alice:pass http://localhost:8080/orders/42
# 200

curl -s -u alice:pass http://localhost:8080/orders/42
# Order 42 belongs to alice

curl -s -o /dev/null -w '%{http_code}\n' -u bob:pass http://localhost:8080/orders/42
# 403

curl -s -o /dev/null -w '%{http_code}\n' -u alice:pass http://localhost:8080/orders/999
# 404
~~~

Lines starting with `#` here are **expected results**/comments for each command, not measured output from the current environment. On Windows PowerShell, use `curl.exe` instead of the `curl` alias if needed. The server listens on port 8080 by default if unchanged.

### Reading the Flow Across 5 Scenarios

| Request | Security Filter | MVC/Service | Expected Result |
| --- | --- | --- | --- |
| `GET /public` without credentials | `permitAll` | Controller returns string | 200 |
| `GET /orders/42` without credentials | Requires authenticated; Basic entry point handles it | Does not enter controller | 401 |
| `GET /orders/42` with alice | Basic auth succeeds; `authenticated` passes | Controller → service; owner is alice | 200 |
| `GET /orders/42` with bob | Authenticated, so **passes** path policy | Service detects not owner, throws `AccessDeniedException` | 403 |
| `GET /orders/999` with alice | Both auth and path policy pass | Service does not find the order | 404 |

Note bob's case: if only `.authenticated()` were checked, the application would fail to block order access. This is why **HTTP authorization** must be separated from **business object permissions**.

## 5. Common Pitfalls in Real Applications

### 401, 403, 404, and 400/500 Come from Different Layers

- **401 Unauthorized:** request is not validly authenticated for a login-required resource; often includes `WWW-Authenticate` in HTTP Basic/bearer APIs.
- **403 Forbidden:** user is authenticated but lacks permission; can also be caused by a missing/invalid CSRF token on a CSRF-protected request.
- **404 Not Found:** after passing appropriate protection, MVC has no mapping or the data layer finds nothing; depending on design, 404 may be returned to avoid disclosing resource existence.
- **400 Bad Request:** malformed input, binding, validation... typically handled by MVC once the request travels far enough.
- **500 Internal Server Error:** improperly handled error; do not turn every service failure into 401/403.

You cannot deduce the error layer **solely from the status code**, because an application can configure custom entry points, error handlers, and exception mappings. Combine the status with logs, dispatcher type, and actual traces.

### CORS and CSRF Do Not Replace Authentication/Authorization

**CORS** is a browser policy specifying which origin's JavaScript may read responses; an `OPTIONS` preflight usually carries no credentials. When using CORS, configure preflight handling in the right order relative to auth (for example, `http.cors(...)` with appropriate CORS configuration). CORS does **not** make an endpoint protected and does not block non-browser clients.

**CSRF** protects state-changing requests against unintended actions when the browser automatically attaches credentials. With sessions/cookies, keep CSRF protection on for POST/PUT/PATCH/DELETE. An API using bearer tokens explicitly placed in headers by the client and not using auto-sent credentials may have a different CSRF model, but you must thoroughly evaluate the authentication mechanism before disabling it. GET should only read data and not mutate state.

### Session, Bearer Token, and "Logged In"

- **Session-based:** cookies usually carry only an ID; the server uses `HttpSession`/`SecurityContextRepository` to associate requests with login state when configured appropriately.
- **Bearer token:** filters verify the token on each request per configuration; do not assume tokens must be tied to an HTTP session.
- **Basic authentication:** requests carry credentials; `Authorization: Basic ...` does not automatically become a session login.
- **Anonymous:** an anonymous `Authentication` may exist in the context. To require a real user, use `authenticated()`/method security appropriately instead of merely checking non-null.

An HTTP authorization layer does not guarantee owner-, tenant-, or data-scope permissions. Conversely, `@PreAuthorize` on a service does not replace HTTP rules for endpoints that need to be blocked upfront.

### `permitAll` Differs from Bypassing the Security Chain

`requestMatchers("/public").permitAll()` still sends requests through the security chain, so applicable filters and security headers can still run. Configuring `web.ignoring()` skips the entire Spring Security filter chain for matching requests; careless use loses filter-level protections. For ordinary public endpoints, prefer `permitAll`.

### When Having Multiple SecurityFilterChains

`@Order` determines chain order, and `securityMatcher` determines whether a request belongs to a chain. The first matching chain is selected; rules inside one chain are not combined from another. When creating a dedicated chain for `/api/**`, check which requests match no chain and whether a fallback chain covers the remainder.

## 6. How to Debug a Misrouted Request

1. **Identify the real request:** method, path, query, origin, whether cookies/`Authorization` are present; never log raw passwords/tokens.
2. **Inspect the response:** status, `WWW-Authenticate`, `Location` (redirect), CORS headers, CSRF-related errors. If 401/403, determine which mechanism rejected it.
3. **Check the matching chain:** if multiple `SecurityFilterChain`s exist, inspect `securityMatcher` and `@Order` ordering. Remember to distinguish `securityMatcher` from `requestMatchers`.
4. **Trace identity:** check whether the authentication filter/provider ran, and what principal/authorities are present; do not treat the presence of anonymous as a successful login.
5. **If it passed the filters:** inspect MVC mappings, binding/validation, `@PreAuthorize`, and owner/tenant checks in the service; verify actual data.
6. **Observe controlled logs:** in development environments, configure `logging.level.org.springframework.security=DEBUG` to see chain/authorization details. Do not enable sensitive logging indiscriminately in production, and never print full secrets/cookies.

A helpful dividing signal: if the controller is not called, check filters/chains and mappings first. If the controller is called but the service rejects it, check method security or data rules. However, MVC mapping, CORS, CSRF, or exception handler issues can complicate initial observation, so rely on traces rather than absolute assumptions.

## 7. Self-Check Your Understanding

**Q:** A user is authenticated and passes `.requestMatchers("/orders/**").authenticated()`—can they view every order?

**A:** No. That rule only requires being logged in at the HTTP level; the service/repository must still verify the user has permission on the requested order.

**Q:** Why can `GET /orders/42` without credentials return 401 without logging inside the controller?

**A:** The security filter chain runs before `DispatcherServlet`; `AuthorizationFilter` rejects the request requiring authentication, and `ExceptionTranslationFilter` triggers the Basic authentication entry point.

**Q:** Is Spring MVC's `HandlerInterceptor` equivalent to a Spring Security filter?

**A:** No. MVC interceptors run during MVC dispatch; security filters can block requests at the Servlet layer before any controller runs.

**Remember the path:** **Client → Servlet filters → Spring Security authentication/HTTP authorization → DispatcherServlet/MVC → service + data-level permissions → repository → response**. Each layer handles a distinct responsibility; the final outcome is secure only when all layers enforce the right policies together.